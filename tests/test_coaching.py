import csv
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fantasy_draft.coaching import (
    CoachingDataError,
    build_coaching_census,
    load_playcaller_registry,
    write_coaching_census_snapshot,
)
from fantasy_draft.sources.official_staff import OFFICIAL_STAFF_URLS, STAFF_FIELDS


def registry_payload() -> dict:
    return {
        "schema_version": "1.0.0",
        "season": 2026,
        "as_of": "2026-09-02",
        "sources": [
            {
                "id": "official",
                "title": "Current caller announcement",
                "publisher": "NFL club",
                "source_type": "official_team",
                "url": "https://example.com/caller",
                "published_at": "2026-08-01",
                "accessed_at": "2026-09-02",
            }
        ],
        "teams": [
            {
                "team": team,
                "head_coach": f"{team} Head",
                "offensive_coordinator": f"{team} Coordinator",
                "play_caller": f"{team} Head",
                "confirmation": "official_explicit",
                "source_ids": ["official"],
                "evidence_summary": "The club explicitly named the head coach.",
            }
            for team in OFFICIAL_STAFF_URLS
        ],
    }


def write_registry(directory: str, payload: dict | None = None) -> Path:
    path = Path(directory) / "registry.json"
    path.write_text(json.dumps(payload or registry_payload()), encoding="utf-8")
    return path


def write_staff(directory: str, *, bad_head_coach: str | None = None) -> Path:
    path = Path(directory) / "staff.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=STAFF_FIELDS)
        writer.writeheader()
        for team in OFFICIAL_STAFF_URLS:
            writer.writerow(
                {
                    "season": 2026,
                    "team": team,
                    "name": bad_head_coach if team == "ARI" and bad_head_coach else f"{team} Head",
                    "role": "Head Coach",
                    "side": "head_coach",
                    "responsibility_categories": "head_coach",
                    "profile_url": f"https://example.com/{team.lower()}-head",
                    "source_url": "https://example.com/staff",
                    "retrieved_at": "2026-09-02T21:00:00.000000Z",
                }
            )
            writer.writerow(
                {
                    "season": 2026,
                    "team": team,
                    "name": f"{team} Coordinator",
                    "role": "Offensive Coordinator",
                    "side": "offense",
                    "responsibility_categories": "offensive_coordinator",
                    "profile_url": f"https://example.com/{team.lower()}-oc",
                    "source_url": "https://example.com/staff",
                    "retrieved_at": "2026-09-02T21:00:00.000000Z",
                }
            )
    return path


class CoachingTests(unittest.TestCase):
    def test_registry_requires_all_32_teams_and_real_caller_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = registry_payload()
            payload["teams"] = payload["teams"][:-1]
            with self.assertRaisesRegex(CoachingDataError, "exactly the 32"):
                load_playcaller_registry(write_registry(directory, payload))

        with tempfile.TemporaryDirectory() as directory:
            payload = registry_payload()
            payload["sources"][0]["source_type"] = "credentialed_local"
            with self.assertRaisesRegex(CoachingDataError, "official source"):
                load_playcaller_registry(write_registry(directory, payload))

    def test_cross_checks_titles_and_marks_only_sourced_caller(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = load_playcaller_registry(write_registry(directory))
            staff_path = write_staff(directory)
            census = build_coaching_census(registry, staff_path)

            self.assertEqual(len(census.team_rows), 32)
            ari = next(row for row in census.team_rows if row["team"] == "ARI")
            self.assertEqual(ari["play_caller"], "ARI Head")
            self.assertEqual(ari["caller_title"], "Head Coach")
            self.assertEqual(ari["evidence_strength"], 1.0)

            offensive = [
                record
                for record in census.official_staff
                if record.team == "ARI" and record.side == "offense"
            ]
            self.assertEqual(len(offensive), 1)
            self.assertEqual(offensive[0].name, "ARI Coordinator")
            self.assertNotEqual(offensive[0].name, ari["play_caller"])

    def test_rejects_registry_title_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry = load_playcaller_registry(write_registry(directory))
            staff_path = write_staff(directory, bad_head_coach="Different Head")
            with self.assertRaisesRegex(CoachingDataError, "does not match official"):
                build_coaching_census(registry, staff_path)

    def test_writes_immutable_hash_bearing_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry_path = write_registry(directory)
            registry_bytes = registry_path.read_bytes()
            registry = load_playcaller_registry(registry_path)
            census = build_coaching_census(registry, write_staff(directory))
            generated_at = datetime(2026, 9, 2, 22, 0, tzinfo=timezone.utc)
            snapshot = write_coaching_census_snapshot(
                census,
                Path(directory) / "derived",
                registry_bytes=registry_bytes,
                generated_at=generated_at,
            )
            manifest = json.loads((snapshot / "manifest.json").read_text())
            teams_csv = (snapshot / "teams.csv").read_bytes()

            self.assertEqual(snapshot.name, "20260902T220000.000000Z")
            self.assertEqual(manifest["status"], "identity_census_only")
            self.assertEqual(manifest["quality"]["team_count"], 32)
            self.assertFalse(manifest["quality"]["title_caller_inference_used"])
            self.assertEqual(
                manifest["artifacts"]["teams"]["sha256"],
                hashlib.sha256(teams_csv).hexdigest(),
            )
            self.assertTrue((snapshot / "offensive_staff.csv").is_file())
            self.assertTrue((snapshot / "sources.json").is_file())
            with self.assertRaises(FileExistsError):
                write_coaching_census_snapshot(
                    census,
                    Path(directory) / "derived",
                    registry_bytes=registry_bytes,
                    generated_at=generated_at,
                )


if __name__ == "__main__":
    unittest.main()
