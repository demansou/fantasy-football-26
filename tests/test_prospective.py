import csv
import hashlib
import io
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from fantasy_draft.prospective import (
    CORRECTION_NOTICE,
    EXPECTED_MODEL_VERSIONS,
    ProspectiveFreezeDataError,
    build_prospective_freeze,
    verify_prospective_freeze,
    write_prospective_freeze,
)


METRIC = "RB_INSIDE_5_CARRIES"
TEAMS = tuple(f"T{index:02d}" for index in range(32))


def write_csv(path: Path, fields, rows) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    raw = stream.getvalue().encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def write_snapshot(
    root: Path,
    component: str,
    tables,
    *,
    extra_manifest=None,
) -> Path:
    snapshot = root / component
    artifacts = {}
    for filename, (fields, rows) in tables.items():
        raw = write_csv(snapshot / filename, fields, rows)
        artifacts[filename] = {"sha256": hashlib.sha256(raw).hexdigest()}
    manifest = {
        "model_version": EXPECTED_MODEL_VERSIONS[component],
        "season": 2026,
        "as_of": "2026-09-01",
        "artifacts": artifacts,
    }
    manifest.update(extra_manifest or {})
    (snapshot / "manifest.json").write_text(json.dumps(manifest))
    return snapshot


class ProspectiveFreezeTests(unittest.TestCase):
    def make_inputs(self, root: Path, *, complete_review: bool = True):
        team_system_fields = (
            "season", "team", "head_coach", "play_caller",
            "broad_system_certainty_v0", "exact_style_certainty_v0",
            "model_status",
        )
        team_systems = [{
            "season": 2026,
            "team": team,
            "head_coach": f"Coach {team}",
            "play_caller": f"Caller {team}",
            "broad_system_certainty_v0": "0.80",
            "exact_style_certainty_v0": "0.70",
            "model_status": "test",
        } for team in TEAMS]
        metric_fields = (
            "season", "team", "play_caller", "metric", "forecast_value_v0",
            "metric_certainty_v0", "model_status",
        )
        metrics = [{
            "season": 2026,
            "team": team,
            "play_caller": f"Caller {team}",
            "metric": "neutral_pass_rate",
            "forecast_value_v0": "0.55",
            "metric_certainty_v0": "0.70",
            "model_status": "test",
        } for team in TEAMS]
        caller = write_snapshot(root, "caller_fingerprints", {
            "teams.csv": (team_system_fields, team_systems),
            "metric_forecasts.csv": (metric_fields, metrics),
        })

        position_fields = (
            "season", "team", "position", "certainty_adjusted_score_v0",
            "team_exact_style_certainty_v0", "model_status",
        )
        positions = [{
            "season": 2026,
            "team": team,
            "position": position,
            "certainty_adjusted_score_v0": "50.0",
            "team_exact_style_certainty_v0": "0.70",
            "model_status": "test",
        } for team in TEAMS for position in ("QB", "RB", "WR", "TE")]
        position = write_snapshot(root, "position_environments", {
            "position_environments.csv": (position_fields, positions),
        })

        role_fields = (
            "season", "team", "position", "resource", "gsis_id",
            "player_name", "role_share_median",
            "full_season_opportunities_median", "model_status",
        )
        roles = [{
            "season": 2026,
            "team": team,
            "position": "RB",
            "resource": "RB_CARRIES",
            "gsis_id": f"p-{team}",
            "player_name": f"Back {team}",
            "role_share_median": "1.0",
            "full_season_opportunities_median": "250.0",
            "model_status": "test",
        } for team in TEAMS]
        candidate_fields = (
            "season", "team", "position", "resource", "gsis_id",
            "player_name", "latent_role_weight", "depth_prior_share",
            "historical_share",
        )
        candidates = [{
            "season": 2026,
            "team": team,
            "position": "RB",
            "resource": "RB_CARRIES",
            "gsis_id": f"p-{team}",
            "player_name": f"Back {team}",
            "latent_role_weight": "1.0",
            "depth_prior_share": "1.0",
            "historical_share": "1.0",
        } for team in TEAMS]
        player_roles = write_snapshot(root, "player_roles", {
            "player_role_priors.csv": (role_fields, roles),
            "player_role_candidates.csv": (candidate_fields, candidates),
        })

        availability_fields = (
            "season", "week", "gameday", "team", "scheduled_game",
            "position", "gsis_id", "player_name", "active_probability_low",
            "active_probability_median", "active_probability_high", "model_status",
        )
        weekly_role_fields = (
            "season", "week", "gameday", "team", "scheduled_game",
            "position", "resource", "gsis_id", "player_name",
            "latent_role_weight", "expected_share_mean",
            "expected_opportunities_this_week", "model_status",
        )
        availability_rows = []
        weekly_roles = []
        for team in TEAMS:
            for week in range(1, 19):
                scheduled = week <= 17
                gameday = (
                    date(2026, 9, 10) + timedelta(days=7 * (week - 1))
                ).isoformat() if scheduled else ""
                base = {
                    "season": 2026,
                    "week": week,
                    "gameday": gameday,
                    "team": team,
                    "scheduled_game": str(scheduled).lower(),
                    "position": "RB",
                    "gsis_id": f"p-{team}",
                    "player_name": f"Back {team}",
                    "model_status": "test",
                }
                availability_rows.append({
                    **base,
                    "active_probability_low": "0.80",
                    "active_probability_median": "0.90",
                    "active_probability_high": "1.00",
                })
                weekly_roles.append({
                    **base,
                    "resource": "RB_CARRIES",
                    "latent_role_weight": "1.0",
                    "expected_share_mean": "1.0",
                    "expected_opportunities_this_week": "15.0",
                })
        availability = write_snapshot(root, "availability", {
            "weekly_availability.csv": (availability_fields, availability_rows),
            "weekly_expected_roles.csv": (weekly_role_fields, weekly_roles),
        })

        high_prior_fields = (
            "season", "team", "position", "metric", "base_resource",
            "gsis_id", "player_name", "base_model_all_affiliated_share",
            "share_p24", "model_status",
        )
        high_priors = [{
            "season": 2026,
            "team": team,
            "position": "RB",
            "metric": METRIC,
            "base_resource": "RB_CARRIES",
            "gsis_id": f"p-{team}",
            "player_name": f"Back {team}",
            "base_model_all_affiliated_share": "1.0",
            "share_p24": "1.0",
            "model_status": "test",
        } for team in TEAMS]
        weekly_high_role_fields = (
            "season", "week", "gameday", "team", "scheduled_game",
            "position", "metric", "base_resource", "gsis_id", "player_name",
            "latent_high_value_share_p24", "expected_share_mean", "model_status",
        )
        weekly_high_roles = [{
            "season": 2026,
            "week": week,
            "gameday": (
                date(2026, 9, 10) + timedelta(days=7 * (week - 1))
            ).isoformat() if week <= 17 else "",
            "team": team,
            "scheduled_game": str(week <= 17).lower(),
            "position": "RB",
            "metric": METRIC,
            "base_resource": "RB_CARRIES",
            "gsis_id": f"p-{team}",
            "player_name": f"Back {team}",
            "latent_high_value_share_p24": "1.0",
            "expected_share_mean": "1.0",
            "model_status": "test",
        } for team in TEAMS for week in range(1, 19)]
        high_value_priors = write_snapshot(root, "high_value_priors", {
            "player_high_value_priors.csv": (high_prior_fields, high_priors),
            "weekly_high_value_roles.csv": (
                weekly_high_role_fields, weekly_high_roles
            ),
        })

        pool_fields = (
            "season", "team", "position", "metric", "base_resource",
            "event_pool_per_game_median", "model_status",
        )
        pools = [{
            "season": 2026,
            "team": team,
            "position": "RB",
            "metric": METRIC,
            "base_resource": "RB_CARRIES",
            "event_pool_per_game_median": "1.5",
            "model_status": "test",
        } for team in TEAMS]
        player_count_fields = (
            "season", "team", "position", "metric", "base_resource",
            "gsis_id", "player_name",
            "availability_adjusted_season_expected_events",
            "requires_current_role_review", "model_status",
        )
        player_counts = [{
            "season": 2026,
            "team": team,
            "position": "RB",
            "metric": METRIC,
            "base_resource": "RB_CARRIES",
            "gsis_id": f"p-{team}",
            "player_name": f"Back {team}",
            "availability_adjusted_season_expected_events": "24.0",
            "requires_current_role_review": str(team == TEAMS[0]).lower(),
            "model_status": "test",
        } for team in TEAMS]
        weekly_count_fields = (
            "season", "week", "gameday", "team", "scheduled_game",
            "position", "metric", "base_resource", "gsis_id", "player_name",
            "expected_event_count_mean", "combined_marginal_scenario_low",
            "combined_marginal_scenario_high", "model_status",
        )
        weekly_counts = [{
            "season": 2026,
            "week": week,
            "gameday": (
                date(2026, 9, 10) + timedelta(days=7 * (week - 1))
            ).isoformat() if week <= 17 else "",
            "team": team,
            "scheduled_game": str(week <= 17).lower(),
            "position": "RB",
            "metric": METRIC,
            "base_resource": "RB_CARRIES",
            "gsis_id": f"p-{team}",
            "player_name": f"Back {team}",
            "expected_event_count_mean": "1.5",
            "combined_marginal_scenario_low": "0.5",
            "combined_marginal_scenario_high": "2.5",
            "model_status": "test",
        } for team in TEAMS for week in range(1, 19)]
        reconciliation_fields = (
            "season", "week", "team", "metric", "reconciliation_error",
        )
        reconciliations = [{
            "season": 2026,
            "week": week,
            "team": team,
            "metric": METRIC,
            "reconciliation_error": "0.0",
        } for team in TEAMS for week in range(1, 19)]
        high_value_volumes = write_snapshot(
            root,
            "high_value_volumes",
            {
                "team_high_value_event_pools.csv": (pool_fields, pools),
                "player_high_value_opportunities.csv": (
                    player_count_fields, player_counts
                ),
                "weekly_player_high_value_opportunities.csv": (
                    weekly_count_fields, weekly_counts
                ),
                "weekly_reconciliation.csv": (
                    reconciliation_fields, reconciliations
                ),
            },
            extra_manifest={"supported_metrics": [METRIC]},
        )

        review_fields = (
            "season", "team", "position", "metric", "gsis_id", "player_name",
            "review_status", "evidence_record_id", "evidence_strength",
            "evidence_as_of", "numeric_override_applied",
        )
        review_status = (
            "reviewed_model_retained" if complete_review else "unreviewed"
        )
        reviews = [{
            "season": 2026,
            "team": TEAMS[0],
            "position": "RB",
            "metric": METRIC,
            "gsis_id": f"p-{TEAMS[0]}",
            "player_name": f"Back {TEAMS[0]}",
            "review_status": review_status,
            "evidence_record_id": "review-1",
            "evidence_strength": "direct_current_role",
            "evidence_as_of": "2026-09-01",
            "numeric_override_applied": "false",
        }]
        team_review_fields = (
            "season", "team", "position", "metric", "review_status",
            "evidence_as_of", "numeric_override_applied",
        )
        coverage_fields = (
            "scope", "metric", "queued_rows", "evidence_reviewed_rows",
            "inconclusive_rows", "unreviewed_rows", "review_coverage",
        )
        coverage = [{
            "scope": "player",
            "metric": "ALL",
            "queued_rows": "1",
            "evidence_reviewed_rows": "1" if complete_review else "0",
            "inconclusive_rows": "0",
            "unreviewed_rows": "0" if complete_review else "1",
            "review_coverage": "1.0" if complete_review else "0.0",
        }]
        source_fields = (
            "source_id", "title", "publisher", "source_type", "url",
            "published_at", "accessed_at",
        )
        sources = [{
            "source_id": "source-1",
            "title": "Official role note",
            "publisher": "Test Club",
            "source_type": "official_team",
            "url": "https://example.com/role",
            "published_at": "2026-08-31",
            "accessed_at": "2026-09-01",
        }]
        role_research = write_snapshot(root, "role_research", {
            "player_review_queue.csv": (review_fields, reviews),
            "team_rate_review_queue.csv": (team_review_fields, []),
            "review_coverage.csv": (coverage_fields, coverage),
            "evidence_sources.csv": (source_fields, sources),
        })
        return (
            caller,
            position,
            player_roles,
            availability,
            high_value_priors,
            high_value_volumes,
            role_research,
        )

    def test_builds_hash_verified_freeze_and_joins_review_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = build_prospective_freeze(
                *self.make_inputs(root), cutoff="2026-09-03"
            )
            self.assertEqual(result.first_scheduled_game.isoformat(), "2026-09-10")
            self.assertEqual(result.quality["team_count"], 32)
            self.assertEqual(result.quality["role_review_unreviewed_rows"], 0)
            output = write_prospective_freeze(result, root / "derived")
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["correction_notice"], CORRECTION_NOTICE)
            for filename, metadata in manifest["artifacts"].items():
                self.assertEqual(
                    metadata["sha256"],
                    hashlib.sha256((output / filename).read_bytes()).hexdigest(),
                )
            verified = verify_prospective_freeze(
                output, expected_fingerprint=result.freeze_fingerprint
            )
            self.assertEqual(
                verified["freeze_fingerprint"], result.freeze_fingerprint
            )
            with (output / "weekly_high_value_count_forecasts.csv").open() as file:
                rows = list(csv.DictReader(file))
            reviewed = [row for row in rows if row["team"] == TEAMS[0]]
            unflagged = [row for row in rows if row["team"] == TEAMS[1]]
            self.assertTrue(all(
                row["current_role_review_status"] == "reviewed_model_retained"
                for row in reviewed
            ))
            self.assertTrue(all(
                row["current_role_review_status"] == "not_required"
                for row in unflagged
            ))
            with (output / "team_systems.csv").open("ab") as file:
                file.write(b"tampered\n")
            with self.assertRaisesRegex(
                ProspectiveFreezeDataError, "artifact hash mismatch"
            ):
                verify_prospective_freeze(
                    output, expected_fingerprint=result.freeze_fingerprint
                )

    def test_rejects_cutoff_on_or_after_first_game(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs = self.make_inputs(Path(directory))
            with self.assertRaisesRegex(
                ProspectiveFreezeDataError, "must be before first scheduled game"
            ):
                build_prospective_freeze(*inputs, cutoff="2026-09-10")

    def test_rejects_changed_correction_notice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = build_prospective_freeze(
                *self.make_inputs(root), cutoff="2026-09-03"
            )
            output = write_prospective_freeze(result, root / "derived")
            manifest_path = output / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["correction_notice"]["reason"] = "changed after publication"
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(
                ProspectiveFreezeDataError, "correction notice"
            ):
                verify_prospective_freeze(output)

    def test_rejects_tampered_parent_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs = self.make_inputs(Path(directory))
            with (inputs[0] / "teams.csv").open("ab") as file:
                file.write(b"tampered\n")
            with self.assertRaisesRegex(ProspectiveFreezeDataError, "hash mismatch"):
                build_prospective_freeze(*inputs, cutoff="2026-09-03")

    def test_rejects_incomplete_current_role_review(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs = self.make_inputs(Path(directory), complete_review=False)
            with self.assertRaisesRegex(
                ProspectiveFreezeDataError, "unreviewed or invalid"
            ):
                build_prospective_freeze(*inputs, cutoff="2026-09-03")


if __name__ == "__main__":
    unittest.main()
