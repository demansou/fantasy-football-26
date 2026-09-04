import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from fantasy_draft.availability import AVAILABILITY_FIELDS
from fantasy_draft.high_value_backtest import (
    COMPARISON_FIELDS,
    EVALUATION_FIELDS,
    MODEL_PRIORS,
    recommend_high_value_metrics,
)
from fantasy_draft.high_value_history import WEEKLY_FIELDS
from fantasy_draft.high_value_priors import (
    HighValuePriorDataError,
    build_high_value_priors,
    write_high_value_prior_snapshot,
)
from fantasy_draft.player_roles import ROLE_CANDIDATE_FIELDS


def write_csv(path: Path, fields, rows) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    raw = stream.getvalue().encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


class HighValuePriorTests(unittest.TestCase):
    def make_inputs(self, root: Path):
        roles = root / "roles"
        role_rows = []
        for player_id, name in (("r1", "One Back"), ("r2", "Two Back")):
            row = {field: "" for field in ROLE_CANDIDATE_FIELDS}
            row.update({
                "season": 2026,
                "team": "AAA",
                "position": "RB",
                "resource": "RB_CARRIES",
                "gsis_id": player_id,
                "player_name": name,
                "current_status": "ACT",
                "roster_status": "ACT",
                "depth_rank": 1 if player_id == "r1" else 2,
                "current_active": "true",
                "active_baseline_share": "0.500000",
                "all_affiliated_share": "0.500000",
                "latent_role_weight": "0.500000000",
                "role_evidence_score_v0": "80.0",
                "role_evidence_label": "strong_role_evidence",
                "candidate_method": "active_share_preserving_all_affiliated_v0",
            })
            role_rows.append(row)
        role_raw = write_csv(
            roles / "player_role_candidates.csv", ROLE_CANDIDATE_FIELDS, role_rows
        )
        (roles / "manifest.json").write_text(json.dumps({
            "artifacts": {
                "player_role_candidates.csv": {
                    "sha256": hashlib.sha256(role_raw).hexdigest()
                }
            }
        }))

        history = root / "history"
        history_rows = []
        for season in (2023, 2024, 2025):
            for player_id, name, inside_five in (
                ("r1", "One Back", 10), ("r2", "Two Back", 0)
            ):
                row = {field: 0 for field in WEEKLY_FIELDS}
                row.update({
                    "season": season,
                    "week": 1,
                    "team": "AAA",
                    "position": "RB",
                    "gsis_id": player_id,
                    "player_name": name,
                    "read_source_available": "true",
                    "carries": 50,
                    "inside_5_carries": inside_five,
                    "target_air_yards": "0.000",
                })
                history_rows.append(row)
        history_raw = write_csv(
            history / "player_week_high_value.csv", WEEKLY_FIELDS, history_rows
        )
        (history / "manifest.json").write_text(json.dumps({
            "artifacts": {
                "player_week_high_value.csv": {
                    "sha256": hashlib.sha256(history_raw).hexdigest()
                }
            }
        }))

        backtest = root / "backtest"
        evaluations = []
        mean_by_model = {
            "base_role": 0.30,
            "rate_adjusted_p12": 0.25,
            "rate_adjusted_p24": 0.24,
            "rate_adjusted_p48": 0.26,
        }
        for window in (4, 8, 18):
            for model in MODEL_PRIORS:
                row = {field: "0" for field in EVALUATION_FIELDS}
                row.update({
                    "segment": "metric",
                    "scope": "RB_INSIDE_5_CARRIES",
                    "window_end": window,
                    "model": model,
                    "room_count": 80,
                    "actual_event_count": 600,
                    "mean_total_variation": f"{mean_by_model[model]:.6f}",
                })
                evaluations.append(row)
        comparisons = []
        for window in (4, 8, 18):
            row = {field: "0" for field in COMPARISON_FIELDS}
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
            backtest / "model_evaluation.csv", EVALUATION_FIELDS, evaluations
        )
        comparison_raw = write_csv(
            backtest / "paired_comparisons.csv", COMPARISON_FIELDS, comparisons
        )
        recommendation = recommend_high_value_metrics(evaluations, comparisons)
        (backtest / "manifest.json").write_text(json.dumps({
            "model_version": "high-value-role-backtest-v0.2.0",
            "parameters": {
                "history_lookback": 3,
                "model_prior_opportunities": dict(MODEL_PRIORS),
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

        availability = root / "availability"
        availability_rows = []
        for week in range(1, 19):
            for player_id, name in (("r1", "One Back"), ("r2", "Two Back")):
                row = {field: "" for field in AVAILABILITY_FIELDS}
                row.update({
                    "season": 2026,
                    "week": week,
                    "gameday": "" if week == 8 else f"2026-10-{week:02d}",
                    "team": "AAA",
                    "opponent": "" if week == 8 else "BBB",
                    "home_away": "" if week == 8 else "home",
                    "scheduled_game": "false" if week == 8 else "true",
                    "position": "RB",
                    "gsis_id": player_id,
                    "player_name": name,
                    "current_status": "ACT",
                    "active_probability_median": "1.000000",
                    "model_status": "test",
                })
                availability_rows.append(row)
        availability_raw = write_csv(
            availability / "weekly_availability.csv",
            AVAILABILITY_FIELDS,
            availability_rows,
        )
        (availability / "manifest.json").write_text(json.dumps({
            "season": 2026,
            "parameters": {"simulation_draws": 100},
            "inputs": {
                "sha256": {
                    "player_role_candidates.csv": hashlib.sha256(role_raw).hexdigest()
                }
            },
            "artifacts": {
                "weekly_availability.csv": {
                    "sha256": hashlib.sha256(availability_raw).hexdigest()
                }
            },
        }))
        return roles, history, backtest, availability

    def test_builds_reconciled_current_and_weekly_conditional_shares(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs = self.make_inputs(Path(directory))
            result = build_high_value_priors(*inputs, random_seed=1)
            self.assertEqual(result.supported_metrics, ("RB_INSIDE_5_CARRIES",))
            current = {row["gsis_id"]: row for row in result.prior_rows}
            self.assertGreater(float(current["r1"]["share_p24"]), 0.5)
            self.assertAlmostEqual(
                sum(float(row["share_p24"]) for row in result.prior_rows), 1.0
            )
            week_one = [row for row in result.weekly_rows if row["week"] == 1]
            self.assertAlmostEqual(
                sum(float(row["expected_share_mean"]) for row in week_one), 1.0
            )
            bye = [row for row in result.weekly_rows if row["week"] == 8]
            self.assertEqual(sum(float(row["expected_share_mean"]) for row in bye), 0)
            self.assertEqual(len(result.weekly_rows), 36)
            self.assertTrue(
                all(float(row["reconciliation_error"]) == 0 for row in result.room_rows)
            )
            self.assertTrue(
                all(
                    float(row["reconciliation_error"]) == 0
                    for row in result.weekly_reconciliation
                )
            )

    def test_rejects_tampered_role_input(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs = self.make_inputs(Path(directory))
            with (inputs[0] / "player_role_candidates.csv").open("ab") as handle:
                handle.write(b"tampered")
            with self.assertRaisesRegex(HighValuePriorDataError, "hash mismatch"):
                build_high_value_priors(*inputs)

    def test_recomputes_and_rejects_edited_backtest_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs = self.make_inputs(Path(directory))
            path = inputs[2] / "manifest.json"
            manifest = json.loads(path.read_text())
            manifest["recommendation"]["supported_metrics"] = []
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(
                HighValuePriorDataError, "does not reproduce"
            ):
                build_high_value_priors(*inputs)

    def test_writes_hash_verified_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = build_high_value_priors(*self.make_inputs(root), random_seed=1)
            path = write_high_value_prior_snapshot(result, root / "derived")
            manifest = json.loads((path / "manifest.json").read_text())
            raw = (path / "player_high_value_priors.csv").read_bytes()
            self.assertEqual(
                manifest["artifacts"]["player_high_value_priors.csv"]["sha256"],
                hashlib.sha256(raw).hexdigest(),
            )
            self.assertEqual(manifest["quality"]["maximum_weekly_reconciliation_error"], 0)


if __name__ == "__main__":
    unittest.main()
