import csv
import gzip
import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fantasy_draft.caller_fingerprints import STYLE_METRICS
from fantasy_draft.transition_backtest import (
    TransitionBacktestDataError,
    _identity,
    build_transition_backtest,
    write_transition_backtest_snapshot,
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

FTN_FIELDS = [
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
]


def csv_bytes(fields: list[str], rows: list[dict[str, object]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


class TransitionBacktestTests(unittest.TestCase):
    teams = ("ARI", "ATL", "BAL", "BUF")

    def test_identity_normalizes_generational_suffixes(self) -> None:
        self.assertEqual(_identity("Robert Griffin III"), _identity("Robert Griffin"))
        self.assertEqual(_identity("Pete Carmichael Jr."), _identity("Pete Carmichael"))

    def _fixture(
        self,
        root: Path,
        *,
        target_published: str = "2024-08-30",
        ambiguous_target: str | None = None,
    ) -> tuple[Path, ...]:
        nflverse = root / "nflverse"
        raw_directory = nflverse / "raw"
        raw_directory.mkdir(parents=True)

        style_rows = []
        plays = {"ARI": 60.0, "ATL": 50.0, "BAL": 70.0, "BUF": 80.0}
        for index, team in enumerate(self.teams, start=1):
            row: dict[str, object] = {"season": 2023, "team": team}
            for metric in STYLE_METRICS:
                if metric == "plays_per_game":
                    row[metric] = plays[team]
                elif metric == "mean_air_yards":
                    row[metric] = 7.0 + index
                elif metric == "neutral_pass_oe":
                    row[metric] = 0.0
                else:
                    row[metric] = 0.1 + index * 0.02
            style_rows.append(row)
        style_raw = csv_bytes(["season", "team", *STYLE_METRICS], style_rows)
        (nflverse / "team_style.csv").write_bytes(style_raw)

        roster_rows = []
        pbp_rows = []
        ftn_rows = []
        for team in self.teams:
            roster_rows.extend(
                [
                    {"season": 2024, "team": team, "position": "WR", "gsis_id": f"{team}_wr"},
                    {"season": 2024, "team": team, "position": "RB", "gsis_id": f"{team}_rb"},
                ]
            )
            for week in range(1, 9):
                game_id = f"2024_{week:02d}_{team}_XXX"
                for offset, pass_play in enumerate((1, 0), start=1):
                    play_id = week * 10 + offset
                    pbp_rows.append(
                        {
                            "season": 2024,
                            "season_type": "REG",
                            "week": week,
                            "game_id": game_id,
                            "play_id": play_id,
                            "posteam": team,
                            "qtr": 1,
                            "down": offset,
                            "yardline_100": 10,
                            "play_type": "pass" if pass_play else "run",
                            "yards_gained": 6,
                            "shotgun": pass_play,
                            "no_huddle": 0,
                            "qb_kneel": 0,
                            "qb_spike": 0,
                            "qb_scramble": 0,
                            "air_yards": 16 if pass_play else "",
                            "epa": 0,
                            "wp": 0.5,
                            "receiver_player_id": f"{team}_wr" if pass_play else "",
                            "rusher_player_id": "" if pass_play else f"{team}_rb",
                            "success": 1,
                            "pass": pass_play,
                            "rush": 1 - pass_play,
                            "pass_oe": 0,
                        }
                    )
                    ftn_rows.append(
                        {
                            "nflverse_game_id": game_id,
                            "nflverse_play_id": play_id,
                            "season": 2024,
                            "qb_location": "S" if pass_play else "U",
                            "n_offense_backfield": 1,
                            "is_motion": "TRUE" if pass_play else "FALSE",
                            "is_play_action": "TRUE" if pass_play else "FALSE",
                            "is_screen_pass": "FALSE",
                            "is_rpo": "FALSE",
                            "is_trick_play": "FALSE",
                            "is_qb_out_of_pocket": "FALSE",
                            "is_qb_sneak": "FALSE",
                        }
                    )
        assets = {
            "play_by_play_2024.csv.gz": gzip.compress(csv_bytes(PBP_FIELDS, pbp_rows)),
            "roster_2024.csv": csv_bytes(
                ["season", "team", "position", "gsis_id"], roster_rows
            ),
            "ftn_charting_2024.csv": csv_bytes(FTN_FIELDS, ftn_rows),
        }
        for name, body in assets.items():
            (raw_directory / name).write_bytes(body)
        manifest = {
            "query": {
                "seasons": [2023, 2024],
                "season_type": "REG",
                "include_ftn_charting": True,
            },
            "artifacts": {
                "normalized": {"sha256": hashlib.sha256(style_raw).hexdigest()},
                "raw": {
                    name: {"sha256": hashlib.sha256(body).hexdigest()}
                    for name, body in assets.items()
                },
            },
        }
        (nflverse / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        caller_fields = [
            "season",
            "team",
            "play_caller",
            "identity_status",
            "candidate_callers",
            "source_url",
            "published_at",
            "temporal_use",
        ]
        prior_names = {"ARI": "Alpha", "ATL": "Beta", "BAL": "Gamma", "BUF": "Epsilon"}
        target_names = {"ARI": "Alpha", "ATL": "Gamma", "BAL": "Delta", "BUF": "Epsilon"}
        caller_paths = []
        for season, names, published in (
            (2023, prior_names, "2023-08-23"),
            (2024, target_names, target_published),
        ):
            caller_path = root / f"callers_{season}.csv"
            caller_path.write_bytes(
                csv_bytes(
                    caller_fields,
                    [
                        {
                            "season": season,
                            "team": team,
                            "play_caller": (
                                ""
                                if season == 2024 and team == ambiguous_target
                                else names[team]
                            ),
                            "identity_status": (
                                "ambiguous"
                                if season == 2024 and team == ambiguous_target
                                else "confirmed"
                            ),
                            "candidate_callers": (
                                "Gamma|Delta"
                                if season == 2024 and team == ambiguous_target
                                else ""
                            ),
                            "source_url": "https://example.com/callers",
                            "published_at": published,
                            "temporal_use": "preseason_identity_evidence",
                        }
                        for team in self.teams
                    ],
                )
            )
            caller_paths.append(caller_path)

        changes = root / "changes.json"
        changes.write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "as_of": "2026-09-02",
                    "target_season": 2024,
                    "max_supported_week_end": 8,
                    "changes": [
                        {
                            "team": "ARI",
                            "opening_caller": "Alpha",
                            "replacement_caller": "Zeta",
                            "first_replacement_week": 8,
                            "reason": "Synthetic in-window handoff.",
                            "source_url": "https://example.com/change",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return nflverse, caller_paths[0], caller_paths[1], changes

    def test_builds_time_correct_windows_and_declared_blends(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            inputs = self._fixture(Path(directory))
            result = build_transition_backtest(*inputs, expected_team_count=4)

            self.assertEqual(result.windows, (6, 8))
            self.assertEqual(len(result.team_rows), 8)
            excluded = next(
                row
                for row in result.team_rows
                if row["team"] == "ARI" and row["week_end"] == 8
            )
            self.assertEqual(excluded["excluded"], "true")
            self.assertFalse(
                any(
                    row["team"] == "ARI" and row["week_end"] == 8
                    for row in result.prediction_rows
                )
            )
            anchored = next(
                row
                for row in result.prediction_rows
                if row["team"] == "ATL"
                and row["week_end"] == 6
                and row["metric"] == "plays_per_game"
                and row["model"] == "caller_aware_v0"
            )
            self.assertEqual(anchored["caller_cohort"], "changed_with_prior_year_anchor")
            self.assertEqual(anchored["prior_anchor_team"], "BAL")
            self.assertAlmostEqual(float(anchored["forecast_value"]), 65.5)
            self.assertEqual(
                result.evaluation["mean_adjustment_decision"],
                "retain_caller_aware_mean_as_experimental_only",
            )

    def test_rejects_target_caller_evidence_after_preseason_cutoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            inputs = self._fixture(Path(directory), target_published="2024-09-01")
            with self.assertRaisesRegex(TransitionBacktestDataError, "before September 1"):
                build_transition_backtest(*inputs, expected_team_count=4)

    def test_verifies_and_binds_caller_snapshot_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = list(self._fixture(root))
            prior_raw = inputs[1].read_bytes()
            snapshot = root / "prior_snapshot"
            snapshot.mkdir()
            callers_path = snapshot / "callers.csv"
            callers_path.write_bytes(prior_raw)
            manifest_path = snapshot / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "season": 2023,
                        "artifacts": {
                            "callers.csv": {
                                "sha256": hashlib.sha256(prior_raw).hexdigest()
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            inputs[1] = snapshot

            result = build_transition_backtest(*inputs, expected_team_count=4)
            self.assertIn(str(manifest_path), result.input_hashes)

            callers_path.write_bytes(prior_raw + b"tampered")
            with self.assertRaisesRegex(TransitionBacktestDataError, "hash mismatch"):
                build_transition_backtest(*inputs, expected_team_count=4)

    def test_excludes_ambiguous_opening_identity_without_hindsight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            inputs = self._fixture(Path(directory), ambiguous_target="BAL")
            result = build_transition_backtest(*inputs, expected_team_count=4)
            rows = [row for row in result.team_rows if row["team"] == "BAL"]

            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row["excluded"] == "true" for row in rows))
            self.assertTrue(
                all(row["caller_cohort"] == "ambiguous_opening_caller" for row in rows)
            )
            self.assertFalse(any(row["team"] == "BAL" for row in result.prediction_rows))

    def test_writes_hash_bearing_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = build_transition_backtest(*self._fixture(root), expected_team_count=4)
            snapshot = write_transition_backtest_snapshot(
                result,
                root / "derived",
                created_at=datetime(2026, 9, 2, 23, 0, tzinfo=timezone.utc),
            )
            manifest = json.loads((snapshot / "manifest.json").read_text())
            paired = (snapshot / "paired_team_effects.csv").read_bytes()

            self.assertEqual(snapshot.name, "20260902T230000.000000Z")
            self.assertEqual(manifest["counts"]["team_window_rows"], 8)
            self.assertEqual(
                manifest["artifacts"]["paired_team_effects.csv"]["sha256"],
                hashlib.sha256(paired).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
