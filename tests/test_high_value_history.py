import csv
import gzip
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from fantasy_draft.high_value_history import (
    HighValueHistoryDataError,
    build_high_value_history,
    write_high_value_history_snapshot,
)


def csv_bytes(fields, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


PBP_FIELDS = [
    "season", "season_type", "week", "game_id", "play_id", "posteam",
    "qtr", "down", "yardline_100", "half_seconds_remaining", "ydstogo",
    "goal_to_go", "air_yards", "qb_kneel", "qb_spike", "qb_scramble",
    "pass", "rush", "receiver_player_id", "receiver_player_name",
    "rusher_player_id", "rusher_player_name",
]
ROSTER_FIELDS = ["season", "position", "gsis_id", "full_name"]
FTN_FIELDS = ["season", "nflverse_game_id", "nflverse_play_id", "read_thrown"]


class HighValueHistoryTests(unittest.TestCase):
    def make_source(
        self, root: Path, *, include_ftn: bool = True, season: int = 2024
    ) -> Path:
        source = root / "team-style"
        raw_root = source / "raw"
        raw_root.mkdir(parents=True)
        roster = csv_bytes(ROSTER_FIELDS, [
            {"season": season, "position": "WR", "gsis_id": "w1", "full_name": "Wide One"},
            {"season": season, "position": "FB", "gsis_id": "r1", "full_name": "Back One"},
            {"season": season, "position": "QB", "gsis_id": "q1", "full_name": "Quarter One"},
        ])
        base = {
            "season": season, "season_type": "REG", "week": 1,
            "game_id": "2024_01_AAA_BBB", "posteam": "AAA",
            "qb_kneel": 0, "qb_spike": 0, "qb_scramble": 0,
            "receiver_player_id": "", "receiver_player_name": "",
            "rusher_player_id": "", "rusher_player_name": "",
        }
        rows = [
            {**base, "play_id": 1, "qtr": 2, "down": 3, "yardline_100": 8, "half_seconds_remaining": 90, "ydstogo": 8, "goal_to_go": 0, "air_yards": 8, "pass": 1, "rush": 0, "receiver_player_id": "w1", "receiver_player_name": "Wide One"},
            {**base, "play_id": 2, "qtr": 1, "down": 1, "yardline_100": 50, "half_seconds_remaining": 1700, "ydstogo": 10, "goal_to_go": 0, "air_yards": 20, "pass": 1, "rush": 0, "receiver_player_id": "w1", "receiver_player_name": "Wide One"},
            {**base, "play_id": 3, "qtr": 4, "down": 3, "yardline_100": 4, "half_seconds_remaining": 60, "ydstogo": 1, "goal_to_go": 1, "air_yards": "", "pass": 0, "rush": 1, "rusher_player_id": "r1", "rusher_player_name": "Back One"},
            {**base, "play_id": 4, "qtr": 1, "down": 1, "yardline_100": 15, "half_seconds_remaining": 1500, "ydstogo": 10, "goal_to_go": 0, "air_yards": "", "pass": 0, "rush": 1, "rusher_player_id": "q1", "rusher_player_name": "Quarter One"},
            {**base, "play_id": 5, "qtr": 4, "down": 1, "yardline_100": 40, "half_seconds_remaining": 30, "ydstogo": 10, "goal_to_go": 0, "air_yards": "", "pass": 0, "rush": 1, "qb_kneel": 1, "rusher_player_id": "q1", "rusher_player_name": "Quarter One"},
        ]
        pbp = gzip.compress(csv_bytes(PBP_FIELDS, rows))
        assets = {
            f"play_by_play_{season}.csv.gz": pbp,
            f"roster_{season}.csv": roster,
        }
        if include_ftn:
            assets[f"ftn_charting_{season}.csv"] = csv_bytes(FTN_FIELDS, [
                {"season": season, "nflverse_game_id": base["game_id"], "nflverse_play_id": 1, "read_thrown": 0},
                {"season": season, "nflverse_game_id": base["game_id"], "nflverse_play_id": 2, "read_thrown": "DES"},
            ])
        raw_manifest = {}
        for name, raw in assets.items():
            (raw_root / name).write_bytes(raw)
            raw_manifest[name] = {
                "sha256": hashlib.sha256(raw).hexdigest(),
                "url": f"https://example.test/{name}",
            }
        (source / "manifest.json").write_text(json.dumps({
            "query": {"seasons": [season], "season_type": "REG"},
            "artifacts": {"raw": raw_manifest},
        }))
        return source

    def test_derives_high_value_counts_by_gsis_id(self):
        with tempfile.TemporaryDirectory() as directory:
            result = build_high_value_history(self.make_source(Path(directory)))
            wide = next(row for row in result.weekly_rows if row["gsis_id"] == "w1")
            back = next(row for row in result.weekly_rows if row["gsis_id"] == "r1")
            qb = next(row for row in result.weekly_rows if row["gsis_id"] == "q1")
            self.assertEqual(wide["targets"], 2)
            self.assertEqual(wide["first_read_targets"], 1)
            self.assertEqual(wide["designed_targets"], 1)
            self.assertEqual(wide["deep_targets"], 1)
            self.assertEqual(wide["end_zone_targets"], 1)
            self.assertEqual(wide["two_minute_targets"], 1)
            self.assertEqual(back["position"], "RB")
            self.assertEqual(back["inside_5_carries"], 1)
            self.assertEqual(back["third_fourth_short_carries"], 1)
            self.assertEqual(qb["designed_qb_carries"], 1)
            self.assertEqual(qb["designed_qb_red_zone_carries"], 1)
            self.assertEqual(qb["designed_qb_inside_10_carries"], 0)
            self.assertEqual(qb["qb_scramble_carries"], 0)
            self.assertEqual(result.coverage_rows[0]["read_labeled_rate"], "1.000000")

    def test_rejects_source_asset_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_source(Path(directory))
            with (source / "raw" / "roster_2024.csv").open("ab") as handle:
                handle.write(b"tampered")
            with self.assertRaisesRegex(HighValueHistoryDataError, "hash mismatch"):
                build_high_value_history(source)

    def test_writes_hash_verified_snapshot_and_route_caveat(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = build_high_value_history(self.make_source(root))
            path = write_high_value_history_snapshot(result, root / "derived")
            manifest = json.loads((path / "manifest.json").read_text())
            raw = (path / "player_week_high_value.csv").read_bytes()
            self.assertEqual(
                manifest["artifacts"]["player_week_high_value.csv"]["sha256"],
                hashlib.sha256(raw).hexdigest(),
            )
            self.assertEqual(
                manifest["quality"]["maximum_player_to_team_reconciliation_error"], 0
            )
            self.assertIn("primary receiver", manifest["definitions"]["routes"])

    def test_missing_ftn_is_structural_missingness_not_zero_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = build_high_value_history(
                self.make_source(root, include_ftn=False)
            )
            self.assertEqual(result.coverage_rows[0]["ftn_available"], "false")
            self.assertEqual(result.weekly_rows[0]["first_read_targets"], "")
            self.assertTrue(any(
                row["issue"] == "read_source_unavailable"
                for row in result.source_review
            ))
            path = write_high_value_history_snapshot(result, root / "derived")
            manifest = json.loads((path / "manifest.json").read_text())
            self.assertEqual(
                manifest["quality"]["minimum_available_read_labeled_rate"], 0
            )

    def test_2022_primary_read_is_structural_missingness(self):
        with tempfile.TemporaryDirectory() as directory:
            result = build_high_value_history(
                self.make_source(Path(directory), season=2022)
            )
            wide = next(row for row in result.weekly_rows if row["gsis_id"] == "w1")
            self.assertEqual(wide["read_source_available"], "true")
            self.assertEqual(wide["primary_read_source_available"], "false")
            self.assertEqual(wide["first_read_targets"], "")
            self.assertEqual(wide["designed_targets"], 1)
            self.assertTrue(any(
                row["issue"] == "primary_read_source_unavailable"
                for row in result.source_review
            ))


if __name__ == "__main__":
    unittest.main()
