"""Time-correct tests of player high-value opportunity persistence.

The benchmark asks a narrow question: after current depth and ordinary carry or
target role are known, does a player's prior high-value rate improve the allocation
of future high-value events?  Actual weekly active status and team event volume are
evaluation-only oracles, matching the separation used by the role backtest.
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

from .player_roles import TRANSFER_RELIABILITY_MULTIPLIER
from .role_backtest import (
    candidate_role_predictions,
    historical_opportunity_groups,
)


SCHEMA_VERSION = "1.0.0"
MODEL_VERSION = "high-value-role-backtest-v0.2.0"
WINDOWS = (4, 8, 18)
BASE_MODEL = "base_role"
PRIMARY_MODEL = "rate_adjusted_p24"
MODEL_PRIORS: Mapping[str, float | None] = {
    BASE_MODEL: None,
    "rate_adjusted_p12": 12.0,
    PRIMARY_MODEL: 24.0,
    "rate_adjusted_p48": 48.0,
}
UNALLOCATED_ID = "__UNALLOCATED__"
RECENCY_FACTOR = 0.65
PRIOR_TEAM_FACTOR = 0.70
RATE_MULTIPLIER_LOW = 0.25
RATE_MULTIPLIER_HIGH = 4.0
MIN_PROMOTION_EVENTS = 500
MIN_PROMOTION_ROOMS = 80


@dataclass(frozen=True)
class HighValueMetric:
    position: str
    base_resource: str
    high_value_field: str
    base_field: str
    requires_read_source: bool = False


METRICS: Mapping[str, HighValueMetric] = {
    "QB_RED_ZONE_DESIGNED_CARRIES": HighValueMetric(
        "QB", "QB_RUSH_OPPORTUNITIES", "designed_qb_red_zone_carries", "carries"
    ),
    "QB_INSIDE_10_DESIGNED_CARRIES": HighValueMetric(
        "QB", "QB_RUSH_OPPORTUNITIES", "designed_qb_inside_10_carries", "carries"
    ),
    "QB_INSIDE_5_DESIGNED_CARRIES": HighValueMetric(
        "QB", "QB_RUSH_OPPORTUNITIES", "designed_qb_inside_5_carries", "carries"
    ),
    "RB_INSIDE_5_CARRIES": HighValueMetric(
        "RB", "RB_CARRIES", "inside_5_carries", "carries"
    ),
    "RB_INSIDE_10_CARRIES": HighValueMetric(
        "RB", "RB_CARRIES", "inside_10_carries", "carries"
    ),
    "RB_SHORT_YARDAGE_CARRIES": HighValueMetric(
        "RB", "RB_CARRIES", "short_yardage_carries", "carries"
    ),
    "RB_TWO_MINUTE_TARGETS": HighValueMetric(
        "RB", "RB_TARGETS", "two_minute_targets", "targets"
    ),
    "RB_FIRST_READ_TARGETS": HighValueMetric(
        "RB", "RB_TARGETS", "first_read_targets", "targets", True
    ),
    "WR_FIRST_READ_TARGETS": HighValueMetric(
        "WR", "WR_TARGETS", "first_read_targets", "targets", True
    ),
    "WR_RED_ZONE_TARGETS": HighValueMetric(
        "WR", "WR_TARGETS", "red_zone_targets", "targets"
    ),
    "WR_END_ZONE_TARGETS": HighValueMetric(
        "WR", "WR_TARGETS", "end_zone_targets", "targets"
    ),
    "WR_DEEP_TARGETS": HighValueMetric(
        "WR", "WR_TARGETS", "deep_targets", "targets"
    ),
    "WR_TWO_MINUTE_TARGETS": HighValueMetric(
        "WR", "WR_TARGETS", "two_minute_targets", "targets"
    ),
    "TE_FIRST_READ_TARGETS": HighValueMetric(
        "TE", "TE_TARGETS", "first_read_targets", "targets", True
    ),
    "TE_RED_ZONE_TARGETS": HighValueMetric(
        "TE", "TE_TARGETS", "red_zone_targets", "targets"
    ),
    "TE_END_ZONE_TARGETS": HighValueMetric(
        "TE", "TE_TARGETS", "end_zone_targets", "targets"
    ),
    "TE_DEEP_TARGETS": HighValueMetric(
        "TE", "TE_TARGETS", "deep_targets", "targets"
    ),
    "TE_TWO_MINUTE_TARGETS": HighValueMetric(
        "TE", "TE_TARGETS", "two_minute_targets", "targets"
    ),
}

PREDICTION_FIELDS = (
    "target_season", "window_end", "team", "position", "metric",
    "base_resource", "model", "prior_opportunities", "gsis_id",
    "player_name", "row_type", "opening_candidate", "depth_rank",
    "base_role_share", "historical_high_value_events",
    "historical_base_opportunities", "historical_team_high_value_rate",
    "rate_multiplier", "predicted_share", "actual_share", "actual_events",
    "absolute_error", "depth_temporal_precision",
)
ROOM_FIELDS = (
    "target_season", "window_end", "team", "position", "metric",
    "base_resource", "model", "prior_opportunities",
    "opening_candidate_count", "actual_player_count", "actual_event_count",
    "prediction_share_sum", "forecast_unallocated_share",
    "opening_candidate_actual_share", "total_variation_distance",
    "player_mae", "predicted_top_gsis_id", "actual_top_gsis_id",
    "top_role_hit", "depth_temporal_precision",
)
EVALUATION_FIELDS = (
    "segment", "scope", "window_end", "model", "room_count",
    "actual_event_count", "mean_total_variation", "median_total_variation",
    "top_role_accuracy", "mean_forecast_unallocated_share",
    "mean_opening_candidate_coverage", "mean_player_mae",
    "delta_tv_vs_base_role",
)
COMPARISON_FIELDS = (
    "segment", "scope", "window_end", "challenger", "baseline",
    "room_count", "cluster_count", "mean_tv_delta", "delta_ci90_low",
    "delta_ci90_high", "paired_room_win_rate", "interpretation",
)
REVIEW_FIELDS = (
    "target_season", "window_end", "team", "position", "metric", "issue",
    "details",
)


class HighValueBacktestDataError(ValueError):
    """Raised when inputs cannot support a time-correct high-value test."""


@dataclass(frozen=True)
class HighValueBacktestResult:
    player_history_path: Path
    high_value_history_path: Path
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


def _read_manifest(path: Path) -> tuple[bytes, Mapping[str, Any]]:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise HighValueBacktestDataError(f"missing input manifest: {manifest_path}")
    raw = manifest_path.read_bytes()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HighValueBacktestDataError(
            f"input manifest is not valid JSON: {manifest_path}"
        ) from error
    if not isinstance(value, dict):
        raise HighValueBacktestDataError(f"input manifest is not an object: {manifest_path}")
    return raw, value


def _verified_csv(
    root: Path,
    manifest: Mapping[str, Any],
    filename: str,
    required: set[str],
    *,
    nested_normalized: bool,
) -> tuple[bytes, list[dict[str, str]]]:
    artifacts = manifest.get("artifacts") or {}
    if nested_normalized:
        artifacts = artifacts.get("normalized") or {}
    meta = artifacts.get(filename)
    if not isinstance(meta, dict) or not meta.get("sha256"):
        raise HighValueBacktestDataError(f"manifest does not describe {filename}")
    path = root / filename
    if not path.is_file():
        raise HighValueBacktestDataError(f"input does not exist: {path}")
    raw = path.read_bytes()
    actual_hash = hashlib.sha256(raw).hexdigest()
    if actual_hash != meta["sha256"]:
        raise HighValueBacktestDataError(
            f"input hash mismatch for {path}: expected {meta['sha256']}, got {actual_hash}"
        )
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        fields = set(reader.fieldnames or ())
        rows = list(reader)
    except UnicodeDecodeError as error:
        raise HighValueBacktestDataError(f"input is not UTF-8 CSV: {path}") from error
    missing = required - fields
    if missing or not rows:
        raise HighValueBacktestDataError(
            f"{path} is empty or missing fields {sorted(missing)}"
        )
    return raw, rows


def _number(value: Any, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise HighValueBacktestDataError(f"{context} must be numeric") from error
    if not math.isfinite(result) or result < 0:
        raise HighValueBacktestDataError(f"{context} must be finite and nonnegative")
    return result


def _integer(value: Any, context: str) -> int:
    result = _number(value, context)
    if not result.is_integer():
        raise HighValueBacktestDataError(f"{context} must be an integer")
    return int(result)


def _optional_rank(value: Any) -> int | None:
    if value is None or not str(value).strip():
        return None
    rank = _integer(value, "depth rank")
    return rank if rank >= 1 else None


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        raise HighValueBacktestDataError("cannot summarize an empty sample")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def high_value_groups(
    rows: Iterable[Mapping[str, str]],
) -> tuple[
    dict[tuple[int, str, str, str, str], dict[str, float]],
    dict[tuple[int, str, str, str], dict[str, float]],
    dict[tuple[int, int, str, str, str], dict[str, float]],
    dict[str, str],
]:
    players: dict[tuple[int, str, str, str, str], dict[str, float]] = defaultdict(
        lambda: {"high_value": 0.0, "base": 0.0}
    )
    teams: dict[tuple[int, str, str, str], dict[str, float]] = defaultdict(
        lambda: {"high_value": 0.0, "base": 0.0}
    )
    weekly: dict[tuple[int, int, str, str, str], dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    names: dict[str, str] = {}
    for row in rows:
        season = _integer(row["season"], "high-value season")
        week = _integer(row["week"], "high-value week")
        if not 1 <= week <= 18:
            continue
        position = row["position"]
        player_id = row["gsis_id"]
        team = row["team"]
        if not player_id or not team:
            continue
        names[player_id] = row["player_name"]
        for metric, spec in METRICS.items():
            if position != spec.position:
                continue
            value_text = row.get(spec.high_value_field, "")
            if value_text is None or not str(value_text).strip():
                continue
            value = _number(value_text, f"{season} {metric} high-value count")
            base = _number(row[spec.base_field], f"{season} {metric} base count")
            player = players[(season, team, position, player_id, metric)]
            player["high_value"] += value
            player["base"] += base
            team_row = teams[(season, team, position, metric)]
            team_row["high_value"] += value
            team_row["base"] += base
            if value > 0:
                weekly[(season, week, team, position, metric)][player_id] += value
    return players, teams, weekly, names


def rate_multipliers(
    player_id: str,
    *,
    target_season: int,
    current_team: str,
    position: str,
    metric: str,
    lookback: int,
    players: Mapping[tuple[int, str, str, str, str], Mapping[str, float]],
    teams: Mapping[tuple[int, str, str, str], Mapping[str, float]],
) -> tuple[dict[str, float], dict[str, Any]]:
    relevant = [
        (key, value)
        for key, value in players.items()
        if key[2] == position
        and key[3] == player_id
        and key[4] == metric
        and target_season - lookback <= key[0] < target_season
    ]
    player_high = 0.0
    player_base = 0.0
    team_high = 0.0
    team_base = 0.0
    for (season, team, _, _, _), values in relevant:
        weight = RECENCY_FACTOR ** ((target_season - 1) - season)
        weight *= 1.0 if team == current_team else PRIOR_TEAM_FACTOR
        player_high += weight * values["high_value"]
        player_base += weight * values["base"]
        team_values = teams[(season, team, position, metric)]
        team_high += weight * team_values["high_value"]
        team_base += weight * team_values["base"]
    observed_relevant = [
        (key, value) for key, value in relevant if value["base"] > 0
    ]
    latest_teams: set[str] = set()
    latest_season: int | None = None
    if observed_relevant:
        latest_season = max(key[0] for key, _ in observed_relevant)
        latest_teams = {
            key[1] for key, _ in observed_relevant if key[0] == latest_season
        }
    team_rate = team_high / team_base if team_base > 0 else 0.0
    multipliers = {BASE_MODEL: 1.0}
    for model, prior in MODEL_PRIORS.items():
        if model == BASE_MODEL:
            continue
        if player_base <= 0 or team_rate <= 0 or prior is None:
            multiplier = 1.0
        else:
            player_rate = (player_high + prior * team_rate) / (player_base + prior)
            multiplier = player_rate / team_rate
            if current_team not in latest_teams:
                multiplier = 1.0 + TRANSFER_RELIABILITY_MULTIPLIER * (
                    multiplier - 1.0
                )
            multiplier = min(
                RATE_MULTIPLIER_HIGH, max(RATE_MULTIPLIER_LOW, multiplier)
            )
        multipliers[model] = multiplier
    return multipliers, {
        "historical_high_value_events": player_high,
        "historical_base_opportunities": player_base,
        "historical_team_high_value_rate": team_rate,
        "historical_season_count": len({key[0] for key, _ in observed_relevant}),
        "historical_latest_season": latest_season,
        "same_team_latest": current_team in latest_teams,
    }


def _aggregate_evaluations(room_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[tuple[str, str, int, list[dict[str, Any]]]] = []
    positions = tuple(sorted({spec.position for spec in METRICS.values()}))
    for window in WINDOWS:
        groups.append((
            "all", "ALL", window,
            [row for row in room_rows if int(row["window_end"]) == window],
        ))
        for position in positions:
            groups.append((
                "position", position, window,
                [
                    row for row in room_rows
                    if int(row["window_end"]) == window
                    and row["position"] == position
                ],
            ))
        for metric in METRICS:
            groups.append((
                "metric", metric, window,
                [
                    row for row in room_rows
                    if int(row["window_end"]) == window
                    and row["metric"] == metric
                ],
            ))
    output: list[dict[str, Any]] = []
    for segment, scope, window, rows in groups:
        model_rows = {
            model: [row for row in rows if row["model"] == model]
            for model in MODEL_PRIORS
        }
        if any(not values for values in model_rows.values()):
            continue
        means = {
            model: sum(float(row["total_variation_distance"]) for row in values)
            / len(values)
            for model, values in model_rows.items()
        }
        for model, values in model_rows.items():
            tvs = [float(row["total_variation_distance"]) for row in values]
            output.append({
                "segment": segment,
                "scope": scope,
                "window_end": window,
                "model": model,
                "room_count": len(values),
                "actual_event_count": f"{sum(float(row['actual_event_count']) for row in values):.0f}",
                "mean_total_variation": f"{means[model]:.6f}",
                "median_total_variation": f"{_percentile(tvs, 0.5):.6f}",
                "top_role_accuracy": f"{sum(row['top_role_hit'] == 'true' for row in values) / len(values):.6f}",
                "mean_forecast_unallocated_share": f"{sum(float(row['forecast_unallocated_share']) for row in values) / len(values):.6f}",
                "mean_opening_candidate_coverage": f"{sum(float(row['opening_candidate_actual_share']) for row in values) / len(values):.6f}",
                "mean_player_mae": f"{sum(float(row['player_mae']) for row in values) / len(values):.6f}",
                "delta_tv_vs_base_role": f"{means[model] - means[BASE_MODEL]:.6f}",
            })
    return output


def paired_comparisons(
    room_rows: list[dict[str, Any]], *, samples: int, seed: int
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    scopes = [
        ("all", "ALL", lambda row: True),
        *[
            ("position", position, lambda row, value=position: row["position"] == value)
            for position in sorted({spec.position for spec in METRICS.values()})
        ],
        *[
            ("metric", metric, lambda row, value=metric: row["metric"] == value)
            for metric in METRICS
        ],
    ]
    for window in WINDOWS:
        for segment, scope, selector in scopes:
            rows = [
                row for row in room_rows
                if int(row["window_end"]) == window and selector(row)
            ]
            lookup = {
                (
                    row["target_season"], row["team"], row["metric"], row["model"]
                ): row
                for row in rows
            }
            for challenger in MODEL_PRIORS:
                if challenger == BASE_MODEL:
                    continue
                deltas: list[tuple[tuple[str, str], float]] = []
                for key, row in lookup.items():
                    season, team, metric, model = key
                    if model != challenger:
                        continue
                    baseline = lookup.get((season, team, metric, BASE_MODEL))
                    if baseline is None:
                        continue
                    deltas.append((
                        (str(season), team),
                        float(row["total_variation_distance"])
                        - float(baseline["total_variation_distance"]),
                    ))
                clusters: dict[tuple[str, str], list[float]] = defaultdict(list)
                for cluster, delta in deltas:
                    clusters[cluster].append(delta)
                cluster_means = [sum(values) / len(values) for values in clusters.values()]
                if not cluster_means:
                    continue
                seed_material = (
                    f"{seed}|{window}|{segment}|{scope}|{challenger}|{BASE_MODEL}"
                ).encode("utf-8")
                comparison_seed = int.from_bytes(
                    hashlib.sha256(seed_material).digest()[:8], "big"
                )
                rng = random.Random(comparison_seed)
                bootstrap = [
                    sum(rng.choice(cluster_means) for _ in cluster_means)
                    / len(cluster_means)
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
                    "segment": segment,
                    "scope": scope,
                    "window_end": window,
                    "challenger": challenger,
                    "baseline": BASE_MODEL,
                    "room_count": len(deltas),
                    "cluster_count": len(cluster_means),
                    "mean_tv_delta": f"{mean_delta:.6f}",
                    "delta_ci90_low": f"{low:.6f}",
                    "delta_ci90_high": f"{high:.6f}",
                    "paired_room_win_rate": f"{sum(delta < 0 for _, delta in deltas) / len(deltas):.6f}",
                    "interpretation": interpretation,
                })
    return output


def recommend_high_value_metrics(
    evaluations: list[dict[str, Any]], comparisons: list[dict[str, Any]]
) -> dict[str, Any]:
    recommendations: dict[str, Any] = {}
    supported: list[str] = []
    for metric in METRICS:
        rows = [
            row for row in evaluations
            if row["segment"] == "metric" and row["scope"] == metric
        ]
        windows = sorted({int(row["window_end"]) for row in rows})
        if not windows:
            continue
        by_model = {
            model: [row for row in rows if row["model"] == model]
            for model in MODEL_PRIORS
        }
        if any(len(values) != len(windows) for values in by_model.values()):
            continue
        means = {
            model: sum(float(row["mean_total_variation"]) for row in values)
            / len(values)
            for model, values in by_model.items()
        }
        primary_comparisons = [
            row for row in comparisons
            if row["segment"] == "metric"
            and row["scope"] == metric
            and row["challenger"] == PRIMARY_MODEL
        ]
        clear_wins = sum(
            float(row["delta_ci90_high"]) < 0 for row in primary_comparisons
        )
        clear_losses = sum(
            float(row["delta_ci90_low"]) > 0 for row in primary_comparisons
        )
        sensitivity_deltas = {
            model: means[model] - means[BASE_MODEL]
            for model in MODEL_PRIORS if model != BASE_MODEL
        }
        week_18_base = next(
            (
                row for row in by_model[BASE_MODEL]
                if int(row["window_end"]) == 18
            ),
            None,
        )
        events = int(float(week_18_base["actual_event_count"])) if week_18_base else 0
        rooms = int(week_18_base["room_count"]) if week_18_base else 0
        promote = (
            windows == list(WINDOWS)
            and events >= MIN_PROMOTION_EVENTS
            and rooms >= MIN_PROMOTION_ROOMS
            and clear_wins >= 2
            and clear_losses == 0
            and all(delta < 0 for delta in sensitivity_deltas.values())
        )
        if promote:
            supported.append(metric)
        recommendations[metric] = {
            "position": METRICS[metric].position,
            "base_resource": METRICS[metric].base_resource,
            "mean_total_variation_by_model": {
                model: round(value, 6) for model, value in means.items()
            },
            "primary_mean_delta_vs_base": round(
                means[PRIMARY_MODEL] - means[BASE_MODEL], 6
            ),
            "primary_clear_win_windows": clear_wins,
            "primary_clear_loss_windows": clear_losses,
            "sensitivity_mean_deltas_vs_base": {
                model: round(value, 6)
                for model, value in sensitivity_deltas.items()
            },
            "week_18_actual_events": events,
            "week_18_room_count": rooms,
            "promotion_gate_passed": promote,
            "recommended_action": (
                "freeze_rate_adjusted_p24_for_prospective_2026_test"
                if promote else "keep_base_role_and_retain_as_diagnostic"
            ),
        }
    return {
        "primary_model": PRIMARY_MODEL,
        "promotion_rule": (
            f"all three windows present; at least {MIN_PROMOTION_EVENTS} Week-18 events "
            f"across at least {MIN_PROMOTION_ROOMS} rooms; primary model has at least "
            "two clear 90% interval wins and no clear loss; p12/p24/p48 mean deltas "
            "are all below zero"
        ),
        "supported_metrics": supported,
        "diagnostic_only_metrics": [
            metric for metric in recommendations if metric not in supported
        ],
        "metrics": recommendations,
        "validation_status": (
            "retrospective_oracle_availability_and_volume_not_prospectively_validated"
        ),
        "routes_status": (
            "not tested: public participation route is only the primary receiver's "
            "route and cannot supply routes run per player"
        ),
        "first_read_status": (
            "tested as current nflreadr dictionary-defined read_thrown code 0, with "
            "2022 primary reads structurally unavailable; no first-read metric "
            "passed the promotion gate"
            if not any("FIRST_READ" in metric for metric in supported)
            else "one or more dictionary-defined first-read metrics passed the gate"
        ),
    }


def build_high_value_backtest(
    player_history: str | Path,
    high_value_history: str | Path,
    *,
    target_seasons: Iterable[int] | None = None,
    history_lookback: int = 3,
    bootstrap_samples: int = 2000,
    random_seed: int = 20260902,
) -> HighValueBacktestResult:
    """Evaluate fixed historical high-value rate adjustments against base role."""

    if (
        isinstance(history_lookback, bool)
        or not isinstance(history_lookback, int)
        or not 1 <= history_lookback <= 10
    ):
        raise ValueError("history_lookback must be an integer from 1 to 10")
    if (
        isinstance(bootstrap_samples, bool)
        or not isinstance(bootstrap_samples, int)
        or not 100 <= bootstrap_samples <= 100_000
    ):
        raise ValueError("bootstrap_samples must be an integer from 100 to 100000")
    if isinstance(random_seed, bool) or not isinstance(random_seed, int):
        raise ValueError("random_seed must be an integer")

    player_root = Path(player_history)
    high_root = Path(high_value_history)
    player_manifest_raw, player_manifest = _read_manifest(player_root)
    high_manifest_raw, high_manifest = _read_manifest(high_root)
    roster_raw, roster_rows = _verified_csv(
        player_root, player_manifest, "weekly_rosters.csv",
        {"season", "week", "team", "position", "gsis_id", "player_name", "status"},
        nested_normalized=True,
    )
    depth_raw, depth_rows = _verified_csv(
        player_root, player_manifest, "opening_depth.csv",
        {"season", "team", "position", "gsis_id", "depth_rank", "temporal_precision"},
        nested_normalized=True,
    )
    opportunity_raw, opportunity_rows = _verified_csv(
        player_root, player_manifest, "weekly_opportunities.csv",
        {"season", "week", "team", "position", "gsis_id", "player_name", "dropbacks", "carries", "targets"},
        nested_normalized=True,
    )
    required_high_fields = {
        "season", "week", "team", "position", "gsis_id", "player_name",
        "read_source_available", "primary_read_source_available", "targets", "carries",
        *(spec.high_value_field for spec in METRICS.values()),
    }
    high_raw, high_rows = _verified_csv(
        high_root, high_manifest, "player_week_high_value.csv",
        required_high_fields, nested_normalized=False,
    )
    coverage_raw, coverage_rows = _verified_csv(
        high_root, high_manifest, "coverage.csv",
        {"season", "ftn_available", "primary_read_available", "read_labeled_rate"},
        nested_normalized=False,
    )
    input_hashes = {
        "player_history_manifest.json": hashlib.sha256(player_manifest_raw).hexdigest(),
        "weekly_rosters.csv": hashlib.sha256(roster_raw).hexdigest(),
        "opening_depth.csv": hashlib.sha256(depth_raw).hexdigest(),
        "weekly_opportunities.csv": hashlib.sha256(opportunity_raw).hexdigest(),
        "high_value_history_manifest.json": hashlib.sha256(high_manifest_raw).hexdigest(),
        "player_week_high_value.csv": hashlib.sha256(high_raw).hexdigest(),
        "coverage.csv": hashlib.sha256(coverage_raw).hexdigest(),
    }

    available_depth_seasons = {
        _integer(row["season"], "depth season") for row in depth_rows
    }
    available_high_seasons = {
        _integer(row["season"], "high-value season") for row in high_rows
    }
    targets = (
        tuple(sorted(set(target_seasons)))
        if target_seasons is not None
        else tuple(sorted(available_depth_seasons & available_high_seasons))
    )
    if not targets or any(
        isinstance(value, bool) or not isinstance(value, int) for value in targets
    ):
        raise ValueError("target_seasons must contain integers")
    if not set(targets).issubset(available_depth_seasons & available_high_seasons):
        raise HighValueBacktestDataError(
            "target seasons must exist in opening depth and high-value history"
        )
    opportunity_seasons = {
        _integer(row["season"], "opportunity season") for row in opportunity_rows
    }
    required_opportunity_history = {
        season
        for target in targets
        for season in range(target - history_lookback, target)
    }
    if not (required_opportunity_history | set(targets)).issubset(opportunity_seasons):
        missing = (required_opportunity_history | set(targets)) - opportunity_seasons
        raise HighValueBacktestDataError(
            f"weekly opportunities lack required seasons {sorted(missing)}"
        )

    primary_read_available = {
        _integer(row["season"], "coverage season")
        for row in coverage_rows if row["primary_read_available"] == "true"
    }
    rooms: dict[tuple[int, str, str], dict[str, Mapping[str, str]]] = defaultdict(dict)
    target_active: dict[tuple[int, int, str], set[str]] = defaultdict(set)
    for row in roster_rows:
        season = _integer(row["season"], "roster season")
        week = _integer(row["week"], "roster week")
        if season in targets and 1 <= week <= 18 and row["status"] == "ACT":
            target_active[(season, week, row["team"])].add(row["gsis_id"])
        if (
            season in targets and week == 1 and row["status"] in {"ACT", "INA"}
            and row["position"] in {"QB", "RB", "WR", "TE"} and row["gsis_id"]
        ):
            rooms[(season, row["team"], row["position"])][row["gsis_id"]] = row
    if not rooms:
        raise HighValueBacktestDataError("no target-season opening candidate rooms")

    depth: dict[tuple[int, str, str, str], Mapping[str, str]] = {}
    precision_by_team: dict[tuple[int, str], set[str]] = defaultdict(set)
    for row in depth_rows:
        season = _integer(row["season"], "depth season")
        if season not in targets:
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
            raise HighValueBacktestDataError(f"mixed depth temporal precision for {key}")

    opportunity_players, opportunity_team_totals = historical_opportunity_groups(
        opportunity_rows
    )
    high_players, high_teams, weekly_actual, high_names = high_value_groups(high_rows)
    prediction_rows: list[dict[str, Any]] = []
    room_rows: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []

    for (season, team, position), candidate_lookup in sorted(rooms.items()):
        precision_values = precision_by_team.get((season, team), set())
        precision = next(iter(precision_values)) if precision_values else "no_depth_rows"
        candidates = list(candidate_lookup.values())
        for metric, spec in METRICS.items():
            if spec.position != position:
                continue
            if spec.requires_read_source and season not in primary_read_available:
                review.append({
                    "target_season": season, "window_end": "", "team": team,
                    "position": position, "metric": metric,
                    "issue": "target_read_source_unavailable",
                    "details": "metric omitted rather than treating missing reads as zero",
                })
                continue
            role_models, role_details = candidate_role_predictions(
                candidates,
                target_season=season,
                team=team,
                position=position,
                resource=spec.base_resource,
                field=spec.base_field,
                lookback=history_lookback,
                depth=depth,
                players=opportunity_players,
                team_totals=opportunity_team_totals,
            )
            base_role = (
                role_models["depth_only"] if position == "QB"
                else role_models["blend_v0"]
            )
            rate_details: dict[str, Mapping[str, Any]] = {}
            model_weights: dict[str, dict[str, float]] = {BASE_MODEL: dict(base_role)}
            raw_adjusted: dict[str, dict[str, float]] = {
                model: {} for model in MODEL_PRIORS if model != BASE_MODEL
            }
            for player_id in candidate_lookup:
                multipliers, detail = rate_multipliers(
                    player_id,
                    target_season=season,
                    current_team=team,
                    position=position,
                    metric=metric,
                    lookback=history_lookback,
                    players=high_players,
                    teams=high_teams,
                )
                rate_details[player_id] = {**detail, "multipliers": multipliers}
                for model in raw_adjusted:
                    raw_adjusted[model][player_id] = (
                        base_role[player_id] * multipliers[model]
                    )
            for model, values in raw_adjusted.items():
                total = sum(values.values())
                if total <= 0:
                    raise HighValueBacktestDataError(
                        f"{season} {team} {metric} {model} has no forecast mass"
                    )
                model_weights[model] = {
                    player_id: value / total for player_id, value in values.items()
                }

            for window in WINDOWS:
                actual_values: dict[str, float] = defaultdict(float)
                for week in range(1, window + 1):
                    for player_id, value in weekly_actual.get(
                        (season, week, team, position, metric), {}
                    ).items():
                        actual_values[player_id] += value
                total_actual = sum(actual_values.values())
                if total_actual <= 0:
                    review.append({
                        "target_season": season, "window_end": window,
                        "team": team, "position": position, "metric": metric,
                        "issue": "zero_actual_event_pool",
                        "details": "room omitted from this window",
                    })
                    continue
                actual_shares = {
                    player_id: value / total_actual
                    for player_id, value in actual_values.items()
                }
                coverage = sum(
                    actual_shares.get(player_id, 0.0) for player_id in candidate_lookup
                )
                actual_top = min(
                    actual_shares,
                    key=lambda player_id: (-actual_shares[player_id], player_id),
                )
                for model, weights in model_weights.items():
                    forecast_events: dict[str, float] = defaultdict(float)
                    for week in range(1, window + 1):
                        weekly_values = weekly_actual.get(
                            (season, week, team, position, metric), {}
                        )
                        weekly_pool = sum(weekly_values.values())
                        if weekly_pool <= 0:
                            continue
                        active_ids = target_active.get((season, week, team), set())
                        active_weights = {
                            player_id: value
                            for player_id, value in weights.items()
                            if player_id in active_ids
                        }
                        active_total = sum(active_weights.values())
                        if active_total <= 0:
                            forecast_events[UNALLOCATED_ID] += weekly_pool
                        else:
                            for player_id, value in active_weights.items():
                                forecast_events[player_id] += (
                                    weekly_pool * value / active_total
                                )
                    forecast = {
                        player_id: value / total_actual
                        for player_id, value in forecast_events.items()
                    }
                    forecast_sum = sum(forecast.values())
                    if abs(forecast_sum - 1.0) > 1e-9:
                        raise HighValueBacktestDataError(
                            f"{season} {team} {metric} {model} does not reconcile"
                        )
                    union = sorted(
                        set(candidate_lookup) | set(actual_shares) | set(forecast)
                    )
                    predicted_top = min(
                        forecast,
                        key=lambda player_id: (-forecast[player_id], player_id),
                    )
                    absolute = [
                        abs(
                            forecast.get(player_id, 0.0)
                            - actual_shares.get(player_id, 0.0)
                        )
                        for player_id in union
                    ]
                    tv = 0.5 * sum(absolute)
                    mae = sum(absolute) / len(absolute)
                    prior = MODEL_PRIORS[model]
                    room_rows.append({
                        "target_season": season, "window_end": window,
                        "team": team, "position": position, "metric": metric,
                        "base_resource": spec.base_resource, "model": model,
                        "prior_opportunities": "" if prior is None else f"{prior:.0f}",
                        "opening_candidate_count": len(candidates),
                        "actual_player_count": len(actual_shares),
                        "actual_event_count": f"{total_actual:.0f}",
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
                        candidate = candidate_lookup.get(player_id)
                        role_detail = role_details.get(player_id)
                        rate_detail = rate_details.get(player_id, {})
                        if player_id == UNALLOCATED_ID:
                            row_type = "unallocated"
                            player_name = "Unallocated opening-roster mass"
                        elif candidate is not None:
                            row_type = "opening_candidate"
                            player_name = candidate["player_name"]
                        else:
                            row_type = "later_entrant"
                            player_name = high_names.get(player_id, "")
                        multiplier = (
                            rate_detail.get("multipliers", {}).get(model, 1.0)
                            if rate_detail else 1.0
                        )
                        observed = actual_shares.get(player_id, 0.0)
                        prediction = forecast.get(player_id, 0.0)
                        prediction_rows.append({
                            "target_season": season, "window_end": window,
                            "team": team, "position": position, "metric": metric,
                            "base_resource": spec.base_resource, "model": model,
                            "prior_opportunities": "" if prior is None else f"{prior:.0f}",
                            "gsis_id": player_id, "player_name": player_name,
                            "row_type": row_type,
                            "opening_candidate": str(candidate is not None).lower(),
                            "depth_rank": (
                                role_detail["depth_rank"]
                                if role_detail and role_detail["depth_rank"] is not None
                                else ""
                            ),
                            "base_role_share": (
                                f"{base_role.get(player_id, 0.0):.9f}"
                                if candidate is not None else ""
                            ),
                            "historical_high_value_events": (
                                f"{rate_detail.get('historical_high_value_events', 0.0):.6f}"
                                if candidate is not None else ""
                            ),
                            "historical_base_opportunities": (
                                f"{rate_detail.get('historical_base_opportunities', 0.0):.6f}"
                                if candidate is not None else ""
                            ),
                            "historical_team_high_value_rate": (
                                f"{rate_detail.get('historical_team_high_value_rate', 0.0):.9f}"
                                if candidate is not None else ""
                            ),
                            "rate_multiplier": (
                                f"{multiplier:.9f}" if candidate is not None else ""
                            ),
                            "predicted_share": f"{prediction:.9f}",
                            "actual_share": f"{observed:.9f}",
                            "actual_events": f"{actual_values.get(player_id, 0.0):.0f}",
                            "absolute_error": f"{abs(prediction - observed):.9f}",
                            "depth_temporal_precision": precision,
                        })

    if not room_rows:
        raise HighValueBacktestDataError("high-value backtest produced no scored rooms")
    evaluations = _aggregate_evaluations(room_rows)
    comparisons = paired_comparisons(
        room_rows, samples=bootstrap_samples, seed=random_seed
    )
    recommendation = recommend_high_value_metrics(evaluations, comparisons)
    return HighValueBacktestResult(
        player_history_path=player_root,
        high_value_history_path=high_root,
        input_hashes=input_hashes,
        target_seasons=targets,
        history_lookback=history_lookback,
        bootstrap_samples=bootstrap_samples,
        random_seed=random_seed,
        prediction_rows=tuple(sorted(prediction_rows, key=lambda row: (
            row["target_season"], row["window_end"], row["team"], row["metric"],
            row["model"], -float(row["predicted_share"]), row["gsis_id"],
        ))),
        room_rows=tuple(sorted(room_rows, key=lambda row: (
            row["target_season"], row["window_end"], row["team"], row["metric"],
            row["model"],
        ))),
        evaluation_rows=tuple(sorted(evaluations, key=lambda row: (
            row["segment"], row["scope"], row["window_end"], row["model"],
        ))),
        comparison_rows=tuple(comparisons),
        source_review=tuple(sorted(review, key=lambda row: (
            row["target_season"], str(row["window_end"]), row["team"],
            row["metric"], row["issue"],
        ))),
        recommendation=recommendation,
    )


def _csv_bytes(fields: tuple[str, ...], rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def write_high_value_backtest_snapshot(
    result: HighValueBacktestResult, root: str | Path
) -> Path:
    """Atomically publish the backtest, sensitivity comparisons, and decision."""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    label = "-".join(str(value) for value in result.target_seasons)
    parent = Path(root) / "high_value_backtest" / label
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"high-value backtest exists: {destination}")
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
        "models": list(MODEL_PRIORS),
        "metrics": {
            name: {
                "position": spec.position,
                "base_resource": spec.base_resource,
                "high_value_field": spec.high_value_field,
                "base_field": spec.base_field,
                "requires_read_source": spec.requires_read_source,
            }
            for name, spec in METRICS.items()
        },
        "methodology": {
            "question": "does strictly prior high-value rate improve future high-value allocation after ordinary role is known",
            "base_role": "resource-selected role policy: depth-only QB and frozen depth/history blend for RB/WR/TE",
            "adjustment": "multiply base role by a player high-value rate relative to his historical team-position rate, beta-shrunk by 12/24/48 base opportunities and bounded from 0.25 to 4.0",
            "history_boundary": "only seasons strictly before each target are used; read-derived seasons with unavailable FTN data are omitted rather than treated as zero",
            "transfer": f"prior-team counts receive {PRIOR_TEAM_FACTOR:.2f} weight and a changed-team multiplier is shrunk toward one by {TRANSFER_RELIABILITY_MULTIPLIER:.2f}",
            "candidate_universe": "target-season Week 1 ACT/INA roster; later entrants remain zero-share forecasts",
            "evaluation_oracles": "actual weekly ACT status and actual team-position metric volume isolate conditional allocation from availability and volume",
            "primary_error": "room total-variation distance",
            "uncertainty": "paired 90% bootstrap intervals resample team-season clusters with a deterministic independent seed per segment, scope, window, and challenger",
            "promotion_gate": result.recommendation["promotion_rule"],
            "validation_caveat": "retrospective model and metric selection with oracle availability/volume; any passing feature must be frozen before prospective 2026 scoring",
        },
        "parameters": {
            "history_lookback": result.history_lookback,
            "history_recency_factor": RECENCY_FACTOR,
            "prior_team_factor": PRIOR_TEAM_FACTOR,
            "transfer_reliability_multiplier": TRANSFER_RELIABILITY_MULTIPLIER,
            "model_prior_opportunities": MODEL_PRIORS,
            "rate_multiplier_bounds": [RATE_MULTIPLIER_LOW, RATE_MULTIPLIER_HIGH],
            "bootstrap_samples": result.bootstrap_samples,
            "random_seed": result.random_seed,
            "comparison_seed_policy": "sha256(base seed, window, segment, scope, challenger, baseline)",
        },
        "inputs": {
            "player_history": str(result.player_history_path),
            "high_value_history": str(result.high_value_history_path),
            "sha256": dict(result.input_hashes),
        },
        "quality": {
            "prediction_rows": len(result.prediction_rows),
            "room_rows": len(result.room_rows),
            "evaluation_rows": len(result.evaluation_rows),
            "comparison_rows": len(result.comparison_rows),
            "source_review_rows": len(result.source_review),
            "maximum_prediction_reconciliation_error": max(
                abs(float(row["prediction_share_sum"]) - 1.0)
                for row in result.room_rows
            ),
            "maximum_forecast_unallocated_share": max(
                float(row["forecast_unallocated_share"]) for row in result.room_rows
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
