"""Convert validated conditional shares into 2026 high-value opportunity counts.

The primary team event rate is selected by a development/holdout backtest.  It is
multiplied by the existing caller-aware RB-carry or position-target pool, then by
the frozen player conditional share.  The result is still opportunity, not catches,
yards, touchdowns, efficiency, or fantasy points.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .high_value_backtest import METRICS
from .high_value_volume_backtest import (
    BASE_MODEL,
    CALIBRATION_FIELDS,
    COMPARISON_FIELDS,
    EVALUATION_FIELDS,
    MODEL_PRIORS,
    MODEL_VERSION as VOLUME_BACKTEST_MODEL_VERSION,
    PREDICTION_FIELDS,
    calibration_rows as recompute_rate_calibration,
    recommend_volume_models,
    _history_groups,
    _model_rate,
    _training_rates,
)
from .resource_backtest import (
    CALIBRATION_FIELDS as RESOURCE_CALIBRATION_FIELDS,
    COMPARISON_FIELDS as RESOURCE_COMPARISON_FIELDS,
    EVALUATION_FIELDS as RESOURCE_EVALUATION_FIELDS,
    MODEL_PRIOR_GAMES as RESOURCE_MODEL_PRIOR_GAMES,
    MODEL_VERSION as RESOURCE_BACKTEST_MODEL_VERSION,
    PREDICTION_FIELDS as RESOURCE_PREDICTION_FIELDS,
    RESOURCES,
    recommend_resource_models,
    resource_calibration_rows as recompute_resource_calibration,
)


SCHEMA_VERSION = "1.2.0"
MODEL_VERSION = "high-value-event-pool-v0.3.0"
HIGH_VALUE_PRIOR_MODEL_VERSION = "high-value-role-prior-v0.2.0"
MATERIAL_RAW_RATE_MULTIPLE = 1.0

TEAM_POOL_FIELDS = (
    "season", "team", "position", "metric", "base_resource",
    "selected_rate_model", "history_seasons", "training_league_events",
    "training_league_base_opportunities", "training_league_rate",
    "training_team_events", "training_team_base_opportunities",
    "diagnostic_raw_team_rate", "diagnostic_candidate_model",
    "diagnostic_candidate_rate", "diagnostic_candidate_delta_vs_primary",
    "conditional_event_rate_low", "conditional_event_rate_median",
    "conditional_event_rate_high", "conformal_rate_radius",
    "heldout_rate_coverage", "base_resource_reference_model",
    "base_resource_reference_gate_passed", "resource_error_radius_per_game",
    "resource_nominal_coverage", "resource_holdout_coverage",
    "resource_interval_status", "base_resource_pool_per_game_low",
    "base_resource_pool_per_game", "base_resource_pool_per_game_high",
    "base_resource_pool_full_season_low", "base_resource_pool_full_season",
    "base_resource_pool_full_season_high", "event_pool_per_game_low",
    "event_pool_per_game_median", "event_pool_per_game_high",
    "event_pool_full_season_low", "event_pool_full_season_median",
    "event_pool_full_season_high", "interval_scope", "model_status",
)
PLAYER_FIELDS = (
    "season", "team", "position", "metric", "base_resource", "gsis_id",
    "player_name", "current_status", "roster_status", "current_active",
    "share_p12_active_scenario", "share_p24_active_scenario",
    "share_p48_active_scenario", "share_sensitivity_low_active_scenario",
    "share_sensitivity_high_active_scenario", "team_event_pool_per_game_median",
    "current_active_events_per_game_low", "current_active_events_per_game_median",
    "current_active_events_per_game_high",
    "availability_adjusted_season_expected_events",
    "season_marginal_scenario_envelope_low",
    "season_marginal_scenario_envelope_high", "role_evidence_score_v0",
    "role_evidence_label", "metric_history_support",
    "historical_metric_base_opportunities", "requires_current_role_review",
    "current_role_review_issues", "ffc_source_player_id", "ffc_adp",
    "projection_scope", "model_status",
)
WEEKLY_FIELDS = (
    "season", "week", "gameday", "team", "opponent", "home_away",
    "scheduled_game", "position", "metric", "base_resource", "gsis_id",
    "player_name", "current_status", "active_probability_median",
    "team_event_pool_per_game_low", "team_event_pool_per_game_median",
    "team_event_pool_per_game_high", "expected_share_mean", "share_p10",
    "share_p50", "share_p90", "expected_event_count_mean",
    "event_count_p10_share_only", "event_count_p50_share_only",
    "event_count_p90_share_only", "combined_marginal_scenario_low",
    "combined_marginal_scenario_high", "ffc_source_player_id", "ffc_adp",
    "simulation_draws", "interval_scope", "model_status",
)
RECONCILIATION_FIELDS = (
    "season", "week", "gameday", "team", "opponent", "home_away",
    "scheduled_game", "position", "metric", "base_resource",
    "team_event_pool_target", "expected_player_event_sum",
    "unallocated_draw_rate", "expected_unallocated_events",
    "reconciled_event_sum", "reconciliation_error",
)
REVIEW_FIELDS = (
    "season", "team", "position", "metric", "issue",
    "training_team_base_opportunities", "primary_rate", "diagnostic_raw_rate",
    "conformal_rate_radius", "details",
)


class HighValueVolumeDataError(ValueError):
    """Raised when current high-value event counts cannot be built safely."""


@dataclass(frozen=True)
class HighValueVolumeResult:
    season: int
    player_roles_path: Path
    high_value_history_path: Path
    high_value_priors_path: Path
    volume_backtest_path: Path
    resource_backtest_path: Path
    input_hashes: Mapping[str, str]
    supported_metrics: tuple[str, ...]
    history_lookback: int
    team_pool_rows: tuple[Mapping[str, Any], ...]
    player_rows: tuple[Mapping[str, Any], ...]
    weekly_rows: tuple[Mapping[str, Any], ...]
    reconciliation_rows: tuple[Mapping[str, Any], ...]
    source_review: tuple[Mapping[str, Any], ...]
    backtest_recommendation: Mapping[str, Any]
    resource_backtest_recommendation: Mapping[str, Any]


def _read_manifest(root: Path) -> tuple[bytes, Mapping[str, Any]]:
    path = root / "manifest.json"
    if not path.is_file():
        raise HighValueVolumeDataError(f"missing input manifest: {path}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HighValueVolumeDataError(
            f"input manifest is not valid JSON: {path}"
        ) from error
    if not isinstance(value, dict):
        raise HighValueVolumeDataError(f"input manifest is not an object: {path}")
    return raw, value


def _verified_csv(
    root: Path,
    manifest: Mapping[str, Any],
    filename: str,
    required: set[str],
    *,
    allow_empty: bool = False,
) -> tuple[bytes, list[dict[str, str]]]:
    metadata = (manifest.get("artifacts") or {}).get(filename)
    if not isinstance(metadata, dict) or not metadata.get("sha256"):
        raise HighValueVolumeDataError(
            f"manifest does not describe {filename}: {root}"
        )
    path = root / filename
    if not path.is_file():
        raise HighValueVolumeDataError(f"input does not exist: {path}")
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != metadata["sha256"]:
        raise HighValueVolumeDataError(
            f"input hash mismatch for {path}: expected {metadata['sha256']}, got {actual}"
        )
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        fields = set(reader.fieldnames or ())
        rows = list(reader)
    except UnicodeDecodeError as error:
        raise HighValueVolumeDataError(f"input is not UTF-8 CSV: {path}") from error
    missing = required - fields
    if missing or (not rows and not allow_empty):
        raise HighValueVolumeDataError(
            f"{path} is empty or missing fields {sorted(missing)}"
        )
    return raw, rows


def _number(value: Any, context: str, *, allow_blank: bool = False) -> float:
    if allow_blank and (value is None or str(value).strip() == ""):
        return 0.0
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise HighValueVolumeDataError(f"{context} must be numeric") from error
    if not math.isfinite(result) or result < 0:
        raise HighValueVolumeDataError(f"{context} must be finite and nonnegative")
    return result


def _integer(value: Any, context: str) -> int:
    result = _number(value, context)
    if not result.is_integer():
        raise HighValueVolumeDataError(f"{context} must be an integer")
    return int(result)


def _string_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    return [{key: str(value) for key, value in row.items()} for row in rows]


def _validate_volume_backtest(
    manifest: Mapping[str, Any],
    predictions: list[dict[str, str]],
    evaluations: list[dict[str, str]],
    comparisons: list[dict[str, str]],
    calibration: list[dict[str, str]],
) -> tuple[tuple[str, ...], Mapping[str, Any]]:
    if manifest.get("model_version") != VOLUME_BACKTEST_MODEL_VERSION:
        raise HighValueVolumeDataError("unsupported team-volume backtest model version")
    parameters = manifest.get("parameters") or {}
    if parameters.get("model_prior_opportunities") != dict(MODEL_PRIORS):
        raise HighValueVolumeDataError("volume backtest model priors changed")
    supported = tuple(manifest.get("supported_metrics") or ())
    if not supported:
        raise HighValueVolumeDataError("volume backtest has no supported metrics")
    recomputed = recommend_volume_models(evaluations, comparisons, supported)
    if recomputed != manifest.get("recommendation"):
        raise HighValueVolumeDataError(
            "volume backtest recommendation does not reproduce from scored artifacts"
        )
    development = tuple(int(value) for value in manifest.get("development_seasons") or ())
    holdout = int(manifest.get("holdout_season"))
    expected_calibration = recompute_rate_calibration(
        predictions,
        recomputed,
        development_seasons=development,
        holdout_season=holdout,
        supported_metrics=supported,
    )
    if _string_rows(expected_calibration) != _string_rows(calibration):
        raise HighValueVolumeDataError(
            "volume backtest calibration does not reproduce from predictions"
        )
    return supported, recomputed


def _validate_resource_backtest(
    manifest: Mapping[str, Any],
    predictions: list[dict[str, str]],
    evaluations: list[dict[str, str]],
    comparisons: list[dict[str, str]],
    calibration: list[dict[str, str]],
) -> tuple[Mapping[str, Any], Mapping[str, Mapping[str, str]]]:
    """Reproduce the frozen resource decision and uncertainty rows fail-closed."""

    if manifest.get("model_version") != RESOURCE_BACKTEST_MODEL_VERSION:
        raise HighValueVolumeDataError("unsupported resource backtest model version")
    parameters = manifest.get("parameters") or {}
    if parameters.get("model_prior_games") != dict(RESOURCE_MODEL_PRIOR_GAMES):
        raise HighValueVolumeDataError("resource backtest model priors changed")
    if tuple(manifest.get("resources") or ()) != tuple(RESOURCES):
        raise HighValueVolumeDataError("resource backtest coverage changed")
    recomputed = recommend_resource_models(evaluations, comparisons)
    if recomputed != manifest.get("recommendation"):
        raise HighValueVolumeDataError(
            "resource backtest recommendation does not reproduce from scored artifacts"
        )
    development = tuple(int(value) for value in manifest.get("development_seasons") or ())
    holdout = int(manifest.get("holdout_season"))
    expected_calibration = recompute_resource_calibration(
        predictions,
        recomputed,
        development_seasons=development,
        holdout_season=holdout,
    )
    if _string_rows(expected_calibration) != _string_rows(calibration):
        raise HighValueVolumeDataError(
            "resource backtest calibration does not reproduce from predictions"
        )
    by_resource = {row["resource"]: row for row in calibration}
    if set(by_resource) != set(RESOURCES):
        raise HighValueVolumeDataError("resource calibration coverage mismatch")
    return recomputed, by_resource


def build_high_value_volumes(
    player_roles: str | Path,
    high_value_history: str | Path,
    high_value_priors: str | Path,
    high_value_volume_backtest: str | Path,
    resource_backtest: str | Path,
) -> HighValueVolumeResult:
    """Build team and player event-count priors from independently tested layers."""

    roles_root = Path(player_roles)
    history_root = Path(high_value_history)
    priors_root = Path(high_value_priors)
    backtest_root = Path(high_value_volume_backtest)
    resource_backtest_root = Path(resource_backtest)
    roles_manifest_raw, roles_manifest = _read_manifest(roles_root)
    history_manifest_raw, history_manifest = _read_manifest(history_root)
    priors_manifest_raw, priors_manifest = _read_manifest(priors_root)
    backtest_manifest_raw, backtest_manifest = _read_manifest(backtest_root)
    resource_manifest_raw, resource_manifest = _read_manifest(resource_backtest_root)

    role_pool_raw, role_pool_rows = _verified_csv(
        roles_root,
        roles_manifest,
        "team_reconciliation.csv",
        {"season", "team", "position", "resource", "team_pool_per_game",
         "team_pool_full_season", "reconciliation_error", "model_status"},
    )
    history_required = {"season", "week", "team", "position"}
    history_required.update(spec.high_value_field for spec in METRICS.values())
    history_required.update(spec.base_field for spec in METRICS.values())
    history_raw, history_rows = _verified_csv(
        history_root,
        history_manifest,
        "team_week_high_value.csv",
        history_required,
    )
    prior_raw, prior_rows = _verified_csv(
        priors_root,
        priors_manifest,
        "player_high_value_priors.csv",
        {"season", "team", "position", "metric", "base_resource", "gsis_id",
         "player_name", "current_status", "roster_status", "current_active",
         "share_p12", "share_p24", "share_p48", "active_conditional_share_p24",
         "role_evidence_score_v0", "role_evidence_label", "history_support",
         "historical_base_opportunities", "ffc_source_player_id", "ffc_adp"},
    )
    prior_review_raw, prior_review_rows = _verified_csv(
        priors_root,
        priors_manifest,
        "source_review.csv",
        {"season", "team", "position", "metric", "gsis_id", "player_name",
         "issue", "details"},
        allow_empty=True,
    )
    weekly_raw, weekly_input_rows = _verified_csv(
        priors_root,
        priors_manifest,
        "weekly_high_value_roles.csv",
        {"season", "week", "gameday", "team", "opponent", "home_away",
         "scheduled_game", "position", "metric", "base_resource", "gsis_id",
         "player_name", "current_status", "active_probability_median",
         "expected_share_mean", "share_p10", "share_p50", "share_p90",
         "ffc_source_player_id", "ffc_adp", "simulation_draws"},
    )
    weekly_recon_raw, weekly_input_reconciliation = _verified_csv(
        priors_root,
        priors_manifest,
        "weekly_reconciliation.csv",
        {"season", "week", "gameday", "team", "opponent", "home_away",
         "scheduled_game", "position", "metric", "base_resource",
         "expected_player_share_sum", "unallocated_draw_rate",
         "reconciled_share_sum", "reconciliation_error"},
    )
    prediction_raw, prediction_rows = _verified_csv(
        backtest_root, backtest_manifest, "predictions.csv", set(PREDICTION_FIELDS)
    )
    evaluation_raw, evaluation_rows = _verified_csv(
        backtest_root, backtest_manifest, "model_evaluation.csv", set(EVALUATION_FIELDS)
    )
    comparison_raw, comparison_rows = _verified_csv(
        backtest_root, backtest_manifest, "paired_comparisons.csv", set(COMPARISON_FIELDS)
    )
    calibration_raw, calibration_input = _verified_csv(
        backtest_root, backtest_manifest, "rate_calibration.csv", set(CALIBRATION_FIELDS)
    )
    supported, recommendation = _validate_volume_backtest(
        backtest_manifest,
        prediction_rows,
        evaluation_rows,
        comparison_rows,
        calibration_input,
    )
    resource_prediction_raw, resource_prediction_rows = _verified_csv(
        resource_backtest_root,
        resource_manifest,
        "predictions.csv",
        set(RESOURCE_PREDICTION_FIELDS),
    )
    resource_evaluation_raw, resource_evaluation_rows = _verified_csv(
        resource_backtest_root,
        resource_manifest,
        "model_evaluation.csv",
        set(RESOURCE_EVALUATION_FIELDS),
    )
    resource_comparison_raw, resource_comparison_rows = _verified_csv(
        resource_backtest_root,
        resource_manifest,
        "paired_comparisons.csv",
        set(RESOURCE_COMPARISON_FIELDS),
    )
    resource_calibration_raw, resource_calibration_input = _verified_csv(
        resource_backtest_root,
        resource_manifest,
        "resource_calibration.csv",
        set(RESOURCE_CALIBRATION_FIELDS),
    )
    resource_recommendation, resource_calibration_by_resource = (
        _validate_resource_backtest(
            resource_manifest,
            resource_prediction_rows,
            resource_evaluation_rows,
            resource_comparison_rows,
            resource_calibration_input,
        )
    )
    if priors_manifest.get("model_version") != HIGH_VALUE_PRIOR_MODEL_VERSION:
        raise HighValueVolumeDataError("unsupported high-value prior model version")
    if tuple(priors_manifest.get("supported_metrics") or ()) != supported:
        raise HighValueVolumeDataError(
            "player-share and team-volume supported metrics do not match"
        )
    prior_links = ((priors_manifest.get("inputs") or {}).get("sha256") or {})
    volume_links = ((backtest_manifest.get("inputs") or {}).get("sha256") or {})
    required_links = {
        "player role manifest": (
            prior_links.get("player_roles_manifest.json"),
            hashlib.sha256(roles_manifest_raw).hexdigest(),
        ),
        "player-share history manifest": (
            prior_links.get("high_value_history_manifest.json"),
            hashlib.sha256(history_manifest_raw).hexdigest(),
        ),
        "team-rate history manifest": (
            volume_links.get("high_value_history_manifest.json"),
            hashlib.sha256(history_manifest_raw).hexdigest(),
        ),
        "shared player-share backtest manifest": (
            volume_links.get("high_value_role_backtest_manifest.json"),
            prior_links.get("high_value_backtest_manifest.json"),
        ),
    }
    for label, (observed, expected) in required_links.items():
        if not observed or not expected or observed != expected:
            raise HighValueVolumeDataError(
                f"input lineage mismatch for {label}: {observed!r} != {expected!r}"
            )
    seasons = {_integer(row["season"], "role pool season") for row in role_pool_rows}
    seasons.update(_integer(row["season"], "player prior season") for row in prior_rows)
    seasons.update(_integer(row["season"], "weekly prior season") for row in weekly_input_rows)
    if len(seasons) != 1:
        raise HighValueVolumeDataError(f"current inputs mix seasons {sorted(seasons)}")
    season = next(iter(seasons))
    if int(priors_manifest.get("season")) != season:
        raise HighValueVolumeDataError("high-value prior manifest season mismatch")

    prior_review_issues: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in prior_review_rows:
        if _integer(row["season"], "high-value prior review season") != season:
            raise HighValueVolumeDataError("high-value prior review season mismatch")
        if row["gsis_id"]:
            prior_review_issues[(row["team"], row["metric"], row["gsis_id"])].add(
                row["issue"]
            )

    history_lookback = int((backtest_manifest.get("parameters") or {})["history_lookback"])
    groups = _history_groups(history_rows, supported)
    calibration_by_metric = {row["metric"]: row for row in calibration_input}
    if set(calibration_by_metric) != set(supported):
        raise HighValueVolumeDataError("rate calibration metric coverage mismatch")

    pools: dict[tuple[str, str], Mapping[str, str]] = {}
    for row in role_pool_rows:
        if abs(_number(row["reconciliation_error"], "role reconciliation")) > 1e-9:
            raise HighValueVolumeDataError("input team resource pool does not reconcile")
        key = row["team"], row["resource"]
        if key in pools:
            raise HighValueVolumeDataError(f"duplicate current team resource pool {key}")
        pools[key] = row

    team_rows: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    team_lookup: dict[tuple[str, str], dict[str, Any]] = {}
    current_teams = sorted({row["team"] for row in prior_rows})
    for metric in supported:
        spec = METRICS[metric]
        resource_calibration = resource_calibration_by_resource.get(spec.base_resource)
        if resource_calibration is None:
            raise HighValueVolumeDataError(
                f"no resource calibration for {spec.base_resource}"
            )
        resource_decision = resource_recommendation["resources"][spec.base_resource]
        if (
            resource_calibration["model"]
            != resource_decision["selected_reference_model"]
        ):
            raise HighValueVolumeDataError(
                f"{spec.base_resource} resource calibration model mismatch"
            )
        resource_radius = _number(
            resource_calibration["conformal_absolute_error_per_game_radius"],
            f"{spec.base_resource} resource radius",
        )
        resource_nominal_coverage = _number(
            resource_calibration["nominal_coverage"],
            f"{spec.base_resource} nominal coverage",
        )
        resource_holdout_coverage = _number(
            resource_calibration["holdout_coverage"],
            f"{spec.base_resource} holdout coverage",
        )
        if resource_nominal_coverage > 1 or resource_holdout_coverage > 1:
            raise HighValueVolumeDataError(
                f"{spec.base_resource} resource coverage must be at most one"
            )
        resource_interval_status = (
            "provisional_transfer_holdout_below_nominal"
            if resource_holdout_coverage + 1e-12 < resource_nominal_coverage
            else "provisional_transfer_holdout_met_or_exceeded_nominal"
        )
        training, league_events, league_base, team_history = _training_rates(
            groups,
            target_season=season,
            metric=metric,
            history_lookback=history_lookback,
        )
        league_rate = league_events / league_base
        selected_model = recommendation["metrics"][metric]["selected_model"]
        diagnostic_model = recommendation["metrics"][metric]["development_candidate"]
        calibration = calibration_by_metric[metric]
        if calibration["model"] != selected_model:
            raise HighValueVolumeDataError(f"{metric} calibration model mismatch")
        radius = _number(
            calibration["conformal_absolute_rate_radius"], f"{metric} rate radius"
        )
        heldout_coverage = _number(
            calibration["holdout_coverage"], f"{metric} holdout coverage"
        )
        for team in current_teams:
            role_pool = pools.get((team, spec.base_resource))
            if role_pool is None:
                raise HighValueVolumeDataError(
                    f"missing {team} {spec.base_resource} current resource pool"
                )
            team_events, team_base = team_history.get(team, (0.0, 0.0))
            primary_rate = _model_rate(
                selected_model,
                league_rate=league_rate,
                team_events=team_events,
                team_base=team_base,
            )
            diagnostic_rate = _model_rate(
                diagnostic_model,
                league_rate=league_rate,
                team_events=team_events,
                team_base=team_base,
            )
            raw_rate = team_events / team_base if team_base > 0 else league_rate
            rate_low = max(0.0, primary_rate - radius)
            rate_high = min(1.0, primary_rate + radius)
            pool_per_game = _number(
                role_pool["team_pool_per_game"], f"{team} base pool per game"
            )
            pool_full = _number(
                role_pool["team_pool_full_season"], f"{team} base pool season"
            )
            if pool_per_game <= 0:
                if pool_full > 0:
                    raise HighValueVolumeDataError(
                        f"{team} base pool has a zero per-game mean and positive season total"
                    )
                season_games = 0.0
            else:
                season_games = pool_full / pool_per_game
            resource_low_per_game = max(0.0, pool_per_game - resource_radius)
            resource_high_per_game = pool_per_game + resource_radius
            resource_low_full = resource_low_per_game * season_games
            resource_high_full = resource_high_per_game * season_games
            values = {
                "season": season,
                "team": team,
                "position": spec.position,
                "metric": metric,
                "base_resource": spec.base_resource,
                "selected_rate_model": selected_model,
                "history_seasons": "|".join(map(str, training)),
                "training_league_events": f"{league_events:.6f}",
                "training_league_base_opportunities": f"{league_base:.6f}",
                "training_league_rate": f"{league_rate:.9f}",
                "training_team_events": f"{team_events:.6f}",
                "training_team_base_opportunities": f"{team_base:.6f}",
                "diagnostic_raw_team_rate": f"{raw_rate:.9f}",
                "diagnostic_candidate_model": diagnostic_model,
                "diagnostic_candidate_rate": f"{diagnostic_rate:.9f}",
                "diagnostic_candidate_delta_vs_primary": f"{diagnostic_rate - primary_rate:.9f}",
                "conditional_event_rate_low": f"{rate_low:.9f}",
                "conditional_event_rate_median": f"{primary_rate:.9f}",
                "conditional_event_rate_high": f"{rate_high:.9f}",
                "conformal_rate_radius": f"{radius:.9f}",
                "heldout_rate_coverage": f"{heldout_coverage:.6f}",
                "base_resource_reference_model": resource_calibration["model"],
                "base_resource_reference_gate_passed": str(
                    bool(resource_decision["reference_gate_passed"])
                ).lower(),
                "resource_error_radius_per_game": f"{resource_radius:.9f}",
                "resource_nominal_coverage": f"{resource_nominal_coverage:.6f}",
                "resource_holdout_coverage": f"{resource_holdout_coverage:.6f}",
                "resource_interval_status": resource_interval_status,
                "base_resource_pool_per_game_low": f"{resource_low_per_game:.6f}",
                "base_resource_pool_per_game": f"{pool_per_game:.6f}",
                "base_resource_pool_per_game_high": f"{resource_high_per_game:.6f}",
                "base_resource_pool_full_season_low": f"{resource_low_full:.6f}",
                "base_resource_pool_full_season": f"{pool_full:.6f}",
                "base_resource_pool_full_season_high": f"{resource_high_full:.6f}",
                "event_pool_per_game_low": f"{resource_low_per_game * rate_low:.6f}",
                "event_pool_per_game_median": f"{pool_per_game * primary_rate:.6f}",
                "event_pool_per_game_high": f"{resource_high_per_game * rate_high:.6f}",
                "event_pool_full_season_low": f"{resource_low_full * rate_low:.6f}",
                "event_pool_full_season_median": f"{pool_full * primary_rate:.6f}",
                "event_pool_full_season_high": f"{resource_high_full * rate_high:.6f}",
                "interval_scope": "outer-product scenario envelope from a provisionally transferred resource-error radius and a separately calibrated conditional-rate radius; not joint coverage",
                "model_status": "caller_aware_mean_with_provisional_resource_and_rate_envelope_not_fantasy_projection",
            }
            team_rows.append(values)
            team_lookup[(team, metric)] = values
            if team_base > 0 and abs(raw_rate - primary_rate) >= (
                MATERIAL_RAW_RATE_MULTIPLE * radius
            ):
                review.append({
                    "season": season,
                    "team": team,
                    "position": spec.position,
                    "metric": metric,
                    "issue": "raw_team_history_outside_rate_calibration_radius",
                    "training_team_base_opportunities": f"{team_base:.6f}",
                    "primary_rate": f"{primary_rate:.9f}",
                    "diagnostic_raw_rate": f"{raw_rate:.9f}",
                    "conformal_rate_radius": f"{radius:.9f}",
                    "details": "research current caller and team context; do not override the holdout-selected pooled rate without new validation",
                })

    active_share_totals: dict[tuple[str, str, str], float] = defaultdict(float)
    for row in prior_rows:
        if row["current_active"] == "true":
            for field in ("share_p12", "share_p24", "share_p48"):
                active_share_totals[(row["team"], row["metric"], field)] += _number(
                    row[field], f"{row['player_name']} {field}"
                )

    input_recon_lookup = {
        (
            _integer(row["season"], "input reconciliation season"),
            _integer(row["week"], "input reconciliation week"),
            row["team"],
            row["metric"],
        ): row
        for row in weekly_input_reconciliation
    }
    raw_weekly_share_sums: dict[tuple[int, int, str, str], float] = defaultdict(float)
    for row in weekly_input_rows:
        raw_weekly_share_sums[(
            _integer(row["season"], "weekly share season"),
            _integer(row["week"], "weekly share week"),
            row["team"],
            row["metric"],
        )] += _number(row["expected_share_mean"], "weekly raw mean share")

    weekly_rows: list[dict[str, Any]] = []
    season_expected: dict[tuple[str, str, str], float] = defaultdict(float)
    season_low: dict[tuple[str, str, str], float] = defaultdict(float)
    season_high: dict[tuple[str, str, str], float] = defaultdict(float)
    weekly_group_sum: dict[tuple[int, int, str, str], float] = defaultdict(float)
    for row in weekly_input_rows:
        week = _integer(row["week"], "weekly event week")
        key = row["team"], row["metric"]
        pool = team_lookup.get(key)
        if pool is None:
            raise HighValueVolumeDataError(f"weekly row lacks team event pool {key}")
        scheduled = row["scheduled_game"] == "true"
        pool_low = float(pool["event_pool_per_game_low"]) if scheduled else 0.0
        pool_median = float(pool["event_pool_per_game_median"]) if scheduled else 0.0
        pool_high = float(pool["event_pool_per_game_high"]) if scheduled else 0.0
        group_key = season, week, row["team"], row["metric"]
        source_reconciliation = input_recon_lookup.get(group_key)
        if source_reconciliation is None:
            raise HighValueVolumeDataError(
                f"weekly row lacks input reconciliation {group_key}"
            )
        raw_mean_share = _number(row["expected_share_mean"], "weekly mean share")
        reported_mean_sum = _number(
            source_reconciliation["expected_player_share_sum"],
            "reported weekly player share sum",
        )
        raw_mean_sum = raw_weekly_share_sums[group_key]
        mean_share = (
            raw_mean_share * reported_mean_sum / raw_mean_sum
            if raw_mean_sum > 0 else 0.0
        )
        share_p10 = _number(row["share_p10"], "weekly p10 share")
        share_p50 = _number(row["share_p50"], "weekly p50 share")
        share_p90 = _number(row["share_p90"], "weekly p90 share")
        expected = pool_median * mean_share
        combined_low = pool_low * share_p10
        combined_high = pool_high * share_p90
        player_key = row["team"], row["metric"], row["gsis_id"]
        season_expected[player_key] += expected
        season_low[player_key] += combined_low
        season_high[player_key] += combined_high
        weekly_group_sum[group_key] += expected
        weekly_rows.append({
            "season": season,
            "week": week,
            "gameday": row["gameday"],
            "team": row["team"],
            "opponent": row["opponent"],
            "home_away": row["home_away"],
            "scheduled_game": row["scheduled_game"],
            "position": row["position"],
            "metric": row["metric"],
            "base_resource": row["base_resource"],
            "gsis_id": row["gsis_id"],
            "player_name": row["player_name"],
            "current_status": row["current_status"],
            "active_probability_median": row["active_probability_median"],
            "team_event_pool_per_game_low": f"{pool_low:.6f}",
            "team_event_pool_per_game_median": f"{pool_median:.6f}",
            "team_event_pool_per_game_high": f"{pool_high:.6f}",
            "expected_share_mean": f"{mean_share:.9f}",
            "share_p10": f"{share_p10:.9f}",
            "share_p50": f"{share_p50:.9f}",
            "share_p90": f"{share_p90:.9f}",
            "expected_event_count_mean": f"{expected:.9f}",
            "event_count_p10_share_only": f"{pool_median * share_p10:.9f}",
            "event_count_p50_share_only": f"{pool_median * share_p50:.9f}",
            "event_count_p90_share_only": f"{pool_median * share_p90:.9f}",
            "combined_marginal_scenario_low": f"{combined_low:.9f}",
            "combined_marginal_scenario_high": f"{combined_high:.9f}",
            "ffc_source_player_id": row["ffc_source_player_id"],
            "ffc_adp": row["ffc_adp"],
            "simulation_draws": row["simulation_draws"],
            "interval_scope": "weekly marginal availability-share quantiles x provisional resource-error envelope x separately calibrated team-rate band; not a joint interval",
            "model_status": "availability_adjusted_high_value_opportunity_not_fantasy_projection",
        })

    reconciliation_rows: list[dict[str, Any]] = []
    for key, source in sorted(input_recon_lookup.items()):
        row_season, week, team, metric = key
        if row_season != season:
            raise HighValueVolumeDataError("weekly reconciliation season mismatch")
        pool = team_lookup.get((team, metric))
        if pool is None:
            raise HighValueVolumeDataError(f"reconciliation lacks team pool {(team, metric)}")
        expected_share = _number(
            source["expected_player_share_sum"], "expected player share sum"
        )
        unallocated_rate = _number(
            source["unallocated_draw_rate"], "unallocated draw rate"
        )
        source_reconciled = _number(source["reconciled_share_sum"], "share reconciliation")
        source_error = _number(source["reconciliation_error"], "share reconciliation error")
        scheduled = source["scheduled_game"] == "true"
        target = float(pool["event_pool_per_game_median"]) if scheduled else 0.0
        player_sum = weekly_group_sum.get(key, 0.0)
        if abs(player_sum - target * expected_share) > 1e-6:
            raise HighValueVolumeDataError(f"weekly player share mismatch for {key}")
        if source_error > 1e-9 or abs(source_reconciled - (1.0 if scheduled else 0.0)) > 1e-6:
            raise HighValueVolumeDataError(f"input weekly shares do not reconcile for {key}")
        reported_unallocated = target * unallocated_rate
        # Preserve the explicit bucket as the exact complement of the serialized
        # player means.  The input draw rate is rounded to nine decimals, so using
        # it directly would manufacture a tiny reconciliation residual.
        unallocated = max(0.0, target - player_sum)
        if abs(unallocated - reported_unallocated) > 1e-6:
            raise HighValueVolumeDataError(
                f"weekly unallocated bucket disagrees with input draw rate for {key}"
            )
        reconciled = player_sum + unallocated
        error = abs(reconciled - target)
        if error > 1e-6:
            raise HighValueVolumeDataError(f"weekly event pool does not reconcile for {key}")
        reconciliation_rows.append({
            "season": season,
            "week": week,
            "gameday": source["gameday"],
            "team": team,
            "opponent": source["opponent"],
            "home_away": source["home_away"],
            "scheduled_game": source["scheduled_game"],
            "position": source["position"],
            "metric": metric,
            "base_resource": source["base_resource"],
            "team_event_pool_target": f"{target:.9f}",
            "expected_player_event_sum": f"{player_sum:.9f}",
            "unallocated_draw_rate": f"{unallocated_rate:.9f}",
            "expected_unallocated_events": f"{unallocated:.9f}",
            "reconciled_event_sum": f"{reconciled:.9f}",
            "reconciliation_error": f"{error:.12f}",
        })

    scheduled_counts: dict[tuple[str, str], int] = defaultdict(int)
    for row in reconciliation_rows:
        if row["scheduled_game"] == "true":
            scheduled_counts[(row["team"], row["metric"])] += 1
    for key, pool in team_lookup.items():
        expected_full = float(pool["event_pool_per_game_median"]) * scheduled_counts[key]
        # The upstream full-season resource pool is intentionally serialized to
        # three decimals, while its per-game value keeps six.  Allow only that
        # bounded presentation-rounding difference.
        if abs(expected_full - float(pool["event_pool_full_season_median"])) > 1e-3:
            raise HighValueVolumeDataError(
                f"schedule and full-season event pools disagree for {key}"
            )

    player_rows: list[dict[str, Any]] = []
    for row in prior_rows:
        key = row["team"], row["metric"]
        pool = team_lookup.get(key)
        if pool is None:
            raise HighValueVolumeDataError(f"player row lacks team event pool {key}")
        active = row["current_active"] == "true"
        shares: dict[str, float] = {}
        for field in ("share_p12", "share_p24", "share_p48"):
            denominator = active_share_totals[(row["team"], row["metric"], field)]
            shares[field] = (
                _number(row[field], f"{row['player_name']} {field}") / denominator
                if active and denominator > 0 else 0.0
            )
        active_p24 = _number(
            row["active_conditional_share_p24"],
            f"{row['player_name']} active p24 share",
            allow_blank=True,
        )
        if abs(active_p24 - shares["share_p24"]) > 2e-6:
            raise HighValueVolumeDataError(
                f"active p24 share does not reproduce for {row['player_name']} {key}"
            )
        share_low = min(shares.values())
        share_high = max(shares.values())
        player_key = row["team"], row["metric"], row["gsis_id"]
        player_review_issues = sorted(prior_review_issues.get(player_key, set()))
        player_rows.append({
            "season": season,
            "team": row["team"],
            "position": row["position"],
            "metric": row["metric"],
            "base_resource": row["base_resource"],
            "gsis_id": row["gsis_id"],
            "player_name": row["player_name"],
            "current_status": row["current_status"],
            "roster_status": row["roster_status"],
            "current_active": row["current_active"],
            "share_p12_active_scenario": f"{shares['share_p12']:.9f}",
            "share_p24_active_scenario": f"{shares['share_p24']:.9f}",
            "share_p48_active_scenario": f"{shares['share_p48']:.9f}",
            "share_sensitivity_low_active_scenario": f"{share_low:.9f}",
            "share_sensitivity_high_active_scenario": f"{share_high:.9f}",
            "team_event_pool_per_game_median": pool["event_pool_per_game_median"],
            "current_active_events_per_game_low": f"{float(pool['event_pool_per_game_low']) * share_low:.9f}",
            "current_active_events_per_game_median": f"{float(pool['event_pool_per_game_median']) * active_p24:.9f}",
            "current_active_events_per_game_high": f"{float(pool['event_pool_per_game_high']) * share_high:.9f}",
            "availability_adjusted_season_expected_events": f"{season_expected[player_key]:.6f}",
            "season_marginal_scenario_envelope_low": f"{season_low[player_key]:.6f}",
            "season_marginal_scenario_envelope_high": f"{season_high[player_key]:.6f}",
            "role_evidence_score_v0": row["role_evidence_score_v0"],
            "role_evidence_label": row["role_evidence_label"],
            "metric_history_support": row["history_support"],
            "historical_metric_base_opportunities": row["historical_base_opportunities"],
            "requires_current_role_review": str(bool(player_review_issues)).lower(),
            "current_role_review_issues": "|".join(player_review_issues),
            "ffc_source_player_id": row["ffc_source_player_id"],
            "ffc_adp": row["ffc_adp"],
            "projection_scope": "named high-value opportunities only; envelope combines marginal availability/share, provisional resource, and conditional-rate sensitivities and is not a calibrated joint interval",
            "model_status": "bottom_up_opportunity_count_not_efficiency_touchdowns_or_fantasy_points",
        })

    return HighValueVolumeResult(
        season=season,
        player_roles_path=roles_root,
        high_value_history_path=history_root,
        high_value_priors_path=priors_root,
        volume_backtest_path=backtest_root,
        resource_backtest_path=resource_backtest_root,
        input_hashes={
            "player_roles_manifest.json": hashlib.sha256(roles_manifest_raw).hexdigest(),
            "team_reconciliation.csv": hashlib.sha256(role_pool_raw).hexdigest(),
            "high_value_history_manifest.json": hashlib.sha256(history_manifest_raw).hexdigest(),
            "team_week_high_value.csv": hashlib.sha256(history_raw).hexdigest(),
            "high_value_priors_manifest.json": hashlib.sha256(priors_manifest_raw).hexdigest(),
            "player_high_value_priors.csv": hashlib.sha256(prior_raw).hexdigest(),
            "high_value_prior_source_review.csv": hashlib.sha256(prior_review_raw).hexdigest(),
            "weekly_high_value_roles.csv": hashlib.sha256(weekly_raw).hexdigest(),
            "weekly_high_value_reconciliation.csv": hashlib.sha256(weekly_recon_raw).hexdigest(),
            "high_value_volume_backtest_manifest.json": hashlib.sha256(backtest_manifest_raw).hexdigest(),
            "volume_predictions.csv": hashlib.sha256(prediction_raw).hexdigest(),
            "volume_model_evaluation.csv": hashlib.sha256(evaluation_raw).hexdigest(),
            "volume_paired_comparisons.csv": hashlib.sha256(comparison_raw).hexdigest(),
            "volume_rate_calibration.csv": hashlib.sha256(calibration_raw).hexdigest(),
            "resource_backtest_manifest.json": hashlib.sha256(resource_manifest_raw).hexdigest(),
            "resource_predictions.csv": hashlib.sha256(resource_prediction_raw).hexdigest(),
            "resource_model_evaluation.csv": hashlib.sha256(resource_evaluation_raw).hexdigest(),
            "resource_paired_comparisons.csv": hashlib.sha256(resource_comparison_raw).hexdigest(),
            "resource_calibration.csv": hashlib.sha256(resource_calibration_raw).hexdigest(),
        },
        supported_metrics=supported,
        history_lookback=history_lookback,
        team_pool_rows=tuple(sorted(team_rows, key=lambda row: (row["team"], row["metric"]))),
        player_rows=tuple(sorted(player_rows, key=lambda row: (
            row["team"], row["metric"], -float(row["availability_adjusted_season_expected_events"]), row["gsis_id"],
        ))),
        weekly_rows=tuple(sorted(weekly_rows, key=lambda row: (
            row["week"], row["team"], row["metric"], -float(row["expected_event_count_mean"]), row["gsis_id"],
        ))),
        reconciliation_rows=tuple(reconciliation_rows),
        source_review=tuple(sorted(review, key=lambda row: (
            row["team"], row["metric"], row["issue"],
        ))),
        backtest_recommendation=recommendation,
        resource_backtest_recommendation=resource_recommendation,
    )


def _csv_bytes(fields: tuple[str, ...], rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def write_high_value_volume_snapshot(
    result: HighValueVolumeResult, root: str | Path
) -> Path:
    """Atomically publish team pools and reconciled player opportunity counts."""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    parent = Path(root) / "high_value_volumes" / str(result.season)
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"high-value volume snapshot exists: {destination}")
    artifacts = {
        "team_high_value_event_pools.csv": _csv_bytes(TEAM_POOL_FIELDS, result.team_pool_rows),
        "player_high_value_opportunities.csv": _csv_bytes(PLAYER_FIELDS, result.player_rows),
        "weekly_player_high_value_opportunities.csv": _csv_bytes(WEEKLY_FIELDS, result.weekly_rows),
        "weekly_reconciliation.csv": _csv_bytes(RECONCILIATION_FIELDS, result.reconciliation_rows),
        "source_review.csv": _csv_bytes(REVIEW_FIELDS, result.source_review),
    }
    fields = {
        "team_high_value_event_pools.csv": TEAM_POOL_FIELDS,
        "player_high_value_opportunities.csv": PLAYER_FIELDS,
        "weekly_player_high_value_opportunities.csv": WEEKLY_FIELDS,
        "weekly_reconciliation.csv": RECONCILIATION_FIELDS,
        "source_review.csv": REVIEW_FIELDS,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "season": result.season,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        ),
        "supported_metrics": list(result.supported_metrics),
        "scope": (
            "team and player counts for seven named high-value opportunities; not "
            "catches, yards, touchdowns, efficiency, health certainty, or fantasy points"
        ),
        "methodology": {
            "team_rate": "use the model selected by the development/untouched-holdout rate gate; current evidence selects a recency-weighted league conditional rate for every metric",
            "team_difference": "multiply the selected conditional rate by each caller-aware 2026 RB-carry or position-target resource pool",
            "player_allocation": "multiply team event pools by the frozen p24 conditional player shares",
            "role_review": "carry player-specific thin-history and large-adjustment review reasons from the conditional-share artifact onto every current opportunity count",
            "availability": "weekly expected counts use the existing common-draw availability redistribution and preserve an explicit unallocated bucket",
            "uncertainty": "the caller-aware resource mean is surrounded by a development-only per-game residual radius tested on 2025; rate low/high separately uses its development-only split-conformal radius tested on 2025; player share quantiles are marginal Monte Carlo outputs",
            "resource_transfer_caveat": "the resource residual radius was calibrated around a simple historical reference and is transferred provisionally around the caller-aware 2026 mean; its coverage is diagnostic, not a direct guarantee for that mean",
            "interval_caveat": "low/high multiplies marginal resource, conditional-rate, availability, and share bounds; it is a stress envelope, not a jointly calibrated prediction interval",
            "team_history_diagnostic": "raw and development-selected team rates are published but cannot move the primary forecast after failing the holdout gate",
        },
        "parameters": {
            "history_lookback": result.history_lookback,
            "material_raw_rate_multiple": MATERIAL_RAW_RATE_MULTIPLE,
        },
        "inputs": {
            "player_roles": str(result.player_roles_path),
            "high_value_history": str(result.high_value_history_path),
            "high_value_priors": str(result.high_value_priors_path),
            "high_value_volume_backtest": str(result.volume_backtest_path),
            "resource_backtest": str(result.resource_backtest_path),
            "sha256": dict(result.input_hashes),
        },
        "backtest_recommendation": dict(result.backtest_recommendation),
        "resource_backtest_recommendation": dict(
            result.resource_backtest_recommendation
        ),
        "recommendation": {
            "use": "use named opportunity counts as a transparent intermediate layer and research queue",
            "do_not_use": "do not convert to fantasy points until efficiency, touchdowns, schedule context, and league scoring are modeled and prospectively tested",
            "team_specific_rate_status": (
                "no team-specific conditional-rate model passed the untouched 2025 gate"
                if not result.backtest_recommendation["team_specific_metrics"]
                else "only explicitly promoted team-specific metric rates are used"
            ),
            "resource_mean_status": "retain the caller-aware 2026 point means; historical resource models inform only provisional residual envelopes",
            "resource_interval_status": "inspect resource_holdout_coverage by resource; below-nominal holdout coverage is explicitly flagged and must not be described as calibrated 2026 coverage",
        },
        "quality": {
            "team_metric_rows": len(result.team_pool_rows),
            "player_metric_rows": len(result.player_rows),
            "weekly_player_metric_rows": len(result.weekly_rows),
            "weekly_reconciliation_rows": len(result.reconciliation_rows),
            "source_review_rows": len(result.source_review),
            "player_metric_rows_requiring_current_role_review": sum(
                row["requires_current_role_review"] == "true"
                for row in result.player_rows
            ),
            "team_count": len({row["team"] for row in result.team_pool_rows}),
            "maximum_weekly_reconciliation_error": max(
                float(row["reconciliation_error"])
                for row in result.reconciliation_rows
            ),
            "minimum_holdout_rate_coverage": min(
                float(row["heldout_rate_coverage"]) for row in result.team_pool_rows
            ),
            "minimum_resource_holdout_coverage": min(
                float(row["resource_holdout_coverage"])
                for row in result.team_pool_rows
            ),
            "resources_below_nominal_holdout_coverage": sorted({
                row["base_resource"] for row in result.team_pool_rows
                if float(row["resource_holdout_coverage"])
                < float(row["resource_nominal_coverage"])
            }),
            "resource_reference_models_promoted": list(
                result.resource_backtest_recommendation[
                    "team_reference_resources"
                ]
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
