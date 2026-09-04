"""Validate and publish researched historical offensive play-caller evidence.

Some seasons do not have a machine-readable, preseason all-team census.  This
module turns a source-dated, human-reviewed evidence registry into the same
``callers.csv`` contract used by the transition backtest.  The registry may
preserve an unresolved assignment; it must never resolve one with hindsight.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from .sources.nfl_record_book import TEAM_NAMES


REGISTRY_SCHEMA_VERSION = "1.0.0"
SNAPSHOT_SCHEMA_VERSION = "1.0.0"
MODEL_VERSION = "researched-playcaller-evidence-v0.1.0"

IDENTITY_STATUSES = {"confirmed", "ambiguous"}
TEMPORAL_USES = {
    "preseason_identity_evidence",
    "historical_identity_evidence_for_later_seasons_only",
}
SOURCE_TYPES = {
    "official_team",
    "official_league",
    "credentialed_national",
    "credentialed_local",
}

CALLER_FIELDS = (
    "season",
    "team",
    "play_caller",
    "identity_status",
    "candidate_callers",
    "source_id",
    "source_url",
    "source_locator",
    "published_at",
    "researched_at",
    "temporal_use",
    "evidence_summary",
)

SOURCE_FIELDS = (
    "source_id",
    "title",
    "publisher",
    "source_type",
    "url",
    "published_at",
    "accessed_at",
    "locator",
    "content_sha256",
    "content_hash_scope",
)


class PlaycallerEvidenceDataError(ValueError):
    """Raised when a researched caller registry violates its evidence contract."""


@dataclass(frozen=True)
class EvidenceSource:
    source_id: str
    title: str
    publisher: str
    source_type: str
    url: str
    published_at: date
    accessed_at: date
    locator: str
    content_sha256: str
    content_hash_scope: str


@dataclass(frozen=True)
class EvidenceTeam:
    team: str
    identity_status: str
    play_caller: str
    candidate_callers: tuple[str, ...]
    source_ids: tuple[str, ...]
    evidence_summary: str


@dataclass(frozen=True)
class PlaycallerEvidenceRegistry:
    season: int
    as_of: date
    temporal_use: str
    forecast_evidence_cutoff: date | None
    methodology: Mapping[str, Any]
    sources: Mapping[str, EvidenceSource]
    teams: tuple[EvidenceTeam, ...]
    raw: bytes


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PlaycallerEvidenceDataError(f"{context} must be an object")
    return value


def _items(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise PlaycallerEvidenceDataError(f"{context} must be a list")
    return value


def _string(value: Any, context: str, *, optional: bool = False) -> str:
    if value is None and optional:
        return ""
    if not isinstance(value, str) or (not optional and not value.strip()):
        qualifier = "a string" if optional else "a non-empty string"
        raise PlaycallerEvidenceDataError(f"{context} must be {qualifier}")
    return value.strip()


def _date(value: Any, context: str) -> date:
    text = _string(value, context)
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise PlaycallerEvidenceDataError(f"{context} must use YYYY-MM-DD") from error


def _url(value: Any, context: str) -> str:
    text = _string(value, context)
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc:
        raise PlaycallerEvidenceDataError(f"{context} must be an absolute HTTPS URL")
    return text


def _source(value: Any, context: str) -> EvidenceSource:
    item = _mapping(value, context)
    source_type = _string(item.get("source_type"), f"{context}.source_type")
    if source_type not in SOURCE_TYPES:
        raise PlaycallerEvidenceDataError(f"{context}.source_type is unsupported")
    digest = _string(
        item.get("content_sha256"), f"{context}.content_sha256", optional=True
    ).lower()
    if digest and (len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest)):
        raise PlaycallerEvidenceDataError(
            f"{context}.content_sha256 must be a 64-character hexadecimal digest"
        )
    hash_scope = _string(
        item.get("content_hash_scope"),
        f"{context}.content_hash_scope",
        optional=True,
    )
    if bool(digest) != bool(hash_scope):
        raise PlaycallerEvidenceDataError(
            f"{context} must provide content_sha256 and content_hash_scope together"
        )
    return EvidenceSource(
        source_id=_string(item.get("id"), f"{context}.id"),
        title=_string(item.get("title"), f"{context}.title"),
        publisher=_string(item.get("publisher"), f"{context}.publisher"),
        source_type=source_type,
        url=_url(item.get("url"), f"{context}.url"),
        published_at=_date(item.get("published_at"), f"{context}.published_at"),
        accessed_at=_date(item.get("accessed_at"), f"{context}.accessed_at"),
        locator=_string(item.get("locator"), f"{context}.locator"),
        content_sha256=digest,
        content_hash_scope=hash_scope,
    )


def load_playcaller_evidence_registry(path: str | Path) -> PlaycallerEvidenceRegistry:
    """Load a complete, source-linked caller registry without filling ambiguity."""

    resolved = Path(path)
    raw = resolved.read_bytes()
    try:
        root = _mapping(json.loads(raw.decode("utf-8")), "registry")
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PlaycallerEvidenceDataError(f"invalid registry JSON: {resolved}") from error
    if root.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise PlaycallerEvidenceDataError(
            f"registry.schema_version must be {REGISTRY_SCHEMA_VERSION!r}"
        )
    season = root.get("season")
    if isinstance(season, bool) or not isinstance(season, int) or not 1999 <= season <= 2100:
        raise PlaycallerEvidenceDataError("registry.season must be an NFL season")
    as_of = _date(root.get("as_of"), "registry.as_of")
    temporal_use = _string(root.get("temporal_use"), "registry.temporal_use")
    if temporal_use not in TEMPORAL_USES:
        raise PlaycallerEvidenceDataError("registry.temporal_use is unsupported")
    cutoff_value = root.get("forecast_evidence_cutoff")
    cutoff = (
        None
        if cutoff_value is None
        else _date(cutoff_value, "registry.forecast_evidence_cutoff")
    )
    if temporal_use == "preseason_identity_evidence" and cutoff is None:
        raise PlaycallerEvidenceDataError(
            "preseason evidence requires registry.forecast_evidence_cutoff"
        )
    methodology = _mapping(root.get("methodology"), "registry.methodology")

    sources: dict[str, EvidenceSource] = {}
    for index, value in enumerate(_items(root.get("sources"), "registry.sources")):
        item = _source(value, f"registry.sources[{index}]")
        if item.source_id in sources:
            raise PlaycallerEvidenceDataError(f"duplicate source ID {item.source_id!r}")
        if item.accessed_at > as_of or item.published_at > as_of:
            raise PlaycallerEvidenceDataError(f"source {item.source_id!r} is dated after as_of")
        if cutoff is not None and item.published_at > cutoff:
            raise PlaycallerEvidenceDataError(
                f"source {item.source_id!r} was published after the forecast cutoff"
            )
        sources[item.source_id] = item
    if not sources:
        raise PlaycallerEvidenceDataError("registry.sources cannot be empty")

    teams: list[EvidenceTeam] = []
    seen: set[str] = set()
    used_sources: set[str] = set()
    for index, value in enumerate(_items(root.get("teams"), "registry.teams")):
        context = f"registry.teams[{index}]"
        item = _mapping(value, context)
        team = _string(item.get("team"), f"{context}.team").upper()
        if team not in TEAM_NAMES or team in seen:
            raise PlaycallerEvidenceDataError(f"{context}.team is unsupported or duplicate")
        seen.add(team)
        status = _string(item.get("identity_status"), f"{context}.identity_status")
        if status not in IDENTITY_STATUSES:
            raise PlaycallerEvidenceDataError(f"{context}.identity_status is unsupported")
        play_caller = _string(item.get("play_caller"), f"{context}.play_caller", optional=True)
        candidates = tuple(
            _string(candidate, f"{context}.candidate_callers[]")
            for candidate in _items(item.get("candidate_callers", []), f"{context}.candidate_callers")
        )
        if len(set(candidates)) != len(candidates):
            raise PlaycallerEvidenceDataError(f"{context}.candidate_callers has duplicates")
        if status == "confirmed" and (not play_caller or candidates):
            raise PlaycallerEvidenceDataError(
                f"{context} confirmed identity needs one caller and no candidates"
            )
        if status == "ambiguous" and (play_caller or len(candidates) < 2):
            raise PlaycallerEvidenceDataError(
                f"{context} ambiguous identity needs at least two candidates and no selected caller"
            )
        source_ids = tuple(
            _string(source_id, f"{context}.source_ids[]")
            for source_id in _items(item.get("source_ids"), f"{context}.source_ids")
        )
        if not source_ids or len(set(source_ids)) != len(source_ids):
            raise PlaycallerEvidenceDataError(f"{context}.source_ids is empty or duplicated")
        unknown = set(source_ids) - set(sources)
        if unknown:
            raise PlaycallerEvidenceDataError(
                f"{team} references unknown sources: {', '.join(sorted(unknown))}"
            )
        used_sources.update(source_ids)
        teams.append(
            EvidenceTeam(
                team=team,
                identity_status=status,
                play_caller=play_caller,
                candidate_callers=candidates,
                source_ids=source_ids,
                evidence_summary=_string(
                    item.get("evidence_summary"), f"{context}.evidence_summary"
                ),
            )
        )
    missing = set(TEAM_NAMES) - seen
    if missing or len(teams) != len(TEAM_NAMES):
        raise PlaycallerEvidenceDataError(
            "registry must cover all 32 teams; missing " + ", ".join(sorted(missing))
        )
    unused = set(sources) - used_sources
    if unused:
        raise PlaycallerEvidenceDataError(
            "registry has unused sources: " + ", ".join(sorted(unused))
        )
    return PlaycallerEvidenceRegistry(
        season=season,
        as_of=as_of,
        temporal_use=temporal_use,
        forecast_evidence_cutoff=cutoff,
        methodology=methodology,
        sources=sources,
        teams=tuple(sorted(teams, key=lambda row: row.team)),
        raw=raw,
    )


def _csv_bytes(fields: tuple[str, ...], rows: list[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_playcaller_evidence_snapshot(
    registry: PlaycallerEvidenceRegistry,
    root: str | Path,
    *,
    created_at: datetime | None = None,
) -> Path:
    """Atomically publish canonical caller rows and their exact registry input."""

    created = created_at or datetime.now(timezone.utc)
    if created.tzinfo is None or created.utcoffset() is None:
        raise ValueError("created_at must include a timezone")
    created = created.astimezone(timezone.utc)
    created_text = created.isoformat(timespec="microseconds").replace("+00:00", "Z")
    parent = Path(root) / "researched_nfl_playcallers" / str(registry.season) / "all"
    destination = parent / created.strftime("%Y%m%dT%H%M%S.%fZ")
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"play-caller evidence snapshot already exists: {destination}")

    caller_rows: list[Mapping[str, Any]] = []
    for team in registry.teams:
        primary_source = registry.sources[team.source_ids[0]]
        latest_publication = max(
            registry.sources[source_id].published_at for source_id in team.source_ids
        )
        caller_rows.append(
            {
                "season": registry.season,
                "team": team.team,
                "play_caller": team.play_caller,
                "identity_status": team.identity_status,
                "candidate_callers": "|".join(team.candidate_callers),
                "source_id": primary_source.source_id,
                "source_url": primary_source.url,
                "source_locator": primary_source.locator,
                "published_at": latest_publication.isoformat(),
                "researched_at": created_text,
                "temporal_use": registry.temporal_use,
                "evidence_summary": team.evidence_summary,
            }
        )
    source_rows = [
        {
            "source_id": source.source_id,
            "title": source.title,
            "publisher": source.publisher,
            "source_type": source.source_type,
            "url": source.url,
            "published_at": source.published_at.isoformat(),
            "accessed_at": source.accessed_at.isoformat(),
            "locator": source.locator,
            "content_sha256": source.content_sha256,
            "content_hash_scope": source.content_hash_scope,
        }
        for source in sorted(registry.sources.values(), key=lambda item: item.source_id)
    ]
    artifacts = {
        "registry.json": registry.raw,
        "callers.csv": _csv_bytes(CALLER_FIELDS, caller_rows),
        "sources.csv": _csv_bytes(SOURCE_FIELDS, source_rows),
    }
    manifest = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "created_at": created_text,
        "season": registry.season,
        "as_of": registry.as_of.isoformat(),
        "temporal_use": registry.temporal_use,
        "forecast_evidence_cutoff": (
            None
            if registry.forecast_evidence_cutoff is None
            else registry.forecast_evidence_cutoff.isoformat()
        ),
        "methodology": dict(registry.methodology),
        "quality": {
            "team_count": len(registry.teams),
            "confirmed_count": sum(
                team.identity_status == "confirmed" for team in registry.teams
            ),
            "ambiguous_count": sum(
                team.identity_status == "ambiguous" for team in registry.teams
            ),
            "source_count": len(registry.sources),
            "hindsight_resolution_used": False,
        },
        "artifacts": {
            name: {"bytes": len(raw), "sha256": _sha256(raw)}
            for name, raw in artifacts.items()
        },
    }
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
    try:
        for name, raw in artifacts.items():
            (staging / name).write_bytes(raw)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
