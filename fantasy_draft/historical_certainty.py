"""Time-correct diagnostic for offensive-style evidence scores.

This module does not retrofit news or scheme judgments into old seasons.  It
reconstructs the portion of the current broad-system and exact-style rubrics
that is available from frozen caller and staff evidence, represents the missing
changed-caller scheme components as score bounds, and tests the conservative
lower bounds against held-out style error.
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


SCHEMA_VERSION = "1.0.0"
MODEL_VERSION = "historical-style-certainty-diagnostic-v0.1.0"
BACKTEST_MODEL_VERSION = "opening-caller-transition-backtest-v0.3.0"
CONTINUITY_MODEL_STATUS = "descriptive_not_style_certainty"
CANDIDATE_MODEL = "caller_aware_v0"
NOMINAL_COVERAGE = 0.90
TIERS = ("low", "middle", "high")
SCORE_KINDS = (
    "broad_system_lower_bound",
    "exact_style_lower_bound",
)

TEAM_SCORE_FIELDS = (
    "target_season",
    "team",
    "opening_caller",
    "prior_caller",
    "caller_cohort",
    "score_status",
    "same_play_caller",
    "play_caller_on_prior_staff",
    "head_coach_continuity",
    "staff_continuity_index_v0",
    "unavailable_core_responsibility_count",
    "one_year_anchor_available",
    "effective_anchor_strength",
    "fingerprint_stability",
    "caller_continuity_component",
    "scheme_component_status",
    "broad_known_weight",
    "broad_system_certainty_lower_bound",
    "broad_system_certainty_upper_bound",
    "exact_known_weight",
    "exact_style_certainty_lower_bound",
    "exact_style_certainty_upper_bound",
    "exact_transition_ceiling_applied",
)

TEAM_ERROR_FIELDS = (
    "target_season",
    "week_start",
    "week_end",
    "team",
    "caller_cohort",
    "metric_count",
    "broad_system_lower_bound",
    "exact_style_lower_bound",
    "mean_normalized_absolute_error",
    "median_normalized_absolute_error",
)

RANK_FIELDS = (
    "score_kind",
    "scope",
    "scope_seasons",
    "week_end",
    "team_season_count",
    "spearman_rank_correlation",
    "bootstrap_95pct_lower",
    "bootstrap_95pct_upper",
    "negative_direction",
    "interval_excludes_zero_below",
)

TIER_FIELDS = (
    "score_kind",
    "week_end",
    "development_seasons",
    "development_team_season_count",
    "low_max_inclusive",
    "middle_max_inclusive",
    "method",
)

CALIBRATION_FIELDS = (
    "score_kind",
    "week_end",
    "metric",
    "tier",
    "development_count",
    "nominal_coverage",
    "finite_sample_rank",
    "normalized_residual_radius",
)

COVERAGE_PREDICTION_FIELDS = (
    "score_kind",
    "target_season",
    "week_end",
    "team",
    "caller_cohort",
    "metric",
    "score_lower_bound",
    "tier",
    "normalized_absolute_error",
    "tier_normalized_radius",
    "tier_covered",
    "global_metric_normalized_radius",
    "global_metric_covered",
)

COVERAGE_SUMMARY_FIELDS = (
    "score_kind",
    "interval_method",
    "target_season",
    "week_end",
    "tier",
    "team_count",
    "comparison_count",
    "covered_count",
    "coverage_rate",
    "wilson_95pct_lower",
    "wilson_95pct_upper",
    "mean_normalized_radius",
)


class HistoricalCertaintyDataError(ValueError):
    """Raised when score-diagnostic inputs violate their provenance contract."""


@dataclass(frozen=True)
class BacktestInput:
    path: Path
    target_season: int
    windows: tuple[int, ...]
    predictions: tuple[Mapping[str, str], ...]
    teams: tuple[Mapping[str, str], ...]
    raw_by_path: Mapping[str, bytes]


@dataclass(frozen=True)
class ContinuityInput:
    path: Path
    target_season: int
    teams: Mapping[str, Mapping[str, str]]
    raw_by_path: Mapping[str, bytes]


@dataclass(frozen=True)
class HistoricalCertaintyResult:
    target_seasons: tuple[int, ...]
    development_seasons: tuple[int, ...]
    holdout_season: int
    windows: tuple[int, ...]
    bootstrap_samples: int
    random_seed: int
    input_paths: tuple[Path, ...]
    input_hashes: Mapping[str, str]
    team_score_rows: tuple[Mapping[str, Any], ...]
    team_error_rows: tuple[Mapping[str, Any], ...]
    rank_rows: tuple[Mapping[str, Any], ...]
    tier_rows: tuple[Mapping[str, Any], ...]
    calibration_rows: tuple[Mapping[str, Any], ...]
    coverage_prediction_rows: tuple[Mapping[str, Any], ...]
    coverage_summary_rows: tuple[Mapping[str, Any], ...]
    evaluation: Mapping[str, Any]


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HistoricalCertaintyDataError(f"{context} must be an object")
    return value


def _integer(value: Any, context: str) -> int:
    if isinstance(value, bool):
        raise HistoricalCertaintyDataError(f"{context} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise HistoricalCertaintyDataError(f"{context} must be an integer") from error


def _finite(value: Any, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise HistoricalCertaintyDataError(f"{context} must be numeric") from error
    if not math.isfinite(result):
        raise HistoricalCertaintyDataError(f"{context} must be finite")
    return result


def _boolean(value: str, context: str, *, allow_blank: bool = False) -> bool | None:
    normalized = value.strip().casefold()
    if allow_blank and not normalized:
        return None
    if normalized not in {"true", "false"}:
        raise HistoricalCertaintyDataError(f"{context} must be true or false")
    return normalized == "true"


def _read_csv(raw: bytes, required: set[str], context: str) -> list[dict[str, str]]:
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    except UnicodeDecodeError as error:
        raise HistoricalCertaintyDataError(f"{context} is not UTF-8") from error
    fields = set(rows[0]) if rows else set()
    missing = required - fields
    if not rows or missing:
        raise HistoricalCertaintyDataError(
            f"{context} has no rows or is missing fields {sorted(missing)}"
        )
    return rows


def _verified_file(path: Path, expected_hash: str, context: str) -> bytes:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise HistoricalCertaintyDataError(f"{context} is unavailable: {path}") from error
    observed = _sha256(raw)
    if observed != expected_hash:
        raise HistoricalCertaintyDataError(
            f"{context} hash mismatch: expected {expected_hash}, observed {observed}"
        )
    return raw


def _merge_raw(destination: dict[str, bytes], source: Mapping[str, bytes]) -> None:
    for path, raw in source.items():
        existing = destination.get(path)
        if existing is not None and existing != raw:
            raise HistoricalCertaintyDataError(
                f"input path was observed with conflicting bytes: {path}"
            )
        destination[path] = raw


def _load_backtest(path: str | Path) -> BacktestInput:
    root = Path(path)
    if not root.is_dir():
        raise HistoricalCertaintyDataError(f"backtest is not a directory: {root}")
    manifest_path = root / "manifest.json"
    try:
        manifest_raw = manifest_path.read_bytes()
        manifest = _mapping(json.loads(manifest_raw.decode("utf-8")), "backtest manifest")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HistoricalCertaintyDataError(
            f"invalid backtest manifest: {manifest_path}"
        ) from error
    if manifest.get("schema_version") != "1.0.0":
        raise HistoricalCertaintyDataError(f"unsupported backtest schema: {root}")
    if manifest.get("model_version") != BACKTEST_MODEL_VERSION:
        raise HistoricalCertaintyDataError(f"unsupported backtest model: {root}")
    seasons = _mapping(manifest.get("seasons"), "backtest manifest.seasons")
    target = _integer(seasons.get("target"), "backtest target season")
    raw_windows = seasons.get("target_windows")
    if not isinstance(raw_windows, list) or not raw_windows:
        raise HistoricalCertaintyDataError("backtest target_windows must be a list")
    try:
        windows = tuple(sorted(int(str(item).rsplit("-", 1)[1]) for item in raw_windows))
    except (IndexError, ValueError) as error:
        raise HistoricalCertaintyDataError("backtest has invalid target window labels") from error

    raw_by_path: dict[str, bytes] = {str(manifest_path): manifest_raw}
    parent_inputs = _mapping(manifest.get("input_sha256"), "backtest input_sha256")
    if not parent_inputs:
        raise HistoricalCertaintyDataError(f"backtest has no bound source inputs: {root}")
    for source, expected in parent_inputs.items():
        if not isinstance(source, str) or not isinstance(expected, str):
            raise HistoricalCertaintyDataError(f"invalid backtest input hash: {root}")
        source_path = Path(source)
        raw_by_path[str(source_path)] = _verified_file(
            source_path, expected, "bound backtest input"
        )

    artifacts = _mapping(manifest.get("artifacts"), "backtest artifacts")
    loaded: dict[str, bytes] = {}
    for filename in ("predictions.csv", "teams.csv"):
        entry = _mapping(artifacts.get(filename), f"backtest artifact {filename}")
        expected = entry.get("sha256")
        if not isinstance(expected, str):
            raise HistoricalCertaintyDataError(f"backtest lacks hash for {filename}")
        artifact_path = root / filename
        loaded[filename] = _verified_file(
            artifact_path, expected, "backtest artifact"
        )
        raw_by_path[str(artifact_path)] = loaded[filename]

    predictions = _read_csv(
        loaded["predictions.csv"],
        {
            "target_season",
            "week_start",
            "week_end",
            "team",
            "caller_cohort",
            "metric",
            "model",
            "tolerance",
            "absolute_error",
            "normalized_absolute_error",
        },
        str(root / "predictions.csv"),
    )
    teams = _read_csv(
        loaded["teams.csv"],
        {
            "target_season",
            "week_end",
            "team",
            "opening_caller",
            "prior_caller",
            "caller_cohort",
            "excluded",
        },
        str(root / "teams.csv"),
    )
    if any(_integer(row["target_season"], "prediction season") != target for row in predictions):
        raise HistoricalCertaintyDataError(f"backtest prediction season mismatch: {root}")
    if any(_integer(row["target_season"], "team season") != target for row in teams):
        raise HistoricalCertaintyDataError(f"backtest team season mismatch: {root}")
    return BacktestInput(
        path=root,
        target_season=target,
        windows=windows,
        predictions=tuple(predictions),
        teams=tuple(teams),
        raw_by_path=raw_by_path,
    )


def _load_continuity(path: str | Path) -> ContinuityInput:
    root = Path(path)
    if not root.is_dir():
        raise HistoricalCertaintyDataError(
            f"staff continuity is not a directory: {root}"
        )
    manifest_path = root / "manifest.json"
    try:
        manifest_raw = manifest_path.read_bytes()
        manifest = _mapping(
            json.loads(manifest_raw.decode("utf-8")), "continuity manifest"
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HistoricalCertaintyDataError(
            f"invalid continuity manifest: {manifest_path}"
        ) from error
    if manifest.get("schema_version") != "1.0.0":
        raise HistoricalCertaintyDataError(f"unsupported continuity schema: {root}")
    if manifest.get("model_status") != CONTINUITY_MODEL_STATUS:
        raise HistoricalCertaintyDataError(f"unsupported continuity status: {root}")
    target = _integer(manifest.get("season"), "continuity season")
    raw_by_path: dict[str, bytes] = {str(manifest_path): manifest_raw}
    inputs = _mapping(manifest.get("inputs"), "continuity inputs")
    for label, value in inputs.items():
        if value is None:
            continue
        entry = _mapping(value, f"continuity input {label}")
        source = entry.get("path")
        expected = entry.get("sha256")
        if not isinstance(source, str) or not isinstance(expected, str):
            raise HistoricalCertaintyDataError(
                f"continuity input {label} lacks path/hash"
            )
        source_path = Path(source)
        raw_by_path[str(source_path)] = _verified_file(
            source_path, expected, "bound continuity input"
        )
    artifacts = _mapping(manifest.get("artifacts"), "continuity artifacts")
    entry = _mapping(artifacts.get("teams.csv"), "continuity teams artifact")
    expected = entry.get("sha256")
    if not isinstance(expected, str):
        raise HistoricalCertaintyDataError("continuity teams artifact lacks hash")
    teams_path = root / "teams.csv"
    teams_raw = _verified_file(teams_path, expected, "continuity teams artifact")
    raw_by_path[str(teams_path)] = teams_raw
    rows = _read_csv(
        teams_raw,
        {
            "season",
            "team",
            "current_play_caller",
            "same_play_caller",
            "play_caller_on_prior_staff",
            "head_coach_status",
            "staff_continuity_index_v0",
            "unavailable_core_responsibility_count",
        },
        str(teams_path),
    )
    by_team: dict[str, Mapping[str, str]] = {}
    for row in rows:
        if _integer(row["season"], "continuity row season") != target:
            raise HistoricalCertaintyDataError(
                f"continuity row season mismatch: {teams_path}"
            )
        team = row["team"].strip().upper()
        if not team or team in by_team:
            raise HistoricalCertaintyDataError(
                f"continuity has blank or duplicate team: {teams_path}"
            )
        by_team[team] = row
    return ContinuityInput(
        path=root,
        target_season=target,
        teams=by_team,
        raw_by_path=raw_by_path,
    )


def _caller_component(
    *, same: bool, cohort: str, on_prior_staff: bool, has_anchor: bool
) -> float:
    if same:
        return 1.0
    if cohort == "changed_with_prior_year_anchor":
        return 0.75
    if on_prior_staff:
        return 0.65 if has_anchor else 0.60
    if has_anchor:
        return 0.50
    return 0.15


def _score_row(
    *,
    season: int,
    team_row: Mapping[str, str],
    continuity: Mapping[str, str],
) -> Mapping[str, Any]:
    team = team_row["team"].strip().upper()
    cohort = team_row["caller_cohort"].strip()
    same = _boolean(
        continuity["same_play_caller"],
        f"{season} {team} same caller",
        allow_blank=True,
    )
    on_prior_staff = _boolean(
        continuity["play_caller_on_prior_staff"],
        f"{season} {team} caller on prior staff",
        allow_blank=True,
    )
    ambiguous = cohort == "ambiguous_opening_caller"
    if ambiguous:
        if same is not None or on_prior_staff is not None:
            raise HistoricalCertaintyDataError(
                f"{season} {team} ambiguous identity was resolved in continuity data"
            )
        return {
            "target_season": season,
            "team": team,
            "opening_caller": team_row["opening_caller"],
            "prior_caller": team_row["prior_caller"],
            "caller_cohort": cohort,
            "score_status": "excluded_ambiguous_preseason_caller",
            "same_play_caller": "",
            "play_caller_on_prior_staff": "",
            "head_coach_continuity": str(
                continuity["head_coach_status"].strip() == "retained_holder"
            ).lower(),
            "staff_continuity_index_v0": continuity[
                "staff_continuity_index_v0"
            ],
            "unavailable_core_responsibility_count": continuity[
                "unavailable_core_responsibility_count"
            ],
            "one_year_anchor_available": "",
            "effective_anchor_strength": "",
            "fingerprint_stability": "",
            "caller_continuity_component": "",
            "scheme_component_status": "missing_ambiguous_identity",
            "broad_known_weight": "",
            "broad_system_certainty_lower_bound": "",
            "broad_system_certainty_upper_bound": "",
            "exact_known_weight": "",
            "exact_style_certainty_lower_bound": "",
            "exact_style_certainty_upper_bound": "",
            "exact_transition_ceiling_applied": "",
        }
    if same is None or on_prior_staff is None:
        raise HistoricalCertaintyDataError(
            f"{season} {team} confirmed caller has blank continuity fields"
        )
    expected_same = cohort == "returning_caller"
    if same != expected_same:
        raise HistoricalCertaintyDataError(
            f"{season} {team} caller cohort conflicts with staff continuity"
        )
    if cohort not in {
        "returning_caller",
        "changed_with_prior_year_anchor",
        "changed_without_prior_year_anchor",
    }:
        raise HistoricalCertaintyDataError(
            f"{season} {team} has unsupported caller cohort {cohort!r}"
        )
    staff = _finite(
        continuity["staff_continuity_index_v0"],
        f"{season} {team} staff continuity",
    ) / 100
    if not 0 <= staff <= 1:
        raise HistoricalCertaintyDataError(
            f"{season} {team} staff continuity must be in [0,100]"
        )
    unavailable = _integer(
        continuity["unavailable_core_responsibility_count"],
        f"{season} {team} unavailable core responsibilities",
    )
    if not 0 <= unavailable <= 7:
        raise HistoricalCertaintyDataError(
            f"{season} {team} unavailable core responsibilities is invalid"
        )
    head_coach_continuity = (
        continuity["head_coach_status"].strip() == "retained_holder"
    )
    has_anchor = cohort in {
        "returning_caller",
        "changed_with_prior_year_anchor",
    }
    anchor_strength = 1 / 2.2 if has_anchor else 0.0
    stability = 0.45 if has_anchor else 0.20
    caller_component = _caller_component(
        same=same,
        cohort=cohort,
        on_prior_staff=on_prior_staff,
        has_anchor=has_anchor,
    )

    broad_known = (
        0.20
        + 0.15 * anchor_strength
        + 0.05 * staff
        + 0.05 * float(head_coach_continuity)
    )
    exact_known = (
        0.10
        + 0.15 * caller_component
        + 0.18 * anchor_strength
        + 0.12 * staff
        + 0.08 * float(head_coach_continuity)
        + 0.12 * stability
    )
    if same:
        broad_lower = broad_upper = 100 * (broad_known + 0.45 + 0.10)
        exact_lower = exact_upper = 100 * (exact_known + 0.15 + 0.10)
        broad_weight = exact_weight = 1.0
        scheme_status = "same_caller_destination_components_reconstructible"
        ceiling_applied = False
    else:
        broad_lower = 100 * broad_known
        broad_upper = 100 * (broad_known + 0.45 + 0.10)
        raw_exact_lower = 100 * exact_known
        raw_exact_upper = 100 * (exact_known + 0.15 + 0.10)
        exact_lower = min(raw_exact_lower, 79.0)
        exact_upper = min(raw_exact_upper, 79.0)
        broad_weight = 0.45
        exact_weight = 0.75
        scheme_status = "changed_caller_scheme_and_destination_components_missing"
        ceiling_applied = raw_exact_upper > 79.0 or raw_exact_lower > 79.0
    return {
        "target_season": season,
        "team": team,
        "opening_caller": team_row["opening_caller"],
        "prior_caller": team_row["prior_caller"],
        "caller_cohort": cohort,
        "score_status": "eligible_one_year_lower_bound_diagnostic",
        "same_play_caller": str(same).lower(),
        "play_caller_on_prior_staff": str(on_prior_staff).lower(),
        "head_coach_continuity": str(head_coach_continuity).lower(),
        "staff_continuity_index_v0": round(100 * staff, 1),
        "unavailable_core_responsibility_count": unavailable,
        "one_year_anchor_available": str(has_anchor).lower(),
        "effective_anchor_strength": round(anchor_strength, 6),
        "fingerprint_stability": round(stability, 6),
        "caller_continuity_component": round(caller_component, 3),
        "scheme_component_status": scheme_status,
        "broad_known_weight": broad_weight,
        "broad_system_certainty_lower_bound": round(broad_lower, 6),
        "broad_system_certainty_upper_bound": round(broad_upper, 6),
        "exact_known_weight": exact_weight,
        "exact_style_certainty_lower_bound": round(exact_lower, 6),
        "exact_style_certainty_upper_bound": round(exact_upper, 6),
        "exact_transition_ceiling_applied": str(ceiling_applied).lower(),
    }


def _average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        end = index
        while end + 1 < len(order) and values[order[end + 1]] == values[order[index]]:
            end += 1
        rank = 1 + (index + end) / 2
        for position in range(index, end + 1):
            ranks[order[position]] = rank
        index = end + 1
    return ranks


def _spearman(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        raise HistoricalCertaintyDataError("Spearman correlation needs paired rows")
    left_ranks = _average_ranks(left)
    right_ranks = _average_ranks(right)
    left_mean = statistics.mean(left_ranks)
    right_mean = statistics.mean(right_ranks)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left_ranks, right_ranks)
    )
    denominator = math.sqrt(
        sum((value - left_mean) ** 2 for value in left_ranks)
        * sum((value - right_mean) ** 2 for value in right_ranks)
    )
    if denominator == 0:
        raise HistoricalCertaintyDataError("Spearman correlation has constant ranks")
    return numerator / denominator


def _percentile(values: list[float], probability: float) -> float:
    if not values or not 0 <= probability <= 1:
        raise HistoricalCertaintyDataError("percentile needs data and p in [0,1]")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _bootstrap_spearman(
    rows: list[Mapping[str, Any]],
    *,
    score_field: str,
    samples: int,
    seed: str,
) -> tuple[float, float]:
    generator = random.Random(seed)
    estimates: list[float] = []
    for _ in range(samples):
        sampled = [rows[generator.randrange(len(rows))] for _ in rows]
        try:
            estimates.append(
                _spearman(
                    [float(row[score_field]) for row in sampled],
                    [float(row["mean_normalized_absolute_error"]) for row in sampled],
                )
            )
        except HistoricalCertaintyDataError:
            continue
    if len(estimates) < max(50, samples // 2):
        raise HistoricalCertaintyDataError(
            "too many degenerate Spearman bootstrap samples"
        )
    return _percentile(estimates, 0.025), _percentile(estimates, 0.975)


def _conformal(values: list[float]) -> tuple[int, float]:
    if not values:
        raise HistoricalCertaintyDataError("cannot calibrate an empty residual set")
    rank = min(len(values), math.ceil((len(values) + 1) * NOMINAL_COVERAGE))
    return rank, sorted(values)[rank - 1]


def _tier(value: float, low_max: float, middle_max: float) -> str:
    if value <= low_max:
        return "low"
    if value <= middle_max:
        return "middle"
    return "high"


def _wilson(successes: int, total: int) -> tuple[float, float]:
    if total <= 0 or not 0 <= successes <= total:
        raise HistoricalCertaintyDataError("Wilson interval counts are invalid")
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    spread = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total + z * z / (4 * total * total)
        )
        / denominator
    )
    return max(0.0, center - spread), min(1.0, center + spread)


def _coverage_summary(
    rows: list[Mapping[str, Any]],
    *,
    score_kind: str,
    method: str,
    season: int,
    week_end: int,
    tier: str,
) -> Mapping[str, Any]:
    radius_field = (
        "tier_normalized_radius"
        if method == "score_tier_metric"
        else "global_metric_normalized_radius"
    )
    covered_field = "tier_covered" if method == "score_tier_metric" else "global_metric_covered"
    successes = sum(str(row[covered_field]).casefold() == "true" for row in rows)
    lower, upper = _wilson(successes, len(rows))
    return {
        "score_kind": score_kind,
        "interval_method": method,
        "target_season": season,
        "week_end": week_end,
        "tier": tier,
        "team_count": len({str(row["team"]) for row in rows}),
        "comparison_count": len(rows),
        "covered_count": successes,
        "coverage_rate": round(successes / len(rows), 6),
        "wilson_95pct_lower": round(lower, 6),
        "wilson_95pct_upper": round(upper, 6),
        "mean_normalized_radius": round(
            statistics.mean(float(row[radius_field]) for row in rows), 6
        ),
    }


def build_historical_certainty_evaluation(
    backtests: Iterable[str | Path],
    continuities: Iterable[str | Path],
    *,
    development_seasons: Iterable[int] = (2023, 2024),
    holdout_season: int = 2025,
    bootstrap_samples: int = 5000,
    random_seed: int = 20260903,
    expected_team_count: int = 32,
    expected_metric_count: int = 23,
) -> HistoricalCertaintyResult:
    """Reconstruct score bounds and evaluate lower bounds on a held-out season."""

    development = tuple(sorted(set(development_seasons)))
    if len(development) < 2 or holdout_season in development:
        raise HistoricalCertaintyDataError(
            "use at least two development seasons and a separate holdout"
        )
    if bootstrap_samples < 100:
        raise HistoricalCertaintyDataError("bootstrap_samples must be at least 100")
    if expected_team_count < 3 or expected_metric_count < 1:
        raise HistoricalCertaintyDataError("expected coverage values are invalid")

    backtest_rows = tuple(_load_backtest(path) for path in backtests)
    continuity_rows = tuple(_load_continuity(path) for path in continuities)
    backtest_by_season = {item.target_season: item for item in backtest_rows}
    continuity_by_season = {item.target_season: item for item in continuity_rows}
    expected_seasons = set(development) | {holdout_season}
    if (
        len(backtest_by_season) != len(backtest_rows)
        or len(continuity_by_season) != len(continuity_rows)
        or set(backtest_by_season) != expected_seasons
        or set(continuity_by_season) != expected_seasons
    ):
        raise HistoricalCertaintyDataError(
            "backtest and continuity snapshots must cover each declared season once"
        )
    window_sets = {item.windows for item in backtest_rows}
    if len(window_sets) != 1:
        raise HistoricalCertaintyDataError("backtests must share target windows")
    windows = next(iter(window_sets))

    input_raw: dict[str, bytes] = {}
    for item in (*backtest_rows, *continuity_rows):
        _merge_raw(input_raw, item.raw_by_path)

    score_rows: list[Mapping[str, Any]] = []
    scores_by_key: dict[tuple[int, str], Mapping[str, Any]] = {}
    for season in sorted(expected_seasons):
        backtest = backtest_by_season[season]
        continuity = continuity_by_season[season]
        team_evidence: dict[str, Mapping[str, str]] = {}
        for row in backtest.teams:
            team = row["team"].strip().upper()
            week = _integer(row["week_end"], f"{season} {team} team week")
            if week not in windows:
                raise HistoricalCertaintyDataError(
                    f"{season} {team} has an undeclared team window"
                )
            comparable = {
                key: row[key]
                for key in ("team", "opening_caller", "prior_caller", "caller_cohort")
            }
            existing = team_evidence.get(team)
            if existing is not None and any(
                existing[key] != comparable[key] for key in comparable
            ):
                raise HistoricalCertaintyDataError(
                    f"{season} {team} identity/cohort changes across windows"
                )
            team_evidence[team] = comparable
        if (
            len(team_evidence) != expected_team_count
            or set(team_evidence) != set(continuity.teams)
        ):
            raise HistoricalCertaintyDataError(
                f"{season} team coverage differs between backtest and continuity"
            )
        for team in sorted(team_evidence):
            row = _score_row(
                season=season,
                team_row=team_evidence[team],
                continuity=continuity.teams[team],
            )
            score_rows.append(row)
            scores_by_key[(season, team)] = row

    metric_error_rows: list[Mapping[str, Any]] = []
    grouped_errors: dict[tuple[int, int, str], list[float]] = defaultdict(list)
    cohort_by_group: dict[tuple[int, int, str], str] = {}
    metrics_by_group: dict[tuple[int, int, str], set[str]] = defaultdict(set)
    for season in sorted(expected_seasons):
        for row in backtest_by_season[season].predictions:
            if row["model"] != CANDIDATE_MODEL:
                continue
            team = row["team"].strip().upper()
            week_end = _integer(row["week_end"], f"{season} {team} prediction week")
            if week_end not in windows:
                raise HistoricalCertaintyDataError(
                    f"{season} {team} prediction has undeclared window"
                )
            score = scores_by_key[(season, team)]
            if score["score_status"] != "eligible_one_year_lower_bound_diagnostic":
                raise HistoricalCertaintyDataError(
                    f"{season} {team} has predictions despite an unavailable score"
                )
            tolerance = _finite(row["tolerance"], f"{season} {team} tolerance")
            absolute_error = _finite(
                row["absolute_error"], f"{season} {team} absolute error"
            )
            normalized_error = _finite(
                row["normalized_absolute_error"],
                f"{season} {team} normalized error",
            )
            if tolerance <= 0 or abs(normalized_error - absolute_error / tolerance) > 0.0001:
                raise HistoricalCertaintyDataError(
                    f"{season} {team} normalized error does not reproduce"
                )
            key = (season, week_end, team)
            metric = row["metric"].strip()
            if not metric or metric in metrics_by_group[key]:
                raise HistoricalCertaintyDataError(
                    f"{season} {team} has blank/duplicate metric in Weeks 1-{week_end}"
                )
            metrics_by_group[key].add(metric)
            grouped_errors[key].append(normalized_error)
            cohort = row["caller_cohort"].strip()
            if key in cohort_by_group and cohort_by_group[key] != cohort:
                raise HistoricalCertaintyDataError(
                    f"{season} {team} cohort changes within a prediction window"
                )
            cohort_by_group[key] = cohort
            metric_error_rows.append(
                {
                    "target_season": season,
                    "week_end": week_end,
                    "team": team,
                    "caller_cohort": cohort,
                    "metric": metric,
                    "normalized_absolute_error": normalized_error,
                    "broad_system_lower_bound": float(
                        score["broad_system_certainty_lower_bound"]
                    ),
                    "exact_style_lower_bound": float(
                        score["exact_style_certainty_lower_bound"]
                    ),
                }
            )
    if not metric_error_rows:
        raise HistoricalCertaintyDataError("no caller-aware prediction errors found")
    for key, metrics in metrics_by_group.items():
        if len(metrics) != expected_metric_count:
            raise HistoricalCertaintyDataError(
                f"{key} has {len(metrics)} metrics; expected {expected_metric_count}"
            )

    team_error_rows: list[Mapping[str, Any]] = []
    for (season, week_end, team), errors in sorted(grouped_errors.items()):
        score = scores_by_key[(season, team)]
        team_error_rows.append(
            {
                "target_season": season,
                "week_start": 1,
                "week_end": week_end,
                "team": team,
                "caller_cohort": cohort_by_group[(season, week_end, team)],
                "metric_count": len(errors),
                "broad_system_lower_bound": round(
                    float(score["broad_system_certainty_lower_bound"]), 6
                ),
                "exact_style_lower_bound": round(
                    float(score["exact_style_certainty_lower_bound"]), 6
                ),
                "mean_normalized_absolute_error": round(statistics.mean(errors), 6),
                "median_normalized_absolute_error": round(statistics.median(errors), 6),
            }
        )

    rank_rows: list[Mapping[str, Any]] = []
    tier_rows: list[Mapping[str, Any]] = []
    calibration_rows: list[Mapping[str, Any]] = []
    coverage_prediction_rows: list[Mapping[str, Any]] = []
    coverage_summary_rows: list[Mapping[str, Any]] = []
    score_field = {
        "broad_system_lower_bound": "broad_system_lower_bound",
        "exact_style_lower_bound": "exact_style_lower_bound",
    }
    tier_definitions: dict[tuple[str, int], tuple[float, float]] = {}
    for kind in SCORE_KINDS:
        field = score_field[kind]
        for week_end in windows:
            for scope, scope_seasons in (
                ("development", development),
                ("holdout", (holdout_season,)),
            ):
                rows = [
                    row
                    for row in team_error_rows
                    if int(row["week_end"]) == week_end
                    and int(row["target_season"]) in scope_seasons
                ]
                if len(rows) < 3:
                    raise HistoricalCertaintyDataError(
                        f"{kind} {scope} Weeks 1-{week_end} has too few team-seasons"
                    )
                correlation = _spearman(
                    [float(row[field]) for row in rows],
                    [float(row["mean_normalized_absolute_error"]) for row in rows],
                )
                lower, upper = _bootstrap_spearman(
                    rows,
                    score_field=field,
                    samples=bootstrap_samples,
                    seed=f"{random_seed}|{kind}|{scope}|{week_end}",
                )
                rank_rows.append(
                    {
                        "score_kind": kind,
                        "scope": scope,
                        "scope_seasons": "|".join(map(str, scope_seasons)),
                        "week_end": week_end,
                        "team_season_count": len(rows),
                        "spearman_rank_correlation": round(correlation, 6),
                        "bootstrap_95pct_lower": round(lower, 6),
                        "bootstrap_95pct_upper": round(upper, 6),
                        "negative_direction": str(correlation < 0).lower(),
                        "interval_excludes_zero_below": str(upper < 0).lower(),
                    }
                )

            development_team_rows = [
                row
                for row in team_error_rows
                if int(row["week_end"]) == week_end
                and int(row["target_season"]) in development
            ]
            low_max = _percentile(
                [float(row[field]) for row in development_team_rows], 1 / 3
            )
            middle_max = _percentile(
                [float(row[field]) for row in development_team_rows], 2 / 3
            )
            if low_max >= middle_max:
                raise HistoricalCertaintyDataError(
                    f"{kind} development tertiles collapse in Weeks 1-{week_end}"
                )
            tier_definitions[(kind, week_end)] = (low_max, middle_max)
            tier_rows.append(
                {
                    "score_kind": kind,
                    "week_end": week_end,
                    "development_seasons": "|".join(map(str, development)),
                    "development_team_season_count": len(development_team_rows),
                    "low_max_inclusive": round(low_max, 6),
                    "middle_max_inclusive": round(middle_max, 6),
                    "method": "development_only_linear_tertiles",
                }
            )

            development_metric_rows = [
                row
                for row in metric_error_rows
                if int(row["week_end"]) == week_end
                and int(row["target_season"]) in development
            ]
            holdout_metric_rows = [
                row
                for row in metric_error_rows
                if int(row["week_end"]) == week_end
                and int(row["target_season"]) == holdout_season
            ]
            metrics = sorted({str(row["metric"]) for row in development_metric_rows})
            if (
                len(metrics) != expected_metric_count
                or set(metrics)
                != {str(row["metric"]) for row in holdout_metric_rows}
            ):
                raise HistoricalCertaintyDataError(
                    f"{kind} metric coverage differs across data split"
                )
            tier_radii: dict[tuple[str, str], float] = {}
            global_radii: dict[str, float] = {}
            for metric in metrics:
                global_values = [
                    float(row["normalized_absolute_error"])
                    for row in development_metric_rows
                    if row["metric"] == metric
                ]
                global_rank, global_radius = _conformal(global_values)
                global_radii[metric] = global_radius
                calibration_rows.append(
                    {
                        "score_kind": kind,
                        "week_end": week_end,
                        "metric": metric,
                        "tier": "global",
                        "development_count": len(global_values),
                        "nominal_coverage": NOMINAL_COVERAGE,
                        "finite_sample_rank": global_rank,
                        "normalized_residual_radius": round(global_radius, 6),
                    }
                )
                for tier in TIERS:
                    values = [
                        float(row["normalized_absolute_error"])
                        for row in development_metric_rows
                        if row["metric"] == metric
                        and _tier(float(row[field]), low_max, middle_max) == tier
                    ]
                    rank, radius = _conformal(values)
                    tier_radii[(metric, tier)] = radius
                    calibration_rows.append(
                        {
                            "score_kind": kind,
                            "week_end": week_end,
                            "metric": metric,
                            "tier": tier,
                            "development_count": len(values),
                            "nominal_coverage": NOMINAL_COVERAGE,
                            "finite_sample_rank": rank,
                            "normalized_residual_radius": round(radius, 6),
                        }
                    )
            current_coverage: list[Mapping[str, Any]] = []
            for row in holdout_metric_rows:
                score = float(row[field])
                assigned = _tier(score, low_max, middle_max)
                metric = str(row["metric"])
                error = float(row["normalized_absolute_error"])
                tier_radius = tier_radii[(metric, assigned)]
                global_radius = global_radii[metric]
                result_row = {
                    "score_kind": kind,
                    "target_season": holdout_season,
                    "week_end": week_end,
                    "team": row["team"],
                    "caller_cohort": row["caller_cohort"],
                    "metric": metric,
                    "score_lower_bound": round(score, 6),
                    "tier": assigned,
                    "normalized_absolute_error": round(error, 6),
                    "tier_normalized_radius": round(tier_radius, 6),
                    "tier_covered": str(error <= tier_radius).lower(),
                    "global_metric_normalized_radius": round(global_radius, 6),
                    "global_metric_covered": str(error <= global_radius).lower(),
                }
                current_coverage.append(result_row)
                coverage_prediction_rows.append(result_row)
            for tier in TIERS:
                rows = [row for row in current_coverage if row["tier"] == tier]
                if not rows:
                    raise HistoricalCertaintyDataError(
                        f"{kind} holdout has no {tier} tier in Weeks 1-{week_end}"
                    )
                coverage_summary_rows.append(
                    _coverage_summary(
                        rows,
                        score_kind=kind,
                        method="score_tier_metric",
                        season=holdout_season,
                        week_end=week_end,
                        tier=tier,
                    )
                )
            coverage_summary_rows.append(
                _coverage_summary(
                    current_coverage,
                    score_kind=kind,
                    method="score_tier_metric",
                    season=holdout_season,
                    week_end=week_end,
                    tier="all",
                )
            )
            coverage_summary_rows.append(
                _coverage_summary(
                    current_coverage,
                    score_kind=kind,
                    method="global_metric",
                    season=holdout_season,
                    week_end=week_end,
                    tier="all",
                )
            )

    rank_lookup = {
        (row["score_kind"], row["scope"], int(row["week_end"])): row
        for row in rank_rows
    }
    coverage_lookup = {
        (
            row["score_kind"],
            row["interval_method"],
            int(row["week_end"]),
            row["tier"],
        ): row
        for row in coverage_summary_rows
    }
    score_decisions: list[Mapping[str, Any]] = []
    for kind in SCORE_KINDS:
        negative_direction = all(
            float(rank_lookup[(kind, "holdout", week)]["spearman_rank_correlation"])
            < 0
            for week in windows
        )
        negative_interval = all(
            float(rank_lookup[(kind, "holdout", week)]["bootstrap_95pct_upper"])
            < 0
            for week in windows
        )
        all_tier_coverage = all(
            float(
                coverage_lookup[(kind, "score_tier_metric", week, tier)][
                    "coverage_rate"
                ]
            )
            >= NOMINAL_COVERAGE
            for week in windows
            for tier in TIERS
        )
        aggregate_coverage = all(
            float(
                coverage_lookup[(kind, "score_tier_metric", week, "all")][
                    "coverage_rate"
                ]
            )
            >= NOMINAL_COVERAGE
            for week in windows
        )
        no_wider_than_global = all(
            float(
                coverage_lookup[(kind, "score_tier_metric", week, "all")][
                    "mean_normalized_radius"
                ]
            )
            <= float(
                coverage_lookup[(kind, "global_metric", week, "all")][
                    "mean_normalized_radius"
                ]
            )
            for week in windows
        )
        promoted = all(
            (
                negative_direction,
                negative_interval,
                all_tier_coverage,
                aggregate_coverage,
                no_wider_than_global,
            )
        )
        score_decisions.append(
            {
                "score_kind": kind,
                "holdout_negative_rank_direction_both_windows": negative_direction,
                "holdout_rank_interval_below_zero_both_windows": negative_interval,
                "every_holdout_tier_at_nominal_coverage": all_tier_coverage,
                "aggregate_holdout_coverage_at_nominal": aggregate_coverage,
                "tiered_mean_radius_no_wider_than_global": no_wider_than_global,
                "promotion_gate_pass": promoted,
            }
        )

    worst_cases = {
        str(week): [
            {
                "team": row["team"],
                "caller_cohort": row["caller_cohort"],
                "broad_system_lower_bound": row["broad_system_lower_bound"],
                "exact_style_lower_bound": row["exact_style_lower_bound"],
                "mean_normalized_absolute_error": row[
                    "mean_normalized_absolute_error"
                ],
            }
            for row in sorted(
                (
                    row
                    for row in team_error_rows
                    if int(row["target_season"]) == holdout_season
                    and int(row["week_end"]) == week
                ),
                key=lambda row: -float(row["mean_normalized_absolute_error"]),
            )[:5]
        ]
        for week in windows
    }
    evaluation: dict[str, Any] = {
        "status": "completed_one_year_lower_bound_diagnostic_not_current_score_calibration",
        "data_split": {
            "development_seasons": list(development),
            "holdout_season": holdout_season,
            "target_windows": [f"Weeks 1-{week}" for week in windows],
            "holdout_was_not_used_for_tier_boundaries_or_residual_radii": True,
        },
        "score_reconstruction": {
            "parent_model": "caller-fingerprint-heuristic-v0.1.0",
            "identity_strength": "1.0 only for source-confirmed preseason callers; ambiguous identities are excluded",
            "history_policy": "one immediately prior opening-caller season only; one anchor contributes 1/2.2 effective strength and 0.45 stability",
            "returning_caller_scheme_policy": "same-caller scheme identity and destination continuity are each reconstructible as 1.0, matching the current rubric",
            "changed_caller_scheme_policy": "time-correct structured scheme and destination-continuity evidence was not reconstructed; report 0-to-1 score bounds and evaluate only the conservative lower bound",
            "missing_values": "never replaced with a neutral midpoint",
        },
        "rank_diagnostics": rank_rows,
        "conditional_interval_diagnostics": coverage_summary_rows,
        "promotion_gate": {
            "criteria": {
                "rank": "held-out Spearman association must be negative with its team-resampled 95% interval below zero in both windows",
                "coverage": "every held-out score tier and the aggregate must attain at least 90% marginal metric coverage in both windows",
                "efficiency": "score-tiered mean normalized radius must be no wider than the per-metric global radius in both windows",
            },
            "score_results": score_decisions,
            "decision": "do_not_condition_2026_style_intervals_on_v0_certainty_scores",
        },
        "recommended_2026_policy": (
            "Keep broad-system and exact-style values as evidence indices only. Use the "
            "development-calibrated per-metric global residual bands for numeric style "
            "uncertainty; do not narrow them for a high evidence score. Preserve the "
            "prospective 2026 freeze so post-season results can test the richer current score."
        ),
        "holdout_worst_team_cases": worst_cases,
        "limitations": [
            "Only three target seasons are available, with 2025 used once as holdout.",
            "Changed-caller scheme-family and destination-continuity research is missing historically, so current full 0-100 scores are not calibrated.",
            "The one-year anchor policy is intentionally narrower than the richer 2026 multi-season caller history.",
            "A few official record books omit one position-group title; staff continuity uses only comparable named responsibilities and surfaces unavailable counts.",
            "Coverage is marginal over team-metric rows and should not be read as simultaneous team-level coverage or a probability that a coach keeps the same style.",
        ],
    }
    return HistoricalCertaintyResult(
        target_seasons=tuple(sorted(expected_seasons)),
        development_seasons=development,
        holdout_season=holdout_season,
        windows=windows,
        bootstrap_samples=bootstrap_samples,
        random_seed=random_seed,
        input_paths=tuple(Path(path) for path in input_raw),
        input_hashes={path: _sha256(raw) for path, raw in input_raw.items()},
        team_score_rows=tuple(score_rows),
        team_error_rows=tuple(team_error_rows),
        rank_rows=tuple(rank_rows),
        tier_rows=tuple(tier_rows),
        calibration_rows=tuple(calibration_rows),
        coverage_prediction_rows=tuple(coverage_prediction_rows),
        coverage_summary_rows=tuple(coverage_summary_rows),
        evaluation=evaluation,
    )


def _csv_bytes(rows: Iterable[Mapping[str, Any]], fields: tuple[str, ...]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def write_historical_certainty_snapshot(
    result: HistoricalCertaintyResult,
    root: str | Path,
    *,
    created_at: datetime | None = None,
) -> Path:
    """Atomically publish the score reconstruction, diagnostics, and hashes."""

    created = created_at or datetime.now(timezone.utc)
    if created.tzinfo is None:
        raise ValueError("created_at must include a timezone")
    created = created.astimezone(timezone.utc)
    season_label = "-".join(map(str, result.target_seasons))
    parent = Path(root) / "historical_certainty_evaluation" / season_label
    destination = parent / created.strftime("%Y%m%dT%H%M%S.%fZ")
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"historical certainty snapshot exists: {destination}")
    artifacts = {
        "team_scores.csv": _csv_bytes(result.team_score_rows, TEAM_SCORE_FIELDS),
        "team_errors.csv": _csv_bytes(result.team_error_rows, TEAM_ERROR_FIELDS),
        "rank_diagnostics.csv": _csv_bytes(result.rank_rows, RANK_FIELDS),
        "tier_definitions.csv": _csv_bytes(result.tier_rows, TIER_FIELDS),
        "calibration.csv": _csv_bytes(result.calibration_rows, CALIBRATION_FIELDS),
        "coverage_predictions.csv": _csv_bytes(
            result.coverage_prediction_rows, COVERAGE_PREDICTION_FIELDS
        ),
        "coverage_summary.csv": _csv_bytes(
            result.coverage_summary_rows, COVERAGE_SUMMARY_FIELDS
        ),
        "evaluation.json": (
            json.dumps(result.evaluation, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
    }
    fields = {
        "team_scores.csv": TEAM_SCORE_FIELDS,
        "team_errors.csv": TEAM_ERROR_FIELDS,
        "rank_diagnostics.csv": RANK_FIELDS,
        "tier_definitions.csv": TIER_FIELDS,
        "calibration.csv": CALIBRATION_FIELDS,
        "coverage_predictions.csv": COVERAGE_PREDICTION_FIELDS,
        "coverage_summary.csv": COVERAGE_SUMMARY_FIELDS,
    }
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "model_status": "diagnostic_lower_bounds_not_probability_calibration",
        "created_at": created.isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        ),
        "target_seasons": list(result.target_seasons),
        "development_seasons": list(result.development_seasons),
        "holdout_season": result.holdout_season,
        "target_windows": [f"Weeks 1-{week}" for week in result.windows],
        "bootstrap": {
            "samples": result.bootstrap_samples,
            "random_seed": result.random_seed,
            "unit": "team-season mean normalized style error",
        },
        "methodology": {
            "scores": "current v0 rubric reconstructed with one-year caller evidence; missing changed-caller scheme components remain lower/upper bounds",
            "rank_test": "Spearman association between conservative score lower bound and team mean normalized absolute error",
            "tiering": "development-only linear tertiles, applied unchanged to holdout",
            "intervals": "90% finite-sample split-conformal normalized residual radii per metric and score tier, compared with per-metric global radii",
            "warning": "These diagnostics do not convert evidence indices into probabilities and do not calibrate the richer 2026 score.",
        },
        "input_sha256": dict(sorted(result.input_hashes.items())),
        "quality": {
            "team_score_count": len(result.team_score_rows),
            "excluded_score_count": sum(
                row["score_status"] != "eligible_one_year_lower_bound_diagnostic"
                for row in result.team_score_rows
            ),
            "team_error_count": len(result.team_error_rows),
            "coverage_prediction_count": len(result.coverage_prediction_rows),
            "promotion_decision": result.evaluation["promotion_gate"]["decision"],
        },
        "artifacts": {},
    }
    for filename, payload in artifacts.items():
        entry: dict[str, Any] = {
            "bytes": len(payload),
            "sha256": _sha256(payload),
        }
        if filename in fields:
            entry["fields"] = list(fields[filename])
        manifest["artifacts"][filename] = entry
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
    try:
        for filename, payload in artifacts.items():
            (staging / filename).write_bytes(payload)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
