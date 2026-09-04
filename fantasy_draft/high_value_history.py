"""Derive audited player high-value usage from preserved nflverse assets.

The transform is deliberately descriptive.  It counts targeted and rushing work
in situations that matter for role quality, but it does not estimate fantasy
points or pretend that the public participation feed contains every route.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import shutil
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "1.1.0"
MODEL_VERSION = "nflverse-high-value-history-v0.2.0"
READ_CODES = {"0", "1", "2", "CHK", "DES", "SD"}
PRIMARY_READ_RATE_REVIEW_THRESHOLD = 0.05
PBP_REQUIRED_FIELDS = {
    "season", "season_type", "week", "game_id", "play_id", "posteam",
    "qtr", "down", "yardline_100", "half_seconds_remaining", "ydstogo",
    "goal_to_go", "air_yards", "qb_kneel", "qb_spike", "qb_scramble",
    "pass", "rush", "receiver_player_id", "receiver_player_name",
    "rusher_player_id", "rusher_player_name",
}
ROSTER_REQUIRED_FIELDS = {"season", "position", "gsis_id", "full_name"}
FTN_REQUIRED_FIELDS = {
    "season", "nflverse_game_id", "nflverse_play_id", "read_thrown",
}

COUNT_FIELDS = (
    "targets", "targets_with_air_yards", "deep_targets", "red_zone_targets",
    "inside_10_targets", "end_zone_targets", "two_minute_targets",
    "third_fourth_down_targets", "ftn_matched_targets",
    "read_labeled_targets", "first_read_targets", "second_read_targets",
    "third_later_read_targets", "designed_targets", "checkdown_targets",
    "scramble_drill_targets",
    "carries", "red_zone_carries", "inside_10_carries", "inside_5_carries",
    "goal_to_go_carries", "short_yardage_carries",
    "third_fourth_short_carries", "two_minute_carries",
    "designed_qb_carries", "designed_qb_red_zone_carries",
    "designed_qb_inside_10_carries", "designed_qb_inside_5_carries",
    "qb_scramble_carries",
)
READ_COUNT_FIELDS = (
    "ftn_matched_targets", "read_labeled_targets", "first_read_targets",
    "second_read_targets", "third_later_read_targets", "designed_targets",
    "checkdown_targets", "scramble_drill_targets",
)
WEEKLY_FIELDS = (
    "season", "week", "team", "position", "gsis_id", "player_name",
    "read_source_available", "primary_read_source_available",
    *COUNT_FIELDS, "target_air_yards",
)
TEAM_WEEK_FIELDS = (
    "season", "week", "team", "position", "player_count",
    "read_source_available", "primary_read_source_available",
    *COUNT_FIELDS, "target_air_yards",
)
COVERAGE_FIELDS = (
    "season", "team_count", "week_count", "target_count", "carry_count",
    "mapped_target_count", "mapped_target_rate", "mapped_carry_count",
    "mapped_carry_rate", "ftn_available", "ftn_matched_target_count",
    "ftn_match_rate", "read_labeled_target_count", "read_labeled_rate",
    "primary_read_available", "first_read_target_count", "primary_read_rate",
    "second_read_target_count", "third_later_read_target_count",
    "designed_target_count", "checkdown_target_count",
    "scramble_drill_target_count", "unknown_read_code_count",
)
REVIEW_FIELDS = (
    "season", "week", "team", "gsis_id", "player_name", "issue",
    "count", "details",
)


class HighValueHistoryDataError(ValueError):
    """Raised when source assets cannot support an audited transformation."""


@dataclass(frozen=True)
class HighValueHistoryResult:
    source_path: Path
    source_manifest_hash: str
    seasons: tuple[int, ...]
    read_available_seasons: tuple[int, ...]
    primary_read_available_seasons: tuple[int, ...]
    input_hashes: Mapping[str, str]
    input_urls: Mapping[str, str]
    weekly_rows: tuple[Mapping[str, Any], ...]
    team_week_rows: tuple[Mapping[str, Any], ...]
    coverage_rows: tuple[Mapping[str, Any], ...]
    source_review: tuple[Mapping[str, Any], ...]
    roster_position_conflicts: int


def _read_csv(raw: bytes, *, context: str) -> csv.DictReader:
    if raw.startswith(b"\x1f\x8b"):
        try:
            raw = gzip.decompress(raw)
        except (OSError, EOFError) as error:
            raise HighValueHistoryDataError(f"{context} is not valid gzip") from error
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise HighValueHistoryDataError(f"{context} is not UTF-8 CSV") from error
    return csv.DictReader(io.StringIO(text, newline=""))


def _finite_float(value: Any) -> float | None:
    if value is None or not str(value).strip():
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any) -> int | None:
    number = _finite_float(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _binary(value: Any) -> int | None:
    number = _integer(value)
    return number if number in {0, 1} else None


def _skill_position(value: str) -> str:
    position = value.strip().upper()
    if position in {"RB", "FB", "HB"}:
        return "RB"
    if position in {"QB", "WR", "TE"}:
        return position
    return "OTHER"


def _verify_asset(path: Path, expected_hash: str) -> bytes:
    if not path.is_file():
        raise HighValueHistoryDataError(f"source asset does not exist: {path}")
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_hash:
        raise HighValueHistoryDataError(
            f"source hash mismatch for {path.name}: expected {expected_hash}, got {actual}"
        )
    return raw


def _roster_identity(
    raw: bytes, *, season: int
) -> tuple[dict[str, str], dict[str, str], int]:
    reader = _read_csv(raw, context=f"roster {season}")
    fields = set(reader.fieldnames or ())
    missing = ROSTER_REQUIRED_FIELDS - fields
    if missing:
        raise HighValueHistoryDataError(
            f"roster {season} is missing fields {sorted(missing)}"
        )
    positions: dict[str, Counter[str]] = defaultdict(Counter)
    names: dict[str, Counter[str]] = defaultdict(Counter)
    for row_number, row in enumerate(reader, start=2):
        row_season = _integer(row.get("season"))
        if row_season != season:
            if row_season is not None:
                raise HighValueHistoryDataError(
                    f"roster {season} row {row_number} contains season {row_season}"
                )
            continue
        player_id = (row.get("gsis_id") or "").strip()
        if not player_id:
            continue
        positions[player_id][_skill_position(row.get("position") or "")] += 1
        name = (row.get("full_name") or "").strip()
        if name:
            names[player_id][name] += 1
    if not positions:
        raise HighValueHistoryDataError(f"roster {season} has no GSIS identities")
    resolved_positions: dict[str, str] = {}
    resolved_names: dict[str, str] = {}
    conflicts = 0
    for player_id, counts in positions.items():
        if len(counts) > 1:
            conflicts += 1
        resolved_positions[player_id] = min(
            counts, key=lambda item: (-counts[item], item)
        )
        if names[player_id]:
            resolved_names[player_id] = min(
                names[player_id], key=lambda item: (-names[player_id][item], item)
            )
    return resolved_positions, resolved_names, conflicts


def _ftn_reads(raw: bytes, *, season: int) -> tuple[dict[tuple[str, str], str], int]:
    reader = _read_csv(raw, context=f"FTN charting {season}")
    fields = set(reader.fieldnames or ())
    missing = FTN_REQUIRED_FIELDS - fields
    if missing:
        raise HighValueHistoryDataError(
            f"FTN charting {season} is missing fields {sorted(missing)}"
        )
    reads: dict[tuple[str, str], str] = {}
    unknown = 0
    for row_number, row in enumerate(reader, start=2):
        row_season = _integer(row.get("season"))
        if row_season != season:
            if row_season is not None:
                raise HighValueHistoryDataError(
                    f"FTN charting {season} row {row_number} contains season {row_season}"
                )
            continue
        key = (
            (row.get("nflverse_game_id") or "").strip(),
            (row.get("nflverse_play_id") or "").strip(),
        )
        if not all(key):
            continue
        if key in reads:
            raise HighValueHistoryDataError(
                f"FTN charting {season} duplicates play {key[0]}:{key[1]}"
            )
        code = (row.get("read_thrown") or "").strip().upper()
        reads[key] = code
        if code and code not in READ_CODES:
            unknown += 1
    if not reads:
        raise HighValueHistoryDataError(f"FTN charting {season} has no play IDs")
    return reads, unknown


def _new_counts() -> dict[str, float]:
    return {field: 0.0 for field in (*COUNT_FIELDS, "target_air_yards")}


def _add_target(
    counts: dict[str, float], *, row: Mapping[str, str], read_present: bool,
    read_code: str,
) -> None:
    counts["targets"] += 1
    yardline = _finite_float(row.get("yardline_100"))
    air_yards = _finite_float(row.get("air_yards"))
    half_seconds = _finite_float(row.get("half_seconds_remaining"))
    quarter = _integer(row.get("qtr"))
    down = _integer(row.get("down"))
    if air_yards is not None:
        counts["targets_with_air_yards"] += 1
        counts["target_air_yards"] += air_yards
        counts["deep_targets"] += air_yards >= 15
        if yardline is not None:
            counts["end_zone_targets"] += air_yards >= yardline
    if yardline is not None:
        counts["red_zone_targets"] += yardline <= 20
        counts["inside_10_targets"] += yardline <= 10
    if quarter in {2, 4} and half_seconds is not None and 0 <= half_seconds <= 120:
        counts["two_minute_targets"] += 1
    if down in {3, 4}:
        counts["third_fourth_down_targets"] += 1
    if read_present:
        counts["ftn_matched_targets"] += 1
    if read_code:
        counts["read_labeled_targets"] += 1
        key = {
            "0": "first_read_targets",
            "1": "second_read_targets",
            "2": "third_later_read_targets",
            "DES": "designed_targets",
            "CHK": "checkdown_targets",
            "SD": "scramble_drill_targets",
        }.get(read_code)
        if key:
            counts[key] += 1


def _add_carry(counts: dict[str, float], *, row: Mapping[str, str], position: str) -> None:
    counts["carries"] += 1
    yardline = _finite_float(row.get("yardline_100"))
    half_seconds = _finite_float(row.get("half_seconds_remaining"))
    yards_to_go = _finite_float(row.get("ydstogo"))
    quarter = _integer(row.get("qtr"))
    down = _integer(row.get("down"))
    if yardline is not None:
        counts["red_zone_carries"] += yardline <= 20
        counts["inside_10_carries"] += yardline <= 10
        counts["inside_5_carries"] += yardline <= 5
    counts["goal_to_go_carries"] += _binary(row.get("goal_to_go")) == 1
    short = yards_to_go is not None and 0 < yards_to_go <= 2
    counts["short_yardage_carries"] += short
    counts["third_fourth_short_carries"] += short and down in {3, 4}
    if quarter in {2, 4} and half_seconds is not None and 0 <= half_seconds <= 120:
        counts["two_minute_carries"] += 1
    if position == "QB":
        scramble = _binary(row.get("qb_scramble")) == 1
        counts["qb_scramble_carries"] += scramble
        counts["designed_qb_carries"] += not scramble
        if not scramble and yardline is not None:
            counts["designed_qb_red_zone_carries"] += yardline <= 20
            counts["designed_qb_inside_10_carries"] += yardline <= 10
            counts["designed_qb_inside_5_carries"] += yardline <= 5


def _format_counts(
    counts: Mapping[str, float], *, read_source_available: bool,
    primary_read_source_available: bool,
) -> dict[str, Any]:
    return {
        **{
            field: (
                int(counts[field])
                if (
                    (field == "first_read_targets" and primary_read_source_available)
                    or (
                        field != "first_read_targets"
                        and (read_source_available or field not in READ_COUNT_FIELDS)
                    )
                )
                else ""
            )
            for field in COUNT_FIELDS
        },
        "target_air_yards": f"{counts['target_air_yards']:.3f}",
    }


def build_high_value_history(nflverse_snapshot: str | Path) -> HighValueHistoryResult:
    """Build player-week high-value usage from one preserved team-style snapshot."""

    source_path = Path(nflverse_snapshot)
    manifest_path = source_path / "manifest.json"
    if not manifest_path.is_file():
        raise HighValueHistoryDataError(f"missing source manifest: {manifest_path}")
    manifest_raw = manifest_path.read_bytes()
    try:
        manifest = json.loads(manifest_raw)
    except json.JSONDecodeError as error:
        raise HighValueHistoryDataError("source manifest is not valid JSON") from error
    query = manifest.get("query") or {}
    if query.get("season_type") != "REG":
        raise HighValueHistoryDataError("high-value history requires REG play-by-play")
    raw_manifest = (manifest.get("artifacts") or {}).get("raw") or {}
    try:
        seasons = tuple(sorted({int(value) for value in query["seasons"]}))
    except (KeyError, TypeError, ValueError) as error:
        raise HighValueHistoryDataError("source manifest has invalid seasons") from error
    if not seasons:
        raise HighValueHistoryDataError("source manifest has no seasons")

    raw_assets: dict[str, bytes] = {}
    input_hashes = {"manifest.json": hashlib.sha256(manifest_raw).hexdigest()}
    input_urls: dict[str, str] = {}
    for season in seasons:
        for name in (f"play_by_play_{season}.csv.gz", f"roster_{season}.csv"):
            meta = raw_manifest.get(name)
            if not isinstance(meta, dict) or not meta.get("sha256"):
                raise HighValueHistoryDataError(f"source manifest lacks {name}")
            raw_assets[name] = _verify_asset(source_path / "raw" / name, meta["sha256"])
            input_hashes[name] = meta["sha256"]
            input_urls[name] = str(meta.get("url") or "")
        ftn_name = f"ftn_charting_{season}.csv"
        if ftn_name in raw_manifest:
            meta = raw_manifest[ftn_name]
            raw_assets[ftn_name] = _verify_asset(
                source_path / "raw" / ftn_name, meta["sha256"]
            )
            input_hashes[ftn_name] = meta["sha256"]
            input_urls[ftn_name] = str(meta.get("url") or "")

    weekly: dict[tuple[int, int, str, str, str], dict[str, float]] = {}
    names_by_key: dict[tuple[int, int, str, str, str], Counter[str]] = defaultdict(Counter)
    coverage: dict[int, Counter[str]] = {season: Counter() for season in seasons}
    teams_by_season: dict[int, set[str]] = defaultdict(set)
    weeks_by_season: dict[int, set[int]] = defaultdict(set)
    review_counts: Counter[tuple[int, int, str, str, str, str, str]] = Counter()
    total_position_conflicts = 0
    read_available_seasons: set[int] = set()
    primary_read_available_seasons: set[int] = set()

    for season in seasons:
        positions, roster_names, conflicts = _roster_identity(
            raw_assets[f"roster_{season}.csv"], season=season
        )
        total_position_conflicts += conflicts
        ftn_name = f"ftn_charting_{season}.csv"
        reads: dict[tuple[str, str], str] = {}
        unknown_ftn_codes = 0
        if ftn_name in raw_assets:
            reads, unknown_ftn_codes = _ftn_reads(raw_assets[ftn_name], season=season)
            read_available_seasons.add(season)
            if season >= 2023:
                primary_read_available_seasons.add(season)
        coverage[season]["unknown_read_code_count"] += unknown_ftn_codes

        reader = _read_csv(
            raw_assets[f"play_by_play_{season}.csv.gz"],
            context=f"play-by-play {season}",
        )
        fields = set(reader.fieldnames or ())
        missing = PBP_REQUIRED_FIELDS - fields
        if missing:
            raise HighValueHistoryDataError(
                f"play-by-play {season} is missing fields {sorted(missing)}"
            )
        seen_event_plays: set[tuple[str, str]] = set()
        for row_number, row in enumerate(reader, start=2):
            row_season = _integer(row.get("season"))
            if row_season != season:
                if row_season is not None:
                    raise HighValueHistoryDataError(
                        f"play-by-play {season} row {row_number} contains season {row_season}"
                    )
                continue
            if (row.get("season_type") or "").strip() != "REG":
                continue
            week = _integer(row.get("week"))
            down = _integer(row.get("down"))
            team = (row.get("posteam") or "").strip().upper()
            if week is None or not 1 <= week <= 18 or down not in {1, 2, 3, 4} or not team:
                continue
            if _binary(row.get("qb_kneel")) == 1 or _binary(row.get("qb_spike")) == 1:
                continue
            receiver_id = (row.get("receiver_player_id") or "").strip()
            rusher_id = (row.get("rusher_player_id") or "").strip()
            target = _binary(row.get("pass")) == 1 and bool(receiver_id)
            carry = _binary(row.get("rush")) == 1 and bool(rusher_id)
            if not target and not carry:
                continue
            play_key = (
                (row.get("game_id") or "").strip(),
                (row.get("play_id") or "").strip(),
            )
            if not all(play_key):
                raise HighValueHistoryDataError(
                    f"play-by-play {season} row {row_number} lacks game/play ID"
                )
            if play_key in seen_event_plays:
                raise HighValueHistoryDataError(
                    f"play-by-play {season} duplicates event play {play_key[0]}:{play_key[1]}"
                )
            seen_event_plays.add(play_key)
            teams_by_season[season].add(team)
            weeks_by_season[season].add(week)

            if target:
                player_id = receiver_id
                position = positions.get(player_id, "UNKNOWN")
                key = season, week, team, position, player_id
                counts = weekly.setdefault(key, _new_counts())
                read_present = play_key in reads
                read_code = reads.get(play_key, "")
                _add_target(
                    counts, row=row, read_present=read_present, read_code=read_code
                )
                player_name = (
                    (row.get("receiver_player_name") or "").strip()
                    or roster_names.get(player_id, "")
                )
                if player_name:
                    names_by_key[key][player_name] += 1
                season_counts = coverage[season]
                season_counts["target_count"] += 1
                season_counts["mapped_target_count"] += position != "UNKNOWN"
                season_counts["ftn_matched_target_count"] += read_present
                season_counts["read_labeled_target_count"] += bool(read_code)
                category = {
                    "0": "first_read_target_count",
                    "1": "second_read_target_count",
                    "2": "third_later_read_target_count",
                    "DES": "designed_target_count",
                    "CHK": "checkdown_target_count",
                    "SD": "scramble_drill_target_count",
                }.get(read_code)
                if category:
                    season_counts[category] += 1
                if read_code and read_code not in READ_CODES:
                    review_counts[(
                        season, week, team, player_id, player_name,
                        "unknown_read_thrown_code", read_code,
                    )] += 1
                if position == "UNKNOWN":
                    review_counts[(
                        season, week, team, player_id, player_name,
                        "target_player_missing_roster_position",
                        "retained as UNKNOWN; no name-based join attempted",
                    )] += 1

            if carry:
                player_id = rusher_id
                position = positions.get(player_id, "UNKNOWN")
                key = season, week, team, position, player_id
                counts = weekly.setdefault(key, _new_counts())
                _add_carry(counts, row=row, position=position)
                player_name = (
                    (row.get("rusher_player_name") or "").strip()
                    or roster_names.get(player_id, "")
                )
                if player_name:
                    names_by_key[key][player_name] += 1
                coverage[season]["carry_count"] += 1
                coverage[season]["mapped_carry_count"] += position != "UNKNOWN"
                if position == "UNKNOWN":
                    review_counts[(
                        season, week, team, player_id, player_name,
                        "rusher_missing_roster_position",
                        "retained as UNKNOWN; no name-based join attempted",
                    )] += 1

        if not coverage[season]["target_count"] or not coverage[season]["carry_count"]:
            raise HighValueHistoryDataError(
                f"play-by-play {season} produced no target or carry events"
            )

    weekly_rows: list[dict[str, Any]] = []
    for key, counts in weekly.items():
        season, week, team, position, player_id = key
        names = names_by_key[key]
        player_name = min(names, key=lambda name: (-names[name], name)) if names else ""
        weekly_rows.append({
            "season": season, "week": week, "team": team,
            "position": position, "gsis_id": player_id,
            "player_name": player_name,
            "read_source_available": str(season in read_available_seasons).lower(),
            "primary_read_source_available": str(
                season in primary_read_available_seasons
            ).lower(),
            **_format_counts(
                counts,
                read_source_available=season in read_available_seasons,
                primary_read_source_available=(
                    season in primary_read_available_seasons
                ),
            ),
        })

    team_groups: dict[tuple[int, int, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in weekly_rows:
        team_groups[(row["season"], row["week"], row["team"], row["position"])].append(row)
    team_week_rows: list[dict[str, Any]] = []
    for (season, week, team, position), rows in team_groups.items():
        totals = _new_counts()
        for row in rows:
            for field in COUNT_FIELDS:
                if row[field] != "":
                    totals[field] += int(row[field])
            totals["target_air_yards"] += float(row["target_air_yards"])
        read_available = season in read_available_seasons
        primary_read_available = season in primary_read_available_seasons
        team_week_rows.append({
            "season": season, "week": week, "team": team,
            "position": position, "player_count": len(rows),
            "read_source_available": str(read_available).lower(),
            "primary_read_source_available": str(primary_read_available).lower(),
            **_format_counts(
                totals,
                read_source_available=read_available,
                primary_read_source_available=primary_read_available,
            ),
        })

    coverage_rows: list[dict[str, Any]] = []
    for season in seasons:
        counts = coverage[season]
        targets = counts["target_count"]
        carries = counts["carry_count"]
        ftn_available = f"ftn_charting_{season}.csv" in raw_assets
        coverage_rows.append({
            "season": season,
            "team_count": len(teams_by_season[season]),
            "week_count": len(weeks_by_season[season]),
            "target_count": targets,
            "carry_count": carries,
            "mapped_target_count": counts["mapped_target_count"],
            "mapped_target_rate": f"{counts['mapped_target_count'] / targets:.6f}",
            "mapped_carry_count": counts["mapped_carry_count"],
            "mapped_carry_rate": f"{counts['mapped_carry_count'] / carries:.6f}",
            "ftn_available": str(ftn_available).lower(),
            "ftn_matched_target_count": counts["ftn_matched_target_count"],
            "ftn_match_rate": f"{counts['ftn_matched_target_count'] / targets:.6f}",
            "read_labeled_target_count": counts["read_labeled_target_count"],
            "read_labeled_rate": f"{counts['read_labeled_target_count'] / targets:.6f}",
            "primary_read_available": str(
                season in primary_read_available_seasons
            ).lower(),
            "first_read_target_count": (
                counts["first_read_target_count"]
                if season in primary_read_available_seasons else ""
            ),
            "primary_read_rate": (
                f"{counts['first_read_target_count'] / targets:.6f}"
                if season in primary_read_available_seasons else ""
            ),
            "second_read_target_count": counts["second_read_target_count"],
            "third_later_read_target_count": counts["third_later_read_target_count"],
            "designed_target_count": counts["designed_target_count"],
            "checkdown_target_count": counts["checkdown_target_count"],
            "scramble_drill_target_count": counts["scramble_drill_target_count"],
            "unknown_read_code_count": counts["unknown_read_code_count"],
        })

    source_review = [
        {
            "season": season, "week": week, "team": team,
            "gsis_id": player_id, "player_name": player_name,
            "issue": issue, "count": count, "details": details,
        }
        for (season, week, team, player_id, player_name, issue, details), count
        in review_counts.items()
    ]
    for row in coverage_rows:
        if row["ftn_available"] == "false":
            source_review.append({
                "season": row["season"], "week": "", "team": "",
                "gsis_id": "", "player_name": "",
                "issue": "read_source_unavailable",
                "count": row["target_count"],
                "details": "read-derived fields are structurally unavailable, not observed zero",
            })
        else:
            if row["primary_read_available"] == "false":
                source_review.append({
                    "season": row["season"], "week": "", "team": "",
                    "gsis_id": "", "player_name": "",
                    "issue": "primary_read_source_unavailable",
                    "count": row["target_count"],
                    "details": "FTN documents that 2022 primary reads are uncoded; first-read fields are blank, not zero",
                })
            if float(row["read_labeled_rate"]) < 0.999:
                source_review.append({
                    "season": row["season"], "week": "", "team": "",
                    "gsis_id": "", "player_name": "",
                    "issue": "read_source_partial",
                    "count": int(row["target_count"]) - int(row["read_labeled_target_count"]),
                    "details": f"read label coverage={row['read_labeled_rate']}",
                })
            if (
                row["primary_read_available"] == "true"
                and float(row["primary_read_rate"])
                < PRIMARY_READ_RATE_REVIEW_THRESHOLD
            ):
                source_review.append({
                    "season": row["season"], "week": "", "team": "",
                    "gsis_id": "", "player_name": "",
                    "issue": "dictionary_defined_primary_read_rate_below_review_threshold",
                    "count": row["first_read_target_count"],
                    "details": (
                        f"code-0 target rate={row['primary_read_rate']}; current "
                        "nflreadr dictionary followed, but promote only if the "
                        "downstream sample and validation gates pass"
                    ),
                })

    return HighValueHistoryResult(
        source_path=source_path,
        source_manifest_hash=hashlib.sha256(manifest_raw).hexdigest(),
        seasons=seasons,
        read_available_seasons=tuple(sorted(read_available_seasons)),
        primary_read_available_seasons=tuple(
            sorted(primary_read_available_seasons)
        ),
        input_hashes=dict(sorted(input_hashes.items())),
        input_urls=dict(sorted(input_urls.items())),
        weekly_rows=tuple(sorted(weekly_rows, key=lambda row: (
            row["season"], row["week"], row["team"], row["position"],
            row["gsis_id"],
        ))),
        team_week_rows=tuple(sorted(team_week_rows, key=lambda row: (
            row["season"], row["week"], row["team"], row["position"],
        ))),
        coverage_rows=tuple(coverage_rows),
        source_review=tuple(sorted(source_review, key=lambda row: (
            row["season"], str(row["week"]), row["team"], row["issue"],
            row["gsis_id"],
        ))),
        roster_position_conflicts=total_position_conflicts,
    )


def _csv_bytes(fields: tuple[str, ...], rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def write_high_value_history_snapshot(
    result: HighValueHistoryResult, root: str | Path
) -> Path:
    """Atomically publish normalized usage, coverage, review, and provenance."""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    label = f"{result.seasons[0]}-{result.seasons[-1]}"
    parent = Path(root) / "high_value_history" / label
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"high-value snapshot exists: {destination}")
    artifacts = {
        "player_week_high_value.csv": _csv_bytes(WEEKLY_FIELDS, result.weekly_rows),
        "team_week_high_value.csv": _csv_bytes(TEAM_WEEK_FIELDS, result.team_week_rows),
        "coverage.csv": _csv_bytes(COVERAGE_FIELDS, result.coverage_rows),
        "source_review.csv": _csv_bytes(REVIEW_FIELDS, result.source_review),
    }
    fields = {
        "player_week_high_value.csv": WEEKLY_FIELDS,
        "team_week_high_value.csv": TEAM_WEEK_FIELDS,
        "coverage.csv": COVERAGE_FIELDS,
        "source_review.csv": REVIEW_FIELDS,
    }
    maximum_reconciliation_error = 0.0
    player_lookup = defaultdict(lambda: _new_counts())
    for row in result.weekly_rows:
        key = row["season"], row["week"], row["team"], row["position"]
        for field in COUNT_FIELDS:
            if row[field] != "":
                player_lookup[key][field] += int(row[field])
        player_lookup[key]["target_air_yards"] += float(row["target_air_yards"])
    for row in result.team_week_rows:
        key = row["season"], row["week"], row["team"], row["position"]
        for field in COUNT_FIELDS:
            if row[field] == "":
                continue
            maximum_reconciliation_error = max(
                maximum_reconciliation_error,
                abs(player_lookup[key][field] - int(row[field])),
            )
        maximum_reconciliation_error = max(
            maximum_reconciliation_error,
            abs(player_lookup[key]["target_air_yards"] - float(row["target_air_yards"])),
        )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "seasons": list(result.seasons),
        "read_available_seasons": list(result.read_available_seasons),
        "primary_read_available_seasons": list(
            result.primary_read_available_seasons
        ),
        "scope": "descriptive player-week high-value opportunity; not a production or fantasy projection",
        "definitions": {
            "first_read_targets": "FTN read_thrown exactly 0 after game/play-ID join; structurally unavailable for 2022 per the current nflreadr dictionary",
            "second_read_targets": "FTN read_thrown exactly 1 after game/play-ID join",
            "third_later_read_targets": "FTN read_thrown exactly 2 after game/play-ID join",
            "designed_targets": "FTN read_thrown exactly DES; kept separate from numeric first read",
            "deep_targets": "target with nflverse air_yards at least 15",
            "red_zone_targets_and_carries": "yardline_100 at most 20",
            "inside_10_targets_and_carries": "yardline_100 at most 10",
            "inside_5_carries": "yardline_100 at most 5",
            "designed_qb_goal_line_carries": "non-scramble QB carries split at the 20, 10, and 5 yard lines",
            "end_zone_targets": "target air_yards greater than or equal to yardline_100",
            "two_minute_work": "target/carry in Q2 or Q4 with half_seconds_remaining from 0 through 120",
            "short_yardage_carries": "carry with ydstogo greater than 0 and at most 2",
            "routes": "not emitted: public participation route identifies only the primary receiver route, not every route run",
        },
        "source_constraints": {
            "identity": "GSIS IDs only; unknown positions remain explicit and names are never join keys",
            "ftn_attribution": "FTN Data via nflverse; CC-BY-SA-4.0",
            "read_categories": ["0", "1", "2", "CHK", "DES", "SD"],
            "read_category_authority": "current nflreadr FTN dictionary updated 2026-08-31; 0=primary, 1=second, 2=third or later",
            "primary_read_rate_review_threshold": PRIMARY_READ_RATE_REVIEW_THRESHOLD,
            "read_missingness": "zero read counts are interpretable only with ftn/read-label coverage",
            "outcomes": "counts describe opportunity placement, not conversion skill or future efficiency",
        },
        "inputs": {
            "nflverse_snapshot": str(result.source_path),
            "source_manifest_sha256": result.source_manifest_hash,
            "sha256": dict(result.input_hashes),
            "urls": dict(result.input_urls),
        },
        "quality": {
            "player_week_rows": len(result.weekly_rows),
            "team_week_rows": len(result.team_week_rows),
            "coverage_rows": len(result.coverage_rows),
            "source_review_rows": len(result.source_review),
            "roster_position_conflicts": result.roster_position_conflicts,
            "maximum_player_to_team_reconciliation_error": maximum_reconciliation_error,
            "minimum_mapped_target_rate": min(
                float(row["mapped_target_rate"]) for row in result.coverage_rows
            ),
            "minimum_mapped_carry_rate": min(
                float(row["mapped_carry_rate"]) for row in result.coverage_rows
            ),
            "minimum_available_read_labeled_rate": min(
                (
                    float(row["read_labeled_rate"])
                    for row in result.coverage_rows
                    if row["ftn_available"] == "true"
                ),
                default=0.0,
            ),
            "minimum_available_primary_read_rate": min(
                (
                    float(row["primary_read_rate"])
                    for row in result.coverage_rows
                    if row["primary_read_available"] == "true"
                ),
                default=0.0,
            ),
        },
        "artifacts": {
            name: {
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "fields": list(fields[name]),
            }
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
