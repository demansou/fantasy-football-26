"""Backtest team high-value event rates before turning player shares into counts.

This layer deliberately isolates a narrow question: conditional on the actual base
resource (RB carries or position targets), does a team's own strictly prior event
rate improve on the time-correct league rate?  Actual target-window base volume is
an evaluation-only oracle.  The production builder later replaces it with the
caller-aware 2026 resource pool.
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

from .high_value_backtest import (
    COMPARISON_FIELDS as ROLE_COMPARISON_FIELDS,
    EVALUATION_FIELDS as ROLE_EVALUATION_FIELDS,
    METRICS,
    MODEL_PRIORS as ROLE_MODEL_PRIORS,
    recommend_high_value_metrics,
)


SCHEMA_VERSION = "1.0.0"
MODEL_VERSION = "high-value-team-volume-backtest-v0.1.0"
ROLE_BACKTEST_MODEL_VERSION = "high-value-role-backtest-v0.2.0"
WINDOWS = (4, 8, 18)
BASE_MODEL = "league_rate"
MODEL_PRIORS: Mapping[str, float | None] = {
    BASE_MODEL: None,
    "team_rate_raw": 0.0,
    "team_rate_p25": 25.0,
    "team_rate_p50": 50.0,
    "team_rate_p100": 100.0,
    "team_rate_p200": 200.0,
}
RECENCY_FACTOR = 0.65
NOMINAL_RATE_COVERAGE = 0.90
MIN_CLEAR_HOLDOUT_WINS = 2

PREDICTION_FIELDS = (
    "target_season", "segment", "window_end", "team", "position", "metric",
    "base_resource", "model", "prior_opportunities", "training_seasons",
    "training_league_events", "training_league_base_opportunities",
    "training_league_rate", "training_team_events",
    "training_team_base_opportunities", "predicted_rate", "actual_games",
    "actual_base_opportunities", "actual_events", "actual_rate",
    "predicted_events_oracle_base", "absolute_rate_error",
    "absolute_event_error", "absolute_event_error_per_game",
)
EVALUATION_FIELDS = (
    "segment", "scope", "window_end", "model", "team_count",
    "team_metric_count", "actual_games", "actual_base_opportunities",
    "actual_events", "mean_absolute_rate_error",
    "opportunity_weighted_absolute_rate_error",
    "mean_absolute_event_error_per_game", "delta_rate_error_vs_league",
)
COMPARISON_FIELDS = (
    "segment", "scope", "window_end", "challenger", "baseline",
    "pair_count", "cluster_count", "mean_rate_error_delta",
    "delta_ci90_low", "delta_ci90_high", "paired_win_rate", "interpretation",
)
CALIBRATION_FIELDS = (
    "metric", "model", "calibration_seasons", "calibration_window_end",
    "calibration_team_seasons", "nominal_coverage",
    "conformal_absolute_rate_radius", "holdout_season", "holdout_team_count",
    "holdout_coverage", "holdout_below_count", "holdout_above_count",
    "holdout_mean_interval_width", "calibration_status",
)
REVIEW_FIELDS = (
    "target_season", "window_end", "team", "metric", "issue", "details",
)


class HighValueVolumeBacktestDataError(ValueError):
    """Raised when a team-volume backtest cannot be reproduced safely."""


@dataclass(frozen=True)
class HighValueVolumeBacktestResult:
    high_value_history_path: Path
    role_backtest_path: Path
    input_hashes: Mapping[str, str]
    development_seasons: tuple[int, ...]
    holdout_season: int
    history_lookback: int
    bootstrap_samples: int
    random_seed: int
    supported_metrics: tuple[str, ...]
    prediction_rows: tuple[Mapping[str, Any], ...]
    evaluation_rows: tuple[Mapping[str, Any], ...]
    comparison_rows: tuple[Mapping[str, Any], ...]
    calibration_rows: tuple[Mapping[str, Any], ...]
    source_review: tuple[Mapping[str, Any], ...]
    recommendation: Mapping[str, Any]


def _read_manifest(root: Path) -> tuple[bytes, Mapping[str, Any]]:
    path = root / "manifest.json"
    if not path.is_file():
        raise HighValueVolumeBacktestDataError(f"missing input manifest: {path}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HighValueVolumeBacktestDataError(
            f"input manifest is not valid JSON: {path}"
        ) from error
    if not isinstance(value, dict):
        raise HighValueVolumeBacktestDataError(
            f"input manifest is not an object: {path}"
        )
    return raw, value


def _verified_csv(
    root: Path,
    manifest: Mapping[str, Any],
    filename: str,
    required: set[str],
) -> tuple[bytes, list[dict[str, str]]]:
    metadata = (manifest.get("artifacts") or {}).get(filename)
    if not isinstance(metadata, dict) or not metadata.get("sha256"):
        raise HighValueVolumeBacktestDataError(
            f"manifest does not describe {filename}: {root}"
        )
    path = root / filename
    if not path.is_file():
        raise HighValueVolumeBacktestDataError(f"input does not exist: {path}")
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != metadata["sha256"]:
        raise HighValueVolumeBacktestDataError(
            f"input hash mismatch for {path}: expected {metadata['sha256']}, got {actual}"
        )
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        fields = set(reader.fieldnames or ())
        rows = list(reader)
    except UnicodeDecodeError as error:
        raise HighValueVolumeBacktestDataError(f"input is not UTF-8 CSV: {path}") from error
    missing = required - fields
    if missing or not rows:
        raise HighValueVolumeBacktestDataError(
            f"{path} is empty or missing fields {sorted(missing)}"
        )
    return raw, rows


def _number(value: Any, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise HighValueVolumeBacktestDataError(f"{context} must be numeric") from error
    if not math.isfinite(result) or result < 0:
        raise HighValueVolumeBacktestDataError(
            f"{context} must be finite and nonnegative"
        )
    return result


def _integer(value: Any, context: str) -> int:
    result = _number(value, context)
    if not result.is_integer():
        raise HighValueVolumeBacktestDataError(f"{context} must be an integer")
    return int(result)


def _percentile(values: Iterable[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise HighValueVolumeBacktestDataError("cannot summarize an empty sample")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _conformal_radius(values: Iterable[float], coverage: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise HighValueVolumeBacktestDataError("cannot calibrate an empty sample")
    rank = math.ceil((len(ordered) + 1) * coverage)
    return ordered[min(rank, len(ordered)) - 1]


def _validated_supported_metrics(
    root: Path,
    manifest: Mapping[str, Any],
    evaluations: list[dict[str, str]],
    comparisons: list[dict[str, str]],
) -> tuple[str, ...]:
    if manifest.get("model_version") != ROLE_BACKTEST_MODEL_VERSION:
        raise HighValueVolumeBacktestDataError(
            "unsupported high-value role backtest model version"
        )
    parameters = manifest.get("parameters") or {}
    if parameters.get("model_prior_opportunities") != dict(ROLE_MODEL_PRIORS):
        raise HighValueVolumeBacktestDataError(
            "role backtest does not use the frozen model priors"
        )
    recomputed = recommend_high_value_metrics(evaluations, comparisons)
    if recomputed != manifest.get("recommendation"):
        raise HighValueVolumeBacktestDataError(
            f"role backtest recommendation does not reproduce: {root}"
        )
    supported = tuple(recomputed.get("supported_metrics") or ())
    if not supported:
        raise HighValueVolumeBacktestDataError(
            "role backtest promoted no high-value metrics"
        )
    return supported


def _history_groups(
    rows: Iterable[Mapping[str, str]], supported_metrics: Iterable[str]
) -> dict[tuple[int, int, str, str], tuple[float, float]]:
    supported = set(supported_metrics)
    output: dict[tuple[int, int, str, str], tuple[float, float]] = {}
    for row in rows:
        season = _integer(row["season"], "history season")
        week = _integer(row["week"], "history week")
        if not 1 <= week <= 18:
            continue
        team = row["team"]
        position = row["position"]
        for metric in supported:
            spec = METRICS[metric]
            if spec.position != position:
                continue
            event = _number(row[spec.high_value_field], f"{metric} events")
            base = _number(row[spec.base_field], f"{metric} base opportunities")
            if event > base + 1e-9:
                raise HighValueVolumeBacktestDataError(
                    f"{season} Week {week} {team} {metric} events exceed base"
                )
            key = season, week, team, metric
            if key in output:
                raise HighValueVolumeBacktestDataError(
                    f"duplicate team-week metric history row: {key}"
                )
            output[key] = event, base
    if not output:
        raise HighValueVolumeBacktestDataError("no supported team metric history")
    return output


def _training_rates(
    groups: Mapping[tuple[int, int, str, str], tuple[float, float]],
    *,
    target_season: int,
    metric: str,
    history_lookback: int,
) -> tuple[tuple[int, ...], float, float, dict[str, tuple[float, float]]]:
    available = sorted({key[0] for key in groups if key[3] == metric})
    training = tuple(
        season for season in available
        if target_season - history_lookback <= season < target_season
    )
    if not training:
        raise HighValueVolumeBacktestDataError(
            f"{metric} target {target_season} has no strictly prior history"
        )
    league_events = 0.0
    league_base = 0.0
    teams: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for (season, _week, team, row_metric), (event, base) in groups.items():
        if row_metric != metric or season not in training:
            continue
        weight = RECENCY_FACTOR ** (target_season - 1 - season)
        league_events += weight * event
        league_base += weight * base
        teams[team][0] += weight * event
        teams[team][1] += weight * base
    if league_base <= 0:
        raise HighValueVolumeBacktestDataError(
            f"{metric} target {target_season} has no training opportunities"
        )
    return (
        training,
        league_events,
        league_base,
        {team: (values[0], values[1]) for team, values in teams.items()},
    )


def _model_rate(
    model: str,
    *,
    league_rate: float,
    team_events: float,
    team_base: float,
) -> float:
    prior = MODEL_PRIORS[model]
    if model == BASE_MODEL or team_base <= 0:
        return league_rate
    if prior == 0:
        return team_events / team_base
    if prior is None:
        raise HighValueVolumeBacktestDataError(f"invalid model prior for {model}")
    return (team_events + prior * league_rate) / (team_base + prior)


def _aggregate_evaluations(
    predictions: list[dict[str, Any]], supported_metrics: Iterable[str]
) -> list[dict[str, Any]]:
    scopes = ["ALL", *supported_metrics]
    output: list[dict[str, Any]] = []
    for segment in ("development", "holdout"):
        for scope in scopes:
            for window in WINDOWS:
                for model in MODEL_PRIORS:
                    values = [
                        row for row in predictions
                        if row["segment"] == segment
                        and int(row["window_end"]) == window
                        and row["model"] == model
                        and (scope == "ALL" or row["metric"] == scope)
                    ]
                    if not values:
                        continue
                    mean_rate_error = sum(
                        float(row["absolute_rate_error"]) for row in values
                    ) / len(values)
                    base_values = [
                        row for row in predictions
                        if row["segment"] == segment
                        and int(row["window_end"]) == window
                        and row["model"] == BASE_MODEL
                        and (scope == "ALL" or row["metric"] == scope)
                    ]
                    base_error = sum(
                        float(row["absolute_rate_error"]) for row in base_values
                    ) / len(base_values)
                    total_base = sum(
                        float(row["actual_base_opportunities"]) for row in values
                    )
                    total_abs_events = sum(
                        float(row["absolute_event_error"]) for row in values
                    )
                    output.append({
                        "segment": segment,
                        "scope": scope,
                        "window_end": window,
                        "model": model,
                        "team_count": len({
                            (row["target_season"], row["team"]) for row in values
                        }),
                        "team_metric_count": len(values),
                        "actual_games": sum(int(row["actual_games"]) for row in values),
                        "actual_base_opportunities": f"{total_base:.0f}",
                        "actual_events": f"{sum(float(row['actual_events']) for row in values):.0f}",
                        "mean_absolute_rate_error": f"{mean_rate_error:.9f}",
                        "opportunity_weighted_absolute_rate_error": (
                            f"{total_abs_events / total_base:.9f}"
                        ),
                        "mean_absolute_event_error_per_game": f"{sum(float(row['absolute_event_error_per_game']) for row in values) / len(values):.9f}",
                        "delta_rate_error_vs_league": f"{mean_rate_error - base_error:.9f}",
                    })
    return output


def paired_comparisons(
    predictions: list[dict[str, Any]],
    *,
    supported_metrics: Iterable[str],
    samples: int,
    seed: int,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for segment in ("development", "holdout"):
        for scope in ("ALL", *supported_metrics):
            for window in WINDOWS:
                rows = [
                    row for row in predictions
                    if row["segment"] == segment
                    and int(row["window_end"]) == window
                    and (scope == "ALL" or row["metric"] == scope)
                ]
                lookup = {
                    (row["target_season"], row["team"], row["metric"], row["model"]): row
                    for row in rows
                }
                for challenger in MODEL_PRIORS:
                    if challenger == BASE_MODEL:
                        continue
                    deltas: list[tuple[tuple[int, str], float]] = []
                    for key, row in lookup.items():
                        season, team, metric, model = key
                        if model != challenger:
                            continue
                        baseline = lookup.get((season, team, metric, BASE_MODEL))
                        if baseline is None:
                            continue
                        deltas.append((
                            (int(season), team),
                            float(row["absolute_rate_error"])
                            - float(baseline["absolute_rate_error"]),
                        ))
                    clusters: dict[tuple[int, str], list[float]] = defaultdict(list)
                    for cluster, delta in deltas:
                        clusters[cluster].append(delta)
                    cluster_means = [
                        sum(values) / len(values) for values in clusters.values()
                    ]
                    if not cluster_means:
                        continue
                    material = (
                        f"{seed}|{segment}|{scope}|{window}|{challenger}|{BASE_MODEL}"
                    ).encode("utf-8")
                    comparison_seed = int.from_bytes(
                        hashlib.sha256(material).digest()[:8], "big"
                    )
                    rng = random.Random(comparison_seed)
                    bootstrap = [
                        sum(rng.choice(cluster_means) for _ in cluster_means)
                        / len(cluster_means)
                        for _ in range(samples)
                    ]
                    mean_delta = sum(value for _, value in deltas) / len(deltas)
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
                        "pair_count": len(deltas),
                        "cluster_count": len(cluster_means),
                        "mean_rate_error_delta": f"{mean_delta:.9f}",
                        "delta_ci90_low": f"{low:.9f}",
                        "delta_ci90_high": f"{high:.9f}",
                        "paired_win_rate": f"{sum(value < 0 for _, value in deltas) / len(deltas):.6f}",
                        "interpretation": interpretation,
                    })
    return output


def recommend_volume_models(
    evaluations: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
    supported_metrics: Iterable[str],
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    promoted: list[str] = []
    for metric in supported_metrics:
        development = [
            row for row in evaluations
            if row["segment"] == "development" and row["scope"] == metric
        ]
        holdout = [
            row for row in evaluations
            if row["segment"] == "holdout" and row["scope"] == metric
        ]
        if not development or not holdout:
            raise HighValueVolumeBacktestDataError(
                f"missing development or holdout evaluation for {metric}"
            )
        development_means = {
            model: sum(
                float(row["mean_absolute_rate_error"])
                for row in development if row["model"] == model
            ) / len(WINDOWS)
            for model in MODEL_PRIORS
        }
        candidate = min(
            (model for model in MODEL_PRIORS if model != BASE_MODEL),
            key=lambda model: (development_means[model], model),
        )
        development_comparisons = [
            row for row in comparisons
            if row["segment"] == "development"
            and row["scope"] == metric and row["challenger"] == candidate
        ]
        holdout_comparisons = [
            row for row in comparisons
            if row["segment"] == "holdout"
            and row["scope"] == metric and row["challenger"] == candidate
        ]
        development_deltas = [
            float(row["mean_rate_error_delta"]) for row in development_comparisons
        ]
        holdout_deltas = [
            float(row["mean_rate_error_delta"]) for row in holdout_comparisons
        ]
        clear_wins = sum(
            float(row["delta_ci90_high"]) < 0 for row in holdout_comparisons
        )
        clear_losses = sum(
            float(row["delta_ci90_low"]) > 0 for row in holdout_comparisons
        )
        passes = (
            len(development_deltas) == len(WINDOWS)
            and len(holdout_deltas) == len(WINDOWS)
            and all(value < 0 for value in development_deltas)
            and all(value < 0 for value in holdout_deltas)
            and clear_wins >= MIN_CLEAR_HOLDOUT_WINS
            and clear_losses == 0
        )
        selected = candidate if passes else BASE_MODEL
        if passes:
            promoted.append(metric)
        holdout_means = {
            model: sum(
                float(row["mean_absolute_rate_error"])
                for row in holdout if row["model"] == model
            ) / len(WINDOWS)
            for model in MODEL_PRIORS
        }
        metrics[metric] = {
            "development_candidate": candidate,
            "development_mean_absolute_rate_error": {
                model: round(value, 6)
                for model, value in development_means.items()
            },
            "holdout_mean_absolute_rate_error": {
                model: round(value, 6) for model, value in holdout_means.items()
            },
            "development_deltas_vs_league": [round(value, 6) for value in development_deltas],
            "holdout_deltas_vs_league": [round(value, 6) for value in holdout_deltas],
            "holdout_clear_win_windows": clear_wins,
            "holdout_clear_loss_windows": clear_losses,
            "team_specific_gate_passed": passes,
            "selected_model": selected,
            "recommended_action": (
                f"use_{candidate}_conditional_rate"
                if passes else "use_time_correct_league_rate"
            ),
        }
    all_development = [
        row for row in evaluations
        if row["segment"] == "development" and row["scope"] == "ALL"
    ]
    aggregate_means = {
        model: sum(
            float(row["mean_absolute_rate_error"])
            for row in all_development if row["model"] == model
        ) / len(WINDOWS)
        for model in MODEL_PRIORS
    }
    return {
        "baseline_model": BASE_MODEL,
        "models": list(MODEL_PRIORS),
        "development_aggregate_best_model": min(
            aggregate_means, key=lambda model: (aggregate_means[model], model)
        ),
        "development_aggregate_mean_absolute_rate_error": {
            model: round(value, 6) for model, value in aggregate_means.items()
        },
        "promotion_rule": (
            "choose the lowest-development-error team model per metric; require "
            "negative mean error deltas in all three development and all three "
            f"untouched holdout windows, at least {MIN_CLEAR_HOLDOUT_WINS} holdout "
            "90% interval wins, and no clear holdout loss; otherwise use league_rate"
        ),
        "team_specific_metrics": promoted,
        "league_rate_metrics": [
            metric for metric in metrics if metric not in promoted
        ],
        "metrics": metrics,
        "recommendation": (
            "use the time-correct recency-weighted league conditional rate for every "
            "supported 2026 team metric; let caller-aware base resource volume create "
            "team differences; retain team-rate persistence only as a diagnostic"
            if not promoted else
            "use promoted team rates only for named metrics and league rates otherwise"
        ),
        "validation_status": (
            "point models selected on development seasons and gated on one untouched "
            "holdout season; interval radii calibrated on development only"
        ),
    }


def calibration_rows(
    predictions: list[dict[str, Any]],
    recommendation: Mapping[str, Any],
    *,
    development_seasons: tuple[int, ...],
    holdout_season: int,
    supported_metrics: Iterable[str],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for metric in supported_metrics:
        model = recommendation["metrics"][metric]["selected_model"]
        development = [
            row for row in predictions
            if row["segment"] == "development"
            and row["metric"] == metric and row["model"] == model
            and int(row["window_end"]) == 18
        ]
        holdout = [
            row for row in predictions
            if row["segment"] == "holdout"
            and row["metric"] == metric and row["model"] == model
            and int(row["window_end"]) == 18
        ]
        radius = _conformal_radius(
            (float(row["absolute_rate_error"]) for row in development),
            NOMINAL_RATE_COVERAGE,
        )
        below = above = covered = 0
        widths: list[float] = []
        for row in holdout:
            prediction = float(row["predicted_rate"])
            actual = float(row["actual_rate"])
            low = max(0.0, prediction - radius)
            high = min(1.0, prediction + radius)
            widths.append(high - low)
            if actual < low:
                below += 1
            elif actual > high:
                above += 1
            else:
                covered += 1
        output.append({
            "metric": metric,
            "model": model,
            "calibration_seasons": "|".join(map(str, development_seasons)),
            "calibration_window_end": 18,
            "calibration_team_seasons": len(development),
            "nominal_coverage": f"{NOMINAL_RATE_COVERAGE:.3f}",
            "conformal_absolute_rate_radius": f"{radius:.9f}",
            "holdout_season": holdout_season,
            "holdout_team_count": len(holdout),
            "holdout_coverage": f"{covered / len(holdout):.6f}",
            "holdout_below_count": below,
            "holdout_above_count": above,
            "holdout_mean_interval_width": f"{sum(widths) / len(widths):.9f}",
            "calibration_status": "development_conformal_radius_tested_once_on_untouched_holdout",
        })
    return output


def build_high_value_volume_backtest(
    high_value_history: str | Path,
    high_value_role_backtest: str | Path,
    *,
    development_seasons: Iterable[int] = (2023, 2024),
    holdout_season: int = 2025,
    history_lookback: int = 3,
    bootstrap_samples: int = 2000,
    random_seed: int = 20260903,
) -> HighValueVolumeBacktestResult:
    """Evaluate team-specific conditional rates against a pooled league baseline."""

    development = tuple(sorted(set(development_seasons)))
    if not development or any(
        isinstance(value, bool) or not isinstance(value, int) for value in development
    ):
        raise ValueError("development_seasons must contain integers")
    if isinstance(holdout_season, bool) or not isinstance(holdout_season, int):
        raise ValueError("holdout_season must be an integer")
    if holdout_season in development or max(development) >= holdout_season:
        raise ValueError("holdout_season must be strictly after development seasons")
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

    history_root = Path(high_value_history)
    role_root = Path(high_value_role_backtest)
    history_manifest_raw, history_manifest = _read_manifest(history_root)
    role_manifest_raw, role_manifest = _read_manifest(role_root)
    required_history = {"season", "week", "team", "position"}
    required_history.update(
        spec.high_value_field for spec in METRICS.values()
    )
    required_history.update(spec.base_field for spec in METRICS.values())
    history_raw, history_rows = _verified_csv(
        history_root, history_manifest, "team_week_high_value.csv", required_history
    )
    role_eval_raw, role_evaluations = _verified_csv(
        role_root, role_manifest, "model_evaluation.csv",
        set(ROLE_EVALUATION_FIELDS),
    )
    role_comparison_raw, role_comparisons = _verified_csv(
        role_root, role_manifest, "paired_comparisons.csv",
        set(ROLE_COMPARISON_FIELDS),
    )
    supported = _validated_supported_metrics(
        role_root, role_manifest, role_evaluations, role_comparisons
    )
    groups = _history_groups(history_rows, supported)
    available_seasons = {key[0] for key in groups}
    targets = (*development, holdout_season)
    if not set(targets).issubset(available_seasons):
        raise HighValueVolumeBacktestDataError(
            f"history lacks target seasons {sorted(set(targets) - available_seasons)}"
        )

    predictions: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    for target in targets:
        segment = "development" if target in development else "holdout"
        for metric in supported:
            spec = METRICS[metric]
            training, league_events, league_base, teams = _training_rates(
                groups,
                target_season=target,
                metric=metric,
                history_lookback=history_lookback,
            )
            league_rate = league_events / league_base
            target_teams = sorted({
                key[2] for key in groups if key[0] == target and key[3] == metric
            })
            for team in target_teams:
                team_events, team_base = teams.get(team, (0.0, 0.0))
                if team_base <= 0:
                    review.append({
                        "target_season": target, "window_end": "", "team": team,
                        "metric": metric, "issue": "no_team_training_history",
                        "details": "all team-specific models fall back to league_rate",
                    })
                for window in WINDOWS:
                    actual_rows = [
                        groups[key]
                        for key in groups
                        if key[0] == target and key[2] == team
                        and key[3] == metric and key[1] <= window
                    ]
                    games = len(actual_rows)
                    actual_events = sum(value[0] for value in actual_rows)
                    actual_base = sum(value[1] for value in actual_rows)
                    if games <= 0 or actual_base <= 0:
                        review.append({
                            "target_season": target, "window_end": window,
                            "team": team, "metric": metric,
                            "issue": "zero_target_base_opportunities",
                            "details": "team-window omitted because conditional rate is undefined",
                        })
                        continue
                    actual_rate = actual_events / actual_base
                    for model, prior in MODEL_PRIORS.items():
                        predicted_rate = _model_rate(
                            model,
                            league_rate=league_rate,
                            team_events=team_events,
                            team_base=team_base,
                        )
                        predicted_events = predicted_rate * actual_base
                        event_error = abs(predicted_events - actual_events)
                        predictions.append({
                            "target_season": target,
                            "segment": segment,
                            "window_end": window,
                            "team": team,
                            "position": spec.position,
                            "metric": metric,
                            "base_resource": spec.base_resource,
                            "model": model,
                            "prior_opportunities": "" if prior is None else f"{prior:.0f}",
                            "training_seasons": "|".join(map(str, training)),
                            "training_league_events": f"{league_events:.6f}",
                            "training_league_base_opportunities": f"{league_base:.6f}",
                            "training_league_rate": f"{league_rate:.9f}",
                            "training_team_events": f"{team_events:.6f}",
                            "training_team_base_opportunities": f"{team_base:.6f}",
                            "predicted_rate": f"{predicted_rate:.9f}",
                            "actual_games": games,
                            "actual_base_opportunities": f"{actual_base:.0f}",
                            "actual_events": f"{actual_events:.0f}",
                            "actual_rate": f"{actual_rate:.9f}",
                            "predicted_events_oracle_base": f"{predicted_events:.6f}",
                            "absolute_rate_error": f"{abs(predicted_rate - actual_rate):.9f}",
                            "absolute_event_error": f"{event_error:.6f}",
                            "absolute_event_error_per_game": f"{event_error / games:.9f}",
                        })
    if not predictions:
        raise HighValueVolumeBacktestDataError("volume backtest produced no predictions")
    evaluations = _aggregate_evaluations(predictions, supported)
    comparisons = paired_comparisons(
        predictions,
        supported_metrics=supported,
        samples=bootstrap_samples,
        seed=random_seed,
    )
    recommendation = recommend_volume_models(evaluations, comparisons, supported)
    calibration = calibration_rows(
        predictions,
        recommendation,
        development_seasons=development,
        holdout_season=holdout_season,
        supported_metrics=supported,
    )
    return HighValueVolumeBacktestResult(
        high_value_history_path=history_root,
        role_backtest_path=role_root,
        input_hashes={
            "high_value_history_manifest.json": hashlib.sha256(history_manifest_raw).hexdigest(),
            "team_week_high_value.csv": hashlib.sha256(history_raw).hexdigest(),
            "high_value_role_backtest_manifest.json": hashlib.sha256(role_manifest_raw).hexdigest(),
            "role_model_evaluation.csv": hashlib.sha256(role_eval_raw).hexdigest(),
            "role_paired_comparisons.csv": hashlib.sha256(role_comparison_raw).hexdigest(),
        },
        development_seasons=development,
        holdout_season=holdout_season,
        history_lookback=history_lookback,
        bootstrap_samples=bootstrap_samples,
        random_seed=random_seed,
        supported_metrics=supported,
        prediction_rows=tuple(sorted(predictions, key=lambda row: (
            row["target_season"], row["window_end"], row["team"],
            row["metric"], row["model"],
        ))),
        evaluation_rows=tuple(sorted(evaluations, key=lambda row: (
            row["segment"], row["scope"], row["window_end"], row["model"],
        ))),
        comparison_rows=tuple(sorted(comparisons, key=lambda row: (
            row["segment"], row["scope"], row["window_end"], row["challenger"],
        ))),
        calibration_rows=tuple(calibration),
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


def write_high_value_volume_backtest_snapshot(
    result: HighValueVolumeBacktestResult, root: str | Path
) -> Path:
    """Atomically publish team-rate evaluation, calibration, and decisions."""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    label = "-".join(map(str, (*result.development_seasons, result.holdout_season)))
    parent = Path(root) / "high_value_volume_backtest" / label
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"high-value volume backtest exists: {destination}")
    artifacts = {
        "predictions.csv": _csv_bytes(PREDICTION_FIELDS, result.prediction_rows),
        "model_evaluation.csv": _csv_bytes(EVALUATION_FIELDS, result.evaluation_rows),
        "paired_comparisons.csv": _csv_bytes(COMPARISON_FIELDS, result.comparison_rows),
        "rate_calibration.csv": _csv_bytes(CALIBRATION_FIELDS, result.calibration_rows),
        "source_review.csv": _csv_bytes(REVIEW_FIELDS, result.source_review),
    }
    fields = {
        "predictions.csv": PREDICTION_FIELDS,
        "model_evaluation.csv": EVALUATION_FIELDS,
        "paired_comparisons.csv": COMPARISON_FIELDS,
        "rate_calibration.csv": CALIBRATION_FIELDS,
        "source_review.csv": REVIEW_FIELDS,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        ),
        "development_seasons": list(result.development_seasons),
        "holdout_season": result.holdout_season,
        "windows": list(WINDOWS),
        "supported_metrics": list(result.supported_metrics),
        "models": dict(MODEL_PRIORS),
        "methodology": {
            "question": "does a team's strictly prior conditional event rate improve on the time-correct league rate after base resource volume is known",
            "history_boundary": "only seasons strictly before each target are used with exponential recency weighting",
            "evaluation_oracle": "actual target-window RB carries or position targets isolate conditional event rate from the separately modeled base resource pool",
            "development_holdout": "2023-24 choose a candidate; 2025 is untouched until the fixed promotion gate is evaluated",
            "primary_error": "unweighted mean absolute team conditional-rate error; event-count error using oracle base volume is diagnostic",
            "uncertainty": "paired 90% bootstrap intervals resample team-season clusters with independent deterministic seeds",
            "rate_band": "90% split-conformal absolute-error radius from development Week 18 forecasts, evaluated once on the untouched 2025 season",
            "scope": "team-position high-value event rate conditional on its base resource; not total offensive volume, player allocation, production, or fantasy points",
        },
        "parameters": {
            "history_lookback": result.history_lookback,
            "history_recency_factor": RECENCY_FACTOR,
            "model_prior_opportunities": dict(MODEL_PRIORS),
            "bootstrap_samples": result.bootstrap_samples,
            "random_seed": result.random_seed,
            "comparison_seed_policy": "sha256(base seed, segment, scope, window, challenger, baseline)",
            "nominal_rate_coverage": NOMINAL_RATE_COVERAGE,
        },
        "inputs": {
            "high_value_history": str(result.high_value_history_path),
            "high_value_role_backtest": str(result.role_backtest_path),
            "sha256": dict(result.input_hashes),
        },
        "quality": {
            "prediction_rows": len(result.prediction_rows),
            "evaluation_rows": len(result.evaluation_rows),
            "comparison_rows": len(result.comparison_rows),
            "calibration_rows": len(result.calibration_rows),
            "source_review_rows": len(result.source_review),
            "minimum_holdout_rate_coverage": min(
                float(row["holdout_coverage"]) for row in result.calibration_rows
            ),
            "aggregate_holdout_rate_coverage": sum(
                float(row["holdout_coverage"]) * int(row["holdout_team_count"])
                for row in result.calibration_rows
            ) / sum(int(row["holdout_team_count"]) for row in result.calibration_rows),
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
