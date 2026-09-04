"""Current coaching-staff ingestion from official NFL club websites.

Official staff pages establish names and titles.  They do not, by themselves,
establish who calls plays, so this adapter never infers that responsibility from
an offensive-coordinator title.
"""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


SOURCE_ID = "official_nfl_club_staff"
SOURCE_NAME = "Official NFL club coaching pages"
ADAPTER_VERSION = "1.0.0"
SNAPSHOT_SCHEMA_VERSION = "1.0.0"
MAX_PAGE_BYTES = 3_000_000

OFFICIAL_STAFF_URLS: Mapping[str, str] = {
    "ARI": "https://www.azcardinals.com/team/coaches-roster/",
    "ATL": "https://www.atlantafalcons.com/team/coaches-roster/",
    "BAL": "https://www.baltimoreravens.com/team/coaches-roster/",
    "BUF": "https://www.buffalobills.com/team/coaches-roster/",
    "CAR": "https://www.panthers.com/team/coaches-roster/",
    "CHI": "https://www.chicagobears.com/team/coaches/",
    "CIN": "https://www.bengals.com/team/coaches-roster/",
    "CLE": "https://www.clevelandbrowns.com/team/coaches-roster/",
    "DAL": "https://www.dallascowboys.com/team/coaches-roster/",
    "DEN": "https://www.denverbroncos.com/team/coaches-roster/",
    "DET": "https://www.detroitlions.com/team/coaches-roster/",
    "GB": "https://www.packers.com/team/coaches-roster/",
    "HOU": "https://www.houstontexans.com/team/coaches-roster/",
    "IND": "https://www.colts.com/team/coaches-roster/",
    "JAX": "https://www.jaguars.com/team/coaches-roster/",
    "KC": "https://www.chiefs.com/team/coaches-roster/",
    "LV": "https://www.raiders.com/team/coaches-roster/",
    "LAC": "https://www.chargers.com/team/coaches-roster/",
    "LAR": "https://www.therams.com/team/coaches-roster/",
    "MIA": "https://www.miamidolphins.com/team/coaches-roster/",
    "MIN": "https://www.vikings.com/team/coaches-roster/",
    "NE": "https://www.patriots.com/team/coaches-roster/",
    "NO": "https://www.neworleanssaints.com/team/coaches-roster/",
    "NYG": "https://www.giants.com/team/coaches-roster/",
    "NYJ": "https://www.newyorkjets.com/team/coaches-roster/",
    "PHI": "https://www.philadelphiaeagles.com/team/coaches/",
    "PIT": "https://www.steelers.com/team/coaches-roster/",
    "SEA": "https://www.seahawks.com/team/coaches-roster/",
    "SF": "https://www.49ers.com/team/coaches-roster/",
    "TB": "https://www.buccaneers.com/team/coaches-roster/",
    "TEN": "https://www.tennesseetitans.com/team/coaches-roster/",
    "WAS": "https://www.commanders.com/team/coaches-roster/",
}

STAFF_FIELDS = (
    "season",
    "team",
    "name",
    "role",
    "side",
    "responsibility_categories",
    "profile_url",
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


class OfficialStaffSourceError(RuntimeError):
    """Raised when an official staff page cannot satisfy the adapter contract."""


@dataclass(frozen=True)
class OfficialStaffQuery:
    season: int
    teams: tuple[str, ...] = tuple(OFFICIAL_STAFF_URLS)

    def __post_init__(self) -> None:
        if isinstance(self.season, bool) or not isinstance(self.season, int):
            raise ValueError("staff season must be an integer")
        if not 2000 <= self.season <= 2100:
            raise ValueError("staff season must be between 2000 and 2100")
        normalized = tuple(sorted(team.strip().upper() for team in self.teams))
        if not normalized:
            raise ValueError("at least one staff team is required")
        if len(set(normalized)) != len(normalized):
            raise ValueError("staff teams cannot contain duplicates")
        unknown = set(normalized) - set(OFFICIAL_STAFF_URLS)
        if unknown:
            raise ValueError(f"unsupported staff teams: {', '.join(sorted(unknown))}")
        object.__setattr__(self, "teams", normalized)

    @property
    def label(self) -> str:
        return "all" if set(self.teams) == set(OFFICIAL_STAFF_URLS) else "-".join(self.teams)


@dataclass(frozen=True)
class OfficialStaffPage:
    team: str
    url: str
    raw_bytes: bytes
    response_last_modified: str | None = None
    response_etag: str | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw_bytes).hexdigest()


@dataclass(frozen=True)
class OfficialStaffRecord:
    season: int
    team: str
    name: str
    role: str
    side: str
    responsibility_categories: tuple[str, ...]
    profile_url: str
    source_url: str
    retrieved_at: datetime

    def to_row(self) -> dict[str, str | int]:
        return {
            "season": self.season,
            "team": self.team,
            "name": self.name,
            "role": self.role,
            "side": self.side,
            "responsibility_categories": "|".join(self.responsibility_categories),
            "profile_url": self.profile_url,
            "source_url": self.source_url,
            "retrieved_at": _iso_z(self.retrieved_at),
        }


@dataclass(frozen=True)
class OfficialStaffSnapshot:
    query: OfficialStaffQuery
    retrieved_at: datetime
    pages: tuple[OfficialStaffPage, ...]
    records: tuple[OfficialStaffRecord, ...]


class _CoachCardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[tuple[str, str, str]] = []
        self._in_card = False
        self._container_tag: str | None = None
        self._container_depth = 0
        self._href = ""
        self._capture: str | None = None
        self._role_parts: list[str] = []
        self._name_parts: list[str] = []

    @staticmethod
    def _attributes(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key: value or "" for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = self._attributes(attrs)
        classes = values.get("class", "")
        href = values.get("href", "")
        is_link_card = tag == "a" and (
            "person-card" in classes
            or ("/team/coaches" in href and "aria-label" in values)
        )
        is_div_card = tag == "div" and (
            "d3-o-person-card--non-featured" in classes
            or "d3-o-person-card--featured" in classes
            or "d3-o-media-object--featured" in classes
        )
        if not self._in_card and (is_link_card or is_div_card):
            self._in_card = True
            self._container_tag = tag
            self._container_depth = 1
            self._href = href
            self._role_parts = []
            self._name_parts = []
            return
        if not self._in_card:
            return
        if tag == self._container_tag:
            self._container_depth += 1
        if tag == "a" and "/team/coaches" in href:
            self._href = href
        if tag in {"h4", "h5", "p"} and (
            "roofline" in classes or "position" in classes or "role" in classes
        ):
            self._capture = "role"
        elif tag in {"h2", "h3", "h4"} and (
            "title" in classes or "name" in classes
        ):
            self._capture = "name"

    def handle_endtag(self, tag: str) -> None:
        if not self._in_card:
            return
        if tag in {"h2", "h3", "h4", "h5", "p"}:
            self._capture = None
        if tag == self._container_tag:
            self._container_depth -= 1
            if self._container_depth == 0:
                self._finish_card()

    def _finish_card(self) -> None:
        role = " ".join("".join(self._role_parts).split())
        name = " ".join("".join(self._name_parts).split())
        if role and name:
            self.cards.append((html.unescape(role), html.unescape(name), self._href))
        self._in_card = False
        self._container_tag = None
        self._container_depth = 0
        self._href = ""
        self._capture = None

    def handle_data(self, data: str) -> None:
        if self._capture == "role":
            self._role_parts.append(data)
        elif self._capture == "name":
            self._name_parts.append(data)


def _normalize_role(role: str) -> str:
    return " ".join(html.unescape(role).replace("\u00a0", " ").split())


def _side(role: str) -> str:
    lowered = role.lower()
    if lowered == "head coach" or lowered.startswith(
        ("head coach/", "head coach &", "head coach and ")
    ):
        return "head_coach"
    if any(word in lowered for word in ("defensive", "defense", "lineback", "secondary")):
        return "defense"
    if any(word in lowered for word in ("special teams", "kicking", "punter", "return game")):
        return "special_teams"
    if any(word in lowered for word in ("strength", "performance", "conditioning")):
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
    if "assistant" in lowered or "quality control" in lowered or "analyst" in lowered:
        categories.add("offensive_assistant")
    return tuple(sorted(categories))


def _utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    return value.astimezone(timezone.utc)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def parse_official_staff_page(
    team: str,
    raw_bytes: bytes,
    *,
    season: int,
    source_url: str,
    retrieved_at: datetime,
) -> tuple[OfficialStaffRecord, ...]:
    """Extract name/title facts from one official club coaching page."""

    team = team.strip().upper()
    if team not in OFFICIAL_STAFF_URLS:
        raise ValueError(f"unsupported staff team {team!r}")
    retrieved_at = _utc_timestamp(retrieved_at)
    try:
        page = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise OfficialStaffSourceError(f"{team} staff page is not UTF-8") from error
    parser = _CoachCardParser()
    parser.feed(page)
    records: list[OfficialStaffRecord] = []
    seen: set[tuple[str, str]] = set()
    for role, name, href in parser.cards:
        role = _normalize_role(role)
        name = " ".join(name.split())
        key = (name.casefold(), role.casefold())
        if key in seen:
            continue
        seen.add(key)
        side = _side(role)
        records.append(
            OfficialStaffRecord(
                season=season,
                team=team,
                name=name,
                role=role,
                side=side,
                responsibility_categories=_categories(role, side),
                profile_url=urljoin(source_url, href) if href else "",
                source_url=source_url,
                retrieved_at=retrieved_at,
            )
        )
    if len(records) < 5:
        raise OfficialStaffSourceError(
            f"{team} official staff page yielded only {len(records)} coach records"
        )
    head_coaches = [record for record in records if record.side == "head_coach"]
    if len(head_coaches) != 1:
        raise OfficialStaffSourceError(
            f"{team} official staff page yielded {len(head_coaches)} head coaches"
        )
    return tuple(sorted(records, key=lambda item: (item.side, item.role, item.name)))


def _download_page(
    team: str,
    url: str,
    *,
    timeout: float,
    urlopen_fn: Callable[..., Any],
) -> OfficialStaffPage:
    request = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "fantasy-football-26/0.1 (+source-attributed personal research)",
        },
    )
    try:
        with urlopen_fn(request, timeout=timeout) as response:
            body = response.read(MAX_PAGE_BYTES + 1)
            final_url = response.geturl() if hasattr(response, "geturl") else url
            last_modified = response.headers.get("Last-Modified")
            etag = response.headers.get("ETag")
    except HTTPError as error:
        raise OfficialStaffSourceError(
            f"{team} official staff page returned HTTP {error.code}: {url}"
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        raise OfficialStaffSourceError(
            f"could not fetch {team} official staff page {url}: {error}"
        ) from error
    if len(body) > MAX_PAGE_BYTES:
        raise OfficialStaffSourceError(
            f"{team} official staff page exceeded {MAX_PAGE_BYTES:,} bytes"
        )
    if not body:
        raise OfficialStaffSourceError(f"{team} official staff page was empty")
    return OfficialStaffPage(
        team=team,
        url=final_url,
        raw_bytes=body,
        response_last_modified=last_modified,
        response_etag=etag,
    )


def fetch_official_staff(
    query: OfficialStaffQuery,
    *,
    timeout: float = 30.0,
    retrieved_at: datetime | None = None,
    urlopen_fn: Callable[..., Any] = urlopen,
) -> OfficialStaffSnapshot:
    """Fetch and validate official coaching pages for the requested teams."""

    if timeout <= 0:
        raise ValueError("staff timeout must be positive")
    retrieved_at = _utc_timestamp(retrieved_at or datetime.now(timezone.utc))
    pages: list[OfficialStaffPage] = []
    records: list[OfficialStaffRecord] = []
    for team in query.teams:
        page = _download_page(
            team,
            OFFICIAL_STAFF_URLS[team],
            timeout=timeout,
            urlopen_fn=urlopen_fn,
        )
        pages.append(page)
        records.extend(
            parse_official_staff_page(
                team,
                page.raw_bytes,
                season=query.season,
                source_url=page.url,
                retrieved_at=retrieved_at,
            )
        )
    return OfficialStaffSnapshot(
        query=query,
        retrieved_at=retrieved_at,
        pages=tuple(sorted(pages, key=lambda item: item.team)),
        records=tuple(sorted(records, key=lambda item: (item.team, item.side, item.role, item.name))),
    )


def _csv_bytes(records: Iterable[OfficialStaffRecord]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=STAFF_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(record.to_row() for record in records)
    return stream.getvalue().encode("utf-8")


def _team_coverage(records: Iterable[OfficialStaffRecord]) -> dict[str, object]:
    items = tuple(records)
    categories = {
        category
        for record in items
        for category in record.responsibility_categories
    }
    offensive_coordinator_records = [
        record
        for record in items
        if "offensive_coordinator" in record.responsibility_categories
    ]
    primary_offensive_coordinators = [
        record
        for record in offensive_coordinator_records
        if "assistant offensive coordinator" not in record.role.lower()
    ]
    return {
        "record_count": len(items),
        "offensive_record_count": sum(record.side == "offense" for record in items),
        "head_coach": next(
            (record.name for record in items if record.side == "head_coach"), None
        ),
        "offensive_coordinator_title_holders": [
            record.name for record in offensive_coordinator_records
        ],
        "primary_offensive_coordinators": [
            record.name for record in primary_offensive_coordinators
        ],
        "responsibility_coverage": {
            category: category in categories for category in REQUIRED_OFFENSIVE_CATEGORIES
        },
        "missing_responsibilities": [
            category for category in REQUIRED_OFFENSIVE_CATEGORIES if category not in categories
        ],
    }


def write_official_staff_snapshot(
    snapshot: OfficialStaffSnapshot,
    root: str | Path,
) -> Path:
    """Atomically publish raw pages, normalized staff tables, and coverage."""

    root = Path(root)
    timestamp = snapshot.retrieved_at.strftime("%Y%m%dT%H%M%S.%fZ")
    parent = root / SOURCE_ID / str(snapshot.query.season) / snapshot.query.label
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"official staff snapshot already exists: {destination}")

    staff_csv = _csv_bytes(snapshot.records)
    offensive_staff_records = [
        record for record in snapshot.records if record.side in {"head_coach", "offense"}
    ]
    offensive_csv = _csv_bytes(offensive_staff_records)
    records_by_team: dict[str, list[OfficialStaffRecord]] = {
        team: [record for record in snapshot.records if record.team == team]
        for team in snapshot.query.teams
    }
    coverage = {
        team: _team_coverage(records) for team, records in records_by_team.items()
    }
    pages = {
        f"{page.team}.html": {
            "path": f"raw/{page.team}.html",
            "team": page.team,
            "url": page.url,
            "bytes": len(page.raw_bytes),
            "sha256": page.sha256,
            "http": {
                "last_modified": page.response_last_modified,
                "etag": page.response_etag,
            },
        }
        for page in snapshot.pages
    }
    manifest = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "source": {
            "id": SOURCE_ID,
            "name": SOURCE_NAME,
            "constraint": (
                "Names/titles are official; actual play-calling responsibility is not inferred."
            ),
        },
        "query": {"season": snapshot.query.season, "teams": list(snapshot.query.teams)},
        "retrieved_at": _iso_z(snapshot.retrieved_at),
        "quality": {
            "team_count": len(snapshot.query.teams),
            "record_count": len(snapshot.records),
            "offensive_record_count": sum(
                record.side == "offense" for record in snapshot.records
            ),
            "offensive_staff_record_count": len(offensive_staff_records),
            "side_counts": dict(sorted(Counter(record.side for record in snapshot.records).items())),
            "teams_missing_offensive_coordinator_title": [
                team
                for team, item in coverage.items()
                if not item["primary_offensive_coordinators"]
            ],
            "teams_missing_position_responsibilities": {
                team: item["missing_responsibilities"]
                for team, item in coverage.items()
                if item["missing_responsibilities"]
            },
        },
        "coverage": coverage,
        "artifacts": {
            "raw_pages": pages,
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
        raw_directory = staging / "raw"
        raw_directory.mkdir()
        for page in snapshot.pages:
            (raw_directory / f"{page.team}.html").write_bytes(page.raw_bytes)
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
