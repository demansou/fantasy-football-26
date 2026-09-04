import csv
import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone

from fantasy_draft.sources.nfl_record_book import (
    NflRecordBookQuery,
    NflRecordBookSnapshot,
    NflRecordBookSourceError,
    fetch_nfl_record_book_staff,
    parse_record_book_staff_text,
    write_nfl_record_book_snapshot,
)


def record_book_fixture(*, omit: str | tuple[str, ...] | None = None) -> str:
    entries = [
        ("Olivia Caller", "offensive coordinator"),
        ("Quinn Back", "quarterbacks"),
        ("Riley Runner", "running backs"),
        ("Will Receiver", "wide receivers"),
        ("Terry End", "tight ends"),
        ("Ollie Line", "offensive line"),
        ("Pat Game", "pass game coordinator"),
        ("Casey Support", "offensive assistant"),
        ("Dee Fence", "defensive coordinator"),
    ]
    omitted = {omit} if isinstance(omit, str) else set(omit or ())
    entries = [item for item in entries if item[1] not in omitted]
    staff = "\n".join(
        f"{name}, {role}; born Jan. 1, 1980, Test City."
        for name, role in entries
    )
    page = f"""KANSAS CITY CHIEFS
2025 COACHING STAFF
Alex Head, Executive VP/Head Coach
ASSISTANT COACHES
{staff}
Pat Variant; passing game coordinator; Test City.
Nora Birthless, offensive assistant. Attended Test University.
Elvis Dumervil, 2014. . . . . 17.0
Willie Taggart, assistant head coach/running backs; born Jan. 2, 1970.
RECORD HOLDERS
2025 NFL Record & Fact Book 97
"""
    return page + ("\f" * 32)


class _Response:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.headers = {
            "Last-Modified": "Tue, 22 Jul 2025 00:00:00 GMT",
            "ETag": '"test-etag"',
        }

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int) -> bytes:
        return self.body

    def geturl(self) -> str:
        return "https://static.clubs.nfl.com/record-book.pdf"


class NflRecordBookSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.retrieved_at = datetime(2026, 9, 2, 22, 0, tzinfo=timezone.utc)
        self.query = NflRecordBookQuery(2025, teams=("KC",))
        self.source_url = "https://static.clubs.nfl.com/record-book.pdf"

    def test_query_normalizes_and_rejects_unsupported_values(self) -> None:
        self.assertEqual(
            NflRecordBookQuery(2025, teams=("sea", "KC")).teams,
            ("KC", "SEA"),
        )
        self.assertEqual(NflRecordBookQuery(2022, teams=("KC",)).season, 2022)
        self.assertEqual(NflRecordBookQuery(2023, teams=("KC",)).season, 2023)
        self.assertEqual(NflRecordBookQuery(2024, teams=("KC",)).season, 2024)
        with self.assertRaisesRegex(ValueError, "duplicates"):
            NflRecordBookQuery(2025, teams=("KC", "kc"))
        with self.assertRaisesRegex(ValueError, "no official NFL record-book"):
            NflRecordBookQuery(2021, teams=("KC",))

    def test_parses_staff_and_rejects_record_table_false_positive(self) -> None:
        records = parse_record_book_staff_text(
            record_book_fixture(),
            self.query,
            source_url=self.source_url,
            retrieved_at=self.retrieved_at,
        )
        by_name = {record.name: record for record in records}

        self.assertEqual(by_name["Alex Head"].side, "head_coach")
        self.assertIn(
            "offensive_coordinator",
            by_name["Olivia Caller"].responsibility_categories,
        )
        self.assertIn("running_backs", by_name["Riley Runner"].responsibility_categories)
        self.assertIn("running_backs", by_name["Willie Taggart"].responsibility_categories)
        self.assertIn("pass_game", by_name["Pat Variant"].responsibility_categories)
        self.assertIn("offensive_assistant", by_name["Nora Birthless"].responsibility_categories)
        self.assertNotIn("Elvis Dumervil", by_name)
        self.assertEqual(by_name["Olivia Caller"].book_page, 97)

    def test_preserves_one_missing_position_responsibility(self) -> None:
        records = parse_record_book_staff_text(
            record_book_fixture(omit="tight ends"),
            self.query,
            source_url=self.source_url,
            retrieved_at=self.retrieved_at,
        )
        categories = {
            category
            for record in records
            for category in record.responsibility_categories
        }
        self.assertNotIn("tight_ends", categories)

    def test_rejects_multiple_missing_position_responsibilities(self) -> None:
        with self.assertRaisesRegex(NflRecordBookSourceError, "tight_ends"):
            parse_record_book_staff_text(
                record_book_fixture(omit=("quarterbacks", "tight ends")),
                self.query,
                source_url=self.source_url,
                retrieved_at=self.retrieved_at,
            )

    def test_fetch_validates_pdf_and_uses_injected_extractor(self) -> None:
        raw_pdf = b"%PDF-1.7\nfixture"

        def fake_urlopen(_request, timeout):
            self.assertEqual(timeout, 12.0)
            return _Response(raw_pdf)

        snapshot = fetch_nfl_record_book_staff(
            self.query,
            timeout=12.0,
            retrieved_at=self.retrieved_at,
            urlopen_fn=fake_urlopen,
            text_extractor=lambda body: (
                record_book_fixture(),
                "fixture extractor",
                "",
            ),
        )

        self.assertEqual(snapshot.raw_pdf, raw_pdf)
        self.assertEqual(snapshot.source_url, self.source_url)
        self.assertEqual(snapshot.extractor, "fixture extractor")
        self.assertEqual(len(snapshot.records), 13)

        with self.assertRaisesRegex(NflRecordBookSourceError, "not a PDF"):
            fetch_nfl_record_book_staff(
                self.query,
                urlopen_fn=lambda *_args, **_kwargs: _Response(b"not-pdf"),
                text_extractor=lambda _body: (record_book_fixture(), "fixture", ""),
            )

    def test_writes_atomic_immutable_snapshot_with_hashes(self) -> None:
        text = record_book_fixture()
        records = parse_record_book_staff_text(
            text,
            self.query,
            source_url=self.source_url,
            retrieved_at=self.retrieved_at,
        )
        snapshot = NflRecordBookSnapshot(
            query=self.query,
            retrieved_at=self.retrieved_at,
            source_url=self.source_url,
            raw_pdf=b"%PDF-1.7\nfixture",
            extracted_text=text,
            records=records,
            extractor="fixture extractor",
        )

        with tempfile.TemporaryDirectory() as directory:
            path = write_nfl_record_book_snapshot(snapshot, directory)
            manifest = json.loads((path / "manifest.json").read_text())
            staff_bytes = (path / "staff.csv").read_bytes()
            rows = list(csv.DictReader(io.StringIO(staff_bytes.decode())))

            self.assertEqual(path.name, "20260902T220000.000000Z")
            self.assertEqual(manifest["quality"]["team_count"], 1)
            self.assertEqual(manifest["quality"]["record_count"], 13)
            self.assertEqual(manifest["coverage"]["KC"]["head_coach"], "Alex Head")
            self.assertEqual(
                manifest["artifacts"]["staff"]["sha256"],
                hashlib.sha256(staff_bytes).hexdigest(),
            )
            self.assertEqual(len(rows), 13)
            self.assertTrue((path / "record_book.pdf").is_file())
            self.assertTrue((path / "record_book.txt").is_file())
            with self.assertRaises(FileExistsError):
                write_nfl_record_book_snapshot(snapshot, directory)


if __name__ == "__main__":
    unittest.main()
