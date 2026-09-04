"""Shared, denominator-consistent team opportunity resource transform.

The nflverse team-style layer counts eligible PBP pass/rush plays.  Those are
not identical to official attempts-plus-sacks, targets, or position carries.
This module keeps those units explicit and learns the three required bridges
from matched team-season history.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


RECENCY_FACTOR = 0.65
RESOURCE_NAMES = (
    "QB_DROPBACKS",
    "QB_RUSH_OPPORTUNITIES",
    "RB_CARRIES",
    "RB_TARGETS",
    "WR_TARGETS",
    "TE_TARGETS",
)
CONVERSION_KEYS = (
    "qb_dropbacks_per_pass_play",
    "target_per_pass_play",
    "rb_carries_per_non_qb_rush_play",
)
RESOURCE_INPUTS: Mapping[str, tuple[str, ...]] = {
    "QB_DROPBACKS": ("plays_per_game", "pass_rate"),
    "QB_RUSH_OPPORTUNITIES": (
        "plays_per_game",
        "pass_rate",
        "qb_scramble_rate",
        "designed_qb_run_share",
    ),
    "RB_CARRIES": (
        "plays_per_game",
        "pass_rate",
        "designed_qb_run_share",
    ),
    "RB_TARGETS": ("plays_per_game", "pass_rate", "rb_target_share"),
    "WR_TARGETS": ("plays_per_game", "pass_rate", "wr_target_share"),
    "TE_TARGETS": ("plays_per_game", "pass_rate", "te_target_share"),
}
TEAM_ALIASES = {"LA": "LAR"}
STYLE_REQUIRED_FIELDS = {
    "season",
    "team",
    "plays",
    "pass_rate",
    "designed_qb_run_share",
}


class ResourceTransformError(ValueError):
    """Raised when resource inputs use inconsistent or invalid units."""


@dataclass(frozen=True)
class VerifiedTeamStyle:
    path: Path
    manifest_path: Path
    rows: tuple[Mapping[str, str], ...]
    raw_by_path: Mapping[str, bytes]


@dataclass(frozen=True)
class ConversionEstimate:
    factors: Mapping[str, float]
    training_seasons: tuple[int, ...]
    team_season_count: int


def canonical_team(value: str) -> str:
    """Normalize the one current nflverse team-code mismatch used in joins."""

    team = value.strip().upper()
    return TEAM_ALIASES.get(team, team)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _finite(value: Any, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ResourceTransformError(f"{context} must be numeric") from error
    if not math.isfinite(result):
        raise ResourceTransformError(f"{context} must be finite")
    return result


def _normalized_metadata(manifest: Mapping[str, Any]) -> Mapping[str, Any] | None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        return None
    normalized = artifacts.get("normalized")
    if isinstance(normalized, Mapping):
        if isinstance(normalized.get("sha256"), str):
            return normalized
        nested = normalized.get("team_style.csv")
        if isinstance(nested, Mapping):
            return nested
    direct = artifacts.get("team_style.csv")
    return direct if isinstance(direct, Mapping) else None


def load_verified_team_style(path: str | Path) -> VerifiedTeamStyle:
    """Load a team-style CSV only when its adjacent manifest binds its hash."""

    supplied = Path(path)
    csv_path = supplied / "team_style.csv" if supplied.is_dir() else supplied
    manifest_path = csv_path.parent / "manifest.json"
    if not csv_path.is_file():
        raise ResourceTransformError(f"team-style CSV does not exist: {csv_path}")
    if not manifest_path.is_file():
        raise ResourceTransformError(
            f"team-style manifest does not exist: {manifest_path}"
        )
    csv_raw = csv_path.read_bytes()
    manifest_raw = manifest_path.read_bytes()
    try:
        manifest = json.loads(manifest_raw)
    except json.JSONDecodeError as error:
        raise ResourceTransformError(
            f"team-style manifest is not valid JSON: {manifest_path}"
        ) from error
    if not isinstance(manifest, Mapping):
        raise ResourceTransformError(
            f"team-style manifest must contain an object: {manifest_path}"
        )
    metadata = _normalized_metadata(manifest)
    expected = metadata.get("sha256") if metadata else None
    if not isinstance(expected, str):
        raise ResourceTransformError(
            f"team-style manifest does not bind team_style.csv: {manifest_path}"
        )
    actual = _sha256(csv_raw)
    if actual != expected:
        raise ResourceTransformError(
            f"team-style hash mismatch for {csv_path}: expected {expected}, got {actual}"
        )
    try:
        reader = csv.DictReader(io.StringIO(csv_raw.decode("utf-8-sig"), newline=""))
        fields = set(reader.fieldnames or ())
        rows = list(reader)
    except UnicodeDecodeError as error:
        raise ResourceTransformError(f"team-style CSV is not UTF-8: {csv_path}") from error
    missing = STYLE_REQUIRED_FIELDS - fields
    if missing or not rows:
        raise ResourceTransformError(
            f"team-style CSV is empty or missing fields {sorted(missing)}: {csv_path}"
        )
    identities: set[tuple[int, str]] = set()
    for row in rows:
        try:
            season = int(row["season"])
        except (TypeError, ValueError) as error:
            raise ResourceTransformError(
                f"team-style season must be an integer: {row.get('season')!r}"
            ) from error
        team = canonical_team(row["team"])
        identity = season, team
        if not team or identity in identities:
            raise ResourceTransformError(
                f"team-style rows have a blank or duplicate identity: {identity}"
            )
        identities.add(identity)
        plays = _finite(row["plays"], f"{season} {team} plays")
        pass_rate = _finite(row["pass_rate"], f"{season} {team} pass rate")
        designed_qb = _finite(
            row["designed_qb_run_share"],
            f"{season} {team} designed-QB-run share",
        )
        if plays <= 0 or not 0 <= pass_rate <= 1 or not 0 <= designed_qb <= 1:
            raise ResourceTransformError(
                f"invalid team-style resource denominator for {season} {team}"
            )
    return VerifiedTeamStyle(
        path=csv_path,
        manifest_path=manifest_path,
        rows=tuple(rows),
        raw_by_path={str(manifest_path): manifest_raw, str(csv_path): csv_raw},
    )


def derive_conversion_factors(
    usage_by_team_season: Mapping[tuple[int, str], Mapping[str, float]],
    style_rows: Iterable[Mapping[str, str]],
    *,
    training_seasons: Iterable[int],
    latest_season: int,
    recency_factor: float = RECENCY_FACTOR,
) -> ConversionEstimate:
    """Fit count bridges on matched team-seasons with explicit PBP denominators.

    ``usage_by_team_season`` must provide ``qb_dropbacks``, ``targets``, and
    ``rb_carries`` as official player-stat totals.  Style rows provide eligible
    PBP pass/rush play totals.  Each season receives one recency weight; within a
    season the estimate is naturally exposure weighted by its play counts.
    """

    seasons = tuple(sorted(set(training_seasons)))
    if not seasons or latest_season != max(seasons):
        raise ResourceTransformError(
            "conversion training seasons must be non-empty and end at latest_season"
        )
    if not 0 < recency_factor <= 1:
        raise ResourceTransformError("conversion recency_factor must lie in (0,1]")
    styles: dict[tuple[int, str], Mapping[str, str]] = {}
    for row in style_rows:
        identity = int(row["season"]), canonical_team(row["team"])
        if identity in styles:
            raise ResourceTransformError(f"duplicate team-style identity {identity}")
        styles[identity] = row

    weighted_qb_dropbacks = 0.0
    weighted_targets = 0.0
    weighted_rb_carries = 0.0
    weighted_pass_plays = 0.0
    weighted_non_qb_rush_plays = 0.0
    matched = 0
    season_counts: dict[int, int] = {}
    for season in seasons:
        identities = sorted(
            identity for identity in usage_by_team_season if identity[0] == season
        )
        if not identities:
            raise ResourceTransformError(
                f"conversion history has no usage teams for {season}"
            )
        missing = [identity for identity in identities if identity not in styles]
        if missing:
            raise ResourceTransformError(
                f"team-style history is missing {len(missing)} usage teams for {season}: "
                + ", ".join(team for _, team in missing[:5])
            )
        weight = recency_factor ** (latest_season - season)
        season_counts[season] = len(identities)
        for identity in identities:
            usage = usage_by_team_season[identity]
            style = styles[identity]
            plays = _finite(style["plays"], f"{identity} plays")
            pass_rate = _finite(style["pass_rate"], f"{identity} pass rate")
            designed_qb = _finite(
                style["designed_qb_run_share"], f"{identity} designed-QB-run share"
            )
            pass_plays = plays * pass_rate
            non_qb_rush_plays = plays * (1 - pass_rate) * (1 - designed_qb)
            qb_dropbacks = _finite(usage.get("qb_dropbacks"), f"{identity} QB dropbacks")
            targets = _finite(usage.get("targets"), f"{identity} targets")
            rb_carries = _finite(usage.get("rb_carries"), f"{identity} RB carries")
            if min(pass_plays, non_qb_rush_plays, qb_dropbacks, targets, rb_carries) < 0:
                raise ResourceTransformError(f"negative conversion input for {identity}")
            weighted_pass_plays += weight * pass_plays
            weighted_non_qb_rush_plays += weight * non_qb_rush_plays
            weighted_qb_dropbacks += weight * qb_dropbacks
            weighted_targets += weight * targets
            weighted_rb_carries += weight * rb_carries
            matched += 1
    if weighted_pass_plays <= 0 or weighted_non_qb_rush_plays <= 0:
        raise ResourceTransformError("conversion history has no positive PBP denominators")
    factors = {
        "qb_dropbacks_per_pass_play": weighted_qb_dropbacks / weighted_pass_plays,
        "target_per_pass_play": weighted_targets / weighted_pass_plays,
        "rb_carries_per_non_qb_rush_play": (
            weighted_rb_carries / weighted_non_qb_rush_plays
        ),
    }
    bounds = {
        "qb_dropbacks_per_pass_play": (0.70, 1.05),
        "target_per_pass_play": (0.55, 1.00),
        "rb_carries_per_non_qb_rush_play": (0.50, 1.10),
    }
    for key, value in factors.items():
        low, high = bounds[key]
        if not low <= value <= high:
            raise ResourceTransformError(
                f"historical {key} is implausible: {value:.6f} not in [{low}, {high}]"
            )
    return ConversionEstimate(
        factors=factors,
        training_seasons=seasons,
        team_season_count=matched,
    )


def resource_forecasts(
    metrics: Mapping[str, float], conversions: Mapping[str, float]
) -> Mapping[str, float]:
    """Convert caller-aware PBP style metrics into six official-stat pools."""

    missing_metrics = set().union(*RESOURCE_INPUTS.values()) - set(metrics)
    missing_conversions = set(CONVERSION_KEYS) - set(conversions)
    if missing_metrics or missing_conversions:
        raise ResourceTransformError(
            "resource transform is missing "
            f"metrics {sorted(missing_metrics)} and conversions {sorted(missing_conversions)}"
        )
    values = {key: _finite(value, key) for key, value in metrics.items()}
    factors = {key: _finite(conversions[key], key) for key in CONVERSION_KEYS}
    plays = values["plays_per_game"]
    pass_rate = values["pass_rate"]
    scramble = values["qb_scramble_rate"]
    designed_qb = values["designed_qb_run_share"]
    share_keys = ("rb_target_share", "wr_target_share", "te_target_share")
    shares = [values[key] for key in share_keys]
    if plays <= 0 or any(not 0 <= value <= 1 for value in [pass_rate, scramble, designed_qb, *shares]):
        raise ResourceTransformError("plays must be positive and every rate/share must lie in [0,1]")
    share_total = sum(shares)
    if share_total > 1.05:
        raise ResourceTransformError(
            "RB/WR/TE target-share forecast is implausibly above one"
        )
    if share_total > 1:
        # Independently blended position-share forecasts can lose compositional
        # closure.  Preserve legitimate residual QB/other targets when the sum
        # is below one, but rescale an impossible overflow instead of creating
        # extra targets.
        shares = [value / share_total for value in shares]
    target_shares = dict(zip(share_keys, shares, strict=True))
    pass_plays = plays * pass_rate
    rush_plays = plays * (1 - pass_rate)
    target_pool = pass_plays * factors["target_per_pass_play"]
    forecasts = {
        "QB_DROPBACKS": pass_plays * factors["qb_dropbacks_per_pass_play"],
        "QB_RUSH_OPPORTUNITIES": (
            pass_plays * scramble + rush_plays * designed_qb
        ),
        "RB_CARRIES": (
            rush_plays
            * (1 - designed_qb)
            * factors["rb_carries_per_non_qb_rush_play"]
        ),
        "RB_TARGETS": target_pool * target_shares["rb_target_share"],
        "WR_TARGETS": target_pool * target_shares["wr_target_share"],
        "TE_TARGETS": target_pool * target_shares["te_target_share"],
    }
    if any(not math.isfinite(value) or value < 0 for value in forecasts.values()):
        raise ResourceTransformError("resource forecast is negative or non-finite")
    return forecasts
