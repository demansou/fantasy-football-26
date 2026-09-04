import csv
import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fantasy_draft.historical_certainty import (
    CALIBRATION_FIELDS,
    COVERAGE_PREDICTION_FIELDS,
    COVERAGE_SUMMARY_FIELDS,
    RANK_FIELDS,
    TEAM_ERROR_FIELDS,
    TEAM_SCORE_FIELDS,
    TIER_FIELDS,
    HistoricalCertaintyResult,
    _conformal,
    _score_row,
    _spearman,
    write_historical_certainty_snapshot,
)


class HistoricalCertaintyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.returning_team = {
            "team": "KC",
            "opening_caller": "Andy Reid",
            "prior_caller": "Andy Reid",
            "caller_cohort": "returning_caller",
        }
        self.returning_continuity = {
            "same_play_caller": "true",
            "play_caller_on_prior_staff": "true",
            "head_coach_status": "retained_holder",
            "staff_continuity_index_v0": "100",
            "unavailable_core_responsibility_count": "0",
        }

    def test_reconstructs_returning_score_and_changed_caller_bounds(self) -> None:
        returning = _score_row(
            season=2025,
            team_row=self.returning_team,
            continuity=self.returning_continuity,
        )
        self.assertAlmostEqual(
            returning["broad_system_certainty_lower_bound"], 91.818182
        )
        self.assertEqual(
            returning["broad_system_certainty_lower_bound"],
            returning["broad_system_certainty_upper_bound"],
        )
        self.assertAlmostEqual(
            returning["exact_style_certainty_lower_bound"], 83.581818
        )

        changed = _score_row(
            season=2025,
            team_row={
                "team": "AAA",
                "opening_caller": "New Caller",
                "prior_caller": "Old Caller",
                "caller_cohort": "changed_without_prior_year_anchor",
            },
            continuity={
                "same_play_caller": "false",
                "play_caller_on_prior_staff": "false",
                "head_coach_status": "changed_holder",
                "staff_continuity_index_v0": "0",
                "unavailable_core_responsibility_count": "0",
            },
        )
        self.assertEqual(changed["broad_known_weight"], 0.45)
        self.assertEqual(changed["exact_known_weight"], 0.75)
        self.assertEqual(changed["broad_system_certainty_lower_bound"], 20.0)
        self.assertEqual(changed["broad_system_certainty_upper_bound"], 75.0)
        self.assertEqual(changed["exact_style_certainty_lower_bound"], 14.65)
        self.assertEqual(changed["exact_style_certainty_upper_bound"], 39.65)

    def test_preserves_ambiguous_identity_as_unscored(self) -> None:
        row = _score_row(
            season=2025,
            team_row={
                "team": "NYG",
                "opening_caller": "Brian Daboll / Mike Kafka",
                "prior_caller": "Brian Daboll",
                "caller_cohort": "ambiguous_opening_caller",
            },
            continuity={
                "same_play_caller": "",
                "play_caller_on_prior_staff": "",
                "head_coach_status": "retained_holder",
                "staff_continuity_index_v0": "80",
                "unavailable_core_responsibility_count": "0",
            },
        )
        self.assertEqual(row["score_status"], "excluded_ambiguous_preseason_caller")
        self.assertEqual(row["exact_style_certainty_lower_bound"], "")

    def test_rank_and_finite_sample_helpers(self) -> None:
        self.assertAlmostEqual(_spearman([1, 2, 3], [3, 2, 1]), -1.0)
        rank, radius = _conformal([float(value) for value in range(10)])
        self.assertEqual(rank, 10)
        self.assertEqual(radius, 9.0)

    def test_writes_immutable_snapshot_with_artifact_hashes(self) -> None:
        def blank(fields):
            return {field: "" for field in fields}

        team_score = blank(TEAM_SCORE_FIELDS)
        team_score.update(
            {
                "target_season": 2025,
                "team": "KC",
                "score_status": "eligible_one_year_lower_bound_diagnostic",
            }
        )
        result = HistoricalCertaintyResult(
            target_seasons=(2023, 2024, 2025),
            development_seasons=(2023, 2024),
            holdout_season=2025,
            windows=(6,),
            bootstrap_samples=100,
            random_seed=7,
            input_paths=(),
            input_hashes={},
            team_score_rows=(team_score,),
            team_error_rows=(blank(TEAM_ERROR_FIELDS),),
            rank_rows=(blank(RANK_FIELDS),),
            tier_rows=(blank(TIER_FIELDS),),
            calibration_rows=(blank(CALIBRATION_FIELDS),),
            coverage_prediction_rows=(blank(COVERAGE_PREDICTION_FIELDS),),
            coverage_summary_rows=(blank(COVERAGE_SUMMARY_FIELDS),),
            evaluation={
                "promotion_gate": {"decision": "do_not_condition"},
            },
        )
        created = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            path = write_historical_certainty_snapshot(
                result, directory, created_at=created
            )
            manifest = json.loads((path / "manifest.json").read_text())
            raw = (path / "team_scores.csv").read_bytes()
            rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))

            self.assertEqual(path.name, "20260903T120000.000000Z")
            self.assertEqual(rows[0]["team"], "KC")
            self.assertEqual(
                manifest["artifacts"]["team_scores.csv"]["sha256"],
                hashlib.sha256(raw).hexdigest(),
            )
            with self.assertRaises(FileExistsError):
                write_historical_certainty_snapshot(
                    result, directory, created_at=created
                )


if __name__ == "__main__":
    unittest.main()
