import csv
import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone

from fantasy_draft.sources.official_staff import (
    STAFF_FIELDS,
    OfficialStaffPage,
    OfficialStaffQuery,
    OfficialStaffSnapshot,
    OfficialStaffSourceError,
    parse_official_staff_page,
    write_official_staff_snapshot,
)


def staff_fixture(*, include_head_coach: bool = True, count: int = 8) -> bytes:
    coaches = [
        ("Head Coach", "Alex Head", "/team/coaches-roster/alex-head"),
        (
            "Assistant Head Coach/Offensive Coordinator",
            "Olivia Caller",
            "/team/coaches-roster/olivia-caller",
        ),
        ("Quarterbacks", "Quinn Back", "/team/coaches-roster/quinn-back"),
        ("Running Backs", "Riley Runner", "/team/coaches-roster/riley-runner"),
        ("Wide Receivers", "Will Receiver", "/team/coaches-roster/will-receiver"),
        ("Tight Ends/Pass Game", "Terry End", "/team/coaches-roster/terry-end"),
        ("Offensive Line/Run Game", "Ollie Line", "/team/coaches-roster/ollie-line"),
        ("Defensive Coordinator", "Dee Fence", "/team/coaches-roster/dee-fence"),
        ("Assistant To The Head Coach", "Casey Support", "/team/coaches-roster/casey-support"),
    ]
    if not include_head_coach:
        coaches = coaches[1:]
    coaches = coaches[:count]
    cards = "".join(
        (
            f'<a class="person-card person-card--link" href="{href}" '
            f'aria-label="View {name}">'
            f'<h5 class="person-card__roofline">{role}</h5>'
            f'<h3 class="person-card__title">{name}</h3>'
            "</a>"
        )
        for role, name, href in coaches
    )
    return f"<!doctype html><html><body>{cards}</body></html>".encode()


def featured_and_unlinked_fixture() -> bytes:
    return b"""<!doctype html><html><body>
    <div class="d3-o-media-object d3-o-person-card--featured">
      <div><h3 class="d3-o-media-object__title">Alex Head</h3>
      <h5 class="d3-o-media-object__roofline">Head Coach</h5>
      <a href="/team/coaches-roster/alex-head">Profile</a></div>
    </div>
    <div class="d3-o-media-object d3-o-person-card--non-featured">
      <div><h5 class="d3-o-media-object__roofline">Quarterbacks</h5>
      <h3 class="d3-o-media-object__title">Quinn Back</h3></div>
    </div>
    <div class="d3-o-media-object d3-o-person-card--non-featured">
      <h5 class="d3-o-media-object__roofline">Running Backs</h5>
      <h3 class="d3-o-media-object__title">Riley Runner</h3>
    </div>
    <div class="d3-o-media-object d3-o-person-card--non-featured">
      <h5 class="d3-o-media-object__roofline">Wide Receivers</h5>
      <h3 class="d3-o-media-object__title">Will Receiver</h3>
    </div>
    <div class="d3-o-media-object d3-o-person-card--non-featured">
      <h5 class="d3-o-media-object__roofline">Offensive Line</h5>
      <h3 class="d3-o-media-object__title">Ollie Line</h3>
    </div>
    </body></html>"""


class OfficialStaffSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.retrieved_at = datetime(2026, 9, 2, 21, 30, tzinfo=timezone.utc)
        self.source_url = "https://www.chiefs.com/team/coaches-roster/"

    def test_query_normalizes_teams_and_rejects_duplicates(self) -> None:
        query = OfficialStaffQuery(2026, teams=("sea", "KC"))
        self.assertEqual(query.teams, ("KC", "SEA"))
        with self.assertRaisesRegex(ValueError, "duplicates"):
            OfficialStaffQuery(2026, teams=("KC", "kc"))
        with self.assertRaisesRegex(ValueError, "unsupported"):
            OfficialStaffQuery(2026, teams=("ZZZ",))

    def test_extracts_offensive_responsibilities_without_inferring_caller(self) -> None:
        records = parse_official_staff_page(
            "KC",
            staff_fixture(),
            season=2026,
            source_url=self.source_url,
            retrieved_at=self.retrieved_at,
        )
        by_name = {record.name: record for record in records}

        self.assertEqual(by_name["Alex Head"].side, "head_coach")
        self.assertEqual(by_name["Olivia Caller"].side, "offense")
        self.assertIn(
            "offensive_coordinator",
            by_name["Olivia Caller"].responsibility_categories,
        )
        self.assertNotIn(
            "offensive_coordinator",
            by_name["Ollie Line"].responsibility_categories,
        )
        self.assertIn("tight_ends", by_name["Terry End"].responsibility_categories)
        self.assertIn("pass_game", by_name["Terry End"].responsibility_categories)
        self.assertIn("offensive_line", by_name["Ollie Line"].responsibility_categories)
        self.assertIn("run_game", by_name["Ollie Line"].responsibility_categories)
        self.assertEqual(by_name["Dee Fence"].side, "defense")
        self.assertEqual(
            by_name["Quinn Back"].profile_url,
            "https://www.chiefs.com/team/coaches-roster/quinn-back",
        )
        self.assertNotIn("play_caller", STAFF_FIELDS)
        self.assertNotIn("play_caller", by_name["Olivia Caller"].to_row())

        assistant = parse_official_staff_page(
            "KC",
            staff_fixture(count=9),
            season=2026,
            source_url=self.source_url,
            retrieved_at=self.retrieved_at,
        )
        self.assertEqual(
            {record.name: record for record in assistant}["Casey Support"].side,
            "other",
        )

    def test_rejects_missing_head_coach_and_too_few_cards(self) -> None:
        with self.assertRaisesRegex(OfficialStaffSourceError, "head coaches"):
            parse_official_staff_page(
                "KC",
                staff_fixture(include_head_coach=False),
                season=2026,
                source_url=self.source_url,
                retrieved_at=self.retrieved_at,
            )
        with self.assertRaisesRegex(OfficialStaffSourceError, "only 4"):
            parse_official_staff_page(
                "KC",
                staff_fixture(count=4),
                season=2026,
                source_url=self.source_url,
                retrieved_at=self.retrieved_at,
            )

    def test_extracts_featured_head_coach_and_unlinked_staff_cards(self) -> None:
        records = parse_official_staff_page(
            "BAL",
            featured_and_unlinked_fixture(),
            season=2026,
            source_url="https://www.baltimoreravens.com/team/coaches-roster/",
            retrieved_at=self.retrieved_at,
        )
        by_name = {record.name: record for record in records}
        self.assertEqual(by_name["Alex Head"].side, "head_coach")
        self.assertEqual(
            by_name["Alex Head"].profile_url,
            "https://www.baltimoreravens.com/team/coaches-roster/alex-head",
        )
        self.assertEqual(by_name["Quinn Back"].profile_url, "")

    def test_writes_atomic_immutable_snapshot_with_coverage_and_hashes(self) -> None:
        raw = staff_fixture()
        records = parse_official_staff_page(
            "KC",
            raw,
            season=2026,
            source_url=self.source_url,
            retrieved_at=self.retrieved_at,
        )
        snapshot = OfficialStaffSnapshot(
            query=OfficialStaffQuery(2026, teams=("KC",)),
            retrieved_at=self.retrieved_at,
            pages=(OfficialStaffPage(team="KC", url=self.source_url, raw_bytes=raw),),
            records=records,
        )

        with tempfile.TemporaryDirectory() as directory:
            path = write_official_staff_snapshot(snapshot, directory)
            manifest = json.loads((path / "manifest.json").read_text())
            staff_csv = (path / "staff.csv").read_bytes()
            rows = list(csv.DictReader(io.StringIO(staff_csv.decode())))

            self.assertEqual(path.name, "20260902T213000.000000Z")
            self.assertEqual(manifest["quality"]["team_count"], 1)
            self.assertEqual(manifest["quality"]["record_count"], 8)
            self.assertEqual(manifest["quality"]["offensive_record_count"], 6)
            self.assertEqual(manifest["quality"]["offensive_staff_record_count"], 7)
            self.assertEqual(manifest["coverage"]["KC"]["head_coach"], "Alex Head")
            self.assertEqual(
                manifest["coverage"]["KC"]["primary_offensive_coordinators"],
                ["Olivia Caller"],
            )
            self.assertEqual(manifest["coverage"]["KC"]["missing_responsibilities"], [])
            self.assertEqual(
                manifest["artifacts"]["staff"]["sha256"],
                hashlib.sha256(staff_csv).hexdigest(),
            )
            self.assertEqual(
                manifest["artifacts"]["raw_pages"]["KC.html"]["sha256"],
                hashlib.sha256(raw).hexdigest(),
            )
            self.assertEqual(len(rows), 8)
            self.assertTrue((path / "raw" / "KC.html").is_file())
            self.assertFalse(
                any(item.name.startswith(".staging-") for item in path.parent.iterdir())
            )
            with self.assertRaises(FileExistsError):
                write_official_staff_snapshot(snapshot, directory)


if __name__ == "__main__":
    unittest.main()
