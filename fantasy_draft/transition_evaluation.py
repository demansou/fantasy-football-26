"""Pool caller-transition cohorts and test residual bands on a held-out season."""

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
from itertools import product
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "1.0.0"
MODEL_VERSION = "transition-multiseason-evaluation-v0.2.0"
BACKTEST_MODEL_VERSION = "opening-caller-transition-backtest-v0.3.0"
BASELINE_MODEL = "shrunken_persistence"
CANDIDATE_MODEL = "caller_aware_v0"
MODELS = (BASELINE_MODEL, CANDIDATE_MODEL)
NOMINAL_COVERAGE = 0.90

PAIRED_SUMMARY_FIELDS = (
    "scope",
    "scope_season",
    "week_end",
    "team_season_count",
    "team_cluster_count",
    "candidate_win_count",
    "mean_paired_delta",
    "bootstrap_95pct_lower",
    "bootstrap_95pct_upper",
)

CALIBRATION_FIELDS = (
    "model",
    "week_end",
    "metric",
    "development_count",
    "nominal_coverage",
    "finite_sample_rank",
    "residual_radius",
    "tolerance",
    "normalized_radius",
)

COVERAGE_PREDICTION_FIELDS = (
    "target_season",
    "week_end",
    "team",
    "caller_cohort",
    "metric",
    "model",
    "forecast_value",
    "actual_value",
    "residual_radius",
    "interval_low",
    "interval_high",
    "covered",
)

COVERAGE_SUMMARY_FIELDS = (
    "target_season",
    "week_end",
    "cohort",
    "model",
    "comparison_count",
    "covered_count",
    "coverage_rate",
    "wilson_95pct_lower",
    "wilson_95pct_upper",
    "mean_normalized_radius",
)

METRIC_COVERAGE_FIELDS = (
    "target_season",
    "week_end",
    "model",
    "metric",
    "comparison_count",
    "covered_count",
    "coverage_rate",
    "wilson_95pct_lower",
    "wilson_95pct_upper",
)


class TransitionEvaluationDataError(ValueError):
    """Raised when transition snapshots cannot support a held-out evaluation."""


@dataclass(frozen=True)
class BacktestInput:
    path: Path
    target_season: int
    windows: tuple[int, ...]
    models: Mapping[str, Any]
    scoring: Mapping[str, Any]
    predictions: tuple[Mapping[str, str], ...]
    paired_effects: tuple[Mapping[str, str], ...]
    input_hashes: Mapping[str, str]


@dataclass(frozen=True)
class TransitionEvaluationResult:
    target_seasons: tuple[int, ...]
    development_seasons: tuple[int, ...]
    holdout_season: int
    windows: tuple[int, ...]
    bootstrap_samples: int
    random_seed: int
    input_paths: tuple[Path, ...]
    input_hashes: Mapping[str, str]
    paired_summary_rows: tuple[Mapping[str, Any], ...]
    calibration_rows: tuple[Mapping[str, Any], ...]
    coverage_prediction_rows: tuple[Mapping[str, Any], ...]
    coverage_summary_rows: tuple[Mapping[str, Any], ...]
    metric_coverage_rows: tuple[Mapping[str, Any], ...]
    evaluation: Mapping[str, Any]


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_csv(raw: bytes, required: set[str], context: str) -> list[dict[str, str]]:
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    except UnicodeDecodeError as error:
        raise TransitionEvaluationDataError(f"{context} is not UTF-8") from error
    fields = set(rows[0]) if rows else set()
    missing = required - fields
    if not rows or missing:
        raise TransitionEvaluationDataError(
            f"{context} has no rows or is missing fields {sorted(missing)}"
        )
    return rows


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TransitionEvaluationDataError(f"{context} must be an object")
    return value


def _integer(value: Any, context: str) -> int:
    if isinstance(value, bool):
        raise TransitionEvaluationDataError(f"{context} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise TransitionEvaluationDataError(f"{context} must be an integer") from error
    return result


def _finite(value: Any, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise TransitionEvaluationDataError(f"{context} must be numeric") from error
    if not math.isfinite(result):
        raise TransitionEvaluationDataError(f"{context} must be finite")
    return result


def _load_backtest(path: str | Path) -> BacktestInput:
    root = Path(path)
    if not root.is_dir():
        raise TransitionEvaluationDataError(f"backtest snapshot is not a directory: {root}")
    manifest_path = root / "manifest.json"
    try:
        manifest_raw = manifest_path.read_bytes()
        manifest = _mapping(json.loads(manifest_raw.decode("utf-8")), "manifest")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TransitionEvaluationDataError(f"invalid backtest manifest: {manifest_path}") from error
    if manifest.get("schema_version") != "1.0.0":
        raise TransitionEvaluationDataError(f"unsupported backtest schema: {root}")
    if manifest.get("model_version") != BACKTEST_MODEL_VERSION:
        raise TransitionEvaluationDataError(f"unsupported backtest model version: {root}")
    seasons = _mapping(manifest.get("seasons"), "manifest.seasons")
    target_season = _integer(seasons.get("target"), "manifest.seasons.target")
    raw_windows = seasons.get("target_windows")
    if not isinstance(raw_windows, list) or not raw_windows:
        raise TransitionEvaluationDataError("manifest.seasons.target_windows must be a list")
    try:
        windows = tuple(int(str(value).rsplit("-", 1)[1]) for value in raw_windows)
    except (IndexError, ValueError) as error:
        raise TransitionEvaluationDataError("invalid target window labels") from error
    artifacts = _mapping(manifest.get("artifacts"), "manifest.artifacts")
    raw_by_path: dict[str, bytes] = {str(manifest_path): manifest_raw}
    parent_inputs = _mapping(manifest.get("input_sha256"), "manifest.input_sha256")
    if not parent_inputs:
        raise TransitionEvaluationDataError(
            f"backtest manifest has no bound source inputs: {root}"
        )
    for source_path, expected in parent_inputs.items():
        if not isinstance(source_path, str) or not isinstance(expected, str):
            raise TransitionEvaluationDataError(
                f"invalid backtest source hash entry: {root}"
            )
        path_object = Path(source_path)
        try:
            raw = path_object.read_bytes()
        except OSError as error:
            raise TransitionEvaluationDataError(
                f"bound backtest source is unavailable: {path_object}"
            ) from error
        if _sha256(raw) != expected:
            raise TransitionEvaluationDataError(
                f"bound backtest source hash mismatch: {path_object}"
            )
        raw_by_path[str(path_object)] = raw
    loaded: dict[str, bytes] = {}
    for name in ("predictions.csv", "paired_team_effects.csv"):
        entry = _mapping(artifacts.get(name), f"manifest.artifacts.{name}")
        expected = entry.get("sha256")
        if not isinstance(expected, str):
            raise TransitionEvaluationDataError(f"missing hash for {name}: {root}")
        artifact_path = root / name
        raw = artifact_path.read_bytes()
        if _sha256(raw) != expected:
            raise TransitionEvaluationDataError(f"hash mismatch for {artifact_path}")
        loaded[name] = raw
        raw_by_path[str(artifact_path)] = raw
    predictions = _read_csv(
        loaded["predictions.csv"],
        {
            "target_season",
            "week_end",
            "team",
            "caller_cohort",
            "metric",
            "tolerance",
            "model",
            "forecast_value",
            "actual_value",
            "absolute_error",
        },
        str(root / "predictions.csv"),
    )
    paired = _read_csv(
        loaded["paired_team_effects.csv"],
        {"target_season", "week_end", "team", "paired_delta", "candidate_wins"},
        str(root / "paired_team_effects.csv"),
    )
    if any(_integer(row["target_season"], "prediction target season") != target_season for row in predictions):
        raise TransitionEvaluationDataError(f"prediction target season mismatch: {root}")
    if any(_integer(row["target_season"], "paired target season") != target_season for row in paired):
        raise TransitionEvaluationDataError(f"paired target season mismatch: {root}")
    return BacktestInput(
        path=root,
        target_season=target_season,
        windows=windows,
        models=_mapping(manifest.get("models"), "manifest.models"),
        scoring=_mapping(manifest.get("scoring"), "manifest.scoring"),
        predictions=tuple(predictions),
        paired_effects=tuple(paired),
        input_hashes={path: _sha256(raw) for path, raw in raw_by_path.items()},
    )


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        raise TransitionEvaluationDataError("cannot summarize an empty sample")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _cluster_interval(
    clusters: list[tuple[float, ...]],
    *,
    samples: int,
    seed: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    if not clusters or any(not cluster for cluster in clusters):
        raise TransitionEvaluationDataError("cannot bootstrap an empty effect sample")
    size = len(clusters)

    def sampled_mean(indices: Iterable[int]) -> float:
        selected = [value for index in indices for value in clusters[index]]
        return sum(selected) / len(selected)

    if size <= 7:
        means = [
            sampled_mean(indices)
            for indices in product(range(size), repeat=size)
        ]
    else:
        rng = random.Random(seed)
        means = [
            sampled_mean(rng.randrange(size) for _ in range(size))
            for _ in range(samples)
        ]
    alpha = (1 - confidence) / 2
    return _percentile(means, alpha), _percentile(means, 1 - alpha)


def _conformal_radius(values: list[float], nominal: float) -> tuple[int, float]:
    if not values:
        raise TransitionEvaluationDataError("cannot calibrate an empty residual sample")
    ordered = sorted(values)
    rank = min(len(ordered), math.ceil((len(ordered) + 1) * nominal))
    return rank, ordered[rank - 1]


def _wilson(successes: int, count: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if count <= 0:
        raise TransitionEvaluationDataError("Wilson interval requires observations")
    observed = successes / count
    denominator = 1 + z * z / count
    center = (observed + z * z / (2 * count)) / denominator
    spread = z * math.sqrt(
        observed * (1 - observed) / count + z * z / (4 * count * count)
    ) / denominator
    return max(0.0, center - spread), min(1.0, center + spread)


def _paired_summary(
    inputs: tuple[BacktestInput, ...],
    *,
    windows: tuple[int, ...],
    bootstrap_samples: int,
    random_seed: int,
) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    seasons = tuple(item.target_season for item in inputs)
    scopes: list[tuple[str, int | None, set[int]]] = [
        ("pooled_all_seasons", None, set(seasons)),
    ]
    scopes.extend(
        ("leave_one_season_out", omitted, set(seasons) - {omitted})
        for omitted in seasons
    )
    scopes.extend(("single_season", season, {season}) for season in seasons)
    for scope_index, (scope, label_season, included) in enumerate(scopes):
        for week_end in windows:
            selected = [
                row
                for item in inputs
                if item.target_season in included
                for row in item.paired_effects
                if _integer(row["week_end"], "paired week") == week_end
            ]
            effects = [_finite(row["paired_delta"], "paired_delta") for row in selected]
            effects_by_team: dict[str, list[float]] = defaultdict(list)
            for row, effect in zip(selected, effects, strict=True):
                effects_by_team[str(row["team"])].append(effect)
            clusters = [tuple(effects_by_team[team]) for team in sorted(effects_by_team)]
            lower, upper = _cluster_interval(
                clusters,
                samples=bootstrap_samples,
                seed=random_seed + scope_index * 100 + week_end,
            )
            rows.append(
                {
                    "scope": scope,
                    "scope_season": "" if label_season is None else label_season,
                    "week_end": week_end,
                    "team_season_count": len(effects),
                    "team_cluster_count": len(clusters),
                    "candidate_win_count": sum(effect < 0 for effect in effects),
                    "mean_paired_delta": round(statistics.mean(effects), 6),
                    "bootstrap_95pct_lower": round(lower, 6),
                    "bootstrap_95pct_upper": round(upper, 6),
                }
            )
    return rows


def _coverage(
    development: tuple[BacktestInput, ...],
    holdout: BacktestInput,
    *,
    windows: tuple[int, ...],
) -> tuple[
    list[Mapping[str, Any]],
    list[Mapping[str, Any]],
    list[Mapping[str, Any]],
    list[Mapping[str, Any]],
]:
    development_rows = [row for item in development for row in item.predictions]
    calibration_rows: list[Mapping[str, Any]] = []
    radii: dict[tuple[str, int, str], tuple[float, float]] = {}
    for model in MODELS:
        for week_end in windows:
            metrics = sorted(
                {
                    row["metric"]
                    for row in development_rows
                    if row["model"] == model
                    and _integer(row["week_end"], "development week") == week_end
                }
            )
            for metric in metrics:
                selected = [
                    row
                    for row in development_rows
                    if row["model"] == model
                    and _integer(row["week_end"], "development week") == week_end
                    and row["metric"] == metric
                ]
                residuals = [
                    _finite(row["absolute_error"], "development absolute_error")
                    for row in selected
                ]
                tolerances = {
                    _finite(row["tolerance"], "development tolerance") for row in selected
                }
                if len(tolerances) != 1:
                    raise TransitionEvaluationDataError(
                        f"tolerance changed for {metric} Weeks 1-{week_end}"
                    )
                tolerance = tolerances.pop()
                rank, radius = _conformal_radius(residuals, NOMINAL_COVERAGE)
                radii[(model, week_end, metric)] = (radius, tolerance)
                calibration_rows.append(
                    {
                        "model": model,
                        "week_end": week_end,
                        "metric": metric,
                        "development_count": len(residuals),
                        "nominal_coverage": NOMINAL_COVERAGE,
                        "finite_sample_rank": rank,
                        "residual_radius": round(radius, 6),
                        "tolerance": round(tolerance, 6),
                        "normalized_radius": round(radius / tolerance, 6),
                    }
                )

    prediction_rows: list[Mapping[str, Any]] = []
    for row in holdout.predictions:
        model = row["model"]
        if model not in MODELS:
            continue
        week_end = _integer(row["week_end"], "holdout week")
        key = (model, week_end, row["metric"])
        if key not in radii:
            raise TransitionEvaluationDataError(f"holdout prediction lacks calibration: {key}")
        radius, _ = radii[key]
        forecast = _finite(row["forecast_value"], "holdout forecast")
        actual = _finite(row["actual_value"], "holdout actual")
        prediction_rows.append(
            {
                "target_season": holdout.target_season,
                "week_end": week_end,
                "team": row["team"],
                "caller_cohort": row["caller_cohort"],
                "metric": row["metric"],
                "model": model,
                "forecast_value": round(forecast, 6),
                "actual_value": round(actual, 6),
                "residual_radius": round(radius, 6),
                "interval_low": round(forecast - radius, 6),
                "interval_high": round(forecast + radius, 6),
                "covered": str(abs(actual - forecast) <= radius).lower(),
            }
        )

    summary_rows: list[Mapping[str, Any]] = []
    cohorts = ("all", "returning_caller", "changed_with_prior_year_anchor", "changed_without_prior_year_anchor")
    tolerance_by_key = {
        (row["model"], int(row["week_end"]), row["metric"]): float(row["tolerance"])
        for row in calibration_rows
    }
    for model in MODELS:
        for week_end in windows:
            for cohort in cohorts:
                selected = [
                    row
                    for row in prediction_rows
                    if row["model"] == model
                    and row["week_end"] == week_end
                    and (cohort == "all" or row["caller_cohort"] == cohort)
                ]
                if not selected:
                    continue
                covered = sum(row["covered"] == "true" for row in selected)
                lower, upper = _wilson(covered, len(selected))
                normalized_radii = [
                    float(row["residual_radius"])
                    / tolerance_by_key[(model, week_end, str(row["metric"]))]
                    for row in selected
                ]
                summary_rows.append(
                    {
                        "target_season": holdout.target_season,
                        "week_end": week_end,
                        "cohort": cohort,
                        "model": model,
                        "comparison_count": len(selected),
                        "covered_count": covered,
                        "coverage_rate": round(covered / len(selected), 6),
                        "wilson_95pct_lower": round(lower, 6),
                        "wilson_95pct_upper": round(upper, 6),
                        "mean_normalized_radius": round(
                            statistics.mean(normalized_radii), 6
                        ),
                    }
                )

    metric_rows: list[Mapping[str, Any]] = []
    for model in MODELS:
        for week_end in windows:
            metrics = sorted(
                {
                    str(row["metric"])
                    for row in prediction_rows
                    if row["model"] == model and row["week_end"] == week_end
                }
            )
            for metric in metrics:
                selected = [
                    row
                    for row in prediction_rows
                    if row["model"] == model
                    and row["week_end"] == week_end
                    and row["metric"] == metric
                ]
                covered = sum(row["covered"] == "true" for row in selected)
                lower, upper = _wilson(covered, len(selected))
                metric_rows.append(
                    {
                        "target_season": holdout.target_season,
                        "week_end": week_end,
                        "model": model,
                        "metric": metric,
                        "comparison_count": len(selected),
                        "covered_count": covered,
                        "coverage_rate": round(covered / len(selected), 6),
                        "wilson_95pct_lower": round(lower, 6),
                        "wilson_95pct_upper": round(upper, 6),
                    }
                )
    return calibration_rows, prediction_rows, summary_rows, metric_rows


def build_transition_evaluation(
    backtests: Iterable[str | Path],
    *,
    development_seasons: Iterable[int] = (2023, 2024),
    holdout_season: int = 2025,
    bootstrap_samples: int = 20_000,
    random_seed: int = 20260903,
) -> TransitionEvaluationResult:
    """Pool fixed-model cohorts and calibrate residual bands before opening holdout."""

    if isinstance(bootstrap_samples, bool) or bootstrap_samples < 1000:
        raise TransitionEvaluationDataError("bootstrap_samples must be at least 1000")
    loaded = tuple(sorted((_load_backtest(path) for path in backtests), key=lambda item: item.target_season))
    seasons = tuple(item.target_season for item in loaded)
    if len(loaded) < 3 or len(set(seasons)) != len(seasons):
        raise TransitionEvaluationDataError("at least three unique target seasons are required")
    development_values = tuple(sorted(set(development_seasons)))
    if not development_values or holdout_season in development_values:
        raise TransitionEvaluationDataError("development seasons must exclude the holdout")
    if set(seasons) != {*development_values, holdout_season}:
        raise TransitionEvaluationDataError(
            "backtests must exactly match the declared development and holdout seasons"
        )
    windows = loaded[0].windows
    if any(item.windows != windows for item in loaded):
        raise TransitionEvaluationDataError("all backtests must use identical windows")
    if any(item.models != loaded[0].models or item.scoring != loaded[0].scoring for item in loaded[1:]):
        raise TransitionEvaluationDataError("model weights and scoring must be identical across seasons")
    development = tuple(item for item in loaded if item.target_season in development_values)
    holdout = next(item for item in loaded if item.target_season == holdout_season)
    paired_rows = _paired_summary(
        loaded,
        windows=windows,
        bootstrap_samples=bootstrap_samples,
        random_seed=random_seed,
    )
    calibration_rows, prediction_rows, coverage_rows, metric_coverage_rows = _coverage(
        development, holdout, windows=windows
    )

    pooled = [row for row in paired_rows if row["scope"] == "pooled_all_seasons"]
    holdout_paired = [
        row
        for row in paired_rows
        if row["scope"] == "single_season" and row["scope_season"] == holdout_season
    ]
    single = [row for row in paired_rows if row["scope"] == "single_season"]
    leave_one_out = [
        row for row in paired_rows if row["scope"] == "leave_one_season_out"
    ]
    every_season_point_improves = all(float(row["mean_paired_delta"]) < 0 for row in single)
    pooled_intervals_below_zero = all(float(row["bootstrap_95pct_upper"]) < 0 for row in pooled)
    holdout_intervals_below_zero = all(
        float(row["bootstrap_95pct_upper"]) < 0 for row in holdout_paired
    )
    all_leave_one_out_intervals_below_zero = all(
        float(row["bootstrap_95pct_upper"]) < 0 for row in leave_one_out
    )
    without_holdout = [
        row for row in leave_one_out if row["scope_season"] == holdout_season
    ]
    promotion_pass = (
        len(seasons) >= 3
        and every_season_point_improves
        and pooled_intervals_below_zero
        and holdout_intervals_below_zero
    )
    caller_coverage = [
        row
        for row in coverage_rows
        if row["cohort"] == "all" and row["model"] == CANDIDATE_MODEL
    ]
    caller_metric_coverage = []
    for week_end in windows:
        selected = [
            row
            for row in metric_coverage_rows
            if row["model"] == CANDIDATE_MODEL and row["week_end"] == week_end
        ]
        weakest = min(selected, key=lambda row: float(row["coverage_rate"]))
        caller_metric_coverage.append(
            {
                "target_season": holdout_season,
                "week_end": week_end,
                "metric_count": len(selected),
                "metrics_at_or_above_nominal": sum(
                    float(row["coverage_rate"]) >= NOMINAL_COVERAGE
                    for row in selected
                ),
                "weakest_metric": weakest["metric"],
                "weakest_metric_coverage": weakest["coverage_rate"],
            }
        )
    evaluation = {
        "status": "three_season_fixed_model_evaluation_with_heldout_coverage",
        "design": {
            "development_seasons": list(development_values),
            "holdout_season": holdout_season,
            "target_windows": [f"Weeks 1-{week}" for week in windows],
            "forecast_weights_retuned": False,
            "metric_tolerances_retuned": False,
            "interval_method": (
                "Per-model, per-metric finite-sample 90% absolute-residual radius "
                "fit on development seasons only and opened once on the holdout."
            ),
            "paired_effect_interval": (
                "Percentile bootstrap clustered by destination team across seasons; "
                "exact for at most seven team clusters, otherwise "
                f"{bootstrap_samples:,} seeded samples."
            ),
        },
        "caller_mean_promotion_gate": {
            "required_target_seasons": 3,
            "observed_target_seasons": len(seasons),
            "every_season_point_estimate_improves_both_windows": every_season_point_improves,
            "pooled_team_season_intervals_below_zero_both_windows": pooled_intervals_below_zero,
            "holdout_team_intervals_below_zero_both_windows": holdout_intervals_below_zero,
            "all_leave_one_season_out_intervals_below_zero": all_leave_one_out_intervals_below_zero,
            "pass": promotion_pass,
            "decision": (
                "promote_fixed_caller_aware_mean_rule_as_historically_supported"
                if promotion_pass
                else "retain_fixed_caller_aware_mean_rule_as_experimental"
            ),
            "robustness_caveat": (
                "The predeclared gate passes, but the development-only 2023-24 "
                "intervals still cross zero; pooled interval significance depends on "
                "the strong untouched 2025 result."
                if any(float(row["bootstrap_95pct_upper"]) >= 0 for row in without_holdout)
                else "The pooled result remains below zero without the holdout season."
            ),
        },
        "heldout_interval_coverage": {
            "nominal": NOMINAL_COVERAGE,
            "caller_aware_all_team_windows": caller_coverage,
            "caller_aware_metric_windows": caller_metric_coverage,
            "decision": (
                "Residual bands have a genuine held-out coverage result, but they are "
                "global metric bands and do not calibrate the current 0-100 evidence scores."
            ),
        },
        "certainty_decision": (
            "Keep broad-system and exact-style 0-100 values as evidence indices. "
            "Historical team-season evidence scores are still needed to model expected "
            "error or interval width conditional on those values."
        ),
        "prospective_freeze_decision": (
            "Do not alter or re-register the already pinned 2026 prospective forecast; "
            "record this as external historical support and score the frozen values as issued."
        ),
    }
    hashes = {
        path: digest for item in loaded for path, digest in item.input_hashes.items()
    }
    return TransitionEvaluationResult(
        target_seasons=seasons,
        development_seasons=development_values,
        holdout_season=holdout_season,
        windows=windows,
        bootstrap_samples=bootstrap_samples,
        random_seed=random_seed,
        input_paths=tuple(item.path for item in loaded),
        input_hashes=hashes,
        paired_summary_rows=tuple(paired_rows),
        calibration_rows=tuple(calibration_rows),
        coverage_prediction_rows=tuple(prediction_rows),
        coverage_summary_rows=tuple(coverage_rows),
        metric_coverage_rows=tuple(metric_coverage_rows),
        evaluation=evaluation,
    )


def _csv_bytes(fields: tuple[str, ...], rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def write_transition_evaluation_snapshot(
    result: TransitionEvaluationResult,
    root: str | Path,
    *,
    created_at: datetime | None = None,
) -> Path:
    """Atomically publish the pooled effects and held-out interval evaluation."""

    created = created_at or datetime.now(timezone.utc)
    if created.tzinfo is None or created.utcoffset() is None:
        raise ValueError("created_at must include a timezone")
    created = created.astimezone(timezone.utc)
    season_label = "-".join(str(season) for season in result.target_seasons)
    parent = Path(root) / "transition_evaluation" / season_label
    destination = parent / created.strftime("%Y%m%dT%H%M%S.%fZ")
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"transition evaluation already exists: {destination}")
    artifacts = {
        "paired_effect_summary.csv": _csv_bytes(
            PAIRED_SUMMARY_FIELDS, result.paired_summary_rows
        ),
        "interval_calibration.csv": _csv_bytes(
            CALIBRATION_FIELDS, result.calibration_rows
        ),
        "holdout_interval_predictions.csv": _csv_bytes(
            COVERAGE_PREDICTION_FIELDS, result.coverage_prediction_rows
        ),
        "interval_coverage_summary.csv": _csv_bytes(
            COVERAGE_SUMMARY_FIELDS, result.coverage_summary_rows
        ),
        "metric_coverage_summary.csv": _csv_bytes(
            METRIC_COVERAGE_FIELDS, result.metric_coverage_rows
        ),
        "evaluation.json": (
            json.dumps(result.evaluation, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "created_at": created.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "seasons": {
            "targets": list(result.target_seasons),
            "development": list(result.development_seasons),
            "holdout": result.holdout_season,
        },
        "windows": list(result.windows),
        "parameters": {
            "nominal_coverage": NOMINAL_COVERAGE,
            "bootstrap_samples": result.bootstrap_samples,
            "random_seed": result.random_seed,
        },
        "input_sha256": dict(sorted(result.input_hashes.items())),
        "artifacts": {
            name: {"bytes": len(raw), "sha256": _sha256(raw)}
            for name, raw in artifacts.items()
        },
        "counts": {
            "paired_summary_rows": len(result.paired_summary_rows),
            "calibration_rows": len(result.calibration_rows),
            "holdout_interval_prediction_rows": len(result.coverage_prediction_rows),
            "coverage_summary_rows": len(result.coverage_summary_rows),
            "metric_coverage_rows": len(result.metric_coverage_rows),
        },
        "evaluation": result.evaluation,
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
