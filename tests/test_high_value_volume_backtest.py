import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from fantasy_draft.high_value_backtest import (
    COMPARISON_FIELDS as ROLE_COMPARISON_FIELDS,
    EVALUATION_FIELDS as ROLE_EVALUATION_FIELDS,
    MODEL_PRIORS as ROLE_MODEL_PRIORS,
    recommend_high_value_metrics,
)
from fantasy_draft.high_value_history import TEAM_WEEK_FIELDS
from fantasy_draft.high_value_volume_backtest import (
    HighValueVolumeBacktestDataError,
    build_high_value_volume_backtest,
    write_high_value_volume_backtest_snapshot,
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


class HighValueVolumeBacktestTests(unittest.TestCase):
    def make_inputs(self, root: Path, *, reverse_holdout: bool = False):
        history = root / ("history-reverse" if reverse_holdout else "history")
        rows = []
        for season in range(2021, 2026):
            for index in range(20):
                high_team = index >= 10
                events = 40 if high_team else 0
                if reverse_holdout and season == 2025:
                    events = 0 if high_team else 40
                row = {field: 0 for field in TEAM_WEEK_FIELDS}
                row.update({
                    "season": season,
                    "week": 1,
                    "team": f"T{index:02d}",
                    "position": "RB",
                    "player_count": 2,
                    "read_source_available": "true",
                    "primary_read_source_available": "true",
                    "carries": 100,
                    "inside_5_carries": events,
                    "target_air_yards": "0.000",
                })
                rows.append(row)
        history_raw = write_csv(
            history / "team_week_high_value.csv", TEAM_WEEK_FIELDS, rows
        )
        (history / "manifest.json").write_text(json.dumps({
            "artifacts": {
                "team_week_high_value.csv": {
                    "sha256": hashlib.sha256(history_raw).hexdigest()
                }
            }
        }))

        role = root / "role-backtest"
        evaluations = []
        means = {
            "base_role": 0.30,
            "rate_adjusted_p12": 0.25,
            "rate_adjusted_p24": 0.24,
            "rate_adjusted_p48": 0.26,
        }
        for window in (4, 8, 18):
            for model in ROLE_MODEL_PRIORS:
                row = {field: "0" for field in ROLE_EVALUATION_FIELDS}
                row.update({
                    "segment": "metric",
                    "scope": "RB_INSIDE_5_CARRIES",
                    "window_end": window,
                    "model": model,
                    "room_count": 80,
                    "actual_event_count": 600,
                    "mean_total_variation": f"{means[model]:.6f}",
                })
                evaluations.append(row)
        comparisons = []
        for window in (4, 8, 18):
            row = {field: "0" for field in ROLE_COMPARISON_FIELDS}
            row.update({
                "segment": "metric",
                "scope": "RB_INSIDE_5_CARRIES",
                "window_end": window,
                "challenger": "rate_adjusted_p24",
                "baseline": "base_role",
                "room_count": 80,
                "cluster_count": 80,
                "mean_tv_delta": "-0.060000",
                "delta_ci90_low": "-0.080000",
                "delta_ci90_high": "-0.040000",
                "paired_room_win_rate": "0.700000",
                "interpretation": "challenger_lower_error_ci_excludes_zero",
            })
            comparisons.append(row)
        evaluation_raw = write_csv(
            role / "model_evaluation.csv", ROLE_EVALUATION_FIELDS, evaluations
        )
        comparison_raw = write_csv(
            role / "paired_comparisons.csv", ROLE_COMPARISON_FIELDS, comparisons
        )
        recommendation = recommend_high_value_metrics(evaluations, comparisons)
        (role / "manifest.json").write_text(json.dumps({
            "model_version": "high-value-role-backtest-v0.2.0",
            "parameters": {
                "model_prior_opportunities": dict(ROLE_MODEL_PRIORS),
            },
            "recommendation": recommendation,
            "artifacts": {
                "model_evaluation.csv": {
                    "sha256": hashlib.sha256(evaluation_raw).hexdigest()
                },
                "paired_comparisons.csv": {
                    "sha256": hashlib.sha256(comparison_raw).hexdigest()
                },
            },
        }))
        return history, role

    def test_promotes_repeatable_team_rate_without_target_leakage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self.make_inputs(root)
            result = build_high_value_volume_backtest(
                *inputs, bootstrap_samples=200, random_seed=1
            )
            metric = result.recommendation["metrics"]["RB_INSIDE_5_CARRIES"]
            self.assertTrue(metric["team_specific_gate_passed"])
            self.assertNotEqual(metric["selected_model"], "league_rate")
            reverse = build_high_value_volume_backtest(
                *self.make_inputs(root, reverse_holdout=True),
                bootstrap_samples=200,
                random_seed=1,
            )

            def forecasts(value):
                return {
                    (row["team"], row["model"]): row["predicted_rate"]
                    for row in value.prediction_rows
                    if row["target_season"] == 2025 and row["window_end"] == 18
                }

            self.assertEqual(forecasts(result), forecasts(reverse))
            self.assertEqual(len(result.calibration_rows), 1)

    def test_rejects_tampered_history(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs = self.make_inputs(Path(directory))
            with (inputs[0] / "team_week_high_value.csv").open("ab") as handle:
                handle.write(b"tampered")
            with self.assertRaisesRegex(
                HighValueVolumeBacktestDataError, "hash mismatch"
            ):
                build_high_value_volume_backtest(*inputs)

    def test_writes_hash_verified_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = build_high_value_volume_backtest(
                *self.make_inputs(root), bootstrap_samples=100
            )
            path = write_high_value_volume_backtest_snapshot(result, root / "derived")
            manifest = json.loads((path / "manifest.json").read_text())
            raw = (path / "rate_calibration.csv").read_bytes()
            self.assertEqual(
                manifest["artifacts"]["rate_calibration.csv"]["sha256"],
                hashlib.sha256(raw).hexdigest(),
            )
            self.assertEqual(manifest["quality"]["calibration_rows"], 1)


if __name__ == "__main__":
    unittest.main()
