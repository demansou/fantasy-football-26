"""Empirical weekly availability marginals and role-redistribution scenarios.

This layer learns population status-to-active curves from historical weekly NFL
rosters.  First-party evidence may impose hard constraints, but it never supplies
an invented return probability.  Role scenarios use common player-availability
draws across a team and reconcile every simulated resource allocation.
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
from urllib.parse import urlparse


SCHEMA_VERSION = "1.1.0"
MODEL_VERSION = "weekly-availability-status-cohort-v0.2.0"
MODEL_STATUS = "population_calibrated_status_prior_not_individual_medical_forecast"
ROLE_POSITIONS = {"QB", "RB", "WR", "TE"}
AFFILIATED_STATUSES = {"ACT", "DEV", "RES", "RSR", "PUP", "RSN", "SUS", "EXE"}
WEEKS = tuple(range(1, 19))
MIN_COHORT_N = 30
INTERVAL_Z = 1.6448536269514722  # 90% Wilson interval

ACTIVE_53 = "active_53"
PRACTICE_SQUAD = "practice_squad"
RETURN_ELIGIBLE_RESERVE = "return_eligible_reserve"
RESERVE_NFI = "reserve_nfi"
RESERVE_OTHER = "reserve_other"
EXEMPT_SUSPENDED = "exempt_or_suspended"
NONACTIVE = "all_nonactive_affiliated"

AVAILABILITY_FIELDS = (
    "season", "week", "gameday", "team", "opponent", "home_away",
    "scheduled_game", "position", "gsis_id", "player_name",
    "current_status", "roster_status", "status_description", "cohort_family",
    "cohort_level", "training_n", "training_active", "active_probability_low",
    "active_probability_median", "active_probability_high", "minimum_games_missed",
    "hard_constraint_applied", "constraint_reason", "evidence_status", "evidence_source_count",
    "ffc_source_player_id", "ffc_adp", "model_support", "model_status",
)

EXPECTED_ROLE_FIELDS = (
    "season", "week", "gameday", "team", "opponent", "home_away",
    "scheduled_game", "position", "resource", "gsis_id", "player_name",
    "current_status", "active_probability_median", "latent_role_weight",
    "expected_share_mean", "share_p10", "share_p50", "share_p90",
    "team_pool_per_game", "team_pool_this_week", "expected_opportunities_this_week", "opportunities_p10",
    "opportunities_p50", "opportunities_p90", "ffc_source_player_id", "ffc_adp",
    "simulation_draws", "model_status",
)

RECONCILIATION_FIELDS = (
    "season", "week", "gameday", "team", "opponent", "home_away",
    "scheduled_game", "position", "resource", "candidate_count",
    "simulation_draws", "team_pool_per_game", "team_pool_this_week",
    "reconciliation_target", "expected_player_share_sum",
    "unallocated_draw_rate", "reconciled_share_sum", "expected_player_opportunities",
    "expected_unallocated_opportunities", "reconciliation_error",
)

BACKTEST_FIELDS = (
    "segment", "model", "observation_count", "brier_score", "mean_prediction",
    "observed_active_rate", "delta_vs_active_flag_baseline", "delta_ci90_low",
    "delta_ci90_high", "paired_cluster_count", "comparison_interpretation",
)

EVIDENCE_REVIEW_FIELDS = (
    "review_type", "gsis_id", "player_name", "team", "position", "issue", "details",
)


class AvailabilityDataError(ValueError):
    """Raised when an input cannot support an audited availability build."""


@dataclass(frozen=True)
class AvailabilityResult:
    season: int
    history_path: Path
    player_context_path: Path
    role_snapshot_path: Path
    evidence_path: Path
    input_hashes: Mapping[str, str]
    weekly_availability: tuple[Mapping[str, Any], ...]
    weekly_expected_roles: tuple[Mapping[str, Any], ...]
    reconciliation: tuple[Mapping[str, Any], ...]
    backtest: tuple[Mapping[str, Any], ...]
    evidence_review: tuple[Mapping[str, Any], ...]
    evaluation: Mapping[str, Any]
    simulation_draws: int
    random_seed: int


def _resolve(path: str | Path, filename: str) -> Path:
    resolved = Path(path)
    if resolved.is_dir():
        resolved = resolved / filename
    if not resolved.is_file():
        raise AvailabilityDataError(f"input does not exist: {resolved}")
    return resolved


def _read_csv(
    path: Path, required: set[str], *, allow_empty: bool = False
) -> tuple[bytes, list[dict[str, str]]]:
    raw = path.read_bytes()
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        fields = set(reader.fieldnames or ())
        rows = list(reader)
    except UnicodeDecodeError as error:
        raise AvailabilityDataError(f"CSV is not UTF-8: {path}") from error
    missing = required - fields
    if missing or (not rows and not allow_empty):
        raise AvailabilityDataError(
            f"CSV is empty or missing fields {sorted(missing)}: {path}"
        )
    return raw, rows


def _float(value: Any, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise AvailabilityDataError(f"{context} must be numeric") from error
    if not math.isfinite(result):
        raise AvailabilityDataError(f"{context} must be finite")
    return result


def _history_family(status: str, description: str) -> str | None:
    status = status.strip().upper()
    description = description.strip().upper()
    if status in {"ACT", "INA"}:
        return ACTIVE_53
    if status == "DEV":
        return PRACTICE_SQUAD
    if status == "PUP":
        return RETURN_ELIGIBLE_RESERVE
    if status == "RES" and description in {"R04", "R48"}:
        return RETURN_ELIGIBLE_RESERVE
    if status == "RES" and description in {"R05", "R27", "R47", "R49"}:
        return RESERVE_NFI
    if status == "RES" and description in {"R30", "R33", "R40"}:
        return EXEMPT_SUSPENDED
    if status == "RES":
        return RESERVE_OTHER
    if status in {"EXE", "SUS"}:
        return EXEMPT_SUSPENDED
    return None


def _current_family(status: str, evidence_status: str = "") -> str:
    status = status.strip().upper()
    evidence_status = evidence_status.strip().lower()
    if evidence_status == "practice_squad":
        return PRACTICE_SQUAD
    if evidence_status in {
        "reserve_pup", "reserve_injured_designated_for_return",
    }:
        return RETURN_ELIGIBLE_RESERVE
    if evidence_status == "reserve_injured":
        return RESERVE_OTHER
    if evidence_status == "commissioners_exempt":
        return EXEMPT_SUSPENDED
    mapping = {
        "ACT": ACTIVE_53,
        "DEV": PRACTICE_SQUAD,
        "PUP": RETURN_ELIGIBLE_RESERVE,
        "RSR": RETURN_ELIGIBLE_RESERVE,
        "RSN": RESERVE_NFI,
        "RES": RESERVE_OTHER,
        "SUS": EXEMPT_SUSPENDED,
        "EXE": EXEMPT_SUSPENDED,
    }
    if status not in mapping:
        raise AvailabilityDataError(f"unsupported current affiliated status {status!r}")
    return mapping[status]


def _wilson(successes: int, trials: int) -> tuple[float, float, float]:
    if trials <= 0 or not 0 <= successes <= trials:
        raise AvailabilityDataError("invalid binomial cohort counts")
    probability = (successes + 1.0) / (trials + 2.0)
    observed = successes / trials
    z2 = INTERVAL_Z * INTERVAL_Z
    denominator = 1.0 + z2 / trials
    center = (observed + z2 / (2.0 * trials)) / denominator
    margin = (
        INTERVAL_Z
        * math.sqrt(observed * (1.0 - observed) / trials + z2 / (4.0 * trials * trials))
        / denominator
    )
    return max(0.0, center - margin), probability, min(1.0, center + margin)


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        raise AvailabilityDataError("cannot summarize empty simulation values")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _build_history(
    rows: Iterable[Mapping[str, str]],
    schedule_rows: Iterable[Mapping[str, str]],
) -> tuple[
    dict[tuple[int, str], Mapping[str, str]],
    dict[tuple[int, str, int], bool],
    dict[tuple[str, str, int], list[int]],
    dict[int, dict[tuple[str, str, int], list[int]]],
]:
    by_player_week: dict[tuple[int, str, int], list[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        season = int(row["season"])
        week = int(row["week"])
        if week in WEEKS and row["gsis_id"] and row["position"] in ROLE_POSITIONS:
            by_player_week[(season, row["gsis_id"], week)].append(row)
    opening: dict[tuple[int, str], Mapping[str, str]] = {}
    priority = {"ACT": 0, "INA": 1, "DEV": 2, "RES": 3, "EXE": 4, "SUS": 5}
    for (season, player_id, week), candidates in by_player_week.items():
        if week == 1:
            selected = min(
                candidates,
                key=lambda row: priority.get(row["status"].strip().upper(), 99),
            )
            if _history_family(selected["status"], selected["status_description"]):
                opening[(season, player_id)] = selected

    scheduled_games = {
        (int(row["season"]), row["team"], int(row["week"]))
        for row in schedule_rows
    }
    outcomes: dict[tuple[int, str, int], bool] = {}
    for (season, player_id), opening_row in opening.items():
        opening_team = opening_row["team"]
        for week in WEEKS:
            candidates = by_player_week.get((season, player_id, week), [])
            candidate_has_game = any(
                (season, row["team"], week) in scheduled_games for row in candidates
            )
            if not candidate_has_game and (season, opening_team, week) not in scheduled_games:
                # Weekly roster releases omit bye teams. A missing bye row is not an
                # inactive-game observation and must not enter the denominator.
                continue
            outcomes[(season, player_id, week)] = any(
                row["status"].strip().upper() == "ACT"
                and (season, row["team"], week) in scheduled_games
                for row in candidates
            )

    totals: dict[tuple[str, str, int], list[int]] = defaultdict(lambda: [0, 0])
    by_season: dict[int, dict[tuple[str, str, int], list[int]]] = defaultdict(
        lambda: defaultdict(lambda: [0, 0])
    )
    for (season, player_id), row in opening.items():
        family = _history_family(row["status"], row["status_description"])
        assert family is not None
        position = row["position"]
        active_flag = ACTIVE_53 if family == ACTIVE_53 else NONACTIVE
        for week in WEEKS:
            outcome_key = season, player_id, week
            if outcome_key not in outcomes:
                continue
            active = int(outcomes[outcome_key])
            for key in (
                (family, position, week),
                (family, "ALL", week),
                (active_flag, position, week),
                (active_flag, "ALL", week),
            ):
                totals[key][0] += 1
                totals[key][1] += active
                by_season[season][key][0] += 1
                by_season[season][key][1] += active
    if not opening:
        raise AvailabilityDataError("historical weekly rosters have no Week 1 cohorts")
    return opening, outcomes, totals, by_season


def _counts_excluding(
    totals: Mapping[tuple[str, str, int], list[int]],
    by_season: Mapping[int, Mapping[tuple[str, str, int], list[int]]],
    season: int | None,
) -> dict[tuple[str, str, int], tuple[int, int]]:
    result: dict[tuple[str, str, int], tuple[int, int]] = {}
    excluded = by_season.get(season, {}) if season is not None else {}
    for key, value in totals.items():
        subtraction = excluded.get(key, (0, 0))
        result[key] = value[0] - subtraction[0], value[1] - subtraction[1]
    return result


def _select_counts(
    counts: Mapping[tuple[str, str, int], tuple[int, int]],
    family: str,
    position: str,
    week: int,
    *,
    baseline: bool = False,
) -> tuple[int, int, str]:
    active_flag = ACTIVE_53 if family == ACTIVE_53 else NONACTIVE
    candidates = (
        ((active_flag, position, week), "active_flag_position"),
        ((active_flag, "ALL", week), "active_flag_all_positions"),
    ) if baseline else (
        ((family, position, week), "status_family_position"),
        ((family, "ALL", week), "status_family_all_positions"),
        ((active_flag, position, week), "fallback_active_flag_position"),
        ((active_flag, "ALL", week), "fallback_active_flag_all_positions"),
    )
    for key, level in candidates:
        trials, successes = counts.get(key, (0, 0))
        if trials >= MIN_COHORT_N:
            return trials, successes, level
    key, level = candidates[-1]
    trials, successes = counts.get(key, (0, 0))
    if trials <= 0:
        raise AvailabilityDataError(
            f"no historical cohort for {family}/{position}/Week {week}"
        )
    return trials, successes, f"weak_{level}"


def _load_evidence(path: Path) -> tuple[bytes, dict[str, Mapping[str, Any]], set[str]]:
    raw = path.read_bytes()
    try:
        root = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AvailabilityDataError(f"invalid availability evidence: {path}") from error
    if not isinstance(root, Mapping) or not str(root.get("schema_version", "")).startswith("1."):
        raise AvailabilityDataError("availability evidence must use schema version 1.x")
    rules = root.get("rule_sources", [])
    if not isinstance(rules, list):
        raise AvailabilityDataError("rule_sources must be a list")
    rule_ids: set[str] = set()
    for rule in rules:
        if not isinstance(rule, Mapping) or not str(rule.get("rule_id", "")).strip():
            raise AvailabilityDataError("each rule source needs a rule_id")
        rule_id = str(rule["rule_id"])
        if rule_id in rule_ids:
            raise AvailabilityDataError(f"duplicate rule_id {rule_id}")
        rule_ids.add(rule_id)
        urls = rule.get("urls")
        if not isinstance(urls, list) or not urls:
            raise AvailabilityDataError(f"rule {rule_id} has no URLs")
        for url in urls:
            parsed = urlparse(str(url))
            if parsed.scheme != "https" or not parsed.netloc:
                raise AvailabilityDataError(f"rule {rule_id} has an invalid URL")
    records = root.get("records")
    if not isinstance(records, list):
        raise AvailabilityDataError("availability evidence records must be a list")
    evidence: dict[str, Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise AvailabilityDataError("availability evidence record must be an object")
        player_id = str(record.get("gsis_id", "")).strip()
        if not player_id or player_id in evidence:
            raise AvailabilityDataError("availability evidence has missing/duplicate GSIS ID")
        minimum = record.get("minimum_games_missed", 0)
        if isinstance(minimum, bool) or not isinstance(minimum, int) or not 0 <= minimum <= 18:
            raise AvailabilityDataError(f"invalid minimum_games_missed for {player_id}")
        constraint = str(record.get("constraint_rule_id", "")).strip()
        if minimum and constraint not in rule_ids:
            raise AvailabilityDataError(f"{player_id} minimum lacks a valid rule source")
        sources = record.get("sources")
        if not isinstance(sources, list) or not sources:
            raise AvailabilityDataError(f"{player_id} has no evidence sources")
        for source in sources:
            parsed = urlparse(str(source.get("url", ""))) if isinstance(source, Mapping) else None
            if parsed is None or parsed.scheme != "https" or not parsed.netloc:
                raise AvailabilityDataError(f"{player_id} has an invalid evidence URL")
        evidence[player_id] = record
    return raw, evidence, rule_ids


def _backtest(
    opening: Mapping[tuple[int, str], Mapping[str, str]],
    outcomes: Mapping[tuple[int, str, int], bool],
    totals: Mapping[tuple[str, str, int], list[int]],
    by_season: Mapping[int, Mapping[tuple[str, str, int], list[int]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    training_counts = {
        season: _counts_excluding(totals, by_season, season)
        for season in {key[0] for key in opening}
    }
    for (season, player_id), row in opening.items():
        family = _history_family(row["status"], row["status_description"])
        assert family is not None
        counts = training_counts[season]
        for week in WEEKS:
            outcome_key = season, player_id, week
            if outcome_key not in outcomes:
                continue
            actual = float(outcomes[outcome_key])
            for model, baseline in (
                ("status_family_v0", False),
                ("active_flag_baseline", True),
            ):
                trials, successes, _ = _select_counts(
                    counts, family, row["position"], week, baseline=baseline
                )
                probability = _wilson(successes, trials)[1]
                observations.append({
                    "season": season,
                    "player_id": player_id,
                    "family": family,
                    "active_flag": ACTIVE_53 if family == ACTIVE_53 else NONACTIVE,
                    "week": week,
                    "model": model,
                    "prediction": probability,
                    "actual": actual,
                    "squared_error": (probability - actual) ** 2,
                })
    segments = {
        "all": lambda row: True,
        "opening_active_53": lambda row: row["active_flag"] == ACTIVE_53,
        "opening_nonactive": lambda row: row["active_flag"] == NONACTIVE,
        "weeks_1_4": lambda row: row["week"] <= 4,
        "weeks_5_8": lambda row: 5 <= row["week"] <= 8,
        "weeks_9_18": lambda row: row["week"] >= 9,
    }
    rows: list[dict[str, Any]] = []
    for segment, predicate in segments.items():
        selected = [row for row in observations if predicate(row)]
        baseline_brier = sum(
            row["squared_error"] for row in selected
            if row["model"] == "active_flag_baseline"
        ) / sum(row["model"] == "active_flag_baseline" for row in selected)
        paired: dict[tuple[int, str, int], dict[str, float]] = defaultdict(dict)
        for row in selected:
            paired[(row["season"], row["player_id"], row["week"])][
                row["model"]
            ] = row["squared_error"]
        cluster_differences: dict[tuple[int, str], list[float]] = defaultdict(list)
        for (season, player_id, _), values in paired.items():
            if set(values) == {"status_family_v0", "active_flag_baseline"}:
                cluster_differences[(season, player_id)].append(
                    values["status_family_v0"] - values["active_flag_baseline"]
                )
        cluster_means = [
            sum(values) / len(values) for values in cluster_differences.values()
        ]
        if len(cluster_means) < 2:
            raise AvailabilityDataError(
                f"{segment} has too few paired player-season clusters"
            )
        paired_delta = sum(cluster_means) / len(cluster_means)
        variance = sum(
            (value - paired_delta) ** 2 for value in cluster_means
        ) / (len(cluster_means) - 1)
        margin = INTERVAL_Z * math.sqrt(variance / len(cluster_means))
        delta_low = paired_delta - margin
        delta_high = paired_delta + margin
        if delta_high < 0:
            interpretation = "status_family_lower_error_ci_excludes_zero"
        elif delta_low > 0:
            interpretation = "status_family_higher_error_ci_excludes_zero"
        else:
            interpretation = "difference_uncertain_ci_includes_zero"
        for model in ("status_family_v0", "active_flag_baseline"):
            model_rows = [row for row in selected if row["model"] == model]
            brier = sum(row["squared_error"] for row in model_rows) / len(model_rows)
            rows.append({
                "segment": segment,
                "model": model,
                "observation_count": len(model_rows),
                "brier_score": f"{brier:.6f}",
                "mean_prediction": f"{sum(row['prediction'] for row in model_rows) / len(model_rows):.6f}",
                "observed_active_rate": f"{sum(row['actual'] for row in model_rows) / len(model_rows):.6f}",
                "delta_vs_active_flag_baseline": f"{brier - baseline_brier:.6f}",
                "delta_ci90_low": f"{delta_low:.6f}" if model == "status_family_v0" else "0.000000",
                "delta_ci90_high": f"{delta_high:.6f}" if model == "status_family_v0" else "0.000000",
                "paired_cluster_count": len(cluster_means),
                "comparison_interpretation": interpretation if model == "status_family_v0" else "reference_model",
            })
    overall = next(
        row for row in rows if row["segment"] == "all" and row["model"] == "status_family_v0"
    )
    return rows, {
        "method": "leave_one_season_out_2021_2025",
        "target": "weekly game-active roster status",
        "overall_status_family_brier": float(overall["brier_score"]),
        "overall_delta_vs_active_flag_baseline": float(
            overall["delta_vs_active_flag_baseline"]
        ),
        "overall_delta_ci90": [
            float(overall["delta_ci90_low"]), float(overall["delta_ci90_high"])
        ],
        "status_family_improves_overall_brier": (
            float(overall["delta_vs_active_flag_baseline"]) < 0
        ),
        "overall_improvement_ci_excludes_zero": (
            float(overall["delta_ci90_high"]) < 0
        ),
        "interpretation": (
            "population status prior only; no claim of individual medical calibration"
        ),
    }


def build_weekly_availability(
    player_history: str | Path,
    player_context: str | Path,
    role_snapshot: str | Path,
    evidence_path: str | Path,
    *,
    simulation_draws: int = 1000,
    random_seed: int = 20260902,
) -> AvailabilityResult:
    """Fit weekly status marginals and simulate reconciled player role allocations."""

    if (
        isinstance(simulation_draws, bool) or not isinstance(simulation_draws, int)
        or not 100 <= simulation_draws <= 100_000
    ):
        raise ValueError("simulation_draws must be an integer from 100 to 100000")
    if isinstance(random_seed, bool) or not isinstance(random_seed, int):
        raise ValueError("random_seed must be an integer")

    history_root = Path(player_history)
    context_root = Path(player_context)
    role_root = Path(role_snapshot)
    evidence_file = Path(evidence_path)
    history_file = _resolve(history_root, "weekly_rosters.csv")
    schedule_file = _resolve(history_root, "team_schedule.csv")
    roster_file = _resolve(context_root, "current_roster.csv")
    candidate_file = _resolve(role_root, "player_role_candidates.csv")
    team_pool_file = _resolve(role_root, "team_reconciliation.csv")
    history_raw, history_rows = _read_csv(
        history_file,
        {"season", "week", "team", "position", "gsis_id", "status", "status_description"},
    )
    schedule_raw, schedule_rows = _read_csv(
        schedule_file,
        {"season", "week", "gameday", "game_id", "team", "opponent", "home_away"},
    )
    roster_raw, roster_rows = _read_csv(
        roster_file,
        {
            "season", "team", "fantasy_position", "gsis_id", "full_name",
            "current_status", "roster_status", "status_description",
        },
    )
    candidate_raw, candidates = _read_csv(
        candidate_file,
        {"season", "team", "position", "resource", "gsis_id", "player_name", "current_status", "latent_role_weight"},
    )
    pool_raw, pools = _read_csv(
        team_pool_file,
        {"season", "team", "position", "resource", "team_pool_per_game"},
    )
    evidence_raw, evidence, _ = _load_evidence(evidence_file)

    seasons = {int(row["season"]) for row in roster_rows}
    if len(seasons) != 1:
        raise AvailabilityDataError("current roster must contain one season")
    season = next(iter(seasons))
    if any(int(row["season"]) != season for row in candidates + pools):
        raise AvailabilityDataError("role inputs do not match current roster season")
    current_schedule = {
        (row["team"], int(row["week"])): row
        for row in schedule_rows if int(row["season"]) == season
    }
    if len(current_schedule) != sum(
        int(row["season"]) == season for row in schedule_rows
    ):
        raise AvailabilityDataError("current schedule contains duplicate team/week rows")
    schedule_teams = {team for team, _ in current_schedule}
    roster_teams = {row["team"] for row in roster_rows if row["team"]}
    if schedule_teams != roster_teams:
        raise AvailabilityDataError(
            "current schedule and roster team sets do not match"
        )
    game_counts = {
        team: sum(schedule_team == team for schedule_team, _ in current_schedule)
        for team in schedule_teams
    }
    if any(count != 17 for count in game_counts.values()):
        raise AvailabilityDataError(
            f"current schedule must contain 17 games per team: {game_counts}"
        )
    roster_by_id = {
        row["gsis_id"]: row for row in roster_rows
        if row["gsis_id"] and row["fantasy_position"] in ROLE_POSITIONS
    }
    if len(roster_by_id) != sum(
        bool(row["gsis_id"]) and row["fantasy_position"] in ROLE_POSITIONS
        for row in roster_rows
    ):
        raise AvailabilityDataError("current skill roster has duplicate GSIS IDs")

    review: list[dict[str, Any]] = []
    for player_id, record in evidence.items():
        roster = roster_by_id.get(player_id)
        if roster is None:
            review.append({
                "review_type": "evidence", "gsis_id": player_id,
                "player_name": record.get("player", ""), "team": record.get("team", ""),
                "position": record.get("position", ""), "issue": "evidence_player_missing",
                "details": "GSIS ID is absent from the current skill roster",
            })
            continue
        if (
            record.get("team") != roster["team"]
            or record.get("position") != roster["fantasy_position"]
            or record.get("current_active") is not False
            or roster["current_status"] == "ACT"
        ):
            review.append({
                "review_type": "evidence", "gsis_id": player_id,
                "player_name": record.get("player", ""), "team": roster["team"],
                "position": roster["fantasy_position"], "issue": "evidence_roster_mismatch",
                "details": "team, position, or active-state evidence disagrees with current roster",
            })

    market_by_id: dict[str, Mapping[str, str]] = {}
    for row in candidates:
        if row.get("ffc_source_player_id"):
            market_by_id[row["gsis_id"]] = row
    market_nonactive = {
        player_id for player_id, row in market_by_id.items()
        if row["current_status"] != "ACT"
    }
    for player_id in sorted(market_nonactive - set(evidence)):
        roster = roster_by_id[player_id]
        review.append({
            "review_type": "market_availability", "gsis_id": player_id,
            "player_name": roster["full_name"], "team": roster["team"],
            "position": roster["fantasy_position"], "issue": "missing_first_party_evidence",
            "details": "FFC-listed non-ACT player requires a reviewed evidence record",
        })
    if review:
        raise AvailabilityDataError(
            f"availability evidence has {len(review)} blocking roster/market mismatches"
        )

    opening, outcomes, totals, by_season = _build_history(history_rows, schedule_rows)
    all_counts = _counts_excluding(totals, by_season, None)
    backtest_rows, evaluation = _backtest(opening, outcomes, totals, by_season)
    availability_rows: list[dict[str, Any]] = []
    probability_lookup: dict[tuple[str, str, int], float] = {}
    affiliated = [
        row for row in roster_by_id.values() if row["current_status"] in AFFILIATED_STATUSES
    ]
    for player in affiliated:
        player_id = player["gsis_id"]
        record = evidence.get(player_id, {})
        family = _current_family(
            player["current_status"], str(record.get("current_status", ""))
        )
        minimum = int(record.get("minimum_games_missed", 0))
        market = market_by_id.get(player_id, {})
        source_count = len(record.get("sources", [])) if record else 0
        for week in WEEKS:
            schedule = current_schedule.get((player["team"], week))
            scheduled_game = schedule is not None
            trials, successes, level = _select_counts(
                all_counts, family, player["fantasy_position"], week
            )
            low, median, high = _wilson(successes, trials)
            rule_hard = bool(minimum and week <= minimum)
            bye_hard = not scheduled_game
            hard = rule_hard or bye_hard
            if hard:
                low = median = high = 0.0
            probability_lookup[(player["team"], player_id, week)] = median
            support = "strong" if trials >= 150 else "moderate" if trials >= MIN_COHORT_N else "weak"
            availability_rows.append({
                "season": season, "week": week,
                "gameday": schedule["gameday"] if schedule else "",
                "team": player["team"],
                "opponent": schedule["opponent"] if schedule else "",
                "home_away": schedule["home_away"] if schedule else "",
                "scheduled_game": str(scheduled_game).lower(),
                "position": player["fantasy_position"], "gsis_id": player_id,
                "player_name": player["full_name"],
                "current_status": player["current_status"],
                "roster_status": player["roster_status"],
                "status_description": player.get("status_description", ""),
                "cohort_family": family, "cohort_level": level,
                "training_n": trials, "training_active": successes,
                "active_probability_low": f"{low:.6f}",
                "active_probability_median": f"{median:.6f}",
                "active_probability_high": f"{high:.6f}",
                "minimum_games_missed": minimum or "",
                "hard_constraint_applied": str(hard).lower(),
                "constraint_reason": (
                    "rule_minimum_and_bye" if rule_hard and bye_hard
                    else "rule_minimum_absence" if rule_hard
                    else "scheduled_bye" if bye_hard else ""
                ),
                "evidence_status": "reviewed_first_party" if record else "status_only",
                "evidence_source_count": source_count,
                "ffc_source_player_id": market.get("ffc_source_player_id", ""),
                "ffc_adp": market.get("ffc_adp", ""),
                "model_support": support, "model_status": MODEL_STATUS,
            })

    pool_lookup = {
        (row["team"], row["resource"]): _float(
            row["team_pool_per_game"], f"{row['team']} {row['resource']} pool"
        )
        for row in pools
    }
    if len(pool_lookup) != len(pools):
        raise AvailabilityDataError("team reconciliation contains duplicate pools")
    candidate_groups: dict[tuple[str, str], list[Mapping[str, str]]] = defaultdict(list)
    for row in candidates:
        key = row["team"], row["resource"]
        if key not in pool_lookup:
            raise AvailabilityDataError(f"candidate has no team pool: {key}")
        if row["gsis_id"] not in roster_by_id:
            raise AvailabilityDataError(f"candidate absent from current roster: {row['gsis_id']}")
        candidate_groups[key].append(row)
    if set(candidate_groups) != set(pool_lookup):
        raise AvailabilityDataError("candidate rooms and team pools do not match")

    rng = random.Random(random_seed)
    expected_rows: list[dict[str, Any]] = []
    reconciliation_rows: list[dict[str, Any]] = []
    teams = sorted({team for team, _ in candidate_groups})
    resources_by_team: dict[str, list[str]] = defaultdict(list)
    for team, resource in candidate_groups:
        resources_by_team[team].append(resource)
    for team in teams:
        player_ids = sorted({
            row["gsis_id"] for resource in resources_by_team[team]
            for row in candidate_groups[(team, resource)]
        })
        for week in WEEKS:
            schedule = current_schedule.get((team, week))
            scheduled_game = schedule is not None
            active_draws = {
                player_id: [
                    rng.random() < probability_lookup[(team, player_id, week)]
                    for _ in range(simulation_draws)
                ]
                for player_id in player_ids
            }
            for resource in sorted(resources_by_team[team]):
                room = candidate_groups[(team, resource)]
                values = {row["gsis_id"]: [0.0] * simulation_draws for row in room}
                unallocated = 0
                if scheduled_game:
                    for draw in range(simulation_draws):
                        available = [row for row in room if active_draws[row["gsis_id"]][draw]]
                        denominator = sum(
                            _float(row["latent_role_weight"], "latent role weight")
                            for row in available
                        )
                        if denominator <= 0:
                            unallocated += 1
                            continue
                        for row in available:
                            values[row["gsis_id"]][draw] = (
                                _float(row["latent_role_weight"], "latent role weight")
                                / denominator
                            )
                pool = pool_lookup[(team, resource)]
                pool_this_week = pool if scheduled_game else 0.0
                player_share_sum = 0.0
                for row in room:
                    shares = values[row["gsis_id"]]
                    mean = sum(shares) / simulation_draws
                    p10 = _percentile(shares, 0.10)
                    p50 = _percentile(shares, 0.50)
                    p90 = _percentile(shares, 0.90)
                    player_share_sum += mean
                    market = market_by_id.get(row["gsis_id"], {})
                    expected_rows.append({
                        "season": season, "week": week,
                        "gameday": schedule["gameday"] if schedule else "",
                        "team": team,
                        "opponent": schedule["opponent"] if schedule else "",
                        "home_away": schedule["home_away"] if schedule else "",
                        "scheduled_game": str(scheduled_game).lower(),
                        "position": row["position"], "resource": resource,
                        "gsis_id": row["gsis_id"], "player_name": row["player_name"],
                        "current_status": row["current_status"],
                        "active_probability_median": f"{probability_lookup[(team, row['gsis_id'], week)]:.6f}",
                        "latent_role_weight": row["latent_role_weight"],
                        "expected_share_mean": f"{mean:.9f}",
                        "share_p10": f"{p10:.9f}", "share_p50": f"{p50:.9f}",
                        "share_p90": f"{p90:.9f}",
                        "team_pool_per_game": f"{pool:.6f}",
                        "team_pool_this_week": f"{pool_this_week:.6f}",
                        "expected_opportunities_this_week": f"{pool_this_week * mean:.9f}",
                        "opportunities_p10": f"{pool_this_week * p10:.9f}",
                        "opportunities_p50": f"{pool_this_week * p50:.9f}",
                        "opportunities_p90": f"{pool_this_week * p90:.9f}",
                        "ffc_source_player_id": market.get("ffc_source_player_id", ""),
                        "ffc_adp": market.get("ffc_adp", ""),
                        "simulation_draws": simulation_draws, "model_status": MODEL_STATUS,
                    })
                unallocated_rate = unallocated / simulation_draws
                reconciled = player_share_sum + unallocated_rate
                reconciliation_target = 1.0 if scheduled_game else 0.0
                error = abs(reconciled - reconciliation_target)
                if error > 1e-9:
                    raise AvailabilityDataError(
                        f"{team} Week {week} {resource} fails reconciliation by {error}"
                    )
                reconciliation_rows.append({
                    "season": season, "week": week,
                    "gameday": schedule["gameday"] if schedule else "",
                    "team": team,
                    "opponent": schedule["opponent"] if schedule else "",
                    "home_away": schedule["home_away"] if schedule else "",
                    "scheduled_game": str(scheduled_game).lower(),
                    "position": room[0]["position"], "resource": resource,
                    "candidate_count": len(room), "simulation_draws": simulation_draws,
                    "team_pool_per_game": f"{pool:.6f}",
                    "team_pool_this_week": f"{pool_this_week:.6f}",
                    "reconciliation_target": f"{reconciliation_target:.1f}",
                    "expected_player_share_sum": f"{player_share_sum:.12f}",
                    "unallocated_draw_rate": f"{unallocated_rate:.12f}",
                    "reconciled_share_sum": f"{reconciled:.12f}",
                    "expected_player_opportunities": f"{pool_this_week * player_share_sum:.9f}",
                    "expected_unallocated_opportunities": f"{pool_this_week * unallocated_rate:.9f}",
                    "reconciliation_error": f"{error:.12f}",
                })

    input_hashes = {
        "weekly_rosters.csv": hashlib.sha256(history_raw).hexdigest(),
        "team_schedule.csv": hashlib.sha256(schedule_raw).hexdigest(),
        "current_roster.csv": hashlib.sha256(roster_raw).hexdigest(),
        "player_role_candidates.csv": hashlib.sha256(candidate_raw).hexdigest(),
        "team_reconciliation.csv": hashlib.sha256(pool_raw).hexdigest(),
        evidence_file.name: hashlib.sha256(evidence_raw).hexdigest(),
    }
    return AvailabilityResult(
        season=season, history_path=history_root, player_context_path=context_root,
        role_snapshot_path=role_root, evidence_path=evidence_file,
        input_hashes=input_hashes,
        weekly_availability=tuple(sorted(
            availability_rows,
            key=lambda row: (row["week"], row["team"], row["position"], row["player_name"]),
        )),
        weekly_expected_roles=tuple(sorted(
            expected_rows,
            key=lambda row: (row["week"], row["team"], row["resource"], -float(row["expected_share_mean"]), row["player_name"]),
        )),
        reconciliation=tuple(sorted(
            reconciliation_rows, key=lambda row: (row["week"], row["team"], row["resource"])
        )),
        backtest=tuple(sorted(backtest_rows, key=lambda row: (row["segment"], row["model"]))),
        evidence_review=tuple(review), evaluation=evaluation,
        simulation_draws=simulation_draws, random_seed=random_seed,
    )


def _csv_bytes(fields: tuple[str, ...], rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def write_availability_snapshot(result: AvailabilityResult, root: str | Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    parent = Path(root) / "availability" / str(result.season)
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"availability snapshot exists: {destination}")
    artifacts = {
        "weekly_availability.csv": _csv_bytes(AVAILABILITY_FIELDS, result.weekly_availability),
        "weekly_expected_roles.csv": _csv_bytes(EXPECTED_ROLE_FIELDS, result.weekly_expected_roles),
        "team_week_reconciliation.csv": _csv_bytes(RECONCILIATION_FIELDS, result.reconciliation),
        "availability_backtest.csv": _csv_bytes(BACKTEST_FIELDS, result.backtest),
        "evidence_review.csv": _csv_bytes(EVIDENCE_REVIEW_FIELDS, result.evidence_review),
    }
    manifest = {
        "schema_version": SCHEMA_VERSION, "model_version": MODEL_VERSION,
        "model_status": MODEL_STATUS, "season": result.season,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "methodology": {
            "availability": "Laplace-smoothed historical Week-1-status cohorts with 90% Wilson sampling intervals",
            "schedule": "historical bye weeks are excluded from active-status training; forecast-season byes force availability and opportunity to zero",
            "validation": "leave-one-season-out weekly Brier score with paired 90% normal intervals over player-season clusters",
            "hard_constraints": "only reviewed evidence linked to a rule source may force zero availability",
            "role_scenarios": "independent marginal Bernoulli draws by player/week; common draws across a team; available latent role weights renormalized within each resource",
            "path_limitation": "weeks are marginal simulations, not correlated recovery paths",
            "medical_limitation": "population roster-status behavior is not an individual injury prognosis",
        },
        "parameters": {
            "weeks": list(WEEKS), "minimum_cohort_n": MIN_COHORT_N,
            "interval": "90% Wilson", "simulation_draws": result.simulation_draws,
            "random_seed": result.random_seed,
        },
        "inputs": {
            "player_history": str(result.history_path),
            "player_context": str(result.player_context_path),
            "role_snapshot": str(result.role_snapshot_path),
            "evidence": str(result.evidence_path), "sha256": dict(result.input_hashes),
        },
        "evaluation": dict(result.evaluation),
        "quality": {
            "availability_rows": len(result.weekly_availability),
            "expected_role_rows": len(result.weekly_expected_roles),
            "reconciliation_rows": len(result.reconciliation),
            "backtest_rows": len(result.backtest),
            "evidence_review_rows": len(result.evidence_review),
            "maximum_reconciliation_error": max(
                (float(row["reconciliation_error"]) for row in result.reconciliation), default=0.0
            ),
            "maximum_unallocated_draw_rate": max(
                (float(row["unallocated_draw_rate"]) for row in result.reconciliation), default=0.0
            ),
            "bye_team_resource_rows": sum(
                row["scheduled_game"] == "false" for row in result.reconciliation
            ),
        },
        "artifacts": {
            name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "fields": list({
                "weekly_availability.csv": AVAILABILITY_FIELDS,
                "weekly_expected_roles.csv": EXPECTED_ROLE_FIELDS,
                "team_week_reconciliation.csv": RECONCILIATION_FIELDS,
                "availability_backtest.csv": BACKTEST_FIELDS,
                "evidence_review.csv": EVIDENCE_REVIEW_FIELDS,
            }[name])}
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
