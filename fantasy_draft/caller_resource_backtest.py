"""Direct backtest of the caller-aware team-resource transform.

The production role layer turns forecast plays, pass rate, quarterback rushing
tendencies, and position target shares into six team opportunity pools.  This
module recreates that transform for historical target seasons, learns only the
three unit-conversion factors from strictly prior matched team/player data, and
scores the result against GSIS-keyed weekly opportunities.

The target-season outcomes are evaluation data only.  They never change a
forecast or a conversion factor for that target season.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import random
import shutil
import statistics
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .resource_transform import (
    RESOURCE_INPUTS,
    ConversionEstimate,
    ResourceTransformError,
    VerifiedTeamStyle,
    canonical_team,
    derive_conversion_factors,
    load_verified_team_style,
    resource_forecasts,
)

SCHEMA_VERSION = "1.1.0"
MODEL_VERSION = "caller-aware-team-resource-backtest-v0.2.0"
TRANSITION_MODEL_VERSION = "opening-caller-transition-backtest-v0.3.0"
SOURCE_MODELS = ("caller_aware_v0", "shrunken_persistence", "persistence")
CANDIDATE_MODEL = "caller_aware_v0"
BASELINE_MODEL = "shrunken_persistence"
RECENCY_FACTOR = 0.65
NOMINAL_COVERAGE = 0.90

RESOURCE_ACTUAL_FIELDS: Mapping[str, tuple[str, str]] = {
    "QB_DROPBACKS": ("QB", "dropbacks"),
    "QB_RUSH_OPPORTUNITIES": ("QB", "carries"),
    "RB_CARRIES": ("RB", "carries"),
    "RB_TARGETS": ("RB", "targets"),
    "WR_TARGETS": ("WR", "targets"),
    "TE_TARGETS": ("TE", "targets"),
}
ROLE_POSITIONS = ("QB", "RB", "WR", "TE")

PREDICTION_FIELDS = (
    "target_season",
    "week_start",
    "week_end",
    "team",
    "caller_cohort",
    "model",
    "resource",
    "forecast_per_game",
    "actual_games",
    "actual_opportunities",
    "actual_per_game",
    "signed_error_per_game",
    "absolute_error_per_game",
    "qb_dropbacks_per_pass_play_factor",
    "target_per_pass_play_factor",
    "rb_carries_per_non_qb_rush_play_factor",
)
SUMMARY_FIELDS = (
    "scope",
    "scope_seasons",
    "week_end",
    "resource",
    "model",
    "team_season_count",
    "team_cluster_count",
    "mean_forecast_per_game",
    "mean_actual_per_game",
    "mean_signed_error_per_game",
    "mean_absolute_error_per_game",
    "root_mean_squared_error_per_game",
    "median_absolute_error_per_game",
)
PAIRED_FIELDS = (
    "target_season",
    "week_end",
    "team",
    "caller_cohort",
    "resource",
    "candidate",
    "baseline",
    "candidate_absolute_error_per_game",
    "baseline_absolute_error_per_game",
    "paired_delta",
    "candidate_wins",
)
PAIRED_SUMMARY_FIELDS = (
    "scope",
    "scope_seasons",
    "week_end",
    "resource",
    "pair_count",
    "team_cluster_count",
    "candidate_win_count",
    "candidate_win_rate",
    "candidate_mean_absolute_error_per_game",
    "baseline_mean_absolute_error_per_game",
    "relative_improvement_pct",
    "mean_paired_delta",
    "team_cluster_bootstrap_95pct_lower",
    "team_cluster_bootstrap_95pct_upper",
)
CONVERSION_FIELDS = (
    "target_season",
    "week_end",
    "requested_training_seasons",
    "training_seasons",
    "training_team_season_count",
    "qb_dropbacks_per_pass_play_forecast",
    "qb_dropbacks_per_pass_play_actual",
    "target_per_pass_play_forecast",
    "target_per_pass_play_actual",
    "rb_carries_per_non_qb_rush_play_forecast",
    "rb_carries_per_non_qb_rush_play_actual",
    "eligible_team_count",
)
CALIBRATION_FIELDS = (
    "resource",
    "week_end",
    "development_seasons",
    "development_team_season_count",
    "nominal_coverage",
    "finite_sample_rank",
    "absolute_error_per_game_radius",
    "holdout_season",
    "holdout_team_count",
    "holdout_covered_count",
    "holdout_coverage",
    "wilson_95pct_lower",
    "wilson_95pct_upper",
    "holdout_mean_interval_width",
)
COVERAGE_FIELDS = (
    "target_season",
    "week_end",
    "team",
    "caller_cohort",
    "resource",
    "forecast_per_game",
    "actual_per_game",
    "absolute_error_per_game_radius",
    "interval_low",
    "interval_high",
    "covered",
)
JOINT_COVERAGE_FIELDS = (
    "target_season",
    "week_end",
    "team_count",
    "resource_count",
    "all_resources_covered_team_count",
    "all_resources_covered_rate",
    "interpretation",
)


class CallerResourceBacktestDataError(ValueError):
    """Raised when a source cannot satisfy the direct resource-test contract."""


@dataclass(frozen=True)
class TransitionInput:
    path: Path
    target_season: int
    windows: tuple[int, ...]
    predictions: tuple[Mapping[str, str], ...]
    team_windows: Mapping[tuple[int, str], Mapping[str, str]]
    raw_by_path: Mapping[str, bytes]


@dataclass(frozen=True)
class PlayerHistoryInput:
    path: Path
    opportunities: tuple[Mapping[str, str], ...]
    schedule: tuple[Mapping[str, str], ...]
    raw_by_path: Mapping[str, bytes]


@dataclass(frozen=True)
class CallerResourceBacktestResult:
    target_seasons: tuple[int, ...]
    development_seasons: tuple[int, ...]
    holdout_season: int
    windows: tuple[int, ...]
    history_lookback: int
    bootstrap_samples: int
    random_seed: int
    input_raw: Mapping[str, bytes]
    prediction_rows: tuple[Mapping[str, Any], ...]
    summary_rows: tuple[Mapping[str, Any], ...]
    paired_rows: tuple[Mapping[str, Any], ...]
    paired_summary_rows: tuple[Mapping[str, Any], ...]
    conversion_rows: tuple[Mapping[str, Any], ...]
    calibration_rows: tuple[Mapping[str, Any], ...]
    coverage_rows: tuple[Mapping[str, Any], ...]
    joint_coverage_rows: tuple[Mapping[str, Any], ...]
    evaluation: Mapping[str, Any]


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_json(path: Path, context: str) -> tuple[bytes, Mapping[str, Any]]:
    if not path.is_file():
        raise CallerResourceBacktestDataError(f"missing {context}: {path}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CallerResourceBacktestDataError(
            f"{context} is not valid JSON: {path}"
        ) from error
    if not isinstance(value, Mapping):
        raise CallerResourceBacktestDataError(
            f"{context} must contain a JSON object: {path}"
        )
    return raw, value


def _read_csv_bytes(
    raw: bytes, required: set[str], context: str
) -> list[dict[str, str]]:
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        fields = set(reader.fieldnames or ())
        rows = list(reader)
    except UnicodeDecodeError as error:
        raise CallerResourceBacktestDataError(
            f"{context} is not UTF-8 CSV"
        ) from error
    missing = required - fields
    if missing or not rows:
        raise CallerResourceBacktestDataError(
            f"{context} is empty or missing fields {sorted(missing)}"
        )
    return rows


def _integer(value: Any, context: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise CallerResourceBacktestDataError(f"{context} must be an integer") from error
    return result


def _finite(value: Any, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise CallerResourceBacktestDataError(f"{context} must be numeric") from error
    if not math.isfinite(result):
        raise CallerResourceBacktestDataError(f"{context} must be finite")
    return result


def _verified_path(path_text: str, expected: str, context: str) -> tuple[str, bytes]:
    path = Path(path_text)
    if not path.is_file():
        raise CallerResourceBacktestDataError(f"missing bound {context}: {path}")
    raw = path.read_bytes()
    actual = _sha256(raw)
    if actual != expected:
        raise CallerResourceBacktestDataError(
            f"hash mismatch for {context} {path}: expected {expected}, got {actual}"
        )
    return str(path), raw


def _verified_artifact(
    root: Path, manifest: Mapping[str, Any], filename: str
) -> tuple[Path, bytes]:
    metadata = (manifest.get("artifacts") or {}).get(filename)
    if not isinstance(metadata, Mapping) or not isinstance(metadata.get("sha256"), str):
        raise CallerResourceBacktestDataError(
            f"manifest does not bind {filename}: {root}"
        )
    path = root / filename
    if not path.is_file():
        raise CallerResourceBacktestDataError(f"missing artifact: {path}")
    raw = path.read_bytes()
    actual = _sha256(raw)
    if actual != metadata["sha256"]:
        raise CallerResourceBacktestDataError(
            f"artifact hash mismatch for {path}: expected {metadata['sha256']}, got {actual}"
        )
    return path, raw


def _merge_raw(destination: dict[str, bytes], source: Mapping[str, bytes]) -> None:
    for path, raw in source.items():
        existing = destination.get(path)
        if existing is not None and existing != raw:
            raise CallerResourceBacktestDataError(
                f"input path has conflicting contents: {path}"
            )
        destination[path] = raw


def _load_transition(path: str | Path) -> TransitionInput:
    root = Path(path)
    if not root.is_dir():
        raise CallerResourceBacktestDataError(
            f"transition backtest snapshot is not a directory: {root}"
        )
    manifest_path = root / "manifest.json"
    manifest_raw, manifest = _read_json(manifest_path, "transition manifest")
    if manifest.get("model_version") != TRANSITION_MODEL_VERSION:
        raise CallerResourceBacktestDataError(
            f"unsupported transition model at {root}: {manifest.get('model_version')!r}"
        )
    seasons = manifest.get("seasons")
    if not isinstance(seasons, Mapping):
        raise CallerResourceBacktestDataError(f"missing transition seasons: {root}")
    target = _integer(seasons.get("target"), f"{root} target season")
    raw_by_path: dict[str, bytes] = {str(manifest_path): manifest_raw}
    input_hashes = manifest.get("input_sha256")
    if not isinstance(input_hashes, Mapping) or not input_hashes:
        raise CallerResourceBacktestDataError(
            f"transition manifest has no bound source inputs: {root}"
        )
    for source_path, expected in input_hashes.items():
        if not isinstance(source_path, str) or not isinstance(expected, str):
            raise CallerResourceBacktestDataError(
                f"transition input hashes are malformed: {root}"
            )
        verified_path, raw = _verified_path(
            source_path, expected, "transition source"
        )
        raw_by_path[verified_path] = raw

    predictions_path, predictions_raw = _verified_artifact(
        root, manifest, "predictions.csv"
    )
    teams_path, teams_raw = _verified_artifact(root, manifest, "teams.csv")
    raw_by_path[str(predictions_path)] = predictions_raw
    raw_by_path[str(teams_path)] = teams_raw
    predictions = _read_csv_bytes(
        predictions_raw,
        {
            "target_season",
            "week_end",
            "team",
            "caller_cohort",
            "metric",
            "model",
            "forecast_value",
            "actual_value",
        },
        str(predictions_path),
    )
    team_rows = _read_csv_bytes(
        teams_raw,
        {
            "target_season",
            "week_end",
            "team",
            "caller_cohort",
            "actual_games",
            "excluded",
        },
        str(teams_path),
    )
    if any(_integer(row["target_season"], str(predictions_path)) != target for row in predictions):
        raise CallerResourceBacktestDataError(
            f"prediction seasons do not match manifest target {target}: {root}"
        )
    team_windows: dict[tuple[int, str], Mapping[str, str]] = {}
    for row in team_rows:
        if _integer(row["target_season"], str(teams_path)) != target:
            raise CallerResourceBacktestDataError(
                f"team seasons do not match manifest target {target}: {root}"
            )
        week = _integer(row["week_end"], f"{target} team week")
        team = row["team"].strip().upper()
        key = week, team
        if not team or key in team_windows:
            raise CallerResourceBacktestDataError(
                f"blank or duplicate transition team-window {key}: {root}"
            )
        excluded = row["excluded"].strip().lower()
        if excluded not in {"true", "false"}:
            raise CallerResourceBacktestDataError(
                f"invalid excluded flag for {target} {team} Weeks 1-{week}"
            )
        games = _integer(row["actual_games"], f"{target} {team} actual games")
        if games <= 0:
            raise CallerResourceBacktestDataError(
                f"{target} {team} Weeks 1-{week} has no games"
            )
        team_windows[key] = row
    windows = tuple(sorted({week for week, _ in team_windows}))
    if not windows:
        raise CallerResourceBacktestDataError(f"transition windows are empty: {root}")
    for row in predictions:
        week = _integer(row["week_end"], f"{target} prediction week")
        team = row["team"].strip().upper()
        team_row = team_windows.get((week, team))
        if team_row is None or team_row["excluded"].strip().lower() != "false":
            raise CallerResourceBacktestDataError(
                f"prediction exists for missing/excluded team-window {target} {team} {week}"
            )
    return TransitionInput(
        path=root,
        target_season=target,
        windows=windows,
        predictions=tuple(predictions),
        team_windows=team_windows,
        raw_by_path=raw_by_path,
    )


def _load_player_history(path: str | Path) -> PlayerHistoryInput:
    root = Path(path)
    if not root.is_dir():
        raise CallerResourceBacktestDataError(
            f"player-history snapshot is not a directory: {root}"
        )
    manifest_path = root / "manifest.json"
    manifest_raw, manifest = _read_json(manifest_path, "player-history manifest")
    normalized = ((manifest.get("artifacts") or {}).get("normalized") or {})
    if not isinstance(normalized, Mapping):
        raise CallerResourceBacktestDataError(
            f"player-history manifest lacks normalized artifacts: {root}"
        )
    raw_by_path: dict[str, bytes] = {str(manifest_path): manifest_raw}
    loaded: dict[str, bytes] = {}
    for filename in ("weekly_opportunities.csv", "team_schedule.csv"):
        metadata = normalized.get(filename)
        if not isinstance(metadata, Mapping) or not isinstance(metadata.get("sha256"), str):
            raise CallerResourceBacktestDataError(
                f"player-history manifest does not bind {filename}: {root}"
            )
        file_path = root / filename
        if not file_path.is_file():
            raise CallerResourceBacktestDataError(f"missing player-history input: {file_path}")
        raw = file_path.read_bytes()
        if _sha256(raw) != metadata["sha256"]:
            raise CallerResourceBacktestDataError(
                f"player-history artifact hash mismatch: {file_path}"
            )
        loaded[filename] = raw
        raw_by_path[str(file_path)] = raw
    opportunities = _read_csv_bytes(
        loaded["weekly_opportunities.csv"],
        {
            "season",
            "week",
            "team",
            "position",
            "gsis_id",
            "dropbacks",
            "carries",
            "targets",
        },
        str(root / "weekly_opportunities.csv"),
    )
    schedule = _read_csv_bytes(
        loaded["team_schedule.csv"],
        {"season", "week", "team", "game_id"},
        str(root / "team_schedule.csv"),
    )
    return PlayerHistoryInput(
        path=root,
        opportunities=tuple(opportunities),
        schedule=tuple(schedule),
        raw_by_path=raw_by_path,
    )


def _history_values(
    history: PlayerHistoryInput,
) -> tuple[
    set[tuple[int, int, str]],
    Mapping[tuple[int, int, str, str], float],
    Mapping[tuple[int, int, str, str], float],
]:
    scheduled: set[tuple[int, int, str]] = set()
    for row in history.schedule:
        season = _integer(row["season"], "schedule season")
        week = _integer(row["week"], "schedule week")
        team = row["team"].strip().upper()
        if not team or not 1 <= week <= 18:
            continue
        key = season, week, team
        if key in scheduled:
            raise CallerResourceBacktestDataError(f"duplicate schedule team-week {key}")
        scheduled.add(key)

    resources: dict[tuple[int, int, str, str], float] = defaultdict(float)
    position_values: dict[tuple[int, int, str, str], float] = defaultdict(float)
    seen: set[tuple[int, int, str, str]] = set()
    for row in history.opportunities:
        season = _integer(row["season"], "opportunity season")
        week = _integer(row["week"], "opportunity week")
        team = row["team"].strip().upper()
        position = row["position"].strip().upper()
        player = row["gsis_id"].strip()
        if not team or not player or position not in ROLE_POSITIONS or not 1 <= week <= 18:
            continue
        identity = season, week, team, player
        if identity in seen:
            raise CallerResourceBacktestDataError(
                f"duplicate weekly player opportunity row {identity}"
            )
        seen.add(identity)
        dropbacks = _finite(row["dropbacks"], f"{identity} dropbacks")
        carries = _finite(row["carries"], f"{identity} carries")
        targets = _finite(row["targets"], f"{identity} targets")
        if min(dropbacks, carries, targets) < 0:
            raise CallerResourceBacktestDataError(
                f"negative weekly opportunity at {identity}"
            )
        position_values[(season, week, team, f"{position}_DROPBACKS")] += dropbacks
        position_values[(season, week, team, f"{position}_CARRIES")] += carries
        position_values[(season, week, team, f"{position}_TARGETS")] += targets
        for resource, (wanted_position, field) in RESOURCE_ACTUAL_FIELDS.items():
            if position != wanted_position:
                continue
            value = {"dropbacks": dropbacks, "carries": carries, "targets": targets}[field]
            resources[(season, week, team, resource)] += value
    if not resources:
        raise CallerResourceBacktestDataError("weekly resource history is empty")
    return scheduled, resources, position_values


def _conversion_factors(
    history: PlayerHistoryInput,
    observed_style: VerifiedTeamStyle,
    *,
    target_season: int,
    history_lookback: int,
) -> tuple[tuple[int, ...], ConversionEstimate]:
    requested = tuple(range(target_season - history_lookback, target_season))
    history_seasons = {
        _integer(row["season"], "opportunity season")
        for row in history.opportunities
    }
    style_seasons = {
        _integer(row["season"], "team-style season")
        for row in observed_style.rows
    }
    training = tuple(
        season
        for season in requested
        if season in history_seasons and season in style_seasons
    )
    minimum_seasons = min(2, history_lookback)
    if (
        len(training) < minimum_seasons
        or training[-1] != target_season - 1
        or training != tuple(range(training[0], target_season))
    ):
        raise CallerResourceBacktestDataError(
            f"target {target_season} lacks a contiguous strictly prior conversion window; "
            f"requested {requested}, usable {training}"
        )
    grouped: dict[tuple[int, str], dict[str, float]] = defaultdict(
        lambda: {"qb_dropbacks": 0.0, "targets": 0.0, "rb_carries": 0.0}
    )
    for row in history.opportunities:
        season = _integer(row["season"], "opportunity season")
        if season not in training:
            continue
        team = canonical_team(row["team"])
        position = row["position"].strip().upper()
        if position not in ROLE_POSITIONS:
            continue
        key = season, team
        if position == "QB":
            grouped[key]["qb_dropbacks"] += _finite(
                row["dropbacks"], "training dropbacks"
            )
        grouped[key]["targets"] += _finite(row["targets"], "training targets")
        if position == "RB":
            grouped[key]["rb_carries"] += _finite(
                row["carries"], "training RB carries"
            )
    try:
        estimate = derive_conversion_factors(
            grouped,
            observed_style.rows,
            training_seasons=training,
            latest_season=target_season - 1,
            recency_factor=RECENCY_FACTOR,
        )
    except ResourceTransformError as error:
        raise CallerResourceBacktestDataError(str(error)) from error
    return requested, estimate


def _resource_forecasts(
    metrics: Mapping[str, float], conversions: Mapping[str, float]
) -> Mapping[str, float]:
    try:
        return resource_forecasts(metrics, conversions)
    except ResourceTransformError as error:
        raise CallerResourceBacktestDataError(str(error)) from error


def _percentile(values: Iterable[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise CallerResourceBacktestDataError("cannot summarize an empty sample")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _conformal_radius(values: Iterable[float], nominal: float) -> tuple[int, float]:
    ordered = sorted(values)
    if not ordered:
        raise CallerResourceBacktestDataError("cannot calibrate empty residuals")
    rank = min(len(ordered), math.ceil((len(ordered) + 1) * nominal))
    return rank, ordered[rank - 1]


def _wilson(successes: int, count: int) -> tuple[float, float]:
    if count <= 0:
        raise CallerResourceBacktestDataError("Wilson interval needs observations")
    z = 1.959963984540054
    observed = successes / count
    denominator = 1 + z * z / count
    center = (observed + z * z / (2 * count)) / denominator
    spread = z * math.sqrt(
        observed * (1 - observed) / count + z * z / (4 * count * count)
    ) / denominator
    return max(0.0, center - spread), min(1.0, center + spread)


def _cluster_interval(
    rows: Iterable[Mapping[str, Any]], *, samples: int, seed: int
) -> tuple[float, float]:
    by_team: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_team[str(row["team"])].append(float(row["paired_delta"]))
    clusters = [tuple(by_team[team]) for team in sorted(by_team)]
    if not clusters:
        raise CallerResourceBacktestDataError("cannot bootstrap empty paired effects")
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(samples):
        sampled = [clusters[rng.randrange(len(clusters))] for _ in clusters]
        flattened = [value for cluster in sampled for value in cluster]
        estimates.append(statistics.mean(flattened))
    return _percentile(estimates, 0.025), _percentile(estimates, 0.975)


def _scope_definitions(
    target_seasons: tuple[int, ...], development: tuple[int, ...], holdout: int
) -> tuple[tuple[str, tuple[int, ...]], ...]:
    return (
        ("development", development),
        ("holdout", (holdout,)),
        ("pooled", target_seasons),
        *((f"season_{season}", (season,)) for season in target_seasons),
    )


def _summaries(
    rows: Iterable[Mapping[str, Any]],
    *,
    target_seasons: tuple[int, ...],
    development: tuple[int, ...],
    holdout: int,
    windows: tuple[int, ...],
) -> list[Mapping[str, Any]]:
    values = list(rows)
    result: list[Mapping[str, Any]] = []
    for scope, seasons in _scope_definitions(target_seasons, development, holdout):
        for week in windows:
            for resource in RESOURCE_INPUTS:
                for model in SOURCE_MODELS:
                    selected = [
                        row
                        for row in values
                        if int(row["target_season"]) in seasons
                        and int(row["week_end"]) == week
                        and row["resource"] == resource
                        and row["model"] == model
                    ]
                    if not selected:
                        continue
                    errors = [float(row["signed_error_per_game"]) for row in selected]
                    absolutes = [abs(value) for value in errors]
                    result.append(
                        {
                            "scope": scope,
                            "scope_seasons": "|".join(map(str, seasons)),
                            "week_end": week,
                            "resource": resource,
                            "model": model,
                            "team_season_count": len(selected),
                            "team_cluster_count": len({str(row["team"]) for row in selected}),
                            "mean_forecast_per_game": round(
                                statistics.mean(float(row["forecast_per_game"]) for row in selected), 6
                            ),
                            "mean_actual_per_game": round(
                                statistics.mean(float(row["actual_per_game"]) for row in selected), 6
                            ),
                            "mean_signed_error_per_game": round(statistics.mean(errors), 6),
                            "mean_absolute_error_per_game": round(statistics.mean(absolutes), 6),
                            "root_mean_squared_error_per_game": round(
                                math.sqrt(statistics.mean(value * value for value in errors)), 6
                            ),
                            "median_absolute_error_per_game": round(statistics.median(absolutes), 6),
                        }
                    )
    return result


def _paired_summaries(
    rows: Iterable[Mapping[str, Any]],
    *,
    target_seasons: tuple[int, ...],
    development: tuple[int, ...],
    holdout: int,
    windows: tuple[int, ...],
    bootstrap_samples: int,
    random_seed: int,
) -> list[Mapping[str, Any]]:
    values = list(rows)
    result: list[Mapping[str, Any]] = []
    for scope_index, (scope, seasons) in enumerate(
        _scope_definitions(target_seasons, development, holdout)
    ):
        for week in windows:
            for resource_index, resource in enumerate(RESOURCE_INPUTS):
                selected = [
                    row
                    for row in values
                    if int(row["target_season"]) in seasons
                    and int(row["week_end"]) == week
                    and row["resource"] == resource
                ]
                if not selected:
                    continue
                lower, upper = _cluster_interval(
                    selected,
                    samples=bootstrap_samples,
                    seed=random_seed + scope_index * 1000 + week * 10 + resource_index,
                )
                candidate_mae = statistics.mean(
                    float(row["candidate_absolute_error_per_game"]) for row in selected
                )
                baseline_mae = statistics.mean(
                    float(row["baseline_absolute_error_per_game"]) for row in selected
                )
                result.append(
                    {
                        "scope": scope,
                        "scope_seasons": "|".join(map(str, seasons)),
                        "week_end": week,
                        "resource": resource,
                        "pair_count": len(selected),
                        "team_cluster_count": len({str(row["team"]) for row in selected}),
                        "candidate_win_count": sum(row["candidate_wins"] == "true" for row in selected),
                        "candidate_win_rate": round(
                            sum(row["candidate_wins"] == "true" for row in selected) / len(selected), 6
                        ),
                        "candidate_mean_absolute_error_per_game": round(candidate_mae, 6),
                        "baseline_mean_absolute_error_per_game": round(baseline_mae, 6),
                        "relative_improvement_pct": round(
                            100 * (baseline_mae - candidate_mae) / baseline_mae, 3
                        ),
                        "mean_paired_delta": round(candidate_mae - baseline_mae, 6),
                        "team_cluster_bootstrap_95pct_lower": round(lower, 6),
                        "team_cluster_bootstrap_95pct_upper": round(upper, 6),
                    }
                )
    return result


def build_caller_resource_backtest(
    backtests: Iterable[str | Path],
    player_history: str | Path,
    observed_styles: str | Path,
    *,
    development_seasons: Iterable[int] = (2023, 2024),
    holdout_season: int = 2025,
    history_lookback: int = 3,
    bootstrap_samples: int = 5000,
    random_seed: int = 20260903,
    expected_team_count: int = 32,
) -> CallerResourceBacktestResult:
    """Recreate and score historical caller-aware team opportunity pools."""

    development = tuple(sorted(set(development_seasons)))
    if len(development) < 2 or holdout_season in development:
        raise CallerResourceBacktestDataError(
            "use at least two development seasons and a separate holdout"
        )
    if history_lookback < 1:
        raise CallerResourceBacktestDataError("history_lookback must be positive")
    if bootstrap_samples < 100:
        raise CallerResourceBacktestDataError("bootstrap_samples must be at least 100")
    if expected_team_count < 2:
        raise CallerResourceBacktestDataError("expected_team_count must be at least 2")

    transition_inputs = tuple(_load_transition(path) for path in backtests)
    by_season = {item.target_season: item for item in transition_inputs}
    expected_seasons = set(development) | {holdout_season}
    if len(by_season) != len(transition_inputs) or set(by_season) != expected_seasons:
        raise CallerResourceBacktestDataError(
            "transition snapshots must cover every declared target season once"
        )
    window_sets = {item.windows for item in transition_inputs}
    if len(window_sets) != 1:
        raise CallerResourceBacktestDataError("transition snapshots use different windows")
    windows = next(iter(window_sets))
    history = _load_player_history(player_history)
    try:
        observed_style = load_verified_team_style(observed_styles)
    except ResourceTransformError as error:
        raise CallerResourceBacktestDataError(str(error)) from error
    for transition in transition_inputs:
        bound_style = [
            raw
            for path, raw in transition.raw_by_path.items()
            if Path(path).resolve() == observed_style.path.resolve()
        ]
        if len(bound_style) != 1 or bound_style[0] != observed_style.raw_by_path[str(observed_style.path)]:
            raise CallerResourceBacktestDataError(
                f"transition {transition.target_season} is not bound to the supplied team-style snapshot"
            )
    scheduled, actual_resources, position_values = _history_values(history)

    input_raw: dict[str, bytes] = {}
    for item in transition_inputs:
        _merge_raw(input_raw, item.raw_by_path)
    _merge_raw(input_raw, history.raw_by_path)
    _merge_raw(input_raw, observed_style.raw_by_path)

    conversions: dict[int, tuple[tuple[int, ...], ConversionEstimate]] = {}
    for season in sorted(expected_seasons):
        conversions[season] = _conversion_factors(
            history,
            observed_style,
            target_season=season,
            history_lookback=history_lookback,
        )

    prediction_rows: list[Mapping[str, Any]] = []
    conversion_rows: list[Mapping[str, Any]] = []
    for season in sorted(expected_seasons):
        transition = by_season[season]
        grouped: dict[tuple[int, str, str], dict[str, float]] = defaultdict(dict)
        actual_grouped: dict[tuple[int, str], dict[str, float]] = defaultdict(dict)
        cohorts: dict[tuple[int, str], str] = {}
        for row in transition.predictions:
            model = row["model"].strip()
            if model not in SOURCE_MODELS:
                continue
            week = _integer(row["week_end"], f"{season} prediction week")
            team = row["team"].strip().upper()
            metric = row["metric"].strip()
            key = week, team, model
            if not metric or metric in grouped[key]:
                raise CallerResourceBacktestDataError(
                    f"duplicate/blank metric for {season} {team} {week} {model}"
                )
            grouped[key][metric] = _finite(
                row["forecast_value"], f"{season} {team} {metric} forecast"
            )
            actual_key = week, team
            actual_value = _finite(
                row["actual_value"], f"{season} {team} {metric} actual"
            )
            prior_actual = actual_grouped[actual_key].get(metric)
            if prior_actual is not None and abs(prior_actual - actual_value) > 1e-12:
                raise CallerResourceBacktestDataError(
                    f"actual metric differs across models for {season} {team} {week} {metric}"
                )
            actual_grouped[actual_key][metric] = actual_value
            cohort_key = week, team
            cohort = row["caller_cohort"].strip()
            if cohort_key in cohorts and cohorts[cohort_key] != cohort:
                raise CallerResourceBacktestDataError(
                    f"caller cohort changes within {season} {team} Weeks 1-{week}"
                )
            cohorts[cohort_key] = cohort

        requested_training, conversion = conversions[season]
        factors = conversion.factors
        included_team_windows = {
            key: row
            for key, row in transition.team_windows.items()
            if row["excluded"].strip().lower() == "false"
        }
        for week in windows:
            all_teams = {
                team for (row_week, team) in transition.team_windows if row_week == week
            }
            if len(all_teams) != expected_team_count:
                raise CallerResourceBacktestDataError(
                    f"{season} Weeks 1-{week} has {len(all_teams)} transition teams; "
                    f"expected {expected_team_count}"
                )
            teams = {team for (row_week, team) in included_team_windows if row_week == week}
            if not teams:
                raise CallerResourceBacktestDataError(
                    f"{season} Weeks 1-{week} has no eligible transition teams"
                )
            aggregate_qb_dropbacks = aggregate_targets = 0.0
            aggregate_rb_carries = 0.0
            aggregate_pass_plays = aggregate_non_qb_rush_plays = 0.0
            for team in sorted(teams):
                team_row = included_team_windows[(week, team)]
                games = _integer(
                    team_row["actual_games"], f"{season} {team} actual games"
                )
                scheduled_games = sum(
                    (season, game_week, team) in scheduled
                    for game_week in range(1, week + 1)
                )
                if scheduled_games != games:
                    raise CallerResourceBacktestDataError(
                        f"schedule games differ from transition target for {season} "
                        f"{team} Weeks 1-{week}: {scheduled_games} != {games}"
                    )
                actual_counts = {
                    resource: sum(
                        actual_resources.get((season, game_week, team, resource), 0.0)
                        for game_week in range(1, week + 1)
                    )
                    for resource in RESOURCE_INPUTS
                }
                actual_metrics = actual_grouped.get((week, team))
                if actual_metrics is None:
                    raise CallerResourceBacktestDataError(
                        f"missing actual style metrics for {season} {team} Weeks 1-{week}"
                    )
                missing_actual = set().union(*RESOURCE_INPUTS.values()) - set(actual_metrics)
                if missing_actual:
                    raise CallerResourceBacktestDataError(
                        f"actual style is missing metrics for {season} {team} Weeks 1-{week}: "
                        f"{sorted(missing_actual)}"
                    )
                actual_plays = actual_metrics["plays_per_game"] * games
                actual_pass_plays = actual_plays * actual_metrics["pass_rate"]
                actual_non_qb_rush_plays = (
                    actual_plays
                    * (1 - actual_metrics["pass_rate"])
                    * (1 - actual_metrics["designed_qb_run_share"])
                )
                aggregate_qb_dropbacks += actual_counts["QB_DROPBACKS"]
                aggregate_targets += sum(
                    sum(
                        position_values.get(
                            (season, game_week, team, f"{position}_TARGETS"), 0.0
                        )
                        for game_week in range(1, week + 1)
                    )
                    for position in ROLE_POSITIONS
                )
                aggregate_rb_carries += actual_counts["RB_CARRIES"]
                aggregate_pass_plays += actual_pass_plays
                aggregate_non_qb_rush_plays += actual_non_qb_rush_plays
                for model in SOURCE_MODELS:
                    metrics = grouped.get((week, team, model))
                    if metrics is None:
                        raise CallerResourceBacktestDataError(
                            f"missing model forecast for {season} {team} {week} {model}"
                        )
                    forecasts = _resource_forecasts(
                        metrics,
                        factors,
                    )
                    for resource, forecast in forecasts.items():
                        actual_count = actual_counts[resource]
                        actual_per_game = actual_count / games
                        signed = forecast - actual_per_game
                        prediction_rows.append(
                            {
                                "target_season": season,
                                "week_start": 1,
                                "week_end": week,
                                "team": team,
                                "caller_cohort": cohorts[(week, team)],
                                "model": model,
                                "resource": resource,
                                "forecast_per_game": round(forecast, 6),
                                "actual_games": games,
                                "actual_opportunities": round(actual_count, 6),
                                "actual_per_game": round(actual_per_game, 6),
                                "signed_error_per_game": round(signed, 6),
                                "absolute_error_per_game": round(abs(signed), 6),
                                "qb_dropbacks_per_pass_play_factor": round(
                                    factors["qb_dropbacks_per_pass_play"], 9
                                ),
                                "target_per_pass_play_factor": round(
                                    factors["target_per_pass_play"], 9
                                ),
                                "rb_carries_per_non_qb_rush_play_factor": round(
                                    factors["rb_carries_per_non_qb_rush_play"], 9
                                ),
                            }
                        )
            if aggregate_pass_plays <= 0 or aggregate_non_qb_rush_plays <= 0:
                raise CallerResourceBacktestDataError(
                    f"{season} Weeks 1-{week} cannot calculate actual conversions"
                )
            conversion_rows.append(
                {
                    "target_season": season,
                    "week_end": week,
                    "requested_training_seasons": "|".join(
                        map(str, requested_training)
                    ),
                    "training_seasons": "|".join(
                        map(str, conversion.training_seasons)
                    ),
                    "training_team_season_count": conversion.team_season_count,
                    "qb_dropbacks_per_pass_play_forecast": round(
                        factors["qb_dropbacks_per_pass_play"], 9
                    ),
                    "qb_dropbacks_per_pass_play_actual": round(
                        aggregate_qb_dropbacks / aggregate_pass_plays, 9
                    ),
                    "target_per_pass_play_forecast": round(
                        factors["target_per_pass_play"], 9
                    ),
                    "target_per_pass_play_actual": round(
                        aggregate_targets / aggregate_pass_plays, 9
                    ),
                    "rb_carries_per_non_qb_rush_play_forecast": round(
                        factors["rb_carries_per_non_qb_rush_play"], 9
                    ),
                    "rb_carries_per_non_qb_rush_play_actual": round(
                        aggregate_rb_carries / aggregate_non_qb_rush_plays, 9
                    ),
                    "eligible_team_count": len(teams),
                }
            )

    expected_prediction_count = sum(
        sum(
            row["excluded"].strip().lower() == "false"
            for row in item.team_windows.values()
        )
        for item in transition_inputs
    ) * len(SOURCE_MODELS) * len(RESOURCE_INPUTS)
    if len(prediction_rows) != expected_prediction_count:
        raise CallerResourceBacktestDataError(
            f"resource prediction count {len(prediction_rows)} != {expected_prediction_count}"
        )

    by_prediction = {
        (
            int(row["target_season"]),
            int(row["week_end"]),
            str(row["team"]),
            str(row["resource"]),
            str(row["model"]),
        ): row
        for row in prediction_rows
    }
    paired_rows: list[Mapping[str, Any]] = []
    base_keys = {
        key[:4]
        for key in by_prediction
        if key[4] == CANDIDATE_MODEL
    }
    for season, week, team, resource in sorted(base_keys):
        candidate = by_prediction[(season, week, team, resource, CANDIDATE_MODEL)]
        baseline = by_prediction[(season, week, team, resource, BASELINE_MODEL)]
        candidate_error = float(candidate["absolute_error_per_game"])
        baseline_error = float(baseline["absolute_error_per_game"])
        paired_rows.append(
            {
                "target_season": season,
                "week_end": week,
                "team": team,
                "caller_cohort": candidate["caller_cohort"],
                "resource": resource,
                "candidate": CANDIDATE_MODEL,
                "baseline": BASELINE_MODEL,
                "candidate_absolute_error_per_game": round(candidate_error, 6),
                "baseline_absolute_error_per_game": round(baseline_error, 6),
                "paired_delta": round(candidate_error - baseline_error, 6),
                "candidate_wins": str(candidate_error < baseline_error).lower(),
            }
        )

    target_seasons = tuple(sorted(expected_seasons))
    summary_rows = _summaries(
        prediction_rows,
        target_seasons=target_seasons,
        development=development,
        holdout=holdout_season,
        windows=windows,
    )
    paired_summary_rows = _paired_summaries(
        paired_rows,
        target_seasons=target_seasons,
        development=development,
        holdout=holdout_season,
        windows=windows,
        bootstrap_samples=bootstrap_samples,
        random_seed=random_seed,
    )

    calibration_rows: list[Mapping[str, Any]] = []
    coverage_rows: list[Mapping[str, Any]] = []
    radius_by_key: dict[tuple[int, str], float] = {}
    for week in windows:
        for resource in RESOURCE_INPUTS:
            development_errors = [
                float(row["absolute_error_per_game"])
                for row in prediction_rows
                if row["model"] == CANDIDATE_MODEL
                and int(row["target_season"]) in development
                and int(row["week_end"]) == week
                and row["resource"] == resource
            ]
            rank, radius = _conformal_radius(development_errors, NOMINAL_COVERAGE)
            radius_by_key[(week, resource)] = radius
            holdout_rows = [
                row
                for row in prediction_rows
                if row["model"] == CANDIDATE_MODEL
                and int(row["target_season"]) == holdout_season
                and int(row["week_end"]) == week
                and row["resource"] == resource
            ]
            covered = 0
            for row in holdout_rows:
                forecast = float(row["forecast_per_game"])
                actual = float(row["actual_per_game"])
                is_covered = abs(actual - forecast) <= radius
                covered += is_covered
                coverage_rows.append(
                    {
                        "target_season": holdout_season,
                        "week_end": week,
                        "team": row["team"],
                        "caller_cohort": row["caller_cohort"],
                        "resource": resource,
                        "forecast_per_game": round(forecast, 6),
                        "actual_per_game": round(actual, 6),
                        "absolute_error_per_game_radius": round(radius, 6),
                        "interval_low": round(max(0.0, forecast - radius), 6),
                        "interval_high": round(forecast + radius, 6),
                        "covered": str(is_covered).lower(),
                    }
                )
            lower, upper = _wilson(covered, len(holdout_rows))
            calibration_rows.append(
                {
                    "resource": resource,
                    "week_end": week,
                    "development_seasons": "|".join(map(str, development)),
                    "development_team_season_count": len(development_errors),
                    "nominal_coverage": NOMINAL_COVERAGE,
                    "finite_sample_rank": rank,
                    "absolute_error_per_game_radius": round(radius, 6),
                    "holdout_season": holdout_season,
                    "holdout_team_count": len(holdout_rows),
                    "holdout_covered_count": covered,
                    "holdout_coverage": round(covered / len(holdout_rows), 6),
                    "wilson_95pct_lower": round(lower, 6),
                    "wilson_95pct_upper": round(upper, 6),
                    "holdout_mean_interval_width": round(2 * radius, 6),
                }
            )

    joint_coverage_rows: list[Mapping[str, Any]] = []
    for week in windows:
        selected = [row for row in coverage_rows if int(row["week_end"]) == week]
        by_team_coverage: dict[str, list[bool]] = defaultdict(list)
        for row in selected:
            by_team_coverage[str(row["team"])].append(row["covered"] == "true")
        if any(len(values) != len(RESOURCE_INPUTS) for values in by_team_coverage.values()):
            raise CallerResourceBacktestDataError(
                f"holdout joint coverage lacks all resources in Weeks 1-{week}"
            )
        all_covered = sum(all(values) for values in by_team_coverage.values())
        joint_coverage_rows.append(
            {
                "target_season": holdout_season,
                "week_end": week,
                "team_count": len(by_team_coverage),
                "resource_count": len(RESOURCE_INPUTS),
                "all_resources_covered_team_count": all_covered,
                "all_resources_covered_rate": round(
                    all_covered / len(by_team_coverage), 6
                ),
                "interpretation": (
                    "Descriptive simultaneous coverage of six separately calibrated "
                    "marginal bands; no joint 90% guarantee."
                ),
            }
        )

    paired_summary_index = {
        (row["scope"], int(row["week_end"]), row["resource"]): row
        for row in paired_summary_rows
    }
    mean_gate_rows: list[Mapping[str, Any]] = []
    for resource in RESOURCE_INPUTS:
        development_rows = [
            paired_summary_index[("development", week, resource)] for week in windows
        ]
        holdout_rows = [
            paired_summary_index[("holdout", week, resource)] for week in windows
        ]
        development_point = all(
            float(row["mean_paired_delta"]) < 0 for row in development_rows
        )
        holdout_point = all(float(row["mean_paired_delta"]) < 0 for row in holdout_rows)
        holdout_interval = all(
            float(row["team_cluster_bootstrap_95pct_upper"]) < 0
            for row in holdout_rows
        )
        mean_gate_rows.append(
            {
                "resource": resource,
                "development_point_improvement_both_windows": development_point,
                "holdout_point_improvement_both_windows": holdout_point,
                "holdout_interval_below_zero_both_windows": holdout_interval,
                "promotion_gate_pass": development_point and holdout_point and holdout_interval,
            }
        )
    calibration_gate_pass = all(
        float(row["holdout_coverage"]) >= NOMINAL_COVERAGE
        for row in calibration_rows
    )
    promoted_resources = [
        row["resource"] for row in mean_gate_rows if row["promotion_gate_pass"]
    ]
    undercovered = [
        {
            "resource": row["resource"],
            "week_end": row["week_end"],
            "coverage": row["holdout_coverage"],
        }
        for row in calibration_rows
        if float(row["holdout_coverage"]) < NOMINAL_COVERAGE
    ]
    evaluation: Mapping[str, Any] = {
        "status": "completed_direct_early_window_resource_test",
        "data_split": {
            "development_seasons": list(development),
            "holdout_season": holdout_season,
            "holdout_used_for_model_or_radius_selection": False,
            "windows": [f"Weeks 1-{week}" for week in windows],
        },
        "forecast_contract": {
            "source_style_models": list(SOURCE_MODELS),
            "candidate": CANDIDATE_MODEL,
            "baseline": BASELINE_MODEL,
            "resources": list(RESOURCE_INPUTS),
            "conversion_factors": (
                "League official QB-dropback/PBP-pass-play, target/PBP-pass-play, "
                f"and RB-carry/non-QB-PBP-rush-play ratios from up to {history_lookback} "
                "strictly prior matched seasons with 0.65 annual recency weighting. "
                "The 2023 target uses 2021-2022 because the preserved style series "
                "begins in 2021."
            ),
            "production_alignment": (
                "The backtest and production role builder share "
                "resource_transform.resource_forecasts; eligible PBP pass/rush units "
                "are never treated as official player-stat units, and outcomes come "
                "from GSIS-keyed weekly player opportunities."
            ),
        },
        "caller_aware_mean_gate": {
            "criteria": (
                "Lower MAE than shrunken persistence in both development and holdout "
                "windows, with both holdout team-clustered 95% intervals below zero."
            ),
            "resource_results": mean_gate_rows,
            "promoted_resources": promoted_resources,
            "decision": (
                "no_resource_clears_strict_direct_mean_gate"
                if not promoted_resources
                else "resource_specific_direct_mean_support"
            ),
        },
        "caller_aware_interval_gate": {
            "nominal_coverage": NOMINAL_COVERAGE,
            "every_resource_window_at_nominal_on_holdout": calibration_gate_pass,
            "undercovered_resource_windows": undercovered,
            "decision": "do_not_replace_provisional_full_season_resource_envelopes",
            "reason": (
                "The direct test covers only early windows and at least one marginal "
                "resource band misses nominal holdout coverage."
            ),
        },
        "recommended_2026_policy": (
            "Apply the denominator-consistent resource transform as a pre-outcome "
            "definition correction in a new immutable 2026 freeze. Do not promote "
            "any caller-aware resource model or replace provisional full-season "
            "envelopes from this early-window test; explicitly flag RB-carry and "
            "QB-rush model risk, and do not claim joint coverage from marginal bands."
        ),
        "limitations": [
            "The direct transition inputs contain Weeks 1-6 and Weeks 1-8, not a Week-18 target.",
            "Only three target seasons are available and 2025 is the sole holdout.",
            "QB carries include official rushing attempts whose definition is not identical to the scramble-plus-designed-run forecast transform.",
            "The preserved team-style series begins in 2021, so the 2023 conversion uses two rather than three strictly prior seasons.",
            "Player opportunity revisions were retrieved after the target seasons; target outcomes are used only for scoring.",
            "Marginal resource bands are not a calibrated simultaneous six-resource interval.",
        ],
    }
    return CallerResourceBacktestResult(
        target_seasons=target_seasons,
        development_seasons=development,
        holdout_season=holdout_season,
        windows=windows,
        history_lookback=history_lookback,
        bootstrap_samples=bootstrap_samples,
        random_seed=random_seed,
        input_raw=input_raw,
        prediction_rows=tuple(prediction_rows),
        summary_rows=tuple(summary_rows),
        paired_rows=tuple(paired_rows),
        paired_summary_rows=tuple(paired_summary_rows),
        conversion_rows=tuple(conversion_rows),
        calibration_rows=tuple(calibration_rows),
        coverage_rows=tuple(coverage_rows),
        joint_coverage_rows=tuple(joint_coverage_rows),
        evaluation=evaluation,
    )


def _csv_bytes(rows: Iterable[Mapping[str, Any]], fields: tuple[str, ...]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def write_caller_resource_backtest_snapshot(
    result: CallerResourceBacktestResult,
    root: str | Path,
    *,
    created_at: datetime | None = None,
) -> Path:
    """Publish an immutable hash-bound direct resource evaluation."""

    created = created_at or datetime.now(timezone.utc)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    created = created.astimezone(timezone.utc)
    season_label = "-".join(map(str, result.target_seasons))
    parent = Path(root) / "caller_resource_backtest" / season_label
    destination = parent / created.strftime("%Y%m%dT%H%M%S.%fZ")
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"caller resource snapshot exists: {destination}")

    artifacts: list[tuple[str, bytes, tuple[str, ...] | None]] = [
        ("resource_predictions.csv", _csv_bytes(result.prediction_rows, PREDICTION_FIELDS), PREDICTION_FIELDS),
        ("model_summary.csv", _csv_bytes(result.summary_rows, SUMMARY_FIELDS), SUMMARY_FIELDS),
        ("paired_effects.csv", _csv_bytes(result.paired_rows, PAIRED_FIELDS), PAIRED_FIELDS),
        ("paired_summary.csv", _csv_bytes(result.paired_summary_rows, PAIRED_SUMMARY_FIELDS), PAIRED_SUMMARY_FIELDS),
        ("conversion_factors.csv", _csv_bytes(result.conversion_rows, CONVERSION_FIELDS), CONVERSION_FIELDS),
        ("calibration.csv", _csv_bytes(result.calibration_rows, CALIBRATION_FIELDS), CALIBRATION_FIELDS),
        ("coverage_predictions.csv", _csv_bytes(result.coverage_rows, COVERAGE_FIELDS), COVERAGE_FIELDS),
        ("joint_coverage.csv", _csv_bytes(result.joint_coverage_rows, JOINT_COVERAGE_FIELDS), JOINT_COVERAGE_FIELDS),
        (
            "evaluation.json",
            (json.dumps(result.evaluation, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            None,
        ),
    ]
    artifact_manifest: dict[str, Mapping[str, Any]] = {}
    for filename, raw, fields in artifacts:
        metadata: dict[str, Any] = {"bytes": len(raw), "sha256": _sha256(raw)}
        if fields is not None:
            metadata["fields"] = list(fields)
        artifact_manifest[filename] = metadata
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "model_status": "retrospective_direct_resource_diagnostic_not_prospective_calibration",
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "target_seasons": list(result.target_seasons),
        "development_seasons": list(result.development_seasons),
        "holdout_season": result.holdout_season,
        "target_windows": [f"Weeks 1-{week}" for week in result.windows],
        "history_lookback": result.history_lookback,
        "bootstrap": {
            "samples": result.bootstrap_samples,
            "random_seed": result.random_seed,
            "cluster": "destination team across target seasons",
            "confidence": 0.95,
        },
        "methodology": result.evaluation["forecast_contract"],
        "quality": {
            "resource_count": len(RESOURCE_INPUTS),
            "prediction_count": len(result.prediction_rows),
            "paired_effect_count": len(result.paired_rows),
            "calibration_row_count": len(result.calibration_rows),
            "coverage_prediction_count": len(result.coverage_rows),
            "mean_decision": result.evaluation["caller_aware_mean_gate"]["decision"],
            "interval_decision": result.evaluation["caller_aware_interval_gate"]["decision"],
        },
        "input_sha256": {
            path: _sha256(raw) for path, raw in sorted(result.input_raw.items())
        },
        "artifacts": artifact_manifest,
    }
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
    try:
        for filename, raw, _ in artifacts:
            (staging / filename).write_bytes(raw)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
