import csv
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fantasy_draft.caller_resource_backtest import (
    CallerResourceBacktestDataError,
    PREDICTION_FIELDS,
    build_caller_resource_backtest,
    write_caller_resource_backtest_snapshot,
)


def csv_bytes(fields, rows):
    import io

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def write_style(root: Path) -> Path:
    snapshot = root / "style"
    snapshot.mkdir()
    fields = ["season", "team", "plays", "pass_rate", "designed_qb_run_share"]
    rows = [
        {
            "season": season,
            "team": team,
            "plays": 480,
            "pass_rate": 2 / 3,
            "designed_qb_run_share": 0,
        }
        for season in range(2020, 2026)
        for team in ("AAA", "BBB")
    ]
    raw = csv_bytes(fields, rows)
    (snapshot / "team_style.csv").write_bytes(raw)
    (snapshot / "manifest.json").write_text(
        json.dumps(
            {
                "artifacts": {
                    "normalized": {
                        "path": "team_style.csv",
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    }
                }
            }
        )
    )
    return snapshot


def write_transition(root: Path, season: int, style: Path) -> Path:
    snapshot = root / f"transition-{season}"
    snapshot.mkdir()
    source = snapshot / "source.txt"
    source.write_text(f"source-{season}")
    team_fields = [
        "target_season",
        "week_start",
        "week_end",
        "team",
        "opening_caller",
        "prior_caller",
        "caller_cohort",
        "prior_anchor_team",
        "actual_games",
        "excluded",
        "exclusion_reason",
        "exclusion_source_url",
    ]
    teams = [
        {
            "target_season": season,
            "week_start": 1,
            "week_end": week,
            "team": team,
            "opening_caller": f"Caller {team}",
            "prior_caller": f"Caller {team}",
            "caller_cohort": "returning_caller",
            "prior_anchor_team": "",
            "actual_games": week,
            "excluded": "false",
            "exclusion_reason": "",
            "exclusion_source_url": "",
        }
        for week in (6, 8)
        for team in ("AAA", "BBB")
    ]
    metric_values = {
        "plays_per_game": 60.0,
        "pass_rate": 2 / 3,
        "qb_scramble_rate": 0.075,
        "designed_qb_run_share": 0.1,
        "rb_target_share": 2 / 9,
        "wr_target_share": 5 / 9,
        "te_target_share": 2 / 9,
    }
    prediction_fields = [
        "target_season",
        "week_start",
        "week_end",
        "team",
        "opening_caller",
        "prior_caller",
        "caller_cohort",
        "prior_anchor_team",
        "metric",
        "dimension",
        "tolerance",
        "model",
        "forecast_value",
        "actual_value",
        "absolute_error",
        "normalized_absolute_error",
        "within_tolerance",
    ]
    predictions = []
    for week in (6, 8):
        for team in ("AAA", "BBB"):
            for model, shift in (
                ("caller_aware_v0", 0.0),
                ("shrunken_persistence", 0.02),
                ("persistence", 0.04),
            ):
                for metric, value in metric_values.items():
                    forecast = value
                    if metric == "pass_rate":
                        forecast = value - shift
                    predictions.append(
                        {
                            "target_season": season,
                            "week_start": 1,
                            "week_end": week,
                            "team": team,
                            "opening_caller": f"Caller {team}",
                            "prior_caller": f"Caller {team}",
                            "caller_cohort": "returning_caller",
                            "prior_anchor_team": "",
                            "metric": metric,
                            "dimension": "test",
                            "tolerance": 1,
                            "model": model,
                            "forecast_value": forecast,
                            "actual_value": value,
                            "absolute_error": abs(forecast - value),
                            "normalized_absolute_error": abs(forecast - value),
                            "within_tolerance": "true",
                        }
                    )
    teams_raw = csv_bytes(team_fields, teams)
    predictions_raw = csv_bytes(prediction_fields, predictions)
    (snapshot / "teams.csv").write_bytes(teams_raw)
    (snapshot / "predictions.csv").write_bytes(predictions_raw)
    manifest = {
        "model_version": "opening-caller-transition-backtest-v0.3.0",
        "seasons": {"target": season},
        "input_sha256": {
            str(source): hashlib.sha256(source.read_bytes()).hexdigest(),
            str(style / "team_style.csv"): hashlib.sha256(
                (style / "team_style.csv").read_bytes()
            ).hexdigest(),
            str(style / "manifest.json"): hashlib.sha256(
                (style / "manifest.json").read_bytes()
            ).hexdigest(),
        },
        "artifacts": {
            "teams.csv": {"sha256": hashlib.sha256(teams_raw).hexdigest()},
            "predictions.csv": {
                "sha256": hashlib.sha256(predictions_raw).hexdigest()
            },
        },
    }
    (snapshot / "manifest.json").write_text(json.dumps(manifest))
    return snapshot


def write_history(root: Path, *, holdout_rb_carries: float = 20.0) -> Path:
    snapshot = root / f"history-{holdout_rb_carries:g}"
    snapshot.mkdir()
    opportunity_fields = [
        "season",
        "week",
        "team",
        "position",
        "gsis_id",
        "player_name",
        "dropbacks",
        "carries",
        "targets",
    ]
    opportunities = []
    for season in range(2020, 2026):
        for week in range(1, 9):
            for team in ("AAA", "BBB"):
                rb_carries = holdout_rb_carries if season == 2025 else 20.0
                values = {
                    "QB": (40.0, 5.0, 0.0),
                    "RB": (0.0, rb_carries, 8.0),
                    "WR": (0.0, 1.0, 20.0),
                    "TE": (0.0, 0.0, 8.0),
                }
                for position, (dropbacks, carries, targets) in values.items():
                    opportunities.append(
                        {
                            "season": season,
                            "week": week,
                            "team": team,
                            "position": position,
                            "gsis_id": f"{season}-{team}-{position}",
                            "player_name": f"{team} {position}",
                            "dropbacks": dropbacks,
                            "carries": carries,
                            "targets": targets,
                        }
                    )
    schedule_fields = [
        "season",
        "week",
        "gameday",
        "game_id",
        "team",
        "opponent",
        "home_away",
    ]
    schedule = [
        {
            "season": season,
            "week": week,
            "gameday": f"{season}-09-01",
            "game_id": f"{season}_{week}_{team}",
            "team": team,
            "opponent": "BBB" if team == "AAA" else "AAA",
            "home_away": "home" if team == "AAA" else "away",
        }
        for season in range(2020, 2026)
        for week in range(1, 9)
        for team in ("AAA", "BBB")
    ]
    opportunities_raw = csv_bytes(opportunity_fields, opportunities)
    schedule_raw = csv_bytes(schedule_fields, schedule)
    (snapshot / "weekly_opportunities.csv").write_bytes(opportunities_raw)
    (snapshot / "team_schedule.csv").write_bytes(schedule_raw)
    manifest = {
        "artifacts": {
            "normalized": {
                "weekly_opportunities.csv": {
                    "sha256": hashlib.sha256(opportunities_raw).hexdigest()
                },
                "team_schedule.csv": {
                    "sha256": hashlib.sha256(schedule_raw).hexdigest()
                },
            }
        }
    }
    (snapshot / "manifest.json").write_text(json.dumps(manifest))
    return snapshot


class CallerResourceBacktestTests(unittest.TestCase):
    def inputs(self, root: Path, *, holdout_rb_carries: float = 20.0):
        style = write_style(root)
        transitions = [
            write_transition(root, season, style) for season in (2023, 2024, 2025)
        ]
        history = write_history(root, holdout_rb_carries=holdout_rb_carries)
        return transitions, history, style

    def test_recreates_six_resources_with_strictly_prior_conversions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transitions, history, style = self.inputs(root)
            result = build_caller_resource_backtest(
                transitions,
                history,
                style,
                expected_team_count=2,
                bootstrap_samples=100,
            )
            self.assertEqual(len(result.prediction_rows), 216)
            self.assertEqual(len(result.conversion_rows), 6)
            self.assertEqual(len(result.calibration_rows), 12)
            self.assertEqual(len(result.coverage_rows), 24)
            row = next(
                row
                for row in result.prediction_rows
                if row["target_season"] == 2025
                and row["week_end"] == 6
                and row["team"] == "AAA"
                and row["model"] == "caller_aware_v0"
                and row["resource"] == "WR_TARGETS"
            )
            self.assertAlmostEqual(float(row["forecast_per_game"]), 20.0, places=5)
            self.assertAlmostEqual(float(row["actual_per_game"]), 20.0, places=5)
            self.assertEqual(
                result.evaluation["data_split"][
                    "holdout_used_for_model_or_radius_selection"
                ],
                False,
            )

    def test_holdout_outcome_does_not_change_its_forecast(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            style = write_style(root)
            transitions = [
                write_transition(root, season, style)
                for season in (2023, 2024, 2025)
            ]
            first = build_caller_resource_backtest(
                transitions,
                write_history(root, holdout_rb_carries=20),
                style,
                expected_team_count=2,
                bootstrap_samples=100,
            )
            second = build_caller_resource_backtest(
                transitions,
                write_history(root, holdout_rb_carries=30),
                style,
                expected_team_count=2,
                bootstrap_samples=100,
            )
            key = lambda row: (
                row["target_season"],
                row["week_end"],
                row["team"],
                row["model"],
                row["resource"],
            )
            first_rows = {key(row): row for row in first.prediction_rows}
            second_rows = {key(row): row for row in second.prediction_rows}
            target = (2025, 6, "AAA", "caller_aware_v0", "RB_CARRIES")
            self.assertEqual(
                first_rows[target]["forecast_per_game"],
                second_rows[target]["forecast_per_game"],
            )
            self.assertNotEqual(
                first_rows[target]["actual_per_game"],
                second_rows[target]["actual_per_game"],
            )

    def test_rejects_tampered_transition_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transitions, history, style = self.inputs(root)
            with (transitions[0] / "predictions.csv").open("ab") as handle:
                handle.write(b"tampered")
            with self.assertRaisesRegex(
                CallerResourceBacktestDataError, "artifact hash mismatch"
            ):
                build_caller_resource_backtest(
                    transitions,
                    history,
                    style,
                    expected_team_count=2,
                    bootstrap_samples=100,
                )

    def test_writes_immutable_snapshot_with_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transitions, history, style = self.inputs(root)
            result = build_caller_resource_backtest(
                transitions,
                history,
                style,
                expected_team_count=2,
                bootstrap_samples=100,
            )
            created = datetime(2026, 9, 3, 13, 0, tzinfo=timezone.utc)
            snapshot = write_caller_resource_backtest_snapshot(
                result, root / "derived", created_at=created
            )
            manifest = json.loads((snapshot / "manifest.json").read_text())
            raw = (snapshot / "resource_predictions.csv").read_bytes()
            self.assertEqual(
                manifest["artifacts"]["resource_predictions.csv"]["sha256"],
                hashlib.sha256(raw).hexdigest(),
            )
            with (snapshot / "resource_predictions.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(tuple(rows[0]), PREDICTION_FIELDS)
            self.assertEqual(
                manifest["quality"]["prediction_count"], len(result.prediction_rows)
            )
            with self.assertRaises(FileExistsError):
                write_caller_resource_backtest_snapshot(
                    result, root / "derived", created_at=created
                )


if __name__ == "__main__":
    unittest.main()
