"""Validated current-season offensive coaching and play-caller census.

Official club staff pages establish names and job titles.  A separate curated
registry establishes actual offensive play-calling responsibility.  Keeping
those facts apart prevents the common but invalid assumption that every
offensive coordinator calls plays.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

from .sources.official_staff import OFFICIAL_STAFF_URLS, STAFF_FIELDS


REGISTRY_SCHEMA_VERSION = "1.0.0"
CENSUS_SCHEMA_VERSION = "1.0.0"
MODEL_STATUS = "identity_census_only"

SOURCE_TYPES = {
    "official_team",
    "official_league",
    "credentialed_local",
    "wire_service",
    "national_reporting",
}

# These are evidence-strength rubric values, not calibrated probabilities.
CONFIRMATION_LEVELS: Mapping[str, float] = {
    "official_explicit": 1.0,
    "official_contextual": 0.90,
    "credentialed_explicit": 0.80,
    "inferred": 0.45,
    "unresolved": 0.0,
}

TEAM_FIELDS = (
    "season",
    "team",
    "head_coach",
    "offensive_coordinator",
    "play_caller",
    "caller_title",
    "confirmation",
    "evidence_strength",
    "evidence_summary",
    "source_ids",
)

OFFENSIVE_STAFF_FIELDS = (*STAFF_FIELDS, "is_play_caller")


class CoachingDataError(ValueError):
    """Raised when coaching research or an official staff snapshot is invalid."""


@dataclass(frozen=True)
class CoachingSource:
    source_id: str
    title: str
    publisher: str
    source_type: str
    url: str
    published_at: date | None
    accessed_at: date


@dataclass(frozen=True)
class PlayCallerEntry:
    team: str
    head_coach: str
    offensive_coordinator: str
    play_caller: str
    confirmation: str
    source_ids: tuple[str, ...]
    evidence_summary: str


@dataclass(frozen=True)
class PlayCallerRegistry:
    season: int
    as_of: date
    sources: Mapping[str, CoachingSource]
    teams: tuple[PlayCallerEntry, ...]


@dataclass(frozen=True)
class OfficialStaffTitle:
    season: int
    team: str
    name: str
    role: str
    side: str
    responsibility_categories: tuple[str, ...]
    profile_url: str
    source_url: str
    retrieved_at: str

    def to_row(self, *, is_play_caller: bool) -> dict[str, str | int]:
        return {
            "season": self.season,
            "team": self.team,
            "name": self.name,
            "role": self.role,
            "side": self.side,
            "responsibility_categories": "|".join(
                self.responsibility_categories
            ),
            "profile_url": self.profile_url,
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at,
            "is_play_caller": "true" if is_play_caller else "false",
        }


@dataclass(frozen=True)
class CoachingCensus:
    registry: PlayCallerRegistry
    official_staff_path: Path
    official_staff_sha256: str
    official_staff: tuple[OfficialStaffTitle, ...]
    team_rows: tuple[Mapping[str, str | int | float], ...]


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CoachingDataError(f"{context} must be an object")
    return value


def _list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise CoachingDataError(f"{context} must be a list")
    return value


def _string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CoachingDataError(f"{context} must be a non-empty string")
    return value.strip()


def _iso_date(value: Any, context: str) -> date:
    text = _string(value, context)
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise CoachingDataError(f"{context} must use YYYY-MM-DD") from error


def _optional_date(value: Any, context: str) -> date | None:
    return None if value is None else _iso_date(value, context)


def _source(data: Mapping[str, Any], context: str) -> CoachingSource:
    source_type = _string(data.get("source_type"), f"{context}.source_type")
    if source_type not in SOURCE_TYPES:
        raise CoachingDataError(f"{context}.source_type is unsupported")
    url = _string(data.get("url"), f"{context}.url")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise CoachingDataError(f"{context}.url must be an absolute HTTPS URL")
    return CoachingSource(
        source_id=_string(data.get("id"), f"{context}.id"),
        title=_string(data.get("title"), f"{context}.title"),
        publisher=_string(data.get("publisher"), f"{context}.publisher"),
        source_type=source_type,
        url=url,
        published_at=_optional_date(data.get("published_at"), f"{context}.published_at"),
        accessed_at=_iso_date(data.get("accessed_at"), f"{context}.accessed_at"),
    )


def _source_ids(value: Any, context: str) -> tuple[str, ...]:
    values = tuple(_string(item, f"{context}[]") for item in _list(value, context))
    if not values:
        raise CoachingDataError(f"{context} cannot be empty")
    if len(set(values)) != len(values):
        raise CoachingDataError(f"{context} cannot contain duplicates")
    return values


def load_playcaller_registry(path: str | Path) -> PlayCallerRegistry:
    """Load and validate a full-league, evidence-backed caller registry."""

    with Path(path).open(encoding="utf-8") as handle:
        root = _mapping(json.load(handle), "registry")
    if root.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise CoachingDataError(
            f"registry.schema_version must be {REGISTRY_SCHEMA_VERSION!r}"
        )
    season = root.get("season")
    if isinstance(season, bool) or not isinstance(season, int):
        raise CoachingDataError("registry.season must be an integer")
    if not 1999 <= season <= 2100:
        raise CoachingDataError("registry.season must be an NFL season")
    as_of = _iso_date(root.get("as_of"), "registry.as_of")

    sources: dict[str, CoachingSource] = {}
    for index, raw in enumerate(_list(root.get("sources"), "registry.sources")):
        context = f"registry.sources[{index}]"
        item = _source(_mapping(raw, context), context)
        if item.source_id in sources:
            raise CoachingDataError(f"duplicate source ID {item.source_id!r}")
        if item.accessed_at > as_of or (
            item.published_at is not None and item.published_at > as_of
        ):
            raise CoachingDataError(f"source {item.source_id!r} is dated after as_of")
        sources[item.source_id] = item
    if not sources:
        raise CoachingDataError("registry.sources cannot be empty")

    teams: list[PlayCallerEntry] = []
    seen: set[str] = set()
    used_sources: set[str] = set()
    for index, raw in enumerate(_list(root.get("teams"), "registry.teams")):
        context = f"registry.teams[{index}]"
        data = _mapping(raw, context)
        team = _string(data.get("team"), f"{context}.team").upper()
        if team in seen:
            raise CoachingDataError(f"duplicate team {team!r}")
        seen.add(team)
        confirmation = _string(
            data.get("confirmation"), f"{context}.confirmation"
        )
        if confirmation not in CONFIRMATION_LEVELS:
            raise CoachingDataError(f"{context}.confirmation is unsupported")
        source_ids = _source_ids(data.get("source_ids"), f"{context}.source_ids")
        unknown_sources = set(source_ids) - set(sources)
        if unknown_sources:
            raise CoachingDataError(
                f"{team} references unknown sources: "
                f"{', '.join(sorted(unknown_sources))}"
            )
        source_types = {sources[source_id].source_type for source_id in source_ids}
        if confirmation.startswith("official_") and not source_types.intersection(
            {"official_team", "official_league"}
        ):
            raise CoachingDataError(
                f"{team} has official confirmation without an official source"
            )
        if confirmation == "credentialed_explicit" and not source_types.intersection(
            {"credentialed_local", "wire_service", "national_reporting"}
        ):
            raise CoachingDataError(
                f"{team} has credentialed confirmation without a reporting source"
            )
        used_sources.update(source_ids)
        teams.append(
            PlayCallerEntry(
                team=team,
                head_coach=_string(data.get("head_coach"), f"{context}.head_coach"),
                offensive_coordinator=_string(
                    data.get("offensive_coordinator"),
                    f"{context}.offensive_coordinator",
                ),
                play_caller=_string(
                    data.get("play_caller"), f"{context}.play_caller"
                ),
                confirmation=confirmation,
                source_ids=source_ids,
                evidence_summary=_string(
                    data.get("evidence_summary"), f"{context}.evidence_summary"
                ),
            )
        )

    expected = set(OFFICIAL_STAFF_URLS)
    missing = expected - seen
    extra = seen - expected
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f"missing {', '.join(sorted(missing))}")
        if extra:
            details.append(f"unsupported {', '.join(sorted(extra))}")
        raise CoachingDataError(
            "registry must contain exactly the 32 supported teams: " + "; ".join(details)
        )
    unused = set(sources) - used_sources
    if unused:
        raise CoachingDataError(
            f"registry contains unused sources: {', '.join(sorted(unused))}"
        )
    return PlayCallerRegistry(
        season=season,
        as_of=as_of,
        sources=sources,
        teams=tuple(sorted(teams, key=lambda item: item.team)),
    )


def _staff_csv_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate / "staff.csv" if candidate.is_dir() else candidate


def load_official_staff_titles(path: str | Path) -> tuple[OfficialStaffTitle, ...]:
    """Load the normalized CSV emitted by the official staff adapter."""

    csv_path = _staff_csv_path(path)
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = set(STAFF_FIELDS) - set(reader.fieldnames or ())
        if missing:
            raise CoachingDataError(
                "official staff CSV is missing fields: "
                + ", ".join(sorted(missing))
            )
        records: list[OfficialStaffTitle] = []
        seen: set[tuple[int, str, str, str]] = set()
        for row_number, row in enumerate(reader, start=2):
            try:
                season = int((row.get("season") or "").strip())
            except ValueError as error:
                raise CoachingDataError(
                    f"official staff row {row_number} has an invalid season"
                ) from error
            team = (row.get("team") or "").strip().upper()
            name = (row.get("name") or "").strip()
            role = (row.get("role") or "").strip()
            side = (row.get("side") or "").strip()
            if not team or not name or not role or not side:
                raise CoachingDataError(
                    f"official staff row {row_number} has a blank required value"
                )
            key = (season, team, name.casefold(), role.casefold())
            if key in seen:
                raise CoachingDataError(
                    f"official staff row {row_number} duplicates {team} {name} {role}"
                )
            seen.add(key)
            categories = tuple(
                item
                for item in (row.get("responsibility_categories") or "").split("|")
                if item
            )
            records.append(
                OfficialStaffTitle(
                    season=season,
                    team=team,
                    name=name,
                    role=role,
                    side=side,
                    responsibility_categories=categories,
                    profile_url=(row.get("profile_url") or "").strip(),
                    source_url=(row.get("source_url") or "").strip(),
                    retrieved_at=(row.get("retrieved_at") or "").strip(),
                )
            )
    if not records:
        raise CoachingDataError("official staff CSV contains no records")
    return tuple(
        sorted(records, key=lambda item: (item.team, item.side, item.role, item.name))
    )


def _primary_offensive_coordinators(
    records: Iterable[OfficialStaffTitle],
) -> tuple[OfficialStaffTitle, ...]:
    return tuple(
        record
        for record in records
        if "offensive_coordinator" in record.responsibility_categories
        and "assistant offensive coordinator" not in record.role.lower()
    )


def build_coaching_census(
    registry: PlayCallerRegistry,
    official_staff_path: str | Path,
) -> CoachingCensus:
    """Cross-check caller research against an exact official staff snapshot."""

    csv_path = _staff_csv_path(official_staff_path)
    raw_staff = csv_path.read_bytes()
    staff = load_official_staff_titles(csv_path)
    seasons = {record.season for record in staff}
    if seasons != {registry.season}:
        raise CoachingDataError(
            f"official staff seasons {sorted(seasons)} do not match {registry.season}"
        )
    staff_teams = {record.team for record in staff}
    registry_teams = {entry.team for entry in registry.teams}
    if staff_teams != registry_teams:
        missing = registry_teams - staff_teams
        extra = staff_teams - registry_teams
        raise CoachingDataError(
            "official staff coverage does not match registry"
            + (f"; missing {', '.join(sorted(missing))}" if missing else "")
            + (f"; extra {', '.join(sorted(extra))}" if extra else "")
        )

    team_rows: list[Mapping[str, str | int | float]] = []
    for entry in registry.teams:
        team_staff = tuple(record for record in staff if record.team == entry.team)
        head_coaches = tuple(
            record for record in team_staff if record.side == "head_coach"
        )
        if len(head_coaches) != 1:
            raise CoachingDataError(
                f"{entry.team} official snapshot has {len(head_coaches)} head coaches"
            )
        coordinators = _primary_offensive_coordinators(team_staff)
        if len(coordinators) != 1:
            raise CoachingDataError(
                f"{entry.team} official snapshot has {len(coordinators)} primary OCs"
            )
        if entry.head_coach != head_coaches[0].name:
            raise CoachingDataError(
                f"{entry.team} registry HC {entry.head_coach!r} does not match "
                f"official {head_coaches[0].name!r}"
            )
        if entry.offensive_coordinator != coordinators[0].name:
            raise CoachingDataError(
                f"{entry.team} registry OC {entry.offensive_coordinator!r} does not "
                f"match official {coordinators[0].name!r}"
            )
        caller_titles = tuple(
            record for record in team_staff if record.name == entry.play_caller
        )
        if not caller_titles:
            raise CoachingDataError(
                f"{entry.team} caller {entry.play_caller!r} is absent from official staff"
            )
        if entry.confirmation == "unresolved":
            raise CoachingDataError(
                f"{entry.team} cannot publish a census with an unresolved caller"
            )
        team_rows.append(
            {
                "season": registry.season,
                "team": entry.team,
                "head_coach": entry.head_coach,
                "offensive_coordinator": entry.offensive_coordinator,
                "play_caller": entry.play_caller,
                "caller_title": " | ".join(
                    sorted({record.role for record in caller_titles})
                ),
                "confirmation": entry.confirmation,
                "evidence_strength": CONFIRMATION_LEVELS[entry.confirmation],
                "evidence_summary": entry.evidence_summary,
                "source_ids": "|".join(entry.source_ids),
            }
        )
    return CoachingCensus(
        registry=registry,
        official_staff_path=csv_path,
        official_staff_sha256=hashlib.sha256(raw_staff).hexdigest(),
        official_staff=staff,
        team_rows=tuple(team_rows),
    )


def _csv_bytes(
    rows: Iterable[Mapping[str, Any]], fields: Iterable[str]
) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=tuple(fields), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _source_payload(source: CoachingSource) -> dict[str, Any]:
    return {
        "id": source.source_id,
        "title": source.title,
        "publisher": source.publisher,
        "source_type": source.source_type,
        "url": source.url,
        "published_at": (
            source.published_at.isoformat() if source.published_at is not None else None
        ),
        "accessed_at": source.accessed_at.isoformat(),
    }


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("generated_at must include a timezone")
    return value.astimezone(timezone.utc)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def write_coaching_census_snapshot(
    census: CoachingCensus,
    root: str | Path,
    *,
    registry_bytes: bytes,
    generated_at: datetime | None = None,
) -> Path:
    """Atomically publish a joined caller and offensive-staff census."""

    generated_at = _utc(generated_at or datetime.now(timezone.utc))
    parent = Path(root) / "coaching_census" / str(census.registry.season)
    destination = parent / generated_at.strftime("%Y%m%dT%H%M%S.%fZ")
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"coaching census snapshot already exists: {destination}")

    team_csv = _csv_bytes(census.team_rows, TEAM_FIELDS)
    callers = {entry.team: entry.play_caller for entry in census.registry.teams}
    offensive_records = tuple(
        record
        for record in census.official_staff
        if record.side in {"head_coach", "offense"}
    )
    offensive_csv = _csv_bytes(
        (
            record.to_row(is_play_caller=record.name == callers[record.team])
            for record in offensive_records
        ),
        OFFENSIVE_STAFF_FIELDS,
    )
    source_payload = [
        _source_payload(census.registry.sources[source_id])
        for source_id in sorted(census.registry.sources)
    ]
    sources_json = (
        json.dumps(source_payload, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    confirmation_counts = Counter(
        entry.confirmation for entry in census.registry.teams
    )
    manifest = {
        "schema_version": CENSUS_SCHEMA_VERSION,
        "status": MODEL_STATUS,
        "season": census.registry.season,
        "as_of": census.registry.as_of.isoformat(),
        "generated_at": _iso_z(generated_at),
        "quality": {
            "team_count": len(census.registry.teams),
            "official_staff_record_count": len(census.official_staff),
            "offensive_staff_record_count": len(offensive_records),
            "play_caller_count": len({entry.team for entry in census.registry.teams}),
            "confirmation_counts": dict(sorted(confirmation_counts.items())),
            "title_caller_inference_used": False,
            "exact_name_matching_used": True,
        },
        "limitations": [
            "Evidence strength is a rubric value, not a probability.",
            "This snapshot identifies current staff and callers; it does not yet audit coach histories or forecast style.",
            "Official staff pages are living pages and are valid only as of their retrieval timestamps.",
        ],
        "inputs": {
            "registry": {
                "bytes": len(registry_bytes),
                "sha256": hashlib.sha256(registry_bytes).hexdigest(),
            },
            "official_staff": {
                "path": str(census.official_staff_path),
                "bytes": census.official_staff_path.stat().st_size,
                "sha256": census.official_staff_sha256,
            },
        },
        "artifacts": {
            "teams": {
                "path": "teams.csv",
                "bytes": len(team_csv),
                "sha256": hashlib.sha256(team_csv).hexdigest(),
                "fields": list(TEAM_FIELDS),
            },
            "offensive_staff": {
                "path": "offensive_staff.csv",
                "bytes": len(offensive_csv),
                "sha256": hashlib.sha256(offensive_csv).hexdigest(),
                "fields": list(OFFENSIVE_STAFF_FIELDS),
            },
            "sources": {
                "path": "sources.json",
                "bytes": len(sources_json),
                "sha256": hashlib.sha256(sources_json).hexdigest(),
            },
        },
    }
    # Guard against a future accidental NaN in a manifest or evidence score.
    if not all(
        math.isfinite(float(row["evidence_strength"])) for row in census.team_rows
    ):
        raise CoachingDataError("census contains a non-finite evidence strength")

    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
    try:
        (staging / "teams.csv").write_bytes(team_csv)
        (staging / "offensive_staff.csv").write_bytes(offensive_csv)
        (staging / "sources.json").write_bytes(sources_json)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
