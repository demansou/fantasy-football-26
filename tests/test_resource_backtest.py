import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from fantasy_draft.resource_backtest import (
    ResourceBacktestDataError,
    build_resource_backtest,
    write_resource_backtest_snapshot,
)


OPPORTUNITY_FIELDS = (
    "season", "week", "team", "position", "gsis_id", "player_name",
    "dropbacks", "carries", "targets",
)
SCHEDULE_FIELDS = (
    "season", "week", "gameday", "game_id", "team", "opponent", "home_away",
)


def write_csv(path: Path, fields, rows) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    raw = stream.getvalue().encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


class ResourceBacktestTests(unittest.TestCase):
    def make_history(self, root: Path) -> Path:
        history = root / "history"
        opportunities = []
        schedule = []
        rates = {
            "AAA": {"rb_carries": 25, "rb_targets": 7, "wr_targets": 20, "te_targets": 8},
            "BBB": {"rb_carries": 15, "rb_targets": 3, "wr_targets": 10, "te_targets": 2},
        }
        for season in range(2021, 2026):
            for week in range(1, 19):
                for team, opponent in (("AAA", "BBB"), ("BBB", "AAA")):
                    schedule.append({
                        "season": season,
                        "week": week,
                        "gameday": f"{season}-09-{min(week, 28):02d}",
                        "game_id": f"{season}_{week:02d}_{team}",
                        "team": team,
                        "opponent": opponent,
                        "home_away": "home" if team == "AAA" else "away",
                    })
                    values = rates[team]
                    opportunities.extend((
                        {
                            "season": season, "week": week, "team": team,
                            "position": "RB", "gsis_id": f"{team}-rb",
                            "player_name": f"{team} Back", "dropbacks": 0,
                            "carries": values["rb_carries"],
                            "targets": values["rb_targets"],
                        },
                        {
                            "season": season, "week": week, "team": team,
                            "position": "WR", "gsis_id": f"{team}-wr",
                            "player_name": f"{team} Receiver", "dropbacks": 0,
                            "carries": 0, "targets": values["wr_targets"],
                        },
                        {
                            "season": season, "week": week, "team": team,
                            "position": "TE", "gsis_id": f"{team}-te",
                            "player_name": f"{team} Tight End", "dropbacks": 0,
                            "carries": 0, "targets": values["te_targets"],
                        },
                    ))
        opportunity_raw = write_csv(
            history / "weekly_opportunities.csv", OPPORTUNITY_FIELDS, opportunities
        )
        schedule_raw = write_csv(
            history / "team_schedule.csv", SCHEDULE_FIELDS, schedule
        )
        (history / "manifest.json").write_text(json.dumps({
            "artifacts": {"normalized": {
                "weekly_opportunities.csv": {
                    "sha256": hashlib.sha256(opportunity_raw).hexdigest()
                },
                "team_schedule.csv": {
                    "sha256": hashlib.sha256(schedule_raw).hexdigest()
                },
            }}
        }))
        return history

    def test_builds_time_correct_reference_gate_and_holdout_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            result = build_resource_backtest(
                self.make_history(Path(directory)),
                bootstrap_samples=100,
                random_seed=1,
                expected_team_count=2,
            )
            self.assertEqual(len(result.prediction_rows), 504)
            self.assertEqual(len(result.calibration_rows), 4)
            self.assertEqual(
                set(result.recommendation["team_reference_resources"]),
                {"RB_CARRIES", "RB_TARGETS", "WR_TARGETS", "TE_TARGETS"},
            )
            self.assertTrue(all(
                float(row["holdout_coverage"]) == 1.0
                for row in result.calibration_rows
            ))
            self.assertTrue(all(
                row["current_mean_transfer_status"].startswith("provisional")
                for row in result.calibration_rows
            ))

    def test_target_outcome_does_not_change_its_preseason_forecast(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = self.make_history(root)
            first = build_resource_backtest(
                history, bootstrap_samples=100, random_seed=1, expected_team_count=2
            )
            path = history / "weekly_opportunities.csv"
            with path.open() as handle:
                rows = list(csv.DictReader(handle))
            for row in rows:
                if row["season"] == "2025" and row["team"] == "AAA" and row["position"] == "WR":
                    row["targets"] = "40"
            raw = write_csv(path, OPPORTUNITY_FIELDS, rows)
            manifest_path = history / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["artifacts"]["normalized"]["weekly_opportunities.csv"]["sha256"] = (
                hashlib.sha256(raw).hexdigest()
            )
            manifest_path.write_text(json.dumps(manifest))
            second = build_resource_backtest(
                history, bootstrap_samples=100, random_seed=1, expected_team_count=2
            )
            key = lambda row: (
                row["target_season"], row["window_end"], row["team"],
                row["resource"], row["model"],
            )
            before = {
                key(row): row["predicted_per_game"] for row in first.prediction_rows
                if row["target_season"] == 2025
            }
            after = {
                key(row): row["predicted_per_game"] for row in second.prediction_rows
                if row["target_season"] == 2025
            }
            self.assertEqual(before, after)

    def test_rejects_tampered_history(self):
        with tempfile.TemporaryDirectory() as directory:
            history = self.make_history(Path(directory))
            with (history / "weekly_opportunities.csv").open("ab") as handle:
                handle.write(b"tampered")
            with self.assertRaisesRegex(ResourceBacktestDataError, "hash mismatch"):
                build_resource_backtest(
                    history, bootstrap_samples=100, expected_team_count=2
                )

    def test_writes_hash_verified_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = build_resource_backtest(
                self.make_history(root),
                bootstrap_samples=100,
                random_seed=1,
                expected_team_count=2,
            )
            path = write_resource_backtest_snapshot(result, root / "output")
            manifest = json.loads((path / "manifest.json").read_text())
            raw = (path / "resource_calibration.csv").read_bytes()
            self.assertEqual(
                manifest["artifacts"]["resource_calibration.csv"]["sha256"],
                hashlib.sha256(raw).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
