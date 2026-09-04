"""Measured year-over-year offensive coaching continuity.

This module joins two dated official staff snapshots by coach identity and by
explicit responsibility category.  It intentionally does not infer who called
plays in the prior season: the current caller can be shown as returning to the
team, but caller-to-caller continuity needs its own historical evidence.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import tempfile
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse


SCHEMA_VERSION = "1.0.0"
ALIAS_SCHEMA_VERSION = "1.0.0"
MODEL_STATUS = "descriptive_not_style_certainty"

CORE_RESPONSIBILITIES = (
    "head_coach",
    "offensive_coordinator",
    "quarterbacks",
    "running_backs",
    "wide_receivers",
    "tight_ends",
    "offensive_line",
)

CURRENT_STAFF_FIELDS = (
    "season",
    "prior_season",
    "team",
    "name",
    "role",
    "responsibility_categories",
    "continuity_status",
    "prior_name",
    "prior_role",
    "prior_side",
    "prior_responsibility_categories",
    "matched_via_alias",
    "is_play_caller",
)

RESPONSIBILITY_FIELDS = (
    "season",
    "prior_season",
    "team",
    "responsibility",
    "status",
    "prior_holders",
    "current_holders",
    "retained_holders",
)

TEAM_FIELDS = (
    "season",
    "prior_season",
    "team",
    "prior_head_coach",
    "current_head_coach",
    "head_coach_status",
    "prior_offensive_coordinator",
    "current_offensive_coordinator",
    "offensive_coordinator_status",
    "prior_play_caller",
    "current_play_caller",
    "same_play_caller",
    "current_caller_2025_status",
    "current_caller_2025_team",
    "play_caller_on_prior_staff",
    "play_caller_prior_role",
    "current_offensive_staff_count",
    "returning_staff_count",
    "returning_staff_share",
    "same_responsibility_count",
    "same_responsibility_share",
    "retained_core_responsibility_count",
    "changed_core_responsibility_count",
    "unavailable_core_responsibility_count",
    "comparable_core_responsibility_count",
    "core_responsibility_retention_share",
    "staff_continuity_index_v0",
    "model_status",
)


class ContinuityDataError(ValueError):
    """Raised when a staff, caller, or identity-alias input is invalid."""


@dataclass(frozen=True)
class StaffTitle:
    season: int
    team: str
    name: str
    role: str
    side: str
    responsibilities: tuple[str, ...]


@dataclass(frozen=True)
class CallerIdentity:
    name: str | None
    identity_status: str
    candidate_callers: tuple[str, ...]


@dataclass(frozen=True)
class IdentityAlias:
    season: int
    team: str
    observed_name: str
    canonical_name: str
    reason: str
    source_urls: tuple[str, ...]


@dataclass(frozen=True)
class ContinuityResult:
    season: int
    prior_season: int
    as_of: date
    prior_staff_path: Path
    current_staff_path: Path
    callers_path: Path
    prior_callers_path: Path
    aliases_path: Path | None
    prior_staff_sha256: str
    current_staff_sha256: str
    callers_sha256: str
    prior_callers_sha256: str
    aliases_sha256: str | None
    current_staff_rows: tuple[Mapping[str, str | int | float], ...]
    responsibility_rows: tuple[Mapping[str, str | int | float], ...]
    team_rows: tuple[Mapping[str, str | int | float], ...]


def _resolve_csv(path: str | Path, filename: str) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / filename
    if not candidate.is_file():
        raise ContinuityDataError(f"input file does not exist: {candidate}")
    return candidate


def _parse_int(value: str, context: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ContinuityDataError(f"{context} must be an integer") from error
    if not 1999 <= parsed <= 2100:
        raise ContinuityDataError(f"{context} must be an NFL season")
    return parsed


def _staff(path: str | Path) -> tuple[Path, bytes, tuple[StaffTitle, ...]]:
    resolved = _resolve_csv(path, "staff.csv")
    raw = resolved.read_bytes()
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    except UnicodeDecodeError as error:
        raise ContinuityDataError(f"staff CSV is not UTF-8: {resolved}") from error
    required = {"season", "team", "name", "role", "side", "responsibility_categories"}
    if not rows or not required.issubset(rows[0]):
        raise ContinuityDataError(f"staff CSV has no rows or required fields: {resolved}")
    result: list[StaffTitle] = []
    seen: set[tuple[int, str, str, str]] = set()
    for index, row in enumerate(rows, start=2):
        season = _parse_int(row["season"], f"{resolved}:{index}.season")
        team = row["team"].strip().upper()
        name = row["name"].strip()
        role = row["role"].strip()
        side = row["side"].strip()
        if not team or not name or not role or not side:
            raise ContinuityDataError(f"blank required staff value at {resolved}:{index}")
        responsibilities = tuple(
            sorted(filter(None, (item.strip() for item in row["responsibility_categories"].split("|"))))
        )
        key = (season, team, _identity(name), role.casefold())
        if key in seen:
            raise ContinuityDataError(f"duplicate staff row at {resolved}:{index}")
        seen.add(key)
        result.append(StaffTitle(season, team, name, role, side, responsibilities))
    return resolved, raw, tuple(result)


def _identity(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).casefold()
    identity = "".join(character for character in normalized if character.isalnum())
    for suffix in ("iii", "ii", "iv", "jr", "sr"):
        if identity.endswith(suffix):
            return identity[: -len(suffix)]
    return identity


def _title_key(role: str) -> str:
    normalized = unicodedata.normalize("NFKD", role).casefold()
    return " ".join("".join(character if character.isalnum() else " " for character in normalized).split())


def load_identity_aliases(path: str | Path) -> tuple[date, tuple[IdentityAlias, ...]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping) or raw.get("schema_version") != ALIAS_SCHEMA_VERSION:
        raise ContinuityDataError(
            f"identity alias schema_version must be {ALIAS_SCHEMA_VERSION!r}"
        )
    try:
        as_of = date.fromisoformat(str(raw.get("as_of")))
    except ValueError as error:
        raise ContinuityDataError("identity alias as_of must use YYYY-MM-DD") from error
    aliases_raw = raw.get("aliases")
    if not isinstance(aliases_raw, list):
        raise ContinuityDataError("identity aliases must be a list")
    aliases: list[IdentityAlias] = []
    seen: set[tuple[int, str, str]] = set()
    for index, item in enumerate(aliases_raw):
        if not isinstance(item, Mapping):
            raise ContinuityDataError(f"identity aliases[{index}] must be an object")
        season = item.get("season")
        if isinstance(season, bool) or not isinstance(season, int):
            raise ContinuityDataError(f"identity aliases[{index}].season must be an integer")
        team = str(item.get("team", "")).strip().upper()
        observed = str(item.get("observed_name", "")).strip()
        canonical = str(item.get("canonical_name", "")).strip()
        reason = str(item.get("reason", "")).strip()
        urls = item.get("source_urls")
        if not team or not observed or not canonical or not reason or not isinstance(urls, list) or not urls:
            raise ContinuityDataError(f"identity aliases[{index}] has blank required values")
        checked_urls: list[str] = []
        for url in urls:
            parsed = urlparse(str(url))
            if parsed.scheme != "https" or not parsed.netloc:
                raise ContinuityDataError(f"identity aliases[{index}] has an invalid source URL")
            checked_urls.append(str(url))
        key = (season, team, _identity(observed))
        if key in seen:
            raise ContinuityDataError(f"duplicate identity alias for {season} {team} {observed}")
        seen.add(key)
        aliases.append(IdentityAlias(season, team, observed, canonical, reason, tuple(checked_urls)))
    return as_of, tuple(aliases)


def _callers(
    path: str | Path, *, filename: str = "teams.csv"
) -> tuple[Path, bytes, int, dict[str, CallerIdentity]]:
    resolved = _resolve_csv(path, filename)
    raw = resolved.read_bytes()
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    required = {"season", "team", "play_caller"}
    if not rows or not required.issubset(rows[0]):
        raise ContinuityDataError("caller CSV has no rows or required fields")
    seasons = {_parse_int(row["season"], "caller season") for row in rows}
    if len(seasons) != 1:
        raise ContinuityDataError("caller CSV must contain exactly one season")
    callers: dict[str, CallerIdentity] = {}
    for row in rows:
        team = row["team"].strip().upper()
        caller = row["play_caller"].strip()
        identity_status = (row.get("identity_status") or "confirmed").strip()
        candidates = tuple(
            item.strip()
            for item in (row.get("candidate_callers") or "").split("|")
            if item.strip()
        )
        if (
            not team
            or team in callers
            or identity_status not in {"confirmed", "ambiguous"}
            or (identity_status == "confirmed" and (not caller or candidates))
            or (identity_status == "ambiguous" and (caller or len(candidates) < 2))
            or len(set(candidates)) != len(candidates)
        ):
            raise ContinuityDataError(
                "caller CSV contains an invalid identity or duplicate team"
            )
        callers[team] = CallerIdentity(
            name=caller or None,
            identity_status=identity_status,
            candidate_callers=candidates,
        )
    return resolved, raw, seasons.pop(), callers


def _holders(rows: Iterable[StaffTitle], responsibility: str) -> tuple[str, ...]:
    return tuple(sorted({row.name for row in rows if responsibility in row.responsibilities}))


def _csv_bytes(rows: Iterable[Mapping[str, Any]], fields: tuple[str, ...]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def build_staff_continuity(
    prior_staff: str | Path,
    current_staff: str | Path,
    callers: str | Path,
    prior_callers: str | Path,
    *,
    aliases: str | Path | None = None,
) -> ContinuityResult:
    """Join official staff snapshots and return descriptive continuity features."""

    prior_path, prior_bytes, prior_rows = _staff(prior_staff)
    current_path, current_bytes, current_rows = _staff(current_staff)
    callers_path, callers_bytes, caller_season, caller_by_team = _callers(callers)
    prior_callers_path, prior_callers_bytes, prior_caller_season, prior_caller_by_team = _callers(
        prior_callers, filename="callers.csv"
    )
    prior_seasons = {row.season for row in prior_rows}
    current_seasons = {row.season for row in current_rows}
    if len(prior_seasons) != 1 or len(current_seasons) != 1:
        raise ContinuityDataError("each staff CSV must contain exactly one season")
    prior_season = prior_seasons.pop()
    season = current_seasons.pop()
    if (
        season != prior_season + 1
        or caller_season != season
        or prior_caller_season != prior_season
    ):
        raise ContinuityDataError("staff and caller seasons are not consecutive/aligned")
    prior_teams = {row.team for row in prior_rows}
    current_teams = {row.team for row in current_rows}
    if (
        prior_teams != current_teams
        or current_teams != set(caller_by_team)
        or prior_teams != set(prior_caller_by_team)
    ):
        raise ContinuityDataError("prior staff, current staff, and caller team sets differ")

    alias_path: Path | None = None
    alias_bytes: bytes | None = None
    alias_rows: tuple[IdentityAlias, ...] = ()
    as_of = date.today()
    if aliases is not None:
        alias_path = Path(aliases)
        alias_bytes = alias_path.read_bytes()
        as_of, alias_rows = load_identity_aliases(alias_path)
    alias_map = {
        (item.season, item.team, _identity(item.observed_name)): _identity(item.canonical_name)
        for item in alias_rows
    }

    def canonical(row: StaffTitle) -> str:
        key = (row.season, row.team, _identity(row.name))
        return alias_map.get(key, key[2])

    def canonical_name(name: str, *, team: str, year: int) -> str:
        key = (year, team, _identity(name))
        return alias_map.get(key, key[2])

    prior_by_team_identity: dict[str, dict[str, list[StaffTitle]]] = defaultdict(lambda: defaultdict(list))
    current_by_team: dict[str, list[StaffTitle]] = defaultdict(list)
    prior_by_team: dict[str, list[StaffTitle]] = defaultdict(list)
    for row in prior_rows:
        prior_by_team[row.team].append(row)
        prior_by_team_identity[row.team][canonical(row)].append(row)
    for row in current_rows:
        current_by_team[row.team].append(row)
    prior_caller_teams_by_identity: dict[str, list[str]] = defaultdict(list)
    for prior_team, prior_caller in prior_caller_by_team.items():
        if prior_caller.name is None:
            continue
        prior_caller_teams_by_identity[
            canonical_name(prior_caller.name, team=prior_team, year=prior_season)
        ].append(prior_team)

    annotated: list[Mapping[str, str | int | float]] = []
    responsibility_rows: list[Mapping[str, str | int | float]] = []
    team_rows: list[Mapping[str, str | int | float]] = []
    for team in sorted(current_teams):
        relevant_current = [
            row for row in current_by_team[team] if row.side in {"head_coach", "offense"}
        ]
        relevant_prior = prior_by_team[team]
        caller_identity = caller_by_team[team]
        caller = caller_identity.name
        caller_key = (
            None
            if caller is None
            else canonical_name(caller, team=team, year=season)
        )
        status_counts: Counter[str] = Counter()
        for row in relevant_current:
            matches = prior_by_team_identity[team].get(canonical(row), [])
            prior_responsibilities = sorted(
                {item for match in matches for item in match.responsibilities}
            )
            if not matches:
                status = "new_to_team"
            elif any(_title_key(match.role) == _title_key(row.role) for match in matches):
                status = "returning_same_title"
            elif set(row.responsibilities).intersection(prior_responsibilities):
                status = "returning_same_responsibility"
            else:
                status = "returning_changed_responsibility"
            status_counts[status] += 1
            annotated.append(
                {
                    "season": season,
                    "prior_season": prior_season,
                    "team": team,
                    "name": row.name,
                    "role": row.role,
                    "responsibility_categories": "|".join(row.responsibilities),
                    "continuity_status": status,
                    "prior_name": "|".join(sorted({match.name for match in matches})),
                    "prior_role": "|".join(sorted({match.role for match in matches})),
                    "prior_side": "|".join(sorted({match.side for match in matches})),
                    "prior_responsibility_categories": "|".join(prior_responsibilities),
                    "matched_via_alias": str(
                        any(
                            (match.season, match.team, _identity(match.name)) in alias_map
                            for match in matches
                        )
                    ).lower(),
                    "is_play_caller": (
                        ""
                        if caller_key is None
                        else str(canonical(row) == caller_key).lower()
                    ),
                }
            )

        responsibility_status: dict[str, str] = {}
        for responsibility in CORE_RESPONSIBILITIES:
            prior_holders = _holders(relevant_prior, responsibility)
            current_holders = _holders(relevant_current, responsibility)
            prior_keys = {
                canonical(row)
                for row in relevant_prior
                if responsibility in row.responsibilities
            }
            current_keys = {
                canonical(row)
                for row in relevant_current
                if responsibility in row.responsibilities
            }
            retained_keys = prior_keys.intersection(current_keys)
            retained_holders = tuple(
                sorted(row.name for row in relevant_current if canonical(row) in retained_keys)
            )
            if not prior_holders or not current_holders:
                status = "not_comparable"
            elif retained_keys:
                status = "retained_holder"
            else:
                status = "changed_holder"
            responsibility_status[responsibility] = status
            responsibility_rows.append(
                {
                    "season": season,
                    "prior_season": prior_season,
                    "team": team,
                    "responsibility": responsibility,
                    "status": status,
                    "prior_holders": "|".join(prior_holders),
                    "current_holders": "|".join(current_holders),
                    "retained_holders": "|".join(retained_holders),
                }
            )

        comparable = sum(value != "not_comparable" for value in responsibility_status.values())
        retained = sum(value == "retained_holder" for value in responsibility_status.values())
        changed = sum(value == "changed_holder" for value in responsibility_status.values())
        unavailable = len(CORE_RESPONSIBILITIES) - comparable
        returning = sum(count for key, count in status_counts.items() if key != "new_to_team")
        same_responsibility = (
            status_counts["returning_same_title"]
            + status_counts["returning_same_responsibility"]
        )
        current_count = len(relevant_current)
        returning_share = returning / current_count
        same_share = same_responsibility / current_count
        core_share = retained / comparable if comparable else 0.0
        # A transparent descriptive index, not a forecast probability: half
        # broad staff retention, half named core-responsibility retention.
        continuity_index = 100.0 * (0.5 * returning_share + 0.5 * core_share)

        caller_prior = (
            []
            if caller_key is None
            else prior_by_team_identity[team].get(caller_key, [])
        )
        prior_identity = prior_caller_by_team[team]
        prior_play_caller = prior_identity.name
        prior_caller_key = (
            None
            if prior_play_caller is None
            else canonical_name(
                prior_play_caller, team=team, year=prior_season
            )
        )
        same_play_caller = (
            None
            if caller_key is None or prior_caller_key is None
            else caller_key == prior_caller_key
        )
        caller_2025_teams = (
            ()
            if caller_key is None
            else tuple(sorted(prior_caller_teams_by_identity.get(caller_key, ())))
        )
        if caller_identity.identity_status == "ambiguous":
            caller_2025_status = "ambiguous_current_identity"
        elif prior_identity.identity_status == "ambiguous":
            caller_2025_status = "ambiguous_prior_identity"
        elif same_play_caller:
            caller_2025_status = "same_team_returning_caller"
        elif caller_2025_teams:
            caller_2025_status = "moved_2025_caller"
        else:
            caller_2025_status = "not_a_2025_primary_caller"
        prior_hc = _holders(relevant_prior, "head_coach")
        current_hc = _holders(relevant_current, "head_coach")
        prior_oc = _holders(relevant_prior, "offensive_coordinator")
        current_oc = _holders(relevant_current, "offensive_coordinator")
        team_rows.append(
            {
                "season": season,
                "prior_season": prior_season,
                "team": team,
                "prior_head_coach": "|".join(prior_hc),
                "current_head_coach": "|".join(current_hc),
                "head_coach_status": responsibility_status["head_coach"],
                "prior_offensive_coordinator": "|".join(prior_oc),
                "current_offensive_coordinator": "|".join(current_oc),
                "offensive_coordinator_status": responsibility_status["offensive_coordinator"],
                "prior_play_caller": prior_play_caller or "",
                "current_play_caller": caller or "",
                "same_play_caller": (
                    "" if same_play_caller is None else str(same_play_caller).lower()
                ),
                "current_caller_2025_status": caller_2025_status,
                "current_caller_2025_team": "|".join(caller_2025_teams),
                "play_caller_on_prior_staff": (
                    "" if caller_key is None else str(bool(caller_prior)).lower()
                ),
                "play_caller_prior_role": "|".join(sorted({row.role for row in caller_prior})),
                "current_offensive_staff_count": current_count,
                "returning_staff_count": returning,
                "returning_staff_share": round(returning_share, 6),
                "same_responsibility_count": same_responsibility,
                "same_responsibility_share": round(same_share, 6),
                "retained_core_responsibility_count": retained,
                "changed_core_responsibility_count": changed,
                "unavailable_core_responsibility_count": unavailable,
                "comparable_core_responsibility_count": comparable,
                "core_responsibility_retention_share": round(core_share, 6),
                "staff_continuity_index_v0": round(continuity_index, 1),
                "model_status": MODEL_STATUS,
            }
        )

    return ContinuityResult(
        season=season,
        prior_season=prior_season,
        as_of=as_of,
        prior_staff_path=prior_path,
        current_staff_path=current_path,
        callers_path=callers_path,
        prior_callers_path=prior_callers_path,
        aliases_path=alias_path,
        prior_staff_sha256=hashlib.sha256(prior_bytes).hexdigest(),
        current_staff_sha256=hashlib.sha256(current_bytes).hexdigest(),
        callers_sha256=hashlib.sha256(callers_bytes).hexdigest(),
        prior_callers_sha256=hashlib.sha256(prior_callers_bytes).hexdigest(),
        aliases_sha256=hashlib.sha256(alias_bytes).hexdigest() if alias_bytes else None,
        current_staff_rows=tuple(annotated),
        responsibility_rows=tuple(responsibility_rows),
        team_rows=tuple(team_rows),
    )


def write_staff_continuity_snapshot(result: ContinuityResult, root: str | Path) -> Path:
    """Atomically publish continuity tables with exact input hashes."""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    parent = Path(root) / "staff_continuity" / str(result.season)
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"continuity snapshot already exists: {destination}")
    staff_csv = _csv_bytes(result.current_staff_rows, CURRENT_STAFF_FIELDS)
    responsibilities_csv = _csv_bytes(result.responsibility_rows, RESPONSIBILITY_FIELDS)
    teams_csv = _csv_bytes(result.team_rows, TEAM_FIELDS)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model_status": MODEL_STATUS,
        "season": result.season,
        "prior_season": result.prior_season,
        "as_of": result.as_of.isoformat(),
        "methodology": {
            "identity": "Normalized exact-name match plus explicitly sourced aliases.",
            "same_responsibility": "At least one official responsibility category overlaps year over year.",
            "core_responsibilities": list(CORE_RESPONSIBILITIES),
            "staff_continuity_index_v0": "50% returning current HC/offensive-staff share plus 50% retained comparable core-responsibility share.",
            "warning": "This is descriptive staff continuity, not calibrated style certainty. Caller fields retain source identity status; an ambiguous preseason assignment remains blank rather than being resolved with hindsight.",
        },
        "inputs": {
            "prior_staff": {"path": str(result.prior_staff_path), "sha256": result.prior_staff_sha256},
            "current_staff": {"path": str(result.current_staff_path), "sha256": result.current_staff_sha256},
            "callers": {"path": str(result.callers_path), "sha256": result.callers_sha256},
            "prior_callers": {"path": str(result.prior_callers_path), "sha256": result.prior_callers_sha256},
            "aliases": None if result.aliases_path is None else {"path": str(result.aliases_path), "sha256": result.aliases_sha256},
        },
        "quality": {
            "team_count": len(result.team_rows),
            "current_staff_record_count": len(result.current_staff_rows),
            "responsibility_record_count": len(result.responsibility_rows),
            "responsibility_status_counts": dict(sorted(Counter(str(row["status"]) for row in result.responsibility_rows).items())),
            "teams_with_unavailable_core_responsibilities": [
                row["team"] for row in result.team_rows if int(row["unavailable_core_responsibility_count"]) > 0
            ],
            "teams_with_ambiguous_current_callers": [
                row["team"]
                for row in result.team_rows
                if row["current_caller_2025_status"] == "ambiguous_current_identity"
            ],
        },
        "artifacts": {},
    }
    for name, payload, fields in (
        ("current_staff.csv", staff_csv, CURRENT_STAFF_FIELDS),
        ("responsibilities.csv", responsibilities_csv, RESPONSIBILITY_FIELDS),
        ("teams.csv", teams_csv, TEAM_FIELDS),
    ):
        manifest["artifacts"][name] = {
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "fields": list(fields),
        }
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
    try:
        (staging / "current_staff.csv").write_bytes(staff_csv)
        (staging / "responsibilities.csv").write_bytes(responsibilities_csv)
        (staging / "teams.csv").write_bytes(teams_csv)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
