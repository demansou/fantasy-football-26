import csv
import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fantasy_draft.playcaller_evidence import (
    PlaycallerEvidenceDataError,
    load_playcaller_evidence_registry,
    write_playcaller_evidence_snapshot,
)
from fantasy_draft.sources.nfl_record_book import TEAM_NAMES


class PlaycallerEvidenceTests(unittest.TestCase):
    def _registry(self, path: Path, *, late_source: bool = False) -> Path:
        source = {
            "id": "census",
            "title": "All-team caller table",
            "publisher": "Example",
            "source_type": "credentialed_national",
            "url": "https://example.com/callers",
            "published_at": "2025-09-02" if late_source else "2025-06-25",
            "accessed_at": "2026-09-03",
            "locator": "Headings 1-32",
            "content_sha256": "a" * 64,
            "content_hash_scope": "Synthetic fixture bytes",
        }
        teams = []
        for team in TEAM_NAMES:
            item = {
                "team": team,
                "identity_status": "confirmed",
                "play_caller": f"Caller {team}",
                "source_ids": ["census"],
                "evidence_summary": "The source names one caller.",
            }
            if team == "NYG":
                item.pop("play_caller")
                item["identity_status"] = "ambiguous"
                item["candidate_callers"] = ["Alpha", "Beta"]
                item["evidence_summary"] = "The source explicitly leaves two candidates."
            teams.append(item)
        path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "season": 2025,
                    "as_of": "2026-09-03",
                    "temporal_use": "preseason_identity_evidence",
                    "forecast_evidence_cutoff": "2025-08-31",
                    "methodology": {"rule": "Do not resolve ambiguity with results."},
                    "sources": [source],
                    "teams": teams,
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_publishes_complete_census_and_preserves_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = load_playcaller_evidence_registry(
                self._registry(root / "registry.json")
            )
            destination = write_playcaller_evidence_snapshot(
                registry,
                root / "raw",
                created_at=datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc),
            )
            rows = list(
                csv.DictReader(io.StringIO((destination / "callers.csv").read_text()))
            )
            manifest = json.loads((destination / "manifest.json").read_text())
            nyg = next(row for row in rows if row["team"] == "NYG")

            self.assertEqual(destination.name, "20260903T120000.000000Z")
            self.assertEqual(len(rows), 32)
            self.assertEqual(nyg["play_caller"], "")
            self.assertEqual(nyg["identity_status"], "ambiguous")
            self.assertEqual(nyg["candidate_callers"], "Alpha|Beta")
            self.assertEqual(manifest["quality"]["ambiguous_count"], 1)
            self.assertFalse(manifest["quality"]["hindsight_resolution_used"])
            caller_raw = (destination / "callers.csv").read_bytes()
            self.assertEqual(
                manifest["artifacts"]["callers.csv"]["sha256"],
                hashlib.sha256(caller_raw).hexdigest(),
            )

    def test_rejects_preseason_source_after_declared_cutoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._registry(Path(directory) / "registry.json", late_source=True)
            with self.assertRaisesRegex(
                PlaycallerEvidenceDataError, "published after the forecast cutoff"
            ):
                load_playcaller_evidence_registry(path)


if __name__ == "__main__":
    unittest.main()
