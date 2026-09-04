"""Team-level offensive opportunity environments by fantasy position.

This is the bridge between a team style forecast and eventual player roles.  It
does not know who wins a depth-chart job, how efficient a player will be, or how
healthy the roster is.  It therefore ranks only the opportunity pool a QB, RB,
WR, or TE room may receive from coaching style and expected team volume.
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


SCHEMA_VERSION = "1.2.0"
MODEL_VERSION = "position-opportunity-environment-v0.3.0"
MODEL_STATUS = "team_opportunity_watch_score_not_resource_calibration"
POSITIONS = ("QB", "RB", "WR", "TE")
REQUIRED_METRICS = {
    "plays_per_game",
    "pass_rate",
    "neutral_early_down_pass_rate",
    "play_action_rate",
    "mean_air_yards",
    "rb_target_share",
    "wr_target_share",
    "te_target_share",
}

FIELDS = (
    "season",
    "team",
    "position",
    "raw_opportunity_score_v0",
    "certainty_adjusted_score_v0",
    "ranking_score_v1",
    "ranking_policy",
    "opportunity_label",
    "league_rank",
    "team_exact_style_certainty_v0",
    "forecast_plays_per_game",
    "forecast_pass_plays_per_game",
    "forecast_rush_plays_per_game",
    "position_target_share",
    "mean_air_yards",
    "primary_drivers",
    "scope_warning",
    "model_status",
)


class PositionEnvironmentDataError(ValueError):
    """Raised when caller-fingerprint outputs cannot support the position join."""


@dataclass(frozen=True)
class PositionEnvironmentResult:
    season: int
    source_teams_path: Path
    source_metrics_path: Path
    source_teams_sha256: str
    source_metrics_sha256: str
    rows: tuple[Mapping[str, Any], ...]


def _resolve(path: str | Path, filename: str) -> Path:
    resolved = Path(path)
    if resolved.is_dir():
        resolved = resolved / filename
    if not resolved.is_file():
        raise PositionEnvironmentDataError(f"input does not exist: {resolved}")
    return resolved


def _rows(path: Path, required: set[str]) -> tuple[bytes, list[dict[str, str]]]:
    raw = path.read_bytes()
    try:
        values = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    except UnicodeDecodeError as error:
        raise PositionEnvironmentDataError(f"CSV is not UTF-8: {path}") from error
    if not values or not required.issubset(values[0]):
        raise PositionEnvironmentDataError(f"CSV has no rows or required fields: {path}")
    return raw, values


def _number(value: str, context: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise PositionEnvironmentDataError(f"{context} must be numeric") from error
    if not math.isfinite(parsed):
        raise PositionEnvironmentDataError(f"{context} must be finite")
    return parsed


def _percentiles(values: Mapping[str, float]) -> dict[str, float]:
    """Return average-rank percentiles in [0, 1], with 0.5 for a singleton."""

    if len(values) == 1:
        return {next(iter(values)): 0.5}
    ordered = sorted(values.items(), key=lambda item: item[1])
    result: dict[str, float] = {}
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        average_rank = (start + end - 1) / 2
        percentile = average_rank / (len(ordered) - 1)
        for index in range(start, end):
            result[ordered[index][0]] = percentile
        start = end
    return result


def _label(score: float) -> str:
    if score >= 80:
        return "strongly_favorable_opportunity"
    if score >= 65:
        return "favorable_opportunity"
    if score > 35:
        return "neutral_opportunity"
    if score > 20:
        return "unfavorable_opportunity"
    return "strongly_unfavorable_opportunity"


def build_position_environments(
    caller_fingerprint_snapshot: str | Path,
) -> PositionEnvironmentResult:
    root = Path(caller_fingerprint_snapshot)
    teams_path = _resolve(root, "teams.csv")
    metrics_path = _resolve(root, "metric_forecasts.csv")
    teams_raw, team_input = _rows(
        teams_path,
        {"season", "team", "exact_style_certainty_v0", "model_status"},
    )
    metrics_raw, metric_input = _rows(
        metrics_path,
        {"season", "team", "metric", "forecast_value_v0", "model_status"},
    )
    teams: dict[str, tuple[int, float]] = {}
    for row in team_input:
        team = row["team"].strip().upper()
        season = int(row["season"])
        certainty = _number(row["exact_style_certainty_v0"], f"{team} certainty")
        if not team or team in teams or not 0 <= certainty <= 100:
            raise PositionEnvironmentDataError("team table has invalid or duplicate rows")
        teams[team] = season, certainty
    if len({season for season, _ in teams.values()}) != 1:
        raise PositionEnvironmentDataError("team table must contain one season")
    season = next(iter(teams.values()))[0]

    metrics: dict[str, dict[str, float]] = defaultdict(dict)
    for row in metric_input:
        team = row["team"].strip().upper()
        metric = row["metric"].strip()
        if team not in teams or int(row["season"]) != season:
            raise PositionEnvironmentDataError("metric table is not aligned to team season")
        if metric in metrics[team]:
            raise PositionEnvironmentDataError(f"duplicate metric {team} {metric}")
        metrics[team][metric] = _number(
            row["forecast_value_v0"], f"{team} {metric}"
        )
    for team in teams:
        missing = REQUIRED_METRICS - set(metrics[team])
        if missing:
            raise PositionEnvironmentDataError(f"{team} is missing metrics: {sorted(missing)}")

    derived: dict[str, dict[str, float]] = {}
    for team, values in metrics.items():
        plays = values["plays_per_game"]
        pass_rate = values["pass_rate"]
        derived[team] = {
            "plays": plays,
            "pass_plays": plays * pass_rate,
            "rush_plays": plays * (1 - pass_rate),
            "neutral_pass": values["neutral_early_down_pass_rate"],
            "play_action": values["play_action_rate"],
            "air_yards": values["mean_air_yards"],
            "rb_share": values["rb_target_share"],
            "wr_share": values["wr_target_share"],
            "te_share": values["te_target_share"],
        }
    percentile: dict[str, dict[str, float]] = {
        feature: _percentiles({team: values[feature] for team, values in derived.items()})
        for feature in next(iter(derived.values()))
    }
    position_weights: Mapping[str, Mapping[str, float]] = {
        "QB": {"pass_plays": 0.55, "neutral_pass": 0.20, "air_yards": 0.15, "play_action": 0.10},
        "RB": {"rush_plays": 0.55, "rb_share": 0.35, "plays": 0.10},
        "WR": {"pass_plays": 0.50, "wr_share": 0.35, "air_yards": 0.15},
        "TE": {"pass_plays": 0.40, "te_share": 0.60},
    }
    provisional: list[dict[str, Any]] = []
    for team in sorted(teams):
        _, certainty = teams[team]
        for position in POSITIONS:
            components = {
                feature: percentile[feature][team]
                for feature in position_weights[position]
            }
            raw_score = 100 * sum(
                components[feature] * weight
                for feature, weight in position_weights[position].items()
            )
            adjusted = 50 + (raw_score - 50) * certainty / 100
            # The historical certainty diagnostic failed to rank held-out error and
            # produced wider score-tiered bands.  Preserve the old adjustment as a
            # transparent diagnostic, but do not let it change the watch-list rank.
            ranking_score = raw_score
            drivers = sorted(
                components,
                key=lambda feature: abs(components[feature] - 0.5)
                * position_weights[position][feature],
                reverse=True,
            )[:2]
            driver_text = "|".join(
                f"{feature}:{'high' if components[feature] >= 0.5 else 'low'}"
                for feature in drivers
            )
            target_share = (
                derived[team][f"{position.lower()}_share"]
                if position in {"RB", "WR", "TE"}
                else ""
            )
            provisional.append(
                {
                    "season": season,
                    "team": team,
                    "position": position,
                    "raw_opportunity_score_v0": round(raw_score, 1),
                    "certainty_adjusted_score_v0": round(adjusted, 1),
                    "ranking_score_v1": round(ranking_score, 1),
                    "ranking_policy": "raw_point_forecast_no_uncalibrated_certainty_shrinkage",
                    "opportunity_label": _label(ranking_score),
                    "league_rank": 0,
                    "team_exact_style_certainty_v0": round(certainty, 1),
                    "forecast_plays_per_game": round(derived[team]["plays"], 3),
                    "forecast_pass_plays_per_game": round(derived[team]["pass_plays"], 3),
                    "forecast_rush_plays_per_game": round(derived[team]["rush_plays"], 3),
                    "position_target_share": "" if target_share == "" else round(float(target_share), 6),
                    "mean_air_yards": round(derived[team]["air_yards"], 3),
                    "primary_drivers": driver_text,
                    "scope_warning": "No player role, roster quality, health, schedule, or efficiency adjustment.",
                    "model_status": MODEL_STATUS,
                }
            )
    for position in POSITIONS:
        ordered = sorted(
            (row for row in provisional if row["position"] == position),
            key=lambda row: (-float(row["ranking_score_v1"]), row["team"]),
        )
        for rank, row in enumerate(ordered, start=1):
            row["league_rank"] = rank
    return PositionEnvironmentResult(
        season=season,
        source_teams_path=teams_path,
        source_metrics_path=metrics_path,
        source_teams_sha256=hashlib.sha256(teams_raw).hexdigest(),
        source_metrics_sha256=hashlib.sha256(metrics_raw).hexdigest(),
        rows=tuple(sorted(provisional, key=lambda row: (row["position"], row["league_rank"]))),
    )


def _csv_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def write_position_environment_snapshot(
    result: PositionEnvironmentResult, root: str | Path
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    parent = Path(root) / "position_environments" / str(result.season)
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"position environment snapshot already exists: {destination}")
    payload = _csv_bytes(result.rows)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "model_status": MODEL_STATUS,
        "season": result.season,
        "methodology": {
            "scope": "Relative team-level opportunity pools by position from eligible nflverse PBP plays, pass/rush allocation, target shares, and passing style.",
            "ranking_policy": "Rank the caller-aware point forecast without shrinking by the uncalibrated 0-100 certainty index.",
            "legacy_certainty_diagnostic": "certainty_adjusted_score_v0 is preserved for audit only; the held-out historical certainty gate failed, so it cannot set rank, label, a numeric forecast, or interval width.",
            "numeric_resource_policy": "forecast_pass_plays_per_game and forecast_rush_plays_per_game retain the exact eligible-PBP definitions of the source; official dropbacks, targets, and carries require separately learned conversion factors.",
            "forbidden": "Do not interpret as player rankings or production projections; player role, personnel quality, health, schedule, and efficiency are absent.",
        },
        "inputs": {
            "teams": {"path": str(result.source_teams_path), "sha256": result.source_teams_sha256},
            "metric_forecasts": {"path": str(result.source_metrics_path), "sha256": result.source_metrics_sha256},
        },
        "quality": {
            "team_count": len({row["team"] for row in result.rows}),
            "position_count": len({row["position"] for row in result.rows}),
            "row_count": len(result.rows),
        },
        "artifacts": {
            "position_environments.csv": {
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "fields": list(FIELDS),
            }
        },
    }
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
    try:
        (staging / "position_environments.csv").write_bytes(payload)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
