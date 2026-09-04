"""Build identity-audited, active-roster-conditional player role priors.

This module does not estimate fantasy points or player efficiency.  It splits
team opportunity envelopes into player shares using current depth placement and
recent actual usage, then publishes every name-match exception and every
non-active roster case instead of treating either as resolved silently.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import shutil
import tempfile
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .resource_transform import (
    ConversionEstimate,
    ResourceTransformError,
    VerifiedTeamStyle,
    canonical_team,
    derive_conversion_factors,
    load_verified_team_style,
    resource_forecasts,
)

SCHEMA_VERSION = "1.4.0"
MODEL_VERSION = "player-role-prior-v0.4.0"
MODEL_STATUS = "resource_selected_retrospective_role_prior_not_prospectively_validated"
ROLE_POSITIONS = ("QB", "RB", "WR", "TE")
AFFILIATED_STATUSES = {"ACT", "DEV", "RES", "RSR", "PUP", "RSN", "SUS", "EXE"}
FULL_SEASON_GAMES = 17
TRANSFER_RELIABILITY_MULTIPLIER = 0.45

RESOURCE_SPECS: Mapping[str, Mapping[str, str]] = {
    "QB_DROPBACKS": {
        "position": "QB",
        "numerator": "dropbacks",
        "denominator": "team_qb_dropbacks",
    },
    "QB_RUSH_OPPORTUNITIES": {
        "position": "QB",
        "numerator": "carries",
        "denominator": "team_position_carries",
    },
    "RB_CARRIES": {
        "position": "RB",
        "numerator": "carries",
        "denominator": "team_position_carries",
    },
    "RB_TARGETS": {
        "position": "RB",
        "numerator": "targets",
        "denominator": "team_position_targets",
    },
    "WR_TARGETS": {
        "position": "WR",
        "numerator": "targets",
        "denominator": "team_position_targets",
    },
    "TE_TARGETS": {
        "position": "TE",
        "numerator": "targets",
        "denominator": "team_position_targets",
    },
}

DEPTH_WEIGHTS = {
    "QB": (1.0, 0.07, 0.015, 0.005),
    "RB": (1.0, 0.55, 0.28, 0.14, 0.07, 0.035),
    "WR": (1.0, 0.90, 0.80, 0.35, 0.22, 0.13, 0.08, 0.05),
    "TE": (1.0, 0.45, 0.18, 0.08, 0.04, 0.02),
}

BASE_INTERVAL_WIDTH = {
    "QB_DROPBACKS": 0.14,
    "QB_RUSH_OPPORTUNITIES": 0.20,
    "RB_CARRIES": 0.20,
    "RB_TARGETS": 0.18,
    "WR_TARGETS": 0.18,
    "TE_TARGETS": 0.19,
}

RESOURCE_HISTORY_WEIGHT = {
    "QB_DROPBACKS": 0.0,
    "QB_RUSH_OPPORTUNITIES": 0.0,
    "RB_CARRIES": 0.45,
    "RB_TARGETS": 0.50,
    "WR_TARGETS": 0.55,
    "TE_TARGETS": 0.55,
}

FFC_FIELDS = (
    "source",
    "source_player_id",
    "source_name",
    "source_team",
    "source_position",
    "adp",
    "canonical_gsis_id",
    "canonical_name",
    "current_team",
    "current_position",
    "current_status",
    "roster_status",
    "match_status",
    "match_method",
    "candidate_gsis_ids",
    "review_reason",
)

ROLE_FIELDS = (
    "season",
    "team",
    "position",
    "gsis_id",
    "player_name",
    "current_status",
    "roster_status",
    "depth_rank",
    "depth_slot",
    "resource",
    "team_pool_per_game",
    "team_pool_full_season",
    "role_share_low",
    "role_share_median",
    "role_share_high",
    "opportunities_per_game_low",
    "opportunities_per_game_median",
    "opportunities_per_game_high",
    "full_season_opportunities_median",
    "historical_share",
    "historical_offense_snap_share",
    "historical_weighted_games",
    "historical_season_count",
    "historical_latest_team",
    "history_current_team_in_latest_season",
    "depth_prior_share",
    "history_blend_weight",
    "role_evidence_score_v0",
    "role_evidence_label",
    "ffc_source_player_id",
    "ffc_adp",
    "model_status",
)

ROLE_CANDIDATE_FIELDS = (
    "season",
    "team",
    "position",
    "resource",
    "gsis_id",
    "player_name",
    "current_status",
    "roster_status",
    "depth_rank",
    "depth_slot",
    "current_active",
    "active_baseline_share",
    "all_affiliated_share",
    "latent_role_weight",
    "historical_share",
    "historical_weighted_games",
    "historical_latest_team",
    "depth_prior_share",
    "history_blend_weight",
    "role_evidence_score_v0",
    "role_evidence_label",
    "ffc_source_player_id",
    "ffc_adp",
    "candidate_method",
)

RECONCILIATION_FIELDS = (
    "season",
    "team",
    "position",
    "resource",
    "active_player_count",
    "team_pool_per_game",
    "team_pool_full_season",
    "median_share_sum",
    "allocated_per_game_sum",
    "reconciliation_error",
    "scope",
    "model_status",
)

IDENTITY_REVIEW_FIELDS = (
    "review_category",
    "source",
    "season",
    "team",
    "source_player_id",
    "source_secondary_id",
    "player_name",
    "position",
    "issue",
    "candidate_gsis_ids",
    "details",
)

AVAILABILITY_FIELDS = (
    "season",
    "team",
    "roster_team",
    "catalog_latest_team",
    "position",
    "gsis_id",
    "player_name",
    "current_status",
    "roster_status",
    "catalog_status",
    "depth_rank",
    "historical_games",
    "ffc_source_player_id",
    "ffc_adp",
    "availability_status",
    "reason",
)


class PlayerRoleDataError(ValueError):
    """Raised when source snapshots cannot support an audited role build."""


@dataclass(frozen=True)
class PlayerRoleResult:
    season: int
    player_context_path: Path
    position_environment_path: Path
    caller_fingerprint_path: Path
    observed_style_path: Path
    observed_style_manifest_path: Path
    ffc_path: Path | None
    input_hashes: Mapping[str, str]
    roles: tuple[Mapping[str, Any], ...]
    role_candidates: tuple[Mapping[str, Any], ...]
    reconciliation: tuple[Mapping[str, Any], ...]
    ffc_crosswalk: tuple[Mapping[str, Any], ...]
    identity_review: tuple[Mapping[str, Any], ...]
    availability_review: tuple[Mapping[str, Any], ...]
    conversion_factors: Mapping[str, float]
    conversion_training_seasons: tuple[int, ...]
    conversion_team_season_count: int


def _resolve(path: str | Path, filename: str) -> Path:
    resolved = Path(path)
    if resolved.is_dir():
        resolved = resolved / filename
    if not resolved.is_file():
        raise PlayerRoleDataError(f"input does not exist: {resolved}")
    return resolved


def _read_rows(
    path: Path,
    required: set[str],
    *,
    allow_empty: bool = False,
) -> tuple[bytes, list[dict[str, str]]]:
    raw = path.read_bytes()
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        fields = set(reader.fieldnames or ())
        rows = list(reader)
    except UnicodeDecodeError as error:
        raise PlayerRoleDataError(f"CSV is not UTF-8: {path}") from error
    if not required.issubset(fields):
        raise PlayerRoleDataError(f"CSV lacks required fields {sorted(required - fields)}: {path}")
    if not rows and not allow_empty:
        raise PlayerRoleDataError(f"CSV has no rows: {path}")
    return raw, rows


def _verify_caller_style_binding(
    caller_path: Path,
    caller_raw: bytes,
    observed_style: VerifiedTeamStyle,
) -> tuple[Path, bytes]:
    """Require the caller snapshot to bind the same observed-style artifact."""

    manifest_path = caller_path.parent / "manifest.json"
    if not manifest_path.is_file():
        raise PlayerRoleDataError(
            f"caller-fingerprint manifest does not exist: {manifest_path}"
        )
    manifest_raw = manifest_path.read_bytes()
    try:
        manifest = json.loads(manifest_raw)
    except json.JSONDecodeError as error:
        raise PlayerRoleDataError(
            f"caller-fingerprint manifest is not valid JSON: {manifest_path}"
        ) from error
    artifacts = manifest.get("artifacts") if isinstance(manifest, Mapping) else None
    metadata = artifacts.get("metric_forecasts.csv") if isinstance(artifacts, Mapping) else None
    expected_caller_hash = metadata.get("sha256") if isinstance(metadata, Mapping) else None
    actual_caller_hash = hashlib.sha256(caller_raw).hexdigest()
    if expected_caller_hash != actual_caller_hash:
        raise PlayerRoleDataError(
            f"caller manifest does not bind metric_forecasts.csv: {manifest_path}"
        )
    inputs = manifest.get("inputs") if isinstance(manifest, Mapping) else None
    if not isinstance(inputs, list):
        raise PlayerRoleDataError(
            f"caller manifest has no auditable input list: {manifest_path}"
        )
    actual_style_hash = hashlib.sha256(
        observed_style.raw_by_path[str(observed_style.path)]
    ).hexdigest()
    matches = [
        row
        for row in inputs
        if isinstance(row, Mapping)
        and isinstance(row.get("path"), str)
        and Path(row["path"]).resolve() == observed_style.path.resolve()
    ]
    if len(matches) != 1 or matches[0].get("sha256") != actual_style_hash:
        raise PlayerRoleDataError(
            "caller snapshot is not bound to the supplied team-style CSV and hash"
        )
    return manifest_path, manifest_raw


def _float(value: str | int | float | None, context: str = "value") -> float:
    if value is None or str(value).strip() == "":
        return 0.0
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise PlayerRoleDataError(f"{context} must be numeric, got {value!r}") from error
    if not math.isfinite(parsed):
        raise PlayerRoleDataError(f"{context} must be finite")
    return parsed


def _optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    number = _float(value)
    return int(number) if number.is_integer() else None


def _normalize_name(value: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    tokens = "".join(character.lower() if character.isalnum() else " " for character in ascii_name).split()
    while tokens and tokens[-1] in {"jr", "sr", "ii", "iii", "iv", "v"}:
        tokens.pop()
    return "".join(tokens)


def _name_aliases(row: Mapping[str, str]) -> set[str]:
    values = {row.get("full_name", ""), row.get("display_name", "")}
    football = row.get("football_name", "").strip()
    last = row.get("last_name", "").strip()
    if football and last:
        values.add(f"{football} {last}")
    return {normalized for value in values if value and (normalized := _normalize_name(value))}


def _build_ffc_crosswalk(
    ffc_rows: Iterable[Mapping[str, str]],
    roster: Iterable[Mapping[str, str]],
    *,
    season: int,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    roster_rows = [row for row in roster if row.get("gsis_id")]
    triple: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    name_position: dict[tuple[str, str], set[str]] = defaultdict(set)
    roster_by_id = {row["gsis_id"]: row for row in roster_rows}
    for row in roster_rows:
        position = row.get("fantasy_position", "")
        if position not in {*ROLE_POSITIONS, "K"}:
            continue
        for name in _name_aliases(row):
            triple[(name, row["team"], position)].add(row["gsis_id"])
            name_position[(name, position)].add(row["gsis_id"])

    crosswalk: list[dict[str, Any]] = []
    for source in ffc_rows:
        position = source.get("position", "").strip().upper()
        source_name = source.get("name", "").strip()
        source_team = source.get("team", "").strip().upper()
        normalized = _normalize_name(source_name)
        candidates = set(triple.get((normalized, source_team, position), set()))
        method = "canonical_name_team_position"
        status = ""
        reason = ""
        canonical = ""
        if position not in ROLE_POSITIONS:
            status = "out_of_scope"
            method = "not_attempted"
            reason = "only QB/RB/WR/TE are in the current player-role scope"
        elif len(candidates) == 1:
            proposed = next(iter(candidates))
            current_status = roster_by_id[proposed].get("current_status", "")
            if current_status in AFFILIATED_STATUSES:
                status = "resolved"
                canonical = proposed
            else:
                status = "review_required"
                reason = f"exact identity candidate has no current club affiliation ({current_status or 'blank'})"
        elif len(candidates) > 1:
            status = "review_required"
            reason = "multiple exact canonical-name/team/position candidates"
        else:
            candidates = set(name_position.get((normalized, position), set()))
            if len(candidates) == 1:
                status = "review_required"
                method = "canonical_name_position_only"
                reason = "unique name/position candidate is on a different current team"
            elif len(candidates) > 1:
                status = "review_required"
                method = "canonical_name_position_only"
                reason = "multiple canonical-name/position candidates"
            else:
                status = "unmatched"
                method = "no_candidate"
                reason = "no current-roster canonical-name/position candidate"
        canonical_row = roster_by_id.get(canonical, {})
        crosswalk.append(
            {
                "source": source.get("source", "fantasy_football_calculator"),
                "source_player_id": source.get("source_player_id", ""),
                "source_name": source_name,
                "source_team": source_team,
                "source_position": position,
                "adp": source.get("adp", ""),
                "canonical_gsis_id": canonical,
                "canonical_name": canonical_row.get("full_name", ""),
                "current_team": canonical_row.get("team", ""),
                "current_position": canonical_row.get("fantasy_position", ""),
                "current_status": canonical_row.get("current_status", ""),
                "roster_status": canonical_row.get("roster_status", ""),
                "match_status": status,
                "match_method": method,
                "candidate_gsis_ids": "|".join(sorted(candidates)),
                "review_reason": reason,
            }
        )

    collisions: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(crosswalk):
        if row["match_status"] == "resolved":
            collisions[row["canonical_gsis_id"]].append(index)
    for gsis_id, indexes in collisions.items():
        if len(indexes) <= 1:
            continue
        for index in indexes:
            crosswalk[index]["match_status"] = "review_required"
            crosswalk[index]["canonical_gsis_id"] = ""
            crosswalk[index]["review_reason"] = (
                f"multiple FFC rows map to the same GSIS candidate {gsis_id}"
            )

    resolved: dict[str, dict[str, Any]] = {
        row["canonical_gsis_id"]: row
        for row in crosswalk
        if row["match_status"] == "resolved"
    }
    review = [
        {
            "review_category": "ffc_identity",
            "source": row["source"],
            "season": season,
            "team": row["source_team"],
            "source_player_id": row["source_player_id"],
            "source_secondary_id": "",
            "player_name": row["source_name"],
            "position": row["source_position"],
            "issue": row["match_status"],
            "candidate_gsis_ids": row["candidate_gsis_ids"],
            "details": row["review_reason"],
        }
        for row in crosswalk
        if row["source_position"] in ROLE_POSITIONS and row["match_status"] != "resolved"
    ]
    return crosswalk, resolved, review


def _depth_weight(position: str, rank: int | None) -> float:
    if rank is None or rank < 1:
        return 0.02
    values = DEPTH_WEIGHTS[position]
    if rank <= len(values):
        return values[rank - 1]
    return values[-1] * (0.55 ** (rank - len(values)))


def _historical_estimate(
    rows: Iterable[Mapping[str, str]],
    *,
    resource: str,
    current_team: str,
    latest_history_season: int,
) -> dict[str, Any]:
    spec = RESOURCE_SPECS[resource]
    relevant = [row for row in rows if row.get("position") == spec["position"]]
    weighted_numerator = 0.0
    weighted_denominator = 0.0
    weighted_games = 0.0
    weighted_snaps = 0.0
    weighted_team_snaps = 0.0
    seasons: set[int] = set()
    latest_teams: set[str] = set()
    for row in relevant:
        season = int(row["season"])
        recency = 0.65 ** (latest_history_season - season)
        transfer = 1.0 if row["team"] == current_team else 0.70
        weight = recency * transfer
        weighted_numerator += weight * _float(row.get(spec["numerator"]), spec["numerator"])
        weighted_denominator += weight * _float(row.get(spec["denominator"]), spec["denominator"])
        weighted_games += weight * _float(row.get("games"), "games")
        weighted_snaps += weight * _float(row.get("offense_snaps"), "offense_snaps")
        weighted_team_snaps += weight * _float(
            row.get("team_offense_snaps"), "team_offense_snaps"
        )
        seasons.add(season)
    if relevant:
        most_recent = max(int(row["season"]) for row in relevant)
        latest_teams = {row["team"] for row in relevant if int(row["season"]) == most_recent}
    return {
        "share": weighted_numerator / weighted_denominator if weighted_denominator > 0 else 0.0,
        "snap_share": weighted_snaps / weighted_team_snaps if weighted_team_snaps > 0 else None,
        "weighted_games": weighted_games,
        "season_count": len(seasons),
        "latest_team": "|".join(sorted(latest_teams)),
        "same_team_latest": current_team in latest_teams,
        "has_history": weighted_denominator > 0,
    }


def _conversion_factors(
    history: Iterable[Mapping[str, str]],
    observed_styles: Iterable[Mapping[str, str]],
) -> ConversionEstimate:
    grouped: dict[tuple[int, str], dict[str, float]] = defaultdict(dict)
    for row in history:
        key = (int(row["season"]), canonical_team(row["team"]))
        position = row["position"]
        grouped[key]["qb_dropbacks"] = max(
            grouped[key].get("qb_dropbacks", 0.0),
            _float(row.get("team_qb_dropbacks")),
        )
        grouped[key][f"targets_{position}"] = max(
            grouped[key].get(f"targets_{position}", 0.0),
            _float(row.get("team_position_targets")),
        )
        grouped[key][f"carries_{position}"] = max(
            grouped[key].get(f"carries_{position}", 0.0),
            _float(row.get("team_position_carries")),
        )
    usage = {
        identity: {
            "qb_dropbacks": values.get("qb_dropbacks", 0.0),
            "targets": sum(
                values.get(f"targets_{position}", 0.0)
                for position in ROLE_POSITIONS
            ),
            "rb_carries": values.get("carries_RB", 0.0),
        }
        for identity, values in grouped.items()
    }
    seasons = tuple(sorted({season for season, _ in usage}))
    try:
        return derive_conversion_factors(
            usage,
            observed_styles,
            training_seasons=seasons,
            latest_season=max(seasons),
        )
    except ResourceTransformError as error:
        raise PlayerRoleDataError(str(error)) from error


def _team_resource_pools(
    environment: Mapping[tuple[str, str], Mapping[str, str]],
    caller: Mapping[str, Mapping[str, float]],
    conversions: Mapping[str, float],
) -> dict[tuple[str, str], float]:
    pools: dict[tuple[str, str], float] = {}
    teams = sorted({team for team, _ in environment})
    for team in teams:
        missing_positions = set(ROLE_POSITIONS) - {
            position for row_team, position in environment if row_team == team
        }
        if missing_positions:
            raise PlayerRoleDataError(
                f"{team} position environment is missing {sorted(missing_positions)}"
            )
        baseline = environment[(team, "QB")]
        plays = _float(baseline.get("forecast_plays_per_game"), f"{team} plays")
        pass_plays = _float(
            baseline.get("forecast_pass_plays_per_game"), f"{team} pass plays"
        )
        rush_plays = _float(
            baseline.get("forecast_rush_plays_per_game"), f"{team} rush plays"
        )
        if plays <= 0 or abs(plays - pass_plays - rush_plays) > 0.01:
            raise PlayerRoleDataError(
                f"{team} PBP pass/rush pools do not reconcile to plays"
            )
        for position in ROLE_POSITIONS:
            row = environment[(team, position)]
            for field, reference in (
                ("forecast_plays_per_game", plays),
                ("forecast_pass_plays_per_game", pass_plays),
                ("forecast_rush_plays_per_game", rush_plays),
            ):
                if abs(_float(row.get(field), f"{team} {position} {field}") - reference) > 1e-6:
                    raise PlayerRoleDataError(
                        f"{team} {field} differs across position rows"
                    )
        metrics = {
            "plays_per_game": plays,
            "pass_rate": pass_plays / plays,
            "qb_scramble_rate": caller[team]["qb_scramble_rate"],
            "designed_qb_run_share": caller[team]["designed_qb_run_share"],
            "rb_target_share": _float(
                environment[(team, "RB")].get("position_target_share"),
                f"{team} RB target share",
            ),
            "wr_target_share": _float(
                environment[(team, "WR")].get("position_target_share"),
                f"{team} WR target share",
            ),
            "te_target_share": _float(
                environment[(team, "TE")].get("position_target_share"),
                f"{team} TE target share",
            ),
        }
        try:
            forecasts = resource_forecasts(metrics, conversions)
        except ResourceTransformError as error:
            raise PlayerRoleDataError(f"{team}: {error}") from error
        pools.update({(team, resource): value for resource, value in forecasts.items()})
    return pools


def _label_evidence(score: float) -> str:
    if score >= 80:
        return "strong_role_evidence"
    if score >= 65:
        return "moderate_role_evidence"
    if score >= 50:
        return "limited_role_evidence"
    return "weak_role_evidence"


def build_player_roles(
    player_context: str | Path,
    position_environments: str | Path,
    caller_fingerprints: str | Path,
    *,
    observed_styles: str | Path,
    ffc_adp: str | Path | None = None,
) -> PlayerRoleResult:
    """Build role-share ranges and exact median team-pool reconciliations."""

    context_root = Path(player_context)
    roster_path = _resolve(context_root, "current_roster.csv")
    depth_path = _resolve(context_root, "current_depth_chart.csv")
    history_path = _resolve(context_root, "historical_usage.csv")
    source_review_path = _resolve(context_root, "source_identity_review.csv")
    environment_path = _resolve(position_environments, "position_environments.csv")
    caller_path = _resolve(caller_fingerprints, "metric_forecasts.csv")
    ffc_path = _resolve(ffc_adp, "adp.csv") if ffc_adp is not None else None
    try:
        observed_style = load_verified_team_style(observed_styles)
    except ResourceTransformError as error:
        raise PlayerRoleDataError(str(error)) from error

    roster_raw, roster = _read_rows(
        roster_path,
        {
            "season", "team", "roster_team", "fantasy_position", "current_status",
            "roster_status", "full_name", "gsis_id",
        },
    )
    depth_raw, depth = _read_rows(
        depth_path,
        {"team", "canonical_gsis_id", "identity_status", "fantasy_position", "pos_rank", "pos_slot"},
    )
    history_raw, history = _read_rows(
        history_path,
        {
            "season",
            "team",
            "gsis_id",
            "position",
            "games",
            "dropbacks",
            "carries",
            "targets",
            "team_qb_dropbacks",
            "team_position_carries",
            "team_position_targets",
        },
    )
    source_review_raw, source_reviews = _read_rows(
        source_review_path,
        {"source", "season", "team", "source_player_id", "player_name", "position", "issue"},
        allow_empty=True,
    )
    environment_raw, environment_rows = _read_rows(
        environment_path,
        {
            "season",
            "team",
            "position",
            "forecast_plays_per_game",
            "forecast_pass_plays_per_game",
            "forecast_rush_plays_per_game",
            "position_target_share",
        },
    )
    caller_raw, caller_rows = _read_rows(
        caller_path, {"season", "team", "metric", "forecast_value_v0"}
    )
    caller_manifest_path, caller_manifest_raw = _verify_caller_style_binding(
        caller_path, caller_raw, observed_style
    )
    ffc_raw = b""
    ffc_rows: list[dict[str, str]] = []
    if ffc_path is not None:
        ffc_raw, ffc_rows = _read_rows(
            ffc_path,
            {"source", "source_player_id", "name", "position", "team", "adp", "season"},
        )

    seasons = {int(row["season"]) for row in roster}
    if len(seasons) != 1:
        raise PlayerRoleDataError("current roster must contain exactly one season")
    season = next(iter(seasons))
    if {int(row["season"]) for row in environment_rows} != {season}:
        raise PlayerRoleDataError("position environments do not match current roster season")
    if any(int(row["season"]) != season for row in caller_rows):
        raise PlayerRoleDataError("caller fingerprints do not match current roster season")
    if ffc_rows and any(int(row["season"]) != season for row in ffc_rows):
        raise PlayerRoleDataError("FFC ADP does not match current roster season")

    ffc_crosswalk, resolved_ffc, ffc_review = _build_ffc_crosswalk(
        ffc_rows, roster, season=season
    )
    identity_review = [
        {
            "review_category": "source_identity",
            "source": row.get("source", ""),
            "season": row.get("season", ""),
            "team": row.get("team", ""),
            "source_player_id": row.get("source_player_id", ""),
            "source_secondary_id": row.get("source_secondary_id", ""),
            "player_name": row.get("player_name", ""),
            "position": row.get("position", ""),
            "issue": row.get("issue", ""),
            "candidate_gsis_ids": row.get("candidate_gsis_ids", ""),
            "details": row.get("details", ""),
        }
        for row in source_reviews
    ] + ffc_review

    environment = {(row["team"], row["position"]): row for row in environment_rows}
    if len(environment) != len(environment_rows):
        raise PlayerRoleDataError("position environments contain duplicate team-position rows")
    caller: dict[str, dict[str, float]] = defaultdict(dict)
    for row in caller_rows:
        if row["metric"] in {"qb_scramble_rate", "designed_qb_run_share"}:
            value = _float(row["forecast_value_v0"], f"{row['team']} {row['metric']}")
            if not 0 <= value <= 1:
                raise PlayerRoleDataError(f"{row['team']} {row['metric']} must be in [0,1]")
            caller[row["team"]][row["metric"]] = value
    for team, _ in environment:
        missing = {"qb_scramble_rate", "designed_qb_run_share"} - set(caller[team])
        if missing:
            raise PlayerRoleDataError(f"{team} caller metrics missing {sorted(missing)}")

    active = [
        row
        for row in roster
        if row["fantasy_position"] in ROLE_POSITIONS
        and row["current_status"] == "ACT"
        and row["gsis_id"]
    ]
    roster_keys = [(row["team"], row["gsis_id"]) for row in active]
    if len(roster_keys) != len(set(roster_keys)):
        raise PlayerRoleDataError("active fantasy roster has duplicate team/GSIS rows")
    rooms: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in active:
        rooms[(row["team"], row["fantasy_position"])].append(row)

    depth_by_player: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in depth:
        position = row["fantasy_position"]
        player_id = row["canonical_gsis_id"]
        if (
            position not in ROLE_POSITIONS
            or not player_id
            or row["identity_status"] != "resolved"
        ):
            continue
        key = (row["team"], position, player_id)
        old = depth_by_player.get(key)
        new_rank = _optional_int(row.get("pos_rank"))
        old_rank = _optional_int(old.get("pos_rank")) if old else None
        if old is None or (new_rank is not None and (old_rank is None or new_rank < old_rank)):
            depth_by_player[key] = row

    history_by_player: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in history:
        history_by_player[row["gsis_id"]].append(row)
    latest_history_season = max(int(row["season"]) for row in history)
    conversion_estimate = _conversion_factors(history, observed_style.rows)
    conversions = conversion_estimate.factors
    resource_pools = _team_resource_pools(environment, caller, conversions)

    roles: list[dict[str, Any]] = []
    reconciliation: list[dict[str, Any]] = []
    for resource, spec in RESOURCE_SPECS.items():
        position = spec["position"]
        for team in sorted({team for team, env_position in environment if env_position == position}):
            candidates = rooms.get((team, position), [])
            if not candidates:
                raise PlayerRoleDataError(
                    f"{team} {position} has no ACT player for {resource}; availability review is required"
                )
            pool = resource_pools[(team, resource)]
            if pool <= 0:
                raise PlayerRoleDataError(f"{team} {resource} has non-positive opportunity pool")

            detail: list[dict[str, Any]] = []
            depth_values: list[float] = []
            for player in candidates:
                player_id = player["gsis_id"]
                depth_row = depth_by_player.get((team, position, player_id), {})
                depth_rank = _optional_int(depth_row.get("pos_rank"))
                depth_weight = _depth_weight(position, depth_rank)
                if position == "RB" and depth_row.get("pos_abb") == "FB":
                    depth_weight *= 0.08 if resource == "RB_CARRIES" else 0.15
                depth_values.append(depth_weight)
                estimate = _historical_estimate(
                    history_by_player.get(player_id, []),
                    resource=resource,
                    current_team=team,
                    latest_history_season=latest_history_season,
                )
                detail.append(
                    {
                        "player": player,
                        "depth": depth_row,
                        "depth_rank": depth_rank,
                        "history": estimate,
                    }
                )
            depth_total = sum(depth_values)
            for item, weight in zip(detail, depth_values, strict=True):
                item["depth_prior"] = weight / depth_total

            history_total = sum(item["history"]["share"] for item in detail)
            raw_scores: list[float] = []
            for item in detail:
                estimate = item["history"]
                history_normalized = (
                    estimate["share"] / history_total if history_total > 0 else item["depth_prior"]
                )
                reliability = min(
                    0.80,
                    estimate["weighted_games"] / (estimate["weighted_games"] + (6.0 if position == "QB" else 8.0)),
                ) if estimate["has_history"] else 0.0
                if reliability and not estimate["same_team_latest"]:
                    reliability *= TRANSFER_RELIABILITY_MULTIPLIER
                item["history_normalized"] = history_normalized
                item["reliability"] = reliability
                history_signal = (
                    reliability * history_normalized
                    + (1.0 - reliability) * item["depth_prior"]
                )
                resource_history_weight = RESOURCE_HISTORY_WEIGHT[resource]
                raw_scores.append(
                    resource_history_weight * history_signal
                    + (1.0 - resource_history_weight) * item["depth_prior"]
                )
            raw_total = sum(raw_scores)
            if raw_total <= 0:
                raise PlayerRoleDataError(f"{team} {resource} produced no positive role scores")

            allocated_sum = 0.0
            share_sum = 0.0
            for item, raw_score in zip(detail, raw_scores, strict=True):
                player = item["player"]
                estimate = item["history"]
                share = raw_score / raw_total
                same_team = bool(estimate["same_team_latest"])
                depth_present = item["depth_rank"] is not None
                evidence = min(
                    95.0,
                    25.0
                    + 40.0 * item["reliability"]
                    + 20.0 * float(depth_present)
                    + 10.0 * float(same_team)
                    + 5.0,
                )
                width = BASE_INTERVAL_WIDTH[resource] * (1.25 - evidence / 100.0)
                low = max(0.0, share - width)
                high = min(1.0, share + width)
                ffc = resolved_ffc.get(player["gsis_id"], {})
                opportunities_median = pool * share
                share_sum += share
                allocated_sum += opportunities_median
                roles.append(
                    {
                        "season": season,
                        "team": team,
                        "position": position,
                        "gsis_id": player["gsis_id"],
                        "player_name": player["full_name"],
                        "current_status": player["current_status"],
                        "roster_status": player["roster_status"],
                        "depth_rank": item["depth_rank"] or "",
                        "depth_slot": item["depth"].get("pos_slot", ""),
                        "resource": resource,
                        "team_pool_per_game": f"{pool:.6f}",
                        "team_pool_full_season": f"{pool * FULL_SEASON_GAMES:.3f}",
                        "role_share_low": f"{low:.6f}",
                        "role_share_median": f"{share:.6f}",
                        "role_share_high": f"{high:.6f}",
                        "opportunities_per_game_low": f"{pool * low:.6f}",
                        "opportunities_per_game_median": f"{opportunities_median:.6f}",
                        "opportunities_per_game_high": f"{pool * high:.6f}",
                        "full_season_opportunities_median": f"{opportunities_median * FULL_SEASON_GAMES:.3f}",
                        "historical_share": f"{estimate['share']:.6f}" if estimate["has_history"] else "",
                        "historical_offense_snap_share": (
                            f"{estimate['snap_share']:.6f}"
                            if estimate["snap_share"] is not None
                            else ""
                        ),
                        "historical_weighted_games": f"{estimate['weighted_games']:.3f}",
                        "historical_season_count": estimate["season_count"],
                        "historical_latest_team": estimate["latest_team"],
                        "history_current_team_in_latest_season": str(same_team).lower(),
                        "depth_prior_share": f"{item['depth_prior']:.6f}",
                        "history_blend_weight": f"{item['reliability'] * RESOURCE_HISTORY_WEIGHT[resource]:.6f}",
                        "role_evidence_score_v0": f"{evidence:.1f}",
                        "role_evidence_label": _label_evidence(evidence),
                        "ffc_source_player_id": ffc.get("source_player_id", ""),
                        "ffc_adp": ffc.get("adp", ""),
                        "model_status": MODEL_STATUS,
                    }
                )
            error = max(abs(share_sum - 1.0), abs(allocated_sum - pool))
            if error > 1e-9:
                raise PlayerRoleDataError(
                    f"{team} {resource} failed reconciliation by {error:.12f}"
                )
            reconciliation.append(
                {
                    "season": season,
                    "team": team,
                    "position": position,
                    "resource": resource,
                    "active_player_count": len(candidates),
                    "team_pool_per_game": f"{pool:.6f}",
                    "team_pool_full_season": f"{pool * FULL_SEASON_GAMES:.3f}",
                    "median_share_sum": f"{share_sum:.12f}",
                    "allocated_per_game_sum": f"{allocated_sum:.6f}",
                    "reconciliation_error": f"{error:.12f}",
                    "scope": "conditional on reconciled nflverse current_status=ACT; marginal low/high bounds are not additive",
                    "model_status": MODEL_STATUS,
                }
            )

    history_games = {
        player_id: sum(_float(row.get("games")) for row in rows)
        for player_id, rows in history_by_player.items()
    }

    # Preserve the active-only allocation exactly while adding latent weights for
    # every currently affiliated player.  When no reserve/practice-squad player is
    # available, renormalizing these weights reproduces player_role_priors.csv.
    # When one returns, its all-affiliated score enters without silently deleting
    # or inventing an active player's role.
    active_role_lookup = {
        (str(row["team"]), str(row["resource"]), str(row["gsis_id"])): row
        for row in roles
    }
    affiliated_rooms: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for player in roster:
        if (
            player["fantasy_position"] in ROLE_POSITIONS
            and player["current_status"] in AFFILIATED_STATUSES
            and player["gsis_id"]
        ):
            affiliated_rooms[(player["team"], player["fantasy_position"])].append(player)
    role_candidates: list[dict[str, Any]] = []
    for resource, spec in RESOURCE_SPECS.items():
        position = spec["position"]
        for team in sorted({
            team for team, env_position in environment if env_position == position
        }):
            candidates = affiliated_rooms.get((team, position), [])
            if not candidates:
                raise PlayerRoleDataError(f"{team} {position} has no affiliated candidates")
            details: list[dict[str, Any]] = []
            depth_values: list[float] = []
            for player in candidates:
                player_id = player["gsis_id"]
                depth_row = depth_by_player.get((team, position, player_id), {})
                depth_rank = _optional_int(depth_row.get("pos_rank"))
                depth_weight = _depth_weight(position, depth_rank)
                if position == "RB" and depth_row.get("pos_abb") == "FB":
                    depth_weight *= 0.08 if resource == "RB_CARRIES" else 0.15
                depth_values.append(depth_weight)
                details.append({
                    "player": player,
                    "depth": depth_row,
                    "depth_rank": depth_rank,
                    "history": _historical_estimate(
                        history_by_player.get(player_id, []),
                        resource=resource,
                        current_team=team,
                        latest_history_season=latest_history_season,
                    ),
                })
            depth_total = sum(depth_values)
            for item, value in zip(details, depth_values, strict=True):
                item["depth_prior"] = value / depth_total
            history_total = sum(item["history"]["share"] for item in details)
            scores: list[float] = []
            for item in details:
                estimate = item["history"]
                history_normalized = (
                    estimate["share"] / history_total
                    if history_total > 0
                    else item["depth_prior"]
                )
                reliability = (
                    min(
                        0.80,
                        estimate["weighted_games"]
                        / (estimate["weighted_games"] + (6.0 if position == "QB" else 8.0)),
                    )
                    if estimate["has_history"]
                    else 0.0
                )
                if reliability and not estimate["same_team_latest"]:
                    reliability *= TRANSFER_RELIABILITY_MULTIPLIER
                item["reliability"] = reliability
                history_signal = (
                    reliability * history_normalized
                    + (1.0 - reliability) * item["depth_prior"]
                )
                scores.append(
                    RESOURCE_HISTORY_WEIGHT[resource] * history_signal
                    + (1.0 - RESOURCE_HISTORY_WEIGHT[resource]) * item["depth_prior"]
                )
            total = sum(scores)
            if total <= 0:
                raise PlayerRoleDataError(f"{team} {resource} has no candidate role weight")
            full_shares = [score / total for score in scores]
            inactive_mass = sum(
                share
                for item, share in zip(details, full_shares, strict=True)
                if item["player"]["current_status"] != "ACT"
            )
            active_mass = 1.0 - inactive_mass
            latent_sum = 0.0
            for item, full_share in zip(details, full_shares, strict=True):
                player = item["player"]
                active_row = active_role_lookup.get((team, resource, player["gsis_id"]))
                active_share = float(active_row["role_share_median"]) if active_row else None
                latent = full_share if active_share is None else active_mass * active_share
                latent_sum += latent
                estimate = item["history"]
                evidence = min(
                    95.0,
                    25.0
                    + 40.0 * item["reliability"]
                    + 20.0 * float(item["depth_rank"] is not None)
                    + 10.0 * float(estimate["same_team_latest"])
                    + 5.0,
                )
                ffc = resolved_ffc.get(player["gsis_id"], {})
                role_candidates.append({
                    "season": season,
                    "team": team,
                    "position": position,
                    "resource": resource,
                    "gsis_id": player["gsis_id"],
                    "player_name": player["full_name"],
                    "current_status": player["current_status"],
                    "roster_status": player["roster_status"],
                    "depth_rank": item["depth_rank"] or "",
                    "depth_slot": item["depth"].get("pos_slot", ""),
                    "current_active": str(player["current_status"] == "ACT").lower(),
                    "active_baseline_share": (
                        f"{active_share:.6f}" if active_share is not None else ""
                    ),
                    "all_affiliated_share": f"{full_share:.6f}",
                    "latent_role_weight": f"{latent:.9f}",
                    "historical_share": (
                        f"{estimate['share']:.6f}" if estimate["has_history"] else ""
                    ),
                    "historical_weighted_games": f"{estimate['weighted_games']:.3f}",
                    "historical_latest_team": estimate["latest_team"],
                    "depth_prior_share": f"{item['depth_prior']:.6f}",
                    "history_blend_weight": (
                        f"{item['reliability'] * RESOURCE_HISTORY_WEIGHT[resource]:.6f}"
                    ),
                    "role_evidence_score_v0": f"{evidence:.1f}",
                    "role_evidence_label": _label_evidence(evidence),
                    "ffc_source_player_id": ffc.get("source_player_id", ""),
                    "ffc_adp": ffc.get("adp", ""),
                    "candidate_method": "active_share_preserving_all_affiliated_v0",
                })
            if abs(latent_sum - 1.0) > 2e-6:
                raise PlayerRoleDataError(
                    f"{team} {resource} latent candidate weights sum to {latent_sum:.12f}"
                )

    availability: list[dict[str, Any]] = []
    ffc_candidates = {
        row["candidate_gsis_ids"]: row
        for row in ffc_crosswalk
        if row["source_position"] in ROLE_POSITIONS
        and row["candidate_gsis_ids"]
        and "|" not in row["candidate_gsis_ids"]
    }
    for player in roster:
        current_status = player["current_status"]
        catalog_status = player.get("catalog_status", "")
        catalog_team = player.get("catalog_latest_team", "")
        roster_status = player["roster_status"]
        effective_team = player["team"]
        if (
            player["fantasy_position"] not in ROLE_POSITIONS
            or current_status == "ACT"
            or current_status not in AFFILIATED_STATUSES
            or not player["gsis_id"]
        ):
            continue
        key = (effective_team, player["fantasy_position"], player["gsis_id"])
        depth_row = depth_by_player.get(key, {})
        ffc = resolved_ffc.get(player["gsis_id"], {}) or ffc_candidates.get(
            player["gsis_id"], {}
        )
        games = history_games.get(player["gsis_id"], 0.0)
        if not depth_row and not ffc and games <= 0:
            continue
        availability.append(
            {
                "season": season,
                "team": effective_team,
                "roster_team": player["roster_team"],
                "catalog_latest_team": catalog_team,
                "position": player["fantasy_position"],
                "gsis_id": player["gsis_id"],
                "player_name": player["full_name"],
                "current_status": current_status,
                "roster_status": roster_status,
                "catalog_status": catalog_status,
                "depth_rank": depth_row.get("pos_rank", ""),
                "historical_games": f"{games:.0f}",
                "ffc_source_player_id": ffc.get("source_player_id", ""),
                "ffc_adp": ffc.get("adp", ""),
                "availability_status": "review_required_not_modeled",
                "reason": (
                    "current affiliation was reconciled from a newer player-catalog team/status; dated transaction evidence required"
                    if player["roster_team"] != effective_team
                    or roster_status != current_status
                    else "non-ACT current status requires dated availability and return-timeline evidence"
                ),
            }
        )

    input_hashes = {
        "current_roster.csv": hashlib.sha256(roster_raw).hexdigest(),
        "current_depth_chart.csv": hashlib.sha256(depth_raw).hexdigest(),
        "historical_usage.csv": hashlib.sha256(history_raw).hexdigest(),
        "source_identity_review.csv": hashlib.sha256(source_review_raw).hexdigest(),
        "position_environments.csv": hashlib.sha256(environment_raw).hexdigest(),
        "metric_forecasts.csv": hashlib.sha256(caller_raw).hexdigest(),
        "caller_fingerprint_manifest.json": hashlib.sha256(caller_manifest_raw).hexdigest(),
        "team_style.csv": hashlib.sha256(
            observed_style.raw_by_path[str(observed_style.path)]
        ).hexdigest(),
        "team_style_manifest.json": hashlib.sha256(
            observed_style.raw_by_path[str(observed_style.manifest_path)]
        ).hexdigest(),
    }
    if ffc_path is not None:
        input_hashes["adp.csv"] = hashlib.sha256(ffc_raw).hexdigest()
    return PlayerRoleResult(
        season=season,
        player_context_path=context_root,
        position_environment_path=environment_path,
        caller_fingerprint_path=caller_path,
        observed_style_path=observed_style.path,
        observed_style_manifest_path=observed_style.manifest_path,
        ffc_path=ffc_path,
        input_hashes=input_hashes,
        roles=tuple(sorted(roles, key=lambda row: (row["team"], row["resource"], -float(row["role_share_median"]), row["player_name"]))),
        role_candidates=tuple(sorted(
            role_candidates,
            key=lambda row: (
                row["team"], row["resource"], -float(row["latent_role_weight"]),
                row["player_name"],
            ),
        )),
        reconciliation=tuple(sorted(reconciliation, key=lambda row: (row["team"], row["resource"]))),
        ffc_crosswalk=tuple(sorted(ffc_crosswalk, key=lambda row: (row["source_position"], _float(row["adp"]) if row["adp"] else 9999, row["source_name"]))),
        identity_review=tuple(sorted(identity_review, key=lambda row: (row["review_category"], str(row["source"]), str(row["team"]), str(row["player_name"])))),
        availability_review=tuple(
            sorted(
                availability,
                key=lambda row: (
                    0 if row["ffc_adp"] else 1,
                    _float(row["ffc_adp"]) if row["ffc_adp"] else 9999,
                    row["team"],
                    row["position"],
                    row["player_name"],
                ),
            )
        ),
        conversion_factors=conversions,
        conversion_training_seasons=conversion_estimate.training_seasons,
        conversion_team_season_count=conversion_estimate.team_season_count,
    )


def _csv_bytes(fields: tuple[str, ...], rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def write_player_role_snapshot(result: PlayerRoleResult, root: str | Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    parent = Path(root) / "player_roles" / str(result.season)
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"player-role snapshot already exists: {destination}")

    artifacts = {
        "player_role_priors.csv": _csv_bytes(ROLE_FIELDS, result.roles),
        "player_role_candidates.csv": _csv_bytes(
            ROLE_CANDIDATE_FIELDS, result.role_candidates
        ),
        "team_reconciliation.csv": _csv_bytes(RECONCILIATION_FIELDS, result.reconciliation),
        "ffc_crosswalk.csv": _csv_bytes(FFC_FIELDS, result.ffc_crosswalk),
        "identity_review.csv": _csv_bytes(IDENTITY_REVIEW_FIELDS, result.identity_review),
        "availability_review.csv": _csv_bytes(AVAILABILITY_FIELDS, result.availability_review),
    }
    ffc_counts: dict[str, int] = defaultdict(int)
    for row in result.ffc_crosswalk:
        ffc_counts[str(row["match_status"])] += 1
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "model_status": MODEL_STATUS,
        "season": result.season,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "methodology": {
            "scope": "player opportunity role priors conditional on reconciled current_status=ACT",
            "identity": "nflverse joins use source IDs; FFC uses unique canonicalized name+team+position only and queues every exception",
            "history": "regular-season usage, recency factor 0.65, prior-team transfer factor 0.70, transferred-role reliability multiplier 0.45, reliability capped at 0.80 and then bounded by resource-specific history weights",
            "current_role": "resource-specific blend of normalized historical share and latest depth rank; QB resources use depth only after the frozen universal blend lost to depth in the availability-conditioned 2023-2025 retrospective test",
            "latent_candidates": "all currently affiliated players receive a latent role weight; active weights are rescaled so removing every non-ACT player exactly reproduces the published active baseline",
            "snap_evidence": "PFR offensive snap share is published as a diagnostic field but is not yet weighted until held-out tests establish incremental value beyond direct opportunities",
            "team_pools": "eligible nflverse PBP pass/rush plays come from the caller-aware environment; matched team-season history separately converts pass plays to official attempts-plus-sacks and targets, and non-QB PBP rush plays to official RB carries",
            "denominator_contract": "QB_DROPBACKS = PBP pass plays * official QB dropbacks/PBP pass play; position targets = PBP pass plays * official targets/PBP pass play * position target share; RB_CARRIES = non-QB PBP rush plays * official RB carries/non-QB PBP rush play",
            "reconciliation": "median resource shares sum to one within every team room and median allocations reproduce the team pool exactly",
            "uncertainty": "low/high are uncalibrated marginal structural ranges; they intentionally do not sum across players; resource selection used evaluation-only actual weekly active status, is retrospective, and must be frozen for prospective 2026 evaluation",
            "availability": "DEV/RES/RSR/PUP/RSN/SUS/EXE players are queued and excluded rather than assigned a zero season projection",
            "forbidden": "not an efficiency, touchdown, health, games-played, or fantasy-point projection",
        },
        "parameters": {
            "history_recency_factor": 0.65,
            "prior_team_transfer_factor": 0.70,
            "transferred_role_reliability_multiplier": TRANSFER_RELIABILITY_MULTIPLIER,
            "maximum_history_blend_weight": 0.80,
            "resource_history_weight": RESOURCE_HISTORY_WEIGHT,
            "full_season_games": FULL_SEASON_GAMES,
            "depth_weights": {key: list(value) for key, value in DEPTH_WEIGHTS.items()},
            "base_interval_width": BASE_INTERVAL_WIDTH,
            "conversion_factors": dict(result.conversion_factors),
            "conversion_training_seasons": list(result.conversion_training_seasons),
            "conversion_team_season_count": result.conversion_team_season_count,
        },
        "inputs": {
            "player_context": str(result.player_context_path),
            "position_environments": str(result.position_environment_path),
            "caller_fingerprints": str(result.caller_fingerprint_path),
            "caller_fingerprint_manifest": str(
                result.caller_fingerprint_path.parent / "manifest.json"
            ),
            "observed_team_style": str(result.observed_style_path),
            "observed_team_style_manifest": str(result.observed_style_manifest_path),
            "ffc_adp": str(result.ffc_path) if result.ffc_path else None,
            "sha256": dict(result.input_hashes),
        },
        "quality": {
            "team_count": len({row["team"] for row in result.reconciliation}),
            "resource_count": len({row["resource"] for row in result.reconciliation}),
            "role_rows": len(result.roles),
            "role_candidate_rows": len(result.role_candidates),
            "reconciliation_rows": len(result.reconciliation),
            "maximum_reconciliation_error": max(
                (float(row["reconciliation_error"]) for row in result.reconciliation),
                default=0.0,
            ),
            "ffc_match_status_counts": dict(sorted(ffc_counts.items())),
            "identity_review_rows": len(result.identity_review),
            "availability_review_rows": len(result.availability_review),
        },
        "artifacts": {
            name: {
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "fields": list(
                    {
                        "player_role_priors.csv": ROLE_FIELDS,
                        "player_role_candidates.csv": ROLE_CANDIDATE_FIELDS,
                        "team_reconciliation.csv": RECONCILIATION_FIELDS,
                        "ffc_crosswalk.csv": FFC_FIELDS,
                        "identity_review.csv": IDENTITY_REVIEW_FIELDS,
                        "availability_review.csv": AVAILABILITY_FIELDS,
                    }[name]
                ),
            }
            for name, payload in artifacts.items()
        },
    }

    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
    try:
        for name, payload in artifacts.items():
            (staging / name).write_bytes(payload)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
