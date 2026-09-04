import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fantasy_draft.availability import (
    AvailabilityDataError,
    _build_history,
    build_weekly_availability,
    write_availability_snapshot,
)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


class AvailabilityTests(unittest.TestCase):
    def test_historical_bye_is_not_counted_as_inactive(self) -> None:
        roster = [{
            "season": "2023", "week": "1", "team": "AAA", "position": "RB",
            "gsis_id": "r1", "player_name": "Active Back", "status": "ACT",
            "status_description": "A01",
        }]
        schedule = [{"season": "2023", "week": "1", "team": "AAA"}]
        _, outcomes, totals, _ = _build_history(roster, schedule)
        self.assertTrue(outcomes[(2023, "r1", 1)])
        self.assertNotIn((2023, "r1", 2), outcomes)
        self.assertNotIn(("active_53", "RB", 2), totals)

    def make_inputs(
        self,
        root: Path,
        *,
        include_evidence: bool = True,
        minimum_games_missed: int = 4,
    ):
        history = root / "history"
        history_fields = [
            "season", "week", "team", "position", "gsis_id", "player_name",
            "status", "status_description",
        ]
        history_rows: list[dict[str, object]] = []
        for season in (2023, 2024):
            for week in range(1, 19):
                history_rows.append({
                    "season": season,
                    "week": week,
                    "team": "AAA",
                    "position": "RB",
                    "gsis_id": f"active-{season}",
                    "player_name": "Historical Active",
                    "status": "ACT",
                    "status_description": "A01",
                })
                history_rows.append({
                    "season": season,
                    "week": week,
                    "team": "AAA",
                    "position": "RB",
                    "gsis_id": f"reserve-{season}",
                    "player_name": "Historical Reserve",
                    "status": "RES" if week <= 4 else "ACT",
                    "status_description": "R04" if week <= 4 else "A01",
                })
        write_csv(history / "weekly_rosters.csv", history_fields, history_rows)
        schedule_fields = [
            "season", "week", "gameday", "game_id", "team", "opponent",
            "home_away",
        ]
        schedule_rows = [
            {
                "season": season, "week": week,
                "gameday": f"{season}-09-{min(week, 28):02d}",
                "game_id": f"{season}_{week:02d}_AAA_BBB", "team": "AAA",
                "opponent": "BBB", "home_away": "home",
            }
            for season in (2023, 2024) for week in range(1, 19)
        ]
        schedule_rows.extend(
            {
                "season": 2026, "week": week,
                "gameday": f"2026-10-{min(week, 28):02d}",
                "game_id": f"2026_{week:02d}_AAA_BBB", "team": "AAA",
                "opponent": "BBB", "home_away": "away",
            }
            for week in range(1, 19) if week != 10
        )
        write_csv(history / "team_schedule.csv", schedule_fields, schedule_rows)

        players = root / "players"
        roster_fields = [
            "season", "team", "fantasy_position", "gsis_id", "full_name",
            "current_status", "roster_status", "status_description",
        ]
        write_csv(players / "current_roster.csv", roster_fields, [
            {
                "season": 2026, "team": "AAA", "fantasy_position": "RB",
                "gsis_id": "r1", "full_name": "Current Active",
                "current_status": "ACT", "roster_status": "ACT",
                "status_description": "A01",
            },
            {
                "season": 2026, "team": "AAA", "fantasy_position": "RB",
                "gsis_id": "r2", "full_name": "Current Reserve",
                "current_status": "PUP", "roster_status": "RES",
                "status_description": "R04",
            },
        ])

        roles = root / "roles"
        candidate_fields = [
            "season", "team", "position", "resource", "gsis_id", "player_name",
            "current_status", "latent_role_weight", "ffc_source_player_id", "ffc_adp",
        ]
        write_csv(roles / "player_role_candidates.csv", candidate_fields, [
            {
                "season": 2026, "team": "AAA", "position": "RB",
                "resource": "RB_CARRIES", "gsis_id": "r1",
                "player_name": "Current Active", "current_status": "ACT",
                "latent_role_weight": 0.7, "ffc_source_player_id": "101",
                "ffc_adp": 30,
            },
            {
                "season": 2026, "team": "AAA", "position": "RB",
                "resource": "RB_CARRIES", "gsis_id": "r2",
                "player_name": "Current Reserve", "current_status": "PUP",
                "latent_role_weight": 0.3, "ffc_source_player_id": "102",
                "ffc_adp": 80,
            },
        ])
        write_csv(
            roles / "team_reconciliation.csv",
            ["season", "team", "position", "resource", "team_pool_per_game"],
            [{
                "season": 2026, "team": "AAA", "position": "RB",
                "resource": "RB_CARRIES", "team_pool_per_game": 25,
            }],
        )

        evidence = root / "evidence.json"
        records = []
        if include_evidence:
            records.append({
                "gsis_id": "r2", "player": "Current Reserve", "team": "AAA",
                "position": "RB", "current_status": "reserve_pup",
                "current_active": False,
                "minimum_games_missed": minimum_games_missed,
                "constraint_rule_id": "four_game_rule",
                "sources": [{"url": "https://example.com/player"}],
            })
        evidence.write_text(json.dumps({
            "schema_version": "1.0.1",
            "rule_sources": [{
                "rule_id": "four_game_rule",
                "urls": ["https://example.com/rule"],
            }],
            "records": records,
        }), encoding="utf-8")
        return history, players, roles, evidence

    def test_hard_return_constraint_and_role_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            inputs = self.make_inputs(Path(directory))
            result = build_weekly_availability(
                *inputs, simulation_draws=500, random_seed=7
            )
            reserve = [
                row for row in result.weekly_availability if row["gsis_id"] == "r2"
            ]
            self.assertTrue(all(
                float(row["active_probability_median"]) == 0
                for row in reserve if int(row["week"]) <= 4
            ))
            self.assertGreater(
                float(next(row for row in reserve if int(row["week"]) == 5)["active_probability_median"]),
                0,
            )
            reserve_roles = [
                row for row in result.weekly_expected_roles if row["gsis_id"] == "r2"
            ]
            self.assertTrue(all(
                float(row["expected_share_mean"]) == 0
                for row in reserve_roles if int(row["week"]) <= 4
            ))
            self.assertGreater(
                float(next(row for row in reserve_roles if int(row["week"]) == 5)["expected_share_mean"]),
                0,
            )
            self.assertTrue(all(
                abs(float(row["reconciled_share_sum"]) - 1) < 1e-9
                for row in result.reconciliation if row["scheduled_game"] == "true"
            ))
            bye = next(row for row in result.reconciliation if int(row["week"]) == 10)
            self.assertEqual(bye["scheduled_game"], "false")
            self.assertEqual(float(bye["reconciliation_target"]), 0)
            self.assertEqual(float(bye["reconciled_share_sum"]), 0)
            self.assertEqual(result.evidence_review, ())

    def test_full_season_rule_constraint_zeros_every_week(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            inputs = self.make_inputs(
                Path(directory), minimum_games_missed=18
            )
            result = build_weekly_availability(
                *inputs, simulation_draws=100, random_seed=11
            )
            reserve = [
                row for row in result.weekly_availability if row["gsis_id"] == "r2"
            ]
            self.assertEqual(len(reserve), 18)
            self.assertTrue(all(
                float(row["active_probability_median"]) == 0
                and row["hard_constraint_applied"] == "true"
                for row in reserve
            ))
            reserve_roles = [
                row for row in result.weekly_expected_roles if row["gsis_id"] == "r2"
            ]
            self.assertTrue(all(
                float(row["expected_share_mean"]) == 0
                and float(row["expected_opportunities_this_week"]) == 0
                for row in reserve_roles
            ))

    def test_market_nonactive_player_requires_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            inputs = self.make_inputs(Path(directory), include_evidence=False)
            with self.assertRaisesRegex(AvailabilityDataError, "blocking"):
                build_weekly_availability(*inputs, simulation_draws=100)

    def test_writes_hash_verified_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = build_weekly_availability(
                *self.make_inputs(root), simulation_draws=100, random_seed=3
            )
            path = write_availability_snapshot(result, root / "derived")
            manifest = json.loads((path / "manifest.json").read_text())
            raw = (path / "weekly_availability.csv").read_bytes()
            self.assertEqual(
                manifest["artifacts"]["weekly_availability.csv"]["sha256"],
                hashlib.sha256(raw).hexdigest(),
            )
            self.assertEqual(manifest["quality"]["maximum_reconciliation_error"], 0)


if __name__ == "__main__":
    unittest.main()
