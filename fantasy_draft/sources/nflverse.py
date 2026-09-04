"""nflverse play-by-play ingestion for observed team offensive styles.

This module intentionally measures what NFL offenses actually did.  It does not
turn historical rates into fantasy projections, and it keeps outcome metrics
(EPA and success rate) separate from play-style metrics.
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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SOURCE_ID = "nflverse"
SOURCE_NAME = "nflverse"
SOURCE_REPOSITORY = "https://github.com/nflverse/nflverse-data"
SOURCE_SCHEDULE = "https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html"
SOURCE_LICENSE = "CC-BY-4.0"
PBP_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/pbp/"
    "play_by_play_{season}.csv.gz"
)
ROSTER_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/rosters/"
    "roster_{season}.csv"
)
FTN_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/ftn_charting/"
    "ftn_charting_{season}.csv"
)
ADAPTER_VERSION = "1.1.0"
SNAPSHOT_SCHEMA_VERSION = "1.1.0"
MAX_PBP_BYTES = 60_000_000
MAX_ROSTER_BYTES = 8_000_000
MAX_FTN_BYTES = 15_000_000

PBP_REQUIRED_FIELDS = {
    "season",
    "season_type",
    "week",
    "game_id",
    "play_id",
    "posteam",
    "qtr",
    "down",
    "yardline_100",
    "play_type",
    "yards_gained",
    "shotgun",
    "no_huddle",
    "qb_kneel",
    "qb_spike",
    "qb_scramble",
    "air_yards",
    "epa",
    "wp",
    "receiver_player_id",
    "rusher_player_id",
    "success",
    "pass",
    "rush",
    "pass_oe",
}
ROSTER_REQUIRED_FIELDS = {"season", "team", "position", "gsis_id"}
FTN_REQUIRED_FIELDS = {
    "nflverse_game_id",
    "nflverse_play_id",
    "season",
    "qb_location",
    "n_offense_backfield",
    "is_motion",
    "is_play_action",
    "is_screen_pass",
    "is_rpo",
    "is_trick_play",
    "is_qb_out_of_pocket",
    "is_qb_sneak",
}

STYLE_FIELDS = (
    "team",
    "season",
    "games",
    "plays",
    "plays_per_game",
    "pass_rate",
    "neutral_early_down_pass_rate",
    "neutral_pass_oe",
    "shotgun_rate",
    "no_huddle_rate",
    "under_center_rate",
    "pistol_rate",
    "motion_rate",
    "play_action_rate",
    "screen_pass_rate",
    "rpo_rate",
    "multi_back_rate",
    "qb_out_of_pocket_rate",
    "qb_sneak_rate",
    "ftn_coverage_rate",
    "red_zone_pass_rate",
    "deep_attempt_rate",
    "mean_air_yards",
    "qb_scramble_rate",
    "designed_qb_run_share",
    "rb_target_share",
    "wr_target_share",
    "te_target_share",
    "other_target_share",
    "unknown_target_share",
    "explosive_play_rate",
    "success_rate",
    "epa_per_play",
)


class NflverseSourceError(RuntimeError):
    """Raised when an nflverse asset violates this adapter's contract."""


@dataclass(frozen=True)
class NflverseStyleQuery:
    """Seasons and game type used to build an observed-style snapshot."""

    seasons: tuple[int, ...]
    season_type: str = "REG"
    include_ftn_charting: bool = True

    def __post_init__(self) -> None:
        normalized: list[int] = []
        for season in self.seasons:
            if isinstance(season, bool) or not isinstance(season, int):
                raise ValueError("nflverse seasons must be integers")
            if not 1999 <= season <= 2100:
                raise ValueError("nflverse seasons must be between 1999 and 2100")
            normalized.append(season)
        if not normalized:
            raise ValueError("at least one nflverse season is required")
        if len(set(normalized)) != len(normalized):
            raise ValueError("nflverse seasons cannot contain duplicates")
        if self.season_type not in {"REG", "POST"}:
            raise ValueError("season_type must be REG or POST")
        object.__setattr__(self, "seasons", tuple(sorted(normalized)))

    @property
    def label(self) -> str:
        if len(self.seasons) == 1:
            return str(self.seasons[0])
        return f"{self.seasons[0]}-{self.seasons[-1]}"


@dataclass(frozen=True)
class NflverseAsset:
    kind: str
    season: int
    url: str
    raw_bytes: bytes
    response_last_modified: str | None = None
    response_etag: str | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw_bytes).hexdigest()

    @property
    def filename(self) -> str:
        prefixes = {
            "play_by_play": "play_by_play",
            "roster": "roster",
            "ftn_charting": "ftn_charting",
        }
        prefix = prefixes[self.kind]
        suffix = ".csv.gz" if self.url.endswith(".gz") else ".csv"
        return f"{prefix}_{self.season}{suffix}"


@dataclass(frozen=True)
class TeamSeasonStyle:
    team: str
    season: int
    games: int
    plays: int
    plays_per_game: float
    pass_rate: float
    neutral_early_down_pass_rate: float | None
    neutral_pass_oe: float | None
    shotgun_rate: float | None
    no_huddle_rate: float | None
    under_center_rate: float | None
    pistol_rate: float | None
    motion_rate: float | None
    play_action_rate: float | None
    screen_pass_rate: float | None
    rpo_rate: float | None
    multi_back_rate: float | None
    qb_out_of_pocket_rate: float | None
    qb_sneak_rate: float | None
    ftn_coverage_rate: float | None
    red_zone_pass_rate: float | None
    deep_attempt_rate: float | None
    mean_air_yards: float | None
    qb_scramble_rate: float | None
    designed_qb_run_share: float | None
    rb_target_share: float | None
    wr_target_share: float | None
    te_target_share: float | None
    other_target_share: float | None
    unknown_target_share: float | None
    explosive_play_rate: float | None
    success_rate: float | None
    epa_per_play: float | None

    def to_row(self) -> dict[str, str | int]:
        values: dict[str, str | int] = {}
        for field_name in STYLE_FIELDS:
            value = getattr(self, field_name)
            if isinstance(value, float):
                values[field_name] = f"{value:.6f}"
            elif value is None:
                values[field_name] = ""
            else:
                values[field_name] = value
        return values


@dataclass(frozen=True)
class NflverseStyleSnapshot:
    query: NflverseStyleQuery
    retrieved_at: datetime
    assets: tuple[NflverseAsset, ...]
    records: tuple[TeamSeasonStyle, ...]
    source_fields: Mapping[str, tuple[str, ...]]
    roster_position_conflicts: int = 0


@dataclass
class _Accumulator:
    games: set[str] = field(default_factory=set)
    plays: int = 0
    passes: int = 0
    neutral_plays: int = 0
    neutral_passes: int = 0
    neutral_pass_oe_sum: float = 0.0
    neutral_pass_oe_count: int = 0
    shotgun_sum: int = 0
    shotgun_count: int = 0
    no_huddle_sum: int = 0
    no_huddle_count: int = 0
    ftn_plays: int = 0
    qb_location_count: int = 0
    under_center_count: int = 0
    pistol_count: int = 0
    motion_sum: int = 0
    motion_count: int = 0
    play_action_sum: int = 0
    play_action_count: int = 0
    screen_pass_sum: int = 0
    screen_pass_count: int = 0
    rpo_sum: int = 0
    rpo_count: int = 0
    backfield_count: int = 0
    multi_back_count: int = 0
    qb_out_of_pocket_sum: int = 0
    qb_out_of_pocket_count: int = 0
    qb_sneak_sum: int = 0
    qb_sneak_count: int = 0
    red_zone_plays: int = 0
    red_zone_passes: int = 0
    pass_plays: int = 0
    deep_attempts: int = 0
    air_yards_sum: float = 0.0
    air_yards_count: int = 0
    scrambles: int = 0
    rush_plays: int = 0
    designed_qb_runs: int = 0
    target_positions: Counter[str] = field(default_factory=Counter)
    targets: int = 0
    explosive_plays: int = 0
    success_sum: int = 0
    success_count: int = 0
    epa_sum: float = 0.0
    epa_count: int = 0


def _utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    return value.astimezone(timezone.utc)


def _csv_reader(raw_bytes: bytes, *, context: str) -> csv.DictReader:
    if raw_bytes.startswith(b"\x1f\x8b"):
        try:
            decompressed = gzip.decompress(raw_bytes)
        except (OSError, EOFError) as error:
            raise NflverseSourceError(f"{context} is not a valid gzip asset") from error
    else:
        decompressed = raw_bytes
    try:
        text = decompressed.decode("utf-8")
    except UnicodeDecodeError as error:
        raise NflverseSourceError(f"{context} is not UTF-8 CSV") from error
    return csv.DictReader(io.StringIO(text, newline=""))


def _finite_float(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _integer(value: str | None) -> int | None:
    number = _finite_float(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _binary(value: str | None) -> int | None:
    number = _integer(value)
    return number if number in {0, 1} else None


def _word_binary(value: str | None) -> int | None:
    normalized = (value or "").strip().upper()
    if normalized in {"TRUE", "1"}:
        return 1
    if normalized in {"FALSE", "0"}:
        return 0
    return None


def _ratio(numerator: float, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _skill_position(position: str) -> str:
    normalized = position.strip().upper()
    if normalized in {"RB", "FB", "HB"}:
        return "RB"
    if normalized in {"WR", "TE", "QB"}:
        return normalized
    return "OTHER"


def _roster_positions(
    raw_bytes: bytes,
    *,
    season: int,
) -> tuple[dict[str, str], tuple[str, ...], int]:
    reader = _csv_reader(raw_bytes, context=f"roster {season}")
    fields = set(reader.fieldnames or ())
    missing = ROSTER_REQUIRED_FIELDS - fields
    if missing:
        raise NflverseSourceError(
            f"roster {season} is missing fields: {', '.join(sorted(missing))}"
        )

    positions: dict[str, Counter[str]] = defaultdict(Counter)
    observed_rows = 0
    for row_number, row in enumerate(reader, start=2):
        row_season = _integer(row.get("season"))
        if row_season != season:
            if row_season is not None:
                raise NflverseSourceError(
                    f"roster {season} row {row_number} contains season {row_season}"
                )
            continue
        player_id = (row.get("gsis_id") or "").strip()
        position = (row.get("position") or "").strip()
        if player_id and position:
            positions[player_id][_skill_position(position)] += 1
            observed_rows += 1
    if not observed_rows:
        raise NflverseSourceError(f"roster {season} contains no mapped player IDs")

    resolved: dict[str, str] = {}
    conflicts = 0
    for player_id, counts in positions.items():
        if len(counts) > 1:
            conflicts += 1
        resolved[player_id] = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    return resolved, tuple(sorted(fields)), conflicts


def _apply_ftn_charting(
    raw_bytes: bytes,
    *,
    season: int,
    play_index: Mapping[tuple[str, str], tuple[str, int]],
    accumulators: Mapping[str, _Accumulator],
) -> tuple[str, ...]:
    reader = _csv_reader(raw_bytes, context=f"FTN charting {season}")
    fields = set(reader.fieldnames or ())
    missing = FTN_REQUIRED_FIELDS - fields
    if missing:
        raise NflverseSourceError(
            f"FTN charting {season} is missing fields: {', '.join(sorted(missing))}"
        )
    seen_matches: set[tuple[str, str]] = set()
    for row_number, row in enumerate(reader, start=2):
        row_season = _integer(row.get("season"))
        if row_season != season:
            if row_season is not None:
                raise NflverseSourceError(
                    f"FTN charting {season} row {row_number} contains season {row_season}"
                )
            continue
        key = (
            (row.get("nflverse_game_id") or "").strip(),
            (row.get("nflverse_play_id") or "").strip(),
        )
        play = play_index.get(key)
        if play is None:
            continue
        if key in seen_matches:
            raise NflverseSourceError(
                f"FTN charting {season} contains duplicate play {key[0]}:{key[1]}"
            )
        seen_matches.add(key)
        team, pass_play = play
        acc = accumulators[team]
        acc.ftn_plays += 1

        location = (row.get("qb_location") or "").strip().upper()
        if location in {"S", "U", "P"}:
            acc.qb_location_count += 1
            acc.under_center_count += location == "U"
            acc.pistol_count += location == "P"
        motion = _word_binary(row.get("is_motion"))
        if motion is not None:
            acc.motion_sum += motion
            acc.motion_count += 1
        rpo = _word_binary(row.get("is_rpo"))
        if rpo is not None:
            acc.rpo_sum += rpo
            acc.rpo_count += 1
        sneak = _word_binary(row.get("is_qb_sneak"))
        if sneak is not None:
            acc.qb_sneak_sum += sneak
            acc.qb_sneak_count += 1

        backs = _integer(row.get("n_offense_backfield"))
        if backs is not None and backs >= 0:
            acc.backfield_count += 1
            acc.multi_back_count += backs >= 2

        if pass_play:
            play_action = _word_binary(row.get("is_play_action"))
            if play_action is not None:
                acc.play_action_sum += play_action
                acc.play_action_count += 1
            screen = _word_binary(row.get("is_screen_pass"))
            if screen is not None:
                acc.screen_pass_sum += screen
                acc.screen_pass_count += 1
            out_of_pocket = _word_binary(row.get("is_qb_out_of_pocket"))
            if out_of_pocket is not None:
                acc.qb_out_of_pocket_sum += out_of_pocket
                acc.qb_out_of_pocket_count += 1
    if not seen_matches:
        raise NflverseSourceError(
            f"FTN charting {season} did not match any eligible play-by-play rows"
        )
    return tuple(sorted(fields))


def _aggregate_pbp(
    raw_bytes: bytes,
    *,
    season: int,
    season_type: str,
    positions: Mapping[str, str],
    ftn_charting: bytes | None = None,
    week_start: int | None = None,
    week_end: int | None = None,
) -> tuple[list[TeamSeasonStyle], tuple[str, ...], tuple[str, ...] | None]:
    if (week_start is None) != (week_end is None):
        raise ValueError("week_start and week_end must be supplied together")
    if week_start is not None:
        if (
            isinstance(week_start, bool)
            or isinstance(week_end, bool)
            or not isinstance(week_start, int)
            or not isinstance(week_end, int)
            or not 1 <= week_start <= week_end <= 22
        ):
            raise ValueError("week window must satisfy 1 <= week_start <= week_end <= 22")
    reader = _csv_reader(raw_bytes, context=f"play-by-play {season}")
    fields = set(reader.fieldnames or ())
    missing = PBP_REQUIRED_FIELDS - fields
    if missing:
        raise NflverseSourceError(
            f"play-by-play {season} is missing fields: {', '.join(sorted(missing))}"
        )

    accumulators: dict[str, _Accumulator] = defaultdict(_Accumulator)
    play_index: dict[tuple[str, str], tuple[str, int]] = {}
    matching_rows = 0
    for row_number, row in enumerate(reader, start=2):
        row_season = _integer(row.get("season"))
        if row_season != season:
            if row_season is not None:
                raise NflverseSourceError(
                    f"play-by-play {season} row {row_number} contains season {row_season}"
                )
            continue
        if (row.get("season_type") or "").strip() != season_type:
            continue
        if week_start is not None:
            row_week = _integer(row.get("week"))
            if row_week is None:
                raise NflverseSourceError(
                    f"play-by-play {season} row {row_number} has no valid week"
                )
            if row_week < week_start or row_week > week_end:
                continue
        team = (row.get("posteam") or "").strip().upper()
        down = _integer(row.get("down"))
        pass_play = _binary(row.get("pass"))
        rush_play = _binary(row.get("rush"))
        if not team or down not in {1, 2, 3, 4}:
            continue
        if pass_play not in {0, 1} or rush_play not in {0, 1} or pass_play + rush_play != 1:
            continue
        if _binary(row.get("qb_kneel")) == 1 or _binary(row.get("qb_spike")) == 1:
            continue

        acc = accumulators[team]
        matching_rows += 1
        acc.plays += 1
        acc.passes += pass_play
        acc.pass_plays += pass_play
        acc.rush_plays += rush_play
        game_id = (row.get("game_id") or "").strip()
        if game_id:
            acc.games.add(game_id)
            play_id = (row.get("play_id") or "").strip()
            if play_id:
                key = (game_id, play_id)
                existing = play_index.get(key)
                current = (team, pass_play)
                if existing is not None and existing != current:
                    raise NflverseSourceError(
                        f"play-by-play {season} has conflicting duplicate play {game_id}:{play_id}"
                    )
                play_index[key] = current

        shotgun = _binary(row.get("shotgun"))
        if shotgun is not None:
            acc.shotgun_sum += shotgun
            acc.shotgun_count += 1
        no_huddle = _binary(row.get("no_huddle"))
        if no_huddle is not None:
            acc.no_huddle_sum += no_huddle
            acc.no_huddle_count += 1

        qtr = _integer(row.get("qtr"))
        wp = _finite_float(row.get("wp"))
        if down in {1, 2} and qtr in {1, 2, 3} and wp is not None and 0.20 <= wp <= 0.80:
            acc.neutral_plays += 1
            acc.neutral_passes += pass_play
            pass_oe = _finite_float(row.get("pass_oe"))
            if pass_oe is not None:
                acc.neutral_pass_oe_sum += pass_oe
                acc.neutral_pass_oe_count += 1

        yardline = _finite_float(row.get("yardline_100"))
        if yardline is not None and yardline <= 20:
            acc.red_zone_plays += 1
            acc.red_zone_passes += pass_play

        air_yards = _finite_float(row.get("air_yards"))
        if pass_play and air_yards is not None:
            acc.air_yards_sum += air_yards
            acc.air_yards_count += 1
            if air_yards >= 15:
                acc.deep_attempts += 1

        if pass_play and _binary(row.get("qb_scramble")) == 1:
            acc.scrambles += 1
        if rush_play and _binary(row.get("qb_scramble")) != 1:
            rusher_id = (row.get("rusher_player_id") or "").strip()
            if rusher_id and positions.get(rusher_id) == "QB":
                acc.designed_qb_runs += 1

        receiver_id = (row.get("receiver_player_id") or "").strip()
        if pass_play and receiver_id:
            acc.targets += 1
            acc.target_positions[positions.get(receiver_id, "UNKNOWN")] += 1

        yards = _finite_float(row.get("yards_gained"))
        if yards is not None and ((pass_play and yards >= 20) or (rush_play and yards >= 10)):
            acc.explosive_plays += 1
        success = _binary(row.get("success"))
        if success is not None:
            acc.success_sum += success
            acc.success_count += 1
        epa = _finite_float(row.get("epa"))
        if epa is not None:
            acc.epa_sum += epa
            acc.epa_count += 1

    if not matching_rows:
        raise NflverseSourceError(
            f"play-by-play {season} contains no eligible {season_type} offensive plays"
        )

    ftn_fields = (
        _apply_ftn_charting(
            ftn_charting,
            season=season,
            play_index=play_index,
            accumulators=accumulators,
        )
        if ftn_charting is not None
        else None
    )

    records: list[TeamSeasonStyle] = []
    for team, acc in sorted(accumulators.items()):
        if not acc.games:
            raise NflverseSourceError(f"{season} {team} has plays but no game IDs")
        target_share = lambda key: _ratio(acc.target_positions[key], acc.targets)
        records.append(
            TeamSeasonStyle(
                team=team,
                season=season,
                games=len(acc.games),
                plays=acc.plays,
                plays_per_game=acc.plays / len(acc.games),
                pass_rate=acc.passes / acc.plays,
                neutral_early_down_pass_rate=_ratio(
                    acc.neutral_passes, acc.neutral_plays
                ),
                neutral_pass_oe=_ratio(
                    acc.neutral_pass_oe_sum, acc.neutral_pass_oe_count
                ),
                shotgun_rate=_ratio(acc.shotgun_sum, acc.shotgun_count),
                no_huddle_rate=_ratio(acc.no_huddle_sum, acc.no_huddle_count),
                under_center_rate=_ratio(acc.under_center_count, acc.qb_location_count),
                pistol_rate=_ratio(acc.pistol_count, acc.qb_location_count),
                motion_rate=_ratio(acc.motion_sum, acc.motion_count),
                play_action_rate=_ratio(acc.play_action_sum, acc.play_action_count),
                screen_pass_rate=_ratio(acc.screen_pass_sum, acc.screen_pass_count),
                rpo_rate=_ratio(acc.rpo_sum, acc.rpo_count),
                multi_back_rate=_ratio(acc.multi_back_count, acc.backfield_count),
                qb_out_of_pocket_rate=_ratio(
                    acc.qb_out_of_pocket_sum, acc.qb_out_of_pocket_count
                ),
                qb_sneak_rate=_ratio(acc.qb_sneak_sum, acc.qb_sneak_count),
                ftn_coverage_rate=(
                    _ratio(acc.ftn_plays, acc.plays)
                    if ftn_charting is not None
                    else None
                ),
                red_zone_pass_rate=_ratio(acc.red_zone_passes, acc.red_zone_plays),
                deep_attempt_rate=_ratio(acc.deep_attempts, acc.air_yards_count),
                mean_air_yards=_ratio(acc.air_yards_sum, acc.air_yards_count),
                qb_scramble_rate=_ratio(acc.scrambles, acc.pass_plays),
                designed_qb_run_share=_ratio(acc.designed_qb_runs, acc.rush_plays),
                rb_target_share=target_share("RB"),
                wr_target_share=target_share("WR"),
                te_target_share=target_share("TE"),
                other_target_share=target_share("OTHER"),
                unknown_target_share=target_share("UNKNOWN"),
                explosive_play_rate=_ratio(acc.explosive_plays, acc.plays),
                success_rate=_ratio(acc.success_sum, acc.success_count),
                epa_per_play=_ratio(acc.epa_sum, acc.epa_count),
            )
        )
    return records, tuple(sorted(fields)), ftn_fields


def derive_nflverse_style_window(
    *,
    season: int,
    week_start: int,
    week_end: int,
    play_by_play: bytes,
    roster: bytes,
    ftn_charting: bytes | None = None,
    season_type: str = "REG",
) -> tuple[TeamSeasonStyle, ...]:
    """Derive team styles for one auditable in-season week window.

    This is intentionally separate from :class:`NflverseStyleQuery`, whose
    snapshots represent complete seasons.  Backtests use this helper against
    already-preserved raw assets so a forecast target can be Weeks 1-6 or 1-8
    without downloading or mutating source data.
    """

    if isinstance(season, bool) or not isinstance(season, int):
        raise ValueError("season must be an integer")
    if season_type not in {"REG", "POST"}:
        raise ValueError("season_type must be REG or POST")
    positions, _, _ = _roster_positions(roster, season=season)
    records, _, _ = _aggregate_pbp(
        play_by_play,
        season=season,
        season_type=season_type,
        positions=positions,
        ftn_charting=ftn_charting,
        week_start=week_start,
        week_end=week_end,
    )
    return tuple(records)


def parse_nflverse_style(
    query: NflverseStyleQuery,
    *,
    play_by_play: Mapping[int, bytes],
    rosters: Mapping[int, bytes],
    ftn_charting: Mapping[int, bytes] | None = None,
    retrieved_at: datetime,
    assets: Iterable[NflverseAsset] = (),
) -> NflverseStyleSnapshot:
    """Validate source assets and derive one observed-style record per team-season."""

    retrieved_at = _utc_timestamp(retrieved_at)
    missing_pbp = set(query.seasons) - set(play_by_play)
    missing_rosters = set(query.seasons) - set(rosters)
    if missing_pbp:
        raise NflverseSourceError(
            f"missing play-by-play seasons: {', '.join(map(str, sorted(missing_pbp)))}"
        )
    if missing_rosters:
        raise NflverseSourceError(
            f"missing roster seasons: {', '.join(map(str, sorted(missing_rosters)))}"
        )
    ftn_charting = ftn_charting or {}
    expected_ftn = {season for season in query.seasons if season >= 2022}
    missing_ftn = expected_ftn - set(ftn_charting)
    if query.include_ftn_charting and missing_ftn:
        raise NflverseSourceError(
            f"missing FTN charting seasons: {', '.join(map(str, sorted(missing_ftn)))}"
        )

    records: list[TeamSeasonStyle] = []
    source_fields: dict[str, tuple[str, ...]] = {}
    position_conflicts = 0
    for season in query.seasons:
        positions, roster_fields, conflicts = _roster_positions(
            rosters[season], season=season
        )
        season_records, pbp_fields, ftn_fields = _aggregate_pbp(
            play_by_play[season],
            season=season,
            season_type=query.season_type,
            positions=positions,
            ftn_charting=ftn_charting.get(season) if query.include_ftn_charting else None,
        )
        records.extend(season_records)
        source_fields[f"roster_{season}"] = roster_fields
        source_fields[f"play_by_play_{season}"] = pbp_fields
        if ftn_fields is not None:
            source_fields[f"ftn_charting_{season}"] = ftn_fields
        position_conflicts += conflicts

    return NflverseStyleSnapshot(
        query=query,
        retrieved_at=retrieved_at,
        assets=tuple(sorted(assets, key=lambda asset: (asset.season, asset.kind))),
        records=tuple(sorted(records, key=lambda record: (record.season, record.team))),
        source_fields=source_fields,
        roster_position_conflicts=position_conflicts,
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
            "Accept": "application/octet-stream",
            "User-Agent": "fantasy-football-26/0.1 (+source-attributed research)",
        },
    )
    try:
        with urlopen_fn(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
            last_modified = response.headers.get("Last-Modified")
            etag = response.headers.get("ETag")
    except HTTPError as error:
        raise NflverseSourceError(f"nflverse returned HTTP {error.code} for {url}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise NflverseSourceError(f"could not fetch nflverse asset {url}: {error}") from error
    if len(body) > max_bytes:
        raise NflverseSourceError(f"nflverse asset exceeded {max_bytes:,} bytes: {url}")
    if not body:
        raise NflverseSourceError(f"nflverse returned an empty asset: {url}")
    return body, last_modified, etag


def fetch_nflverse_style(
    query: NflverseStyleQuery,
    *,
    timeout: float = 60.0,
    retrieved_at: datetime | None = None,
    urlopen_fn: Callable[..., Any] = urlopen,
) -> NflverseStyleSnapshot:
    """Fetch roster/PBP assets and return a validated observed-style snapshot."""

    if timeout <= 0:
        raise ValueError("nflverse timeout must be positive")
    retrieved_at = _utc_timestamp(retrieved_at or datetime.now(timezone.utc))
    pbp: dict[int, bytes] = {}
    rosters: dict[int, bytes] = {}
    ftn_charting: dict[int, bytes] = {}
    assets: list[NflverseAsset] = []
    for season in query.seasons:
        for kind, template, limit, destination in (
            ("play_by_play", PBP_URL, MAX_PBP_BYTES, pbp),
            ("roster", ROSTER_URL, MAX_ROSTER_BYTES, rosters),
        ):
            url = template.format(season=season)
            body, last_modified, etag = _download_asset(
                url,
                timeout=timeout,
                max_bytes=limit,
                urlopen_fn=urlopen_fn,
            )
            destination[season] = body
            assets.append(
                NflverseAsset(
                    kind=kind,
                    season=season,
                    url=url,
                    raw_bytes=body,
                    response_last_modified=last_modified,
                    response_etag=etag,
                )
            )
        if query.include_ftn_charting and season >= 2022:
            url = FTN_URL.format(season=season)
            body, last_modified, etag = _download_asset(
                url,
                timeout=timeout,
                max_bytes=MAX_FTN_BYTES,
                urlopen_fn=urlopen_fn,
            )
            ftn_charting[season] = body
            assets.append(
                NflverseAsset(
                    kind="ftn_charting",
                    season=season,
                    url=url,
                    raw_bytes=body,
                    response_last_modified=last_modified,
                    response_etag=etag,
                )
            )
    return parse_nflverse_style(
        query,
        play_by_play=pbp,
        rosters=rosters,
        ftn_charting=ftn_charting,
        retrieved_at=retrieved_at,
        assets=assets,
    )


def _normalized_csv(snapshot: NflverseStyleSnapshot) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=STYLE_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(record.to_row() for record in snapshot.records)
    return stream.getvalue().encode("utf-8")


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def write_nflverse_style_snapshot(
    snapshot: NflverseStyleSnapshot,
    root: str | Path,
) -> Path:
    """Atomically publish raw assets, normalized team styles, and provenance."""

    root = Path(root)
    timestamp = snapshot.retrieved_at.strftime("%Y%m%dT%H%M%S.%fZ")
    parent = root / SOURCE_ID / "team_style" / snapshot.query.label
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"nflverse snapshot already exists: {destination}")

    normalized = _normalized_csv(snapshot)
    raw_manifest: dict[str, dict[str, object]] = {}
    for asset in snapshot.assets:
        raw_manifest[asset.filename] = {
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
    teams_per_season = {
        str(season): len({r.team for r in snapshot.records if r.season == season})
        for season in snapshot.query.seasons
    }
    unknown_target_shares = [
        record.unknown_target_share
        for record in snapshot.records
        if record.unknown_target_share is not None
    ]
    manifest = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "source": {
            "id": SOURCE_ID,
            "name": SOURCE_NAME,
            "repository": SOURCE_REPOSITORY,
            "update_schedule": SOURCE_SCHEDULE,
            "license": SOURCE_LICENSE,
        },
        "query": {
            "seasons": list(snapshot.query.seasons),
            "season_type": snapshot.query.season_type,
            "include_ftn_charting": snapshot.query.include_ftn_charting,
        },
        "retrieved_at": _iso_z(snapshot.retrieved_at),
        "methodology": {
            "eligible_plays": (
                "downs 1-4 with exactly one nflverse pass/rush flag; kneels and spikes excluded"
            ),
            "neutral_early_down": "downs 1-2, quarters 1-3, win probability 0.20-0.80",
            "deep_attempt": "air_yards >= 15",
            "explosive_play": "pass yards >= 20 or rush yards >= 10",
            "neutral_pass_oe_unit": "percentage points as published by nflverse",
            "targets": "receiver GSIS IDs joined to same-season nflverse rosters",
            "charting": (
                "FTN charting joined on nflverse game/play IDs for 2022 onward; "
                "play-action, screen, and out-of-pocket rates use charted dropbacks"
            ),
        },
        "quality": {
            "record_count": len(snapshot.records),
            "teams_per_season": teams_per_season,
            "roster_position_conflicts": snapshot.roster_position_conflicts,
            "unique_team_seasons": len({(record.season, record.team) for record in snapshot.records}),
            "target_position_coverage": {
                "mean_unknown_share": (
                    sum(unknown_target_shares) / len(unknown_target_shares)
                    if unknown_target_shares
                    else None
                ),
                "max_unknown_share": max(unknown_target_shares, default=None),
                "team_seasons_over_5pct_unknown": sum(
                    share > 0.05 for share in unknown_target_shares
                ),
            },
        },
        "source_fields": {key: list(value) for key, value in snapshot.source_fields.items()},
        "artifacts": {
            "raw": raw_manifest,
            "normalized": {
                "path": "team_style.csv",
                "bytes": len(normalized),
                "sha256": hashlib.sha256(normalized).hexdigest(),
                "fields": list(STYLE_FIELDS),
            },
        },
    }

    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
    try:
        raw_directory = staging / "raw"
        raw_directory.mkdir()
        for asset in snapshot.assets:
            (raw_directory / asset.filename).write_bytes(asset.raw_bytes)
        (staging / "team_style.csv").write_bytes(normalized)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
