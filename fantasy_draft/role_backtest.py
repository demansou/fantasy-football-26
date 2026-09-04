"""Time-correct retrospective tests for conditional player opportunity priors.

The evaluator freezes each target-season player universe at the Week 1 roster
and opening depth chart, uses only earlier-season opportunities as history, and
then supplies actual weekly active status as an evaluation-only oracle. This
isolates conditional role from the separate availability model. Every later
entrant remains a zero-share forecast, so roster churn is still visible.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import random
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .player_roles import (
    DEPTH_WEIGHTS,
    TRANSFER_RELIABILITY_MULTIPLIER,
)


SCHEMA_VERSION = "1.1.0"
MODEL_VERSION = "player-role-retrospective-backtest-v0.2.0"
UNALLOCATED_ID = "__UNALLOCATED__"
WINDOWS = (4, 8, 18)
MODELS = ("depth_only", "prior_share_only", "blend_v0")
RESOURCE_SPECS: Mapping[str, tuple[str, str]] = {
    "QB_DROPBACKS": ("QB", "dropbacks"),
    "QB_RUSH_OPPORTUNITIES": ("QB", "carries"),
    "RB_CARRIES": ("RB", "carries"),
    "RB_TARGETS": ("RB", "targets"),
    "WR_TARGETS": ("WR", "targets"),
    "TE_TARGETS": ("TE", "targets"),
}
# Freeze the universal v0 formula independently of later production-model
# choices.  Otherwise a future code change would rewrite the meaning of this
# retrospective benchmark.
FROZEN_RESOURCE_HISTORY_WEIGHT: Mapping[str, float] = {
    "QB_DROPBACKS": 0.15,
    "QB_RUSH_OPPORTUNITIES": 0.25,
    "RB_CARRIES": 0.45,
    "RB_TARGETS": 0.50,
    "WR_TARGETS": 0.55,
    "TE_TARGETS": 0.55,
}

PREDICTION_FIELDS = (
    "target_season", "window_end", "team", "position", "resource", "model",
    "gsis_id", "player_name", "row_type", "opening_candidate", "depth_rank",
    "historical_share", "historical_weighted_games", "predicted_share",
    "actual_share", "actual_opportunities", "absolute_error",
    "depth_temporal_precision",
)
ROOM_FIELDS = (
    "target_season", "window_end", "team", "position", "resource", "model",
    "opening_candidate_count", "actual_player_count", "prediction_share_sum",
    "forecast_unallocated_share", "opening_candidate_actual_share",
    "total_variation_distance", "player_mae",
    "predicted_top_gsis_id", "actual_top_gsis_id", "top_role_hit",
    "depth_temporal_precision",
)
EVALUATION_FIELDS = (
    "segment", "target_season", "window_end", "resource", "model", "room_count",
    "mean_total_variation", "median_total_variation", "top_role_accuracy",
    "mean_forecast_unallocated_share", "mean_opening_candidate_coverage", "mean_player_mae",
    "delta_tv_vs_depth_only", "delta_tv_vs_prior_share_only",
)
COMPARISON_FIELDS = (
    "window_end", "resource", "challenger", "baseline", "room_count", "cluster_count",
    "mean_tv_delta", "delta_ci90_low", "delta_ci90_high", "paired_room_win_rate",
    "interpretation",
)
REVIEW_FIELDS = (
    "target_season", "team", "position", "resource", "issue", "details",
)


class RoleBacktestDataError(ValueError):
    """Raised when historical inputs cannot support an audited role test."""


@dataclass(frozen=True)
class RoleBacktestResult:
    history_path: Path
    input_hashes: Mapping[str, str]
    target_seasons: tuple[int, ...]
    history_lookback: int
    bootstrap_samples: int
    random_seed: int
    prediction_rows: tuple[Mapping[str, Any], ...]
    room_rows: tuple[Mapping[str, Any], ...]
    evaluation_rows: tuple[Mapping[str, Any], ...]
    comparison_rows: tuple[Mapping[str, Any], ...]
    source_review: tuple[Mapping[str, Any], ...]
    recommendation: Mapping[str, Any]


def _resolve(path: str | Path, filename: str) -> Path:
    resolved = Path(path)
    if resolved.is_dir():
        resolved = resolved / filename
    if not resolved.is_file():
        raise RoleBacktestDataError(f"input does not exist: {resolved}")
    return resolved


def _read_csv(path: Path, required: set[str]) -> tuple[bytes, list[dict[str, str]]]:
    raw = path.read_bytes()
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        fields = set(reader.fieldnames or ())
        rows = list(reader)
    except UnicodeDecodeError as error:
        raise RoleBacktestDataError(f"CSV is not UTF-8: {path}") from error
    missing = required - fields
    if missing or not rows:
        raise RoleBacktestDataError(
            f"CSV is empty or missing fields {sorted(missing)}: {path}"
        )
    return raw, rows


def _number(value: Any, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise RoleBacktestDataError(f"{context} must be numeric") from error
    if not math.isfinite(result) or result < 0:
        raise RoleBacktestDataError(f"{context} must be finite and nonnegative")
    return result


def _integer(value: Any, context: str) -> int:
    number = _number(value, context)
    if not number.is_integer():
        raise RoleBacktestDataError(f"{context} must be an integer")
    return int(number)


def _optional_rank(value: Any) -> int | None:
    if value is None or not str(value).strip():
        return None
    rank = _integer(value, "depth rank")
    return rank if rank >= 1 else None


def _depth_weight(position: str, rank: int | None) -> float:
    if rank is None:
        return 0.02
    weights = DEPTH_WEIGHTS[position]
    if rank <= len(weights):
        return weights[rank - 1]
    return weights[-1] * (0.55 ** (rank - len(weights)))


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise RoleBacktestDataError("cannot summarize an empty sample")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def historical_opportunity_groups(
    rows: Iterable[Mapping[str, str]],
) -> tuple[
    dict[tuple[int, str, str, str], dict[str, Any]],
    dict[tuple[int, str, str, str], float],
]:
    players: dict[tuple[int, str, str, str], dict[str, Any]] = {}
    team_totals: dict[tuple[int, str, str, str], float] = defaultdict(float)
    for row in rows:
        season = _integer(row["season"], "opportunity season")
        week = _integer(row["week"], "opportunity week")
        if not 1 <= week <= 18:
            continue
        team = row["team"]
        position = row["position"]
        player_id = row["gsis_id"]
        if not team or position not in {"QB", "RB", "WR", "TE"} or not player_id:
            continue
        key = season, team, position, player_id
        record = players.setdefault(key, {
            "player_name": row["player_name"], "weeks": set(),
            "dropbacks": 0.0, "carries": 0.0, "targets": 0.0,
        })
        record["weeks"].add(week)
        for field in ("dropbacks", "carries", "targets"):
            value = _number(row[field], f"{season} {team} {player_id} {field}")
            record[field] += value
            team_totals[(season, team, position, field)] += value
    return players, team_totals


def _historical_estimate(
    player_id: str,
    *,
    target_season: int,
    current_team: str,
    position: str,
    field: str,
    lookback: int,
    players: Mapping[tuple[int, str, str, str], Mapping[str, Any]],
    team_totals: Mapping[tuple[int, str, str, str], float],
) -> dict[str, Any]:
    relevant = [
        (key, value)
        for key, value in players.items()
        if key[2] == position
        and key[3] == player_id
        and target_season - lookback <= key[0] < target_season
    ]
    weighted_numerator = 0.0
    weighted_denominator = 0.0
    weighted_games = 0.0
    for (season, team, _, _), row in relevant:
        recency = 0.65 ** ((target_season - 1) - season)
        transfer = 1.0 if team == current_team else 0.70
        weight = recency * transfer
        weighted_numerator += weight * float(row[field])
        weighted_denominator += weight * team_totals.get(
            (season, team, position, field), 0.0
        )
        weighted_games += weight * len(row["weeks"])
    latest_teams: set[str] = set()
    if relevant:
        latest = max(key[0] for key, _ in relevant)
        latest_teams = {key[1] for key, _ in relevant if key[0] == latest}
    return {
        "share": (
            weighted_numerator / weighted_denominator
            if weighted_denominator > 0 else 0.0
        ),
        "weighted_games": weighted_games,
        "has_history": weighted_denominator > 0,
        "same_team_latest": current_team in latest_teams,
    }


def candidate_role_predictions(
    candidates: list[Mapping[str, str]],
    *,
    target_season: int,
    team: str,
    position: str,
    resource: str,
    field: str,
    lookback: int,
    depth: Mapping[tuple[int, str, str, str], Mapping[str, str]],
    players: Mapping[tuple[int, str, str, str], Mapping[str, Any]],
    team_totals: Mapping[tuple[int, str, str, str], float],
) -> tuple[dict[str, dict[str, float]], dict[str, Mapping[str, Any]]]:
    details: dict[str, dict[str, Any]] = {}
    depth_values: list[float] = []
    for candidate in candidates:
        player_id = candidate["gsis_id"]
        depth_row = depth.get((target_season, team, position, player_id), {})
        rank = _optional_rank(depth_row.get("depth_rank"))
        weight = _depth_weight(position, rank)
        if position == "RB" and depth_row.get("depth_position") == "FB":
            weight *= 0.08 if resource == "RB_CARRIES" else 0.15
        depth_values.append(weight)
        details[player_id] = {
            "depth_rank": rank,
            "history": _historical_estimate(
                player_id,
                target_season=target_season,
                current_team=team,
                position=position,
                field=field,
                lookback=lookback,
                players=players,
                team_totals=team_totals,
            ),
        }
    depth_total = sum(depth_values)
    if depth_total <= 0:
        raise RoleBacktestDataError(f"{target_season} {team} {resource} has no depth mass")
    for candidate, weight in zip(candidates, depth_values, strict=True):
        details[candidate["gsis_id"]]["depth_prior"] = weight / depth_total

    history_total = sum(item["history"]["share"] for item in details.values())
    raw: dict[str, dict[str, float]] = {model: {} for model in MODELS}
    for player_id, item in details.items():
        history = item["history"]
        depth_prior = item["depth_prior"]
        history_normalized = (
            history["share"] / history_total if history_total > 0 else depth_prior
        )
        reliability = (
            min(
                0.80,
                history["weighted_games"]
                / (history["weighted_games"] + (6.0 if position == "QB" else 8.0)),
            )
            if history["has_history"] else 0.0
        )
        if reliability and not history["same_team_latest"]:
            reliability *= TRANSFER_RELIABILITY_MULTIPLIER
        history_signal = reliability * history_normalized + (1.0 - reliability) * depth_prior
        raw["depth_only"][player_id] = depth_prior
        raw["prior_share_only"][player_id] = (
            history_normalized if history_total > 0 else depth_prior
        )
        raw["blend_v0"][player_id] = (
            FROZEN_RESOURCE_HISTORY_WEIGHT[resource] * history_signal
            + (1.0 - FROZEN_RESOURCE_HISTORY_WEIGHT[resource]) * depth_prior
        )
    predictions: dict[str, dict[str, float]] = {}
    for model, values in raw.items():
        total = sum(values.values())
        if total <= 0:
            raise RoleBacktestDataError(
                f"{target_season} {team} {resource} {model} has no forecast mass"
            )
        predictions[model] = {key: value / total for key, value in values.items()}
    return predictions, details


def _aggregate_evaluations(
    room_rows: list[dict[str, Any]], target_seasons: tuple[int, ...]
) -> list[dict[str, Any]]:
    groups: list[tuple[str, int | str, int, str, list[dict[str, Any]]]] = []
    for window in WINDOWS:
        groups.append((
            "all", "", window, "ALL",
            [row for row in room_rows if int(row["window_end"]) == window],
        ))
        for season in target_seasons:
            groups.append((
                "season", season, window, "ALL",
                [
                    row for row in room_rows
                    if int(row["window_end"]) == window
                    and int(row["target_season"]) == season
                ],
            ))
        for segment, precision in (
            ("timestamped_depth", "timestamp_before_first_regular_season_gameday"),
            ("week_labeled_depth", "week_1_label_only_no_source_timestamp"),
        ):
            selected = [
                row for row in room_rows
                if int(row["window_end"]) == window
                and row["depth_temporal_precision"] == precision
            ]
            if selected:
                groups.append((segment, "", window, "ALL", selected))
        for resource in RESOURCE_SPECS:
            groups.append((
                "resource", "", window, resource,
                [
                    row for row in room_rows
                    if int(row["window_end"]) == window
                    and row["resource"] == resource
                ],
            ))

    output: list[dict[str, Any]] = []
    for segment, season, window, resource, rows in groups:
        model_values = {
            model: [row for row in rows if row["model"] == model]
            for model in MODELS
        }
        if any(not values for values in model_values.values()):
            continue
        means = {
            model: sum(float(row["total_variation_distance"]) for row in values)
            / len(values)
            for model, values in model_values.items()
        }
        for model, values in model_values.items():
            tvs = [float(row["total_variation_distance"]) for row in values]
            output.append({
                "segment": segment,
                "target_season": season,
                "window_end": window,
                "resource": resource,
                "model": model,
                "room_count": len(values),
                "mean_total_variation": f"{means[model]:.6f}",
                "median_total_variation": f"{_percentile(tvs, 0.5):.6f}",
                "top_role_accuracy": f"{sum(row['top_role_hit'] == 'true' for row in values) / len(values):.6f}",
                "mean_forecast_unallocated_share": f"{sum(float(row['forecast_unallocated_share']) for row in values) / len(values):.6f}",
                "mean_opening_candidate_coverage": f"{sum(float(row['opening_candidate_actual_share']) for row in values) / len(values):.6f}",
                "mean_player_mae": f"{sum(float(row['player_mae']) for row in values) / len(values):.6f}",
                "delta_tv_vs_depth_only": f"{means[model] - means['depth_only']:.6f}",
                "delta_tv_vs_prior_share_only": f"{means[model] - means['prior_share_only']:.6f}",
            })
    return output


def _paired_comparisons(
    room_rows: list[dict[str, Any]], *, samples: int, seed: int
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    output: list[dict[str, Any]] = []
    for window in WINDOWS:
        window_rows = [row for row in room_rows if int(row["window_end"]) == window]
        for resource_scope in ("ALL", *RESOURCE_SPECS):
            rows = [
                row for row in window_rows
                if resource_scope == "ALL" or row["resource"] == resource_scope
            ]
            lookup = {
                (row["target_season"], row["team"], row["resource"], row["model"]): row
                for row in rows
            }
            for challenger, baseline in (
                ("blend_v0", "depth_only"),
                ("blend_v0", "prior_share_only"),
                ("prior_share_only", "depth_only"),
            ):
                deltas: list[tuple[tuple[str, str], float]] = []
                for key, row in lookup.items():
                    season, team, resource, model = key
                    if model != challenger:
                        continue
                    base = lookup[(season, team, resource, baseline)]
                    deltas.append((
                        (str(season), str(team)),
                        float(row["total_variation_distance"])
                        - float(base["total_variation_distance"]),
                    ))
                clusters: dict[tuple[str, str], list[float]] = defaultdict(list)
                for cluster, delta in deltas:
                    clusters[cluster].append(delta)
                cluster_means = [sum(values) / len(values) for values in clusters.values()]
                if not cluster_means:
                    continue
                bootstrap = [
                    sum(rng.choice(cluster_means) for _ in cluster_means) / len(cluster_means)
                    for _ in range(samples)
                ]
                mean_delta = sum(delta for _, delta in deltas) / len(deltas)
                low = _percentile(bootstrap, 0.05)
                high = _percentile(bootstrap, 0.95)
                if high < 0:
                    interpretation = "challenger_lower_error_ci_excludes_zero"
                elif low > 0:
                    interpretation = "challenger_higher_error_ci_excludes_zero"
                else:
                    interpretation = "difference_uncertain_ci_includes_zero"
                output.append({
                    "window_end": window,
                    "resource": resource_scope,
                    "challenger": challenger,
                    "baseline": baseline,
                    "room_count": len(deltas),
                    "cluster_count": len(cluster_means),
                    "mean_tv_delta": f"{mean_delta:.6f}",
                    "delta_ci90_low": f"{low:.6f}",
                    "delta_ci90_high": f"{high:.6f}",
                    "paired_room_win_rate": f"{sum(delta < 0 for _, delta in deltas) / len(deltas):.6f}",
                    "interpretation": interpretation,
                })
    return output


def build_role_backtest(
    player_history: str | Path,
    *,
    target_seasons: Iterable[int] | None = None,
    history_lookback: int = 3,
    bootstrap_samples: int = 2000,
    random_seed: int = 20260902,
) -> RoleBacktestResult:
    """Evaluate frozen role shares conditional on actual weekly active status."""

    if (
        isinstance(history_lookback, bool) or not isinstance(history_lookback, int)
        or not 1 <= history_lookback <= 10
    ):
        raise ValueError("history_lookback must be an integer from 1 to 10")
    if (
        isinstance(bootstrap_samples, bool) or not isinstance(bootstrap_samples, int)
        or not 100 <= bootstrap_samples <= 100_000
    ):
        raise ValueError("bootstrap_samples must be an integer from 100 to 100000")
    if isinstance(random_seed, bool) or not isinstance(random_seed, int):
        raise ValueError("random_seed must be an integer")

    history_root = Path(player_history)
    roster_path = _resolve(history_root, "weekly_rosters.csv")
    depth_path = _resolve(history_root, "opening_depth.csv")
    opportunity_path = _resolve(history_root, "weekly_opportunities.csv")
    roster_raw, roster_rows = _read_csv(roster_path, {
        "season", "week", "team", "position", "gsis_id", "player_name",
        "status", "status_description",
    })
    depth_raw, depth_rows = _read_csv(depth_path, {
        "season", "team", "position", "gsis_id", "player_name",
        "depth_position", "depth_rank", "temporal_precision",
    })
    opportunity_raw, opportunity_rows = _read_csv(opportunity_path, {
        "season", "week", "team", "position", "gsis_id", "player_name",
        "dropbacks", "carries", "targets",
    })

    available_targets = tuple(sorted({_integer(row["season"], "depth season") for row in depth_rows}))
    targets = tuple(sorted(set(target_seasons))) if target_seasons is not None else available_targets
    if not targets or any(isinstance(value, bool) or not isinstance(value, int) for value in targets):
        raise ValueError("target_seasons must contain integers")
    if not set(targets).issubset(available_targets):
        raise RoleBacktestDataError(
            f"target seasons {targets} not covered by opening depth {available_targets}"
        )
    opportunity_seasons = {_integer(row["season"], "opportunity season") for row in opportunity_rows}
    required_history = {
        season for target in targets for season in range(target - history_lookback, target)
    }
    missing_history = required_history - opportunity_seasons
    if missing_history or not set(targets).issubset(opportunity_seasons):
        raise RoleBacktestDataError(
            f"weekly opportunities lack target/history seasons {sorted(missing_history | (set(targets) - opportunity_seasons))}"
        )

    rooms: dict[tuple[int, str, str], dict[str, Mapping[str, str]]] = defaultdict(dict)
    target_active: dict[tuple[int, int, str], set[str]] = defaultdict(set)
    for row in roster_rows:
        season = _integer(row["season"], "roster season")
        week = _integer(row["week"], "roster week")
        if (
            season in targets and 1 <= week <= 18 and row["status"] == "ACT"
            and row["gsis_id"]
        ):
            target_active[(season, week, row["team"])].add(row["gsis_id"])
        if (
            season in targets and week == 1 and row["status"] in {"ACT", "INA"}
            and row["position"] in {"QB", "RB", "WR", "TE"} and row["gsis_id"]
        ):
            key = season, row["team"], row["position"]
            rooms[key][row["gsis_id"]] = row
    if not rooms:
        raise RoleBacktestDataError("no target-season Week 1 ACT/INA candidate rooms")

    depth: dict[tuple[int, str, str, str], Mapping[str, str]] = {}
    precision_by_team: dict[tuple[int, str], set[str]] = defaultdict(set)
    for row in depth_rows:
        season = _integer(row["season"], "depth season")
        if season not in targets or row["position"] not in {"QB", "RB", "WR", "TE"}:
            continue
        precision_by_team[(season, row["team"])].add(row["temporal_precision"])
        key = season, row["team"], row["position"], row["gsis_id"]
        old = depth.get(key)
        if old is None or (_optional_rank(row["depth_rank"]) or 999) < (
            _optional_rank(old["depth_rank"]) or 999
        ):
            depth[key] = row
    for key, values in precision_by_team.items():
        if len(values) != 1:
            raise RoleBacktestDataError(f"mixed depth temporal precision for {key}")

    history_players, team_totals = historical_opportunity_groups(opportunity_rows)
    actual: dict[tuple[int, int, str, str, str], dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    weekly_actual: dict[tuple[int, int, str, str, str], dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    actual_names: dict[str, str] = {}
    for row in opportunity_rows:
        season = _integer(row["season"], "opportunity season")
        week = _integer(row["week"], "opportunity week")
        if season not in targets or not 1 <= week <= 18:
            continue
        actual_names[row["gsis_id"]] = row["player_name"]
        for resource, (position, field) in RESOURCE_SPECS.items():
            if row["position"] != position:
                continue
            value = _number(row[field], f"{season} {resource} actual")
            weekly_actual[(season, week, row["team"], position, resource)][row["gsis_id"]] += value
            for window in WINDOWS:
                if week <= window:
                    actual[(season, window, row["team"], position, resource)][row["gsis_id"]] += value

    prediction_rows: list[dict[str, Any]] = []
    room_rows: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    for (season, team, position), candidate_lookup in sorted(rooms.items()):
        precision_values = precision_by_team.get((season, team), set())
        precision = next(iter(precision_values)) if precision_values else "no_depth_rows"
        candidates = list(candidate_lookup.values())
        for resource, (resource_position, field) in RESOURCE_SPECS.items():
            if resource_position != position:
                continue
            predictions, details = candidate_role_predictions(
                candidates,
                target_season=season,
                team=team,
                position=position,
                resource=resource,
                field=field,
                lookback=history_lookback,
                depth=depth,
                players=history_players,
                team_totals=team_totals,
            )
            missing_depth = sum(
                details[player_id]["depth_rank"] is None for player_id in candidate_lookup
            )
            if missing_depth:
                review.append({
                    "target_season": season, "team": team, "position": position,
                    "resource": resource, "issue": "opening_candidate_missing_depth",
                    "details": f"{missing_depth} of {len(candidates)} candidates use the explicit fallback weight",
                })
            for window in WINDOWS:
                actual_values = actual.get((season, window, team, position, resource), {})
                total_actual = sum(actual_values.values())
                if total_actual <= 0:
                    review.append({
                        "target_season": season, "team": team, "position": position,
                        "resource": resource, "issue": "zero_actual_opportunity_pool",
                        "details": f"no positive opportunities through Week {window}; room omitted",
                    })
                    continue
                actual_shares = {
                    player_id: value / total_actual for player_id, value in actual_values.items()
                }
                coverage = sum(actual_shares.get(player_id, 0.0) for player_id in candidate_lookup)
                actual_top = min(
                    actual_shares,
                    key=lambda player_id: (-actual_shares[player_id], player_id),
                )
                for model in MODELS:
                    forecast_opportunities: dict[str, float] = defaultdict(float)
                    for week in range(1, window + 1):
                        weekly_values = weekly_actual.get(
                            (season, week, team, position, resource), {}
                        )
                        weekly_pool = sum(weekly_values.values())
                        if weekly_pool <= 0:
                            continue
                        active_ids = target_active.get((season, week, team), set())
                        active_weights = {
                            player_id: weight
                            for player_id, weight in predictions[model].items()
                            if player_id in active_ids
                        }
                        active_weight_total = sum(active_weights.values())
                        if active_weight_total <= 0:
                            forecast_opportunities[UNALLOCATED_ID] += weekly_pool
                            continue
                        for player_id, weight in active_weights.items():
                            forecast_opportunities[player_id] += (
                                weekly_pool * weight / active_weight_total
                            )
                    forecast = {
                        player_id: value / total_actual
                        for player_id, value in forecast_opportunities.items()
                    }
                    forecast_sum = sum(forecast.values())
                    if abs(forecast_sum - 1.0) > 1e-9:
                        raise RoleBacktestDataError(
                            f"{season} {team} {resource} {model} does not reconcile"
                        )
                    union = sorted(
                        set(candidate_lookup) | set(actual_shares) | set(forecast)
                    )
                    predicted_top = min(
                        forecast, key=lambda player_id: (-forecast[player_id], player_id)
                    )
                    absolute = [
                        abs(forecast.get(player_id, 0.0) - actual_shares.get(player_id, 0.0))
                        for player_id in union
                    ]
                    tv = 0.5 * sum(absolute)
                    mae = sum(absolute) / len(absolute)
                    room_rows.append({
                        "target_season": season, "window_end": window,
                        "team": team, "position": position, "resource": resource,
                        "model": model, "opening_candidate_count": len(candidates),
                        "actual_player_count": len(actual_shares),
                        "prediction_share_sum": f"{forecast_sum:.12f}",
                        "forecast_unallocated_share": f"{forecast.get(UNALLOCATED_ID, 0.0):.9f}",
                        "opening_candidate_actual_share": f"{coverage:.9f}",
                        "total_variation_distance": f"{tv:.9f}",
                        "player_mae": f"{mae:.9f}",
                        "predicted_top_gsis_id": predicted_top,
                        "actual_top_gsis_id": actual_top,
                        "top_role_hit": str(predicted_top == actual_top).lower(),
                        "depth_temporal_precision": precision,
                    })
                    for player_id in union:
                        detail = details.get(player_id)
                        history = detail["history"] if detail else {}
                        prediction = forecast.get(player_id, 0.0)
                        observed = actual_shares.get(player_id, 0.0)
                        candidate = candidate_lookup.get(player_id)
                        if player_id == UNALLOCATED_ID:
                            row_type = "unallocated"
                        elif candidate is not None:
                            row_type = "opening_candidate"
                        else:
                            row_type = "later_entrant"
                        prediction_rows.append({
                            "target_season": season, "window_end": window,
                            "team": team, "position": position, "resource": resource,
                            "model": model, "gsis_id": player_id,
                            "player_name": (
                                "Unallocated opening-roster mass"
                                if player_id == UNALLOCATED_ID
                                else candidate["player_name"] if candidate
                                else actual_names.get(player_id, "")
                            ),
                            "row_type": row_type,
                            "opening_candidate": str(candidate is not None).lower(),
                            "depth_rank": detail["depth_rank"] if detail and detail["depth_rank"] is not None else "",
                            "historical_share": f"{history.get('share', 0.0):.9f}" if detail else "",
                            "historical_weighted_games": f"{history.get('weighted_games', 0.0):.6f}" if detail else "",
                            "predicted_share": f"{prediction:.9f}",
                            "actual_share": f"{observed:.9f}",
                            "actual_opportunities": f"{actual_values.get(player_id, 0.0):.6f}",
                            "absolute_error": f"{abs(prediction - observed):.9f}",
                            "depth_temporal_precision": precision,
                        })

    if not room_rows:
        raise RoleBacktestDataError("role backtest produced no scored rooms")
    evaluation = _aggregate_evaluations(room_rows, targets)
    comparisons = _paired_comparisons(
        room_rows, samples=bootstrap_samples, seed=random_seed
    )
    all_rows = [row for row in evaluation if row["segment"] == "all"]
    aggregate_means = {
        model: sum(
            float(row["mean_total_variation"])
            for row in all_rows if row["model"] == model
        ) / len(WINDOWS)
        for model in MODELS
    }
    best_model = min(aggregate_means, key=aggregate_means.get)
    blend_comparisons = [
        row for row in comparisons
        if row["resource"] == "ALL" and row["challenger"] == "blend_v0"
    ]
    blend_clear_wins = [
        row for row in blend_comparisons if float(row["delta_ci90_high"]) < 0
    ]
    resource_recommendations: dict[str, Any] = {}
    for resource in RESOURCE_SPECS:
        rows = [
            row for row in evaluation
            if row["segment"] == "resource" and row["resource"] == resource
        ]
        means = {
            model: sum(
                float(row["mean_total_variation"])
                for row in rows if row["model"] == model
            ) / len(WINDOWS)
            for model in MODELS
        }
        resource_comparisons = [
            row for row in comparisons
            if row["resource"] == resource and row["challenger"] == "blend_v0"
        ]
        versus_depth = [
            row for row in resource_comparisons if row["baseline"] == "depth_only"
        ]
        versus_prior = [
            row for row in resource_comparisons if row["baseline"] == "prior_share_only"
        ]
        lowest = min(means, key=means.get)
        resource_recommendations[resource] = {
            "mean_total_variation_by_model": {
                model: round(value, 6) for model, value in means.items()
            },
            "lowest_error_model": lowest,
            "blend_clear_wins_vs_depth": sum(
                float(row["delta_ci90_high"]) < 0 for row in versus_depth
            ),
            "blend_clear_losses_vs_depth": sum(
                float(row["delta_ci90_low"]) > 0 for row in versus_depth
            ),
            "blend_clear_wins_vs_prior_share": sum(
                float(row["delta_ci90_high"]) < 0 for row in versus_prior
            ),
            "blend_clear_losses_vs_prior_share": sum(
                float(row["delta_ci90_low"]) > 0 for row in versus_prior
            ),
            "recommended_frozen_model": lowest,
            "selection_caveat": "chosen retrospectively; freeze before any new-season validation",
        }
    universal_blend = (
        best_model == "blend_v0"
        and len(blend_clear_wins) == len(blend_comparisons)
        and all(
            item["lowest_error_model"] == "blend_v0"
            and item["blend_clear_losses_vs_depth"] == 0
            and item["blend_clear_losses_vs_prior_share"] == 0
            for item in resource_recommendations.values()
        )
    )
    recommendation = {
        "selection_metric": "mean availability-conditioned room total-variation distance across Weeks 1-4, 1-8, and 1-18",
        "mean_total_variation_by_model": {
            model: round(value, 6) for model, value in aggregate_means.items()
        },
        "lowest_error_model": best_model,
        "blend_clear_win_comparisons": len(blend_clear_wins),
        "blend_comparison_count": len(blend_comparisons),
        "aggregate_blend_supported": (
            best_model == "blend_v0"
            and len(blend_clear_wins) == len(blend_comparisons)
        ),
        "adopt_blend_v0_as_universal_model": universal_blend,
        "resource_recommendations": resource_recommendations,
        "decision_rule": "do not use one universal blend when a resource has a different lowest-error model or a clear held-out loss; resource choices are retrospective and must be frozen before new-season validation",
        "validation_status": "retrospective_oracle_availability_frozen_parameters_not_prospective_validation",
    }
    return RoleBacktestResult(
        history_path=history_root,
        input_hashes={
            "weekly_rosters.csv": hashlib.sha256(roster_raw).hexdigest(),
            "opening_depth.csv": hashlib.sha256(depth_raw).hexdigest(),
            "weekly_opportunities.csv": hashlib.sha256(opportunity_raw).hexdigest(),
        },
        target_seasons=targets,
        history_lookback=history_lookback,
        bootstrap_samples=bootstrap_samples,
        random_seed=random_seed,
        prediction_rows=tuple(sorted(prediction_rows, key=lambda row: (
            row["target_season"], row["window_end"], row["team"], row["resource"],
            row["model"], -float(row["predicted_share"]), row["gsis_id"],
        ))),
        room_rows=tuple(sorted(room_rows, key=lambda row: (
            row["target_season"], row["window_end"], row["team"], row["resource"], row["model"],
        ))),
        evaluation_rows=tuple(sorted(evaluation, key=lambda row: (
            row["segment"], str(row["target_season"]), row["window_end"], row["model"],
        ))),
        comparison_rows=tuple(comparisons),
        source_review=tuple(sorted(review, key=lambda row: (
            row["target_season"], row["team"], row["resource"], row["issue"],
        ))),
        recommendation=recommendation,
    )


def _csv_bytes(fields: tuple[str, ...], rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def write_role_backtest_snapshot(result: RoleBacktestResult, root: str | Path) -> Path:
    """Atomically publish predictions, evaluations, comparisons, and hashes."""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    season_label = "-".join(str(value) for value in result.target_seasons)
    parent = Path(root) / "role_backtest" / season_label
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"role-backtest snapshot exists: {destination}")
    artifacts = {
        "player_predictions.csv": _csv_bytes(PREDICTION_FIELDS, result.prediction_rows),
        "room_evaluation.csv": _csv_bytes(ROOM_FIELDS, result.room_rows),
        "model_evaluation.csv": _csv_bytes(EVALUATION_FIELDS, result.evaluation_rows),
        "paired_comparisons.csv": _csv_bytes(COMPARISON_FIELDS, result.comparison_rows),
        "source_review.csv": _csv_bytes(REVIEW_FIELDS, result.source_review),
    }
    fields = {
        "player_predictions.csv": PREDICTION_FIELDS,
        "room_evaluation.csv": ROOM_FIELDS,
        "model_evaluation.csv": EVALUATION_FIELDS,
        "paired_comparisons.csv": COMPARISON_FIELDS,
        "source_review.csv": REVIEW_FIELDS,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "target_seasons": list(result.target_seasons),
        "windows": list(WINDOWS),
        "models": list(MODELS),
        "methodology": {
            "candidate_universe": "target-season Week 1 ACT/INA roster rows; later entrants receive a zero forecast and remain in scoring",
            "time_boundary": "history is restricted to the configured number of seasons strictly before each target season",
            "availability_conditioning": "actual weekly ACT status is supplied only as an evaluation oracle; frozen base weights are renormalized among active opening candidates before that week's observed team pool is allocated",
            "unallocated_handling": "when no opening candidate is ACT in a week with a positive team pool, forecast mass is assigned to an explicit __UNALLOCATED__ row and scored as error",
            "depth_only": "normalized opening depth-rank weights",
            "prior_share_only": "normalized recency- and prior-team-weighted historical opportunity share; depth fallback only when a room has no history",
            "blend_v0": "the frozen current role formula: depth plus reliability-discounted historical share and resource-specific history weights",
            "outcome": "availability-conditioned player opportunity share through Weeks 1-4, 1-8, and 1-18",
            "primary_error": "room total-variation distance; zero is perfect and one is disjoint",
            "uncertainty": "paired 90% bootstrap intervals resample team-season clusters",
            "temporal_caveat": "2023-2024 depth has only a Week 1 label; 2025 depth uses the last timestamp strictly before first gameday",
            "validation_caveat": "retrospective frozen-parameter evaluation with oracle availability, not a deployable forecast or prospective validation",
        },
        "parameters": {
            "history_lookback": result.history_lookback,
            "history_recency_factor": 0.65,
            "prior_team_transfer_factor": 0.70,
            "transferred_role_reliability_multiplier": TRANSFER_RELIABILITY_MULTIPLIER,
            "resource_history_weight": FROZEN_RESOURCE_HISTORY_WEIGHT,
            "depth_weights": {key: list(value) for key, value in DEPTH_WEIGHTS.items()},
            "bootstrap_samples": result.bootstrap_samples,
            "random_seed": result.random_seed,
        },
        "inputs": {
            "player_history": str(result.history_path),
            "sha256": dict(result.input_hashes),
        },
        "quality": {
            "prediction_rows": len(result.prediction_rows),
            "room_rows": len(result.room_rows),
            "evaluation_rows": len(result.evaluation_rows),
            "comparison_rows": len(result.comparison_rows),
            "source_review_rows": len(result.source_review),
            "maximum_forecast_unallocated_share": max(
                float(row["forecast_unallocated_share"])
                for row in result.room_rows
            ),
            "maximum_prediction_reconciliation_error": max(
                abs(float(row["prediction_share_sum"]) - 1.0)
                for row in result.room_rows
            ),
        },
        "recommendation": dict(result.recommendation),
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
