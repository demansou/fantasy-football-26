import csv
import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fantasy_draft.environment import (
    METRICS,
    EnvironmentDataError,
    build_team_environment_forecast,
    load_observed_styles,
    load_research_dataset,
    write_environment_snapshot,
)


def research_payload() -> dict[str, object]:
    source = {
        "id": "official_staff",
        "title": "Official staff and scheme notes",
        "publisher": "Example Team",
        "source_type": "official_team",
        "url": "https://example.com/staff",
        "published_at": "2026-08-01",
        "accessed_at": "2026-09-02",
    }
    returning_team = {
        "team": "AAA",
        "scheme_family": "Established system",
        "scheme_continuity": 1.0,
        "scheme_rationale": "The head coach and caller return.",
        "scheme_source_ids": ["official_staff"],
        "returning_starters_fraction": 0.9,
        "personnel_source_ids": ["official_staff"],
        "staff": [
            {
                "name": "Returning Head Coach",
                "roles": ["Head Coach"],
                "continuity": "returning_same_role",
                "influence_dimensions": ["pass_run_tendency"],
                "influence_weight": 2.0,
                "source_ids": ["official_staff"],
                "is_head_coach": True,
            },
            {
                "name": "Returning Caller",
                "roles": ["Offensive Coordinator", "Play Caller"],
                "continuity": "returning_same_role",
                "influence_dimensions": ["pass_run_tendency", "pace"],
                "influence_weight": 2.0,
                "source_ids": ["official_staff"],
                "is_play_caller": True,
                "playcaller_confirmation": "official",
                "completed_nfl_playcalling_seasons": 8,
            },
            {
                "name": "Returning Line Coach",
                "roles": ["Offensive Line"],
                "continuity": "returning_same_role",
                "influence_dimensions": ["run_concepts"],
                "influence_weight": 1.0,
                "source_ids": ["official_staff"],
            },
        ],
        "historical_anchors": [
            {"team": "AAA", "season": 2024, "weight": 0.8, "reason": "Same caller"},
            {"team": "AAA", "season": 2025, "weight": 1.0, "reason": "Same caller"},
        ],
        "claims": [
            {
                "id": "aaa_continuity",
                "source_id": "official_staff",
                "summary": "The offense will retain its core system.",
                "evidence_type": "direct_quote",
                "dimensions": ["pass_run_tendency"],
                "reliability": 0.9,
                "strength": 0.8,
                "certainty_effect": 1.0,
                "metric_signals": {},
            }
        ],
    }
    new_team = {
        "team": "BBB",
        "scheme_family": "Related but new system",
        "scheme_continuity": 0.6,
        "scheme_rationale": "A first-time caller comes from a related tree.",
        "scheme_source_ids": ["official_staff"],
        "returning_starters_fraction": None,
        "personnel_source_ids": [],
        "staff": [
            {
                "name": "Returning Defensive Head Coach",
                "roles": ["Head Coach"],
                "continuity": "returning_same_role",
                "influence_dimensions": [],
                "influence_weight": 1.0,
                "source_ids": ["official_staff"],
                "is_head_coach": True,
            },
            {
                "name": "First-Time Caller",
                "roles": ["Offensive Coordinator", "Play Caller"],
                "continuity": "new_to_team",
                "influence_dimensions": ["pass_run_tendency"],
                "influence_weight": 2.0,
                "source_ids": ["official_staff"],
                "is_play_caller": True,
                "playcaller_confirmation": "official",
                "completed_nfl_playcalling_seasons": 0,
            },
            {
                "name": "New Line Coach",
                "roles": ["Offensive Line"],
                "continuity": "new_to_team",
                "influence_dimensions": ["run_concepts"],
                "influence_weight": 1.0,
                "source_ids": ["official_staff"],
            },
        ],
        "historical_anchors": [
            {"team": "BBB", "season": 2025, "weight": 1.0, "reason": "Retained roster"}
        ],
        "claims": [
            {
                "id": "bbb_more_run",
                "source_id": "official_staff",
                "summary": "The new offense intends to emphasize the run.",
                "evidence_type": "direct_quote",
                "dimensions": ["pass_run_tendency"],
                "reliability": 0.8,
                "strength": 0.7,
                "certainty_effect": -0.5,
                "metric_signals": {"pass_rate": -1.0},
            }
        ],
    }
    return {
        "schema_version": "1.0.0",
        "season": 2026,
        "as_of": "2026-09-02",
        "sources": [source],
        "teams": [returning_team, new_team],
    }


def observed_csv() -> bytes:
    stream = io.StringIO(newline="")
    fields = ["team", "season", *METRICS]
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    defaults = {
        "plays_per_game": 64,
        "pass_rate": 0.58,
        "neutral_early_down_pass_rate": 0.55,
        "neutral_pass_oe": 0.01,
        "shotgun_rate": 0.70,
        "no_huddle_rate": 0.10,
        "red_zone_pass_rate": 0.50,
        "deep_attempt_rate": 0.18,
        "mean_air_yards": 8.0,
        "qb_scramble_rate": 0.06,
        "designed_qb_run_share": 0.04,
        "rb_target_share": 0.20,
        "wr_target_share": 0.58,
        "te_target_share": 0.20,
        "explosive_play_rate": 0.11,
        "success_rate": 0.45,
        "epa_per_play": 0.02,
    }
    writer.writerow({"team": "AAA", "season": 2024, **defaults})
    writer.writerow(
        {
            "team": "AAA",
            "season": 2025,
            **defaults,
            "pass_rate": 0.60,
            "neutral_early_down_pass_rate": 0.58,
            "epa_per_play": 0.10,
        }
    )
    writer.writerow(
        {
            "team": "BBB",
            "season": 2025,
            **defaults,
            "pass_rate": 0.52,
            "neutral_early_down_pass_rate": 0.49,
            "rb_target_share": 0.25,
        }
    )
    return stream.getvalue().encode("utf-8")


class EnvironmentTests(unittest.TestCase):
    def _inputs(self, directory: str) -> tuple[Path, Path]:
        research_path = Path(directory) / "research.json"
        style_path = Path(directory) / "styles.csv"
        research_path.write_text(json.dumps(research_payload()), encoding="utf-8")
        style_path.write_bytes(observed_csv())
        return research_path, style_path

    def test_builds_explainable_certainty_and_news_shift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            research_path, style_path = self._inputs(directory)
            research = load_research_dataset(research_path)
            observed = load_observed_styles(style_path)
            forecast = build_team_environment_forecast(
                research,
                observed,
                generated_at=datetime(2026, 9, 2, 21, 0, tzinfo=timezone.utc),
            )

            teams = {team["team"]: team for team in forecast["teams"]}
            self.assertGreater(
                teams["AAA"]["certainty"]["structural_score"],
                teams["BBB"]["certainty"]["structural_score"],
            )
            bbb_pass = teams["BBB"]["style_forecast"]["pass_rate"]
            self.assertLess(bbb_pass["value"], bbb_pass["anchor_value"])
            self.assertEqual(bbb_pass["evidence_claim_ids"], ["bbb_more_run"])
            self.assertIn(teams["AAA"]["certainty"]["tier"], {"high", "medium_high"})
            self.assertGreater(teams["AAA"]["position_environments"]["QB"]["coverage"], 0.9)
            self.assertEqual(forecast["calibration_status"], "uncalibrated_heuristic")

    def test_rejects_dangling_source_reference(self) -> None:
        payload = research_payload()
        payload["teams"][0]["scheme_source_ids"] = ["missing"]  # type: ignore[index]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "research.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(EnvironmentDataError, "unknown sources"):
                load_research_dataset(path)

    def test_writes_immutable_forecast_with_input_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            research_path, style_path = self._inputs(directory)
            research_bytes = research_path.read_bytes()
            style_bytes = style_path.read_bytes()
            forecast = build_team_environment_forecast(
                load_research_dataset(research_path),
                load_observed_styles(style_path),
                generated_at=datetime(2026, 9, 2, 21, 0, tzinfo=timezone.utc),
            )
            path = write_environment_snapshot(
                forecast,
                Path(directory) / "derived",
                research_bytes=research_bytes,
                observed_style_bytes=style_bytes,
            )
            manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            summary_rows = list(
                csv.DictReader(
                    io.StringIO((path / "team_environment.csv").read_text(encoding="utf-8"))
                )
            )

            self.assertEqual(manifest["quality"]["teams"], ["AAA", "BBB"])
            self.assertEqual(
                manifest["inputs"]["research_sha256"],
                hashlib.sha256(research_bytes).hexdigest(),
            )
            self.assertEqual(len(summary_rows), 2)
            with self.assertRaises(FileExistsError):
                write_environment_snapshot(
                    forecast,
                    Path(directory) / "derived",
                    research_bytes=research_bytes,
                    observed_style_bytes=style_bytes,
                )


if __name__ == "__main__":
    unittest.main()
