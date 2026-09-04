import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from fantasy_draft.continuity import (
    ContinuityDataError,
    build_staff_continuity,
    write_staff_continuity_snapshot,
)


FIELDS = (
    "season",
    "team",
    "name",
    "role",
    "side",
    "responsibility_categories",
)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(stream.getvalue(), encoding="utf-8")


def row(season, name, role, side, categories, team="KC"):
    return {
        "season": str(season),
        "team": team,
        "name": name,
        "role": role,
        "side": side,
        "responsibility_categories": categories,
    }


class StaffContinuityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prior = [
            row(2025, "Alex Head", "Head Coach", "head_coach", "head_coach"),
            row(2025, "Olivia Caller", "offensive coordinator", "offense", "offensive_coordinator"),
            row(2025, "Quinn Back", "quarterbacks", "offense", "quarterbacks"),
            row(2025, "Nicholas Runner-Luke", "running backs", "offense", "running_backs"),
            row(2025, "Old Wide", "wide receivers", "offense", "wide_receivers"),
            row(2025, "Terry End", "tight ends", "offense", "tight_ends"),
            row(2025, "Ollie Line", "offensive line", "offense", "offensive_line"),
        ]
        self.current = [
            row(2026, "Alex Head", "Head Coach", "head_coach", "head_coach"),
            row(2026, "Olivia Caller", "Offensive Coordinator", "offense", "offensive_coordinator"),
            row(2026, "Quinn Back", "Quarterbacks Coach", "offense", "quarterbacks"),
            row(2026, "Nicholas Runner", "Running Backs", "offense", "running_backs"),
            row(2026, "New Wide", "Wide Receivers", "offense", "wide_receivers"),
            row(2026, "Ollie Line", "Offensive Line Coach", "offense", "offensive_line"),
        ]

    def _inputs(self, directory: str):
        root = Path(directory)
        prior = root / "prior.csv"
        current = root / "current.csv"
        callers = root / "teams.csv"
        prior_callers = root / "callers.csv"
        aliases = root / "aliases.json"
        write_csv(prior, self.prior)
        write_csv(current, self.current)
        callers.write_text(
            "season,team,play_caller\n2026,KC,Olivia Caller\n", encoding="utf-8"
        )
        prior_callers.write_text(
            "season,team,play_caller\n2025,KC,Olivia Caller\n", encoding="utf-8"
        )
        aliases.write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "as_of": "2026-09-02",
                    "aliases": [
                        {
                            "season": 2025,
                            "team": "KC",
                            "observed_name": "Nicholas Runner-Luke",
                            "canonical_name": "Nicholas Runner",
                            "reason": "Official current source shortens the surname.",
                            "source_urls": ["https://example.com/official"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return prior, current, callers, prior_callers, aliases

    def test_measures_identity_and_responsibility_continuity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prior, current, callers, prior_callers, aliases = self._inputs(directory)
            result = build_staff_continuity(
                prior, current, callers, prior_callers, aliases=aliases
            )

            team = result.team_rows[0]
            self.assertEqual(team["returning_staff_count"], 5)
            self.assertEqual(team["same_responsibility_count"], 5)
            self.assertEqual(team["retained_core_responsibility_count"], 5)
            self.assertEqual(team["changed_core_responsibility_count"], 1)
            self.assertEqual(team["unavailable_core_responsibility_count"], 1)
            self.assertEqual(team["play_caller_on_prior_staff"], "true")
            self.assertEqual(team["same_play_caller"], "true")
            self.assertEqual(
                team["current_caller_2025_status"], "same_team_returning_caller"
            )
            self.assertEqual(team["staff_continuity_index_v0"], 83.3)

            by_name = {item["name"]: item for item in result.current_staff_rows}
            self.assertEqual(
                by_name["Quinn Back"]["continuity_status"],
                "returning_same_responsibility",
            )
            self.assertEqual(by_name["Nicholas Runner"]["matched_via_alias"], "true")
            self.assertEqual(by_name["New Wide"]["continuity_status"], "new_to_team")

            responsibility = {
                item["responsibility"]: item for item in result.responsibility_rows
            }
            self.assertEqual(responsibility["running_backs"]["status"], "retained_holder")
            self.assertEqual(responsibility["wide_receivers"]["status"], "changed_holder")
            self.assertEqual(responsibility["tight_ends"]["status"], "not_comparable")

    def test_rejects_misaligned_team_sets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prior, current, callers, prior_callers, aliases = self._inputs(directory)
            callers.write_text(
                "season,team,play_caller\n2026,SEA,Someone Else\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ContinuityDataError, "team sets differ"):
                build_staff_continuity(
                    prior, current, callers, prior_callers, aliases=aliases
                )

    def test_preserves_ambiguous_current_caller_without_hindsight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prior, current, callers, prior_callers, aliases = self._inputs(directory)
            callers.write_text(
                "season,team,play_caller,identity_status,candidate_callers\n"
                "2026,KC,,ambiguous,Olivia Caller|Alex Head\n",
                encoding="utf-8",
            )
            result = build_staff_continuity(
                prior, current, callers, prior_callers, aliases=aliases
            )

            team = result.team_rows[0]
            self.assertEqual(team["current_play_caller"], "")
            self.assertEqual(team["same_play_caller"], "")
            self.assertEqual(team["play_caller_on_prior_staff"], "")
            self.assertEqual(
                team["current_caller_2025_status"], "ambiguous_current_identity"
            )
            self.assertEqual(team["staff_continuity_index_v0"], 83.3)

    def test_normalizes_caller_generation_suffixes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prior, current, callers, prior_callers, aliases = self._inputs(directory)
            prior_callers.write_text(
                "season,team,play_caller\n2025,KC,Olivia Caller Jr.\n",
                encoding="utf-8",
            )
            result = build_staff_continuity(
                prior, current, callers, prior_callers, aliases=aliases
            )

            self.assertEqual(result.team_rows[0]["same_play_caller"], "true")

    def test_writes_snapshot_with_method_warning_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prior, current, callers, prior_callers, aliases = self._inputs(directory)
            result = build_staff_continuity(
                prior, current, callers, prior_callers, aliases=aliases
            )
            output = Path(directory) / "derived"
            path = write_staff_continuity_snapshot(result, output)
            manifest = json.loads((path / "manifest.json").read_text())
            teams = list(
                csv.DictReader(io.StringIO((path / "teams.csv").read_text()))
            )

            self.assertEqual(manifest["model_status"], "descriptive_not_style_certainty")
            self.assertIn("not calibrated style certainty", manifest["methodology"]["warning"])
            self.assertEqual(manifest["quality"]["team_count"], 1)
            self.assertEqual(len(teams), 1)
            self.assertTrue((path / "current_staff.csv").is_file())
            self.assertTrue((path / "responsibilities.csv").is_file())


if __name__ == "__main__":
    unittest.main()
