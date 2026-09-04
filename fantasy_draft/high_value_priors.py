"""Freeze supported high-value role signals into prospective 2026 priors.

The output remains an allocation layer, not a fantasy projection.  It estimates a
player's share of a named team-position high-value event conditional on that event
occurring.  Team event volume, efficiency, yards, touchdowns, and fantasy scoring
are deliberately outside this module.
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
    BASE_MODEL,
    COMPARISON_FIELDS,
    EVALUATION_FIELDS,
    METRICS,
    MODEL_PRIORS,
    PRIMARY_MODEL,
    high_value_groups,
    rate_multipliers,
    recommend_high_value_metrics,
)


SCHEMA_VERSION = "1.1.0"
MODEL_VERSION = "high-value-role-prior-v0.2.0"
MODEL_STATUS = (
    "retrospective_feature_selected_conditional_share_prior_"
    "frozen_for_prospective_2026_test"
)
WEEKS = tuple(range(1, 19))
MATERIAL_NO_HISTORY_SHARE = 0.05
MATERIAL_ADJUSTMENT_DELTA = 0.10

PRIOR_FIELDS = (
    "season", "team", "position", "metric", "base_resource", "gsis_id",
    "player_name", "current_status", "roster_status", "depth_rank",
    "current_active", "base_model_all_affiliated_share", "base_latent_role_share",
    "base_active_conditional_share", "historical_high_value_events",
    "historical_base_opportunities", "historical_peer_team_high_value_rate",
    "historical_season_count", "historical_latest_season",
    "history_current_team_in_latest_season", "rate_multiplier_p12",
    "rate_multiplier_p24", "rate_multiplier_p48", "share_p12", "share_p24",
    "share_p48", "share_sensitivity_low", "share_sensitivity_high",
    "active_conditional_share_p24", "delta_vs_base_latent_role_share",
    "history_support", "role_evidence_score_v0", "role_evidence_label",
    "ffc_source_player_id", "ffc_adp", "backtest_primary_mean_delta_vs_base",
    "backtest_primary_clear_win_windows", "backtest_primary_clear_loss_windows",
    "backtest_week_18_actual_events", "backtest_week_18_room_count",
    "model_status",
)

ROOM_FIELDS = (
    "season", "team", "position", "metric", "base_resource",
    "candidate_count", "current_active_count", "players_with_history",
    "material_players_without_history", "material_players_with_limited_history",
    "base_model_all_affiliated_share_sum",
    "base_latent_role_share_sum",
    "p12_share_sum", "p24_share_sum", "p48_share_sum",
    "p24_active_conditional_share_sum", "maximum_sensitivity_width",
    "backtest_primary_mean_delta_vs_base", "backtest_primary_clear_win_windows",
    "backtest_primary_clear_loss_windows", "backtest_week_18_actual_events",
    "backtest_week_18_room_count", "promotion_status", "reconciliation_error",
)

WEEKLY_FIELDS = (
    "season", "week", "gameday", "team", "opponent", "home_away",
    "scheduled_game", "position", "metric", "base_resource", "gsis_id",
    "player_name", "current_status", "active_probability_median",
    "latent_high_value_share_p24", "expected_share_mean", "share_p10",
    "share_p50", "share_p90", "ffc_source_player_id", "ffc_adp",
    "simulation_draws", "model_status",
)

WEEKLY_RECONCILIATION_FIELDS = (
    "season", "week", "gameday", "team", "opponent", "home_away",
    "scheduled_game", "position", "metric", "base_resource",
    "candidate_count", "simulation_draws", "reconciliation_target",
    "expected_player_share_sum", "unallocated_draw_rate",
    "reconciled_share_sum", "reconciliation_error",
)

REVIEW_FIELDS = (
    "season", "team", "position", "metric", "gsis_id", "player_name",
    "issue", "details",
)


class HighValuePriorDataError(ValueError):
    """Raised when frozen high-value priors cannot be built safely."""


@dataclass(frozen=True)
class HighValuePriorResult:
    season: int
    role_snapshot_path: Path
    high_value_history_path: Path
    high_value_backtest_path: Path
    availability_path: Path
    input_hashes: Mapping[str, str]
    history_lookback: int
    simulation_draws: int
    random_seed: int
    supported_metrics: tuple[str, ...]
    prior_rows: tuple[Mapping[str, Any], ...]
    room_rows: tuple[Mapping[str, Any], ...]
    weekly_rows: tuple[Mapping[str, Any], ...]
    weekly_reconciliation: tuple[Mapping[str, Any], ...]
    source_review: tuple[Mapping[str, Any], ...]
    backtest_recommendation: Mapping[str, Any]


def _read_manifest(root: Path) -> tuple[bytes, Mapping[str, Any]]:
    path = root / "manifest.json"
    if not path.is_file():
        raise HighValuePriorDataError(f"missing input manifest: {path}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HighValuePriorDataError(f"input manifest is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise HighValuePriorDataError(f"input manifest is not an object: {path}")
    return raw, value


def _verified_csv(
    root: Path,
    manifest: Mapping[str, Any],
    filename: str,
    required: set[str],
) -> tuple[bytes, list[dict[str, str]]]:
    metadata = (manifest.get("artifacts") or {}).get(filename)
    if not isinstance(metadata, dict) or not metadata.get("sha256"):
        raise HighValuePriorDataError(f"manifest does not describe {filename}: {root}")
    path = root / filename
    if not path.is_file():
        raise HighValuePriorDataError(f"input does not exist: {path}")
    raw = path.read_bytes()
    actual_hash = hashlib.sha256(raw).hexdigest()
    if actual_hash != metadata["sha256"]:
        raise HighValuePriorDataError(
            f"input hash mismatch for {path}: expected {metadata['sha256']}, got {actual_hash}"
        )
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        fields = set(reader.fieldnames or ())
        rows = list(reader)
    except UnicodeDecodeError as error:
        raise HighValuePriorDataError(f"input is not UTF-8 CSV: {path}") from error
    missing = required - fields
    if missing or not rows:
        raise HighValuePriorDataError(
            f"{path} is empty or missing fields {sorted(missing)}"
        )
    return raw, rows


def _number(value: Any, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise HighValuePriorDataError(f"{context} must be numeric") from error
    if not math.isfinite(result) or result < 0:
        raise HighValuePriorDataError(f"{context} must be finite and nonnegative")
    return result


def _integer(value: Any, context: str) -> int:
    result = _number(value, context)
    if not result.is_integer():
        raise HighValuePriorDataError(f"{context} must be an integer")
    return int(result)


def _percentile_from_sorted(values: list[float], probability: float) -> float:
    if not values:
        raise HighValuePriorDataError("cannot summarize an empty simulation")
    position = (len(values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def _validate_backtest_decision(
    root: Path,
    manifest: Mapping[str, Any],
    evaluation_rows: list[dict[str, str]],
    comparison_rows: list[dict[str, str]],
) -> Mapping[str, Any]:
    if manifest.get("model_version") != "high-value-role-backtest-v0.2.0":
        raise HighValuePriorDataError("unsupported high-value backtest model version")
    parameters = manifest.get("parameters") or {}
    if parameters.get("model_prior_opportunities") != dict(MODEL_PRIORS):
        raise HighValuePriorDataError("backtest does not use the frozen model priors")
    recomputed = recommend_high_value_metrics(evaluation_rows, comparison_rows)
    if recomputed != manifest.get("recommendation"):
        raise HighValuePriorDataError(
            f"backtest recommendation does not reproduce from scored artifacts: {root}"
        )
    if recomputed.get("primary_model") != PRIMARY_MODEL:
        raise HighValuePriorDataError("backtest primary model is not rate_adjusted_p24")
    supported = recomputed.get("supported_metrics") or []
    if not supported:
        raise HighValuePriorDataError("backtest promoted no high-value metrics")
    for metric in supported:
        details = (recomputed.get("metrics") or {}).get(metric) or {}
        if metric not in METRICS or not details.get("promotion_gate_passed"):
            raise HighValuePriorDataError(f"invalid promoted metric {metric}")
        if details.get("recommended_action") != (
            "freeze_rate_adjusted_p24_for_prospective_2026_test"
        ):
            raise HighValuePriorDataError(f"metric {metric} lacks a freeze decision")
    return recomputed


def _history_support(base_opportunities: float) -> str:
    if base_opportunities <= 0:
        return "no_player_history"
    if base_opportunities < 24:
        return "limited_below_primary_prior"
    if base_opportunities < 48:
        return "moderate_24_to_48_opportunities"
    return "strong_at_least_48_opportunities"


def build_high_value_priors(
    player_roles: str | Path,
    high_value_history: str | Path,
    high_value_backtest: str | Path,
    availability: str | Path,
    *,
    random_seed: int = 20260902,
) -> HighValuePriorResult:
    """Apply only backtest-promoted features to current conditional role shares."""

    if isinstance(random_seed, bool) or not isinstance(random_seed, int):
        raise ValueError("random_seed must be an integer")
    role_root = Path(player_roles)
    history_root = Path(high_value_history)
    backtest_root = Path(high_value_backtest)
    availability_root = Path(availability)

    role_manifest_raw, role_manifest = _read_manifest(role_root)
    history_manifest_raw, history_manifest = _read_manifest(history_root)
    backtest_manifest_raw, backtest_manifest = _read_manifest(backtest_root)
    availability_manifest_raw, availability_manifest = _read_manifest(availability_root)

    role_raw, role_rows = _verified_csv(
        role_root,
        role_manifest,
        "player_role_candidates.csv",
        {
            "season", "team", "position", "resource", "gsis_id", "player_name",
            "current_status", "roster_status", "depth_rank", "current_active",
            "active_baseline_share", "all_affiliated_share", "latent_role_weight",
            "role_evidence_score_v0", "role_evidence_label",
            "ffc_source_player_id", "ffc_adp",
        },
    )
    required_history_fields = {
        "season", "week", "team", "position", "gsis_id", "player_name",
        "targets", "carries", *(spec.high_value_field for spec in METRICS.values()),
    }
    history_raw, history_rows = _verified_csv(
        history_root,
        history_manifest,
        "player_week_high_value.csv",
        required_history_fields,
    )
    evaluation_raw, evaluation_rows = _verified_csv(
        backtest_root,
        backtest_manifest,
        "model_evaluation.csv",
        set(EVALUATION_FIELDS),
    )
    comparison_raw, comparison_rows = _verified_csv(
        backtest_root,
        backtest_manifest,
        "paired_comparisons.csv",
        set(COMPARISON_FIELDS),
    )
    availability_raw, availability_rows = _verified_csv(
        availability_root,
        availability_manifest,
        "weekly_availability.csv",
        {
            "season", "week", "gameday", "team", "opponent", "home_away",
            "scheduled_game", "position", "gsis_id", "player_name",
            "current_status", "active_probability_median", "ffc_source_player_id",
            "ffc_adp",
        },
    )

    recommendation = _validate_backtest_decision(
        backtest_root, backtest_manifest, evaluation_rows, comparison_rows
    )
    supported = tuple(recommendation["supported_metrics"])
    history_lookback = _integer(
        (backtest_manifest.get("parameters") or {}).get("history_lookback"),
        "backtest history_lookback",
    )
    simulation_draws = _integer(
        (availability_manifest.get("parameters") or {}).get("simulation_draws"),
        "availability simulation_draws",
    )
    if not 100 <= simulation_draws <= 100_000:
        raise HighValuePriorDataError("availability simulation_draws is outside 100..100000")

    seasons = {_integer(row["season"], "role season") for row in role_rows}
    if len(seasons) != 1:
        raise HighValuePriorDataError("player-role candidates must contain one season")
    season = next(iter(seasons))
    if _integer(availability_manifest.get("season"), "availability season") != season:
        raise HighValuePriorDataError("availability and role seasons do not match")
    recorded_role_hash = ((availability_manifest.get("inputs") or {}).get("sha256") or {}).get(
        "player_role_candidates.csv"
    )
    if recorded_role_hash != hashlib.sha256(role_raw).hexdigest():
        raise HighValuePriorDataError(
            "availability snapshot was not built from this player-role candidate artifact"
        )

    history_players, history_teams, _, _ = high_value_groups(history_rows)
    role_rooms: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in role_rows:
        if not row["team"] or not row["gsis_id"]:
            raise HighValuePriorDataError("player-role candidate lacks team or GSIS ID")
        role_rooms[(row["team"], row["resource"])].append(row)

    prior_rows: list[dict[str, Any]] = []
    room_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    prior_lookup: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = {}

    for metric in supported:
        spec = METRICS[metric]
        evidence = recommendation["metrics"][metric]
        metric_rooms = [
            (team, rows)
            for (team, resource), rows in role_rooms.items()
            if resource == spec.base_resource
        ]
        if not metric_rooms:
            raise HighValuePriorDataError(f"no current rooms for promoted metric {metric}")
        for team, candidates in sorted(metric_rooms):
            if {row["position"] for row in candidates} != {spec.position}:
                raise HighValuePriorDataError(
                    f"{team} {metric} candidate position does not match {spec.position}"
                )
            latent = {
                row["gsis_id"]: _number(
                    row["latent_role_weight"], f"{team} {metric} latent role weight"
                )
                for row in candidates
            }
            latent_total = sum(latent.values())
            if latent_total <= 0:
                raise HighValuePriorDataError(f"{team} {metric} has no base role mass")
            base = {player_id: value / latent_total for player_id, value in latent.items()}
            published_total = sum(
                _number(
                    row["all_affiliated_share"],
                    f"{team} {metric} published all-affiliated share",
                )
                for row in candidates
            )
            if abs(published_total - 1.0) > 5e-6:
                raise HighValuePriorDataError(
                    f"{team} {metric} published all-affiliated shares do not sum to one"
                )

            details_by_player: dict[str, Mapping[str, Any]] = {}
            shares_by_model: dict[str, dict[str, float]] = {}
            raw_by_model: dict[str, dict[str, float]] = {
                model: {} for model in MODEL_PRIORS if model != BASE_MODEL
            }
            for row in candidates:
                player_id = row["gsis_id"]
                multipliers, details = rate_multipliers(
                    player_id,
                    target_season=season,
                    current_team=team,
                    position=spec.position,
                    metric=metric,
                    lookback=history_lookback,
                    players=history_players,
                    teams=history_teams,
                )
                details_by_player[player_id] = {**details, "multipliers": multipliers}
                for model in raw_by_model:
                    raw_by_model[model][player_id] = base[player_id] * multipliers[model]
            for model, values in raw_by_model.items():
                total = sum(values.values())
                if total <= 0:
                    raise HighValuePriorDataError(f"{team} {metric} {model} has no mass")
                shares_by_model[model] = {
                    player_id: value / total for player_id, value in values.items()
                }

            active_ids = {
                row["gsis_id"] for row in candidates if row["current_active"] == "true"
            }
            active_total = sum(shares_by_model[PRIMARY_MODEL][value] for value in active_ids)
            active_shares = (
                {
                    player_id: shares_by_model[PRIMARY_MODEL][player_id] / active_total
                    for player_id in active_ids
                }
                if active_total > 0 else {}
            )
            base_active_total = sum(base[value] for value in active_ids)
            if active_ids and base_active_total <= 0:
                raise HighValuePriorDataError(f"{team} {metric} has no active base mass")
            for row in candidates:
                if row["current_active"] != "true":
                    continue
                expected_base_active = base[row["gsis_id"]] / base_active_total
                published_active = _number(
                    row["active_baseline_share"],
                    f"{team} {metric} active baseline share",
                )
                if abs(expected_base_active - published_active) > 5e-6:
                    raise HighValuePriorDataError(
                        f"{team} {metric} latent weights do not reproduce active baseline"
                    )
            if not active_ids:
                review_rows.append({
                    "season": season, "team": team, "position": spec.position,
                    "metric": metric, "gsis_id": "", "player_name": "",
                    "issue": "no_current_active_candidate",
                    "details": "all-affiliated prior exists but current-active conditional share is unavailable",
                })

            room_output: dict[str, dict[str, Any]] = {}
            material_without_history = 0
            material_with_limited_history = 0
            for row in candidates:
                player_id = row["gsis_id"]
                detail = details_by_player[player_id]
                history_base = float(detail["historical_base_opportunities"])
                model_shares = {
                    model: shares_by_model[model][player_id]
                    for model in shares_by_model
                }
                sensitivity_low = min(model_shares.values())
                sensitivity_high = max(model_shares.values())
                if history_base <= 0 and base[player_id] >= MATERIAL_NO_HISTORY_SHARE:
                    material_without_history += 1
                    review_rows.append({
                        "season": season, "team": team, "position": spec.position,
                        "metric": metric, "gsis_id": player_id,
                        "player_name": row["player_name"],
                        "issue": "material_role_without_player_metric_history",
                        "details": (
                            f"base latent role share {base[player_id]:.3f}; "
                            "rate multiplier defaults to 1.0"
                        ),
                    })
                elif (
                    history_base < float(MODEL_PRIORS[PRIMARY_MODEL] or 0)
                    and base[player_id] >= MATERIAL_NO_HISTORY_SHARE
                ):
                    material_with_limited_history += 1
                    review_rows.append({
                        "season": season, "team": team, "position": spec.position,
                        "metric": metric, "gsis_id": player_id,
                        "player_name": row["player_name"],
                        "issue": "material_role_with_limited_player_metric_history",
                        "details": (
                            f"base latent role share {base[player_id]:.3f}; "
                            f"only {history_base:.3f} weighted base opportunities; "
                            f"primary shrinkage prior is {MODEL_PRIORS[PRIMARY_MODEL]:.0f}"
                        ),
                    })
                output = {
                    "season": season, "team": team, "position": spec.position,
                    "metric": metric, "base_resource": spec.base_resource,
                    "gsis_id": player_id, "player_name": row["player_name"],
                    "current_status": row["current_status"],
                    "roster_status": row["roster_status"],
                    "depth_rank": row["depth_rank"],
                    "current_active": row["current_active"],
                    "base_model_all_affiliated_share": row["all_affiliated_share"],
                    "base_latent_role_share": f"{base[player_id]:.9f}",
                    "base_active_conditional_share": (
                        row["active_baseline_share"] if row["current_active"] == "true" else ""
                    ),
                    "historical_high_value_events": f"{float(detail['historical_high_value_events']):.6f}",
                    "historical_base_opportunities": f"{history_base:.6f}",
                    "historical_peer_team_high_value_rate": f"{float(detail['historical_team_high_value_rate']):.9f}",
                    "historical_season_count": detail["historical_season_count"],
                    "historical_latest_season": detail["historical_latest_season"] or "",
                    "history_current_team_in_latest_season": str(bool(detail["same_team_latest"])).lower(),
                    "rate_multiplier_p12": f"{float(detail['multipliers']['rate_adjusted_p12']):.9f}",
                    "rate_multiplier_p24": f"{float(detail['multipliers'][PRIMARY_MODEL]):.9f}",
                    "rate_multiplier_p48": f"{float(detail['multipliers']['rate_adjusted_p48']):.9f}",
                    "share_p12": f"{model_shares['rate_adjusted_p12']:.9f}",
                    "share_p24": f"{model_shares[PRIMARY_MODEL]:.9f}",
                    "share_p48": f"{model_shares['rate_adjusted_p48']:.9f}",
                    "share_sensitivity_low": f"{sensitivity_low:.9f}",
                    "share_sensitivity_high": f"{sensitivity_high:.9f}",
                    "active_conditional_share_p24": (
                        f"{active_shares[player_id]:.9f}" if player_id in active_shares else ""
                    ),
                    "delta_vs_base_latent_role_share": f"{model_shares[PRIMARY_MODEL] - base[player_id]:.9f}",
                    "history_support": _history_support(history_base),
                    "role_evidence_score_v0": row["role_evidence_score_v0"],
                    "role_evidence_label": row["role_evidence_label"],
                    "ffc_source_player_id": row["ffc_source_player_id"],
                    "ffc_adp": row["ffc_adp"],
                    "backtest_primary_mean_delta_vs_base": f"{float(evidence['primary_mean_delta_vs_base']):.6f}",
                    "backtest_primary_clear_win_windows": evidence["primary_clear_win_windows"],
                    "backtest_primary_clear_loss_windows": evidence["primary_clear_loss_windows"],
                    "backtest_week_18_actual_events": evidence["week_18_actual_events"],
                    "backtest_week_18_room_count": evidence["week_18_room_count"],
                    "model_status": MODEL_STATUS,
                }
                delta = model_shares[PRIMARY_MODEL] - base[player_id]
                if abs(delta) >= MATERIAL_ADJUSTMENT_DELTA:
                    review_rows.append({
                        "season": season, "team": team, "position": spec.position,
                        "metric": metric, "gsis_id": player_id,
                        "player_name": row["player_name"],
                        "issue": "large_historical_adjustment_requires_current_role_review",
                        "details": (
                            f"base latent share {base[player_id]:.3f}; p24 share "
                            f"{model_shares[PRIMARY_MODEL]:.3f}; delta {delta:+.3f}; "
                            f"history support {_history_support(history_base)}"
                        ),
                    })
                prior_rows.append(output)
                room_output[player_id] = output

            share_sums = {
                model: sum(shares_by_model[model].values()) for model in shares_by_model
            }
            active_sum = sum(active_shares.values())
            reconciliation_error = max(
                abs(sum(base.values()) - 1.0),
                *(abs(value - 1.0) for value in share_sums.values()),
                abs(active_sum - 1.0) if active_ids else 0.0,
            )
            room_rows.append({
                "season": season, "team": team, "position": spec.position,
                "metric": metric, "base_resource": spec.base_resource,
                "candidate_count": len(candidates),
                "current_active_count": len(active_ids),
                "players_with_history": sum(
                    float(value["historical_base_opportunities"]) > 0
                    for value in details_by_player.values()
                ),
                "material_players_without_history": material_without_history,
                "material_players_with_limited_history": material_with_limited_history,
                "base_model_all_affiliated_share_sum": f"{published_total:.12f}",
                "base_latent_role_share_sum": f"{sum(base.values()):.12f}",
                "p12_share_sum": f"{share_sums['rate_adjusted_p12']:.12f}",
                "p24_share_sum": f"{share_sums[PRIMARY_MODEL]:.12f}",
                "p48_share_sum": f"{share_sums['rate_adjusted_p48']:.12f}",
                "p24_active_conditional_share_sum": (
                    f"{active_sum:.12f}" if active_ids else ""
                ),
                "maximum_sensitivity_width": f"{max(float(value['share_sensitivity_high']) - float(value['share_sensitivity_low']) for value in room_output.values()):.9f}",
                "backtest_primary_mean_delta_vs_base": f"{float(evidence['primary_mean_delta_vs_base']):.6f}",
                "backtest_primary_clear_win_windows": evidence["primary_clear_win_windows"],
                "backtest_primary_clear_loss_windows": evidence["primary_clear_loss_windows"],
                "backtest_week_18_actual_events": evidence["week_18_actual_events"],
                "backtest_week_18_room_count": evidence["week_18_room_count"],
                "promotion_status": "frozen_for_prospective_2026_test",
                "reconciliation_error": f"{reconciliation_error:.12f}",
            })
            prior_lookup[(team, spec.position, metric)] = room_output

    availability_lookup: dict[tuple[int, str, str], dict[str, str]] = {}
    schedule_meta: dict[tuple[int, str], tuple[str, str, str, str]] = {}
    for row in availability_rows:
        row_season = _integer(row["season"], "availability row season")
        week = _integer(row["week"], "availability week")
        if row_season != season or week not in WEEKS:
            raise HighValuePriorDataError("availability contains an unexpected season or week")
        key = week, row["team"], row["gsis_id"]
        if key in availability_lookup:
            raise HighValuePriorDataError(f"duplicate availability row for {key}")
        availability_lookup[key] = row
        meta = (
            row["gameday"], row["opponent"], row["home_away"], row["scheduled_game"]
        )
        schedule_key = week, row["team"]
        if schedule_key in schedule_meta and schedule_meta[schedule_key] != meta:
            raise HighValuePriorDataError(f"mixed schedule metadata for {schedule_key}")
        schedule_meta[schedule_key] = meta

    weekly_rows: list[dict[str, Any]] = []
    weekly_reconciliation: list[dict[str, Any]] = []
    rng = random.Random(random_seed)
    teams = sorted({key[0] for key in prior_lookup})
    for team in teams:
        team_rooms = [
            (key, players) for key, players in prior_lookup.items() if key[0] == team
        ]
        unique_ids = sorted({player_id for _, players in team_rooms for player_id in players})
        for week in WEEKS:
            meta = schedule_meta.get((week, team))
            if meta is None:
                raise HighValuePriorDataError(f"availability lacks {team} Week {week}")
            gameday, opponent, home_away, scheduled_game = meta
            probabilities: dict[str, float] = {}
            for player_id in unique_ids:
                row = availability_lookup.get((week, team, player_id))
                if row is None:
                    raise HighValuePriorDataError(
                        f"availability lacks {team} Week {week} player {player_id}"
                    )
                probability = _number(
                    row["active_probability_median"],
                    f"{team} Week {week} {player_id} active probability",
                )
                if probability > 1:
                    raise HighValuePriorDataError("active probability exceeds one")
                probabilities[player_id] = probability
            active_draws = {
                player_id: [rng.random() < probabilities[player_id] for _ in range(simulation_draws)]
                for player_id in unique_ids
            }
            for (_, position, metric), players in sorted(team_rooms):
                spec = METRICS[metric]
                player_ids = sorted(players)
                values = {player_id: [] for player_id in player_ids}
                unallocated = 0
                if scheduled_game == "true":
                    for draw in range(simulation_draws):
                        active = {
                            player_id for player_id in player_ids
                            if active_draws[player_id][draw]
                        }
                        denominator = sum(
                            float(players[player_id]["share_p24"]) for player_id in active
                        )
                        if denominator <= 0:
                            unallocated += 1
                            for player_id in player_ids:
                                values[player_id].append(0.0)
                        else:
                            for player_id in player_ids:
                                values[player_id].append(
                                    float(players[player_id]["share_p24"]) / denominator
                                    if player_id in active else 0.0
                                )
                    target = 1.0
                    unallocated_rate = unallocated / simulation_draws
                else:
                    values = {
                        player_id: [0.0] * simulation_draws for player_id in player_ids
                    }
                    target = 0.0
                    unallocated_rate = 0.0
                expected_sum = 0.0
                for player_id in player_ids:
                    prior = players[player_id]
                    samples = values[player_id]
                    mean = sum(samples) / simulation_draws
                    expected_sum += mean
                    ordered_samples = sorted(samples)
                    availability_row = availability_lookup[(week, team, player_id)]
                    weekly_rows.append({
                        "season": season, "week": week, "gameday": gameday,
                        "team": team, "opponent": opponent, "home_away": home_away,
                        "scheduled_game": scheduled_game, "position": position,
                        "metric": metric, "base_resource": spec.base_resource,
                        "gsis_id": player_id, "player_name": prior["player_name"],
                        "current_status": prior["current_status"],
                        "active_probability_median": availability_row["active_probability_median"],
                        "latent_high_value_share_p24": prior["share_p24"],
                        "expected_share_mean": f"{mean:.9f}",
                        "share_p10": f"{_percentile_from_sorted(ordered_samples, 0.10):.9f}",
                        "share_p50": f"{_percentile_from_sorted(ordered_samples, 0.50):.9f}",
                        "share_p90": f"{_percentile_from_sorted(ordered_samples, 0.90):.9f}",
                        "ffc_source_player_id": prior["ffc_source_player_id"],
                        "ffc_adp": prior["ffc_adp"],
                        "simulation_draws": simulation_draws,
                        "model_status": MODEL_STATUS,
                    })
                reconciled = expected_sum + unallocated_rate
                error = abs(reconciled - target)
                weekly_reconciliation.append({
                    "season": season, "week": week, "gameday": gameday,
                    "team": team, "opponent": opponent, "home_away": home_away,
                    "scheduled_game": scheduled_game, "position": position,
                    "metric": metric, "base_resource": spec.base_resource,
                    "candidate_count": len(player_ids),
                    "simulation_draws": simulation_draws,
                    "reconciliation_target": f"{target:.9f}",
                    "expected_player_share_sum": f"{expected_sum:.9f}",
                    "unallocated_draw_rate": f"{unallocated_rate:.9f}",
                    "reconciled_share_sum": f"{reconciled:.9f}",
                    "reconciliation_error": f"{error:.12f}",
                })

    input_hashes = {
        "player_roles_manifest.json": hashlib.sha256(role_manifest_raw).hexdigest(),
        "player_role_candidates.csv": hashlib.sha256(role_raw).hexdigest(),
        "high_value_history_manifest.json": hashlib.sha256(history_manifest_raw).hexdigest(),
        "player_week_high_value.csv": hashlib.sha256(history_raw).hexdigest(),
        "high_value_backtest_manifest.json": hashlib.sha256(backtest_manifest_raw).hexdigest(),
        "model_evaluation.csv": hashlib.sha256(evaluation_raw).hexdigest(),
        "paired_comparisons.csv": hashlib.sha256(comparison_raw).hexdigest(),
        "availability_manifest.json": hashlib.sha256(availability_manifest_raw).hexdigest(),
        "weekly_availability.csv": hashlib.sha256(availability_raw).hexdigest(),
    }
    return HighValuePriorResult(
        season=season,
        role_snapshot_path=role_root,
        high_value_history_path=history_root,
        high_value_backtest_path=backtest_root,
        availability_path=availability_root,
        input_hashes=input_hashes,
        history_lookback=history_lookback,
        simulation_draws=simulation_draws,
        random_seed=random_seed,
        supported_metrics=supported,
        prior_rows=tuple(sorted(prior_rows, key=lambda row: (
            row["team"], row["metric"], -float(row["share_p24"]), row["gsis_id"],
        ))),
        room_rows=tuple(sorted(room_rows, key=lambda row: (row["team"], row["metric"]))),
        weekly_rows=tuple(sorted(weekly_rows, key=lambda row: (
            row["week"], row["team"], row["metric"],
            -float(row["expected_share_mean"]), row["gsis_id"],
        ))),
        weekly_reconciliation=tuple(sorted(
            weekly_reconciliation,
            key=lambda row: (row["week"], row["team"], row["metric"]),
        )),
        source_review=tuple(sorted(review_rows, key=lambda row: (
            row["team"], row["metric"], row["issue"], row["gsis_id"],
        ))),
        backtest_recommendation=recommendation,
    )


def _csv_bytes(fields: tuple[str, ...], rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def write_high_value_prior_snapshot(
    result: HighValuePriorResult, root: str | Path
) -> Path:
    """Atomically publish current and availability-adjusted high-value shares."""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    parent = Path(root) / "high_value_priors" / str(result.season)
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"high-value prior snapshot exists: {destination}")
    artifacts = {
        "player_high_value_priors.csv": _csv_bytes(PRIOR_FIELDS, result.prior_rows),
        "team_metric_reconciliation.csv": _csv_bytes(ROOM_FIELDS, result.room_rows),
        "weekly_high_value_roles.csv": _csv_bytes(WEEKLY_FIELDS, result.weekly_rows),
        "weekly_reconciliation.csv": _csv_bytes(
            WEEKLY_RECONCILIATION_FIELDS, result.weekly_reconciliation
        ),
        "source_review.csv": _csv_bytes(REVIEW_FIELDS, result.source_review),
    }
    fields = {
        "player_high_value_priors.csv": PRIOR_FIELDS,
        "team_metric_reconciliation.csv": ROOM_FIELDS,
        "weekly_high_value_roles.csv": WEEKLY_FIELDS,
        "weekly_reconciliation.csv": WEEKLY_RECONCILIATION_FIELDS,
        "source_review.csv": REVIEW_FIELDS,
    }
    backtest_metrics = result.backtest_recommendation["metrics"]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "model_status": MODEL_STATUS,
        "season": result.season,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        ),
        "scope": (
            "conditional player share of a named team-position high-value event; "
            "not team event volume, production, or fantasy points"
        ),
        "supported_metrics": list(result.supported_metrics),
        "metric_definitions": {
            metric: {
                "position": METRICS[metric].position,
                "base_resource": METRICS[metric].base_resource,
                "historical_field": METRICS[metric].high_value_field,
                "requires_ftn_read_source": METRICS[metric].requires_read_source,
                "backtest": dict(backtest_metrics[metric]),
            }
            for metric in result.supported_metrics
        },
        "methodology": {
            "base_role": "availability-ready latent role weights from the frozen resource-selected player-role model; filtering current active players reproduces the published active baseline",
            "adjustment": "multiply base role by the historical player rate relative to his peer team-position rate, beta-shrunk by 24 base opportunities and normalized within the room",
            "sensitivity": "p12 and p48 are parameter sensitivity bounds, not calibrated confidence intervals",
            "history_boundary": f"only the {result.history_lookback} seasons strictly before {result.season}",
            "transfer": "uses the same prior-team and changed-team shrinkage frozen in the backtest",
            "availability": "marginal Bernoulli draws reuse one player availability state across every supported metric in a team-week and renormalize p24 latent shares",
            "weekly_scope": "share conditional on the named event occurring; no current team metric-event volume is forecast here",
            "selection_caveat": "metrics were selected retrospectively on 2023-25 and are now frozen for prospective 2026 scoring without retuning",
            "routes_limitation": "public nflverse participation route marks only the primary receiver and cannot measure every player's routes run",
        },
        "parameters": {
            "primary_model": PRIMARY_MODEL,
            "model_prior_opportunities": MODEL_PRIORS,
            "history_lookback": result.history_lookback,
            "simulation_draws": result.simulation_draws,
            "random_seed": result.random_seed,
            "material_no_history_share": MATERIAL_NO_HISTORY_SHARE,
            "material_limited_history_opportunities": MODEL_PRIORS[PRIMARY_MODEL],
            "material_adjustment_delta": MATERIAL_ADJUSTMENT_DELTA,
        },
        "inputs": {
            "player_roles": str(result.role_snapshot_path),
            "high_value_history": str(result.high_value_history_path),
            "high_value_backtest": str(result.high_value_backtest_path),
            "availability": str(result.availability_path),
            "sha256": dict(result.input_hashes),
        },
        "backtest_recommendation": dict(result.backtest_recommendation),
        "recommendation": {
            "use": "use p24 shares only for the supported named metrics in prospective 2026 conditional-role scoring",
            "do_not_use": "do not infer routes, total event counts, efficiency, touchdowns, or fantasy points from this artifact",
            "diagnostic_only_metrics": result.backtest_recommendation[
                "diagnostic_only_metrics"
            ],
        },
        "quality": {
            "prior_rows": len(result.prior_rows),
            "team_metric_rows": len(result.room_rows),
            "weekly_rows": len(result.weekly_rows),
            "weekly_reconciliation_rows": len(result.weekly_reconciliation),
            "source_review_rows": len(result.source_review),
            "maximum_room_reconciliation_error": max(
                (float(row["reconciliation_error"]) for row in result.room_rows),
                default=0.0,
            ),
            "maximum_weekly_reconciliation_error": max(
                (
                    float(row["reconciliation_error"])
                    for row in result.weekly_reconciliation
                ),
                default=0.0,
            ),
            "bye_team_metric_rows": sum(
                row["scheduled_game"] == "false"
                for row in result.weekly_reconciliation
            ),
            "maximum_unallocated_draw_rate": max(
                (
                    float(row["unallocated_draw_rate"])
                    for row in result.weekly_reconciliation
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
