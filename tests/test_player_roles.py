import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fantasy_draft.player_roles import build_player_roles, write_player_role_snapshot


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


class PlayerRoleTests(unittest.TestCase):
    def make_inputs(self, root: Path):
        context = root / "context"
        roster_fields = [
            "season", "team", "roster_team", "fantasy_position", "current_status",
            "roster_status", "full_name", "display_name", "first_name", "last_name",
            "football_name", "gsis_id", "catalog_latest_team", "catalog_status",
        ]
        roster = [
            {"season": 2026, "team": "AAA", "roster_team": "AAA", "fantasy_position": "QB", "current_status": "ACT", "roster_status": "ACT", "full_name": "Alpha QB", "display_name": "Alpha QB", "first_name": "Alpha", "last_name": "QB", "football_name": "Alpha", "gsis_id": "q1", "catalog_latest_team": "AAA", "catalog_status": "ACT"},
            {"season": 2026, "team": "AAA", "roster_team": "AAA", "fantasy_position": "QB", "current_status": "ACT", "roster_status": "ACT", "full_name": "Backup QB", "display_name": "Backup QB", "first_name": "Backup", "last_name": "QB", "football_name": "Backup", "gsis_id": "q2", "catalog_latest_team": "AAA", "catalog_status": "ACT"},
            {"season": 2026, "team": "AAA", "roster_team": "AAA", "fantasy_position": "RB", "current_status": "ACT", "roster_status": "ACT", "full_name": "Beta Back", "display_name": "Beta Back", "first_name": "Beta", "last_name": "Back", "football_name": "Beta", "gsis_id": "r1", "catalog_latest_team": "AAA", "catalog_status": "ACT"},
            {"season": 2026, "team": "AAA", "roster_team": "AAA", "fantasy_position": "RB", "current_status": "PUP", "roster_status": "ACT", "full_name": "Reserve Back", "display_name": "Reserve Back", "first_name": "Reserve", "last_name": "Back", "football_name": "Reserve", "gsis_id": "r2", "catalog_latest_team": "AAA", "catalog_status": "PUP"},
            {"season": 2026, "team": "AAA", "roster_team": "AAA", "fantasy_position": "WR", "current_status": "ACT", "roster_status": "ACT", "full_name": "Gamma Wide", "display_name": "Gamma Wide", "first_name": "Gamma", "last_name": "Wide", "football_name": "Gamma", "gsis_id": "w1", "catalog_latest_team": "AAA", "catalog_status": "ACT"},
            {"season": 2026, "team": "AAA", "roster_team": "OLD", "fantasy_position": "WR", "current_status": "ACT", "roster_status": "RET", "full_name": "Rookie Wide", "display_name": "Rookie Wide", "first_name": "Rookie", "last_name": "Wide", "football_name": "Rookie", "gsis_id": "w2", "catalog_latest_team": "AAA", "catalog_status": "ACT"},
            {"season": 2026, "team": "AAA", "roster_team": "AAA", "fantasy_position": "TE", "current_status": "ACT", "roster_status": "ACT", "full_name": "Delta Tight", "display_name": "Delta Tight", "first_name": "Delta", "last_name": "Tight", "football_name": "Delta", "gsis_id": "t1", "catalog_latest_team": "AAA", "catalog_status": "ACT"},
            {"season": 2026, "team": "BBB", "roster_team": "BBB", "fantasy_position": "RB", "current_status": "ACT", "roster_status": "ACT", "full_name": "Moved Back", "display_name": "Moved Back", "first_name": "Moved", "last_name": "Back", "football_name": "Moved", "gsis_id": "r3", "catalog_latest_team": "BBB", "catalog_status": "ACT"},
            {"season": 2026, "team": "PHI", "roster_team": "DAL", "fantasy_position": "RB", "current_status": "DEV", "roster_status": "CUT", "full_name": "Practice Back", "display_name": "Practice Back", "first_name": "Practice", "last_name": "Back", "football_name": "Practice", "gsis_id": "r4", "catalog_latest_team": "PHI", "catalog_status": "DEV"},
        ]
        write_csv(context / "current_roster.csv", roster_fields, roster)
        depth_fields = [
            "team", "canonical_gsis_id", "identity_status", "fantasy_position",
            "pos_rank", "pos_slot", "pos_abb",
        ]
        write_csv(
            context / "current_depth_chart.csv",
            depth_fields,
            [
                {"team": "AAA", "canonical_gsis_id": "q1", "identity_status": "resolved", "fantasy_position": "QB", "pos_rank": 1, "pos_slot": 9, "pos_abb": "QB"},
                {"team": "AAA", "canonical_gsis_id": "q2", "identity_status": "resolved", "fantasy_position": "QB", "pos_rank": 2, "pos_slot": 9, "pos_abb": "QB"},
                {"team": "AAA", "canonical_gsis_id": "r1", "identity_status": "resolved", "fantasy_position": "RB", "pos_rank": 1, "pos_slot": 11, "pos_abb": "RB"},
                {"team": "AAA", "canonical_gsis_id": "r2", "identity_status": "resolved", "fantasy_position": "RB", "pos_rank": 2, "pos_slot": 11, "pos_abb": "RB"},
                {"team": "AAA", "canonical_gsis_id": "w1", "identity_status": "resolved", "fantasy_position": "WR", "pos_rank": 1, "pos_slot": 1, "pos_abb": "WR"},
                {"team": "AAA", "canonical_gsis_id": "w2", "identity_status": "resolved", "fantasy_position": "WR", "pos_rank": 2, "pos_slot": 2, "pos_abb": "WR"},
                {"team": "AAA", "canonical_gsis_id": "t1", "identity_status": "resolved", "fantasy_position": "TE", "pos_rank": 1, "pos_slot": 10, "pos_abb": "TE"},
            ],
        )
        history_fields = [
            "season", "team", "gsis_id", "position", "games", "dropbacks", "carries",
            "targets", "team_qb_dropbacks", "team_position_carries", "team_position_targets",
        ]
        history = [
            {"season": 2025, "team": "AAA", "gsis_id": "q1", "position": "QB", "games": 17, "dropbacks": 100, "carries": 10, "targets": 0, "team_qb_dropbacks": 100, "team_position_carries": 10, "team_position_targets": 0},
            {"season": 2025, "team": "AAA", "gsis_id": "r1", "position": "RB", "games": 17, "dropbacks": 0, "carries": 80, "targets": 20, "team_qb_dropbacks": 100, "team_position_carries": 80, "team_position_targets": 20},
            {"season": 2025, "team": "AAA", "gsis_id": "r2", "position": "RB", "games": 10, "dropbacks": 0, "carries": 20, "targets": 5, "team_qb_dropbacks": 100, "team_position_carries": 100, "team_position_targets": 25},
            {"season": 2025, "team": "AAA", "gsis_id": "w1", "position": "WR", "games": 17, "dropbacks": 0, "carries": 2, "targets": 60, "team_qb_dropbacks": 100, "team_position_carries": 2, "team_position_targets": 60},
            {"season": 2025, "team": "AAA", "gsis_id": "t1", "position": "TE", "games": 17, "dropbacks": 0, "carries": 0, "targets": 10, "team_qb_dropbacks": 100, "team_position_carries": 0, "team_position_targets": 10},
        ]
        write_csv(context / "historical_usage.csv", history_fields, history)
        source_review_fields = [
            "source", "season", "team", "source_player_id", "source_secondary_id",
            "player_name", "position", "issue", "candidate_gsis_ids", "details",
        ]
        write_csv(context / "source_identity_review.csv", source_review_fields, [])

        environments = root / "environments"
        environment_fields = [
            "season", "team", "position", "forecast_plays_per_game",
            "forecast_pass_plays_per_game", "forecast_rush_plays_per_game",
            "position_target_share",
        ]
        write_csv(
            environments / "position_environments.csv",
            environment_fields,
            [
                {"season": 2026, "team": "AAA", "position": position, "forecast_plays_per_game": 65, "forecast_pass_plays_per_game": 40, "forecast_rush_plays_per_game": 25, "position_target_share": share}
                for position, share in (("QB", ""), ("RB", 0.22), ("WR", 0.62), ("TE", 0.16))
            ],
        )
        styles = root / "styles"
        write_csv(
            styles / "team_style.csv",
            ["season", "team", "plays", "pass_rate", "designed_qb_run_share"],
            [
                {
                    "season": 2025,
                    "team": "AAA",
                    "plays": 200,
                    "pass_rate": 0.5,
                    "designed_qb_run_share": 0,
                }
            ],
        )
        style_raw = (styles / "team_style.csv").read_bytes()
        (styles / "manifest.json").write_text(
            json.dumps(
                {
                    "artifacts": {
                        "normalized": {
                            "path": "team_style.csv",
                            "sha256": hashlib.sha256(style_raw).hexdigest(),
                        }
                    }
                }
            )
        )
        callers = root / "callers"
        write_csv(
            callers / "metric_forecasts.csv",
            ["season", "team", "metric", "forecast_value_v0"],
            [
                {"season": 2026, "team": "AAA", "metric": "qb_scramble_rate", "forecast_value_v0": 0.05},
                {"season": 2026, "team": "AAA", "metric": "designed_qb_run_share", "forecast_value_v0": 0.04},
            ],
        )
        caller_raw = (callers / "metric_forecasts.csv").read_bytes()
        (callers / "manifest.json").write_text(
            json.dumps(
                {
                    "artifacts": {
                        "metric_forecasts.csv": {
                            "sha256": hashlib.sha256(caller_raw).hexdigest()
                        }
                    },
                    "inputs": [
                        {
                            "path": str(styles / "team_style.csv"),
                            "sha256": hashlib.sha256(style_raw).hexdigest(),
                        }
                    ],
                }
            )
        )
        ffc = root / "ffc"
        write_csv(
            ffc / "adp.csv",
            ["source", "source_player_id", "name", "position", "team", "adp", "season"],
            [
                {"source": "fantasy_football_calculator", "source_player_id": "10", "name": "Alpha Q.B.", "position": "QB", "team": "AAA", "adp": 50, "season": 2026},
                {"source": "fantasy_football_calculator", "source_player_id": "11", "name": "Moved Back", "position": "RB", "team": "AAA", "adp": 100, "season": 2026},
                {"source": "fantasy_football_calculator", "source_player_id": "12", "name": "Reserve Back", "position": "RB", "team": "AAA", "adp": 120, "season": 2026},
                {"source": "fantasy_football_calculator", "source_player_id": "13", "name": "Practice Back", "position": "RB", "team": "PHI", "adp": 130, "season": 2026},
            ],
        )
        return context, environments, callers, styles, ffc

    def test_reconciles_every_resource_and_queues_exceptions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            inputs = self.make_inputs(Path(directory))
            result = build_player_roles(
                *inputs[:3], observed_styles=inputs[3], ffc_adp=inputs[4]
            )
            self.assertEqual(len(result.reconciliation), 6)
            self.assertTrue(all(float(row["median_share_sum"]) == 1 for row in result.reconciliation))
            self.assertTrue(all(float(row["reconciliation_error"]) == 0 for row in result.reconciliation))
            moved = next(row for row in result.ffc_crosswalk if row["source_player_id"] == "11")
            self.assertEqual(moved["match_status"], "review_required")
            self.assertEqual(moved["candidate_gsis_ids"], "r3")
            reserve = next(row for row in result.availability_review if row["gsis_id"] == "r2")
            self.assertEqual(reserve["availability_status"], "review_required_not_modeled")
            self.assertEqual(reserve["current_status"], "PUP")
            self.assertFalse(any(row["gsis_id"] == "r2" for row in result.roles))
            practice = next(row for row in result.ffc_crosswalk if row["source_player_id"] == "13")
            self.assertEqual(practice["match_status"], "resolved")
            self.assertEqual(practice["current_status"], "DEV")
            rookie_roles = [row for row in result.roles if row["gsis_id"] == "w2"]
            self.assertTrue(rookie_roles)
            self.assertTrue(all(row["current_status"] == "ACT" for row in rookie_roles))
            rb_candidates = [
                row for row in result.role_candidates
                if row["team"] == "AAA" and row["resource"] == "RB_CARRIES"
            ]
            self.assertEqual({row["gsis_id"] for row in rb_candidates}, {"r1", "r2"})
            self.assertAlmostEqual(
                sum(float(row["latent_role_weight"]) for row in rb_candidates), 1.0, 8
            )
            active = next(row for row in rb_candidates if row["gsis_id"] == "r1")
            reserve_candidate = next(row for row in rb_candidates if row["gsis_id"] == "r2")
            self.assertEqual(active["current_active"], "true")
            self.assertEqual(reserve_candidate["current_active"], "false")

    def test_writes_manifest_with_zero_reconciliation_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self.make_inputs(root)
            result = build_player_roles(
                *inputs[:3], observed_styles=inputs[3], ffc_adp=inputs[4]
            )
            path = write_player_role_snapshot(result, root / "derived")
            manifest = json.loads((path / "manifest.json").read_text())
            self.assertEqual(manifest["quality"]["maximum_reconciliation_error"], 0)
            self.assertEqual(manifest["quality"]["resource_count"], 6)
            self.assertGreater(manifest["quality"]["role_candidate_rows"], len(result.roles))
            self.assertEqual(
                manifest["parameters"]["conversion_factors"],
                {
                    "qb_dropbacks_per_pass_play": 1.0,
                    "rb_carries_per_non_qb_rush_play": 1.0,
                    "target_per_pass_play": 0.95,
                },
            )


if __name__ == "__main__":
    unittest.main()
