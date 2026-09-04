"""Time-correct backtest and provisional calibration for team resource pools.

The current opportunity pipeline forecasts its mean from caller-aware plays, pass
rate, run share, and position target share.  Only one direct caller-transition cohort
is available, so this module does not pretend to validate that mean.  Instead, it
tests simple preseason resource-rate references across 2023-24 development and an
untouched 2025 holdout, then produces empirical per-game error radii that can be
carried as a clearly labeled uncertainty layer around the current mean.
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


SCHEMA_VERSION = "1.0.0"
MODEL_VERSION = "team-resource-backtest-v0.1.0"
WINDOWS = (4, 8, 18)
RESOURCES: Mapping[str, tuple[str, str]] = {
    "RB_CARRIES": ("RB", "carries"),
    "RB_TARGETS": ("RB", "targets"),
    "WR_TARGETS": ("WR", "targets"),
    "TE_TARGETS": ("TE", "targets"),
}
BASE_MODEL = "league_rate"
MODEL_PRIOR_GAMES: Mapping[str, float | None] = {
    BASE_MODEL: None,
    "team_rate_raw": 0.0,
    "team_rate_p4": 4.0,
    "team_rate_p8": 8.0,
    "team_rate_p16": 16.0,
    "team_rate_p32": 32.0,
    "team_rate_p64": 64.0,
}
RECENCY_FACTOR = 0.65
NOMINAL_COVERAGE = 0.90
MIN_CLEAR_HOLDOUT_WINS = 2

PREDICTION_FIELDS = (
    "target_season", "segment", "window_end", "team", "resource", "model",
    "prior_games", "training_seasons", "training_league_opportunities",
    "training_league_games", "training_league_rate",
    "training_team_opportunities", "training_team_games", "predicted_per_game",
    "actual_games", "actual_opportunities", "actual_per_game",
    "absolute_error_per_game",
)
EVALUATION_FIELDS = (
    "segment", "scope", "window_end", "model", "team_count",
    "team_resource_count", "actual_games", "actual_opportunities",
    "mean_absolute_error_per_game", "root_mean_squared_error_per_game",
    "median_absolute_error_per_game", "delta_mae_vs_league",
)
COMPARISON_FIELDS = (
    "segment", "scope", "window_end", "challenger", "baseline", "pair_count",
    "cluster_count", "mean_error_delta", "delta_ci90_low", "delta_ci90_high",
    "paired_win_rate", "interpretation",
)
CALIBRATION_FIELDS = (
    "resource", "model", "calibration_seasons", "calibration_window_end",
    "calibration_team_seasons", "nominal_coverage",
    "conformal_absolute_error_per_game_radius", "holdout_season",
    "holdout_team_count", "holdout_coverage", "holdout_below_count",
    "holdout_above_count", "holdout_mean_interval_width",
    "current_mean_transfer_status", "calibration_status",
)


class ResourceBacktestDataError(ValueError):
    """Raised when resource history cannot support a reproducible backtest."""


@dataclass(frozen=True)
class ResourceBacktestResult:
    player_history_path: Path
    input_hashes: Mapping[str, str]
    development_seasons: tuple[int, ...]
    holdout_season: int
    history_lookback: int
    bootstrap_samples: int
    random_seed: int
    prediction_rows: tuple[Mapping[str, Any], ...]
    evaluation_rows: tuple[Mapping[str, Any], ...]
    comparison_rows: tuple[Mapping[str, Any], ...]
    calibration_rows: tuple[Mapping[str, Any], ...]
    recommendation: Mapping[str, Any]


def _read_manifest(root: Path) -> tuple[bytes, Mapping[str, Any]]:
    path = root / "manifest.json"
    if not path.is_file():
        raise ResourceBacktestDataError(f"missing input manifest: {path}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ResourceBacktestDataError(f"input manifest is not valid JSON: {path}") from error
    if not isinstance(value, Mapping):
        raise ResourceBacktestDataError(f"input manifest is not an object: {path}")
    return raw, value


def _verified_history_csv(
    root: Path,
    manifest: Mapping[str, Any],
    filename: str,
    required: set[str],
) -> tuple[bytes, list[dict[str, str]]]:
    metadata = (((manifest.get("artifacts") or {}).get("normalized") or {}).get(filename))
    if not isinstance(metadata, Mapping) or not metadata.get("sha256"):
        raise ResourceBacktestDataError(
            f"manifest does not describe normalized {filename}: {root}"
        )
    path = root / filename
    if not path.is_file():
        raise ResourceBacktestDataError(f"input does not exist: {path}")
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != metadata["sha256"]:
        raise ResourceBacktestDataError(
            f"input hash mismatch for {path}: expected {metadata['sha256']}, got {actual}"
        )
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        fields = set(reader.fieldnames or ())
        rows = list(reader)
    except UnicodeDecodeError as error:
        raise ResourceBacktestDataError(f"input is not UTF-8 CSV: {path}") from error
    missing = required - fields
    if missing or not rows:
        raise ResourceBacktestDataError(
            f"{path} is empty or missing fields {sorted(missing)}"
        )
    return raw, rows


def _number(value: Any, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ResourceBacktestDataError(f"{context} must be numeric") from error
    if not math.isfinite(result) or result < 0:
        raise ResourceBacktestDataError(f"{context} must be finite and nonnegative")
    return result


def _integer(value: Any, context: str) -> int:
    result = _number(value, context)
    if not result.is_integer():
        raise ResourceBacktestDataError(f"{context} must be an integer")
    return int(result)


def _percentile(values: Iterable[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ResourceBacktestDataError("cannot summarize an empty sample")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _conformal_radius(values: Iterable[float], coverage: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ResourceBacktestDataError("cannot calibrate an empty sample")
    rank = math.ceil((len(ordered) + 1) * coverage)
    return ordered[min(rank, len(ordered)) - 1]


def _resource_history(
    opportunity_rows: Iterable[Mapping[str, str]],
    schedule_rows: Iterable[Mapping[str, str]],
    *,
    expected_team_count: int,
) -> tuple[
    dict[tuple[int, int, str], int],
    dict[tuple[int, int, str, str], float],
]:
    games: dict[tuple[int, int, str], int] = {}
    teams_by_season: dict[int, set[str]] = defaultdict(set)
    for row in schedule_rows:
        season = _integer(row["season"], "schedule season")
        week = _integer(row["week"], "schedule week")
        team = row["team"].strip().upper()
        if not team or not 1 <= week <= 18:
            continue
        key = season, week, team
        if key in games:
            raise ResourceBacktestDataError(f"duplicate schedule team-week {key}")
        games[key] = 1
        teams_by_season[season].add(team)
    values: dict[tuple[int, int, str, str], float] = defaultdict(float)
    seen: set[tuple[int, int, str, str]] = set()
    for row in opportunity_rows:
        season = _integer(row["season"], "opportunity season")
        week = _integer(row["week"], "opportunity week")
        team = row["team"].strip().upper()
        position = row["position"].strip().upper()
        player_id = row["gsis_id"].strip()
        if not team or not player_id or not 1 <= week <= 18:
            continue
        identity = season, week, team, player_id
        if identity in seen:
            raise ResourceBacktestDataError(f"duplicate player opportunity row {identity}")
        seen.add(identity)
        for resource, (wanted_position, field) in RESOURCES.items():
            if position == wanted_position:
                values[(season, week, team, resource)] += _number(
                    row[field], f"{identity} {field}"
                )
    target_seasons = sorted({key[0] for key in games} & {key[0] for key in values})
    for season in target_seasons:
        if len(teams_by_season[season]) != expected_team_count:
            raise ResourceBacktestDataError(
                f"schedule season {season} has {len(teams_by_season[season])} teams; "
                f"expected {expected_team_count}"
            )
    if not values:
        raise ResourceBacktestDataError("resource history is empty")
    return games, dict(values)


def _training_rates(
    games: Mapping[tuple[int, int, str], int],
    values: Mapping[tuple[int, int, str, str], float],
    *,
    target_season: int,
    resource: str,
    history_lookback: int,
) -> tuple[tuple[int, ...], float, float, dict[str, tuple[float, float]]]:
    available = sorted({key[0] for key in games})
    training = tuple(
        season for season in available
        if target_season - history_lookback <= season < target_season
    )
    if not training:
        raise ResourceBacktestDataError(
            f"{resource} target {target_season} has no strictly prior history"
        )
    league_opportunities = 0.0
    league_games = 0.0
    teams: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for (season, week, team), game in games.items():
        if season not in training:
            continue
        weight = RECENCY_FACTOR ** (target_season - 1 - season)
        opportunities = values.get((season, week, team, resource), 0.0)
        league_opportunities += weight * opportunities
        league_games += weight * game
        teams[team][0] += weight * opportunities
        teams[team][1] += weight * game
    if league_games <= 0:
        raise ResourceBacktestDataError(f"{resource} has no weighted training games")
    return (
        training,
        league_opportunities,
        league_games,
        {team: (value[0], value[1]) for team, value in teams.items()},
    )


def _model_rate(
    model: str,
    *,
    league_rate: float,
    team_opportunities: float,
    team_games: float,
) -> float:
    prior = MODEL_PRIOR_GAMES[model]
    if model == BASE_MODEL or team_games <= 0:
        return league_rate
    if prior == 0:
        return team_opportunities / team_games
    if prior is None:
        raise ResourceBacktestDataError(f"invalid model prior for {model}")
    return (team_opportunities + prior * league_rate) / (team_games + prior)


def _evaluations(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for segment in ("development", "holdout"):
        for scope in ("ALL", *RESOURCES):
            for window in WINDOWS:
                for model in MODEL_PRIOR_GAMES:
                    selected = [
                        row for row in predictions
                        if row["segment"] == segment
                        and int(row["window_end"]) == window
                        and row["model"] == model
                        and (scope == "ALL" or row["resource"] == scope)
                    ]
                    if not selected:
                        continue
                    errors = [float(row["absolute_error_per_game"]) for row in selected]
                    baseline = [
                        row for row in predictions
                        if row["segment"] == segment
                        and int(row["window_end"]) == window
                        and row["model"] == BASE_MODEL
                        and (scope == "ALL" or row["resource"] == scope)
                    ]
                    baseline_mae = sum(
                        float(row["absolute_error_per_game"]) for row in baseline
                    ) / len(baseline)
                    output.append({
                        "segment": segment,
                        "scope": scope,
                        "window_end": window,
                        "model": model,
                        "team_count": len({
                            (row["target_season"], row["team"]) for row in selected
                        }),
                        "team_resource_count": len(selected),
                        "actual_games": sum(int(row["actual_games"]) for row in selected),
                        "actual_opportunities": f"{sum(float(row['actual_opportunities']) for row in selected):.0f}",
                        "mean_absolute_error_per_game": f"{sum(errors) / len(errors):.9f}",
                        "root_mean_squared_error_per_game": f"{math.sqrt(sum(error * error for error in errors) / len(errors)):.9f}",
                        "median_absolute_error_per_game": f"{_percentile(errors, 0.5):.9f}",
                        "delta_mae_vs_league": f"{sum(errors) / len(errors) - baseline_mae:.9f}",
                    })
    return output


def paired_resource_comparisons(
    predictions: list[dict[str, Any]],
    *,
    samples: int,
    seed: int,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for segment in ("development", "holdout"):
        for scope in ("ALL", *RESOURCES):
            for window in WINDOWS:
                rows = [
                    row for row in predictions
                    if row["segment"] == segment
                    and int(row["window_end"]) == window
                    and (scope == "ALL" or row["resource"] == scope)
                ]
                lookup = {
                    (row["target_season"], row["team"], row["resource"], row["model"]): row
                    for row in rows
                }
                for challenger in MODEL_PRIOR_GAMES:
                    if challenger == BASE_MODEL:
                        continue
                    paired: list[tuple[tuple[int, str], float]] = []
                    for key, row in lookup.items():
                        target, team, resource, model = key
                        if model != challenger:
                            continue
                        baseline = lookup.get((target, team, resource, BASE_MODEL))
                        if baseline is None:
                            continue
                        paired.append((
                            (int(target), team),
                            float(row["absolute_error_per_game"])
                            - float(baseline["absolute_error_per_game"]),
                        ))
                    clusters: dict[tuple[int, str], list[float]] = defaultdict(list)
                    for cluster, delta in paired:
                        clusters[cluster].append(delta)
                    cluster_means = [
                        sum(items) / len(items) for items in clusters.values()
                    ]
                    if not cluster_means:
                        continue
                    material = (
                        f"{seed}|{segment}|{scope}|{window}|{challenger}|{BASE_MODEL}"
                    ).encode()
                    comparison_seed = int.from_bytes(
                        hashlib.sha256(material).digest()[:8], "big"
                    )
                    rng = random.Random(comparison_seed)
                    bootstrap = [
                        sum(rng.choice(cluster_means) for _ in cluster_means)
                        / len(cluster_means)
                        for _ in range(samples)
                    ]
                    mean_delta = sum(delta for _, delta in paired) / len(paired)
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
                        "pair_count": len(paired),
                        "cluster_count": len(cluster_means),
                        "mean_error_delta": f"{mean_delta:.9f}",
                        "delta_ci90_low": f"{low:.9f}",
                        "delta_ci90_high": f"{high:.9f}",
                        "paired_win_rate": f"{sum(delta < 0 for _, delta in paired) / len(paired):.6f}",
                        "interpretation": interpretation,
                    })
    return output


def recommend_resource_models(
    evaluations: list[Mapping[str, Any]],
    comparisons: list[Mapping[str, Any]],
) -> dict[str, Any]:
    resources: dict[str, Any] = {}
    promoted: list[str] = []
    for resource in RESOURCES:
        development = [
            row for row in evaluations
            if row["segment"] == "development" and row["scope"] == resource
        ]
        holdout = [
            row for row in evaluations
            if row["segment"] == "holdout" and row["scope"] == resource
        ]
        if not development or not holdout:
            raise ResourceBacktestDataError(
                f"missing development or holdout evaluation for {resource}"
            )
        development_means = {
            model: sum(
                float(row["mean_absolute_error_per_game"])
                for row in development if row["model"] == model
            ) / len(WINDOWS)
            for model in MODEL_PRIOR_GAMES
        }
        candidate = min(
            (model for model in MODEL_PRIOR_GAMES if model != BASE_MODEL),
            key=lambda model: (development_means[model], model),
        )
        development_comparisons = [
            row for row in comparisons
            if row["segment"] == "development" and row["scope"] == resource
            and row["challenger"] == candidate
        ]
        holdout_comparisons = [
            row for row in comparisons
            if row["segment"] == "holdout" and row["scope"] == resource
            and row["challenger"] == candidate
        ]
        development_deltas = [float(row["mean_error_delta"]) for row in development_comparisons]
        holdout_deltas = [float(row["mean_error_delta"]) for row in holdout_comparisons]
        clear_wins = sum(float(row["delta_ci90_high"]) < 0 for row in holdout_comparisons)
        clear_losses = sum(float(row["delta_ci90_low"]) > 0 for row in holdout_comparisons)
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
            promoted.append(resource)
        holdout_means = {
            model: sum(
                float(row["mean_absolute_error_per_game"])
                for row in holdout if row["model"] == model
            ) / len(WINDOWS)
            for model in MODEL_PRIOR_GAMES
        }
        resources[resource] = {
            "development_candidate": candidate,
            "development_mean_absolute_error_per_game": {
                model: round(value, 6) for model, value in development_means.items()
            },
            "holdout_mean_absolute_error_per_game": {
                model: round(value, 6) for model, value in holdout_means.items()
            },
            "development_deltas_vs_league": [round(value, 6) for value in development_deltas],
            "holdout_deltas_vs_league": [round(value, 6) for value in holdout_deltas],
            "holdout_clear_win_windows": clear_wins,
            "holdout_clear_loss_windows": clear_losses,
            "reference_gate_passed": passes,
            "selected_reference_model": selected,
        }
    return {
        "baseline_model": BASE_MODEL,
        "models": list(MODEL_PRIOR_GAMES),
        "promotion_rule": (
            "choose the lowest-development-error team model per resource; require "
            "negative deltas in all development and untouched-holdout windows, at "
            f"least {MIN_CLEAR_HOLDOUT_WINS} clear holdout wins, and no clear loss"
        ),
        "team_reference_resources": promoted,
        "league_reference_resources": [resource for resource in RESOURCES if resource not in promoted],
        "resources": resources,
        "current_mean_policy": (
            "reference-model selection is used only to calibrate an empirical error "
            "radius; it does not replace the caller-aware 2026 point estimate"
        ),
    }


def resource_calibration_rows(
    predictions: list[Mapping[str, Any]],
    recommendation: Mapping[str, Any],
    *,
    development_seasons: tuple[int, ...],
    holdout_season: int,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for resource in RESOURCES:
        model = recommendation["resources"][resource]["selected_reference_model"]
        development = [
            row for row in predictions
            if row["segment"] == "development" and row["resource"] == resource
            and row["model"] == model and int(row["window_end"]) == 18
        ]
        holdout = [
            row for row in predictions
            if row["segment"] == "holdout" and row["resource"] == resource
            and row["model"] == model and int(row["window_end"]) == 18
        ]
        radius = _conformal_radius(
            (float(row["absolute_error_per_game"]) for row in development),
            NOMINAL_COVERAGE,
        )
        below = above = covered = 0
        widths: list[float] = []
        for row in holdout:
            prediction = float(row["predicted_per_game"])
            actual = float(row["actual_per_game"])
            low = max(0.0, prediction - radius)
            high = prediction + radius
            widths.append(high - low)
            if actual < low:
                below += 1
            elif actual > high:
                above += 1
            else:
                covered += 1
        if not holdout:
            raise ResourceBacktestDataError(f"no holdout rows for {resource}")
        output.append({
            "resource": resource,
            "model": model,
            "calibration_seasons": "|".join(map(str, development_seasons)),
            "calibration_window_end": 18,
            "calibration_team_seasons": len(development),
            "nominal_coverage": f"{NOMINAL_COVERAGE:.3f}",
            "conformal_absolute_error_per_game_radius": f"{radius:.9f}",
            "holdout_season": holdout_season,
            "holdout_team_count": len(holdout),
            "holdout_coverage": f"{covered / len(holdout):.6f}",
            "holdout_below_count": below,
            "holdout_above_count": above,
            "holdout_mean_interval_width": f"{sum(widths) / len(widths):.9f}",
            "current_mean_transfer_status": "provisional_radius_transfer_to_caller_aware_mean_not_directly_calibrated",
            "calibration_status": "development_split_conformal_radius_tested_once_on_untouched_holdout",
        })
    return output


def build_resource_backtest(
    player_history: str | Path,
    *,
    development_seasons: Iterable[int] = (2023, 2024),
    holdout_season: int = 2025,
    history_lookback: int = 3,
    bootstrap_samples: int = 2000,
    random_seed: int = 20260903,
    expected_team_count: int = 32,
) -> ResourceBacktestResult:
    """Backtest team resource-rate references and calibrate per-game errors."""

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
    if (
        isinstance(expected_team_count, bool) or not isinstance(expected_team_count, int)
        or expected_team_count < 2
    ):
        raise ValueError("expected_team_count must be an integer of at least 2")

    root = Path(player_history)
    manifest_raw, manifest = _read_manifest(root)
    opportunities_raw, opportunity_rows = _verified_history_csv(
        root,
        manifest,
        "weekly_opportunities.csv",
        {"season", "week", "team", "position", "gsis_id", "player_name",
         "dropbacks", "carries", "targets"},
    )
    schedule_raw, schedule_rows = _verified_history_csv(
        root,
        manifest,
        "team_schedule.csv",
        {"season", "week", "gameday", "game_id", "team", "opponent", "home_away"},
    )
    games, history = _resource_history(
        opportunity_rows, schedule_rows, expected_team_count=expected_team_count
    )
    available = {key[0] for key in games}
    targets = (*development, holdout_season)
    if not set(targets).issubset(available):
        raise ResourceBacktestDataError(
            f"schedule lacks target seasons {sorted(set(targets) - available)}"
        )

    predictions: list[dict[str, Any]] = []
    for target in targets:
        segment = "development" if target in development else "holdout"
        target_teams = sorted({key[2] for key in games if key[0] == target})
        if len(target_teams) != expected_team_count:
            raise ResourceBacktestDataError(
                f"target season {target} has {len(target_teams)} teams; expected {expected_team_count}"
            )
        for resource in RESOURCES:
            training, league_opportunities, league_games, team_history = _training_rates(
                games,
                history,
                target_season=target,
                resource=resource,
                history_lookback=history_lookback,
            )
            league_rate = league_opportunities / league_games
            for team in target_teams:
                team_opportunities, team_games = team_history.get(team, (0.0, 0.0))
                for window in WINDOWS:
                    actual_games = sum(
                        game for (season, week, row_team), game in games.items()
                        if season == target and row_team == team and week <= window
                    )
                    if actual_games <= 0:
                        raise ResourceBacktestDataError(
                            f"{target} {team} Weeks 1-{window} has no games"
                        )
                    actual_opportunities = sum(
                        value for (season, week, row_team, row_resource), value in history.items()
                        if season == target and row_team == team
                        and row_resource == resource and week <= window
                    )
                    actual_rate = actual_opportunities / actual_games
                    for model, prior in MODEL_PRIOR_GAMES.items():
                        forecast = _model_rate(
                            model,
                            league_rate=league_rate,
                            team_opportunities=team_opportunities,
                            team_games=team_games,
                        )
                        predictions.append({
                            "target_season": target,
                            "segment": segment,
                            "window_end": window,
                            "team": team,
                            "resource": resource,
                            "model": model,
                            "prior_games": "" if prior is None else f"{prior:.0f}",
                            "training_seasons": "|".join(map(str, training)),
                            "training_league_opportunities": f"{league_opportunities:.6f}",
                            "training_league_games": f"{league_games:.6f}",
                            "training_league_rate": f"{league_rate:.9f}",
                            "training_team_opportunities": f"{team_opportunities:.6f}",
                            "training_team_games": f"{team_games:.6f}",
                            "predicted_per_game": f"{forecast:.9f}",
                            "actual_games": actual_games,
                            "actual_opportunities": f"{actual_opportunities:.6f}",
                            "actual_per_game": f"{actual_rate:.9f}",
                            "absolute_error_per_game": f"{abs(forecast - actual_rate):.9f}",
                        })
    evaluations = _evaluations(predictions)
    comparisons = paired_resource_comparisons(
        predictions, samples=bootstrap_samples, seed=random_seed
    )
    recommendation = recommend_resource_models(evaluations, comparisons)
    calibration = resource_calibration_rows(
        predictions,
        recommendation,
        development_seasons=development,
        holdout_season=holdout_season,
    )
    return ResourceBacktestResult(
        player_history_path=root,
        input_hashes={
            "player_history_manifest.json": hashlib.sha256(manifest_raw).hexdigest(),
            "weekly_opportunities.csv": hashlib.sha256(opportunities_raw).hexdigest(),
            "team_schedule.csv": hashlib.sha256(schedule_raw).hexdigest(),
        },
        development_seasons=development,
        holdout_season=holdout_season,
        history_lookback=history_lookback,
        bootstrap_samples=bootstrap_samples,
        random_seed=random_seed,
        prediction_rows=tuple(sorted(predictions, key=lambda row: (
            row["target_season"], row["window_end"], row["team"],
            row["resource"], row["model"],
        ))),
        evaluation_rows=tuple(sorted(evaluations, key=lambda row: (
            row["segment"], row["scope"], row["window_end"], row["model"],
        ))),
        comparison_rows=tuple(sorted(comparisons, key=lambda row: (
            row["segment"], row["scope"], row["window_end"], row["challenger"],
        ))),
        calibration_rows=tuple(calibration),
        recommendation=recommendation,
    )


def _csv_bytes(fields: tuple[str, ...], rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def write_resource_backtest_snapshot(
    result: ResourceBacktestResult,
    root: str | Path,
) -> Path:
    """Atomically publish resource predictions, gates, and calibration radii."""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    label = "-".join(map(str, (*result.development_seasons, result.holdout_season)))
    parent = Path(root) / "resource_backtest" / label
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"resource backtest snapshot exists: {destination}")
    artifacts = {
        "predictions.csv": _csv_bytes(PREDICTION_FIELDS, result.prediction_rows),
        "model_evaluation.csv": _csv_bytes(EVALUATION_FIELDS, result.evaluation_rows),
        "paired_comparisons.csv": _csv_bytes(COMPARISON_FIELDS, result.comparison_rows),
        "resource_calibration.csv": _csv_bytes(CALIBRATION_FIELDS, result.calibration_rows),
    }
    fields = {
        "predictions.csv": PREDICTION_FIELDS,
        "model_evaluation.csv": EVALUATION_FIELDS,
        "paired_comparisons.csv": COMPARISON_FIELDS,
        "resource_calibration.csv": CALIBRATION_FIELDS,
    }
    aggregate_coverage = sum(
        float(row["holdout_coverage"]) * int(row["holdout_team_count"])
        for row in result.calibration_rows
    ) / sum(int(row["holdout_team_count"]) for row in result.calibration_rows)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        ),
        "development_seasons": list(result.development_seasons),
        "holdout_season": result.holdout_season,
        "windows": list(WINDOWS),
        "resources": list(RESOURCES),
        "models": dict(MODEL_PRIOR_GAMES),
        "methodology": {
            "question": "how much per-game error remains in simple time-correct team resource-rate references",
            "history_boundary": "only seasons strictly before each target with exponential recency weighting",
            "development_holdout": "2023-24 select and gate a reference; 2025 remains untouched until the fixed gate",
            "actuals": "GSIS-keyed nflverse weekly attempts/sacks, carries, and targets aggregated only across scheduled games",
            "uncertainty": "paired 90% bootstrap intervals resample team-season clusters; split-conformal radii use development Week 18 and are evaluated once on 2025",
            "current_mean_boundary": "the 2026 mean remains caller-aware; these empirical residual radii transfer around that mean provisionally and are not direct coverage calibration of it",
            "scope": "RB carries and RB/WR/TE targets only; QB resources, efficiency, touchdowns, opponent, and fantasy points are excluded",
        },
        "parameters": {
            "history_lookback": result.history_lookback,
            "history_recency_factor": RECENCY_FACTOR,
            "model_prior_games": dict(MODEL_PRIOR_GAMES),
            "bootstrap_samples": result.bootstrap_samples,
            "random_seed": result.random_seed,
            "nominal_coverage": NOMINAL_COVERAGE,
        },
        "inputs": {
            "player_history": str(result.player_history_path),
            "sha256": dict(result.input_hashes),
        },
        "quality": {
            "prediction_rows": len(result.prediction_rows),
            "evaluation_rows": len(result.evaluation_rows),
            "comparison_rows": len(result.comparison_rows),
            "calibration_rows": len(result.calibration_rows),
            "minimum_holdout_coverage": min(
                float(row["holdout_coverage"]) for row in result.calibration_rows
            ),
            "aggregate_holdout_coverage": aggregate_coverage,
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
