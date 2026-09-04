"""Historical all-team offensive play-caller censuses from ESPN NFL Nation.

The sources are valuable because coordinator titles alone do not establish who
called plays.  The 2023 and 2024 articles were published before their seasons;
the September 2025 article was published after that season began.  The latter
may support later-season caller history, but must not leak into a preseason-2025
forecast backtest.
"""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .nfl_record_book import TEAM_NAMES


SOURCE_ID = "espn_nfl_playcallers"
SOURCE_NAME = "ESPN NFL Nation all-team play-caller census"
SOURCE_URLS: Mapping[int, str] = {
    2023: "https://www.espn.com/nfl/story/_/id/38108724/key-intel-all-32-nfl-playcallers-including-mike-mccarthy",
    2024: "https://www.espn.com/nfl/story/_/id/41018846/nfl-playcallers-32-teams-mike-mcdaniel-sean-mcvay-nathaniel-hackett",
    2025: "https://www.espn.com/nfl/story/_/id/46137832/nfl-playcallers-32-teams-mike-mcdaniel-sean-mcvay-brian-schottenheimer"
}
SOURCE_PUBLISHED_AT: Mapping[int, date] = {
    2023: date(2023, 8, 23),
    2024: date(2024, 8, 30),
    2025: date(2025, 9, 9),
}
TEMPORAL_USE_BY_SEASON: Mapping[int, str] = {
    2023: "preseason_identity_evidence",
    2024: "preseason_identity_evidence",
    2025: "historical_identity_only_not_preseason_backtest_evidence",
}
ADAPTER_VERSION = "1.0.1"
SNAPSHOT_SCHEMA_VERSION = "1.0.0"
MAX_HTML_BYTES = 5_000_000

TEAM_BY_NAME = {name.title(): team for team, name in TEAM_NAMES.items()}
TEAM_BY_NAME.update(
    {
        "Los Angeles Chargers": "LAC",
        "Los Angeles Rams": "LAR",
        "San Francisco 49ers": "SF",
    }
)

FIELDS = (
    "season",
    "team",
    "play_caller",
    "caller_title",
    "experience_text",
    "source_url",
    "published_at",
    "retrieved_at",
    "temporal_use",
)

H2_PATTERN = re.compile(r"<h2[^>]*>(.*?)</h2>", re.IGNORECASE | re.DOTALL)
P_PATTERN = re.compile(r"<p[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
TAG_PATTERN = re.compile(r"<[^>]+>")


class EspnPlaycallerSourceError(RuntimeError):
    """Raised when the ESPN page cannot provide a complete requested census."""


@dataclass(frozen=True)
class EspnPlaycallerQuery:
    season: int
    teams: tuple[str, ...] = tuple(TEAM_NAMES)

    def __post_init__(self) -> None:
        if self.season not in SOURCE_URLS:
            raise ValueError(f"no ESPN play-caller census configured for {self.season}")
        normalized = tuple(sorted(team.strip().upper() for team in self.teams))
        if not normalized:
            raise ValueError("at least one team is required")
        if len(set(normalized)) != len(normalized):
            raise ValueError("teams cannot contain duplicates")
        unknown = set(normalized) - set(TEAM_NAMES)
        if unknown:
            raise ValueError(f"unsupported teams: {', '.join(sorted(unknown))}")
        object.__setattr__(self, "teams", normalized)

    @property
    def label(self) -> str:
        return "all" if set(self.teams) == set(TEAM_NAMES) else "-".join(self.teams)


@dataclass(frozen=True)
class EspnPlaycallerRecord:
    season: int
    team: str
    play_caller: str
    caller_title: str
    experience_text: str
    source_url: str
    published_at: date
    retrieved_at: datetime

    def to_row(self) -> dict[str, str | int]:
        return {
            "season": self.season,
            "team": self.team,
            "play_caller": self.play_caller,
            "caller_title": self.caller_title,
            "experience_text": self.experience_text,
            "source_url": self.source_url,
            "published_at": self.published_at.isoformat(),
            "retrieved_at": _iso_z(self.retrieved_at),
            "temporal_use": TEMPORAL_USE_BY_SEASON[self.season],
        }


@dataclass(frozen=True)
class EspnPlaycallerSnapshot:
    query: EspnPlaycallerQuery
    retrieved_at: datetime
    source_url: str
    published_at: date
    raw_html: bytes
    records: tuple[EspnPlaycallerRecord, ...]
    response_last_modified: str | None = None
    response_etag: str | None = None


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    return value.astimezone(timezone.utc)


def _text(fragment: str) -> str:
    return " ".join(html.unescape(TAG_PATTERN.sub(" ", fragment)).split())


def parse_espn_playcallers(
    raw_html: bytes,
    query: EspnPlaycallerQuery,
    *,
    source_url: str,
    published_at: date,
    retrieved_at: datetime,
) -> tuple[EspnPlaycallerRecord, ...]:
    """Parse requested team sections and validate one explicit caller per team."""

    try:
        document = raw_html.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EspnPlaycallerSourceError("ESPN response is not UTF-8") from error
    headings = list(H2_PATTERN.finditer(document))
    found: dict[str, EspnPlaycallerRecord] = {}
    for index, heading in enumerate(headings):
        team_name = _text(heading.group(1))
        team = TEAM_BY_NAME.get(team_name)
        if team is None or team not in query.teams:
            continue
        stop = headings[index + 1].start() if index + 1 < len(headings) else len(document)
        paragraphs = [_text(item) for item in P_PATTERN.findall(document[heading.end():stop])]
        playcaller = next((item for item in paragraphs if item.startswith("Playcaller:")), None)
        experience = next((item for item in paragraphs if item.startswith("Experience:")), None)
        if playcaller is None or experience is None:
            raise EspnPlaycallerSourceError(f"{team} section lacks caller or experience text")
        value = playcaller.removeprefix("Playcaller:").strip()
        if "," not in value:
            raise EspnPlaycallerSourceError(f"{team} caller line lacks a title")
        name, title = (part.strip() for part in value.rsplit(",", 1))
        if not name or not title or team in found:
            raise EspnPlaycallerSourceError(f"{team} caller section is blank or duplicated")
        found[team] = EspnPlaycallerRecord(
            season=query.season,
            team=team,
            play_caller=name,
            caller_title=title,
            experience_text=experience.removeprefix("Experience:").strip(),
            source_url=source_url,
            published_at=published_at,
            retrieved_at=_utc(retrieved_at),
        )
    missing = set(query.teams) - set(found)
    if missing:
        raise EspnPlaycallerSourceError(
            f"ESPN play-caller census is missing: {', '.join(sorted(missing))}"
        )
    return tuple(found[team] for team in sorted(found))


def fetch_espn_playcallers(
    query: EspnPlaycallerQuery,
    *,
    timeout: float = 30.0,
    retrieved_at: datetime | None = None,
    urlopen_fn: Callable[..., Any] = urlopen,
) -> EspnPlaycallerSnapshot:
    if timeout <= 0:
        raise ValueError("HTTP timeout must be positive")
    retrieved_at = _utc(retrieved_at or datetime.now(timezone.utc))
    url = SOURCE_URLS[query.season]
    request = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "Mozilla/5.0 (compatible; fantasy-football-26/0.1; personal research)",
        },
    )
    try:
        with urlopen_fn(request, timeout=timeout) as response:
            raw = response.read(MAX_HTML_BYTES + 1)
            final_url = response.geturl() if hasattr(response, "geturl") else url
            last_modified = response.headers.get("Last-Modified")
            etag = response.headers.get("ETag")
    except HTTPError as error:
        raise EspnPlaycallerSourceError(f"ESPN returned HTTP {error.code}: {url}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise EspnPlaycallerSourceError(f"could not fetch ESPN census: {error}") from error
    if len(raw) > MAX_HTML_BYTES:
        raise EspnPlaycallerSourceError(f"ESPN response exceeded {MAX_HTML_BYTES:,} bytes")
    records = parse_espn_playcallers(
        raw,
        query,
        source_url=final_url,
        published_at=SOURCE_PUBLISHED_AT[query.season],
        retrieved_at=retrieved_at,
    )
    return EspnPlaycallerSnapshot(
        query=query,
        retrieved_at=retrieved_at,
        source_url=final_url,
        published_at=SOURCE_PUBLISHED_AT[query.season],
        raw_html=raw,
        records=records,
        response_last_modified=last_modified,
        response_etag=etag,
    )


def _csv_bytes(records: Iterable[EspnPlaycallerRecord]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(record.to_row() for record in records)
    return stream.getvalue().encode("utf-8")


def write_espn_playcaller_snapshot(
    snapshot: EspnPlaycallerSnapshot, root: str | Path
) -> Path:
    timestamp = snapshot.retrieved_at.strftime("%Y%m%dT%H%M%S.%fZ")
    parent = Path(root) / SOURCE_ID / str(snapshot.query.season) / snapshot.query.label
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"ESPN caller snapshot already exists: {destination}")
    callers_csv = _csv_bytes(snapshot.records)
    manifest = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "source": {
            "id": SOURCE_ID,
            "name": SOURCE_NAME,
            "url": snapshot.source_url,
            "published_at": snapshot.published_at.isoformat(),
            "source_type": "credentialed_national",
        },
        "query": {"season": snapshot.query.season, "teams": list(snapshot.query.teams)},
        "retrieved_at": _iso_z(snapshot.retrieved_at),
        "temporal_use": {
            "classification": snapshot.records[0].to_row()["temporal_use"],
            "allowed": "Historical caller identity and experience evidence for later seasons.",
            "forbidden": (
                "Preseason forecast input for this season because publication followed the start of its regular season."
                if TEMPORAL_USE_BY_SEASON[snapshot.query.season]
                == "historical_identity_only_not_preseason_backtest_evidence"
                else None
            ),
        },
        "http": {"last_modified": snapshot.response_last_modified, "etag": snapshot.response_etag},
        "quality": {"team_count": len(snapshot.records), "unique_caller_count": len({item.play_caller for item in snapshot.records})},
        "artifacts": {
            "raw_html": {"path": "article.html", "bytes": len(snapshot.raw_html), "sha256": hashlib.sha256(snapshot.raw_html).hexdigest()},
            "callers": {"path": "callers.csv", "bytes": len(callers_csv), "sha256": hashlib.sha256(callers_csv).hexdigest(), "fields": list(FIELDS)},
        },
    }
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
    try:
        (staging / "article.html").write_bytes(snapshot.raw_html)
        (staging / "callers.csv").write_bytes(callers_csv)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
