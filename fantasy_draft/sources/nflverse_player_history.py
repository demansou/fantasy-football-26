"""Reproducible historical player-state inputs for availability and role tests.

The adapter preserves nflverse weekly rosters, opening depth charts, and weekly
opportunity data.  It deliberately keeps the weaker temporal precision of the
pre-2025 depth schema visible instead of pretending those rows have timestamps.
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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SOURCE_ID = "nflverse"
ADAPTER_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"
SOURCE_REPOSITORY = "https://github.com/nflverse/nflverse-data"
SOURCE_LICENSE = "CC-BY-4.0"

WEEKLY_ROSTER_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/"
    "roster_weekly_{season}.csv"
)
DEPTH_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/depth_charts/"
    "depth_charts_{season}.csv"
)
WEEKLY_STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/stats_player/"
    "stats_player_week_{season}.csv"
)
SCHEDULE_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"

MAX_BYTES = {
    "weekly_roster": 25_000_000,
    "depth": 90_000_000,
    "weekly_stats": 25_000_000,
    "schedule": 5_000_000,
}

WEEKLY_ROSTER_REQUIRED = {
    "season", "team", "position", "status", "full_name", "gsis_id", "week",
    "game_type", "status_description_abbr",
}
OLD_DEPTH_REQUIRED = {
    "season", "club_code", "week", "game_type", "depth_team", "formation",
    "gsis_id", "position", "depth_position", "full_name",
}
DATED_DEPTH_REQUIRED = {
    "dt", "team", "player_name", "gsis_id", "pos_grp", "pos_abb", "pos_slot",
    "pos_rank",
}
WEEKLY_STATS_REQUIRED = {
    "player_id", "player_display_name", "position", "season", "week",
    "season_type", "team", "attempts", "sacks_suffered", "carries", "targets",
}
SCHEDULE_REQUIRED = {
    "game_id", "season", "game_type", "week", "gameday", "away_team",
    "home_team",
}

WEEKLY_ROSTER_FIELDS = (
    "season", "week", "team", "position", "gsis_id", "player_name", "status",
    "status_description",
)
OPENING_DEPTH_FIELDS = (
    "season", "cutoff", "team", "position", "gsis_id", "player_name",
    "depth_position", "depth_slot", "depth_rank", "source_schema",
    "source_timestamp", "temporal_precision",
)
WEEKLY_OPPORTUNITY_FIELDS = (
    "season", "week", "team", "position", "gsis_id", "player_name", "dropbacks",
    "carries", "targets",
)
TEAM_SCHEDULE_FIELDS = (
    "season", "week", "gameday", "game_id", "team", "opponent", "home_away",
)
REVIEW_FIELDS = (
    "source", "season", "week", "team", "gsis_id", "player_name", "position",
    "issue", "details",
)

TEAM_ALIASES = {
    "ARZ": "ARI", "BLT": "BAL", "CLV": "CLE", "HST": "HOU", "JAC": "JAX",
    "LA": "LAR", "OAK": "LV", "SD": "LAC", "STL": "LAR", "WSH": "WAS",
}


class NflversePlayerHistoryError(RuntimeError):
    """Raised when the historical player-state source contract is violated."""


@dataclass(frozen=True)
class NflversePlayerHistoryQuery:
    availability_seasons: tuple[int, ...]
    role_target_seasons: tuple[int, ...]
    role_history_lookback: int = 3
    expected_team_count: int = 32
    forecast_season: int | None = None

    def __post_init__(self) -> None:
        for label, seasons in (
            ("availability", self.availability_seasons),
            ("role target", self.role_target_seasons),
        ):
            if not seasons:
                raise ValueError(f"{label} seasons cannot be empty")
            if any(isinstance(item, bool) or not isinstance(item, int) for item in seasons):
                raise ValueError(f"{label} seasons must be integers")
            if any(not 2002 <= item <= 2100 for item in seasons):
                raise ValueError(f"{label} seasons must be between 2002 and 2100")
            if len(set(seasons)) != len(seasons):
                raise ValueError(f"{label} seasons cannot contain duplicates")
        if (
            isinstance(self.role_history_lookback, bool)
            or not isinstance(self.role_history_lookback, int)
            or not 1 <= self.role_history_lookback <= 10
        ):
            raise ValueError("role_history_lookback must be an integer from 1 to 10")
        if (
            isinstance(self.expected_team_count, bool)
            or not isinstance(self.expected_team_count, int)
            or not 1 <= self.expected_team_count <= 32
        ):
            raise ValueError("expected_team_count must be an integer from 1 to 32")
        targets = tuple(sorted(self.role_target_seasons))
        availability = tuple(sorted(self.availability_seasons))
        if not set(targets).issubset(availability):
            raise ValueError("role target seasons must be covered by availability seasons")
        object.__setattr__(self, "availability_seasons", availability)
        object.__setattr__(self, "role_target_seasons", targets)
        forecast = self.forecast_season
        if forecast is None:
            forecast = max(targets) + 1
        if isinstance(forecast, bool) or not isinstance(forecast, int) or not 2002 <= forecast <= 2100:
            raise ValueError("forecast_season must be an integer from 2002 to 2100")
        object.__setattr__(self, "forecast_season", forecast)

    @property
    def stat_seasons(self) -> tuple[int, ...]:
        first = min(self.role_target_seasons) - self.role_history_lookback
        return tuple(range(first, max(self.role_target_seasons) + 1))


@dataclass(frozen=True)
class NflversePlayerHistoryAsset:
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
        if self.kind == "schedule":
            return "games.csv"
        prefixes = {
            "weekly_roster": "roster_weekly",
            "depth": "depth_charts",
            "weekly_stats": "stats_player_week",
        }
        return f"{prefixes[self.kind]}_{self.season}.csv"


@dataclass(frozen=True)
class NflversePlayerHistorySnapshot:
    query: NflversePlayerHistoryQuery
    retrieved_at: datetime
    assets: tuple[NflversePlayerHistoryAsset, ...]
    weekly_rosters: tuple[Mapping[str, Any], ...]
    opening_depth: tuple[Mapping[str, Any], ...]
    weekly_opportunities: tuple[Mapping[str, Any], ...]
    team_schedule: tuple[Mapping[str, Any], ...]
    source_review: tuple[Mapping[str, Any], ...]
    opening_cutoffs: Mapping[int, str]
    source_fields: Mapping[str, tuple[str, ...]]


def _team(value: str | None) -> str:
    observed = (value or "").strip().upper()
    return TEAM_ALIASES.get(observed, observed)


def _position(value: str | None) -> str:
    observed = (value or "").strip().upper()
    if observed in {"RB", "HB", "FB"}:
        return "RB"
    return observed if observed in {"QB", "WR", "TE"} else ""


def _integer(value: str | None, context: str) -> int:
    try:
        number = float((value or "").strip())
    except ValueError as error:
        raise NflversePlayerHistoryError(f"{context} must be numeric") from error
    if not math.isfinite(number) or not number.is_integer():
        raise NflversePlayerHistoryError(f"{context} must be a finite integer")
    return int(number)


def _number(value: str | None, context: str) -> float:
    if value is None or not value.strip():
        return 0.0
    try:
        number = float(value)
    except ValueError as error:
        raise NflversePlayerHistoryError(f"{context} must be numeric") from error
    if not math.isfinite(number):
        raise NflversePlayerHistoryError(f"{context} must be finite")
    return number


def _reader(
    raw: bytes, *, context: str, required: set[str]
) -> tuple[csv.DictReader, tuple[str, ...]]:
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    except UnicodeDecodeError as error:
        raise NflversePlayerHistoryError(f"{context} is not UTF-8 CSV") from error
    fields = tuple(reader.fieldnames or ())
    missing = required - set(fields)
    if missing:
        raise NflversePlayerHistoryError(
            f"{context} is missing fields: {', '.join(sorted(missing))}"
        )
    return reader, tuple(sorted(fields))


def _review(
    source: str,
    *,
    season: int,
    issue: str,
    row: Mapping[str, Any],
    week: int | str = "",
    team: str = "",
    position: str = "",
    details: str = "",
) -> dict[str, Any]:
    return {
        "source": source,
        "season": season,
        "week": week,
        "team": team,
        "gsis_id": str(row.get("gsis_id") or row.get("player_id") or "").strip(),
        "player_name": str(
            row.get("full_name") or row.get("player_name")
            or row.get("player_display_name") or ""
        ).strip(),
        "position": position,
        "issue": issue,
        "details": details,
    }


def _parse_schedule(
    schedule: bytes,
    *,
    targets: Iterable[int],
    schedule_seasons: Iterable[int],
) -> tuple[dict[int, str], list[dict[str, Any]], tuple[str, ...]]:
    reader, fields = _reader(schedule, context="schedule", required=SCHEDULE_REQUIRED)
    first_days: dict[int, date] = {}
    target_set = set(targets)
    schedule_set = set(schedule_seasons)
    records: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str]] = set()
    for row in reader:
        try:
            season = int(row["season"])
            week = int(row["week"])
        except ValueError:
            continue
        if row["game_type"] != "REG" or not 1 <= week <= 18:
            continue
        try:
            gameday = date.fromisoformat(row["gameday"])
        except ValueError as error:
            raise NflversePlayerHistoryError(
                f"schedule has invalid gameday {row['gameday']!r}"
            ) from error
        if season in target_set and week == 1 and (
            season not in first_days or gameday < first_days[season]
        ):
            first_days[season] = gameday
        if season not in schedule_set:
            continue
        away = _team(row.get("away_team"))
        home = _team(row.get("home_team"))
        game_id = row["game_id"].strip()
        if not away or not home or away == home or not game_id:
            raise NflversePlayerHistoryError(
                f"schedule has invalid teams/game ID for {season} Week {week}"
            )
        for team, opponent, home_away in (
            (away, home, "away"), (home, away, "home")
        ):
            key = season, week, team
            if key in seen:
                raise NflversePlayerHistoryError(
                    f"schedule has duplicate {season} Week {week} team {team}"
                )
            seen.add(key)
            records.append({
                "season": season,
                "week": week,
                "gameday": gameday.isoformat(),
                "game_id": game_id,
                "team": team,
                "opponent": opponent,
                "home_away": home_away,
            })
    missing = target_set - set(first_days)
    if missing:
        raise NflversePlayerHistoryError(f"schedule lacks Week 1 openers for {sorted(missing)}")
    cutoffs = {
        season: f"{first_days[season].isoformat()}T00:00:00Z"
        for season in sorted(first_days)
    }
    missing_schedule = schedule_set - {int(row["season"]) for row in records}
    if missing_schedule:
        raise NflversePlayerHistoryError(
            f"schedule lacks regular-season games for {sorted(missing_schedule)}"
        )
    return cutoffs, records, fields


def _parse_weekly_rosters(
    raws: Mapping[int, bytes], review: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, tuple[str, ...]]]:
    records: list[dict[str, Any]] = []
    source_fields: dict[str, tuple[str, ...]] = {}
    seen: set[tuple[int, int, str, str]] = set()
    for season in sorted(raws):
        reader, fields = _reader(
            raws[season], context=f"weekly roster {season}", required=WEEKLY_ROSTER_REQUIRED
        )
        source_fields[f"weekly_roster_{season}"] = fields
        for row_number, row in enumerate(reader, start=2):
            if row["game_type"].strip().upper() != "REG":
                continue
            position = _position(row.get("position"))
            if not position:
                continue
            week = _integer(row.get("week"), f"weekly roster {season} row {row_number} week")
            if not 1 <= week <= 18:
                continue
            gsis_id = row["gsis_id"].strip()
            team = _team(row.get("team"))
            if not gsis_id:
                review.append(_review(
                    "nflverse_weekly_rosters", season=season, week=week, team=team,
                    position=position, issue="missing_gsis_id", row=row,
                    details=f"source row {row_number}",
                ))
                continue
            key = season, week, team, gsis_id
            if key in seen:
                review.append(_review(
                    "nflverse_weekly_rosters", season=season, week=week, team=team,
                    position=position, issue="duplicate_team_player_week", row=row,
                    details=f"source row {row_number} omitted from normalized table",
                ))
                continue
            seen.add(key)
            records.append({
                "season": season,
                "week": week,
                "team": team,
                "position": position,
                "gsis_id": gsis_id,
                "player_name": row["full_name"].strip(),
                "status": row["status"].strip().upper(),
                "status_description": row["status_description_abbr"].strip().upper(),
            })
    if not records:
        raise NflversePlayerHistoryError("weekly rosters contain no skill-position rows")
    return records, source_fields


def _parse_opening_depth(
    raws: Mapping[int, bytes],
    cutoffs: Mapping[int, str],
    review: list[dict[str, Any]],
    *,
    expected_team_count: int,
) -> tuple[list[dict[str, Any]], dict[str, tuple[str, ...]]]:
    records: list[dict[str, Any]] = []
    source_fields: dict[str, tuple[str, ...]] = {}
    for season in sorted(raws):
        probe = csv.DictReader(io.StringIO(raws[season].decode("utf-8-sig"), newline=""))
        fields_seen = set(probe.fieldnames or ())
        if DATED_DEPTH_REQUIRED.issubset(fields_seen):
            reader, fields = _reader(
                raws[season], context=f"depth {season}", required=DATED_DEPTH_REQUIRED
            )
            source_fields[f"depth_{season}"] = fields
            cutoff = cutoffs[season]
            latest_by_team: dict[str, str] = {}
            rows_by_team: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in reader:
                timestamp = row["dt"].strip()
                team = _team(row.get("team"))
                if not timestamp or not team or timestamp >= cutoff:
                    continue
                current = latest_by_team.get(team)
                if current is None or timestamp > current:
                    latest_by_team[team] = timestamp
                    rows_by_team[team] = [row]
                elif timestamp == current:
                    rows_by_team[team].append(row)
            if len(latest_by_team) != expected_team_count:
                raise NflversePlayerHistoryError(
                    f"dated depth {season} has {len(latest_by_team)} teams before {cutoff}; "
                    f"expected {expected_team_count}"
                )
            source_rows = (
                (team, latest_by_team[team], row) for team in sorted(rows_by_team)
                for row in rows_by_team[team]
            )
            for team, timestamp, row in source_rows:
                position = _position(row.get("pos_abb"))
                if not position:
                    continue
                gsis_id = row["gsis_id"].strip()
                if not gsis_id:
                    review.append(_review(
                        "nflverse_depth_charts", season=season, team=team,
                        position=position, issue="missing_gsis_id", row=row,
                        details=f"opening timestamp {timestamp}",
                    ))
                    continue
                records.append({
                    "season": season, "cutoff": cutoff, "team": team,
                    "position": position, "gsis_id": gsis_id,
                    "player_name": row["player_name"].strip(),
                    "depth_position": row["pos_abb"].strip().upper(),
                    "depth_slot": str(_integer(row.get("pos_slot"), "depth slot")),
                    "depth_rank": str(_integer(row.get("pos_rank"), "depth rank")),
                    "source_schema": "dated_2025_plus",
                    "source_timestamp": timestamp,
                    "temporal_precision": "timestamp_before_first_regular_season_gameday",
                })
        elif OLD_DEPTH_REQUIRED.issubset(fields_seen):
            reader, fields = _reader(
                raws[season], context=f"depth {season}", required=OLD_DEPTH_REQUIRED
            )
            source_fields[f"depth_{season}"] = fields
            cutoff = cutoffs[season]
            for row in reader:
                if (
                    row["game_type"].strip().upper() != "REG"
                    or _integer(row.get("week"), f"depth {season} week") != 1
                    or row["formation"].strip().lower() != "offense"
                ):
                    continue
                position = _position(row.get("position"))
                if not position:
                    continue
                team = _team(row.get("club_code"))
                gsis_id = row["gsis_id"].strip()
                if not gsis_id:
                    review.append(_review(
                        "nflverse_depth_charts", season=season, week=1, team=team,
                        position=position, issue="missing_gsis_id", row=row,
                        details="old schema Week 1 opening row",
                    ))
                    continue
                records.append({
                    "season": season, "cutoff": cutoff, "team": team,
                    "position": position, "gsis_id": gsis_id,
                    "player_name": row["full_name"].strip(),
                    "depth_position": row["depth_position"].strip().upper(),
                    "depth_slot": "",
                    "depth_rank": str(_integer(row.get("depth_team"), "depth team/rank")),
                    "source_schema": "weekly_pre_2025",
                    "source_timestamp": "",
                    "temporal_precision": "week_1_label_only_no_source_timestamp",
                })
        else:
            raise NflversePlayerHistoryError(f"depth {season} has an unknown schema")
    deduplicated: dict[tuple[int, str, str, str], dict[str, Any]] = {}
    for row in records:
        key = int(row["season"]), str(row["team"]), str(row["position"]), str(row["gsis_id"])
        old = deduplicated.get(key)
        if old is None or int(row["depth_rank"]) < int(old["depth_rank"]):
            deduplicated[key] = row
    if not deduplicated:
        raise NflversePlayerHistoryError("opening depth contains no resolved skill players")
    for season in raws:
        team_count = len({
            row["team"] for row in deduplicated.values() if row["season"] == season
        })
        if team_count != expected_team_count:
            raise NflversePlayerHistoryError(
                f"opening depth {season} has {team_count} teams; expected {expected_team_count}"
            )
    return list(deduplicated.values()), source_fields


def _parse_weekly_opportunities(
    raws: Mapping[int, bytes], review: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, tuple[str, ...]]]:
    records: list[dict[str, Any]] = []
    fields_by_source: dict[str, tuple[str, ...]] = {}
    seen: set[tuple[int, int, str, str]] = set()
    for season in sorted(raws):
        reader, fields = _reader(
            raws[season], context=f"weekly stats {season}", required=WEEKLY_STATS_REQUIRED
        )
        fields_by_source[f"weekly_stats_{season}"] = fields
        for row_number, row in enumerate(reader, start=2):
            if row["season_type"].strip().upper() != "REG":
                continue
            position = _position(row.get("position"))
            if not position:
                continue
            week = _integer(row.get("week"), f"weekly stats {season} row {row_number} week")
            if not 1 <= week <= 18:
                continue
            player_id = row["player_id"].strip()
            team = _team(row.get("team"))
            if not player_id:
                review.append(_review(
                    "nflverse_weekly_stats", season=season, week=week, team=team,
                    position=position, issue="missing_gsis_id", row=row,
                    details=f"source row {row_number}",
                ))
                continue
            key = season, week, team, player_id
            if key in seen:
                raise NflversePlayerHistoryError(
                    f"weekly stats has duplicate player/team/week {key}"
                )
            seen.add(key)
            records.append({
                "season": season, "week": week, "team": team,
                "position": position, "gsis_id": player_id,
                "player_name": row["player_display_name"].strip(),
                "dropbacks": f"{_number(row.get('attempts'), 'attempts') + _number(row.get('sacks_suffered'), 'sacks_suffered'):.6f}",
                "carries": f"{_number(row.get('carries'), 'carries'):.6f}",
                "targets": f"{_number(row.get('targets'), 'targets'):.6f}",
            })
    if not records:
        raise NflversePlayerHistoryError("weekly stats contain no skill-position opportunities")
    return records, fields_by_source


def parse_nflverse_player_history(
    query: NflversePlayerHistoryQuery,
    *,
    weekly_rosters: Mapping[int, bytes],
    depth_charts: Mapping[int, bytes],
    weekly_stats: Mapping[int, bytes],
    schedule: bytes,
    retrieved_at: datetime,
    assets: Iterable[NflversePlayerHistoryAsset] = (),
) -> NflversePlayerHistorySnapshot:
    """Validate raw assets and build time-labeled historical player inputs."""

    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    expected = {
        "weekly rosters": (set(query.availability_seasons), set(weekly_rosters)),
        "depth charts": (set(query.role_target_seasons), set(depth_charts)),
        "weekly stats": (set(query.stat_seasons), set(weekly_stats)),
    }
    for label, (wanted, observed) in expected.items():
        if wanted != observed:
            raise NflversePlayerHistoryError(
                f"{label} seasons mismatch: expected {sorted(wanted)}, got {sorted(observed)}"
            )
    review: list[dict[str, Any]] = []
    schedule_seasons = set(query.availability_seasons) | {int(query.forecast_season)}
    cutoffs, team_schedule, schedule_fields = _parse_schedule(
        schedule,
        targets=query.role_target_seasons,
        schedule_seasons=schedule_seasons,
    )
    rosters, roster_fields = _parse_weekly_rosters(weekly_rosters, review)
    depth, depth_fields = _parse_opening_depth(
        depth_charts, cutoffs, review, expected_team_count=query.expected_team_count
    )
    opportunities, stats_fields = _parse_weekly_opportunities(weekly_stats, review)
    return NflversePlayerHistorySnapshot(
        query=query,
        retrieved_at=retrieved_at.astimezone(timezone.utc),
        assets=tuple(sorted(assets, key=lambda item: (item.kind, item.season or 0))),
        weekly_rosters=tuple(sorted(
            rosters, key=lambda row: (row["season"], row["week"], row["team"], row["gsis_id"])
        )),
        opening_depth=tuple(sorted(
            depth, key=lambda row: (row["season"], row["team"], row["position"], int(row["depth_rank"]), row["gsis_id"])
        )),
        weekly_opportunities=tuple(sorted(
            opportunities, key=lambda row: (row["season"], row["week"], row["team"], row["position"], row["gsis_id"])
        )),
        team_schedule=tuple(sorted(
            team_schedule, key=lambda row: (row["season"], row["week"], row["team"])
        )),
        source_review=tuple(sorted(
            review, key=lambda row: (row["source"], row["season"], str(row["week"]), row["team"], row["player_name"])
        )),
        opening_cutoffs=cutoffs,
        source_fields={"schedule": schedule_fields, **roster_fields, **depth_fields, **stats_fields},
    )


def _download(
    url: str,
    *,
    max_bytes: int,
    timeout: float,
    urlopen_fn: Callable[..., Any],
) -> tuple[bytes, str | None, str | None]:
    request = Request(url, headers={
        "Accept": "text/csv,application/octet-stream",
        "User-Agent": "fantasy-football-26/0.1 (+source-attributed research)",
    })
    try:
        with urlopen_fn(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
            modified = response.headers.get("Last-Modified")
            etag = response.headers.get("ETag")
    except HTTPError as error:
        raise NflversePlayerHistoryError(f"HTTP {error.code} for {url}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise NflversePlayerHistoryError(f"could not fetch {url}: {error}") from error
    if not raw or len(raw) > max_bytes:
        raise NflversePlayerHistoryError(
            f"asset is empty or exceeds {max_bytes:,} bytes: {url}"
        )
    return raw, modified, etag


def fetch_nflverse_player_history(
    query: NflversePlayerHistoryQuery,
    *,
    timeout: float = 90.0,
    workers: int = 6,
    retrieved_at: datetime | None = None,
    urlopen_fn: Callable[..., Any] = urlopen,
) -> NflversePlayerHistorySnapshot:
    """Fetch and normalize historical weekly roster/depth/opportunity assets."""

    if timeout <= 0 or isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise ValueError("timeout and workers must be positive")
    specs: list[tuple[str, int | None, str]] = [("schedule", None, SCHEDULE_URL)]
    specs.extend(
        ("weekly_roster", season, WEEKLY_ROSTER_URL.format(season=season))
        for season in query.availability_seasons
    )
    specs.extend(
        ("depth", season, DEPTH_URL.format(season=season))
        for season in query.role_target_seasons
    )
    specs.extend(
        ("weekly_stats", season, WEEKLY_STATS_URL.format(season=season))
        for season in query.stat_seasons
    )

    def load(spec: tuple[str, int | None, str]) -> NflversePlayerHistoryAsset:
        kind, season, url = spec
        raw, modified, etag = _download(
            url, max_bytes=MAX_BYTES[kind], timeout=timeout, urlopen_fn=urlopen_fn
        )
        return NflversePlayerHistoryAsset(kind, url, raw, season, modified, etag)

    assets: list[NflversePlayerHistoryAsset] = []
    with ThreadPoolExecutor(max_workers=min(workers, len(specs))) as executor:
        futures = [executor.submit(load, spec) for spec in specs]
        for future in as_completed(futures):
            assets.append(future.result())
    lookup = {(asset.kind, asset.season): asset.raw_bytes for asset in assets}
    return parse_nflverse_player_history(
        query,
        weekly_rosters={s: lookup[("weekly_roster", s)] for s in query.availability_seasons},
        depth_charts={s: lookup[("depth", s)] for s in query.role_target_seasons},
        weekly_stats={s: lookup[("weekly_stats", s)] for s in query.stat_seasons},
        schedule=lookup[("schedule", None)],
        retrieved_at=retrieved_at or datetime.now(timezone.utc),
        assets=assets,
    )


def _csv_bytes(fields: tuple[str, ...], rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def write_nflverse_player_history_snapshot(
    snapshot: NflversePlayerHistorySnapshot, root: str | Path
) -> Path:
    """Atomically publish raw assets, normalized tables, hashes, and limitations."""

    timestamp = snapshot.retrieved_at.strftime("%Y%m%dT%H%M%S.%fZ")
    parent = Path(root) / SOURCE_ID / "player_history" / timestamp
    destination = parent
    parent.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"player-history snapshot exists: {destination}")
    artifacts = {
        "weekly_rosters.csv": _csv_bytes(WEEKLY_ROSTER_FIELDS, snapshot.weekly_rosters),
        "opening_depth.csv": _csv_bytes(OPENING_DEPTH_FIELDS, snapshot.opening_depth),
        "weekly_opportunities.csv": _csv_bytes(WEEKLY_OPPORTUNITY_FIELDS, snapshot.weekly_opportunities),
        "team_schedule.csv": _csv_bytes(TEAM_SCHEDULE_FIELDS, snapshot.team_schedule),
        "source_review.csv": _csv_bytes(REVIEW_FIELDS, snapshot.source_review),
    }
    raw_manifest = {
        asset.filename: {
            "kind": asset.kind, "season": asset.season, "url": asset.url,
            "bytes": len(asset.raw_bytes), "sha256": asset.sha256,
            "http": {"last_modified": asset.response_last_modified, "etag": asset.response_etag},
        }
        for asset in snapshot.assets
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "source": {"id": SOURCE_ID, "repository": SOURCE_REPOSITORY, "license": SOURCE_LICENSE},
        "retrieved_at": snapshot.retrieved_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "query": {
            "availability_seasons": list(snapshot.query.availability_seasons),
            "role_target_seasons": list(snapshot.query.role_target_seasons),
            "role_history_lookback": snapshot.query.role_history_lookback,
            "expected_team_count": snapshot.query.expected_team_count,
            "forecast_season": snapshot.query.forecast_season,
            "stat_seasons": list(snapshot.query.stat_seasons),
        },
        "opening_cutoffs": {str(key): value for key, value in snapshot.opening_cutoffs.items()},
        "methodology": {
            "identity": "GSIS only; no player-name joins",
            "weekly_rosters": "regular-season Weeks 1-18, QB/RB/WR/TE only",
            "opening_depth_pre_2025": "REG Week 1 rows; source has no retrieval timestamp, so temporal precision is explicitly weaker",
            "opening_depth_2025_plus": "latest per-team timestamp strictly before 00:00 UTC on the first regular-season gameday",
            "weekly_opportunities": "regular-season attempts plus sacks, carries, and targets by GSIS ID",
            "team_schedule": "one row per team/game for historical bye exclusion and explicit forecast-season bye weeks",
        },
        "quality": {
            "weekly_roster_rows": len(snapshot.weekly_rosters),
            "opening_depth_rows": len(snapshot.opening_depth),
            "weekly_opportunity_rows": len(snapshot.weekly_opportunities),
            "team_schedule_rows": len(snapshot.team_schedule),
            "forecast_schedule_team_count": len({
                row["team"] for row in snapshot.team_schedule
                if row["season"] == snapshot.query.forecast_season
            }),
            "source_review_rows": len(snapshot.source_review),
            "roster_season_counts": dict(sorted(Counter(str(row["season"]) for row in snapshot.weekly_rosters).items())),
            "depth_season_counts": dict(sorted(Counter(str(row["season"]) for row in snapshot.opening_depth).items())),
        },
        "source_fields": {key: list(value) for key, value in snapshot.source_fields.items()},
        "artifacts": {
            "raw": raw_manifest,
            "normalized": {
                name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "fields": list({
                    "weekly_rosters.csv": WEEKLY_ROSTER_FIELDS,
                    "opening_depth.csv": OPENING_DEPTH_FIELDS,
                    "weekly_opportunities.csv": WEEKLY_OPPORTUNITY_FIELDS,
                    "team_schedule.csv": TEAM_SCHEDULE_FIELDS,
                    "source_review.csv": REVIEW_FIELDS,
                }[name])}
                for name, raw in artifacts.items()
            },
        },
    }
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent.parent))
    try:
        raw_directory = staging / "raw"
        raw_directory.mkdir()
        for asset in snapshot.assets:
            (raw_directory / asset.filename).write_bytes(asset.raw_bytes)
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
