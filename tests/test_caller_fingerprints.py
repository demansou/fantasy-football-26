import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fantasy_draft.caller_fingerprints import (
    METRIC_FIELDS,
    STYLE_METRICS,
    CallerFingerprintDataError,
    build_caller_fingerprints,
    write_caller_fingerprint_snapshot,
)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


class CallerFingerprintTests(unittest.TestCase):
    def make_inputs(self, root: Path) -> dict[str, Path]:
        current = root / "current" / "teams.csv"
        write_csv(
            current,
            ["season", "team", "head_coach", "play_caller", "evidence_strength"],
            [
                {"season": 2026, "team": "KC", "head_coach": "Andy Reid", "play_caller": "Andy Reid", "evidence_strength": 1.0},
                {"season": 2026, "team": "SEA", "head_coach": "Head Coach", "play_caller": "New Caller", "evidence_strength": 1.0},
            ],
        )
        continuity = root / "continuity" / "teams.csv"
        write_csv(
            continuity,
            [
                "team",
                "current_caller_2025_status",
                "same_play_caller",
                "play_caller_on_prior_staff",
                "head_coach_status",
                "staff_continuity_index_v0",
            ],
            [
                {"team": "KC", "current_caller_2025_status": "same_team_returning_caller", "same_play_caller": "true", "play_caller_on_prior_staff": "true", "head_coach_status": "retained_holder", "staff_continuity_index_v0": 80},
                {"team": "SEA", "current_caller_2025_status": "not_a_2025_primary_caller", "same_play_caller": "false", "play_caller_on_prior_staff": "true", "head_coach_status": "retained_holder", "staff_continuity_index_v0": 60},
            ],
        )
        historical = root / "historical" / "callers.csv"
        write_csv(
            historical,
            ["season", "team", "play_caller", "source_url", "temporal_use", "experience_text"],
            [
                {"season": 2025, "team": "KC", "play_caller": "Andy Reid", "source_url": "https://example.com/2025", "temporal_use": "historical_identity_evidence", "experience_text": "Returning caller."},
                {"season": 2025, "team": "SEA", "play_caller": "Old Caller", "source_url": "https://example.com/2025", "temporal_use": "historical_identity_evidence", "experience_text": "Prior caller."},
            ],
        )
        style = root / "styles" / "team_style.csv"
        style_fields = ["season", "team", *STYLE_METRICS]
        style_rows = []
        for season, team, offset in (
            (2024, "KC", 0.01),
            (2024, "SEA", 0.02),
            (2025, "KC", 0.03),
            (2025, "SEA", 0.04),
        ):
            row: dict[str, object] = {"season": season, "team": team}
            for metric in STYLE_METRICS:
                row[metric] = 60 + offset if metric == "plays_per_game" else 0.5 + offset
            style_rows.append(row)
        write_csv(style, style_fields, style_rows)
        overrides = root / "overrides.json"
        overrides.write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "as_of": "2026-09-02",
                    "exclusions": [],
                    "additions": [
                        {
                            "season": 2024,
                            "team": "KC",
                            "caller": "Andy Reid",
                            "coverage": "full_regular_season_primary_caller",
                            "full_team_season_anchor": True,
                            "style_weight": 1.0,
                            "source_url": "https://example.com/2024",
                            "evidence_summary": "Audited earlier season.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        system = root / "system.json"
        system.write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "as_of": "2026-09-02",
                    "teams": [
                        {
                            "team": "SEA",
                            "play_caller": "New Caller",
                            "scheme_family": "retained system",
                            "scheme_identity_score": 0.9,
                            "destination_scheme_continuity": 0.9,
                            "rationale": "The team explicitly plans to preserve the prior system.",
                            "source_urls": ["https://example.com/system"],
                            "metric_signals": {"motion_rate": 0.5},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return {
            "current": current.parent,
            "continuity": continuity.parent,
            "historical": historical.parent,
            "style": style.parent,
            "overrides": overrides,
            "system": system,
        }

    def test_builds_returning_and_first_time_caller_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            inputs = self.make_inputs(Path(directory))
            result = build_caller_fingerprints(
                inputs["current"],
                inputs["continuity"],
                [inputs["historical"]],
                inputs["style"],
                inputs["overrides"],
                inputs["system"],
            )
            by_team = {row["team"]: row for row in result.team_rows}
            self.assertEqual(len(result.team_rows), 2)
            self.assertEqual(by_team["KC"]["recent_full_season_anchor_count"], 2)
            self.assertEqual(by_team["SEA"]["recent_full_season_anchor_count"], 0)
            self.assertGreater(
                by_team["KC"]["exact_style_certainty_v0"],
                by_team["SEA"]["exact_style_certainty_v0"],
            )
            self.assertEqual(len(result.metric_rows), 2 * len(STYLE_METRICS))
            sea_pass = next(
                row
                for row in result.metric_rows
                if row["team"] == "SEA" and row["metric"] == "pass_rate"
            )
            self.assertEqual(sea_pass["caller_weight"], 0.0)
            self.assertEqual(sea_pass["destination_weight"], 0.8)

    def test_rejects_an_exclusion_that_does_not_match_a_census_episode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            inputs = self.make_inputs(Path(directory))
            overrides = json.loads(inputs["overrides"].read_text())
            overrides["exclusions"] = [
                {
                    "season": 2025,
                    "team": "SEA",
                    "caller": "New Caller",
                    "reason": "Not actually present.",
                    "source_url": "https://example.com/exclusion",
                }
            ]
            inputs["overrides"].write_text(json.dumps(overrides), encoding="utf-8")
            with self.assertRaisesRegex(CallerFingerprintDataError, "does not match"):
                build_caller_fingerprints(
                    inputs["current"],
                    inputs["continuity"],
                    [inputs["historical"]],
                    inputs["style"],
                    inputs["overrides"],
                    inputs["system"],
                )

    def test_writes_hashed_atomic_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = self.make_inputs(root)
            result = build_caller_fingerprints(
                inputs["current"],
                inputs["continuity"],
                [inputs["historical"]],
                inputs["style"],
                inputs["overrides"],
                inputs["system"],
            )
            snapshot = write_caller_fingerprint_snapshot(result, root / "derived")
            manifest = json.loads((snapshot / "manifest.json").read_text())
            metric_bytes = (snapshot / "metric_forecasts.csv").read_bytes()
            with (snapshot / "metric_forecasts.csv").open() as handle:
                metric_rows = list(csv.DictReader(handle))
            self.assertEqual(manifest["quality"]["team_count"], 2)
            self.assertEqual(manifest["artifacts"]["metric_forecasts.csv"]["sha256"], hashlib.sha256(metric_bytes).hexdigest())
            self.assertEqual(tuple(metric_rows[0]), METRIC_FIELDS)


if __name__ == "__main__":
    unittest.main()
