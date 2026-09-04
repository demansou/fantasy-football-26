"""Current NFL player identity, roster, depth, usage, and snap ingestion.

The source contract is deliberately narrower than a fantasy projection feed:
current employment and depth placement come from nflverse roster/depth releases,
historical opportunities come from nflverse's official-stat-aligned weekly data,
and offensive snaps come from its Pro Football Reference snap-count release.
Names are never used to join these source families.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import shutil
import tempfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SOURCE_ID = "nflverse"
SOURCE_NAME = "nflverse"
SOURCE_REPOSITORY = "https://github.com/nflverse/nflverse-data"
PLAYERS_REPOSITORY = "https://github.com/nflverse/nflverse-players"
ROSTERS_REPOSITORY = "https://github.com/nflverse/nflverse-rosters"
SOURCE_LICENSE = "CC-BY-4.0"
ADAPTER_VERSION = "1.1.0"
SNAPSHOT_SCHEMA_VERSION = "1.1.0"

PLAYERS_URL = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
ROSTER_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/rosters/"
    "roster_{season}.csv"
)
DEPTH_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/depth_charts/"
    "depth_charts_{season}.csv"
)
WEEKLY_STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/stats_player/"
    "stats_player_week_{season}.csv"
)
SNAP_COUNTS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/snap_counts/"
    "snap_counts_{season}.csv"
)

MAX_BYTES = {
    "players": 15_000_000,
    "roster": 10_000_000,
    "depth_charts": 90_000_000,
    "weekly_stats": 20_000_000,
    "snap_counts": 12_000_000,
}

PLAYERS_REQUIRED = {"gsis_id", "display_name", "pfr_id", "espn_id"}
ROSTER_REQUIRED = {
    "season",
    "team",
    "position",
    "status",
    "full_name",
    "gsis_id",
    "espn_id",
    "pfr_id",
    "yahoo_id",
    "week",
    "game_type",
}
DEPTH_REQUIRED = {
    "dt",
    "team",
    "player_name",
    "espn_id",
    "gsis_id",
    "pos_grp",
    "pos_name",
    "pos_abb",
    "pos_slot",
    "pos_rank",
}
STATS_REQUIRED = {
    "player_id",
    "player_display_name",
    "position",
    "season",
    "week",
    "season_type",
    "game_id",
    "team",
    "attempts",
    "sacks_suffered",
    "carries",
    "targets",
    "receptions",
    "receiving_air_yards",
}
SNAPS_REQUIRED = {
    "game_id",
    "season",
    "game_type",
    "week",
    "player",
    "pfr_player_id",
    "position",
    "team",
    "offense_snaps",
}

CURRENT_ROSTER_FIELDS = (
    "season",
    "team",
    "roster_team",
    "roster_position",
    "fantasy_position",
    "depth_chart_position",
    "current_status",
    "roster_status",
    "status_description",
    "full_name",
    "display_name",
    "first_name",
    "last_name",
    "football_name",
    "gsis_id",
    "espn_id",
    "pfr_id",
    "yahoo_id",
    "sleeper_id",
    "pff_id",
    "rotowire_id",
    "fantasy_data_id",
    "birth_date",
    "years_experience",
    "roster_week",
    "game_type",
    "catalog_latest_team",
    "catalog_status",
)

DEPTH_FIELDS = (
    "snapshot_dt",
    "team",
    "player_name",
    "source_gsis_id",
    "source_espn_id",
    "canonical_gsis_id",
    "identity_status",
    "identity_method",
    "on_current_team_roster",
    "current_status",
    "roster_status",
    "pos_group",
    "pos_name",
    "pos_abb",
    "fantasy_position",
    "pos_slot",
    "pos_rank",
)

HISTORY_FIELDS = (
    "season",
    "team",
    "gsis_id",
    "player_name",
    "position",
    "games",
    "attempts",
    "sacks_suffered",
    "dropbacks",
    "carries",
    "targets",
    "receptions",
    "receiving_air_yards",
    "offense_snaps",
    "team_offense_snaps",
    "team_qb_dropbacks",
    "team_position_carries",
    "team_position_targets",
    "team_position_air_yards",
    "dropback_share",
    "carry_share_within_position",
    "target_share_within_position",
    "air_yards_share_within_position",
    "offense_snap_share",
)

REVIEW_FIELDS = (
    "source",
    "season",
    "team",
    "source_player_id",
    "source_secondary_id",
    "player_name",
    "position",
    "issue",
    "candidate_gsis_ids",
    "details",
)

TEAM_ALIASES = {
    "ARZ": "ARI",
    "BLT": "BAL",
    "CLV": "CLE",
    "HST": "HOU",
    "JAC": "JAX",
    "LA": "LAR",
    "OAK": "LV",
    "SD": "LAC",
    "STL": "LAR",
    "WSH": "WAS",
}

# The player catalog is refreshed independently of the season roster release.
# These codes all indicate an ongoing club affiliation, but only ACT is eligible
# for the active-roster-conditional role model downstream.
CATALOG_AFFILIATED_STATUSES = frozenset(
    {"ACT", "DEV", "RES", "RSR", "PUP", "RSN", "SUS", "EXE"}
)


class NflversePlayerSourceError(RuntimeError):
    """Raised when player-context source data violates the adapter contract."""


@dataclass(frozen=True)
class NflversePlayerQuery:
    season: int
    history_seasons: tuple[int, ...]

    def __post_init__(self) -> None:
        if isinstance(self.season, bool) or not isinstance(self.season, int):
            raise ValueError("current player season must be an integer")
        if not 1999 <= self.season <= 2100:
            raise ValueError("current player season must be between 1999 and 2100")
        normalized: list[int] = []
        for season in self.history_seasons:
            if isinstance(season, bool) or not isinstance(season, int):
                raise ValueError("history seasons must be integers")
            if not 1999 <= season < self.season:
                raise ValueError("history seasons must precede the current season")
            normalized.append(season)
        if not normalized:
            raise ValueError("at least one history season is required")
        if len(set(normalized)) != len(normalized):
            raise ValueError("history seasons cannot contain duplicates")
        object.__setattr__(self, "history_seasons", tuple(sorted(normalized)))


@dataclass(frozen=True)
class NflversePlayerAsset:
    kind: str
    url: str
    raw_bytes: bytes
    season: int | None = None
    response_last_modified: str | None = None
    response_etag: str | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw_bytes).hexdigest()

    @property
    def filename(self) -> str:
        if self.kind == "players":
            return "players.csv"
        prefixes = {
            "roster": "roster",
            "depth_charts": "depth_charts",
            "weekly_stats": "stats_player_week",
            "snap_counts": "snap_counts",
        }
        return f"{prefixes[self.kind]}_{self.season}.csv"


@dataclass(frozen=True)
class NflversePlayerContextSnapshot:
    query: NflversePlayerQuery
    retrieved_at: datetime
    assets: tuple[NflversePlayerAsset, ...]
    current_roster: tuple[Mapping[str, Any], ...]
    current_depth_chart: tuple[Mapping[str, Any], ...]
    historical_usage: tuple[Mapping[str, Any], ...]
    identity_review: tuple[Mapping[str, Any], ...]
    source_fields: Mapping[str, tuple[str, ...]]
    latest_depth_by_team: Mapping[str, str]


def _utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    return value.astimezone(timezone.utc)


def _team(value: str | None) -> str:
    normalized = (value or "").strip().upper()
    return TEAM_ALIASES.get(normalized, normalized)


def _fantasy_position(value: str | None) -> str:
    normalized = (value or "").strip().upper()
    if normalized in {"RB", "HB", "FB"}:
        return "RB"
    if normalized in {"QB", "WR", "TE"}:
        return normalized
    if normalized in {"K", "PK"}:
        return "K"
    return ""


def _number(value: str | None) -> float:
    if value is None or not value.strip():
        return 0.0
    try:
        parsed = float(value)
    except ValueError as error:
        raise NflversePlayerSourceError(f"invalid numeric value {value!r}") from error
    if not math.isfinite(parsed):
        raise NflversePlayerSourceError(f"non-finite numeric value {value!r}")
    return parsed


def _integer_text(value: str | None) -> str:
    if value is None or not value.strip():
        return ""
    number = _number(value)
    return str(int(number)) if number.is_integer() else f"{number:.6f}"


def _reader(
    raw_bytes: bytes,
    *,
    context: str,
    required: set[str],
) -> tuple[csv.DictReader, tuple[str, ...]]:
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise NflversePlayerSourceError(f"{context} is not UTF-8 CSV") from error
    reader = csv.DictReader(io.StringIO(text, newline=""))
    fields = tuple(reader.fieldnames or ())
    missing = required - set(fields)
    if missing:
        raise NflversePlayerSourceError(
            f"{context} is missing fields: {', '.join(sorted(missing))}"
        )
    return reader, tuple(sorted(fields))


def _catalog(
    raw_bytes: bytes,
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, set[str]],
    dict[str, set[str]],
    tuple[str, ...],
]:
    reader, fields = _reader(raw_bytes, context="players", required=PLAYERS_REQUIRED)
    catalog: dict[str, dict[str, str]] = {}
    espn_index: dict[str, set[str]] = defaultdict(set)
    pfr_index: dict[str, set[str]] = defaultdict(set)
    for row_number, row in enumerate(reader, start=2):
        gsis_id = (row.get("gsis_id") or "").strip()
        if not gsis_id:
            continue
        if gsis_id in catalog:
            raise NflversePlayerSourceError(
                f"players contains duplicate GSIS ID {gsis_id!r} at row {row_number}"
            )
        clean = {key: (value or "").strip() for key, value in row.items() if key}
        catalog[gsis_id] = clean
        if clean.get("espn_id"):
            espn_index[clean["espn_id"]].add(gsis_id)
        if clean.get("pfr_id"):
            pfr_index[clean["pfr_id"]].add(gsis_id)
    if not catalog:
        raise NflversePlayerSourceError("players contains no GSIS identities")
    return catalog, espn_index, pfr_index, fields


def _review_row(
    *,
    source: str,
    season: int,
    team: str = "",
    source_player_id: str = "",
    source_secondary_id: str = "",
    player_name: str = "",
    position: str = "",
    issue: str,
    candidates: Iterable[str] = (),
    details: str = "",
) -> dict[str, Any]:
    return {
        "source": source,
        "season": season,
        "team": team,
        "source_player_id": source_player_id,
        "source_secondary_id": source_secondary_id,
        "player_name": player_name,
        "position": position,
        "issue": issue,
        "candidate_gsis_ids": "|".join(sorted(set(candidates))),
        "details": details,
    }


def _parse_roster(
    raw_bytes: bytes,
    *,
    season: int,
    catalog: Mapping[str, Mapping[str, str]],
    review: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    reader, fields = _reader(raw_bytes, context=f"roster {season}", required=ROSTER_REQUIRED)
    records: list[dict[str, Any]] = []
    seen_gsis: set[str] = set()
    for row_number, row in enumerate(reader, start=2):
        row_season = _integer_text(row.get("season"))
        if row_season != str(season):
            raise NflversePlayerSourceError(
                f"roster {season} row {row_number} has season {row_season!r}"
            )
        gsis_id = (row.get("gsis_id") or "").strip()
        team = _team(row.get("team"))
        full_name = (row.get("full_name") or "").strip()
        if not gsis_id:
            review.append(
                _review_row(
                    source="nflverse_roster",
                    season=season,
                    team=team,
                    player_name=full_name,
                    position=(row.get("position") or "").strip(),
                    issue="missing_gsis_id",
                    details=f"roster row {row_number}",
                )
            )
        elif gsis_id in seen_gsis:
            raise NflversePlayerSourceError(
                f"roster {season} contains duplicate GSIS ID {gsis_id!r}"
            )
        else:
            seen_gsis.add(gsis_id)
        player = catalog.get(gsis_id, {})
        roster_status = (row.get("status") or "").strip().upper()
        catalog_team = _team(player.get("latest_team"))
        catalog_status = (player.get("status") or "").strip().upper()
        current_status = catalog_status or roster_status
        current_team = (
            catalog_team
            if catalog_team and catalog_status in CATALOG_AFFILIATED_STATUSES
            else team
        )
        roster_espn = (row.get("espn_id") or "").strip()
        catalog_espn = player.get("espn_id", "")
        if gsis_id and roster_espn and catalog_espn and roster_espn != catalog_espn:
            review.append(
                _review_row(
                    source="nflverse_roster",
                    season=season,
                    team=team,
                    source_player_id=gsis_id,
                    source_secondary_id=roster_espn,
                    player_name=full_name,
                    position=(row.get("position") or "").strip(),
                    issue="catalog_espn_id_conflict",
                    candidates=(gsis_id,),
                    details=f"players.csv ESPN ID is {catalog_espn}",
                )
            )
        if gsis_id and catalog_team and current_team != team:
            review.append(
                _review_row(
                    source="nflverse_roster_players_catalog",
                    season=season,
                    team=current_team,
                    source_player_id=gsis_id,
                    player_name=full_name,
                    position=(row.get("position") or "").strip(),
                    issue="roster_catalog_affiliation_disagreement",
                    candidates=(gsis_id,),
                    details=(
                        f"raw roster={team}/{roster_status or 'blank'}; "
                        f"player catalog={catalog_team}/{catalog_status or 'blank'}; "
                        f"effective={current_team}/{current_status or 'blank'}"
                    ),
                )
            )
        elif gsis_id and catalog_status and catalog_status != roster_status:
            review.append(
                _review_row(
                    source="nflverse_roster_players_catalog",
                    season=season,
                    team=current_team,
                    source_player_id=gsis_id,
                    player_name=full_name,
                    position=(row.get("position") or "").strip(),
                    issue="roster_catalog_status_disagreement",
                    candidates=(gsis_id,),
                    details=(
                        f"raw roster={team}/{roster_status or 'blank'}; "
                        f"player catalog={catalog_team or 'blank'}/{catalog_status}; "
                        f"effective={current_team}/{current_status}"
                    ),
                )
            )

        def source_or_catalog(key: str) -> str:
            return (row.get(key) or "").strip() or player.get(key, "")

        records.append(
            {
                "season": season,
                "team": current_team,
                "roster_team": team,
                "roster_position": (row.get("position") or "").strip().upper(),
                "fantasy_position": _fantasy_position(row.get("position")),
                "depth_chart_position": (row.get("depth_chart_position") or "").strip(),
                "current_status": current_status,
                "roster_status": roster_status,
                "status_description": (row.get("status_description_abbr") or "").strip(),
                "full_name": full_name,
                "display_name": player.get("display_name", "") or full_name,
                "first_name": (row.get("first_name") or "").strip(),
                "last_name": (row.get("last_name") or "").strip(),
                "football_name": (row.get("football_name") or "").strip(),
                "gsis_id": gsis_id,
                "espn_id": source_or_catalog("espn_id"),
                "pfr_id": source_or_catalog("pfr_id"),
                "yahoo_id": (row.get("yahoo_id") or "").strip(),
                "sleeper_id": (row.get("sleeper_id") or "").strip(),
                "pff_id": source_or_catalog("pff_id"),
                "rotowire_id": (row.get("rotowire_id") or "").strip(),
                "fantasy_data_id": (row.get("fantasy_data_id") or "").strip(),
                "birth_date": (row.get("birth_date") or "").strip() or player.get("birth_date", ""),
                "years_experience": _integer_text(row.get("years_exp") or player.get("years_of_experience")),
                "roster_week": _integer_text(row.get("week")),
                "game_type": (row.get("game_type") or "").strip(),
                "catalog_latest_team": catalog_team,
                "catalog_status": catalog_status,
            }
        )
    if not records:
        raise NflversePlayerSourceError(f"roster {season} contains no records")
    return records, fields


def _parse_depth(
    raw_bytes: bytes,
    *,
    season: int,
    roster: Iterable[Mapping[str, Any]],
    catalog: Mapping[str, Mapping[str, str]],
    espn_index: Mapping[str, set[str]],
    review: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str], tuple[str, ...]]:
    reader, fields = _reader(
        raw_bytes, context=f"depth charts {season}", required=DEPTH_REQUIRED
    )
    latest_by_team: dict[str, str] = {}
    rows_by_team: dict[str, list[dict[str, str]]] = {}
    for row in reader:
        team = _team(row.get("team"))
        timestamp = (row.get("dt") or "").strip()
        if not team or not timestamp:
            continue
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as error:
            raise NflversePlayerSourceError(
                f"depth charts {season} has invalid timestamp {timestamp!r}"
            ) from error
        if parsed.tzinfo is None:
            raise NflversePlayerSourceError(
                f"depth charts {season} timestamp lacks a timezone: {timestamp!r}"
            )
        current = latest_by_team.get(team)
        if current is None or timestamp > current:
            latest_by_team[team] = timestamp
            rows_by_team[team] = [{key: (value or "") for key, value in row.items()}]
        elif timestamp == current:
            rows_by_team[team].append({key: (value or "") for key, value in row.items()})
    if not latest_by_team:
        raise NflversePlayerSourceError(f"depth charts {season} contains no dated records")

    roster_by_id = {
        str(row["gsis_id"]): row for row in roster if str(row.get("gsis_id", ""))
    }
    records: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str, str, str]] = set()
    for team in sorted(rows_by_team):
        for row in rows_by_team[team]:
            source_gsis = row["gsis_id"].strip()
            source_espn = row["espn_id"].strip()
            espn_candidates = set(espn_index.get(source_espn, set())) if source_espn else set()
            canonical = source_gsis
            identity_status = "resolved"
            identity_method = "gsis_id"
            issue = ""
            if source_gsis and len(espn_candidates) == 1 and source_gsis not in espn_candidates:
                identity_status = "review_required"
                identity_method = "conflicting_source_ids"
                issue = "gsis_espn_identity_conflict"
            elif not source_gsis and len(espn_candidates) == 1:
                canonical = next(iter(espn_candidates))
                identity_method = "unique_espn_id"
            elif not source_gsis and len(espn_candidates) > 1:
                identity_status = "review_required"
                identity_method = "ambiguous_espn_id"
                issue = "ambiguous_espn_id"
            elif not source_gsis:
                identity_status = "review_required"
                identity_method = "unresolved"
                issue = "missing_resolvable_player_id"

            roster_row = roster_by_id.get(canonical)
            on_team = bool(roster_row and roster_row["team"] == team)
            if canonical and roster_row and not on_team and not issue:
                identity_status = "review_required"
                issue = "depth_roster_team_mismatch"
            if canonical and canonical not in catalog and canonical not in roster_by_id and not issue:
                identity_status = "review_required"
                issue = "gsis_id_absent_from_players_and_roster"
            if issue:
                review.append(
                    _review_row(
                        source="nflverse_depth_charts",
                        season=season,
                        team=team,
                        source_player_id=source_gsis,
                        source_secondary_id=source_espn,
                        player_name=row["player_name"].strip(),
                        position=row["pos_abb"].strip(),
                        issue=issue,
                        candidates=espn_candidates | ({source_gsis} if source_gsis else set()),
                        details=f"latest team depth timestamp {latest_by_team[team]}",
                    )
                )
            key = (
                team,
                canonical or source_espn or row["player_name"].strip(),
                row["pos_grp"].strip(),
                row["pos_abb"].strip(),
                row["pos_rank"].strip(),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            records.append(
                {
                    "snapshot_dt": latest_by_team[team],
                    "team": team,
                    "player_name": row["player_name"].strip(),
                    "source_gsis_id": source_gsis,
                    "source_espn_id": source_espn,
                    "canonical_gsis_id": canonical,
                    "identity_status": identity_status,
                    "identity_method": identity_method,
                    "on_current_team_roster": str(on_team).lower(),
                    "current_status": roster_row["current_status"] if roster_row else "",
                    "roster_status": roster_row["roster_status"] if roster_row else "",
                    "pos_group": row["pos_grp"].strip(),
                    "pos_name": row["pos_name"].strip(),
                    "pos_abb": row["pos_abb"].strip().upper(),
                    "fantasy_position": _fantasy_position(row["pos_abb"]),
                    "pos_slot": _integer_text(row["pos_slot"]),
                    "pos_rank": _integer_text(row["pos_rank"]),
                }
            )
    return records, latest_by_team, fields


@dataclass
class _Usage:
    name: str = ""
    positions: Counter[str] | None = None
    games: set[str] | None = None
    attempts: float = 0.0
    sacks: float = 0.0
    carries: float = 0.0
    targets: float = 0.0
    receptions: float = 0.0
    air_yards: float = 0.0

    def __post_init__(self) -> None:
        self.positions = Counter() if self.positions is None else self.positions
        self.games = set() if self.games is None else self.games


def _historical_usage(
    *,
    query: NflversePlayerQuery,
    weekly_stats: Mapping[int, bytes],
    snap_counts: Mapping[int, bytes],
    pfr_index: Mapping[str, set[str]],
    review: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, tuple[str, ...]]]:
    usage: dict[tuple[int, str, str], _Usage] = {}
    source_fields: dict[str, tuple[str, ...]] = {}
    for season in query.history_seasons:
        reader, fields = _reader(
            weekly_stats[season],
            context=f"weekly player stats {season}",
            required=STATS_REQUIRED,
        )
        source_fields[f"weekly_stats_{season}"] = fields
        for row_number, row in enumerate(reader, start=2):
            if (row.get("season_type") or "").strip().upper() != "REG":
                continue
            if _integer_text(row.get("season")) != str(season):
                raise NflversePlayerSourceError(
                    f"weekly player stats {season} row {row_number} has a different season"
                )
            position = _fantasy_position(row.get("position"))
            if position not in {"QB", "RB", "WR", "TE"}:
                continue
            gsis_id = (row.get("player_id") or "").strip()
            team = _team(row.get("team"))
            if not gsis_id or not team:
                review.append(
                    _review_row(
                        source="nflverse_weekly_stats",
                        season=season,
                        team=team,
                        source_player_id=gsis_id,
                        player_name=(row.get("player_display_name") or "").strip(),
                        position=position,
                        issue="missing_player_or_team_id",
                        details=f"weekly stats row {row_number}",
                    )
                )
                continue
            key = (season, team, gsis_id)
            record = usage.setdefault(key, _Usage())
            record.name = (row.get("player_display_name") or "").strip() or record.name
            assert record.positions is not None and record.games is not None
            record.positions[position] += 1
            game_id = (row.get("game_id") or "").strip()
            if game_id:
                record.games.add(game_id)
            record.attempts += _number(row.get("attempts"))
            record.sacks += _number(row.get("sacks_suffered"))
            record.carries += _number(row.get("carries"))
            record.targets += _number(row.get("targets"))
            record.receptions += _number(row.get("receptions"))
            record.air_yards += _number(row.get("receiving_air_yards"))

    player_snaps: dict[tuple[int, str, str], float] = defaultdict(float)
    game_team_snaps: dict[tuple[int, str, str], float] = defaultdict(float)
    snap_review_seen: set[tuple[int, str, str, str]] = set()
    for season in query.history_seasons:
        reader, fields = _reader(
            snap_counts[season], context=f"snap counts {season}", required=SNAPS_REQUIRED
        )
        source_fields[f"snap_counts_{season}"] = fields
        for row_number, row in enumerate(reader, start=2):
            if (row.get("game_type") or "").strip().upper() != "REG":
                continue
            if _integer_text(row.get("season")) != str(season):
                raise NflversePlayerSourceError(
                    f"snap counts {season} row {row_number} has a different season"
                )
            team = _team(row.get("team"))
            game_id = (row.get("game_id") or "").strip()
            offense_snaps = _number(row.get("offense_snaps"))
            if team and game_id:
                key = (season, team, game_id)
                game_team_snaps[key] = max(game_team_snaps[key], offense_snaps)
            pfr_id = (row.get("pfr_player_id") or "").strip()
            candidates = pfr_index.get(pfr_id, set()) if pfr_id else set()
            if len(candidates) == 1:
                gsis_id = next(iter(candidates))
                player_snaps[(season, team, gsis_id)] += offense_snaps
            elif offense_snaps and _fantasy_position(row.get("position")):
                review_key = (
                    season,
                    team,
                    pfr_id,
                    (row.get("player") or "").strip(),
                )
                if review_key in snap_review_seen:
                    continue
                snap_review_seen.add(review_key)
                review.append(
                    _review_row(
                        source="pro_football_reference_snap_counts_via_nflverse",
                        season=season,
                        team=team,
                        source_player_id=pfr_id,
                        player_name=(row.get("player") or "").strip(),
                        position=(row.get("position") or "").strip(),
                        issue=("ambiguous_pfr_id" if len(candidates) > 1 else "unmapped_pfr_id"),
                        candidates=candidates,
                        details=f"one or more regular-season snap rows; first seen at row {row_number}",
                    )
                )

    team_snaps: dict[tuple[int, str], float] = defaultdict(float)
    for (season, team, _), snaps in game_team_snaps.items():
        team_snaps[(season, team)] += snaps

    resolved_usage: dict[tuple[int, str, str], tuple[_Usage, str]] = {}
    for key, value in usage.items():
        assert value.positions is not None
        position = sorted(value.positions.items(), key=lambda item: (-item[1], item[0]))[0][0]
        resolved_usage[key] = value, position

    qb_dropbacks: dict[tuple[int, str], float] = defaultdict(float)
    position_carries: dict[tuple[int, str, str], float] = defaultdict(float)
    position_targets: dict[tuple[int, str, str], float] = defaultdict(float)
    position_air: dict[tuple[int, str, str], float] = defaultdict(float)
    for (season, team, _), (value, position) in resolved_usage.items():
        if position == "QB":
            qb_dropbacks[(season, team)] += value.attempts + value.sacks
        position_carries[(season, team, position)] += value.carries
        position_targets[(season, team, position)] += value.targets
        position_air[(season, team, position)] += value.air_yards

    def ratio(numerator: float, denominator: float) -> str:
        return "" if denominator <= 0 else f"{numerator / denominator:.6f}"

    def count(value: float) -> str:
        return str(int(value)) if value.is_integer() else f"{value:.6f}"

    records: list[dict[str, Any]] = []
    for (season, team, gsis_id), (value, position) in sorted(resolved_usage.items()):
        assert value.games is not None
        dropbacks = value.attempts + value.sacks
        team_db = qb_dropbacks[(season, team)]
        team_carries = position_carries[(season, team, position)]
        team_targets = position_targets[(season, team, position)]
        team_air = position_air[(season, team, position)]
        snaps = player_snaps.get((season, team, gsis_id), 0.0)
        total_snaps = team_snaps.get((season, team), 0.0)
        records.append(
            {
                "season": season,
                "team": team,
                "gsis_id": gsis_id,
                "player_name": value.name,
                "position": position,
                "games": len(value.games),
                "attempts": count(value.attempts),
                "sacks_suffered": count(value.sacks),
                "dropbacks": count(dropbacks),
                "carries": count(value.carries),
                "targets": count(value.targets),
                "receptions": count(value.receptions),
                "receiving_air_yards": count(value.air_yards),
                "offense_snaps": count(snaps),
                "team_offense_snaps": count(total_snaps),
                "team_qb_dropbacks": count(team_db),
                "team_position_carries": count(team_carries),
                "team_position_targets": count(team_targets),
                "team_position_air_yards": count(team_air),
                "dropback_share": ratio(dropbacks, team_db) if position == "QB" else "",
                "carry_share_within_position": ratio(value.carries, team_carries),
                "target_share_within_position": ratio(value.targets, team_targets),
                "air_yards_share_within_position": ratio(value.air_yards, team_air),
                "offense_snap_share": ratio(snaps, total_snaps),
            }
        )
    if not records:
        raise NflversePlayerSourceError("historical stats contain no fantasy-position usage")
    return records, source_fields


def parse_nflverse_player_context(
    query: NflversePlayerQuery,
    *,
    players: bytes,
    roster: bytes,
    depth_charts: bytes,
    weekly_stats: Mapping[int, bytes],
    snap_counts: Mapping[int, bytes],
    retrieved_at: datetime,
    assets: Iterable[NflversePlayerAsset] = (),
) -> NflversePlayerContextSnapshot:
    """Validate source assets and normalize identity-safe player context."""

    retrieved_at = _utc_timestamp(retrieved_at)
    missing_stats = set(query.history_seasons) - set(weekly_stats)
    missing_snaps = set(query.history_seasons) - set(snap_counts)
    if missing_stats:
        raise NflversePlayerSourceError(f"missing weekly stats seasons: {sorted(missing_stats)}")
    if missing_snaps:
        raise NflversePlayerSourceError(f"missing snap-count seasons: {sorted(missing_snaps)}")

    review: list[dict[str, Any]] = []
    catalog, espn_index, pfr_index, player_fields = _catalog(players)
    current_roster, roster_fields = _parse_roster(
        roster, season=query.season, catalog=catalog, review=review
    )
    current_depth, latest_depth, depth_fields = _parse_depth(
        depth_charts,
        season=query.season,
        roster=current_roster,
        catalog=catalog,
        espn_index=espn_index,
        review=review,
    )
    history, history_fields = _historical_usage(
        query=query,
        weekly_stats=weekly_stats,
        snap_counts=snap_counts,
        pfr_index=pfr_index,
        review=review,
    )
    source_fields = {
        "players": player_fields,
        f"roster_{query.season}": roster_fields,
        f"depth_charts_{query.season}": depth_fields,
        **history_fields,
    }
    return NflversePlayerContextSnapshot(
        query=query,
        retrieved_at=retrieved_at,
        assets=tuple(sorted(assets, key=lambda item: (item.kind, item.season or 0))),
        current_roster=tuple(sorted(current_roster, key=lambda row: (row["team"], row["full_name"], row["gsis_id"]))),
        current_depth_chart=tuple(sorted(current_depth, key=lambda row: (row["team"], row["pos_group"], row["pos_slot"], row["pos_rank"], row["player_name"]))),
        historical_usage=tuple(history),
        identity_review=tuple(sorted(review, key=lambda row: (row["source"], row["season"], row["team"], row["player_name"], row["issue"]))),
        source_fields=source_fields,
        latest_depth_by_team=latest_depth,
    )


def _download_asset(
    url: str,
    *,
    timeout: float,
    max_bytes: int,
    urlopen_fn: Callable[..., Any],
) -> tuple[bytes, str | None, str | None]:
    request = Request(
        url,
        headers={
            "Accept": "text/csv,application/octet-stream",
            "User-Agent": "fantasy-football-26/0.1 (+source-attributed research)",
        },
    )
    try:
        with urlopen_fn(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
            last_modified = response.headers.get("Last-Modified")
            etag = response.headers.get("ETag")
    except HTTPError as error:
        raise NflversePlayerSourceError(
            f"nflverse returned HTTP {error.code} for {url}"
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        raise NflversePlayerSourceError(f"could not fetch nflverse asset {url}: {error}") from error
    if len(body) > max_bytes:
        raise NflversePlayerSourceError(f"nflverse asset exceeded {max_bytes:,} bytes: {url}")
    if not body:
        raise NflversePlayerSourceError(f"nflverse returned an empty asset: {url}")
    return body, last_modified, etag


def fetch_nflverse_player_context(
    query: NflversePlayerQuery,
    *,
    timeout: float = 60.0,
    workers: int = 6,
    retrieved_at: datetime | None = None,
    urlopen_fn: Callable[..., Any] = urlopen,
) -> NflversePlayerContextSnapshot:
    """Fetch current identity/depth plus prior usage and PFR snap releases."""

    if timeout <= 0:
        raise ValueError("nflverse timeout must be positive")
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise ValueError("workers must be a positive integer")
    retrieved_at = _utc_timestamp(retrieved_at or datetime.now(timezone.utc))
    specifications: list[tuple[str, int | None, str]] = [
        ("players", None, PLAYERS_URL),
        ("roster", query.season, ROSTER_URL.format(season=query.season)),
        ("depth_charts", query.season, DEPTH_URL.format(season=query.season)),
    ]
    for season in query.history_seasons:
        specifications.extend(
            (
                ("weekly_stats", season, WEEKLY_STATS_URL.format(season=season)),
                ("snap_counts", season, SNAP_COUNTS_URL.format(season=season)),
            )
        )

    def fetch(specification: tuple[str, int | None, str]) -> NflversePlayerAsset:
        kind, season, url = specification
        body, last_modified, etag = _download_asset(
            url,
            timeout=timeout,
            max_bytes=MAX_BYTES[kind],
            urlopen_fn=urlopen_fn,
        )
        return NflversePlayerAsset(
            kind=kind,
            season=season,
            url=url,
            raw_bytes=body,
            response_last_modified=last_modified,
            response_etag=etag,
        )

    assets: list[NflversePlayerAsset] = []
    with ThreadPoolExecutor(max_workers=min(workers, len(specifications))) as executor:
        futures = {executor.submit(fetch, spec): spec for spec in specifications}
        for future in as_completed(futures):
            assets.append(future.result())
    by_kind_season = {(asset.kind, asset.season): asset.raw_bytes for asset in assets}
    return parse_nflverse_player_context(
        query,
        players=by_kind_season[("players", None)],
        roster=by_kind_season[("roster", query.season)],
        depth_charts=by_kind_season[("depth_charts", query.season)],
        weekly_stats={season: by_kind_season[("weekly_stats", season)] for season in query.history_seasons},
        snap_counts={season: by_kind_season[("snap_counts", season)] for season in query.history_seasons},
        retrieved_at=retrieved_at,
        assets=assets,
    )


def _csv_bytes(fields: tuple[str, ...], rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def write_nflverse_player_context_snapshot(
    snapshot: NflversePlayerContextSnapshot,
    root: str | Path,
) -> Path:
    """Atomically publish raw inputs, normalized tables, and provenance."""

    timestamp = snapshot.retrieved_at.strftime("%Y%m%dT%H%M%S.%fZ")
    parent = Path(root) / SOURCE_ID / "player_context" / str(snapshot.query.season)
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"nflverse player-context snapshot already exists: {destination}")

    artifacts = {
        "current_roster.csv": _csv_bytes(CURRENT_ROSTER_FIELDS, snapshot.current_roster),
        "current_depth_chart.csv": _csv_bytes(DEPTH_FIELDS, snapshot.current_depth_chart),
        "historical_usage.csv": _csv_bytes(HISTORY_FIELDS, snapshot.historical_usage),
        "source_identity_review.csv": _csv_bytes(REVIEW_FIELDS, snapshot.identity_review),
    }
    raw_manifest = {
        asset.filename: {
            "kind": asset.kind,
            "season": asset.season,
            "url": asset.url,
            "bytes": len(asset.raw_bytes),
            "sha256": asset.sha256,
            "http": {
                "last_modified": asset.response_last_modified,
                "etag": asset.response_etag,
            },
        }
        for asset in snapshot.assets
    }
    fantasy_roster = [row for row in snapshot.current_roster if row["fantasy_position"]]
    manifest = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "source": {
            "id": SOURCE_ID,
            "name": SOURCE_NAME,
            "repository": SOURCE_REPOSITORY,
            "players_repository": PLAYERS_REPOSITORY,
            "rosters_repository": ROSTERS_REPOSITORY,
            "license": SOURCE_LICENSE,
            "snap_count_origin": "Pro Football Reference via nflverse snap_counts release",
        },
        "query": {
            "season": snapshot.query.season,
            "history_seasons": list(snapshot.query.history_seasons),
            "season_type": "REG",
        },
        "retrieved_at": _iso_z(snapshot.retrieved_at),
        "methodology": {
            "identity": "GSIS primary key; unique ESPN fallback for depth only; no name joins",
            "current_affiliation": "raw roster_team/roster_status are preserved; team/current_status use the independently refreshed player catalog when it reports a current club affiliation; every disagreement is queued for review",
            "depth": "latest available timestamp selected independently for each team",
            "usage": "weekly regular-season box-score opportunities aggregated by GSIS ID, team, and season",
            "snaps": "PFR player ID joined through players.csv; team snaps inferred as each team-game maximum offensive snap count",
        },
        "quality": {
            "roster_rows": len(snapshot.current_roster),
            "roster_team_count": len({row["roster_team"] for row in snapshot.current_roster}),
            "current_team_count": len({row["team"] for row in snapshot.current_roster}),
            "fantasy_roster_rows": len(fantasy_roster),
            "active_fantasy_roster_rows": sum(row["current_status"] == "ACT" for row in fantasy_roster),
            "current_status_counts": dict(sorted(Counter(row["current_status"] for row in snapshot.current_roster).items())),
            "roster_status_counts": dict(sorted(Counter(row["roster_status"] for row in snapshot.current_roster).items())),
            "roster_catalog_affiliation_review_rows": sum(
                row["issue"] == "roster_catalog_affiliation_disagreement"
                for row in snapshot.identity_review
            ),
            "roster_catalog_status_review_rows": sum(
                row["issue"] == "roster_catalog_status_disagreement"
                for row in snapshot.identity_review
            ),
            "latest_depth_by_team": dict(sorted(snapshot.latest_depth_by_team.items())),
            "depth_team_count": len(snapshot.latest_depth_by_team),
            "latest_depth_rows": len(snapshot.current_depth_chart),
            "historical_usage_rows": len(snapshot.historical_usage),
            "identity_review_rows": len(snapshot.identity_review),
            "depth_review_rows": sum(row["source"] == "nflverse_depth_charts" for row in snapshot.identity_review),
            "snap_review_rows": sum(row["source"] == "pro_football_reference_snap_counts_via_nflverse" for row in snapshot.identity_review),
        },
        "source_fields": {key: list(value) for key, value in snapshot.source_fields.items()},
        "artifacts": {
            "raw": raw_manifest,
            "normalized": {
                name: {
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "fields": list(
                        {
                            "current_roster.csv": CURRENT_ROSTER_FIELDS,
                            "current_depth_chart.csv": DEPTH_FIELDS,
                            "historical_usage.csv": HISTORY_FIELDS,
                            "source_identity_review.csv": REVIEW_FIELDS,
                        }[name]
                    ),
                }
                for name, payload in artifacts.items()
            },
        },
    }

    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
    try:
        raw_directory = staging / "raw"
        raw_directory.mkdir()
        for asset in snapshot.assets:
            (raw_directory / asset.filename).write_bytes(asset.raw_bytes)
        for name, payload in artifacts.items():
            (staging / name).write_bytes(payload)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
