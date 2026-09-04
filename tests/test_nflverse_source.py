import csv
import gzip
import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone

from fantasy_draft.sources.nflverse import (
    NflverseSourceError,
    NflverseStyleQuery,
    derive_nflverse_style_window,
    parse_nflverse_style,
    write_nflverse_style_snapshot,
)


PBP_FIELDS = [
    "season",
    "season_type",
    "week",
    "game_id",
    "play_id",
    "posteam",
    "qtr",
    "down",
    "yardline_100",
    "play_type",
    "yards_gained",
    "shotgun",
    "no_huddle",
    "qb_kneel",
    "qb_spike",
    "qb_scramble",
    "air_yards",
    "epa",
    "wp",
    "receiver_player_id",
    "rusher_player_id",
    "success",
    "pass",
    "rush",
    "pass_oe",
]


def gzipped_csv(fields: list[str], rows: list[dict[str, object]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return gzip.compress(stream.getvalue().encode("utf-8"))


def roster_fixture() -> bytes:
    return gzip.decompress(gzipped_csv(
        ["season", "team", "position", "gsis_id"],
        [
            {"season": 2025, "team": "SEA", "position": "WR", "gsis_id": "wr1"},
            {"season": 2025, "team": "SEA", "position": "QB", "gsis_id": "qb1"},
            {"season": 2025, "team": "KC", "position": "TE", "gsis_id": "te1"},
        ],
    ))


def pbp_fixture() -> bytes:
    defaults: dict[str, object] = {
        "season": 2025,
        "season_type": "REG",
        "week": 1,
        "game_id": "2025_01_SEA_KC",
        "play_id": 10,
        "posteam": "SEA",
        "qtr": 1,
        "down": 1,
        "yardline_100": 50,
        "play_type": "pass",
        "yards_gained": 0,
        "shotgun": 0,
        "no_huddle": 0,
        "qb_kneel": 0,
        "qb_spike": 0,
        "qb_scramble": 0,
        "air_yards": "",
        "epa": 0,
        "wp": 0.5,
        "receiver_player_id": "",
        "rusher_player_id": "",
        "success": 0,
        "pass": 1,
        "rush": 0,
        "pass_oe": 0,
    }

    def row(**values: object) -> dict[str, object]:
        return {**defaults, **values}

    return gzipped_csv(
        PBP_FIELDS,
        [
            row(
                yardline_100=20,
                yards_gained=25,
                shotgun=1,
                no_huddle=1,
                air_yards=20,
                epa=1.2,
                receiver_player_id="wr1",
                success=1,
                pass_oe=0.10,
            ),
            row(
                play_id=20,
                down=2,
                yardline_100=10,
                play_type="run",
                yards_gained=12,
                rusher_player_id="qb1",
                success=1,
                pass_oe=-0.20,
                **{"pass": 0, "rush": 1},
            ),
            row(
                play_id=30,
                down=2,
                play_type="run",
                yards_gained=5,
                shotgun=1,
                qb_scramble=1,
                rusher_player_id="qb1",
                pass_oe=0.05,
                **{"pass": 1, "rush": 0},
            ),
            row(
                play_id=40,
                play_type="run",
                yards_gained=-1,
                qb_kneel=1,
                rusher_player_id="qb1",
                **{"pass": 0, "rush": 1},
            ),
            row(
                play_id=50,
                posteam="KC",
                receiver_player_id="te1",
                air_yards=8,
                yards_gained=9,
                success=1,
                epa=0.5,
            ),
        ],
    )


class NflverseSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.query = NflverseStyleQuery((2025,), include_ftn_charting=False)
        self.retrieved_at = datetime(2026, 9, 2, 20, 0, tzinfo=timezone.utc)

    def test_query_normalizes_seasons_and_rejects_duplicates(self) -> None:
        self.assertEqual(NflverseStyleQuery((2025, 2023, 2024)).seasons, (2023, 2024, 2025))
        with self.assertRaisesRegex(ValueError, "duplicates"):
            NflverseStyleQuery((2025, 2025))

    def test_derives_style_and_position_target_shares(self) -> None:
        snapshot = parse_nflverse_style(
            self.query,
            play_by_play={2025: pbp_fixture()},
            rosters={2025: roster_fixture()},
            retrieved_at=self.retrieved_at,
        )
        records = {record.team: record for record in snapshot.records}
        sea = records["SEA"]

        self.assertEqual(sea.plays, 3)
        self.assertAlmostEqual(sea.pass_rate, 2 / 3)
        self.assertAlmostEqual(sea.neutral_early_down_pass_rate or 0, 2 / 3)
        self.assertAlmostEqual(sea.neutral_pass_oe or 0, -1 / 60)
        self.assertAlmostEqual(sea.shotgun_rate or 0, 2 / 3)
        self.assertAlmostEqual(sea.red_zone_pass_rate or 0, 0.5)
        self.assertEqual(sea.deep_attempt_rate, 1.0)
        self.assertEqual(sea.qb_scramble_rate, 0.5)
        self.assertEqual(sea.designed_qb_run_share, 1.0)
        self.assertEqual(sea.wr_target_share, 1.0)
        self.assertAlmostEqual(sea.explosive_play_rate or 0, 2 / 3)
        self.assertIsNone(sea.ftn_coverage_rate)
        self.assertEqual(records["KC"].te_target_share, 1.0)

    def test_rejects_missing_source_columns(self) -> None:
        bad_pbp = gzipped_csv([field for field in PBP_FIELDS if field != "pass_oe"], [])
        with self.assertRaisesRegex(NflverseSourceError, "pass_oe"):
            parse_nflverse_style(
                self.query,
                play_by_play={2025: bad_pbp},
                rosters={2025: roster_fixture()},
                retrieved_at=self.retrieved_at,
            )

    def test_joins_ftn_charting_by_game_and_play(self) -> None:
        ftn = gzipped_csv(
            [
                "nflverse_game_id",
                "nflverse_play_id",
                "season",
                "qb_location",
                "n_offense_backfield",
                "is_motion",
                "is_play_action",
                "is_screen_pass",
                "is_rpo",
                "is_trick_play",
                "is_qb_out_of_pocket",
                "is_qb_sneak",
            ],
            [
                {
                    "nflverse_game_id": "2025_01_SEA_KC",
                    "nflverse_play_id": 10,
                    "season": 2025,
                    "qb_location": "S",
                    "n_offense_backfield": 1,
                    "is_motion": "TRUE",
                    "is_play_action": "TRUE",
                    "is_screen_pass": "FALSE",
                    "is_rpo": "FALSE",
                    "is_trick_play": "FALSE",
                    "is_qb_out_of_pocket": "FALSE",
                    "is_qb_sneak": "FALSE",
                },
                {
                    "nflverse_game_id": "2025_01_SEA_KC",
                    "nflverse_play_id": 20,
                    "season": 2025,
                    "qb_location": "U",
                    "n_offense_backfield": 2,
                    "is_motion": "TRUE",
                    "is_play_action": "FALSE",
                    "is_screen_pass": "FALSE",
                    "is_rpo": "TRUE",
                    "is_trick_play": "FALSE",
                    "is_qb_out_of_pocket": "FALSE",
                    "is_qb_sneak": "TRUE",
                },
                {
                    "nflverse_game_id": "2025_01_SEA_KC",
                    "nflverse_play_id": 30,
                    "season": 2025,
                    "qb_location": "P",
                    "n_offense_backfield": 1,
                    "is_motion": "FALSE",
                    "is_play_action": "FALSE",
                    "is_screen_pass": "TRUE",
                    "is_rpo": "FALSE",
                    "is_trick_play": "FALSE",
                    "is_qb_out_of_pocket": "TRUE",
                    "is_qb_sneak": "FALSE",
                },
                {
                    "nflverse_game_id": "2025_01_SEA_KC",
                    "nflverse_play_id": 50,
                    "season": 2025,
                    "qb_location": "S",
                    "n_offense_backfield": 1,
                    "is_motion": "FALSE",
                    "is_play_action": "FALSE",
                    "is_screen_pass": "FALSE",
                    "is_rpo": "FALSE",
                    "is_trick_play": "FALSE",
                    "is_qb_out_of_pocket": "FALSE",
                    "is_qb_sneak": "FALSE",
                },
            ],
        )
        snapshot = parse_nflverse_style(
            NflverseStyleQuery((2025,), include_ftn_charting=True),
            play_by_play={2025: pbp_fixture()},
            rosters={2025: roster_fixture()},
            ftn_charting={2025: ftn},
            retrieved_at=self.retrieved_at,
        )
        sea = next(record for record in snapshot.records if record.team == "SEA")

        self.assertAlmostEqual(sea.under_center_rate or 0, 1 / 3)
        self.assertAlmostEqual(sea.pistol_rate or 0, 1 / 3)
        self.assertAlmostEqual(sea.motion_rate or 0, 2 / 3)
        self.assertAlmostEqual(sea.play_action_rate or 0, 0.5)
        self.assertAlmostEqual(sea.screen_pass_rate or 0, 0.5)
        self.assertAlmostEqual(sea.rpo_rate or 0, 1 / 3)
        self.assertAlmostEqual(sea.multi_back_rate or 0, 1 / 3)
        self.assertAlmostEqual(sea.qb_out_of_pocket_rate or 0, 0.5)
        self.assertAlmostEqual(sea.qb_sneak_rate or 0, 1 / 3)
        self.assertEqual(sea.ftn_coverage_rate, 1.0)

    def test_derives_an_inseason_week_window(self) -> None:
        rows = list(csv.DictReader(io.StringIO(gzip.decompress(pbp_fixture()).decode())))
        rows[0]["week"] = "1"
        rows[0]["game_id"] = "2025_01_SEA_KC"
        rows[1]["week"] = "2"
        rows[1]["game_id"] = "2025_02_SEA_KC"
        rows[2]["week"] = "3"
        rows[2]["game_id"] = "2025_03_SEA_KC"
        rows[3]["week"] = "3"
        rows[3]["game_id"] = "2025_03_SEA_KC"
        rows[4]["week"] = "3"
        rows[4]["game_id"] = "2025_03_SEA_KC"
        window = derive_nflverse_style_window(
            season=2025,
            week_start=1,
            week_end=2,
            play_by_play=gzipped_csv(PBP_FIELDS, rows),
            roster=roster_fixture(),
        )

        self.assertEqual(len(window), 1)
        self.assertEqual(window[0].team, "SEA")
        self.assertEqual(window[0].games, 2)
        self.assertEqual(window[0].plays, 2)
        self.assertEqual(window[0].pass_rate, 0.5)

    def test_rejects_an_invalid_week_window(self) -> None:
        with self.assertRaisesRegex(ValueError, "week window"):
            derive_nflverse_style_window(
                season=2025,
                week_start=8,
                week_end=6,
                play_by_play=pbp_fixture(),
                roster=roster_fixture(),
            )

    def test_writes_normalized_snapshot_and_manifest(self) -> None:
        snapshot = parse_nflverse_style(
            self.query,
            play_by_play={2025: pbp_fixture()},
            rosters={2025: roster_fixture()},
            retrieved_at=self.retrieved_at,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = write_nflverse_style_snapshot(snapshot, directory)
            normalized = (path / "team_style.csv").read_bytes()
            manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(path.name, "20260902T200000.000000Z")
            self.assertEqual(manifest["quality"]["record_count"], 2)
            self.assertEqual(manifest["quality"]["teams_per_season"], {"2025": 2})
            self.assertEqual(
                manifest["artifacts"]["normalized"]["sha256"],
                hashlib.sha256(normalized).hexdigest(),
            )
            with self.assertRaises(FileExistsError):
                write_nflverse_style_snapshot(snapshot, directory)


if __name__ == "__main__":
    unittest.main()
