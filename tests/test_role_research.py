import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from fantasy_draft.high_value_volumes import PLAYER_FIELDS, REVIEW_FIELDS
from fantasy_draft.role_research import (
    RoleResearchDataError,
    build_role_research_audit,
    write_role_research_snapshot,
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


class RoleResearchTests(unittest.TestCase):
    def make_inputs(self, root: Path):
        volume = root / "volume"
        players = []
        for player_id, name, expected, flagged in (
            ("p1", "First Back", "8.000000", True),
            ("p2", "Second Back", "3.000000", True),
            ("p3", "Third Back", "1.000000", False),
        ):
            row = {field: "" for field in PLAYER_FIELDS}
            row.update({
                "season": 2026,
                "team": "AAA",
                "position": "RB",
                "metric": "RB_INSIDE_5_CARRIES",
                "base_resource": "RB_CARRIES",
                "gsis_id": player_id,
                "player_name": name,
                "current_status": "ACT",
                "availability_adjusted_season_expected_events": expected,
                "season_marginal_scenario_envelope_low": "1.000000",
                "season_marginal_scenario_envelope_high": "10.000000",
                "metric_history_support": "limited_below_primary_prior",
                "historical_metric_base_opportunities": "10.000000",
                "requires_current_role_review": str(flagged).lower(),
                "current_role_review_issues": (
                    "material_role_with_limited_player_metric_history" if flagged else ""
                ),
            })
            players.append(row)
        player_raw = write_csv(
            volume / "player_high_value_opportunities.csv", PLAYER_FIELDS, players
        )
        team_review = {field: "" for field in REVIEW_FIELDS}
        team_review.update({
            "season": 2026,
            "team": "AAA",
            "position": "RB",
            "metric": "RB_INSIDE_5_CARRIES",
            "issue": "raw_team_history_outside_rate_calibration_radius",
            "training_team_base_opportunities": "500.000000",
            "primary_rate": "0.050000000",
            "diagnostic_raw_rate": "0.010000000",
            "conformal_rate_radius": "0.020000000",
            "details": "test team-rate exception",
        })
        review_raw = write_csv(
            volume / "source_review.csv", REVIEW_FIELDS, [team_review]
        )
        (volume / "manifest.json").write_text(json.dumps({
            "model_version": "high-value-event-pool-v0.3.0",
            "season": 2026,
            "supported_metrics": ["RB_INSIDE_5_CARRIES"],
            "artifacts": {
                "player_high_value_opportunities.csv": {
                    "sha256": hashlib.sha256(player_raw).hexdigest()
                },
                "source_review.csv": {
                    "sha256": hashlib.sha256(review_raw).hexdigest()
                },
            },
        }))

        evidence = root / "evidence.json"
        evidence.write_text(json.dumps({
            "schema_version": "1.0.0",
            "season": 2026,
            "as_of": "2026-09-03",
            "numeric_override_policy": "forbidden_until_time_correct_validation",
            "sources": [{
                "id": "official_a",
                "title": "Official role note",
                "publisher": "AAA Club",
                "source_type": "official_team",
                "url": "https://example.com/role",
                "published_at": "2026-09-01",
                "accessed_at": "2026-09-03",
            }],
            "player_records": [{
                "id": "p1_review",
                "team": "AAA",
                "position": "RB",
                "gsis_id": "p1",
                "player_name": "First Back",
                "metrics": ["RB_INSIDE_5_CARRIES"],
                "review_status": "reviewed_role_conflict_model_retained",
                "evidence_strength": "direct_current_role",
                "claim": "The official role note creates doubt.",
                "model_implication": "Retain the estimate but show the conflict.",
                "remaining_uncertainty": "Regular-season usage is unknown.",
                "source_ids": ["official_a"],
                "numeric_override_applied": False,
            }],
            "team_records": [{
                "id": "aaa_rate_review",
                "team": "AAA",
                "metric": "RB_INSIDE_5_CARRIES",
                "issue": "raw_team_history_outside_rate_calibration_radius",
                "review_status": "reviewed_model_retained",
                "evidence_strength": "direct_current_role",
                "claim": "The current caller is confirmed.",
                "model_implication": "Retain the gated pooled rate.",
                "remaining_uncertainty": "Current regular-season rate is unknown.",
                "source_ids": ["official_a"],
                "numeric_override_applied": False,
            }],
        }))
        return volume, evidence

    def test_joins_reviewed_evidence_and_preserves_unreviewed_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            result = build_role_research_audit(*self.make_inputs(Path(directory)))
            self.assertEqual(len(result.player_review_rows), 2)
            self.assertEqual(result.player_review_rows[0]["gsis_id"], "p1")
            self.assertEqual(
                result.player_review_rows[0]["review_status"],
                "reviewed_role_conflict_model_retained",
            )
            self.assertEqual(result.player_review_rows[1]["review_status"], "unreviewed")
            self.assertEqual(len(result.team_review_rows), 1)
            self.assertTrue(all(
                row["numeric_override_applied"] == "false"
                for row in (*result.player_review_rows, *result.team_review_rows)
            ))
            overall = next(
                row for row in result.coverage_rows
                if row["scope"] == "player" and row["metric"] == "ALL"
            )
            self.assertEqual(overall["evidence_reviewed_rows"], 1)
            self.assertEqual(overall["unreviewed_rows"], 1)

    def test_rejects_unvalidated_numeric_override(self):
        with tempfile.TemporaryDirectory() as directory:
            volume, evidence = self.make_inputs(Path(directory))
            payload = json.loads(evidence.read_text())
            payload["player_records"][0]["numeric_override_applied"] = True
            evidence.write_text(json.dumps(payload))
            with self.assertRaisesRegex(RoleResearchDataError, "numeric override"):
                build_role_research_audit(volume, evidence)

    def test_rejects_evidence_for_unflagged_target(self):
        with tempfile.TemporaryDirectory() as directory:
            volume, evidence = self.make_inputs(Path(directory))
            payload = json.loads(evidence.read_text())
            payload["player_records"][0].update({
                "gsis_id": "p3",
                "player_name": "Third Back",
            })
            evidence.write_text(json.dumps(payload))
            with self.assertRaisesRegex(RoleResearchDataError, "does not match a flagged"):
                build_role_research_audit(volume, evidence)

    def test_writes_hash_verified_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = build_role_research_audit(*self.make_inputs(root))
            path = write_role_research_snapshot(result, root / "output")
            manifest = json.loads((path / "manifest.json").read_text())
            raw = (path / "player_review_queue.csv").read_bytes()
            self.assertEqual(
                manifest["artifacts"]["player_review_queue.csv"]["sha256"],
                hashlib.sha256(raw).hexdigest(),
            )
            self.assertEqual(manifest["quality"]["numeric_overrides_applied"], 0)


if __name__ == "__main__":
    unittest.main()
