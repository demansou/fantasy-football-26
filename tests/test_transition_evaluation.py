import csv
import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fantasy_draft.transition_evaluation import (
    TransitionEvaluationDataError,
    build_transition_evaluation,
    write_transition_evaluation_snapshot,
)


def csv_bytes(fields: list[str], rows: list[dict[str, object]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


class TransitionEvaluationTests(unittest.TestCase):
    def _snapshot(self, root: Path, season: int, *, effect: float) -> Path:
        destination = root / str(season)
        destination.mkdir(parents=True)
        prediction_fields = [
            "target_season",
            "week_end",
            "team",
            "caller_cohort",
            "metric",
            "tolerance",
            "model",
            "forecast_value",
            "actual_value",
            "absolute_error",
        ]
        prediction_rows = []
        paired_rows = []
        for week in (6, 8):
            for index, team in enumerate(("AAA", "BBB"), start=1):
                actual = 10.0
                for model, error in (
                    ("shrunken_persistence", 1.0 + index / 10),
                    ("caller_aware_v0", 0.5 + index / 10),
                ):
                    prediction_rows.append(
                        {
                            "target_season": season,
                            "week_end": week,
                            "team": team,
                            "caller_cohort": "changed_with_prior_year_anchor",
                            "metric": "plays_per_game",
                            "tolerance": 2.0,
                            "model": model,
                            "forecast_value": actual - error,
                            "actual_value": actual,
                            "absolute_error": error,
                        }
                    )
                paired_rows.append(
                    {
                        "target_season": season,
                        "week_end": week,
                        "team": team,
                        "paired_delta": effect - index / 100,
                        "candidate_wins": "true",
                    }
                )
        artifacts = {
            "predictions.csv": csv_bytes(prediction_fields, prediction_rows),
            "paired_team_effects.csv": csv_bytes(
                [
                    "target_season",
                    "week_end",
                    "team",
                    "paired_delta",
                    "candidate_wins",
                ],
                paired_rows,
            ),
        }
        for name, raw in artifacts.items():
            (destination / name).write_bytes(raw)
        source_path = destination / "bound_source.txt"
        source_raw = f"source for {season}\n".encode()
        source_path.write_bytes(source_raw)
        manifest = {
            "schema_version": "1.0.0",
            "model_version": "opening-caller-transition-backtest-v0.3.0",
            "seasons": {
                "prior": season - 1,
                "target": season,
                "target_windows": ["Weeks 1-6", "Weeks 1-8"],
            },
            "models": {
                "shrunken_persistence": "fixed baseline",
                "caller_aware_v0": "fixed candidate",
            },
            "scoring": {"normalized_absolute_error": "fixed tolerance"},
            "input_sha256": {
                str(source_path): hashlib.sha256(source_raw).hexdigest()
            },
            "artifacts": {
                name: {"sha256": hashlib.sha256(raw).hexdigest()}
                for name, raw in artifacts.items()
            },
        }
        (destination / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return destination

    def test_pools_three_seasons_and_scores_heldout_bands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = [
                self._snapshot(root, 2023, effect=-0.10),
                self._snapshot(root, 2024, effect=-0.12),
                self._snapshot(root, 2025, effect=-0.20),
            ]
            result = build_transition_evaluation(inputs, bootstrap_samples=1000)
            destination = write_transition_evaluation_snapshot(
                result,
                root / "derived",
                created_at=datetime(2026, 9, 3, 13, 0, tzinfo=timezone.utc),
            )

            self.assertTrue(result.evaluation["caller_mean_promotion_gate"]["pass"])
            self.assertEqual(len(result.coverage_prediction_rows), 8)
            self.assertEqual(len(result.metric_coverage_rows), 4)
            pooled = next(
                row
                for row in result.paired_summary_rows
                if row["scope"] == "pooled_all_seasons" and row["week_end"] == 6
            )
            self.assertEqual(pooled["team_season_count"], 6)
            self.assertEqual(pooled["team_cluster_count"], 2)
            metric_window = result.evaluation["heldout_interval_coverage"][
                "caller_aware_metric_windows"
            ][0]
            self.assertEqual(metric_window["metric_count"], 1)
            self.assertEqual(metric_window["metrics_at_or_above_nominal"], 1)
            self.assertTrue(
                all(row["covered"] == "true" for row in result.coverage_prediction_rows)
            )
            self.assertEqual(destination.name, "20260903T130000.000000Z")
            manifest = json.loads((destination / "manifest.json").read_text())
            summary_raw = (destination / "paired_effect_summary.csv").read_bytes()
            self.assertEqual(
                manifest["artifacts"]["paired_effect_summary.csv"]["sha256"],
                hashlib.sha256(summary_raw).hexdigest(),
            )

    def test_rejects_tampered_parent_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = [
                self._snapshot(root, 2023, effect=-0.10),
                self._snapshot(root, 2024, effect=-0.12),
                self._snapshot(root, 2025, effect=-0.20),
            ]
            with (inputs[-1] / "predictions.csv").open("ab") as stream:
                stream.write(b"tampered")
            with self.assertRaisesRegex(TransitionEvaluationDataError, "hash mismatch"):
                build_transition_evaluation(inputs, bootstrap_samples=1000)

    def test_rejects_tampered_bound_backtest_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = [
                self._snapshot(root, 2023, effect=-0.10),
                self._snapshot(root, 2024, effect=-0.12),
                self._snapshot(root, 2025, effect=-0.20),
            ]
            (inputs[0] / "bound_source.txt").write_text(
                "changed after backtest\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                TransitionEvaluationDataError, "bound backtest source hash mismatch"
            ):
                build_transition_evaluation(inputs, bootstrap_samples=1000)


if __name__ == "__main__":
    unittest.main()
