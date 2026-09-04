import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fantasy_draft.role_backtest import build_role_backtest, write_role_backtest_snapshot


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


class RoleBacktestTests(unittest.TestCase):
    def make_history(
        self,
        root: Path,
        *,
        reverse_target: bool = False,
        include_unallocated_week: bool = False,
    ) -> Path:
        history = root / ("history-reverse" if reverse_target else "history")
        write_csv(
            history / "weekly_rosters.csv",
            [
                "season", "week", "team", "position", "gsis_id", "player_name",
                "status", "status_description",
            ],
            [
                {"season": 2023, "week": 1, "team": "AAA", "position": "RB", "gsis_id": "r1", "player_name": "One Back", "status": "ACT", "status_description": "A01"},
                {"season": 2023, "week": 1, "team": "AAA", "position": "RB", "gsis_id": "r2", "player_name": "Two Back", "status": "INA", "status_description": "A01"},
            ],
        )
        write_csv(
            history / "opening_depth.csv",
            [
                "season", "team", "position", "gsis_id", "player_name",
                "depth_position", "depth_rank", "temporal_precision",
            ],
            [
                {"season": 2023, "team": "AAA", "position": "RB", "gsis_id": "r1", "player_name": "One Back", "depth_position": "RB", "depth_rank": 1, "temporal_precision": "week_1_label_only_no_source_timestamp"},
                {"season": 2023, "team": "AAA", "position": "RB", "gsis_id": "r2", "player_name": "Two Back", "depth_position": "RB", "depth_rank": 2, "temporal_precision": "week_1_label_only_no_source_timestamp"},
            ],
        )
        opportunity_fields = [
            "season", "week", "team", "position", "gsis_id", "player_name",
            "dropbacks", "carries", "targets",
        ]
        opportunities: list[dict[str, object]] = []
        for season in (2021, 2022):
            opportunities.extend([
                {"season": season, "week": 1, "team": "AAA", "position": "RB", "gsis_id": "r1", "player_name": "One Back", "dropbacks": 0, "carries": 80, "targets": 16},
                {"season": season, "week": 1, "team": "AAA", "position": "RB", "gsis_id": "r2", "player_name": "Two Back", "dropbacks": 0, "carries": 20, "targets": 4},
            ])
        target = (15, 65) if reverse_target else (65, 15)
        opportunities.extend([
            {"season": 2023, "week": 1, "team": "AAA", "position": "RB", "gsis_id": "r1", "player_name": "One Back", "dropbacks": 0, "carries": target[0], "targets": target[0] / 5},
            {"season": 2023, "week": 1, "team": "AAA", "position": "RB", "gsis_id": "r2", "player_name": "Two Back", "dropbacks": 0, "carries": target[1], "targets": target[1] / 5},
            {"season": 2023, "week": 1, "team": "AAA", "position": "RB", "gsis_id": "r3", "player_name": "Late Back", "dropbacks": 0, "carries": 20, "targets": 4},
        ])
        if include_unallocated_week:
            opportunities.append(
                {"season": 2023, "week": 2, "team": "AAA", "position": "RB", "gsis_id": "r3", "player_name": "Late Back", "dropbacks": 0, "carries": 10, "targets": 2}
            )
        write_csv(history / "weekly_opportunities.csv", opportunity_fields, opportunities)
        return history

    def test_player_split_outcomes_do_not_change_forecast_when_oracles_fixed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = build_role_backtest(
                self.make_history(root), target_seasons=(2023,),
                history_lookback=2, bootstrap_samples=100, random_seed=1,
            )
            second = build_role_backtest(
                self.make_history(root, reverse_target=True), target_seasons=(2023,),
                history_lookback=2, bootstrap_samples=100, random_seed=1,
            )
            def forecasts(result):
                return {
                    (row["resource"], row["model"], row["gsis_id"]): row["predicted_share"]
                    for row in result.prediction_rows if int(row["window_end"]) == 4
                }
            self.assertEqual(forecasts(first), forecasts(second))
            self.assertTrue(all(
                abs(float(row["prediction_share_sum"]) - 1) < 1e-9
                for row in first.room_rows
            ))
            late = [row for row in first.prediction_rows if row["gsis_id"] == "r3"]
            self.assertTrue(late)
            self.assertTrue(all(float(row["predicted_share"]) == 0 for row in late))
            self.assertTrue(all(row["opening_candidate"] == "false" for row in late))
            self.assertTrue(all(row["row_type"] == "later_entrant" for row in late))
            self.assertLess(
                float(next(row for row in first.room_rows if row["model"] == "depth_only")["opening_candidate_actual_share"]),
                1,
            )

    def test_positive_pool_without_active_opening_candidate_is_scored_unallocated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = build_role_backtest(
                self.make_history(root, include_unallocated_week=True),
                target_seasons=(2023,), history_lookback=2,
                bootstrap_samples=100, random_seed=1,
            )
            unallocated = [
                row for row in result.prediction_rows
                if row["resource"] == "RB_CARRIES"
                and int(row["window_end"]) == 4
                and row["gsis_id"] == "__UNALLOCATED__"
            ]
            self.assertEqual(len(unallocated), 3)
            self.assertTrue(all(row["row_type"] == "unallocated" for row in unallocated))
            self.assertTrue(all(abs(float(row["predicted_share"]) - 10 / 110) < 1e-9 for row in unallocated))
            self.assertTrue(all(float(row["actual_share"]) == 0 for row in unallocated))

    def test_writes_hash_verified_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = build_role_backtest(
                self.make_history(root), target_seasons=(2023,),
                history_lookback=2, bootstrap_samples=100,
            )
            path = write_role_backtest_snapshot(result, root / "derived")
            manifest = json.loads((path / "manifest.json").read_text())
            raw = (path / "room_evaluation.csv").read_bytes()
            self.assertEqual(
                manifest["artifacts"]["room_evaluation.csv"]["sha256"],
                hashlib.sha256(raw).hexdigest(),
            )
            self.assertEqual(
                manifest["quality"]["maximum_prediction_reconciliation_error"], 0
            )


if __name__ == "__main__":
    unittest.main()
