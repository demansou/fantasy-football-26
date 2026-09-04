"""Historical coaching staffs from official NFL Record & Fact Books.

The record book is a frozen, league-published source that avoids reconstructing
prior staffs from living club pages.  The 2022-25 editions contain standardized
coaching-staff sections for every club, including position coaches.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SOURCE_ID = "official_nfl_record_fact_book"
SOURCE_NAME = "Official NFL Record & Fact Book"
ADAPTER_VERSION = "1.1.0"
SNAPSHOT_SCHEMA_VERSION = "1.0.0"
MAX_PDF_BYTES = 100_000_000

# NFL-authored books are preserved on league and official club CDNs.  These
# immutable Cloudinary assets remain available after older Football Operations
# vanity URLs stop resolving.
RECORD_BOOK_URLS: Mapping[int, str] = {
    2022: "https://static.www.nfl.com/image/upload/league/apps/league-site/media-guides/2022/2022_NFL_Record_and_Fact_Book.pdf",
    2023: "https://static.clubs.nfl.com/image/upload/patriots/wlpvln9lfdtvfqc5gu40.pdf",
    2024: "https://static.www.nfl.com/image/upload/league/apps/league-site/media-guides/2024/2024_Record_and_Fact_Book_incl_Supplemental.pdf",
    2025: "https://static.clubs.nfl.com/image/upload/patriots/fvc6qgwyqlztq1muztpi.pdf",
}

TEAM_NAMES: Mapping[str, str] = {
    "ARI": "ARIZONA CARDINALS",
    "ATL": "ATLANTA FALCONS",
    "BAL": "BALTIMORE RAVENS",
    "BUF": "BUFFALO BILLS",
    "CAR": "CAROLINA PANTHERS",
    "CHI": "CHICAGO BEARS",
    "CIN": "CINCINNATI BENGALS",
    "CLE": "CLEVELAND BROWNS",
    "DAL": "DALLAS COWBOYS",
    "DEN": "DENVER BRONCOS",
    "DET": "DETROIT LIONS",
    "GB": "GREEN BAY PACKERS",
    "HOU": "HOUSTON TEXANS",
    "IND": "INDIANAPOLIS COLTS",
    "JAX": "JACKSONVILLE JAGUARS",
    "KC": "KANSAS CITY CHIEFS",
    "LAC": "LOS ANGELES CHARGERS",
    "LAR": "LOS ANGELES RAMS",
    "LV": "LAS VEGAS RAIDERS",
    "MIA": "MIAMI DOLPHINS",
    "MIN": "MINNESOTA VIKINGS",
    "NE": "NEW ENGLAND PATRIOTS",
    "NO": "NEW ORLEANS SAINTS",
    "NYG": "NEW YORK GIANTS",
    "NYJ": "NEW YORK JETS",
    "PHI": "PHILADELPHIA EAGLES",
    "PIT": "PITTSBURGH STEELERS",
    "SEA": "SEATTLE SEAHAWKS",
    "SF": "SAN FRANCISCO 49ERS",
    "TB": "TAMPA BAY BUCCANEERS",
    "TEN": "TENNESSEE TITANS",
    "WAS": "WASHINGTON COMMANDERS",
}

STAFF_FIELDS = (
    "season",
    "team",
    "name",
    "role",
    "side",
    "responsibility_categories",
    "pdf_page",
    "book_page",
    "source_url",
    "retrieved_at",
)

REQUIRED_OFFENSIVE_CATEGORIES = (
    "quarterbacks",
    "running_backs",
    "wide_receivers",
    "tight_ends",
    "offensive_line",
)
MAX_MISSING_OFFENSIVE_CATEGORIES = 1

COACH_ROLE_TERMS = (
    "coach",
    "coordinator",
    "assistant",
    "offensive line",
    "quarterback",
    "running back",
    "wide receiver",
    "tight end",
    "defensive line",
    "linebacker",
    "secondary",
    "safeties",
    "cornerbacks",
    "quality control",
    "pass game",
    "passing game",
    "run game",
    "running game",
    "strength",
    "sports science",
    "statistical analysis",
)

NAME_PATTERN = r"[A-Z][A-Za-zÀ-ÖØ-öø-ÿ.'’\-]*(?:[ \t]+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ.'’\-]*){1,5}"
ASSISTANT_ENTRY = re.compile(
    rf"(?=^[ \t]*(?P<name>{NAME_PATTERN})(?:,\s*(?P<suffix>Jr\.|Sr\.|II|III|IV))?[,;]\s*"
    rf"(?P<role>.{{2,140}}?)[;,]\s*[Bb]orn\b)",
    re.MULTILINE | re.DOTALL,
)
SEMICOLON_ENTRY = re.compile(
    rf"(?=^[ \t]*(?P<name>{NAME_PATTERN})(?:,\s*(?P<suffix>Jr\.|Sr\.|II|III|IV))?[,;]\s*"
    rf"(?P<role>[^;]{{2,140}}?);)",
    re.MULTILINE,
)
PERIOD_ENTRY = re.compile(
    rf"(?=^[ \t]*(?P<name>{NAME_PATTERN})(?:,\s*(?P<suffix>Jr\.|Sr\.|II|III|IV))?[,;]\s*"
    rf"(?P<role>[^.;\n]{{2,70}}?)\.\s)",
    re.MULTILINE,
)
HEAD_COACH_ENTRY = re.compile(
    rf"^[ \t]*(?P<name>{NAME_PATTERN}),\s*"
    rf"(?P<role>(?:[^\n]*\n)?[^\n]*Head Coach)\s*$",
    re.MULTILINE,
)
class NflRecordBookSourceError(RuntimeError):
    """Raised when a record-book fetch, extraction, or parse is invalid."""


@dataclass(frozen=True)
class NflRecordBookQuery:
    season: int
    teams: tuple[str, ...] = tuple(TEAM_NAMES)

    def __post_init__(self) -> None:
        if self.season not in RECORD_BOOK_URLS:
            raise ValueError(
                f"no official NFL record-book URL configured for {self.season}"
            )
        normalized = tuple(sorted(team.strip().upper() for team in self.teams))
        if not normalized:
            raise ValueError("at least one record-book team is required")
        if len(set(normalized)) != len(normalized):
            raise ValueError("record-book teams cannot contain duplicates")
        unknown = set(normalized) - set(TEAM_NAMES)
        if unknown:
            raise ValueError(
                f"unsupported record-book teams: {', '.join(sorted(unknown))}"
            )
        object.__setattr__(self, "teams", normalized)

    @property
    def label(self) -> str:
        return "all" if set(self.teams) == set(TEAM_NAMES) else "-".join(self.teams)


@dataclass(frozen=True)
class HistoricalStaffRecord:
    season: int
    team: str
    name: str
    role: str
    side: str
    responsibility_categories: tuple[str, ...]
    pdf_page: int
    book_page: int | None
    source_url: str
    retrieved_at: datetime

    def to_row(self) -> dict[str, str | int]:
        return {
            "season": self.season,
            "team": self.team,
            "name": self.name,
            "role": self.role,
            "side": self.side,
            "responsibility_categories": "|".join(
                self.responsibility_categories
            ),
            "pdf_page": self.pdf_page,
            "book_page": "" if self.book_page is None else self.book_page,
            "source_url": self.source_url,
            "retrieved_at": _iso_z(self.retrieved_at),
        }


@dataclass(frozen=True)
class NflRecordBookSnapshot:
    query: NflRecordBookQuery
    retrieved_at: datetime
    source_url: str
    raw_pdf: bytes
    extracted_text: str
    records: tuple[HistoricalStaffRecord, ...]
    response_last_modified: str | None = None
    response_etag: str | None = None
    extractor: str = "pdftotext"
    extractor_stderr: str = ""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    return value.astimezone(timezone.utc)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _normalize_role(value: str) -> str:
    value = value.replace("\u00a0", " ")
    value = re.sub(r"(?<=[A-Za-z])-\s*\n\s*(?=[a-z])", "", value)
    value = re.sub(r"(?<=[a-z])-\s+(?=[a-z])", "", value)
    return " ".join(value.split()).strip(" .")


def _is_coach_role(role: str) -> bool:
    lowered = role.lower()
    # A true header contains only the staff title between the coach's name and
    # the birth marker. These guards reject a record-table row or biography
    # that happened to run into the next coach header in reading order.
    if len(role) > 70 or any(character.isdigit() for character in role):
        return False
    if "assistant coaches" in lowered or "joined " in lowered or "his wife" in lowered:
        return False
    return any(term in lowered for term in COACH_ROLE_TERMS)


def _side(role: str) -> str:
    lowered = role.lower()
    if lowered == "head coach" or lowered.endswith("/head coach"):
        return "head_coach"
    if any(term in lowered for term in ("defensive", "defense", "lineback", "secondary")):
        return "defense"
    if any(term in lowered for term in ("special teams", "kicking", "punter", "return game")):
        return "special_teams"
    if any(term in lowered for term in ("strength", "sports science", "conditioning")):
        return "performance"
    offensive_terms = (
        "offensive",
        "offense",
        "quarterback",
        "running back",
        "wide receiver",
        "tight end",
        "pass game",
        "passing game",
        "run game",
        "running game",
    )
    if any(term in lowered for term in offensive_terms):
        return "offense"
    return "other"


def _categories(role: str, side: str) -> tuple[str, ...]:
    lowered = role.lower()
    categories: set[str] = set()
    if side == "head_coach":
        categories.add("head_coach")
    if side != "offense":
        return tuple(sorted(categories))
    if "offensive coordinator" in lowered or "offense coordinator" in lowered:
        categories.add("offensive_coordinator")
    if "quarterback" in lowered:
        categories.add("quarterbacks")
    if "running back" in lowered:
        categories.add("running_backs")
    if "wide receiver" in lowered:
        categories.add("wide_receivers")
    if "tight end" in lowered:
        categories.add("tight_ends")
    if "offensive line" in lowered or "offense line" in lowered:
        categories.add("offensive_line")
    if "pass game" in lowered or "passing game" in lowered:
        categories.add("pass_game")
    if "run game" in lowered or "running game" in lowered:
        categories.add("run_game")
    if "assistant" in lowered or "quality control" in lowered:
        categories.add("offensive_assistant")
    return tuple(sorted(categories))


def _book_page(page: str, *, season: int) -> int | None:
    pattern = re.compile(
        rf"(?:{season} NFL Record & Fact Book\s+(\d+)|(\d+)\s+{season} NFL Record & Fact Book)"
    )
    matches = pattern.findall(page)
    if not matches:
        return None
    left, right = matches[-1]
    return int(left or right)


def _coaching_pages(
    pages: list[str], *, season: int, team: str
) -> tuple[tuple[int, str], ...]:
    team_name = TEAM_NAMES[team]
    marker = f"{season} COACHING STAFF"
    start = next(
        (
            index
            for index, page in enumerate(pages)
            if team_name in page
            and (marker in page or HEAD_COACH_ENTRY.search(page) is not None)
        ),
        None,
    )
    if start is None:
        raise NflRecordBookSourceError(
            f"{team} record-book coaching section was not found"
        )
    selected: list[tuple[int, str]] = []
    for index in range(start, min(start + 5, len(pages))):
        page = pages[index]
        if index > start and marker in page and team_name not in page:
            break
        if "RECORD HOLDERS" in page:
            # Reading-order extraction can place a final staff column after the
            # record-holder heading. Keep the page and rely on the strong staff
            # entry signature plus role filtering below.
            selected.append((index + 1, page))
            break
        selected.append((index + 1, page))
    if not selected:
        raise NflRecordBookSourceError(f"{team} coaching section was empty")
    return tuple(selected)


def parse_record_book_staff_text(
    text: str,
    query: NflRecordBookQuery,
    *,
    source_url: str,
    retrieved_at: datetime,
) -> tuple[HistoricalStaffRecord, ...]:
    """Extract standardized team coaching entries from pdftotext reading order."""

    retrieved_at = _utc(retrieved_at)
    pages = text.replace("\r\n", "\n").split("\f")
    if len(pages) < 32:
        raise NflRecordBookSourceError(
            f"record-book text yielded only {len(pages)} PDF pages"
        )
    records: list[HistoricalStaffRecord] = []
    for team in query.teams:
        team_records: list[HistoricalStaffRecord] = []
        seen: set[tuple[str, str]] = set()
        for pdf_page, page in _coaching_pages(
            pages, season=query.season, team=team
        ):
            book_page = _book_page(page, season=query.season)
            entries: list[tuple[str, str]] = []
            entries.extend(
                (match.group("name"), _normalize_role(match.group("role")))
                for match in HEAD_COACH_ENTRY.finditer(page)
            )
            for pattern in (ASSISTANT_ENTRY, SEMICOLON_ENTRY, PERIOD_ENTRY):
                entries.extend(
                    (
                        " ".join(
                            part
                            for part in (match.group("name"), match.group("suffix"))
                            if part
                        ),
                        _normalize_role(match.group("role")),
                    )
                    for match in pattern.finditer(page)
                )
            for name, role in entries:
                name = " ".join(name.split())
                role = _normalize_role(role)
                if not _is_coach_role(role):
                    continue
                key = (name.casefold(), role.casefold())
                if key in seen:
                    continue
                seen.add(key)
                side = _side(role)
                team_records.append(
                    HistoricalStaffRecord(
                        season=query.season,
                        team=team,
                        name=name,
                        role=role,
                        side=side,
                        responsibility_categories=_categories(role, side),
                        pdf_page=pdf_page,
                        book_page=book_page,
                        source_url=source_url,
                        retrieved_at=retrieved_at,
                    )
                )
        head_coaches = [
            record for record in team_records if record.side == "head_coach"
        ]
        if len(head_coaches) != 1:
            raise NflRecordBookSourceError(
                f"{team} record-book section yielded {len(head_coaches)} head coaches"
            )
        if len(team_records) < 10:
            raise NflRecordBookSourceError(
                f"{team} record-book section yielded only {len(team_records)} coaches"
            )
        categories = {
            category
            for record in team_records
            for category in record.responsibility_categories
        }
        missing = set(REQUIRED_OFFENSIVE_CATEGORIES) - categories
        # Some official books do not assign one of the five position-group
        # labels even though the full staff biography section is present (for
        # example, New England listed no quarterbacks coach in 2022). Preserve
        # that missingness in the snapshot instead of inferring a holder. More
        # than one missing group still signals a likely extraction failure.
        if len(missing) > MAX_MISSING_OFFENSIVE_CATEGORIES:
            raise NflRecordBookSourceError(
                f"{team} record-book section is missing offensive responsibilities: "
                f"{', '.join(sorted(missing))}"
            )
        records.extend(team_records)
    return tuple(
        sorted(records, key=lambda item: (item.team, item.side, item.role, item.name))
    )


def find_pdftotext() -> Path:
    """Locate Poppler's pdftotext in PATH or the Codex bundled runtime."""

    executable = shutil.which("pdftotext")
    if executable:
        return Path(executable)
    candidates = (
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/poppler/bin/pdftotext",
        Path("/opt/homebrew/bin/pdftotext"),
        Path("/usr/local/bin/pdftotext"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise NflRecordBookSourceError(
        "pdftotext is required to extract the official record book; install Poppler"
    )


def extract_pdf_text(
    raw_pdf: bytes,
    *,
    executable: str | Path | None = None,
    timeout: float = 120.0,
) -> tuple[str, str, str]:
    """Return reading-order text, extractor label, and extractor stderr."""

    if timeout <= 0:
        raise ValueError("PDF extraction timeout must be positive")
    binary = Path(executable) if executable is not None else find_pdftotext()
    try:
        result = subprocess.run(
            [str(binary), "-", "-"],
            input=raw_pdf,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise NflRecordBookSourceError(
            f"could not run pdftotext at {binary}: {error}"
        ) from error
    stderr = result.stderr.decode("utf-8", errors="replace").strip()
    if result.returncode != 0:
        raise NflRecordBookSourceError(
            f"pdftotext failed with exit code {result.returncode}: {stderr}"
        )
    try:
        text = result.stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        raise NflRecordBookSourceError("pdftotext output was not UTF-8") from error
    if not text.strip():
        raise NflRecordBookSourceError("pdftotext produced no text")
    return text, str(binary), stderr


def _download_pdf(
    url: str,
    *,
    timeout: float,
    urlopen_fn: Callable[..., Any],
) -> tuple[bytes, str, str | None, str | None]:
    request = Request(
        url,
        headers={
            "Accept": "application/pdf",
            "User-Agent": "fantasy-football-26/0.1 (+source-attributed personal research)",
        },
    )
    try:
        with urlopen_fn(request, timeout=timeout) as response:
            body = response.read(MAX_PDF_BYTES + 1)
            final_url = response.geturl() if hasattr(response, "geturl") else url
            last_modified = response.headers.get("Last-Modified")
            etag = response.headers.get("ETag")
    except HTTPError as error:
        raise NflRecordBookSourceError(
            f"NFL record book returned HTTP {error.code}: {url}"
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        raise NflRecordBookSourceError(
            f"could not fetch NFL record book {url}: {error}"
        ) from error
    if len(body) > MAX_PDF_BYTES:
        raise NflRecordBookSourceError(
            f"NFL record book exceeded {MAX_PDF_BYTES:,} bytes"
        )
    if not body.startswith(b"%PDF-"):
        raise NflRecordBookSourceError("NFL record-book response is not a PDF")
    return body, final_url, last_modified, etag


def fetch_nfl_record_book_staff(
    query: NflRecordBookQuery,
    *,
    timeout: float = 60.0,
    extraction_timeout: float = 120.0,
    retrieved_at: datetime | None = None,
    urlopen_fn: Callable[..., Any] = urlopen,
    text_extractor: Callable[[bytes], tuple[str, str, str]] | None = None,
) -> NflRecordBookSnapshot:
    """Fetch, extract, and validate historical coaching staff entries."""

    if timeout <= 0:
        raise ValueError("record-book HTTP timeout must be positive")
    retrieved_at = _utc(retrieved_at or datetime.now(timezone.utc))
    raw_pdf, final_url, last_modified, etag = _download_pdf(
        RECORD_BOOK_URLS[query.season], timeout=timeout, urlopen_fn=urlopen_fn
    )
    if text_extractor is None:
        extracted_text, extractor, extractor_stderr = extract_pdf_text(
            raw_pdf, timeout=extraction_timeout
        )
    else:
        extracted_text, extractor, extractor_stderr = text_extractor(raw_pdf)
    records = parse_record_book_staff_text(
        extracted_text,
        query,
        source_url=final_url,
        retrieved_at=retrieved_at,
    )
    return NflRecordBookSnapshot(
        query=query,
        retrieved_at=retrieved_at,
        source_url=final_url,
        raw_pdf=raw_pdf,
        extracted_text=extracted_text,
        records=records,
        response_last_modified=last_modified,
        response_etag=etag,
        extractor=extractor,
        extractor_stderr=extractor_stderr,
    )


def _csv_bytes(records: Iterable[HistoricalStaffRecord]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=STAFF_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(record.to_row() for record in records)
    return stream.getvalue().encode("utf-8")


def _coverage(records: Iterable[HistoricalStaffRecord]) -> dict[str, object]:
    items = tuple(records)
    categories = {
        category for record in items for category in record.responsibility_categories
    }
    return {
        "record_count": len(items),
        "offensive_record_count": sum(record.side == "offense" for record in items),
        "head_coach": next(
            (record.name for record in items if record.side == "head_coach"), None
        ),
        "offensive_coordinator_title_holders": [
            record.name
            for record in items
            if "offensive_coordinator" in record.responsibility_categories
        ],
        "responsibility_coverage": {
            category: category in categories for category in REQUIRED_OFFENSIVE_CATEGORIES
        },
        "missing_responsibilities": [
            category for category in REQUIRED_OFFENSIVE_CATEGORIES if category not in categories
        ],
    }


def write_nfl_record_book_snapshot(
    snapshot: NflRecordBookSnapshot,
    root: str | Path,
) -> Path:
    """Atomically publish the exact PDF, extracted text, staff tables, and hashes."""

    timestamp = snapshot.retrieved_at.strftime("%Y%m%dT%H%M%S.%fZ")
    parent = (
        Path(root)
        / SOURCE_ID
        / str(snapshot.query.season)
        / snapshot.query.label
    )
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"record-book snapshot already exists: {destination}")

    staff_csv = _csv_bytes(snapshot.records)
    offensive_records = tuple(
        record
        for record in snapshot.records
        if record.side in {"head_coach", "offense"}
    )
    offensive_csv = _csv_bytes(offensive_records)
    extracted_bytes = snapshot.extracted_text.encode("utf-8")
    by_team = {
        team: tuple(record for record in snapshot.records if record.team == team)
        for team in snapshot.query.teams
    }
    coverage = {team: _coverage(records) for team, records in by_team.items()}
    manifest = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "source": {
            "id": SOURCE_ID,
            "name": SOURCE_NAME,
            "url": snapshot.source_url,
            "constraint": (
                "The record book establishes historical names and titles; actual "
                "play-calling responsibility still requires separate evidence."
            ),
        },
        "query": {
            "season": snapshot.query.season,
            "teams": list(snapshot.query.teams),
        },
        "retrieved_at": _iso_z(snapshot.retrieved_at),
        "http": {
            "last_modified": snapshot.response_last_modified,
            "etag": snapshot.response_etag,
        },
        "extraction": {
            "tool": snapshot.extractor,
            "stderr": snapshot.extractor_stderr,
            "text_sha256": hashlib.sha256(extracted_bytes).hexdigest(),
        },
        "quality": {
            "team_count": len(snapshot.query.teams),
            "record_count": len(snapshot.records),
            "offensive_record_count": sum(
                record.side == "offense" for record in snapshot.records
            ),
            "offensive_staff_record_count": len(offensive_records),
            "side_counts": dict(
                sorted(Counter(record.side for record in snapshot.records).items())
            ),
            "teams_missing_position_responsibilities": {
                team: item["missing_responsibilities"]
                for team, item in coverage.items()
                if item["missing_responsibilities"]
            },
        },
        "coverage": coverage,
        "artifacts": {
            "raw_pdf": {
                "path": "record_book.pdf",
                "bytes": len(snapshot.raw_pdf),
                "sha256": hashlib.sha256(snapshot.raw_pdf).hexdigest(),
            },
            "extracted_text": {
                "path": "record_book.txt",
                "bytes": len(extracted_bytes),
                "sha256": hashlib.sha256(extracted_bytes).hexdigest(),
            },
            "staff": {
                "path": "staff.csv",
                "bytes": len(staff_csv),
                "sha256": hashlib.sha256(staff_csv).hexdigest(),
                "fields": list(STAFF_FIELDS),
            },
            "offensive_staff": {
                "path": "offensive_staff.csv",
                "bytes": len(offensive_csv),
                "sha256": hashlib.sha256(offensive_csv).hexdigest(),
                "fields": list(STAFF_FIELDS),
            },
        },
    }

    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
    try:
        (staging / "record_book.pdf").write_bytes(snapshot.raw_pdf)
        (staging / "record_book.txt").write_bytes(extracted_bytes)
        (staging / "staff.csv").write_bytes(staff_csv)
        (staging / "offensive_staff.csv").write_bytes(offensive_csv)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
