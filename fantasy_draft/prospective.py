"""Tamper-evident preseason freeze for prospective NFL forecast evaluation.

The freeze is intentionally boring: it verifies the selected upstream snapshots,
copies the exact issued forecasts into one immutable bundle, joins current-role audit
status onto the weekly high-value rows, and refuses to run on or after the first
scheduled game.  Future scoring must consume this bundle rather than rebuild a
forecast with later data or changed code.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "1.1.0"
MODEL_VERSION = "prospective-preseason-freeze-v0.4.0"
MODEL_STATUS = "immutable_preseason_forecast_frozen_before_outcomes"
CORRECTION_NOTICE: Mapping[str, Any] = {
    "supersedes_model_version": "prospective-preseason-freeze-v0.3.0",
    "supersedes_freeze_fingerprint": (
        "a515fe9780fbd9e62a0e6751215d10ae0939d7b621f01f6fa31f821beda8cb04"
    ),
    "issued_before_outcomes": True,
    "reason": (
        "correct a denominator-definition mismatch by converting eligible PBP "
        "pass and rush plays to official QB dropbacks, targets, and RB carries "
        "with frozen matched-history factors"
    ),
    "unchanged_elements": (
        "team style point forecasts, player role shares, availability policy, "
        "qualitative evidence decisions, and scoring windows"
    ),
}
EXPECTED_MODEL_VERSIONS: Mapping[str, str] = {
    "caller_fingerprints": "caller-fingerprint-heuristic-v0.1.0",
    "position_environments": "position-opportunity-environment-v0.3.0",
    "player_roles": "player-role-prior-v0.4.0",
    "availability": "weekly-availability-status-cohort-v0.2.0",
    "high_value_priors": "high-value-role-prior-v0.2.0",
    "high_value_volumes": "high-value-event-pool-v0.3.0",
    "role_research": "current-role-research-audit-v0.1.0",
}
WEEKS = tuple(range(1, 19))
POSITIONS = {"QB", "RB", "WR", "TE"}
REVIEW_STATUSES = {
    "reviewed_model_retained",
    "reviewed_inconclusive_model_retained",
    "reviewed_role_conflict_model_retained",
}
INVENTORY_FIELDS = (
    "component", "snapshot_path", "model_version", "source_date",
    "age_days_at_cutoff", "artifact", "artifact_sha256", "row_count",
    "temporal_status",
)
JOINED_REVIEW_FIELDS = (
    "current_role_review_status", "evidence_record_id", "evidence_strength",
    "evidence_as_of", "numeric_override_applied",
)
SCORING_CONTRACT: Mapping[str, Any] = {
    "contract_version": "2026-preseason-evaluation-v1",
    "evaluation_windows": [4, 8, 18],
    "outcome_policy": (
        "use newly retrieved, hash-preserved nflverse weekly roster, opportunity, "
        "schedule, and high-value event data; never rebuild the forecast inputs"
    ),
    "candidate_universe": (
        "union frozen candidates with later actual roster entrants; any later "
        "entrant receives zero forecast mass"
    ),
    "availability": {
        "forecast_field": "active_probability_median",
        "target": "scheduled-game weekly roster status ACT equals 1; INA equals 0",
        "primary_metric": "Brier score across frozen player-weeks",
        "secondary_metrics": [
            "mean prediction",
            "observed active rate",
            "calibration by frozen status cohort and position",
        ],
    },
    "ordinary_role": {
        "forecast": (
            "renormalize frozen latent_role_weight among actual ACT opening "
            "candidates and allocate the observed team resource"
        ),
        "primary_metric": (
            "unweighted mean team-position-resource total variation distance"
        ),
        "secondary_metrics": [
            "median total variation distance",
            "player share mean absolute error",
            "top-role accuracy",
            "opening-candidate actual-share coverage",
        ],
        "baselines": ["depth_prior_share", "historical_share"],
    },
    "ordinary_issued_counts": {
        "forecast_field": "expected_opportunities_this_week",
        "targets": ["dropbacks", "carries", "targets"],
        "primary_metric": "mean absolute error per player-game",
        "secondary_metrics": [
            "root mean squared error per player-game",
            "mean signed error per player-game",
            "descriptive p10-p90 containment without a nominal coverage claim",
        ],
    },
    "high_value_role": {
        "forecast": (
            "renormalize frozen latent_high_value_share_p24 among actual ACT "
            "opening candidates and allocate the observed team-metric event pool"
        ),
        "primary_metric": "unweighted mean team-metric total variation distance",
        "secondary_metrics": [
            "median total variation distance",
            "player share mean absolute error",
            "opening-candidate actual-share coverage",
        ],
        "baseline": "base_model_all_affiliated_share",
    },
    "high_value_issued_counts": {
        "forecast_field": "expected_event_count_mean",
        "primary_metric": "mean absolute error per player-game",
        "secondary_metrics": [
            "root mean squared error per player-game",
            "mean signed error per player-game",
            "descriptive scenario-envelope containment without a nominal coverage claim",
        ],
    },
    "team_resources": {
        "forecast_field": "team_pool_this_week",
        "unit_contract": (
            "eligible PBP pass/rush plays are converted to official QB dropbacks, "
            "targets, and RB carries with frozen matched-history factors"
        ),
        "primary_metric": "mean absolute error per team-game",
        "secondary_metric": "root mean squared error per team-game",
    },
    "certainty_diagnostic": (
        "within each directly matchable team metric, report absolute error by "
        "frozen metric-certainty tier and its rank association; do not reinterpret "
        "0-100 certainty indices as probabilities"
    ),
    "retuning": (
        "forbidden inside the 2026 evaluation; code, evidence, target, exclusion, "
        "or metric changes require a separately versioned forecast"
    ),
    "excluded_targets": [
        "efficiency",
        "touchdowns",
        "fantasy points",
        "position-environment composite accuracy until an outcome target is frozen",
    ],
}


class ProspectiveFreezeDataError(ValueError):
    """Raised when inputs cannot support a leakage-safe preseason freeze."""


@dataclass(frozen=True)
class ProspectiveFreezeResult:
    season: int
    cutoff: date
    first_scheduled_game: date
    component_inputs: Mapping[str, Mapping[str, Any]]
    input_hashes: Mapping[str, str]
    artifacts: Mapping[str, bytes]
    artifact_fields: Mapping[str, tuple[str, ...]]
    quality: Mapping[str, Any]
    freeze_fingerprint: str


def _parse_date(value: str | date, context: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as error:
        raise ProspectiveFreezeDataError(
            f"{context} must be an ISO date (YYYY-MM-DD)"
        ) from error


def _integer(value: Any, context: str) -> int:
    try:
        result = int(str(value))
    except (TypeError, ValueError) as error:
        raise ProspectiveFreezeDataError(f"{context} must be an integer") from error
    if str(result) != str(value).strip():
        raise ProspectiveFreezeDataError(f"{context} must be an integer")
    return result


def _read_manifest(
    root: Path, component: str
) -> tuple[bytes, Mapping[str, Any]]:
    path = root / "manifest.json"
    if not path.is_file():
        raise ProspectiveFreezeDataError(f"missing {component} manifest: {path}")
    raw = path.read_bytes()
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ProspectiveFreezeDataError(
            f"invalid {component} manifest JSON: {path}"
        ) from error
    if not isinstance(manifest, Mapping):
        raise ProspectiveFreezeDataError(f"{component} manifest is not an object")
    expected = EXPECTED_MODEL_VERSIONS[component]
    if manifest.get("model_version") != expected:
        raise ProspectiveFreezeDataError(
            f"unsupported {component} model version: expected {expected}, "
            f"got {manifest.get('model_version')}"
        )
    return raw, manifest


def _read_verified_csv(
    root: Path,
    manifest: Mapping[str, Any],
    filename: str,
    required: set[str],
    *,
    allow_empty: bool = False,
) -> tuple[bytes, tuple[str, ...], list[dict[str, str]]]:
    metadata = (manifest.get("artifacts") or {}).get(filename)
    if not isinstance(metadata, Mapping) or not metadata.get("sha256"):
        raise ProspectiveFreezeDataError(
            f"manifest does not describe {filename}: {root}"
        )
    path = root / filename
    if not path.is_file():
        raise ProspectiveFreezeDataError(f"input does not exist: {path}")
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != metadata["sha256"]:
        raise ProspectiveFreezeDataError(
            f"input hash mismatch for {path}: expected {metadata['sha256']}, got {actual}"
        )
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        fields = tuple(reader.fieldnames or ())
        rows = list(reader)
    except UnicodeDecodeError as error:
        raise ProspectiveFreezeDataError(f"input is not UTF-8 CSV: {path}") from error
    missing = required - set(fields)
    if missing or (not rows and not allow_empty):
        raise ProspectiveFreezeDataError(
            f"{path} is empty or missing fields {sorted(missing)}"
        )
    return raw, fields, rows


def _snapshot_date(root: Path, manifest: Mapping[str, Any], component: str) -> date:
    for field in ("as_of", "created_at", "retrieved_at"):
        value = str(manifest.get(field) or "").strip()
        if value:
            try:
                return date.fromisoformat(value[:10])
            except ValueError as error:
                raise ProspectiveFreezeDataError(
                    f"{component} {field} is not ISO dated: {value}"
                ) from error
    prefix = root.name[:8]
    try:
        return datetime.strptime(prefix, "%Y%m%d").date()
    except ValueError as error:
        raise ProspectiveFreezeDataError(
            f"cannot derive a source date for {component}: {root}"
        ) from error


def _csv_bytes(fields: tuple[str, ...], rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _single_season(rows: Iterable[Mapping[str, str]], context: str) -> int:
    seasons = {_integer(row.get("season"), f"{context} season") for row in rows}
    if len(seasons) != 1:
        raise ProspectiveFreezeDataError(
            f"{context} must contain exactly one season, got {sorted(seasons)}"
        )
    return next(iter(seasons))


def _team_set(rows: Iterable[Mapping[str, str]], context: str) -> set[str]:
    teams = {str(row.get("team") or "").strip() for row in rows}
    if "" in teams:
        raise ProspectiveFreezeDataError(f"{context} contains a blank team")
    return teams


def build_prospective_freeze(
    caller_fingerprints: str | Path,
    position_environments: str | Path,
    player_roles: str | Path,
    availability: str | Path,
    high_value_priors: str | Path,
    high_value_volumes: str | Path,
    role_research: str | Path,
    *,
    cutoff: str | date,
) -> ProspectiveFreezeResult:
    """Verify and bundle the issued preseason forecasts before any game is played."""

    cutoff_date = _parse_date(cutoff, "cutoff")
    roots = {
        "caller_fingerprints": Path(caller_fingerprints),
        "position_environments": Path(position_environments),
        "player_roles": Path(player_roles),
        "availability": Path(availability),
        "high_value_priors": Path(high_value_priors),
        "high_value_volumes": Path(high_value_volumes),
        "role_research": Path(role_research),
    }
    manifests: dict[str, Mapping[str, Any]] = {}
    manifest_raw: dict[str, bytes] = {}
    source_dates: dict[str, date] = {}
    for component, root in roots.items():
        raw, manifest = _read_manifest(root, component)
        manifest_raw[component] = raw
        manifests[component] = manifest
        source_date = _snapshot_date(root, manifest, component)
        if source_date > cutoff_date:
            raise ProspectiveFreezeDataError(
                f"{component} source date {source_date} is after cutoff {cutoff_date}"
            )
        source_dates[component] = source_date

    loaded: dict[str, tuple[bytes, tuple[str, ...], list[dict[str, str]]]] = {}
    specifications = (
        ("caller_fingerprints", "teams.csv", "team_systems.csv", {
            "season", "team", "head_coach", "play_caller",
            "broad_system_certainty_v0", "exact_style_certainty_v0", "model_status",
        }),
        ("caller_fingerprints", "metric_forecasts.csv", "team_metric_forecasts.csv", {
            "season", "team", "play_caller", "metric", "forecast_value_v0",
            "metric_certainty_v0", "model_status",
        }),
        ("position_environments", "position_environments.csv", "position_environments.csv", {
            "season", "team", "position", "certainty_adjusted_score_v0",
            "team_exact_style_certainty_v0", "model_status",
        }),
        ("player_roles", "player_role_priors.csv", "player_role_priors.csv", {
            "season", "team", "position", "resource", "gsis_id", "player_name",
            "role_share_median", "full_season_opportunities_median", "model_status",
        }),
        ("player_roles", "player_role_candidates.csv", "player_role_candidates.csv", {
            "season", "team", "position", "resource", "gsis_id", "player_name",
            "latent_role_weight", "depth_prior_share", "historical_share",
        }),
        ("availability", "weekly_availability.csv", "weekly_availability_forecasts.csv", {
            "season", "week", "gameday", "team", "scheduled_game", "position",
            "gsis_id", "player_name", "active_probability_low",
            "active_probability_median", "active_probability_high", "model_status",
        }),
        ("availability", "weekly_expected_roles.csv", "weekly_role_forecasts.csv", {
            "season", "week", "gameday", "team", "scheduled_game", "position",
            "resource", "gsis_id", "player_name", "latent_role_weight",
            "expected_share_mean", "expected_opportunities_this_week", "model_status",
        }),
        ("high_value_priors", "player_high_value_priors.csv", "player_high_value_priors.csv", {
            "season", "team", "position", "metric", "base_resource", "gsis_id",
            "player_name", "base_model_all_affiliated_share", "share_p24", "model_status",
        }),
        ("high_value_priors", "weekly_high_value_roles.csv", "weekly_high_value_role_forecasts.csv", {
            "season", "week", "gameday", "team", "scheduled_game", "position",
            "metric", "base_resource", "gsis_id", "player_name",
            "latent_high_value_share_p24", "expected_share_mean", "model_status",
        }),
        ("high_value_volumes", "team_high_value_event_pools.csv", "team_high_value_event_pools.csv", {
            "season", "team", "position", "metric", "base_resource",
            "event_pool_per_game_median", "model_status",
        }),
        ("high_value_volumes", "player_high_value_opportunities.csv", "player_high_value_opportunities.csv", {
            "season", "team", "position", "metric", "base_resource", "gsis_id",
            "player_name", "availability_adjusted_season_expected_events",
            "requires_current_role_review", "model_status",
        }),
        ("high_value_volumes", "weekly_player_high_value_opportunities.csv", "weekly_high_value_count_forecasts.csv", {
            "season", "week", "gameday", "team", "scheduled_game", "position",
            "metric", "base_resource", "gsis_id", "player_name",
            "expected_event_count_mean", "combined_marginal_scenario_low",
            "combined_marginal_scenario_high", "model_status",
        }),
        ("high_value_volumes", "weekly_reconciliation.csv", "weekly_high_value_reconciliation.csv", {
            "season", "week", "team", "metric", "reconciliation_error",
        }),
        ("role_research", "player_review_queue.csv", "role_evidence.csv", {
            "season", "team", "position", "metric", "gsis_id", "player_name",
            "review_status", "evidence_record_id", "evidence_strength", "evidence_as_of",
            "numeric_override_applied",
        }),
        ("role_research", "team_rate_review_queue.csv", "team_rate_evidence.csv", {
            "season", "team", "position", "metric", "review_status",
            "evidence_as_of", "numeric_override_applied",
        }),
        ("role_research", "review_coverage.csv", "review_coverage.csv", {
            "scope", "metric", "queued_rows", "evidence_reviewed_rows",
            "inconclusive_rows", "unreviewed_rows", "review_coverage",
        }),
        ("role_research", "evidence_sources.csv", "evidence_sources.csv", {
            "source_id", "title", "publisher", "source_type", "url", "accessed_at",
        }),
    )
    output_artifacts: dict[str, bytes] = {}
    output_fields: dict[str, tuple[str, ...]] = {}
    input_hashes: dict[str, str] = {}
    inventory: list[dict[str, Any]] = []
    component_inputs: dict[str, dict[str, Any]] = {}
    for component, root in roots.items():
        manifest_hash = hashlib.sha256(manifest_raw[component]).hexdigest()
        input_hashes[f"{component}/manifest.json"] = manifest_hash
        component_inputs[component] = {
            "path": str(root),
            "model_version": EXPECTED_MODEL_VERSIONS[component],
            "manifest_sha256": manifest_hash,
            "source_date": source_dates[component].isoformat(),
            "age_days_at_cutoff": (cutoff_date - source_dates[component]).days,
            "artifact_sha256": {},
        }

    output_names: dict[tuple[str, str], str] = {}
    for component, source_name, output_name, required in specifications:
        raw, fields, rows = _read_verified_csv(
            roots[component], manifests[component], source_name, required,
            allow_empty=source_name == "team_rate_review_queue.csv",
        )
        loaded[f"{component}/{source_name}"] = (raw, fields, rows)
        output_names[(component, source_name)] = output_name
        digest = hashlib.sha256(raw).hexdigest()
        input_hashes[f"{component}/{source_name}"] = digest
        component_inputs[component]["artifact_sha256"][source_name] = digest
        inventory.append({
            "component": component,
            "snapshot_path": str(roots[component]),
            "model_version": EXPECTED_MODEL_VERSIONS[component],
            "source_date": source_dates[component].isoformat(),
            "age_days_at_cutoff": (cutoff_date - source_dates[component]).days,
            "artifact": source_name,
            "artifact_sha256": digest,
            "row_count": len(rows),
            "temporal_status": "available_on_or_before_cutoff",
        })
        if source_name != "weekly_player_high_value_opportunities.csv":
            output_artifacts[output_name] = raw
            output_fields[output_name] = fields

    season_sets: list[tuple[str, list[dict[str, str]]]] = []
    for key, (_, _, rows) in loaded.items():
        if rows and "season" in rows[0]:
            season_sets.append((key, rows))
    seasons = {_single_season(rows, key) for key, rows in season_sets}
    if len(seasons) != 1:
        raise ProspectiveFreezeDataError(
            f"input components mix seasons: {sorted(seasons)}"
        )
    season = next(iter(seasons))
    manifest_seasons = {
        _integer(manifest.get("season"), f"{component} manifest season")
        for component, manifest in manifests.items()
    }
    if manifest_seasons != {season}:
        raise ProspectiveFreezeDataError(
            f"manifest seasons do not match row season {season}: {sorted(manifest_seasons)}"
        )

    caller_teams = loaded["caller_fingerprints/teams.csv"][2]
    metric_rows = loaded["caller_fingerprints/metric_forecasts.csv"][2]
    position_rows = loaded["position_environments/position_environments.csv"][2]
    role_rows = loaded["player_roles/player_role_priors.csv"][2]
    availability_rows = loaded["availability/weekly_availability.csv"][2]
    weekly_role_rows = loaded["availability/weekly_expected_roles.csv"][2]
    high_prior_rows = loaded["high_value_priors/player_high_value_priors.csv"][2]
    weekly_high_role_rows = loaded["high_value_priors/weekly_high_value_roles.csv"][2]
    team_high_rows = loaded["high_value_volumes/team_high_value_event_pools.csv"][2]
    player_high_rows = loaded["high_value_volumes/player_high_value_opportunities.csv"][2]
    _, weekly_high_fields, weekly_high_rows = loaded[
        "high_value_volumes/weekly_player_high_value_opportunities.csv"
    ]
    research_rows = loaded["role_research/player_review_queue.csv"][2]
    team_research_rows = loaded["role_research/team_rate_review_queue.csv"][2]
    coverage_rows = loaded["role_research/review_coverage.csv"][2]
    evidence_sources = loaded["role_research/evidence_sources.csv"][2]

    team_sets = {
        "caller teams": _team_set(caller_teams, "caller teams"),
        "caller metrics": _team_set(metric_rows, "caller metrics"),
        "position environments": _team_set(position_rows, "position environments"),
        "player roles": _team_set(role_rows, "player roles"),
        "availability": _team_set(availability_rows, "availability"),
        "weekly roles": _team_set(weekly_role_rows, "weekly roles"),
        "high-value priors": _team_set(high_prior_rows, "high-value priors"),
        "weekly high-value roles": _team_set(
            weekly_high_role_rows, "weekly high-value roles"
        ),
        "team high-value pools": _team_set(team_high_rows, "team high-value pools"),
        "player high-value counts": _team_set(player_high_rows, "player high-value counts"),
        "weekly high-value counts": _team_set(weekly_high_rows, "weekly high-value counts"),
    }
    teams = team_sets["caller teams"]
    if len(teams) != 32:
        raise ProspectiveFreezeDataError(
            f"preseason freeze requires all 32 NFL teams, got {len(teams)}"
        )
    for context, values in team_sets.items():
        if values != teams:
            raise ProspectiveFreezeDataError(
                f"{context} team set does not match caller team set"
            )
    positions_by_team: dict[str, set[str]] = defaultdict(set)
    for row in position_rows:
        positions_by_team[row["team"]].add(row["position"])
    if any(values != POSITIONS for values in positions_by_team.values()):
        raise ProspectiveFreezeDataError(
            "position environments must contain QB/RB/WR/TE for every team"
        )

    schedule: dict[tuple[str, int], tuple[str, str]] = {}
    for row in availability_rows:
        week = _integer(row["week"], "availability week")
        key = row["team"], week
        value = row["scheduled_game"], row["gameday"]
        if key in schedule and schedule[key] != value:
            raise ProspectiveFreezeDataError(
                f"availability contains inconsistent schedule values for {key}"
            )
        schedule[key] = value
    expected_schedule = {(team, week) for team in teams for week in WEEKS}
    if set(schedule) != expected_schedule:
        raise ProspectiveFreezeDataError(
            "availability must cover every team and Week 1-18"
        )
    scheduled_counts = Counter(
        team for (team, _), (scheduled, _) in schedule.items()
        if scheduled == "true"
    )
    if any(scheduled_counts[team] != 17 for team in teams):
        raise ProspectiveFreezeDataError(
            "availability schedule must contain 17 games per team"
        )
    game_dates = [
        _parse_date(gameday, f"{team} Week {week} gameday")
        for (team, week), (scheduled, gameday) in schedule.items()
        if scheduled == "true"
    ]
    first_game = min(game_dates)
    if cutoff_date >= first_game:
        raise ProspectiveFreezeDataError(
            f"cutoff {cutoff_date} must be before first scheduled game {first_game}"
        )
    for context, rows in (
        ("weekly roles", weekly_role_rows),
        ("weekly high-value roles", weekly_high_role_rows),
        ("weekly high-value counts", weekly_high_rows),
    ):
        weeks = {_integer(row["week"], f"{context} week") for row in rows}
        if weeks != set(WEEKS):
            raise ProspectiveFreezeDataError(
                f"{context} must cover Weeks 1-18, got {sorted(weeks)}"
            )
        for row in rows:
            key = row["team"], _integer(row["week"], f"{context} week")
            if schedule.get(key) != (row["scheduled_game"], row["gameday"]):
                raise ProspectiveFreezeDataError(
                    f"{context} schedule does not match availability for {key}"
                )

    supported_metrics = set(manifests["high_value_volumes"].get("supported_metrics") or ())
    if not supported_metrics:
        raise ProspectiveFreezeDataError("high-value volume manifest has no metrics")
    for context, rows in (
        ("team high-value pools", team_high_rows),
        ("player high-value priors", high_prior_rows),
        ("weekly high-value roles", weekly_high_role_rows),
        ("player high-value counts", player_high_rows),
        ("weekly high-value counts", weekly_high_rows),
    ):
        if {row["metric"] for row in rows} != supported_metrics:
            raise ProspectiveFreezeDataError(
                f"{context} do not match the supported metric set"
            )

    research: dict[tuple[str, str, str], Mapping[str, str]] = {}
    for row in research_rows:
        key = row["team"], row["metric"], row["gsis_id"]
        if key in research:
            raise ProspectiveFreezeDataError(f"duplicate current-role review key {key}")
        if row["review_status"] not in REVIEW_STATUSES:
            raise ProspectiveFreezeDataError(
                f"current-role review remains unreviewed or invalid for {key}"
            )
        if row["numeric_override_applied"] != "false":
            raise ProspectiveFreezeDataError(
                f"current-role review attempts a numeric override for {key}"
            )
        research[key] = row
    for row in team_research_rows:
        if row["review_status"] not in REVIEW_STATUSES:
            raise ProspectiveFreezeDataError(
                "team-rate evidence remains unreviewed or invalid"
            )
        if row["numeric_override_applied"] != "false":
            raise ProspectiveFreezeDataError(
                "team-rate evidence contains a numeric override"
            )
    for row in research_rows:
        if _parse_date(
            row["evidence_as_of"], "player role evidence_as_of"
        ) > cutoff_date:
            raise ProspectiveFreezeDataError(
                "player role evidence contains information after the cutoff"
            )
    for row in team_research_rows:
        if _parse_date(
            row["evidence_as_of"], "team-rate evidence_as_of"
        ) > cutoff_date:
            raise ProspectiveFreezeDataError(
                "team-rate evidence contains information after the cutoff"
            )
    for row in evidence_sources:
        for field in ("published_at", "accessed_at"):
            value = str(row.get(field) or "").strip()
            if value and _parse_date(value, f"evidence source {field}") > cutoff_date:
                raise ProspectiveFreezeDataError(
                    f"evidence source {field} contains information after the cutoff"
                )
    overall = next(
        (
            row for row in coverage_rows
            if row["scope"] == "player" and row["metric"] == "ALL"
        ),
        None,
    )
    if overall is None:
        raise ProspectiveFreezeDataError("role research has no player/ALL coverage row")
    if (
        overall["queued_rows"] != overall["evidence_reviewed_rows"]
        or overall["unreviewed_rows"] != "0"
        or float(overall["review_coverage"]) != 1.0
        or _integer(overall["queued_rows"], "player review queued rows")
        != len(research_rows)
    ):
        raise ProspectiveFreezeDataError(
            "role research must have complete review coverage before freezing"
        )
    if team_research_rows:
        team_overall = next(
            (
                row for row in coverage_rows
                if row["scope"] == "team_rate" and row["metric"] == "ALL"
            ),
            None,
        )
        if team_overall is None or (
            team_overall["queued_rows"] != team_overall["evidence_reviewed_rows"]
            or team_overall["unreviewed_rows"] != "0"
            or float(team_overall["review_coverage"]) != 1.0
            or _integer(
                team_overall["queued_rows"], "team-rate review queued rows"
            ) != len(team_research_rows)
        ):
            raise ProspectiveFreezeDataError(
                "team-rate research must have complete review coverage before freezing"
            )

    joined_rows: list[dict[str, Any]] = []
    seen_research: set[tuple[str, str, str]] = set()
    required_by_player = {
        (row["team"], row["metric"], row["gsis_id"]): row[
            "requires_current_role_review"
        ]
        for row in player_high_rows
    }
    for row in weekly_high_rows:
        key = row["team"], row["metric"], row["gsis_id"]
        record = research.get(key)
        required = required_by_player.get(key)
        if required is None:
            raise ProspectiveFreezeDataError(
                f"weekly high-value row has no season-level parent {key}"
            )
        if (required == "true") != (record is not None):
            raise ProspectiveFreezeDataError(
                f"current-role review requirement and evidence disagree for {key}"
            )
        if record:
            seen_research.add(key)
            review_values = {
                "current_role_review_status": record["review_status"],
                "evidence_record_id": record["evidence_record_id"],
                "evidence_strength": record["evidence_strength"],
                "evidence_as_of": record["evidence_as_of"],
                "numeric_override_applied": record["numeric_override_applied"],
            }
        else:
            review_values = {
                "current_role_review_status": "not_required",
                "evidence_record_id": "",
                "evidence_strength": "",
                "evidence_as_of": "",
                "numeric_override_applied": "false",
            }
        joined_rows.append({**row, **review_values})
    if seen_research != set(research):
        missing = sorted(set(research) - seen_research)[:5]
        raise ProspectiveFreezeDataError(
            f"reviewed rows are missing from weekly high-value forecasts: {missing}"
        )
    joined_fields = (*weekly_high_fields, *JOINED_REVIEW_FIELDS)
    output_artifacts["weekly_high_value_count_forecasts.csv"] = _csv_bytes(
        joined_fields, joined_rows
    )
    output_fields["weekly_high_value_count_forecasts.csv"] = joined_fields

    inventory_raw = _csv_bytes(INVENTORY_FIELDS, inventory)
    output_artifacts["input_inventory.csv"] = inventory_raw
    output_fields["input_inventory.csv"] = INVENTORY_FIELDS

    output_hashes = {
        name: hashlib.sha256(raw).hexdigest()
        for name, raw in sorted(output_artifacts.items())
    }
    fingerprint_payload = json.dumps(
        {
            "model_version": MODEL_VERSION,
            "season": season,
            "cutoff": cutoff_date.isoformat(),
            "first_scheduled_game": first_game.isoformat(),
            "input_hashes": dict(sorted(input_hashes.items())),
            "output_hashes": output_hashes,
            "scoring_contract": SCORING_CONTRACT,
            "correction_notice": CORRECTION_NOTICE,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    fingerprint = hashlib.sha256(fingerprint_payload).hexdigest()
    review_counts = Counter(row["review_status"] for row in research_rows)
    quality = {
        "team_count": len(teams),
        "team_system_rows": len(caller_teams),
        "team_metric_forecast_rows": len(metric_rows),
        "position_environment_rows": len(position_rows),
        "player_role_rows": len(role_rows),
        "weekly_availability_rows": len(availability_rows),
        "weekly_role_rows": len(weekly_role_rows),
        "player_high_value_prior_rows": len(high_prior_rows),
        "weekly_high_value_role_rows": len(weekly_high_role_rows),
        "team_high_value_pool_rows": len(team_high_rows),
        "player_high_value_count_rows": len(player_high_rows),
        "weekly_high_value_count_rows": len(joined_rows),
        "role_review_queue_rows": len(research_rows),
        "role_review_resolved_rows": (
            review_counts["reviewed_model_retained"]
            + review_counts["reviewed_role_conflict_model_retained"]
        ),
        "role_review_inconclusive_rows": review_counts[
            "reviewed_inconclusive_model_retained"
        ],
        "role_review_unreviewed_rows": 0,
        "evidence_source_rows": len(evidence_sources),
        "numeric_overrides_applied": 0,
        "supported_high_value_metrics": sorted(supported_metrics),
        "first_scheduled_game": first_game.isoformat(),
        "frozen_before_first_scheduled_game": True,
    }
    return ProspectiveFreezeResult(
        season=season,
        cutoff=cutoff_date,
        first_scheduled_game=first_game,
        component_inputs=component_inputs,
        input_hashes=input_hashes,
        artifacts=output_artifacts,
        artifact_fields=output_fields,
        quality=quality,
        freeze_fingerprint=fingerprint,
    )


def verify_prospective_freeze(
    root: str | Path,
    *,
    expected_fingerprint: str | None = None,
) -> Mapping[str, Any]:
    """Verify frozen bytes and identity before any future outcome scoring."""

    snapshot = Path(root)
    manifest_path = snapshot / "manifest.json"
    if not manifest_path.is_file():
        raise ProspectiveFreezeDataError(
            f"missing prospective freeze manifest: {manifest_path}"
        )
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except json.JSONDecodeError as error:
        raise ProspectiveFreezeDataError(
            f"invalid prospective freeze manifest JSON: {manifest_path}"
        ) from error
    if not isinstance(manifest, Mapping):
        raise ProspectiveFreezeDataError("prospective freeze manifest is not an object")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ProspectiveFreezeDataError(
            f"unsupported prospective freeze schema: {manifest.get('schema_version')}"
        )
    if manifest.get("model_version") != MODEL_VERSION:
        raise ProspectiveFreezeDataError(
            f"unsupported prospective freeze model: {manifest.get('model_version')}"
        )
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or not artifacts:
        raise ProspectiveFreezeDataError("prospective freeze has no artifacts")
    output_hashes: dict[str, str] = {}
    for name, metadata in artifacts.items():
        if Path(name).name != name or not isinstance(metadata, Mapping):
            raise ProspectiveFreezeDataError(
                f"invalid prospective freeze artifact declaration: {name}"
            )
        expected = str(metadata.get("sha256") or "")
        path = snapshot / name
        if not expected or not path.is_file():
            raise ProspectiveFreezeDataError(
                f"missing prospective freeze artifact or hash: {path}"
            )
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ProspectiveFreezeDataError(
                f"prospective freeze artifact hash mismatch for {path}: "
                f"expected {expected}, got {actual}"
            )
        output_hashes[name] = actual
    input_hashes = manifest.get("input_sha256")
    if not isinstance(input_hashes, Mapping) or not input_hashes:
        raise ProspectiveFreezeDataError(
            "prospective freeze manifest has no parent input hashes"
        )
    scoring_contract = manifest.get("scoring_contract")
    if scoring_contract != SCORING_CONTRACT:
        raise ProspectiveFreezeDataError(
            "prospective freeze scoring contract is missing or unsupported"
        )
    correction_notice = manifest.get("correction_notice")
    if correction_notice != CORRECTION_NOTICE:
        raise ProspectiveFreezeDataError(
            "prospective freeze correction notice is missing or unsupported"
        )
    try:
        season = _integer(manifest.get("season"), "prospective freeze season")
        cutoff = _parse_date(
            str(manifest.get("forecast_cutoff") or ""), "forecast cutoff"
        )
        first_game = _parse_date(
            str(manifest.get("first_scheduled_game") or ""),
            "first scheduled game",
        )
    except ProspectiveFreezeDataError:
        raise
    if cutoff >= first_game:
        raise ProspectiveFreezeDataError(
            "prospective freeze cutoff is not before the first scheduled game"
        )
    fingerprint_payload = json.dumps(
        {
            "model_version": MODEL_VERSION,
            "season": season,
            "cutoff": cutoff.isoformat(),
            "first_scheduled_game": first_game.isoformat(),
            "input_hashes": dict(sorted(input_hashes.items())),
            "output_hashes": dict(sorted(output_hashes.items())),
            "scoring_contract": scoring_contract,
            "correction_notice": correction_notice,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    actual_fingerprint = hashlib.sha256(fingerprint_payload).hexdigest()
    declared_fingerprint = str(manifest.get("freeze_fingerprint") or "")
    if actual_fingerprint != declared_fingerprint:
        raise ProspectiveFreezeDataError(
            "prospective freeze fingerprint does not match its declared content"
        )
    if (
        expected_fingerprint is not None
        and actual_fingerprint != expected_fingerprint
    ):
        raise ProspectiveFreezeDataError(
            "prospective freeze fingerprint does not match the pinned identity"
        )
    return manifest


def write_prospective_freeze(
    result: ProspectiveFreezeResult, root: str | Path
) -> Path:
    """Atomically publish an immutable preseason forecast bundle."""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    parent = Path(root) / "prospective_freeze" / str(result.season)
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"prospective freeze exists: {destination}")
    artifacts = {
        name: {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "fields": list(result.artifact_fields[name]),
        }
        for name, raw in result.artifacts.items()
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "model_status": MODEL_STATUS,
        "season": result.season,
        "forecast_cutoff": result.cutoff.isoformat(),
        "first_scheduled_game": result.first_scheduled_game.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z"),
        "freeze_fingerprint": result.freeze_fingerprint,
        "scope": (
            "issued team environment, player opportunity, availability, and named "
            "high-value opportunity forecasts; no efficiency, touchdowns, fantasy "
            "points, or retrospective outcomes"
        ),
        "methodology": {
            "temporal_gate": "every selected source date is on or before the cutoff, which must precede the first scheduled game",
            "immutability": "future evaluation must verify this manifest and consume these copied forecast bytes rather than rebuild them",
            "role_evidence": "review status is joined for qualification only; numeric overrides remain forbidden",
            "market_data": "fantasy ADP remains metadata and is not the football projection",
        },
        "correction_notice": CORRECTION_NOTICE,
        "scoring_contract": SCORING_CONTRACT,
        "inputs": result.component_inputs,
        "input_sha256": dict(result.input_hashes),
        "quality": dict(result.quality),
        "artifacts": artifacts,
    }
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
    try:
        for name, raw in result.artifacts.items():
            (staging / name).write_bytes(raw)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staging.rename(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
