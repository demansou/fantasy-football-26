import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from fantasy_draft.high_value_backtest import (
    HighValueBacktestDataError,
    build_high_value_backtest,
    paired_comparisons,
    write_high_value_backtest_snapshot,
)
from fantasy_draft.high_value_history import COVERAGE_FIELDS, WEEKLY_FIELDS


def write_csv(path: Path, fields, rows) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    raw = stream.getvalue().encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def high_row(season: int, player_id: str, carries: int, inside_five: int):
    row = {field: 0 for field in WEEKLY_FIELDS}
    row.update({
        "season": season,
        "week": 1,
        "team": "AAA",
        "position": "RB",
        "gsis_id": player_id,
        "player_name": "One Back" if player_id == "r1" else "Two Back",
        "read_source_available": "true",
        "primary_read_source_available": "true",
        "carries": carries,
        "inside_5_carries": inside_five,
        "target_air_yards": "0.000",
    })
    return row


class HighValueBacktestTests(unittest.TestCase):
    def make_inputs(self, root: Path, *, reverse_target: bool = False):
        player = root / ("player-reverse" if reverse_target else "player")
        roster_fields = [
            "season", "week", "team", "position", "gsis_id", "player_name",
            "status", "status_description",
        ]
        roster_raw = write_csv(player / "weekly_rosters.csv", roster_fields, [
            {"season": 2023, "week": 1, "team": "AAA", "position": "RB", "gsis_id": "r1", "player_name": "One Back", "status": "ACT", "status_description": "A01"},
            {"season": 2023, "week": 1, "team": "AAA", "position": "RB", "gsis_id": "r2", "player_name": "Two Back", "status": "ACT", "status_description": "A01"},
        ])
        depth_fields = [
            "season", "team", "position", "gsis_id", "player_name",
            "depth_position", "depth_rank", "temporal_precision",
        ]
        depth_raw = write_csv(player / "opening_depth.csv", depth_fields, [
            {"season": 2023, "team": "AAA", "position": "RB", "gsis_id": "r1", "player_name": "One Back", "depth_position": "RB", "depth_rank": 1, "temporal_precision": "week_1_label_only_no_source_timestamp"},
            {"season": 2023, "team": "AAA", "position": "RB", "gsis_id": "r2", "player_name": "Two Back", "depth_position": "RB", "depth_rank": 2, "temporal_precision": "week_1_label_only_no_source_timestamp"},
        ])
        opportunity_fields = [
            "season", "week", "team", "position", "gsis_id", "player_name",
            "dropbacks", "carries", "targets",
        ]
        opportunity_rows = []
        for season in (2021, 2022, 2023):
            opportunity_rows.extend([
                {"season": season, "week": 1, "team": "AAA", "position": "RB", "gsis_id": "r1", "player_name": "One Back", "dropbacks": 0, "carries": 50, "targets": 10},
                {"season": season, "week": 1, "team": "AAA", "position": "RB", "gsis_id": "r2", "player_name": "Two Back", "dropbacks": 0, "carries": 50, "targets": 10},
            ])
        opportunity_raw = write_csv(
            player / "weekly_opportunities.csv", opportunity_fields, opportunity_rows
        )
        (player / "manifest.json").write_text(json.dumps({
            "artifacts": {"normalized": {
                "weekly_rosters.csv": {"sha256": hashlib.sha256(roster_raw).hexdigest()},
                "opening_depth.csv": {"sha256": hashlib.sha256(depth_raw).hexdigest()},
                "weekly_opportunities.csv": {"sha256": hashlib.sha256(opportunity_raw).hexdigest()},
            }}
        }))

        high = root / ("high-reverse" if reverse_target else "high")
        target = (10, 0) if reverse_target else (0, 10)
        high_rows = [
            high_row(2021, "r1", 50, 0),
            high_row(2021, "r2", 50, 10),
            high_row(2022, "r1", 50, 0),
            high_row(2022, "r2", 50, 10),
            high_row(2023, "r1", 50, target[0]),
            high_row(2023, "r2", 50, target[1]),
        ]
        high_raw = write_csv(high / "player_week_high_value.csv", WEEKLY_FIELDS, high_rows)
        coverage_rows = []
        for season in (2021, 2022, 2023):
            row = {field: 0 for field in COVERAGE_FIELDS}
            row.update({
                "season": season,
                "ftn_available": "true",
                "primary_read_available": "true",
                "read_labeled_rate": "1.000000",
            })
            coverage_rows.append(row)
        coverage_raw = write_csv(high / "coverage.csv", COVERAGE_FIELDS, coverage_rows)
        (high / "manifest.json").write_text(json.dumps({
            "artifacts": {
                "player_week_high_value.csv": {
                    "sha256": hashlib.sha256(high_raw).hexdigest()
                },
                "coverage.csv": {"sha256": hashlib.sha256(coverage_raw).hexdigest()},
            }
        }))
        return player, high

    def test_prior_high_value_rate_improves_matching_target_without_leakage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            player, high = self.make_inputs(root)
            result = build_high_value_backtest(
                player, high, target_seasons=(2023,), history_lookback=2,
                bootstrap_samples=100, random_seed=1,
            )
            metric_rows = [
                row for row in result.room_rows
                if row["metric"] == "RB_INSIDE_5_CARRIES"
                and int(row["window_end"]) == 4
            ]
            base = next(row for row in metric_rows if row["model"] == "base_role")
            adjusted = next(
                row for row in metric_rows if row["model"] == "rate_adjusted_p24"
            )
            self.assertLess(
                float(adjusted["total_variation_distance"]),
                float(base["total_variation_distance"]),
            )
            reverse_player, reverse_high = self.make_inputs(root, reverse_target=True)
            reverse = build_high_value_backtest(
                reverse_player, reverse_high, target_seasons=(2023,),
                history_lookback=2, bootstrap_samples=100, random_seed=1,
            )

            def forecasts(value):
                return {
                    (row["model"], row["gsis_id"]): row["predicted_share"]
                    for row in value.prediction_rows
                    if row["metric"] == "RB_INSIDE_5_CARRIES"
                    and int(row["window_end"]) == 4
                }

            self.assertEqual(forecasts(result), forecasts(reverse))
            self.assertFalse(
                result.recommendation["metrics"]["RB_INSIDE_5_CARRIES"][
                    "promotion_gate_passed"
                ]
            )

    def test_rejects_tampered_normalized_input(self):
        with tempfile.TemporaryDirectory() as directory:
            player, high = self.make_inputs(Path(directory))
            with (high / "player_week_high_value.csv").open("ab") as handle:
                handle.write(b"tampered")
            with self.assertRaisesRegex(HighValueBacktestDataError, "hash mismatch"):
                build_high_value_backtest(
                    player, high, target_seasons=(2023,), history_lookback=2
                )

    def test_writes_hash_verified_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            player, high = self.make_inputs(root)
            result = build_high_value_backtest(
                player, high, target_seasons=(2023,), history_lookback=2,
                bootstrap_samples=100,
            )
            path = write_high_value_backtest_snapshot(result, root / "derived")
            manifest = json.loads((path / "manifest.json").read_text())
            raw = (path / "room_evaluation.csv").read_bytes()
            self.assertEqual(
                manifest["artifacts"]["room_evaluation.csv"]["sha256"],
                hashlib.sha256(raw).hexdigest(),
            )
            self.assertEqual(
                manifest["quality"]["maximum_prediction_reconciliation_error"], 0
            )

    def test_metric_bootstrap_is_independent_of_unrelated_scopes(self):
        def rows_for(metric, position, offset):
            rows = []
            for index in range(12):
                base = 0.30 + index / 1000
                challenger = base - 0.01 + ((index % 3) - 1) / 1000 + offset
                for model, value in (
                    ("base_role", base), ("rate_adjusted_p24", challenger)
                ):
                    rows.append({
                        "target_season": 2023,
                        "window_end": 4,
                        "team": f"T{index:02d}",
                        "position": position,
                        "metric": metric,
                        "model": model,
                        "total_variation_distance": f"{value:.6f}",
                    })
            return rows

        target = rows_for("WR_DEEP_TARGETS", "WR", 0.0)
        unrelated = rows_for("QB_RED_ZONE_DESIGNED_CARRIES", "QB", 0.004)

        def select(rows):
            return next(
                row for row in paired_comparisons(rows, samples=200, seed=7)
                if row["segment"] == "metric"
                and row["scope"] == "WR_DEEP_TARGETS"
                and row["challenger"] == "rate_adjusted_p24"
            )

        self.assertEqual(select(target), select(unrelated + target))


if __name__ == "__main__":
    unittest.main()
