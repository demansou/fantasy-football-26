import csv
import hashlib
import io
import json
import tempfile
import unittest
from datetime import date, datetime, timezone

from fantasy_draft.sources.espn_playcallers import (
    EspnPlaycallerQuery,
    EspnPlaycallerSnapshot,
    EspnPlaycallerSourceError,
    parse_espn_playcallers,
    write_espn_playcaller_snapshot,
)


def article_fixture(*, include_experience: bool = True) -> bytes:
    experience = (
        "<p><strong>Experience:</strong> Reid has called plays for many seasons.</p>"
        if include_experience
        else ""
    )
    return f"""<!doctype html><html><body>
    <h2>AFC WEST</h2>
    <h2><a>Kansas City Chiefs</a></h2>
    <p><strong>Playcaller: </strong>Andy Reid, head coach</p>
    {experience}
    <p><strong>What to know:</strong> Context.</p>
    <h2><a>Seattle Seahawks</a></h2>
    <p><strong>Playcaller: </strong>Klint Kubiak, offensive coordinator</p>
    <p><strong>Experience:</strong> Kubiak called plays for prior teams.</p>
    </body></html>""".encode()


class EspnPlaycallerSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.retrieved_at = datetime(2026, 9, 2, 22, 15, tzinfo=timezone.utc)
        self.url = "https://www.espn.com/nfl/story/_/id/46137832/example"
        self.query = EspnPlaycallerQuery(2025, teams=("KC", "SEA"))

    def test_query_normalizes_and_rejects_invalid_values(self) -> None:
        self.assertEqual(self.query.teams, ("KC", "SEA"))
        with self.assertRaisesRegex(ValueError, "duplicates"):
            EspnPlaycallerQuery(2025, teams=("KC", "kc"))
        self.assertEqual(EspnPlaycallerQuery(2024, teams=("KC",)).season, 2024)
        with self.assertRaisesRegex(ValueError, "no ESPN"):
            EspnPlaycallerQuery(2022, teams=("KC",))

    def test_parses_one_explicit_caller_and_experience_section_per_team(self) -> None:
        records = parse_espn_playcallers(
            article_fixture(),
            self.query,
            source_url=self.url,
            published_at=date(2025, 9, 9),
            retrieved_at=self.retrieved_at,
        )
        by_team = {record.team: record for record in records}
        self.assertEqual(by_team["KC"].play_caller, "Andy Reid")
        self.assertEqual(by_team["KC"].caller_title, "head coach")
        self.assertIn("many seasons", by_team["KC"].experience_text)
        self.assertEqual(by_team["SEA"].play_caller, "Klint Kubiak")

    def test_rejects_missing_experience_section(self) -> None:
        with self.assertRaisesRegex(EspnPlaycallerSourceError, "lacks caller or experience"):
            parse_espn_playcallers(
                article_fixture(include_experience=False),
                self.query,
                source_url=self.url,
                published_at=date(2025, 9, 9),
                retrieved_at=self.retrieved_at,
            )

    def test_writes_temporally_labeled_snapshot(self) -> None:
        raw = article_fixture()
        records = parse_espn_playcallers(
            raw,
            self.query,
            source_url=self.url,
            published_at=date(2025, 9, 9),
            retrieved_at=self.retrieved_at,
        )
        snapshot = EspnPlaycallerSnapshot(
            query=self.query,
            retrieved_at=self.retrieved_at,
            source_url=self.url,
            published_at=date(2025, 9, 9),
            raw_html=raw,
            records=records,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = write_espn_playcaller_snapshot(snapshot, directory)
            manifest = json.loads((path / "manifest.json").read_text())
            caller_bytes = (path / "callers.csv").read_bytes()
            rows = list(csv.DictReader(io.StringIO(caller_bytes.decode())))

            self.assertEqual(path.name, "20260902T221500.000000Z")
            self.assertEqual(manifest["quality"]["team_count"], 2)
            self.assertIn("forbidden", manifest["temporal_use"])
            self.assertEqual(
                manifest["artifacts"]["callers"]["sha256"],
                hashlib.sha256(caller_bytes).hexdigest(),
            )
            self.assertEqual(rows[0]["temporal_use"], "historical_identity_only_not_preseason_backtest_evidence")
            self.assertTrue((path / "article.html").is_file())


if __name__ == "__main__":
    unittest.main()
