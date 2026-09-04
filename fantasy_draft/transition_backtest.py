"""Time-correct backtest of offensive style forecasts across caller transitions.

Each cohort uses source-dated caller identity evidence, prior-season measured
style, and fixed forecast weights. Target outcomes are used only for scoring.
Audited in-window caller changes and unresolved opening assignments are excluded
rather than silently attributed or resolved with hindsight.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import shutil
import statistics
import tempfile
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

from .caller_fingerprints import STYLE_METRICS
from .environment import METRICS
from .sources.nflverse import TeamSeasonStyle, derive_nflverse_style_window


SCHEMA_VERSION = "1.0.0"
MODEL_VERSION = "opening-caller-transition-backtest-v0.3.0"
STYLE_TEAM_ALIASES = {"LA": "LAR"}
MODELS = ("persistence", "shrunken_persistence", "caller_aware_v0")
COHORTS = (
    "all",
    "returning_caller",
    "changed_all",
    "changed_with_prior_year_anchor",
    "changed_without_prior_year_anchor",
)

PREDICTION_FIELDS = (
    "target_season",
    "week_start",
    "week_end",
    "team",
    "opening_caller",
    "prior_caller",
    "caller_cohort",
    "prior_anchor_team",
    "metric",
    "dimension",
    "tolerance",
    "model",
    "forecast_value",
    "actual_value",
    "absolute_error",
    "normalized_absolute_error",
    "within_tolerance",
)

TEAM_FIELDS = (
    "target_season",
    "week_start",
    "week_end",
    "team",
    "opening_caller",
    "prior_caller",
    "caller_cohort",
    "prior_anchor_team",
    "actual_games",
    "excluded",
    "exclusion_reason",
    "exclusion_source_url",
)

SUMMARY_FIELDS = (
    "target_season",
    "week_start",
    "week_end",
    "cohort",
    "model",
    "team_count",
    "comparison_count",
    "normalized_mae",
    "median_normalized_absolute_error",
    "p75_normalized_absolute_error",
    "within_tolerance_rate",
    "delta_vs_shrunken_persistence",
    "relative_improvement_vs_shrunken_pct",
)

METRIC_SUMMARY_FIELDS = (
    "target_season",
    "week_start",
    "week_end",
    "cohort",
    "metric",
    "dimension",
    "model",
    "team_count",
    "mean_absolute_error",
    "normalized_mae",
    "within_tolerance_rate",
    "delta_vs_shrunken_persistence",
)

PAIRED_EFFECT_FIELDS = (
    "target_season",
    "week_start",
    "week_end",
    "cohort",
    "team",
    "baseline_model",
    "candidate_model",
    "baseline_team_nmae",
    "candidate_team_nmae",
    "paired_delta",
    "candidate_wins",
)


class TransitionBacktestDataError(ValueError):
    """Raised when a backtest input violates its time or coverage contract."""


@dataclass(frozen=True)
class Caller:
    season: int
    team: str
    name: str
    source_url: str
    published_at: date
    temporal_use: str
    identity_status: str = "confirmed"
    candidate_callers: tuple[str, ...] = ()


@dataclass(frozen=True)
class CallerChange:
    team: str
    opening_caller: str
    replacement_caller: str
    first_replacement_week: int
    reason: str
    source_url: str


@dataclass(frozen=True)
class TransitionBacktestResult:
    prior_season: int
    target_season: int
    windows: tuple[int, ...]
    as_of: date
    input_paths: tuple[Path, ...]
    input_hashes: Mapping[str, str]
    prediction_rows: tuple[Mapping[str, Any], ...]
    team_rows: tuple[Mapping[str, Any], ...]
    summary_rows: tuple[Mapping[str, Any], ...]
    metric_summary_rows: tuple[Mapping[str, Any], ...]
    paired_effect_rows: tuple[Mapping[str, Any], ...]
    evaluation: Mapping[str, Any]


def _identity(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).casefold()
    identity = "".join(character for character in normalized if character.isalnum())
    for suffix in ("iii", "ii", "iv", "jr", "sr"):
        if identity.endswith(suffix):
            return identity[: -len(suffix)]
    return identity


def _team(value: str) -> str:
    observed = value.strip().upper()
    return STYLE_TEAM_ALIASES.get(observed, observed)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _resolve(path: str | Path, filename: str) -> Path:
    resolved = Path(path)
    if resolved.is_dir():
        resolved = resolved / filename
    if not resolved.is_file():
        raise TransitionBacktestDataError(f"input does not exist: {resolved}")
    return resolved


def _read_csv(path: Path, required: set[str]) -> tuple[bytes, list[dict[str, str]]]:
    raw = path.read_bytes()
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    except UnicodeDecodeError as error:
        raise TransitionBacktestDataError(f"CSV is not UTF-8: {path}") from error
    fields = set(rows[0]) if rows else set()
    missing = required - fields
    if not rows or missing:
        raise TransitionBacktestDataError(
            f"CSV has no rows or is missing fields {sorted(missing)}: {path}"
        )
    return raw, rows


def _float(value: str, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise TransitionBacktestDataError(f"{context} must be numeric") from error
    if not math.isfinite(result):
        raise TransitionBacktestDataError(f"{context} must be finite")
    return result


def _https_url(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TransitionBacktestDataError(f"{context} must be a non-empty URL")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise TransitionBacktestDataError(f"{context} must be an absolute HTTPS URL")
    return value.strip()


def _load_callers(
    path: str | Path,
) -> tuple[Path, dict[str, bytes], int, dict[str, Caller]]:
    source_path = Path(path)
    resolved = _resolve(path, "callers.csv")
    raw = resolved.read_bytes()
    provenance = {str(resolved): raw}
    declared_season: Any = None
    manifest_path: Path | None = None
    if source_path.is_dir():
        manifest_path = source_path / "manifest.json"
        if not manifest_path.is_file():
            raise TransitionBacktestDataError(
                f"caller snapshot directory lacks manifest.json: {source_path}"
            )
        manifest_raw = manifest_path.read_bytes()
        try:
            manifest = json.loads(manifest_raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TransitionBacktestDataError(
                f"invalid caller snapshot manifest: {manifest_path}"
            ) from error
        if not isinstance(manifest, Mapping) or not isinstance(
            manifest.get("artifacts"), Mapping
        ):
            raise TransitionBacktestDataError(
                f"caller snapshot manifest lacks artifacts: {manifest_path}"
            )
        caller_entries = []
        for key, value in manifest["artifacts"].items():
            if not isinstance(value, Mapping):
                continue
            artifact_path = value.get("path", key)
            if artifact_path == "callers.csv":
                caller_entries.append(value)
        if len(caller_entries) != 1 or not isinstance(
            caller_entries[0].get("sha256"), str
        ):
            raise TransitionBacktestDataError(
                f"caller snapshot manifest must hash callers.csv: {manifest_path}"
            )
        expected_hash = caller_entries[0]["sha256"]
        if _sha256(raw) != expected_hash:
            raise TransitionBacktestDataError(
                f"caller snapshot callers.csv hash mismatch: {resolved}"
            )
        declared_season = manifest.get("season")
        if declared_season is None and isinstance(manifest.get("query"), Mapping):
            declared_season = manifest["query"].get("season")
        provenance[str(manifest_path)] = manifest_raw

    _, rows = _read_csv(
        resolved,
        {
            "season",
            "team",
            "play_caller",
            "source_url",
            "published_at",
            "temporal_use",
        },
    )
    seasons: set[int] = set()
    callers: dict[str, Caller] = {}
    for row in rows:
        try:
            season = int(row["season"])
            published = date.fromisoformat(row["published_at"])
        except ValueError as error:
            raise TransitionBacktestDataError(
                f"caller census has an invalid season/date: {resolved}"
            ) from error
        team = _team(row["team"])
        name = row["play_caller"].strip()
        temporal_use = row["temporal_use"].strip()
        identity_status = (row.get("identity_status") or "confirmed").strip()
        candidate_callers = tuple(
            candidate.strip()
            for candidate in (row.get("candidate_callers") or "").split("|")
            if candidate.strip()
        )
        if (
            not team
            or team in callers
            or temporal_use
            not in {
                "preseason_identity_evidence",
                "historical_identity_evidence_for_later_seasons_only",
            }
            or identity_status not in {"confirmed", "ambiguous"}
            or (identity_status == "confirmed" and (not name or candidate_callers))
            or (
                identity_status == "ambiguous"
                and (name or len(candidate_callers) < 2)
            )
            or len(set(candidate_callers)) != len(candidate_callers)
        ):
            raise TransitionBacktestDataError(
                f"caller census must be unique and have valid temporal/identity labels: {resolved}"
            )
        callers[team] = Caller(
            season=season,
            team=team,
            name=name,
            source_url=_https_url(row["source_url"], f"{team} caller source"),
            published_at=published,
            temporal_use=temporal_use,
            identity_status=identity_status,
            candidate_callers=candidate_callers,
        )
        seasons.add(season)
    if len(seasons) != 1:
        raise TransitionBacktestDataError(f"caller census must contain one season: {resolved}")
    season = seasons.pop()
    if declared_season is not None and manifest_path is not None and _integer_manifest_season(
        declared_season, manifest_path
    ) != season:
        raise TransitionBacktestDataError(
            f"caller snapshot season mismatch: {manifest_path}"
        )
    return resolved, provenance, season, callers


def _integer_manifest_season(value: Any, path: Path) -> int:
    if isinstance(value, bool):
        raise TransitionBacktestDataError(f"invalid caller snapshot season: {path}")
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise TransitionBacktestDataError(
            f"invalid caller snapshot season: {path}"
        ) from error


def _verify_file(path: Path, expected_hash: str, context: str) -> bytes:
    raw = path.read_bytes()
    observed = _sha256(raw)
    if observed != expected_hash:
        raise TransitionBacktestDataError(
            f"{context} hash mismatch: expected {expected_hash}, observed {observed}"
        )
    return raw


def _load_nflverse_snapshot(
    path: str | Path,
    *,
    prior_season: int,
    target_season: int,
) -> tuple[
    tuple[Path, ...],
    dict[str, bytes],
    dict[tuple[int, str], dict[str, float | None]],
    bytes,
    bytes,
    bytes,
]:
    root = Path(path)
    if not root.is_dir():
        raise TransitionBacktestDataError("nflverse backtest input must be a snapshot directory")
    manifest_path = root / "manifest.json"
    style_path = root / "team_style.csv"
    try:
        manifest_raw = manifest_path.read_bytes()
        manifest = json.loads(manifest_raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TransitionBacktestDataError(f"invalid nflverse manifest: {manifest_path}") from error
    if not isinstance(manifest, Mapping):
        raise TransitionBacktestDataError("nflverse manifest must be an object")
    query = manifest.get("query")
    artifacts = manifest.get("artifacts")
    if not isinstance(query, Mapping) or not isinstance(artifacts, Mapping):
        raise TransitionBacktestDataError("nflverse manifest is missing query/artifacts")
    seasons = query.get("seasons")
    if not isinstance(seasons, list) or not {prior_season, target_season}.issubset(seasons):
        raise TransitionBacktestDataError("nflverse snapshot does not cover both backtest seasons")
    if query.get("season_type") != "REG" or query.get("include_ftn_charting") is not True:
        raise TransitionBacktestDataError(
            "backtest requires regular-season nflverse data with FTN charting"
        )
    normalized = artifacts.get("normalized")
    raw_manifest = artifacts.get("raw")
    if not isinstance(normalized, Mapping) or not isinstance(raw_manifest, Mapping):
        raise TransitionBacktestDataError("nflverse artifact manifest is incomplete")
    expected_style_hash = normalized.get("sha256")
    if not isinstance(expected_style_hash, str):
        raise TransitionBacktestDataError("nflverse normalized hash is missing")
    style_raw = _verify_file(style_path, expected_style_hash, "nflverse team_style.csv")
    _, style_rows = _read_csv(style_path, {"season", "team", *STYLE_METRICS})
    styles: dict[tuple[int, str], dict[str, float | None]] = {}
    for row in style_rows:
        try:
            season = int(row["season"])
        except ValueError as error:
            raise TransitionBacktestDataError("nflverse style season must be an integer") from error
        team = _team(row["team"])
        key = season, team
        if key in styles:
            raise TransitionBacktestDataError(f"duplicate nflverse style row: {key}")
        styles[key] = {
            metric: None if not row[metric].strip() else _float(row[metric], f"{key} {metric}")
            for metric in STYLE_METRICS
        }

    asset_names = (
        f"play_by_play_{target_season}.csv.gz",
        f"roster_{target_season}.csv",
        f"ftn_charting_{target_season}.csv",
    )
    asset_bytes: dict[str, bytes] = {}
    asset_paths: list[Path] = []
    for name in asset_names:
        entry = raw_manifest.get(name)
        if not isinstance(entry, Mapping) or not isinstance(entry.get("sha256"), str):
            raise TransitionBacktestDataError(f"nflverse manifest is missing {name}")
        asset_path = root / "raw" / name
        asset_bytes[name] = _verify_file(asset_path, entry["sha256"], name)
        asset_paths.append(asset_path)
    return (
        (manifest_path, style_path, *asset_paths),
        {str(manifest_path): manifest_raw, str(style_path): style_raw, **{
            str(path): asset_bytes[path.name] for path in asset_paths
        }},
        styles,
        asset_bytes[asset_names[0]],
        asset_bytes[asset_names[1]],
        asset_bytes[asset_names[2]],
    )


def _load_changes(
    path: str | Path,
    *,
    target_season: int,
    target_callers: Mapping[str, Caller],
    windows: tuple[int, ...],
) -> tuple[Path, bytes, date, dict[str, CallerChange]]:
    resolved = Path(path)
    raw = resolved.read_bytes()
    try:
        root = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TransitionBacktestDataError(f"invalid change registry: {resolved}") from error
    if not isinstance(root, Mapping) or root.get("schema_version") != "1.0.0":
        raise TransitionBacktestDataError("change registry schema_version must be '1.0.0'")
    if root.get("target_season") != target_season:
        raise TransitionBacktestDataError("change registry target season mismatch")
    maximum = root.get("max_supported_week_end")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or max(windows) > maximum:
        raise TransitionBacktestDataError("change registry does not cover requested week windows")
    try:
        as_of = date.fromisoformat(str(root.get("as_of")))
    except ValueError as error:
        raise TransitionBacktestDataError("change registry as_of must use YYYY-MM-DD") from error
    items = root.get("changes")
    if not isinstance(items, list):
        raise TransitionBacktestDataError("change registry changes must be a list")
    changes: dict[str, CallerChange] = {}
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise TransitionBacktestDataError(f"changes[{index}] must be an object")
        team = _team(str(item.get("team", "")))
        opening = str(item.get("opening_caller", "")).strip()
        replacement = str(item.get("replacement_caller", "")).strip()
        reason = str(item.get("reason", "")).strip()
        first_week = item.get("first_replacement_week")
        if (
            team not in target_callers
            or target_callers[team].identity_status != "confirmed"
            or team in changes
            or not opening
            or not replacement
            or not reason
            or isinstance(first_week, bool)
            or not isinstance(first_week, int)
            or not 1 <= first_week <= maximum
        ):
            raise TransitionBacktestDataError(f"changes[{index}] is invalid or duplicate")
        if _identity(opening) != _identity(target_callers[team].name):
            raise TransitionBacktestDataError(f"change registry opening caller mismatch for {team}")
        changes[team] = CallerChange(
            team=team,
            opening_caller=opening,
            replacement_caller=replacement,
            first_replacement_week=first_week,
            reason=reason,
            source_url=_https_url(item.get("source_url"), f"changes[{index}].source_url"),
        )
    return resolved, raw, as_of, changes


def _weighted(values: Iterable[tuple[float | None, float]]) -> float | None:
    usable = [(value, weight) for value, weight in values if value is not None and weight > 0]
    total = sum(weight for _, weight in usable)
    if not total:
        return None
    return sum(value * weight for value, weight in usable) / total


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        raise TransitionBacktestDataError("cannot summarize an empty error sample")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _cohort_membership(caller_cohort: str, cohort: str) -> bool:
    if cohort == "all":
        return True
    if cohort == "changed_all":
        return caller_cohort.startswith("changed_")
    return caller_cohort == cohort


def _summaries(
    rows: list[Mapping[str, Any]],
    *,
    target_season: int,
    windows: tuple[int, ...],
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    summary_rows: list[Mapping[str, Any]] = []
    metric_rows: list[Mapping[str, Any]] = []
    for week_end in windows:
        window_rows = [row for row in rows if row["week_end"] == week_end]
        for cohort in COHORTS:
            cohort_rows = [
                row
                for row in window_rows
                if _cohort_membership(str(row["caller_cohort"]), cohort)
            ]
            if not cohort_rows:
                continue
            by_model = {
                model: [row for row in cohort_rows if row["model"] == model]
                for model in MODELS
            }
            baseline = statistics.mean(
                float(row["normalized_absolute_error"])
                for row in by_model["shrunken_persistence"]
            )
            for model in MODELS:
                model_rows = by_model[model]
                errors = [float(row["normalized_absolute_error"]) for row in model_rows]
                nmae = statistics.mean(errors)
                delta = nmae - baseline
                summary_rows.append(
                    {
                        "target_season": target_season,
                        "week_start": 1,
                        "week_end": week_end,
                        "cohort": cohort,
                        "model": model,
                        "team_count": len({str(row["team"]) for row in model_rows}),
                        "comparison_count": len(model_rows),
                        "normalized_mae": round(nmae, 6),
                        "median_normalized_absolute_error": round(
                            statistics.median(errors), 6
                        ),
                        "p75_normalized_absolute_error": round(_percentile(errors, 0.75), 6),
                        "within_tolerance_rate": round(
                            sum(error <= 1 for error in errors) / len(errors), 6
                        ),
                        "delta_vs_shrunken_persistence": round(delta, 6),
                        "relative_improvement_vs_shrunken_pct": round(
                            -100 * delta / baseline if baseline else 0.0, 3
                        ),
                    }
                )

            metrics = sorted({str(row["metric"]) for row in cohort_rows})
            for metric in metrics:
                metric_cohort_rows = [row for row in cohort_rows if row["metric"] == metric]
                baseline_metric_rows = [
                    row
                    for row in metric_cohort_rows
                    if row["model"] == "shrunken_persistence"
                ]
                baseline_metric = statistics.mean(
                    float(row["normalized_absolute_error"])
                    for row in baseline_metric_rows
                )
                for model in MODELS:
                    selected = [row for row in metric_cohort_rows if row["model"] == model]
                    raw_errors = [float(row["absolute_error"]) for row in selected]
                    normalized_errors = [
                        float(row["normalized_absolute_error"]) for row in selected
                    ]
                    nmae = statistics.mean(normalized_errors)
                    metric_rows.append(
                        {
                            "target_season": target_season,
                            "week_start": 1,
                            "week_end": week_end,
                            "cohort": cohort,
                            "metric": metric,
                            "dimension": METRICS[metric].dimension,
                            "model": model,
                            "team_count": len({str(row["team"]) for row in selected}),
                            "mean_absolute_error": round(statistics.mean(raw_errors), 6),
                            "normalized_mae": round(nmae, 6),
                            "within_tolerance_rate": round(
                                sum(error <= 1 for error in normalized_errors)
                                / len(normalized_errors),
                                6,
                            ),
                            "delta_vs_shrunken_persistence": round(
                                nmae - baseline_metric, 6
                            ),
                        }
                    )
    return summary_rows, metric_rows


def _summary_lookup(
    rows: Iterable[Mapping[str, Any]], week_end: int, cohort: str, model: str
) -> Mapping[str, Any]:
    return next(
        row
        for row in rows
        if row["week_end"] == week_end
        and row["cohort"] == cohort
        and row["model"] == model
    )


def _paired_team_effects(
    prediction_rows: Iterable[Mapping[str, Any]],
    *,
    target_season: int,
    windows: tuple[int, ...],
    cohort: str,
    baseline_model: str = "shrunken_persistence",
    candidate_model: str = "caller_aware_v0",
) -> list[Mapping[str, Any]]:
    """Collapse correlated metric errors to paired team-level effects."""

    rows = list(prediction_rows)
    effects: list[Mapping[str, Any]] = []
    for week_end in windows:
        teams = sorted(
            {
                str(row["team"])
                for row in rows
                if row["week_end"] == week_end
                and _cohort_membership(str(row["caller_cohort"]), cohort)
            }
        )
        for team in teams:
            by_model: dict[str, list[float]] = {}
            for model in (baseline_model, candidate_model):
                by_model[model] = [
                    float(row["normalized_absolute_error"])
                    for row in rows
                    if row["week_end"] == week_end
                    and row["team"] == team
                    and row["model"] == model
                ]
            if not by_model[baseline_model] or not by_model[candidate_model]:
                raise TransitionBacktestDataError(
                    f"missing paired model errors for {team} Weeks 1-{week_end}"
                )
            baseline = statistics.mean(by_model[baseline_model])
            candidate = statistics.mean(by_model[candidate_model])
            effects.append(
                {
                    "target_season": target_season,
                    "week_start": 1,
                    "week_end": week_end,
                    "cohort": cohort,
                    "team": team,
                    "baseline_model": baseline_model,
                    "candidate_model": candidate_model,
                    "baseline_team_nmae": round(baseline, 6),
                    "candidate_team_nmae": round(candidate, 6),
                    "paired_delta": round(candidate - baseline, 6),
                    "candidate_wins": str(candidate < baseline).lower(),
                }
            )
    return effects


def _exact_cluster_bootstrap_interval(
    effects: list[float], confidence: float = 0.95
) -> tuple[float, float]:
    """Exact ordinary bootstrap percentile interval when the cohort is small."""

    if not effects or len(effects) > 7:
        raise TransitionBacktestDataError(
            "exact cluster bootstrap requires between one and seven team effects"
        )
    means = sorted(
        sum(effects[index] for index in indices) / len(effects)
        for indices in product(range(len(effects)), repeat=len(effects))
    )
    alpha = (1 - confidence) / 2
    return _percentile(means, alpha), _percentile(means, 1 - alpha)


def build_transition_backtest(
    nflverse_snapshot: str | Path,
    prior_callers: str | Path,
    target_callers: str | Path,
    change_registry: str | Path,
    *,
    windows: Iterable[int] = (6, 8),
    expected_team_count: int = 32,
) -> TransitionBacktestResult:
    """Build the declared 2024-style transition test without tuning on results."""

    window_values = tuple(sorted(set(windows)))
    if (
        not window_values
        or any(isinstance(value, bool) or not isinstance(value, int) for value in window_values)
        or window_values[0] < 1
        or window_values[-1] > 22
    ):
        raise TransitionBacktestDataError("windows must be unique integer week ends from 1 to 22")
    prior_path, prior_raw, prior_season, prior = _load_callers(prior_callers)
    target_path, target_raw, target_season, target = _load_callers(target_callers)
    if target_season != prior_season + 1:
        raise TransitionBacktestDataError("caller censuses must cover consecutive seasons")
    if set(prior) != set(target) or len(target) != expected_team_count:
        raise TransitionBacktestDataError(
            f"caller censuses must contain the same {expected_team_count} teams"
        )
    if any(caller.identity_status != "confirmed" for caller in prior.values()):
        raise TransitionBacktestDataError(
            "prior caller census must have confirmed identities for every team"
        )
    if any(
        caller.temporal_use != "preseason_identity_evidence"
        for caller in target.values()
    ):
        raise TransitionBacktestDataError(
            "target caller evidence must be labeled preseason_identity_evidence"
        )
    if any(caller.published_at >= date(target_season, 9, 1) for caller in target.values()):
        raise TransitionBacktestDataError(
            "target caller evidence must be published before September 1 of target season"
        )

    (
        nfl_paths,
        nfl_raw,
        styles,
        target_pbp,
        target_roster,
        target_ftn,
    ) = _load_nflverse_snapshot(
        nflverse_snapshot,
        prior_season=prior_season,
        target_season=target_season,
    )
    change_path, change_raw, as_of, changes = _load_changes(
        change_registry,
        target_season=target_season,
        target_callers=target,
        windows=window_values,
    )
    prior_styles = {
        team: styles[(prior_season, team)]
        for team in target
        if (prior_season, team) in styles
    }
    if set(prior_styles) != set(target):
        raise TransitionBacktestDataError("nflverse prior styles do not cover caller teams")
    league_medians = {
        metric: statistics.median(
            value
            for team in prior_styles.values()
            if (value := team[metric]) is not None
        )
        for metric in STYLE_METRICS
    }
    prior_by_identity: dict[str, list[Caller]] = defaultdict(list)
    for caller in prior.values():
        prior_by_identity[_identity(caller.name)].append(caller)

    prediction_rows: list[Mapping[str, Any]] = []
    team_rows: list[Mapping[str, Any]] = []
    for week_end in window_values:
        actual_records = derive_nflverse_style_window(
            season=target_season,
            week_start=1,
            week_end=week_end,
            play_by_play=target_pbp,
            roster=target_roster,
            ftn_charting=target_ftn,
        )
        actual = {_team(record.team): record for record in actual_records}
        if set(actual) != set(target):
            raise TransitionBacktestDataError(
                f"Weeks 1-{week_end} actual styles do not cover all caller teams"
            )
        for team in sorted(target):
            opening = target[team]
            prior_caller = prior[team]
            if opening.identity_status == "ambiguous":
                candidates = " / ".join(opening.candidate_callers)
                team_rows.append(
                    {
                        "target_season": target_season,
                        "week_start": 1,
                        "week_end": week_end,
                        "team": team,
                        "opening_caller": candidates,
                        "prior_caller": prior_caller.name,
                        "caller_cohort": "ambiguous_opening_caller",
                        "prior_anchor_team": "",
                        "actual_games": actual[team].games,
                        "excluded": "true",
                        "exclusion_reason": (
                            "Preseason evidence did not resolve the opening caller "
                            f"between {candidates}; no hindsight identity was selected."
                        ),
                        "exclusion_source_url": opening.source_url,
                    }
                )
                continue
            same = _identity(opening.name) == _identity(prior_caller.name)
            candidate_anchors = prior_by_identity.get(_identity(opening.name), [])
            anchor = (
                candidate_anchors[0]
                if not same and len(candidate_anchors) == 1
                else None
            )
            caller_cohort = (
                "returning_caller"
                if same
                else (
                    "changed_with_prior_year_anchor"
                    if anchor is not None
                    else "changed_without_prior_year_anchor"
                )
            )
            change = changes.get(team)
            excluded = change is not None and change.first_replacement_week <= week_end
            team_rows.append(
                {
                    "target_season": target_season,
                    "week_start": 1,
                    "week_end": week_end,
                    "team": team,
                    "opening_caller": opening.name,
                    "prior_caller": prior_caller.name,
                    "caller_cohort": caller_cohort,
                    "prior_anchor_team": "" if anchor is None else anchor.team,
                    "actual_games": actual[team].games,
                    "excluded": str(excluded).lower(),
                    "exclusion_reason": "" if not excluded else change.reason,
                    "exclusion_source_url": "" if not excluded else change.source_url,
                }
            )
            if excluded:
                continue
            for metric in STYLE_METRICS:
                destination = prior_styles[team][metric]
                observed = getattr(actual[team], metric)
                league = league_medians[metric]
                anchor_value = None if anchor is None else prior_styles[anchor.team][metric]
                if destination is None or observed is None:
                    continue
                forecasts = {
                    "persistence": destination,
                    "shrunken_persistence": _weighted(
                        ((destination, 0.80), (league, 0.20))
                    ),
                    "caller_aware_v0": (
                        _weighted(((destination, 0.95), (league, 0.05)))
                        if same
                        else (
                            _weighted(
                                (
                                    (anchor_value, 0.70),
                                    (destination, 0.20),
                                    (league, 0.10),
                                )
                            )
                            if anchor is not None
                            else _weighted(((destination, 0.60), (league, 0.40)))
                        )
                    ),
                }
                tolerance = METRICS[metric].tolerance
                for model, forecast in forecasts.items():
                    assert forecast is not None
                    absolute_error = abs(forecast - observed)
                    prediction_rows.append(
                        {
                            "target_season": target_season,
                            "week_start": 1,
                            "week_end": week_end,
                            "team": team,
                            "opening_caller": opening.name,
                            "prior_caller": prior_caller.name,
                            "caller_cohort": caller_cohort,
                            "prior_anchor_team": "" if anchor is None else anchor.team,
                            "metric": metric,
                            "dimension": METRICS[metric].dimension,
                            "tolerance": tolerance,
                            "model": model,
                            "forecast_value": round(forecast, 6),
                            "actual_value": round(observed, 6),
                            "absolute_error": round(absolute_error, 6),
                            "normalized_absolute_error": round(
                                absolute_error / tolerance, 6
                            ),
                            "within_tolerance": str(absolute_error <= tolerance).lower(),
                        }
                    )

    summary_rows, metric_summary_rows = _summaries(
        prediction_rows,
        target_season=target_season,
        windows=window_values,
    )
    paired_effect_rows = _paired_team_effects(
        prediction_rows,
        target_season=target_season,
        windows=window_values,
        cohort="changed_with_prior_year_anchor",
    )
    changed_comparisons = []
    h1_point_estimate_pass = True
    h2_pass = True
    for week_end in window_values:
        caller = _summary_lookup(
            summary_rows,
            week_end,
            "changed_with_prior_year_anchor",
            "caller_aware_v0",
        )
        shrunken = _summary_lookup(
            summary_rows,
            week_end,
            "changed_with_prior_year_anchor",
            "shrunken_persistence",
        )
        caller_all_changed = _summary_lookup(
            summary_rows, week_end, "changed_all", "caller_aware_v0"
        )
        shrunken_all_changed = _summary_lookup(
            summary_rows, week_end, "changed_all", "shrunken_persistence"
        )
        returning = _summary_lookup(
            summary_rows, week_end, "returning_caller", "persistence"
        )
        changed = _summary_lookup(summary_rows, week_end, "changed_all", "persistence")
        improved = float(caller["normalized_mae"]) < float(shrunken["normalized_mae"])
        lower_drift = float(returning["normalized_mae"]) < float(changed["normalized_mae"])
        h1_point_estimate_pass = h1_point_estimate_pass and improved
        h2_pass = h2_pass and lower_drift
        team_effects = [
            float(row["paired_delta"])
            for row in paired_effect_rows
            if row["week_end"] == week_end
        ]
        lower_ci, upper_ci = _exact_cluster_bootstrap_interval(team_effects)
        changed_comparisons.append(
            {
                "week_end": week_end,
                "anchored_changed_team_count": int(caller["team_count"]),
                "anchored_caller_aware_nmae": caller["normalized_mae"],
                "anchored_shrunken_persistence_nmae": shrunken["normalized_mae"],
                "anchored_relative_improvement_pct": caller[
                    "relative_improvement_vs_shrunken_pct"
                ],
                "anchored_caller_aware_point_estimate_wins": improved,
                "anchored_team_win_count": sum(value < 0 for value in team_effects),
                "anchored_team_effect_count": len(team_effects),
                "anchored_mean_paired_delta": round(statistics.mean(team_effects), 6),
                "anchored_exact_team_bootstrap_95pct_interval": [
                    round(lower_ci, 6),
                    round(upper_ci, 6),
                ],
                "all_changed_caller_aware_nmae": caller_all_changed[
                    "normalized_mae"
                ],
                "all_changed_shrunken_persistence_nmae": shrunken_all_changed[
                    "normalized_mae"
                ],
                "all_changed_relative_improvement_pct": caller_all_changed[
                    "relative_improvement_vs_shrunken_pct"
                ],
                "returning_persistence_nmae": returning["normalized_mae"],
                "changed_persistence_nmae": changed["normalized_mae"],
                "returning_has_lower_style_drift": lower_drift,
            }
        )
    evaluation: dict[str, Any] = {
        "status": "exploratory_single_transition_cohort_not_probability_calibration",
        "predeclared_hypotheses": {
            "h1": (
                "For changed callers with a clean prior-year caller anchor, "
                "caller_aware_v0 has lower normalized MAE than shrunken persistence "
                "in both Weeks 1-6 and Weeks 1-8."
            ),
            "h2": (
                "Raw destination-style persistence error is lower for returning callers "
                "than changed callers in both windows."
            ),
        },
        "results": {
            "h1_point_estimate_pass": h1_point_estimate_pass,
            "h2_pass": h2_pass,
            "window_comparisons": changed_comparisons,
        },
        "post_audit_promotion_gate": (
            "Do not call caller-history mean shifts validated until there are at least "
            "three time-correct target seasons and the paired team-cluster interval "
            "excludes zero on held-out data."
        ),
        "mean_adjustment_decision": "retain_caller_aware_mean_as_experimental_only",
        "certainty_decision": (
            "No 0-100 evidence score is converted to a probability or coverage interval. "
            "At least two additional time-correct transition cohorts and interval coverage "
            "testing are required."
        ),
    }
    inputs = {
        **prior_raw,
        **target_raw,
        str(change_path): change_raw,
        **nfl_raw,
    }
    return TransitionBacktestResult(
        prior_season=prior_season,
        target_season=target_season,
        windows=window_values,
        as_of=as_of,
        input_paths=tuple(Path(path) for path in inputs),
        input_hashes={path: _sha256(raw) for path, raw in inputs.items()},
        prediction_rows=tuple(prediction_rows),
        team_rows=tuple(team_rows),
        summary_rows=tuple(summary_rows),
        metric_summary_rows=tuple(metric_summary_rows),
        paired_effect_rows=tuple(paired_effect_rows),
        evaluation=evaluation,
    )


def _csv_bytes(rows: Iterable[Mapping[str, Any]], fields: tuple[str, ...]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def write_transition_backtest_snapshot(
    result: TransitionBacktestResult,
    root: str | Path,
    *,
    created_at: datetime | None = None,
) -> Path:
    """Atomically publish predictions, summaries, evaluation, and provenance."""

    created = created_at or datetime.now(timezone.utc)
    if created.tzinfo is None:
        raise ValueError("created_at must include a timezone")
    created = created.astimezone(timezone.utc)
    parent = Path(root) / "transition_backtest" / str(result.target_season)
    destination = parent / created.strftime("%Y%m%dT%H%M%S.%fZ")
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"transition backtest snapshot already exists: {destination}")

    artifacts = {
        "predictions.csv": _csv_bytes(result.prediction_rows, PREDICTION_FIELDS),
        "teams.csv": _csv_bytes(result.team_rows, TEAM_FIELDS),
        "summary.csv": _csv_bytes(result.summary_rows, SUMMARY_FIELDS),
        "metric_summary.csv": _csv_bytes(
            result.metric_summary_rows, METRIC_SUMMARY_FIELDS
        ),
        "paired_team_effects.csv": _csv_bytes(
            result.paired_effect_rows, PAIRED_EFFECT_FIELDS
        ),
        "evaluation.json": (
            json.dumps(result.evaluation, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "created_at": created.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "as_of": result.as_of.isoformat(),
        "seasons": {
            "prior": result.prior_season,
            "target": result.target_season,
            "target_windows": [f"Weeks 1-{week}" for week in result.windows],
        },
        "time_validity": {
            "caller_identity_inputs": (
                "source-dated preseason censuses; prior-season identity may use "
                "a contemporaneous factual table audited later"
            ),
            "target_results_used_as_features": False,
            "target_results_used_only_for_scoring": True,
            "in_window_caller_changes": "team-window excluded at first replacement week",
            "ambiguous_opening_callers": (
                "excluded for every window without hindsight resolution"
            ),
        },
        "models": {
            "persistence": "100% prior-year destination team style",
            "shrunken_persistence": "80% destination style + 20% prior league median",
            "caller_aware_v0": {
                "returning_caller": "95% destination + 5% league median",
                "changed_with_prior_year_anchor": (
                    "70% caller prior team + 20% destination + 10% league median"
                ),
                "changed_without_prior_year_anchor": (
                    "60% destination + 40% league median"
                ),
            },
        },
        "scoring": {
            "target": "observed nflverse team style in each week window",
            "normalized_absolute_error": (
                "absolute error divided by the predeclared metric tolerance in "
                "fantasy_draft.environment.METRICS"
            ),
            "efficiency_and_explosiveness_included": False,
            "aggregation": "macro mean over available team-metric comparisons",
        },
        "limitations": [
            "One target season is insufficient to calibrate probabilities or intervals.",
            "The test isolates caller identity/history; it does not recreate time-correct staff, scheme-news, personnel, injury, or opponent inputs.",
            "Early-season observations contain schedule, personnel, game-state, and sampling noise.",
            "A prior full team-season is an imperfect proxy for individual caller causality.",
        ],
        "input_sha256": dict(sorted(result.input_hashes.items())),
        "artifacts": {
            name: {
                "bytes": len(raw),
                "sha256": _sha256(raw),
            }
            for name, raw in artifacts.items()
        },
        "counts": {
            "prediction_rows": len(result.prediction_rows),
            "team_window_rows": len(result.team_rows),
            "summary_rows": len(result.summary_rows),
            "metric_summary_rows": len(result.metric_summary_rows),
            "paired_team_effect_rows": len(result.paired_effect_rows),
        },
        "evaluation": result.evaluation,
    }

    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
    try:
        for name, raw in artifacts.items():
            (staging / name).write_bytes(raw)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
