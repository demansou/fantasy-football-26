"""Google News RSS discovery for current NFL offensive-environment research.

RSS results are a coverage and freshness queue, not model-ready evidence.  A
headline's tone is never converted directly into a football adjustment.  Each
article must first become a narrow, sourced claim about responsibility, scheme,
formation, role, injury, or personnel usage.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .nfl_record_book import TEAM_NAMES


SOURCE_ID = "google_news_nfl_environment"
SOURCE_NAME = "Google News RSS search"
SOURCE_BASE_URL = "https://news.google.com/rss/search"
ADAPTER_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"
MAX_XML_BYTES = 2_000_000

FIELDS = (
    "season",
    "team",
    "query",
    "play_caller",
    "published_at",
    "headline",
    "publisher",
    "publisher_url",
    "google_news_url",
    "guid",
    "topic_hints",
    "retrieved_at",
    "research_status",
    "sentiment_used",
)

TOPIC_PATTERNS: Mapping[str, re.Pattern[str]] = {
    "play_calling": re.compile(
        r"\b(play.?call(?:er|ing)?|call(?:ing|s)? plays?|coordinator)\b", re.I
    ),
    "scheme_style": re.compile(r"\b(scheme|system|offense|tempo|motion|formation|play.?action|rpo)\b", re.I),
    "offensive_line": re.compile(r"\b(offensive line|o-line|lineman|guard|tackle|center)\b", re.I),
    "injury_availability": re.compile(r"\b(injur|recover|return|absen|questionable|pup|reserve)\w*\b", re.I),
    "role_usage": re.compile(r"\b(starter|starting|depth chart|rotation|snaps?|targets?|carries|routes?)\b", re.I),
    "quarterback": re.compile(r"\b(quarterback|\bqb\b)\b", re.I),
    "running_back": re.compile(r"\b(running back|\brb\b|backfield)\b", re.I),
    "receiver_tight_end": re.compile(r"\b(receiver|wideout|tight end|\bwr\b|\bte\b)\b", re.I),
}


class GoogleNewsSourceError(RuntimeError):
    """Raised when the news-discovery source violates its data contract."""


@dataclass(frozen=True)
class GoogleNewsQuery:
    season: int
    teams: tuple[str, ...] = tuple(TEAM_NAMES)
    lookback_days: int = 45
    max_articles_per_team: int = 25

    def __post_init__(self) -> None:
        if isinstance(self.season, bool) or not isinstance(self.season, int):
            raise ValueError("season must be an integer")
        normalized = tuple(sorted(team.strip().upper() for team in self.teams))
        if not normalized or len(set(normalized)) != len(normalized):
            raise ValueError("teams must be non-empty and unique")
        unknown = set(normalized) - set(TEAM_NAMES)
        if unknown:
            raise ValueError(f"unsupported teams: {', '.join(sorted(unknown))}")
        if not 1 <= self.lookback_days <= 365:
            raise ValueError("lookback_days must be between 1 and 365")
        if not 1 <= self.max_articles_per_team <= 100:
            raise ValueError("max_articles_per_team must be between 1 and 100")
        object.__setattr__(self, "teams", normalized)

    @property
    def label(self) -> str:
        return "all" if set(self.teams) == set(TEAM_NAMES) else "-".join(self.teams)


@dataclass(frozen=True)
class GoogleNewsArticle:
    season: int
    team: str
    query: str
    play_caller: str
    published_at: datetime
    headline: str
    publisher: str
    publisher_url: str
    google_news_url: str
    guid: str
    topic_hints: tuple[str, ...]
    retrieved_at: datetime

    def to_row(self) -> dict[str, str | int]:
        return {
            "season": self.season,
            "team": self.team,
            "query": self.query,
            "play_caller": self.play_caller,
            "published_at": _iso_z(self.published_at),
            "headline": self.headline,
            "publisher": self.publisher,
            "publisher_url": self.publisher_url,
            "google_news_url": self.google_news_url,
            "guid": self.guid,
            "topic_hints": "|".join(self.topic_hints),
            "retrieved_at": _iso_z(self.retrieved_at),
            "research_status": "metadata_only_unreviewed_not_model_evidence",
            "sentiment_used": "false",
        }


@dataclass(frozen=True)
class GoogleNewsSnapshot:
    query: GoogleNewsQuery
    retrieved_at: datetime
    callers: Mapping[str, str]
    search_queries: Mapping[str, str]
    raw_xml: Mapping[str, bytes]
    articles: tuple[GoogleNewsArticle, ...]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(timezone.utc)


def _iso_z(value: datetime) -> str:
    return _utc(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_current_callers(path: str | Path) -> tuple[int, dict[str, str]]:
    resolved = Path(path)
    if resolved.is_dir():
        resolved = resolved / "teams.csv"
    if not resolved.is_file():
        raise GoogleNewsSourceError(f"caller census does not exist: {resolved}")
    try:
        rows = list(csv.DictReader(io.StringIO(resolved.read_text(encoding="utf-8"))))
    except UnicodeDecodeError as error:
        raise GoogleNewsSourceError(f"caller census is not UTF-8: {resolved}") from error
    required = {"season", "team", "play_caller"}
    if not rows or not required.issubset(rows[0]):
        raise GoogleNewsSourceError("caller census has no rows or required fields")
    try:
        seasons = {int(row["season"]) for row in rows}
    except ValueError as error:
        raise GoogleNewsSourceError("caller census season is invalid") from error
    if len(seasons) != 1:
        raise GoogleNewsSourceError("caller census must contain exactly one season")
    callers: dict[str, str] = {}
    for row in rows:
        team = row["team"].strip().upper()
        caller = row["play_caller"].strip()
        if not team or not caller or team in callers:
            raise GoogleNewsSourceError("caller census has a blank or duplicate team")
        callers[team] = caller
    return seasons.pop(), callers


def build_search_query(team: str, play_caller: str, lookback_days: int) -> str:
    team_name = TEAM_NAMES[team].title()
    return (
        f'"{team_name}" ("{play_caller}" OR "offensive coordinator" OR '
        f'"play caller" OR offense) when:{lookback_days}d'
    )


def build_search_url(query: str) -> str:
    return f"{SOURCE_BASE_URL}?{urlencode({'q': query, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})}"


def _topic_hints(headline: str) -> tuple[str, ...]:
    return tuple(name for name, pattern in TOPIC_PATTERNS.items() if pattern.search(headline))


def parse_google_news_rss(
    raw_xml: bytes,
    *,
    season: int,
    team: str,
    query: str,
    play_caller: str,
    retrieved_at: datetime,
    max_articles: int,
) -> tuple[GoogleNewsArticle, ...]:
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as error:
        raise GoogleNewsSourceError(f"{team} Google News response is invalid XML") from error
    items = root.findall("./channel/item")
    articles: list[GoogleNewsArticle] = []
    seen: set[str] = set()
    for item in items:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or link).strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        source = item.find("source")
        publisher = "" if source is None or source.text is None else source.text.strip()
        publisher_url = "" if source is None else (source.attrib.get("url") or "").strip()
        if not title or not link or not guid or not pub_date or not publisher:
            continue
        if guid in seen:
            continue
        try:
            published_at = parsedate_to_datetime(pub_date)
        except (TypeError, ValueError) as error:
            raise GoogleNewsSourceError(f"{team} article has invalid pubDate") from error
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        seen.add(guid)
        articles.append(
            GoogleNewsArticle(
                season=season,
                team=team,
                query=query,
                play_caller=play_caller,
                published_at=_utc(published_at),
                headline=title,
                publisher=publisher,
                publisher_url=publisher_url,
                google_news_url=link,
                guid=guid,
                topic_hints=_topic_hints(title),
                retrieved_at=_utc(retrieved_at),
            )
        )
        if len(articles) >= max_articles:
            break
    return tuple(articles)


def _download(
    url: str,
    *,
    timeout: float,
    urlopen_fn: Callable[..., Any],
) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/rss+xml, application/xml, text/xml",
            "User-Agent": "Mozilla/5.0 (compatible; fantasy-football-26/0.1; personal research)",
        },
    )
    try:
        with urlopen_fn(request, timeout=timeout) as response:
            body = response.read(MAX_XML_BYTES + 1)
    except HTTPError as error:
        raise GoogleNewsSourceError(f"Google News returned HTTP {error.code}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise GoogleNewsSourceError(f"could not fetch Google News RSS: {error}") from error
    if not body:
        raise GoogleNewsSourceError("Google News returned an empty response")
    if len(body) > MAX_XML_BYTES:
        raise GoogleNewsSourceError(f"Google News response exceeded {MAX_XML_BYTES:,} bytes")
    return body


def fetch_google_news(
    query: GoogleNewsQuery,
    callers: Mapping[str, str],
    *,
    timeout: float = 30.0,
    retrieved_at: datetime | None = None,
    urlopen_fn: Callable[..., Any] = urlopen,
    workers: int = 8,
) -> GoogleNewsSnapshot:
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if workers < 1:
        raise ValueError("workers must be positive")
    missing = set(query.teams) - set(callers)
    if missing:
        raise GoogleNewsSourceError(f"caller map is missing: {', '.join(sorted(missing))}")
    retrieved_at = _utc(retrieved_at or datetime.now(timezone.utc))
    search_queries = {
        team: build_search_query(team, callers[team], query.lookback_days)
        for team in query.teams
    }
    raw_xml: dict[str, bytes] = {}
    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(workers, len(query.teams))) as executor:
        futures = {
            executor.submit(
                _download,
                build_search_url(search_queries[team]),
                timeout=timeout,
                urlopen_fn=urlopen_fn,
            ): team
            for team in query.teams
        }
        for future in as_completed(futures):
            team = futures[future]
            try:
                raw_xml[team] = future.result()
            except GoogleNewsSourceError as error:
                failures[team] = str(error)
    if failures:
        details = "; ".join(f"{team}: {message}" for team, message in sorted(failures.items()))
        raise GoogleNewsSourceError(f"news discovery failed closed: {details}")

    articles: list[GoogleNewsArticle] = []
    for team in query.teams:
        articles.extend(
            parse_google_news_rss(
                raw_xml[team],
                season=query.season,
                team=team,
                query=search_queries[team],
                play_caller=callers[team],
                retrieved_at=retrieved_at,
                max_articles=query.max_articles_per_team,
            )
        )
    return GoogleNewsSnapshot(
        query=query,
        retrieved_at=retrieved_at,
        callers={team: callers[team] for team in query.teams},
        search_queries=search_queries,
        raw_xml=raw_xml,
        articles=tuple(sorted(articles, key=lambda item: (item.team, -item.published_at.timestamp(), item.headline))),
    )


def _csv_bytes(articles: Iterable[GoogleNewsArticle]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(article.to_row() for article in articles)
    return stream.getvalue().encode("utf-8")


def write_google_news_snapshot(snapshot: GoogleNewsSnapshot, root: str | Path) -> Path:
    timestamp = snapshot.retrieved_at.strftime("%Y%m%dT%H%M%S.%fZ")
    parent = Path(root) / SOURCE_ID / str(snapshot.query.season) / snapshot.query.label
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"Google News snapshot already exists: {destination}")
    articles_csv = _csv_bytes(snapshot.articles)
    counts = {
        team: sum(article.team == team for article in snapshot.articles)
        for team in snapshot.query.teams
    }
    raw_artifacts = {
        f"{team}.xml": {
            "bytes": len(snapshot.raw_xml[team]),
            "sha256": hashlib.sha256(snapshot.raw_xml[team]).hexdigest(),
            "query": snapshot.search_queries[team],
            "url": build_search_url(snapshot.search_queries[team]),
        }
        for team in snapshot.query.teams
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "source": {
            "id": SOURCE_ID,
            "name": SOURCE_NAME,
            "base_url": SOURCE_BASE_URL,
            "source_role": "discovery_metadata_only",
        },
        "query": {
            "season": snapshot.query.season,
            "teams": list(snapshot.query.teams),
            "lookback_days": snapshot.query.lookback_days,
            "max_articles_per_team": snapshot.query.max_articles_per_team,
            "play_callers": dict(snapshot.callers),
        },
        "retrieved_at": _iso_z(snapshot.retrieved_at),
        "methodology": {
            "allowed": "Use article metadata to create a coverage queue and locate candidate sources for structured claims.",
            "forbidden": "Do not treat headline tone, result rank, or publisher repetition as a style or player projection signal.",
            "promotion_gate": "Read the underlying article and encode a narrow sourced claim before model use.",
        },
        "quality": {
            "team_count": len(snapshot.query.teams),
            "article_count": len(snapshot.articles),
            "articles_per_team": counts,
            "teams_without_results": [team for team, count in counts.items() if count == 0],
        },
        "artifacts": {
            "articles.csv": {
                "bytes": len(articles_csv),
                "sha256": hashlib.sha256(articles_csv).hexdigest(),
                "fields": list(FIELDS),
            },
            "raw": raw_artifacts,
        },
    }
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
    try:
        (staging / "raw").mkdir()
        (staging / "articles.csv").write_bytes(articles_csv)
        for team, payload in snapshot.raw_xml.items():
            (staging / "raw" / f"{team}.xml").write_bytes(payload)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
