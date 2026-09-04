"""Audit current-role research against flagged high-value opportunity priors.

This layer is deliberately non-modeling.  It joins dated, source-backed role claims
to the automated exception queue, preserves unresolved cases, and refuses manual
numeric overrides.  A future evidence-to-prior rule must earn promotion in a
time-correct backtest before it can change an opportunity estimate.
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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse


SCHEMA_VERSION = "1.0.0"
MODEL_VERSION = "current-role-research-audit-v0.1.0"
HIGH_VALUE_VOLUME_MODEL_VERSION = "high-value-event-pool-v0.3.0"
ALLOWED_REVIEW_STATUSES = {
    "reviewed_model_retained",
    "reviewed_inconclusive_model_retained",
    "reviewed_role_conflict_model_retained",
}
ALLOWED_EVIDENCE_STRENGTHS = {
    "direct_current_role",
    "indirect_current_role",
    "context_only",
}

SOURCE_FIELDS = (
    "source_id", "title", "publisher", "source_type", "url",
    "published_at", "accessed_at",
)
PLAYER_REVIEW_FIELDS = (
    "queue_rank", "season", "team", "position", "metric", "base_resource",
    "gsis_id", "player_name", "current_status", "ffc_adp",
    "availability_adjusted_season_expected_events",
    "season_marginal_scenario_envelope_low",
    "season_marginal_scenario_envelope_high", "metric_history_support",
    "historical_metric_base_opportunities", "automated_review_issues",
    "review_status", "evidence_record_id", "evidence_strength",
    "evidence_as_of", "role_claim", "model_implication",
    "remaining_uncertainty", "source_ids", "numeric_override_applied",
)
TEAM_REVIEW_FIELDS = (
    "season", "team", "position", "metric", "issue",
    "training_team_base_opportunities", "primary_rate", "diagnostic_raw_rate",
    "conformal_rate_radius", "automated_details", "review_status",
    "evidence_record_id", "evidence_strength", "evidence_as_of", "role_claim",
    "model_implication", "remaining_uncertainty", "source_ids",
    "numeric_override_applied",
)
COVERAGE_FIELDS = (
    "scope", "metric", "queued_rows", "evidence_reviewed_rows",
    "resolved_model_retained_rows", "inconclusive_rows", "unreviewed_rows",
    "review_coverage",
)


class RoleResearchDataError(ValueError):
    """Raised when role research cannot be joined without ambiguity."""


@dataclass(frozen=True)
class RoleResearchResult:
    season: int
    as_of: date
    high_value_volumes_path: Path
    evidence_path: Path
    input_hashes: Mapping[str, str]
    source_rows: tuple[Mapping[str, Any], ...]
    player_review_rows: tuple[Mapping[str, Any], ...]
    team_review_rows: tuple[Mapping[str, Any], ...]
    coverage_rows: tuple[Mapping[str, Any], ...]


def _read_manifest(root: Path) -> tuple[bytes, Mapping[str, Any]]:
    path = root / "manifest.json"
    if not path.is_file():
        raise RoleResearchDataError(f"missing input manifest: {path}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RoleResearchDataError(f"input manifest is not valid JSON: {path}") from error
    if not isinstance(value, Mapping):
        raise RoleResearchDataError(f"input manifest is not an object: {path}")
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
    if not isinstance(metadata, Mapping) or not metadata.get("sha256"):
        raise RoleResearchDataError(f"manifest does not describe {filename}: {root}")
    path = root / filename
    if not path.is_file():
        raise RoleResearchDataError(f"input does not exist: {path}")
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != metadata["sha256"]:
        raise RoleResearchDataError(
            f"input hash mismatch for {path}: expected {metadata['sha256']}, got {actual}"
        )
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        fields = set(reader.fieldnames or ())
        rows = list(reader)
    except UnicodeDecodeError as error:
        raise RoleResearchDataError(f"input is not UTF-8 CSV: {path}") from error
    missing = required - fields
    if missing or (not rows and not allow_empty):
        raise RoleResearchDataError(
            f"{path} is empty or missing fields {sorted(missing)}"
        )
    return raw, rows


def _text(value: Any, context: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise RoleResearchDataError(f"{context} must be nonempty")
    return result


def _number(value: Any, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise RoleResearchDataError(f"{context} must be numeric") from error
    if not math.isfinite(result) or result < 0:
        raise RoleResearchDataError(f"{context} must be finite and nonnegative")
    return result


def _date(value: Any, context: str) -> date:
    try:
        return date.fromisoformat(_text(value, context))
    except ValueError as error:
        raise RoleResearchDataError(f"{context} must be an ISO date") from error


def _load_evidence(
    path: Path,
    *,
    season: int,
) -> tuple[
    bytes,
    date,
    tuple[dict[str, str], ...],
    list[Mapping[str, Any]],
    list[Mapping[str, Any]],
]:
    raw = path.read_bytes()
    try:
        root = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RoleResearchDataError(f"invalid role evidence JSON: {path}") from error
    if not isinstance(root, Mapping) or not str(root.get("schema_version", "")).startswith("1."):
        raise RoleResearchDataError("role evidence must use schema version 1.x")
    if root.get("numeric_override_policy") != "forbidden_until_time_correct_validation":
        raise RoleResearchDataError("role evidence must forbid unvalidated numeric overrides")
    if root.get("season") != season:
        raise RoleResearchDataError("role evidence season does not match opportunity snapshot")
    as_of = _date(root.get("as_of"), "role evidence as_of")

    sources = root.get("sources")
    if not isinstance(sources, list) or not sources:
        raise RoleResearchDataError("role evidence sources must be a nonempty list")
    source_ids: set[str] = set()
    source_rows: list[dict[str, str]] = []
    for source in sources:
        if not isinstance(source, Mapping):
            raise RoleResearchDataError("each role evidence source must be an object")
        source_id = _text(source.get("id"), "source id")
        if source_id in source_ids:
            raise RoleResearchDataError(f"duplicate source id {source_id}")
        source_ids.add(source_id)
        url = _text(source.get("url"), f"source {source_id} URL")
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise RoleResearchDataError(f"source {source_id} has an invalid URL")
        published = str(source.get("published_at") or "").strip()
        accessed = str(source.get("accessed_at") or "").strip()
        if published:
            _date(published, f"source {source_id} published_at")
        if not accessed:
            raise RoleResearchDataError(f"source {source_id} needs accessed_at")
        _date(accessed, f"source {source_id} accessed_at")
        source_rows.append({
            "source_id": source_id,
            "title": _text(source.get("title"), f"source {source_id} title"),
            "publisher": _text(source.get("publisher"), f"source {source_id} publisher"),
            "source_type": _text(source.get("source_type"), f"source {source_id} type"),
            "url": url,
            "published_at": published,
            "accessed_at": accessed,
        })

    player_records = root.get("player_records", [])
    team_records = root.get("team_records", [])
    if not isinstance(player_records, list) or not isinstance(team_records, list):
        raise RoleResearchDataError("player_records and team_records must be lists")
    record_ids: set[str] = set()
    for record_type, records in (("player", player_records), ("team", team_records)):
        for record in records:
            if not isinstance(record, Mapping):
                raise RoleResearchDataError(f"each {record_type} record must be an object")
            record_id = _text(record.get("id"), f"{record_type} record id")
            if record_id in record_ids:
                raise RoleResearchDataError(f"duplicate evidence record id {record_id}")
            record_ids.add(record_id)
            status = _text(record.get("review_status"), f"record {record_id} review_status")
            if status not in ALLOWED_REVIEW_STATUSES:
                raise RoleResearchDataError(f"record {record_id} has unsupported review status")
            strength = _text(
                record.get("evidence_strength"), f"record {record_id} evidence_strength"
            )
            if strength not in ALLOWED_EVIDENCE_STRENGTHS:
                raise RoleResearchDataError(f"record {record_id} has unsupported evidence strength")
            if record.get("numeric_override_applied") is not False:
                raise RoleResearchDataError(
                    f"record {record_id} attempts an unvalidated numeric override"
                )
            refs = record.get("source_ids")
            if not isinstance(refs, list) or not refs or any(ref not in source_ids for ref in refs):
                raise RoleResearchDataError(f"record {record_id} has invalid source references")
            for field in ("claim", "model_implication", "remaining_uncertainty"):
                _text(record.get(field), f"record {record_id} {field}")
    return raw, as_of, tuple(source_rows), player_records, team_records


def _evidence_columns(record: Mapping[str, Any] | None, as_of: date) -> dict[str, str]:
    if record is None:
        return {
            "review_status": "unreviewed",
            "evidence_record_id": "",
            "evidence_strength": "",
            "evidence_as_of": "",
            "role_claim": "",
            "model_implication": "research before changing the frozen estimate",
            "remaining_uncertainty": "current role has not been source-reviewed",
            "source_ids": "",
            "numeric_override_applied": "false",
        }
    return {
        "review_status": str(record["review_status"]),
        "evidence_record_id": str(record["id"]),
        "evidence_strength": str(record["evidence_strength"]),
        "evidence_as_of": as_of.isoformat(),
        "role_claim": str(record["claim"]),
        "model_implication": str(record["model_implication"]),
        "remaining_uncertainty": str(record["remaining_uncertainty"]),
        "source_ids": "|".join(str(value) for value in record["source_ids"]),
        "numeric_override_applied": "false",
    }


def _coverage_row(
    scope: str,
    metric: str,
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    selected = list(rows)
    reviewed = sum(row["review_status"] != "unreviewed" for row in selected)
    inconclusive = sum(
        row["review_status"] == "reviewed_inconclusive_model_retained"
        for row in selected
    )
    resolved = reviewed - inconclusive
    total = len(selected)
    return {
        "scope": scope,
        "metric": metric,
        "queued_rows": total,
        "evidence_reviewed_rows": reviewed,
        "resolved_model_retained_rows": resolved,
        "inconclusive_rows": inconclusive,
        "unreviewed_rows": total - reviewed,
        "review_coverage": f"{reviewed / total:.9f}" if total else "1.000000000",
    }


def build_role_research_audit(
    high_value_volumes: str | Path,
    evidence_path: str | Path,
) -> RoleResearchResult:
    """Join reviewed current-role evidence to automated player/team exceptions."""

    volume_root = Path(high_value_volumes)
    evidence_file = Path(evidence_path)
    manifest_raw, manifest = _read_manifest(volume_root)
    if manifest.get("model_version") != HIGH_VALUE_VOLUME_MODEL_VERSION:
        raise RoleResearchDataError("unsupported high-value volume model version")
    season = int(manifest.get("season"))
    supported = tuple(manifest.get("supported_metrics") or ())
    if not supported:
        raise RoleResearchDataError("opportunity snapshot has no supported metrics")
    player_raw, players = _verified_csv(
        volume_root,
        manifest,
        "player_high_value_opportunities.csv",
        {"season", "team", "position", "metric", "base_resource", "gsis_id",
         "player_name", "current_status", "ffc_adp",
         "availability_adjusted_season_expected_events",
         "season_marginal_scenario_envelope_low",
         "season_marginal_scenario_envelope_high", "metric_history_support",
         "historical_metric_base_opportunities", "requires_current_role_review",
         "current_role_review_issues"},
    )
    team_raw, team_reviews = _verified_csv(
        volume_root,
        manifest,
        "source_review.csv",
        {"season", "team", "position", "metric", "issue",
         "training_team_base_opportunities", "primary_rate", "diagnostic_raw_rate",
         "conformal_rate_radius", "details"},
        allow_empty=True,
    )
    evidence_raw, as_of, sources, player_records, team_records = _load_evidence(
        evidence_file, season=season
    )

    flagged: dict[tuple[str, str, str], Mapping[str, str]] = {}
    for row in players:
        if int(row["season"]) != season:
            raise RoleResearchDataError("player opportunity rows mix seasons")
        key = row["team"], row["metric"], row["gsis_id"]
        if key in flagged and row["requires_current_role_review"] == "true":
            raise RoleResearchDataError(f"duplicate flagged player/metric row {key}")
        if row["requires_current_role_review"] == "true":
            if not row["current_role_review_issues"]:
                raise RoleResearchDataError(f"flagged player/metric row has no reason {key}")
            flagged[key] = row

    player_evidence: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for record in player_records:
        team = _text(record.get("team"), f"record {record['id']} team")
        player_id = _text(record.get("gsis_id"), f"record {record['id']} GSIS ID")
        position = _text(record.get("position"), f"record {record['id']} position")
        player_name = _text(record.get("player_name"), f"record {record['id']} player_name")
        metrics = record.get("metrics")
        if not isinstance(metrics, list) or not metrics:
            raise RoleResearchDataError(f"record {record['id']} needs metrics")
        for metric in metrics:
            if metric not in supported:
                raise RoleResearchDataError(f"record {record['id']} has unsupported metric {metric}")
            key = team, str(metric), player_id
            target = flagged.get(key)
            if target is None:
                raise RoleResearchDataError(
                    f"record {record['id']} does not match a flagged player/metric row {key}"
                )
            if target["position"] != position or target["player_name"] != player_name:
                raise RoleResearchDataError(f"record {record['id']} player identity mismatch")
            if key in player_evidence:
                raise RoleResearchDataError(f"multiple evidence records target {key}")
            player_evidence[key] = record

    team_targets: dict[tuple[str, str, str], Mapping[str, str]] = {}
    for row in team_reviews:
        if int(row["season"]) != season:
            raise RoleResearchDataError("team review rows mix seasons")
        key = row["team"], row["metric"], row["issue"]
        if key in team_targets:
            raise RoleResearchDataError(f"duplicate team review row {key}")
        team_targets[key] = row
    team_evidence: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for record in team_records:
        key = (
            _text(record.get("team"), f"record {record['id']} team"),
            _text(record.get("metric"), f"record {record['id']} metric"),
            _text(record.get("issue"), f"record {record['id']} issue"),
        )
        if key not in team_targets:
            raise RoleResearchDataError(
                f"record {record['id']} does not match a team-rate review row {key}"
            )
        if key in team_evidence:
            raise RoleResearchDataError(f"multiple evidence records target {key}")
        team_evidence[key] = record

    ordered_players = sorted(
        flagged.values(),
        key=lambda row: (
            -_number(
                row["availability_adjusted_season_expected_events"],
                f"{row['player_name']} expected events",
            ),
            row["team"], row["metric"], row["gsis_id"],
        ),
    )
    player_rows: list[dict[str, Any]] = []
    for rank, row in enumerate(ordered_players, start=1):
        key = row["team"], row["metric"], row["gsis_id"]
        player_rows.append({
            "queue_rank": rank,
            "season": season,
            "team": row["team"],
            "position": row["position"],
            "metric": row["metric"],
            "base_resource": row["base_resource"],
            "gsis_id": row["gsis_id"],
            "player_name": row["player_name"],
            "current_status": row["current_status"],
            "ffc_adp": row["ffc_adp"],
            "availability_adjusted_season_expected_events": row[
                "availability_adjusted_season_expected_events"
            ],
            "season_marginal_scenario_envelope_low": row[
                "season_marginal_scenario_envelope_low"
            ],
            "season_marginal_scenario_envelope_high": row[
                "season_marginal_scenario_envelope_high"
            ],
            "metric_history_support": row["metric_history_support"],
            "historical_metric_base_opportunities": row[
                "historical_metric_base_opportunities"
            ],
            "automated_review_issues": row["current_role_review_issues"],
            **_evidence_columns(player_evidence.get(key), as_of),
        })

    team_rows: list[dict[str, Any]] = []
    for key, row in sorted(team_targets.items()):
        team_rows.append({
            "season": season,
            "team": row["team"],
            "position": row["position"],
            "metric": row["metric"],
            "issue": row["issue"],
            "training_team_base_opportunities": row["training_team_base_opportunities"],
            "primary_rate": row["primary_rate"],
            "diagnostic_raw_rate": row["diagnostic_raw_rate"],
            "conformal_rate_radius": row["conformal_rate_radius"],
            "automated_details": row["details"],
            **_evidence_columns(team_evidence.get(key), as_of),
        })

    coverage_rows = [_coverage_row("player", "ALL", player_rows)]
    for metric in supported:
        coverage_rows.append(_coverage_row(
            "player", metric, (row for row in player_rows if row["metric"] == metric)
        ))
    coverage_rows.append(_coverage_row("team_rate", "ALL", team_rows))
    for metric in supported:
        selected = [row for row in team_rows if row["metric"] == metric]
        if selected:
            coverage_rows.append(_coverage_row("team_rate", metric, selected))

    return RoleResearchResult(
        season=season,
        as_of=as_of,
        high_value_volumes_path=volume_root,
        evidence_path=evidence_file,
        input_hashes={
            "high_value_volumes_manifest.json": hashlib.sha256(manifest_raw).hexdigest(),
            "player_high_value_opportunities.csv": hashlib.sha256(player_raw).hexdigest(),
            "high_value_volume_source_review.csv": hashlib.sha256(team_raw).hexdigest(),
            "player_role_evidence.json": hashlib.sha256(evidence_raw).hexdigest(),
        },
        source_rows=tuple(sorted(sources, key=lambda row: row["source_id"])),
        player_review_rows=tuple(player_rows),
        team_review_rows=tuple(team_rows),
        coverage_rows=tuple(coverage_rows),
    )


def _csv_bytes(fields: tuple[str, ...], rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def write_role_research_snapshot(
    result: RoleResearchResult,
    root: str | Path,
) -> Path:
    """Atomically publish the current-role evidence audit and unresolved queue."""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    parent = Path(root) / "role_research" / str(result.season)
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"role research snapshot exists: {destination}")
    artifacts = {
        "evidence_sources.csv": _csv_bytes(SOURCE_FIELDS, result.source_rows),
        "player_review_queue.csv": _csv_bytes(
            PLAYER_REVIEW_FIELDS, result.player_review_rows
        ),
        "team_rate_review_queue.csv": _csv_bytes(
            TEAM_REVIEW_FIELDS, result.team_review_rows
        ),
        "review_coverage.csv": _csv_bytes(COVERAGE_FIELDS, result.coverage_rows),
    }
    fields = {
        "evidence_sources.csv": SOURCE_FIELDS,
        "player_review_queue.csv": PLAYER_REVIEW_FIELDS,
        "team_rate_review_queue.csv": TEAM_REVIEW_FIELDS,
        "review_coverage.csv": COVERAGE_FIELDS,
    }
    player_reviewed = sum(
        row["review_status"] != "unreviewed" for row in result.player_review_rows
    )
    player_inconclusive = sum(
        row["review_status"] == "reviewed_inconclusive_model_retained"
        for row in result.player_review_rows
    )
    team_reviewed = sum(
        row["review_status"] != "unreviewed" for row in result.team_review_rows
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "season": result.season,
        "as_of": result.as_of.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        ),
        "scope": (
            "source-backed review status for automated current-player and team-rate "
            "exceptions; opportunity estimates are copied unchanged"
        ),
        "policy": {
            "numeric_override": "forbidden until an evidence-to-prior rule passes a time-correct validation gate",
            "official_depth_chart": "current role evidence but explicitly unofficial where the club labels it so",
            "camp_report": "context only unless a repeatable, validated translation to regular-season role exists",
            "unreviewed": "remains visibly queued and cannot be represented as current-role certainty",
        },
        "inputs": {
            "high_value_volumes": str(result.high_value_volumes_path),
            "evidence": str(result.evidence_path),
            "sha256": dict(result.input_hashes),
        },
        "quality": {
            "evidence_source_count": len(result.source_rows),
            "player_review_queue_rows": len(result.player_review_rows),
            "player_evidence_reviewed_rows": player_reviewed,
            "player_resolved_model_retained_rows": player_reviewed - player_inconclusive,
            "player_inconclusive_rows": player_inconclusive,
            "player_unreviewed_rows": len(result.player_review_rows) - player_reviewed,
            "team_rate_review_queue_rows": len(result.team_review_rows),
            "team_rate_evidence_reviewed_rows": team_reviewed,
            "numeric_overrides_applied": 0,
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
