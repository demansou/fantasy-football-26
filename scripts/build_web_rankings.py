#!/usr/bin/env python3
"""Build the static draft-board ranking dataset from pinned 2026 snapshots."""

from __future__ import annotations

import csv
import argparse
import hashlib
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from fantasy_draft.prospective import verify_prospective_freeze


REPO_ROOT = Path(__file__).resolve().parents[1]
FREEZE = REPO_ROOT / "data/derived/prospective_freeze/2026/20260903T133149.697043Z"
FFC_ROOT = REPO_ROOT / "data/raw/fantasy_football_calculator/adp/2026"
OUTPUT = REPO_ROOT / "web/data/players.ts"
EXPECTED_FREEZE_FINGERPRINT = "f16a467087044aa6f4f1385ca8bc4eb86c51a287c13dfe1e3dca08349b96f115"
SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def percentile_map(values: dict[str, float]) -> dict[str, float]:
    """Return deterministic 0-100 within-group percentile ranks."""

    ordered = sorted(values.items(), key=lambda item: (item[1], item[0]))
    if len(ordered) <= 1:
        return {key: 50.0 for key, _ in ordered}
    return {
        key: round(index / (len(ordered) - 1) * 100, 1)
        for index, (key, _) in enumerate(ordered)
    }


def latest_ffc_snapshot() -> Path:
    snapshots = sorted(path for path in FFC_ROOT.iterdir() if path.is_dir())
    if not snapshots:
        raise RuntimeError("no 2026 FFC ADP snapshot is available")
    return snapshots[-1]


def verify_ffc_snapshot(snapshot: Path, *, as_of: date, max_age_days: int) -> dict[str, object]:
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("query") != {"scoring": "ppr", "season": 2026, "teams": 10}:
        raise RuntimeError("FFC snapshot is not the pinned 2026 10-team PPR query")
    normalized = manifest["artifacts"]["normalized"]
    actual = hashlib.sha256((snapshot / normalized["path"]).read_bytes()).hexdigest()
    if actual != normalized["sha256"]:
        raise RuntimeError("FFC ADP snapshot hash mismatch")
    source_end = date.fromisoformat(manifest["source_snapshot"]["end_date"])
    age_days = (as_of - source_end).days
    if age_days < 0:
        raise RuntimeError("FFC snapshot source window ends after the ranking as-of date")
    if age_days > max_age_days:
        raise RuntimeError(
            f"FFC ADP is stale: {age_days} days old, maximum is {max_age_days}; fetch a new snapshot"
        )
    quality = manifest.get("quality", {})
    if quality.get("record_count") != 264 or quality.get("duplicate_source_ids") != 0:
        raise RuntimeError("FFC ADP coverage is incomplete or contains duplicate player IDs")
    expected_positions = {"DST": 27, "K": 21, "QB": 31, "RB": 70, "TE": 26, "WR": 89}
    if quality.get("position_counts") != expected_positions:
        raise RuntimeError("FFC ADP position coverage differs from the reviewed snapshot")
    manifest["verified_age_days"] = age_days
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--max-adp-age-days", type=int, default=4)
    parser.add_argument("--check", action="store_true", help="fail if the generated web file differs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    freeze_manifest = verify_prospective_freeze(
        FREEZE, expected_fingerprint=EXPECTED_FREEZE_FINGERPRINT
    )
    ffc_snapshot = latest_ffc_snapshot()
    ffc_manifest = verify_ffc_snapshot(
        ffc_snapshot, as_of=args.as_of, max_age_days=args.max_adp_age_days
    )
    adp_rows = read_csv(ffc_snapshot / "adp.csv")

    weekly = [
        row
        for row in read_csv(FREEZE / "weekly_role_forecasts.csv")
        if row["scheduled_game"] == "true" and row["ffc_source_player_id"]
    ]
    environments = {
        (row["team"], row["position"]): row
        for row in read_csv(FREEZE / "position_environments.csv")
    }
    team_systems = {
        row["team"]: row for row in read_csv(FREEZE / "team_systems.csv")
    }
    candidates = [
        row
        for row in read_csv(FREEZE / "player_role_candidates.csv")
        if row["ffc_source_player_id"]
    ]
    high_value_rows = [
        row
        for row in read_csv(FREEZE / "player_high_value_opportunities.csv")
        if row["ffc_source_player_id"]
    ]

    resource_totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    scheduled_weeks: dict[str, set[str]] = defaultdict(set)
    status_by_id: dict[str, str] = {}
    active_by_id: dict[str, bool] = {}
    gsis_by_id: dict[str, str] = {}
    for row in weekly:
        player_id = row["ffc_source_player_id"]
        resource_totals[player_id][row["resource"]] += float(row["expected_opportunities_this_week"])
        scheduled_weeks[player_id].add(row["week"])
        status_by_id[player_id] = row["current_status"]
        gsis_by_id[player_id] = row["gsis_id"].strip()

    evidence_values: dict[str, list[float]] = defaultdict(list)
    for row in candidates:
        player_id = row["ffc_source_player_id"]
        evidence_values[player_id].append(float(row["role_evidence_score_v0"]))
        active_by_id[player_id] = row["current_active"] == "true"

    opportunity_raw: dict[str, dict[str, float]] = defaultdict(dict)
    for row in adp_rows:
        player_id, position = row["source_player_id"], row["position"]
        totals = resource_totals[player_id]
        if position == "QB":
            value = totals["QB_DROPBACKS"] + 2 * totals["QB_RUSH_OPPORTUNITIES"]
        elif position == "RB":
            value = totals["RB_CARRIES"] + 2 * totals["RB_TARGETS"]
        elif position in {"WR", "TE"}:
            value = totals[f"{position}_TARGETS"]
        else:
            continue
        opportunity_raw[position][player_id] = value

    opportunity_scores: dict[str, float] = {}
    for values in opportunity_raw.values():
        opportunity_scores.update(percentile_map(values))

    hv_by_metric: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for row in high_value_rows:
        hv_by_metric[(row["position"], row["metric"])][row["ffc_source_player_id"]] = float(
            row["availability_adjusted_season_expected_events"]
        )
    hv_percentiles: dict[str, list[float]] = defaultdict(list)
    for values in hv_by_metric.values():
        for player_id, score in percentile_map(values).items():
            hv_percentiles[player_id].append(score)

    players: list[dict[str, object]] = []
    for adp_rank, row in enumerate(sorted(adp_rows, key=lambda item: float(item["adp"])), 1):
        player_id, position, team = row["source_player_id"], row["position"], row["team"]
        adp = float(row["adp"])
        market_base = 100 - 0.35 * (adp - 1)
        coverage = "modeled" if position in SKILL_POSITIONS and player_id in opportunity_scores else "market_only"
        environment = environments.get((team, position))
        team_system = team_systems.get(team)
        opportunity = opportunity_scores.get(player_id, 50.0)
        high_value = (
            round(sum(hv_percentiles[player_id]) / len(hv_percentiles[player_id]), 1)
            if hv_percentiles[player_id]
            else 50.0
        )
        role_evidence = (
            round(sum(evidence_values[player_id]) / len(evidence_values[player_id]), 1)
            if evidence_values[player_id]
            else 50.0
        )
        environment_score = float(environment["ranking_score_v1"]) if environment else 50.0
        adjustment = 0.0
        if coverage == "modeled":
            adjustment = (
                0.08 * (opportunity - 50)
                + 0.04 * (high_value - 50)
                + 0.03 * (environment_score - 50)
                + 0.015 * (role_evidence - 50)
            )

        totals = resource_totals[player_id]
        games = max(1, len(scheduled_weeks[player_id]))
        if position == "QB" and coverage == "modeled":
            summary = f'{totals["QB_DROPBACKS"] / games:.1f} DB + {totals["QB_RUSH_OPPORTUNITIES"] / games:.1f} rush/g'
        elif position == "RB" and coverage == "modeled":
            summary = f'{totals["RB_CARRIES"] / games:.1f} carries + {totals["RB_TARGETS"] / games:.1f} targets/g'
        elif position in {"WR", "TE"} and coverage == "modeled":
            summary = f'{totals[f"{position}_TARGETS"] / games:.1f} targets/g'
        else:
            summary = "Market-only ranking"

        environment_rank = int(environment["league_rank"]) if environment else None
        play_caller = team_system["play_caller"] if team_system and position in SKILL_POSITIONS else None
        style_evidence = (
            float(team_system["exact_style_certainty_v0"])
            if team_system and position in SKILL_POSITIONS
            else None
        )
        style_evidence_label = (
            team_system["exact_style_certainty_label"]
            if team_system and position in SKILL_POSITIONS
            else None
        )
        context = (
            f"{summary} · {play_caller} · style evidence {style_evidence:.0f}/100"
            if play_caller and style_evidence is not None
            else f"{summary} · {team} {position} environment #{environment_rank}"
            if environment_rank
            else summary
        )
        players.append(
            {
                "id": f"{position.lower()}-{player_id}",
                "sourceId": player_id,
                "gsisId": gsis_by_id.get(player_id) or None,
                "name": row["name"],
                "position": position,
                "team": team,
                "bye": int(row["bye_week"]),
                "adp": adp,
                "adpStdev": float(row["adp_stdev"]),
                "marketHighPick": int(row["high_pick"]),
                "marketLowPick": int(row["low_pick"]),
                "timesDrafted": int(row["times_drafted"]),
                "adpRank": adp_rank,
                "draftScore": round(market_base + adjustment, 2),
                "marketBase": round(market_base, 2),
                "tier": 0,
                "context": context,
                "playCaller": play_caller,
                "styleEvidence": style_evidence,
                "styleEvidenceLabel": style_evidence_label,
                "coverage": coverage,
                "status": status_by_id.get(player_id, "MARKET"),
                "currentActive": active_by_id.get(player_id, True),
                "metrics": {
                    "opportunity": opportunity,
                    "highValue": high_value,
                    "environment": round(environment_score, 1),
                    "roleEvidence": role_evidence,
                },
            }
        )

    players.sort(key=lambda item: (-float(item["draftScore"]), float(item["adp"]), str(item["id"])))
    tier_cutoffs = {
        "QB": (5, 12, 20), "RB": (12, 30, 50), "WR": (12, 30, 55),
        "TE": (5, 12, 20), "K": (8, 16, 24), "DST": (8, 16, 24),
    }
    position_ranks: dict[str, int] = defaultdict(int)
    for model_rank, player in enumerate(players, 1):
        position = str(player["position"])
        position_ranks[position] += 1
        position_rank = position_ranks[position]
        cutoffs = tier_cutoffs[position]
        player["modelRank"] = model_rank
        player["positionRank"] = position_rank
        player["rankDelta"] = int(player["adpRank"]) - model_rank
        player["tier"] = 1 + sum(position_rank > cutoff for cutoff in cutoffs)

    metadata = {
        "season": 2026,
        "generatedFrom": "verified pinned snapshots",
        "freezeCutoff": freeze_manifest["forecast_cutoff"],
        "freezeFingerprint": freeze_manifest["freeze_fingerprint"],
        "freezeModel": freeze_manifest["model_version"],
        "ffcWindow": f'{ffc_manifest["source_snapshot"]["start_date"]} to {ffc_manifest["source_snapshot"]["end_date"]}',
        "ffcDrafts": ffc_manifest["source_snapshot"]["total_drafts"],
        "ffcAgeDays": ffc_manifest["verified_age_days"],
        "freshnessStatus": "fresh",
        "playerCount": len(players),
        "modeledPlayerCount": sum(player["coverage"] == "modeled" for player in players),
        "method": "Market ADP plus within-position opportunity, high-value usage, team environment, and role-evidence adjustments; no efficiency, touchdown, or fantasy-point projection.",
    }
    source = """// Generated by scripts/build_web_rankings.py. Do not edit by hand.\n\n"""
    source += "export const RANKING_METADATA = " + json.dumps(metadata, indent=2) + " as const;\n\n"
    source += "export const PLAYERS = " + json.dumps(players, indent=2) + " as const;\n"
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != source:
            raise RuntimeError("web ranking artifact is not synchronized with verified inputs")
        print(f"Verified {OUTPUT} is synchronized with fresh inputs")
        return
    OUTPUT.write_text(source, encoding="utf-8")
    print(f"Wrote {len(players)} rankings ({metadata['modeledPlayerCount']} model-backed) to {OUTPUT}")


if __name__ == "__main__":
    main()
