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
from fantasy_draft.high_value_priors import (
    PRIOR_FIELDS,
    REVIEW_FIELDS as PRIOR_REVIEW_FIELDS,
    WEEKLY_FIELDS as SHARE_WEEKLY_FIELDS,
)
from fantasy_draft.high_value_volume_backtest import (
    build_high_value_volume_backtest,
    write_high_value_volume_backtest_snapshot,
)
from fantasy_draft.high_value_volumes import (
    HighValueVolumeDataError,
    build_high_value_volumes,
    write_high_value_volume_snapshot,
)
from fantasy_draft.player_roles import RECONCILIATION_FIELDS as ROLE_RECONCILIATION_FIELDS
from fantasy_draft.resource_backtest import (
    build_resource_backtest,
    write_resource_backtest_snapshot,
)


RESOURCE_OPPORTUNITY_FIELDS = (
    "season", "week", "team", "position", "gsis_id", "player_name",
    "dropbacks", "carries", "targets",
)
RESOURCE_SCHEDULE_FIELDS = (
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


class HighValueVolumeTests(unittest.TestCase):
    def make_inputs(self, root: Path):
        history = root / "history"
        history_rows = []
        for season in range(2021, 2026):
            for index in range(20):
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
                    "inside_5_carries": 40 if index >= 10 else 0,
                    "target_air_yards": "0.000",
                })
                history_rows.append(row)
        history_raw = write_csv(
            history / "team_week_high_value.csv", TEAM_WEEK_FIELDS, history_rows
        )
        (history / "manifest.json").write_text(json.dumps({
            "artifacts": {
                "team_week_high_value.csv": {
                    "sha256": hashlib.sha256(history_raw).hexdigest()
                }
            }
        }))

        role_test = root / "role-test"
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
                "segment": "metric", "scope": "RB_INSIDE_5_CARRIES",
                "window_end": window, "challenger": "rate_adjusted_p24",
                "baseline": "base_role", "room_count": 80, "cluster_count": 80,
                "mean_tv_delta": "-0.060000", "delta_ci90_low": "-0.080000",
                "delta_ci90_high": "-0.040000", "paired_room_win_rate": "0.700000",
                "interpretation": "challenger_lower_error_ci_excludes_zero",
            })
            comparisons.append(row)
        eval_raw = write_csv(
            role_test / "model_evaluation.csv", ROLE_EVALUATION_FIELDS, evaluations
        )
        comp_raw = write_csv(
            role_test / "paired_comparisons.csv", ROLE_COMPARISON_FIELDS, comparisons
        )
        role_recommendation = recommend_high_value_metrics(evaluations, comparisons)
        (role_test / "manifest.json").write_text(json.dumps({
            "model_version": "high-value-role-backtest-v0.2.0",
            "parameters": {"model_prior_opportunities": dict(ROLE_MODEL_PRIORS)},
            "recommendation": role_recommendation,
            "artifacts": {
                "model_evaluation.csv": {"sha256": hashlib.sha256(eval_raw).hexdigest()},
                "paired_comparisons.csv": {"sha256": hashlib.sha256(comp_raw).hexdigest()},
            },
        }))
        volume_result = build_high_value_volume_backtest(
            history, role_test, bootstrap_samples=100, random_seed=1
        )
        volume_test = write_high_value_volume_backtest_snapshot(
            volume_result, root / "derived"
        )

        resource_history = root / "resource-history"
        resource_opportunities = []
        resource_schedule = []
        for season in range(2021, 2026):
            season_offset = (season - 2021) % 3
            for week in range(1, 19):
                for team, opponent, team_offset in (
                    ("AAA", "BBB", 0),
                    ("BBB", "AAA", 1),
                ):
                    resource_schedule.append({
                        "season": season,
                        "week": week,
                        "gameday": f"{season}-09-{min(week, 28):02d}",
                        "game_id": f"{season}_{week:02d}_{team}",
                        "team": team,
                        "opponent": opponent,
                        "home_away": "home" if team == "AAA" else "away",
                    })
                    resource_opportunities.extend((
                        {
                            "season": season, "week": week, "team": team,
                            "position": "RB", "gsis_id": f"{team}-rb",
                            "player_name": f"{team} Back", "dropbacks": 0,
                            "carries": 18 + 4 * team_offset + season_offset,
                            "targets": 4 + team_offset + season_offset,
                        },
                        {
                            "season": season, "week": week, "team": team,
                            "position": "WR", "gsis_id": f"{team}-wr",
                            "player_name": f"{team} Receiver", "dropbacks": 0,
                            "carries": 0,
                            "targets": 16 + 3 * team_offset + season_offset,
                        },
                        {
                            "season": season, "week": week, "team": team,
                            "position": "TE", "gsis_id": f"{team}-te",
                            "player_name": f"{team} Tight End", "dropbacks": 0,
                            "carries": 0,
                            "targets": 6 + team_offset + season_offset,
                        },
                    ))
        resource_opportunity_raw = write_csv(
            resource_history / "weekly_opportunities.csv",
            RESOURCE_OPPORTUNITY_FIELDS,
            resource_opportunities,
        )
        resource_schedule_raw = write_csv(
            resource_history / "team_schedule.csv",
            RESOURCE_SCHEDULE_FIELDS,
            resource_schedule,
        )
        (resource_history / "manifest.json").write_text(json.dumps({
            "artifacts": {"normalized": {
                "weekly_opportunities.csv": {
                    "sha256": hashlib.sha256(resource_opportunity_raw).hexdigest()
                },
                "team_schedule.csv": {
                    "sha256": hashlib.sha256(resource_schedule_raw).hexdigest()
                },
            }}
        }))
        resource_result = build_resource_backtest(
            resource_history,
            bootstrap_samples=100,
            random_seed=1,
            expected_team_count=2,
        )
        resource_test = write_resource_backtest_snapshot(
            resource_result, root / "derived"
        )

        roles = root / "roles"
        role_pool = {field: "" for field in ROLE_RECONCILIATION_FIELDS}
        role_pool.update({
            "season": 2026,
            "team": "AAA",
            "position": "RB",
            "resource": "RB_CARRIES",
            "active_player_count": 2,
            "team_pool_per_game": "20.000000",
            "team_pool_full_season": "340.000",
            "median_share_sum": "1.000000000000",
            "allocated_per_game_sum": "20.000000",
            "reconciliation_error": "0.000000000000",
            "scope": "test",
            "model_status": "test",
        })
        role_pool_raw = write_csv(
            roles / "team_reconciliation.csv", ROLE_RECONCILIATION_FIELDS, [role_pool]
        )
        (roles / "manifest.json").write_text(json.dumps({
            "artifacts": {
                "team_reconciliation.csv": {
                    "sha256": hashlib.sha256(role_pool_raw).hexdigest()
                }
            }
        }))

        priors = root / "priors"
        player_rows = []
        for player_id, name in (("r1", "One Back"), ("r2", "Two Back")):
            row = {field: "" for field in PRIOR_FIELDS}
            row.update({
                "season": 2026, "team": "AAA", "position": "RB",
                "metric": "RB_INSIDE_5_CARRIES", "base_resource": "RB_CARRIES",
                "gsis_id": player_id, "player_name": name, "current_status": "ACT",
                "roster_status": "ACT", "current_active": "true",
                "share_p12": "0.500000000", "share_p24": "0.500000000",
                "share_p48": "0.500000000", "active_conditional_share_p24": "0.500000000",
                "role_evidence_score_v0": "80.0", "role_evidence_label": "strong",
                "history_support": "strong_at_least_48_opportunities",
                "historical_base_opportunities": "100.000000",
            })
            player_rows.append(row)
        player_raw = write_csv(
            priors / "player_high_value_priors.csv", PRIOR_FIELDS, player_rows
        )
        prior_review_raw = write_csv(
            priors / "source_review.csv",
            PRIOR_REVIEW_FIELDS,
            [{
                "season": 2026,
                "team": "AAA",
                "position": "RB",
                "metric": "RB_INSIDE_5_CARRIES",
                "gsis_id": "r1",
                "player_name": "One Back",
                "issue": "material_role_with_limited_player_metric_history",
                "details": "test review reason",
            }],
        )
        weekly_rows = []
        weekly_reconciliation = []
        reconciliation_fields = (
            "season", "week", "gameday", "team", "opponent", "home_away",
            "scheduled_game", "position", "metric", "base_resource",
            "candidate_count", "simulation_draws", "reconciliation_target",
            "expected_player_share_sum", "unallocated_draw_rate",
            "reconciled_share_sum", "reconciliation_error",
        )
        for week in range(1, 19):
            scheduled = week != 8
            for player_id, name in (("r1", "One Back"), ("r2", "Two Back")):
                row = {field: "" for field in SHARE_WEEKLY_FIELDS}
                row.update({
                    "season": 2026, "week": week,
                    "gameday": f"2026-10-{week:02d}" if scheduled else "",
                    "team": "AAA", "opponent": "BBB" if scheduled else "",
                    "home_away": "home" if scheduled else "",
                    "scheduled_game": str(scheduled).lower(), "position": "RB",
                    "metric": "RB_INSIDE_5_CARRIES", "base_resource": "RB_CARRIES",
                    "gsis_id": player_id, "player_name": name, "current_status": "ACT",
                    "active_probability_median": "1.000000",
                    "expected_share_mean": "0.500000000" if scheduled else "0.000000000",
                    "share_p10": "0.500000000" if scheduled else "0.000000000",
                    "share_p50": "0.500000000" if scheduled else "0.000000000",
                    "share_p90": "0.500000000" if scheduled else "0.000000000",
                    "simulation_draws": 100,
                })
                weekly_rows.append(row)
            weekly_reconciliation.append({
                "season": 2026, "week": week,
                "gameday": f"2026-10-{week:02d}" if scheduled else "",
                "team": "AAA", "opponent": "BBB" if scheduled else "",
                "home_away": "home" if scheduled else "",
                "scheduled_game": str(scheduled).lower(), "position": "RB",
                "metric": "RB_INSIDE_5_CARRIES", "base_resource": "RB_CARRIES",
                "candidate_count": 2, "simulation_draws": 100,
                "reconciliation_target": "1.000000000" if scheduled else "0.000000000",
                "expected_player_share_sum": "1.000000000" if scheduled else "0.000000000",
                "unallocated_draw_rate": "0.000000000",
                "reconciled_share_sum": "1.000000000" if scheduled else "0.000000000",
                "reconciliation_error": "0.000000000000",
            })
        weekly_raw = write_csv(
            priors / "weekly_high_value_roles.csv", SHARE_WEEKLY_FIELDS, weekly_rows
        )
        recon_raw = write_csv(
            priors / "weekly_reconciliation.csv", reconciliation_fields,
            weekly_reconciliation,
        )
        (priors / "manifest.json").write_text(json.dumps({
            "model_version": "high-value-role-prior-v0.2.0",
            "season": 2026,
            "supported_metrics": ["RB_INSIDE_5_CARRIES"],
            "inputs": {"sha256": {
                "player_roles_manifest.json": hashlib.sha256(
                    (roles / "manifest.json").read_bytes()
                ).hexdigest(),
                "high_value_history_manifest.json": hashlib.sha256(
                    (history / "manifest.json").read_bytes()
                ).hexdigest(),
                "high_value_backtest_manifest.json": hashlib.sha256(
                    (role_test / "manifest.json").read_bytes()
                ).hexdigest(),
            }},
            "artifacts": {
                "player_high_value_priors.csv": {"sha256": hashlib.sha256(player_raw).hexdigest()},
                "source_review.csv": {"sha256": hashlib.sha256(prior_review_raw).hexdigest()},
                "weekly_high_value_roles.csv": {"sha256": hashlib.sha256(weekly_raw).hexdigest()},
                "weekly_reconciliation.csv": {"sha256": hashlib.sha256(recon_raw).hexdigest()},
            },
        }))
        return roles, history, priors, volume_test, resource_test

    def test_builds_reconciled_team_and_player_event_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            result = build_high_value_volumes(*self.make_inputs(Path(directory)))
            self.assertEqual(len(result.team_pool_rows), 1)
            self.assertEqual(len(result.player_rows), 2)
            self.assertEqual(len(result.weekly_rows), 36)
            self.assertEqual(len(result.reconciliation_rows), 18)
            team_pool = float(result.team_pool_rows[0]["event_pool_per_game_median"])
            team_row = result.team_pool_rows[0]
            self.assertGreater(float(team_row["resource_error_radius_per_game"]), 0)
            self.assertLess(
                float(team_row["base_resource_pool_per_game_low"]),
                float(team_row["base_resource_pool_per_game"]),
            )
            self.assertGreater(
                float(team_row["base_resource_pool_per_game_high"]),
                float(team_row["base_resource_pool_per_game"]),
            )
            self.assertIn("provisional_transfer", team_row["resource_interval_status"])
            self.assertAlmostEqual(
                float(result.player_rows[0]["current_active_events_per_game_median"]),
                team_pool / 2,
            )
            self.assertAlmostEqual(
                float(result.player_rows[0]["availability_adjusted_season_expected_events"]),
                team_pool * 17 / 2,
                places=5,
            )
            self.assertTrue(all(
                float(row["reconciliation_error"]) == 0
                for row in result.reconciliation_rows
            ))
            by_id = {row["gsis_id"]: row for row in result.player_rows}
            self.assertEqual(by_id["r1"]["requires_current_role_review"], "true")
            self.assertIn(
                "material_role_with_limited_player_metric_history",
                by_id["r1"]["current_role_review_issues"],
            )
            self.assertEqual(by_id["r2"]["requires_current_role_review"], "false")

    def test_rejects_tampered_role_pool(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs = self.make_inputs(Path(directory))
            with (inputs[0] / "team_reconciliation.csv").open("ab") as handle:
                handle.write(b"tampered")
            with self.assertRaisesRegex(HighValueVolumeDataError, "hash mismatch"):
                build_high_value_volumes(*inputs)

    def test_rejects_edited_backtest_recommendation(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs = self.make_inputs(Path(directory))
            path = inputs[3] / "manifest.json"
            manifest = json.loads(path.read_text())
            manifest["recommendation"]["team_specific_metrics"] = []
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(HighValueVolumeDataError, "does not reproduce"):
                build_high_value_volumes(*inputs)

    def test_rejects_tampered_resource_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs = self.make_inputs(Path(directory))
            with (inputs[4] / "resource_calibration.csv").open("ab") as handle:
                handle.write(b"tampered")
            with self.assertRaisesRegex(HighValueVolumeDataError, "hash mismatch"):
                build_high_value_volumes(*inputs)

    def test_writes_hash_verified_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = build_high_value_volumes(*self.make_inputs(root))
            path = write_high_value_volume_snapshot(result, root / "output")
            manifest = json.loads((path / "manifest.json").read_text())
            raw = (path / "player_high_value_opportunities.csv").read_bytes()
            self.assertEqual(
                manifest["artifacts"]["player_high_value_opportunities.csv"]["sha256"],
                hashlib.sha256(raw).hexdigest(),
            )
            self.assertEqual(manifest["quality"]["maximum_weekly_reconciliation_error"], 0)
            self.assertIn("minimum_resource_holdout_coverage", manifest["quality"])


if __name__ == "__main__":
    unittest.main()
