import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fantasy_draft.position_environments import (
    FIELDS,
    build_position_environments,
    write_position_environment_snapshot,
)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


class PositionEnvironmentTests(unittest.TestCase):
    def make_snapshot(self, root: Path) -> Path:
        snapshot = root / "fingerprints"
        write_csv(
            snapshot / "teams.csv",
            ["season", "team", "exact_style_certainty_v0", "model_status"],
            [
                {"season": 2026, "team": "AAA", "exact_style_certainty_v0": 100, "model_status": "test"},
                {"season": 2026, "team": "BBB", "exact_style_certainty_v0": 20, "model_status": "test"},
                {"season": 2026, "team": "CCC", "exact_style_certainty_v0": 100, "model_status": "test"},
            ],
        )
        values = {
            "AAA": {"plays_per_game": 70, "pass_rate": 0.7, "neutral_early_down_pass_rate": 0.7, "play_action_rate": 0.3, "mean_air_yards": 9, "rb_target_share": 0.25, "wr_target_share": 0.65, "te_target_share": 0.10},
            "BBB": {"plays_per_game": 65, "pass_rate": 0.6, "neutral_early_down_pass_rate": 0.6, "play_action_rate": 0.25, "mean_air_yards": 8, "rb_target_share": 0.20, "wr_target_share": 0.55, "te_target_share": 0.25},
            "CCC": {"plays_per_game": 60, "pass_rate": 0.5, "neutral_early_down_pass_rate": 0.5, "play_action_rate": 0.2, "mean_air_yards": 7, "rb_target_share": 0.15, "wr_target_share": 0.45, "te_target_share": 0.15},
        }
        metric_rows = [
            {"season": 2026, "team": team, "metric": metric, "forecast_value_v0": value, "model_status": "test"}
            for team, metrics in values.items()
            for metric, value in metrics.items()
        ]
        write_csv(
            snapshot / "metric_forecasts.csv",
            ["season", "team", "metric", "forecast_value_v0", "model_status"],
            metric_rows,
        )
        return snapshot

    def test_builds_four_relative_position_opportunity_tables(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = build_position_environments(self.make_snapshot(Path(directory)))
            self.assertEqual(len(result.rows), 12)
            qb = [row for row in result.rows if row["position"] == "QB"]
            self.assertEqual(qb[0]["team"], "AAA")
            self.assertEqual(qb[0]["league_rank"], 1)
            te = [row for row in result.rows if row["position"] == "TE"]
            self.assertEqual(te[0]["team"], "BBB")
            bbb = next(row for row in te if row["team"] == "BBB")
            self.assertLess(
                abs(float(bbb["certainty_adjusted_score_v0"]) - 50),
                abs(float(bbb["raw_opportunity_score_v0"]) - 50),
            )
            self.assertEqual(
                bbb["ranking_score_v1"], bbb["raw_opportunity_score_v0"]
            )
            self.assertEqual(
                bbb["ranking_policy"],
                "raw_point_forecast_no_uncalibrated_certainty_shrinkage",
            )

    def test_writes_hashed_snapshot_with_scope_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = build_position_environments(self.make_snapshot(root))
            path = write_position_environment_snapshot(result, root / "derived")
            payload = (path / "position_environments.csv").read_bytes()
            manifest = json.loads((path / "manifest.json").read_text())
            with (path / "position_environments.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(tuple(rows[0]), FIELDS)
            self.assertIn("No player role", rows[0]["scope_warning"])
            self.assertEqual(manifest["quality"]["row_count"], 12)
            self.assertEqual(
                manifest["model_version"],
                "position-opportunity-environment-v0.3.0",
            )
            self.assertIn("forecast_pass_plays_per_game", rows[0])
            self.assertNotIn("forecast_dropbacks_per_game", rows[0])
            self.assertIn(
                "cannot set rank",
                manifest["methodology"]["legacy_certainty_diagnostic"],
            )
            self.assertEqual(manifest["artifacts"]["position_environments.csv"]["sha256"], hashlib.sha256(payload).hexdigest())


if __name__ == "__main__":
    unittest.main()
