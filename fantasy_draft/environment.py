"""Evidence-backed team offensive-style forecasts and position environments.

The model in this module is deliberately a transparent, uncalibrated v0.  Its
certainty scores are rubric scores until historical coach-transition backtests
map them to empirical coverage probabilities.
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
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse


MODEL_VERSION = "team-environment-heuristic-v0.1.0"
SNAPSHOT_SCHEMA_VERSION = "1.0.0"
CALIBRATION_STATUS = "uncalibrated_heuristic"

DIMENSIONS = {
    "volume",
    "pass_run_tendency",
    "pace",
    "formation",
    "passing_profile",
    "quarterback_run",
    "target_distribution",
    "explosiveness",
    "efficiency",
    "run_concepts",
    "pass_concepts",
    "red_zone",
}


@dataclass(frozen=True)
class MetricSpec:
    dimension: str
    tolerance: float
    label: str
    minimum: float | None = None
    maximum: float | None = None


METRICS: Mapping[str, MetricSpec] = {
    "plays_per_game": MetricSpec("volume", 4.0, "plays per game", 0.0),
    "pass_rate": MetricSpec("pass_run_tendency", 0.05, "overall dropback rate", 0.0, 1.0),
    "neutral_early_down_pass_rate": MetricSpec(
        "pass_run_tendency", 0.06, "neutral early-down dropback rate", 0.0, 1.0
    ),
    "neutral_pass_oe": MetricSpec(
        "pass_run_tendency",
        6.0,
        "neutral pass rate over expectation (percentage points)",
        -100.0,
        100.0,
    ),
    "shotgun_rate": MetricSpec("formation", 0.10, "shotgun rate", 0.0, 1.0),
    "no_huddle_rate": MetricSpec("pace", 0.06, "no-huddle rate", 0.0, 1.0),
    "under_center_rate": MetricSpec(
        "formation", 0.10, "under-center rate on charted QB-location plays", 0.0, 1.0
    ),
    "pistol_rate": MetricSpec(
        "formation", 0.04, "pistol rate on charted QB-location plays", 0.0, 1.0
    ),
    "motion_rate": MetricSpec("formation", 0.08, "pre-snap motion rate", 0.0, 1.0),
    "play_action_rate": MetricSpec(
        "pass_concepts", 0.06, "play-action rate on charted dropbacks", 0.0, 1.0
    ),
    "screen_pass_rate": MetricSpec(
        "pass_concepts", 0.04, "screen rate on charted dropbacks", 0.0, 1.0
    ),
    "rpo_rate": MetricSpec("pass_concepts", 0.04, "RPO rate", 0.0, 1.0),
    "multi_back_rate": MetricSpec(
        "run_concepts", 0.08, "two-plus-player backfield rate", 0.0, 1.0
    ),
    "qb_out_of_pocket_rate": MetricSpec(
        "passing_profile", 0.05, "QB out-of-pocket rate on charted dropbacks", 0.0, 1.0
    ),
    "qb_sneak_rate": MetricSpec(
        "quarterback_run", 0.02, "QB sneak rate", 0.0, 1.0
    ),
    "red_zone_pass_rate": MetricSpec("red_zone", 0.08, "red-zone dropback rate", 0.0, 1.0),
    "deep_attempt_rate": MetricSpec(
        "passing_profile", 0.05, "deep-attempt rate", 0.0, 1.0
    ),
    "mean_air_yards": MetricSpec("passing_profile", 1.5, "mean target depth"),
    "qb_scramble_rate": MetricSpec(
        "quarterback_run", 0.025, "scrambles per dropback", 0.0, 1.0
    ),
    "designed_qb_run_share": MetricSpec(
        "quarterback_run", 0.04, "designed-QB share of rushes", 0.0, 1.0
    ),
    "rb_target_share": MetricSpec(
        "target_distribution", 0.05, "running-back target share", 0.0, 1.0
    ),
    "wr_target_share": MetricSpec(
        "target_distribution", 0.07, "wide-receiver target share", 0.0, 1.0
    ),
    "te_target_share": MetricSpec(
        "target_distribution", 0.05, "tight-end target share", 0.0, 1.0
    ),
    "explosive_play_rate": MetricSpec(
        "explosiveness", 0.025, "explosive-play rate", 0.0, 1.0
    ),
    "success_rate": MetricSpec("efficiency", 0.04, "play success rate", 0.0, 1.0),
    "epa_per_play": MetricSpec("efficiency", 0.10, "EPA per play"),
}

CONTINUITY_VALUES = {
    "returning_same_role": 1.0,
    "returning_changed_role": 0.60,
    "returning_after_gap": 0.40,
    "new_to_team": 0.0,
    "unknown": 0.25,
}
PLAYCALLER_CONFIRMATION = {
    "official": 1.0,
    "reported": 0.85,
    "inferred": 0.45,
    "unknown": 0.0,
}
CERTAINTY_COMPONENT_WEIGHTS = {
    "playcaller_confirmed": 0.15,
    "same_playcaller": 0.20,
    "playcalling_experience": 0.15,
    "head_coach_continuity": 0.10,
    "scheme_continuity": 0.15,
    "offensive_staff_continuity": 0.10,
    "personnel_continuity": 0.10,
    "evidence_agreement": 0.05,
}

SOURCE_TYPES = {
    "official_team",
    "official_league",
    "credentialed_local",
    "wire_service",
    "national_reporting",
}
EVIDENCE_TYPES = {"staff_fact", "direct_quote", "practice_observation", "analysis"}


@dataclass(frozen=True)
class EvidenceSource:
    source_id: str
    title: str
    publisher: str
    source_type: str
    url: str
    published_at: date | None
    accessed_at: date


@dataclass(frozen=True)
class StaffMember:
    name: str
    roles: tuple[str, ...]
    continuity: str
    influence_dimensions: tuple[str, ...]
    influence_weight: float
    source_ids: tuple[str, ...]
    is_head_coach: bool = False
    is_play_caller: bool = False
    playcaller_confirmation: str = "unknown"
    completed_nfl_playcalling_seasons: int = 0


@dataclass(frozen=True)
class HistoricalAnchor:
    team: str
    season: int
    weight: float
    reason: str


@dataclass(frozen=True)
class NewsClaim:
    claim_id: str
    source_id: str
    summary: str
    evidence_type: str
    dimensions: tuple[str, ...]
    reliability: float
    strength: float
    certainty_effect: float
    metric_signals: Mapping[str, float]

    @property
    def evidence_weight(self) -> float:
        return self.reliability * self.strength


@dataclass(frozen=True)
class TeamResearch:
    team: str
    scheme_family: str
    scheme_continuity: float
    scheme_rationale: str
    scheme_source_ids: tuple[str, ...]
    returning_starters_fraction: float | None
    personnel_source_ids: tuple[str, ...]
    staff: tuple[StaffMember, ...]
    historical_anchors: tuple[HistoricalAnchor, ...]
    claims: tuple[NewsClaim, ...]

    @property
    def head_coach(self) -> StaffMember:
        return next(member for member in self.staff if member.is_head_coach)

    @property
    def play_caller(self) -> StaffMember:
        return next(member for member in self.staff if member.is_play_caller)


@dataclass(frozen=True)
class ResearchDataset:
    season: int
    as_of: date
    sources: Mapping[str, EvidenceSource]
    teams: tuple[TeamResearch, ...]


@dataclass(frozen=True)
class ObservedStyle:
    team: str
    season: int
    metrics: Mapping[str, float | None]


class EnvironmentDataError(ValueError):
    """Raised when curated evidence or observed style is invalid."""


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EnvironmentDataError(f"{context} must be an object")
    return value


def _list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise EnvironmentDataError(f"{context} must be a list")
    return value


def _string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EnvironmentDataError(f"{context} must be a non-empty string")
    return value.strip()


def _number(value: Any, context: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EnvironmentDataError(f"{context} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise EnvironmentDataError(f"{context} must be between {minimum} and {maximum}")
    return number


def _date(value: Any, context: str) -> date:
    text = _string(value, context)
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise EnvironmentDataError(f"{context} must use YYYY-MM-DD") from error


def _optional_date(value: Any, context: str) -> date | None:
    return None if value is None else _date(value, context)


def _string_tuple(value: Any, context: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    raw = _list(value, context)
    result = tuple(_string(item, f"{context}[]") for item in raw)
    if not allow_empty and not result:
        raise EnvironmentDataError(f"{context} cannot be empty")
    if len(set(result)) != len(result):
        raise EnvironmentDataError(f"{context} cannot contain duplicates")
    return result


def _source_from_dict(data: Mapping[str, Any], context: str) -> EvidenceSource:
    source_id = _string(data.get("id"), f"{context}.id")
    source_type = _string(data.get("source_type"), f"{context}.source_type")
    if source_type not in SOURCE_TYPES:
        raise EnvironmentDataError(f"{context}.source_type is unsupported")
    url = _string(data.get("url"), f"{context}.url")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise EnvironmentDataError(f"{context}.url must be an absolute HTTPS URL")
    return EvidenceSource(
        source_id=source_id,
        title=_string(data.get("title"), f"{context}.title"),
        publisher=_string(data.get("publisher"), f"{context}.publisher"),
        source_type=source_type,
        url=url,
        published_at=_optional_date(data.get("published_at"), f"{context}.published_at"),
        accessed_at=_date(data.get("accessed_at"), f"{context}.accessed_at"),
    )


def _staff_from_dict(data: Mapping[str, Any], context: str) -> StaffMember:
    continuity = _string(data.get("continuity"), f"{context}.continuity")
    if continuity not in CONTINUITY_VALUES:
        raise EnvironmentDataError(f"{context}.continuity is unsupported")
    dimensions = _string_tuple(
        data.get("influence_dimensions", []),
        f"{context}.influence_dimensions",
        allow_empty=True,
    )
    unknown_dimensions = set(dimensions) - DIMENSIONS
    if unknown_dimensions:
        raise EnvironmentDataError(
            f"{context} has unknown dimensions: {', '.join(sorted(unknown_dimensions))}"
        )
    is_play_caller = bool(data.get("is_play_caller", False))
    confirmation = _string(
        data.get("playcaller_confirmation", "unknown"),
        f"{context}.playcaller_confirmation",
    )
    if confirmation not in PLAYCALLER_CONFIRMATION:
        raise EnvironmentDataError(f"{context}.playcaller_confirmation is unsupported")
    experience = data.get("completed_nfl_playcalling_seasons", 0)
    if isinstance(experience, bool) or not isinstance(experience, int) or experience < 0:
        raise EnvironmentDataError(
            f"{context}.completed_nfl_playcalling_seasons must be a non-negative integer"
        )
    if not is_play_caller and (confirmation != "unknown" or experience):
        raise EnvironmentDataError(f"{context} has play-caller fields but is not the play caller")
    return StaffMember(
        name=_string(data.get("name"), f"{context}.name"),
        roles=_string_tuple(data.get("roles"), f"{context}.roles"),
        continuity=continuity,
        influence_dimensions=dimensions,
        influence_weight=_number(
            data.get("influence_weight", 1.0),
            f"{context}.influence_weight",
            0.1,
            3.0,
        ),
        source_ids=_string_tuple(data.get("source_ids"), f"{context}.source_ids"),
        is_head_coach=bool(data.get("is_head_coach", False)),
        is_play_caller=is_play_caller,
        playcaller_confirmation=confirmation,
        completed_nfl_playcalling_seasons=experience,
    )


def _anchor_from_dict(data: Mapping[str, Any], context: str) -> HistoricalAnchor:
    season = data.get("season")
    if isinstance(season, bool) or not isinstance(season, int) or not 1999 <= season <= 2100:
        raise EnvironmentDataError(f"{context}.season must be an NFL season")
    return HistoricalAnchor(
        team=_string(data.get("team"), f"{context}.team").upper(),
        season=season,
        weight=_number(data.get("weight"), f"{context}.weight", 0.01, 3.0),
        reason=_string(data.get("reason"), f"{context}.reason"),
    )


def _claim_from_dict(data: Mapping[str, Any], context: str) -> NewsClaim:
    evidence_type = _string(data.get("evidence_type"), f"{context}.evidence_type")
    if evidence_type not in EVIDENCE_TYPES:
        raise EnvironmentDataError(f"{context}.evidence_type is unsupported")
    dimensions = _string_tuple(data.get("dimensions"), f"{context}.dimensions")
    unknown_dimensions = set(dimensions) - DIMENSIONS
    if unknown_dimensions:
        raise EnvironmentDataError(
            f"{context} has unknown dimensions: {', '.join(sorted(unknown_dimensions))}"
        )
    raw_signals = _mapping(data.get("metric_signals", {}), f"{context}.metric_signals")
    signals: dict[str, float] = {}
    for metric, raw_signal in raw_signals.items():
        if metric not in METRICS:
            raise EnvironmentDataError(f"{context} has unknown metric signal {metric!r}")
        if METRICS[metric].dimension not in dimensions:
            raise EnvironmentDataError(
                f"{context} signal {metric!r} is not covered by its dimensions"
            )
        signals[metric] = _number(raw_signal, f"{context}.metric_signals.{metric}", -1.0, 1.0)
    return NewsClaim(
        claim_id=_string(data.get("id"), f"{context}.id"),
        source_id=_string(data.get("source_id"), f"{context}.source_id"),
        summary=_string(data.get("summary"), f"{context}.summary"),
        evidence_type=evidence_type,
        dimensions=dimensions,
        reliability=_number(data.get("reliability"), f"{context}.reliability", 0.0, 1.0),
        strength=_number(data.get("strength"), f"{context}.strength", 0.0, 1.0),
        certainty_effect=_number(
            data.get("certainty_effect"), f"{context}.certainty_effect", -1.0, 1.0
        ),
        metric_signals=signals,
    )


def load_research_dataset(path: str | Path) -> ResearchDataset:
    """Load and cross-validate a curated team staff/news research file."""

    with Path(path).open(encoding="utf-8") as handle:
        root = _mapping(json.load(handle), "research")
    if root.get("schema_version") != "1.0.0":
        raise EnvironmentDataError("research.schema_version must be '1.0.0'")
    season = root.get("season")
    if isinstance(season, bool) or not isinstance(season, int) or not 1999 <= season <= 2100:
        raise EnvironmentDataError("research.season must be an NFL season")
    as_of = _date(root.get("as_of"), "research.as_of")

    sources: dict[str, EvidenceSource] = {}
    for index, raw_source in enumerate(_list(root.get("sources"), "research.sources")):
        source = _source_from_dict(
            _mapping(raw_source, f"research.sources[{index}]"),
            f"research.sources[{index}]",
        )
        if source.source_id in sources:
            raise EnvironmentDataError(f"duplicate source ID {source.source_id!r}")
        if (source.published_at is not None and source.published_at > as_of) or source.accessed_at > as_of:
            raise EnvironmentDataError(f"source {source.source_id!r} is dated after as_of")
        sources[source.source_id] = source
    if not sources:
        raise EnvironmentDataError("research.sources cannot be empty")

    teams: list[TeamResearch] = []
    seen_teams: set[str] = set()
    seen_claims: set[str] = set()
    for team_index, raw_team in enumerate(_list(root.get("teams"), "research.teams")):
        context = f"research.teams[{team_index}]"
        data = _mapping(raw_team, context)
        team = _string(data.get("team"), f"{context}.team").upper()
        if team in seen_teams:
            raise EnvironmentDataError(f"duplicate team {team!r}")
        seen_teams.add(team)
        staff = tuple(
            _staff_from_dict(_mapping(item, f"{context}.staff[{index}]"), f"{context}.staff[{index}]")
            for index, item in enumerate(_list(data.get("staff"), f"{context}.staff"))
        )
        if sum(member.is_head_coach for member in staff) != 1:
            raise EnvironmentDataError(f"{team} must have exactly one head coach")
        if sum(member.is_play_caller for member in staff) != 1:
            raise EnvironmentDataError(f"{team} must have exactly one play caller")
        if len({member.name for member in staff}) != len(staff):
            raise EnvironmentDataError(f"{team} staff contains a duplicate coach")

        anchors = tuple(
            _anchor_from_dict(
                _mapping(item, f"{context}.historical_anchors[{index}]"),
                f"{context}.historical_anchors[{index}]",
            )
            for index, item in enumerate(
                _list(data.get("historical_anchors"), f"{context}.historical_anchors")
            )
        )
        if not anchors:
            raise EnvironmentDataError(f"{team} must contain historical anchors")
        claims = tuple(
            _claim_from_dict(_mapping(item, f"{context}.claims[{index}]"), f"{context}.claims[{index}]")
            for index, item in enumerate(_list(data.get("claims"), f"{context}.claims"))
        )
        for claim in claims:
            if claim.claim_id in seen_claims:
                raise EnvironmentDataError(f"duplicate claim ID {claim.claim_id!r}")
            seen_claims.add(claim.claim_id)

        source_references: set[str] = set()
        for member in staff:
            source_references.update(member.source_ids)
        scheme_source_ids = _string_tuple(
            data.get("scheme_source_ids"), f"{context}.scheme_source_ids"
        )
        personnel_source_ids = _string_tuple(
            data.get("personnel_source_ids", []),
            f"{context}.personnel_source_ids",
            allow_empty=True,
        )
        source_references.update(scheme_source_ids)
        source_references.update(personnel_source_ids)
        source_references.update(claim.source_id for claim in claims)
        unknown_sources = source_references - set(sources)
        if unknown_sources:
            raise EnvironmentDataError(
                f"{team} references unknown sources: {', '.join(sorted(unknown_sources))}"
            )

        raw_starters = data.get("returning_starters_fraction")
        starters = (
            None
            if raw_starters is None
            else _number(raw_starters, f"{context}.returning_starters_fraction", 0.0, 1.0)
        )
        teams.append(
            TeamResearch(
                team=team,
                scheme_family=_string(data.get("scheme_family"), f"{context}.scheme_family"),
                scheme_continuity=_number(
                    data.get("scheme_continuity"), f"{context}.scheme_continuity", 0.0, 1.0
                ),
                scheme_rationale=_string(
                    data.get("scheme_rationale"), f"{context}.scheme_rationale"
                ),
                scheme_source_ids=scheme_source_ids,
                returning_starters_fraction=starters,
                personnel_source_ids=personnel_source_ids,
                staff=staff,
                historical_anchors=anchors,
                claims=claims,
            )
        )
    if not teams:
        raise EnvironmentDataError("research.teams cannot be empty")
    return ResearchDataset(
        season=season,
        as_of=as_of,
        sources=sources,
        teams=tuple(sorted(teams, key=lambda item: item.team)),
    )


def load_observed_styles(path: str | Path) -> tuple[ObservedStyle, ...]:
    """Load the normalized CSV produced by the nflverse style adapter."""

    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        required = {"team", "season", *METRICS}
        missing = required - fields
        if missing:
            raise EnvironmentDataError(
                f"observed style is missing fields: {', '.join(sorted(missing))}"
            )
        records: list[ObservedStyle] = []
        seen: set[tuple[str, int]] = set()
        for row_number, row in enumerate(reader, start=2):
            team = (row.get("team") or "").strip().upper()
            try:
                season = int((row.get("season") or "").strip())
            except ValueError as error:
                raise EnvironmentDataError(
                    f"observed style row {row_number} has an invalid season"
                ) from error
            if not team:
                raise EnvironmentDataError(f"observed style row {row_number} has no team")
            key = (team, season)
            if key in seen:
                raise EnvironmentDataError(f"duplicate observed style for {season} {team}")
            seen.add(key)
            metrics: dict[str, float | None] = {}
            for metric in METRICS:
                raw = (row.get(metric) or "").strip()
                if not raw:
                    metrics[metric] = None
                    continue
                try:
                    value = float(raw)
                except ValueError as error:
                    raise EnvironmentDataError(
                        f"observed style row {row_number} has invalid {metric}"
                    ) from error
                if not math.isfinite(value):
                    raise EnvironmentDataError(
                        f"observed style row {row_number} has non-finite {metric}"
                    )
                metrics[metric] = value
            records.append(ObservedStyle(team=team, season=season, metrics=metrics))
    if not records:
        raise EnvironmentDataError("observed style contains no rows")
    return tuple(sorted(records, key=lambda item: (item.season, item.team)))


def _weighted_mean(values: Iterable[tuple[float, float]]) -> float:
    pairs = tuple(values)
    total_weight = sum(weight for _, weight in pairs)
    return sum(value * weight for value, weight in pairs) / total_weight


def _weighted_std(values: Iterable[tuple[float, float]], mean: float) -> float:
    pairs = tuple(values)
    total_weight = sum(weight for _, weight in pairs)
    return math.sqrt(sum(weight * (value - mean) ** 2 for value, weight in pairs) / total_weight)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _tier(score: float) -> str:
    if score >= 80:
        return "high"
    if score >= 65:
        return "medium_high"
    if score >= 50:
        return "medium"
    if score >= 35:
        return "low_medium"
    return "low"


def _staff_continuity(team: TeamResearch) -> tuple[float, int]:
    members = [
        member
        for member in team.staff
        if not member.is_head_coach and not member.is_play_caller
    ]
    if not members:
        return 0.25, 0
    denominator = sum(member.influence_weight for member in members)
    numerator = sum(
        CONTINUITY_VALUES[member.continuity] * member.influence_weight
        for member in members
    )
    return numerator / denominator, len(members)


def _evidence_agreement(claims: Iterable[NewsClaim]) -> float:
    weighted = [(claim.certainty_effect, claim.evidence_weight) for claim in claims]
    total_weight = sum(weight for _, weight in weighted)
    if not total_weight:
        return 0.5
    effect = sum(value * weight for value, weight in weighted) / total_weight
    return (effect + 1.0) / 2.0


def _certainty_components(team: TeamResearch) -> tuple[float, dict[str, dict[str, float]]]:
    caller = team.play_caller
    head_coach = team.head_coach
    staff_continuity, staff_count = _staff_continuity(team)
    values = {
        "playcaller_confirmed": PLAYCALLER_CONFIRMATION[caller.playcaller_confirmation],
        "same_playcaller": 1.0 if caller.continuity == "returning_same_role" else 0.0,
        "playcalling_experience": min(caller.completed_nfl_playcalling_seasons / 5.0, 1.0),
        "head_coach_continuity": CONTINUITY_VALUES[head_coach.continuity],
        "scheme_continuity": team.scheme_continuity,
        "offensive_staff_continuity": staff_continuity,
        "personnel_continuity": (
            team.returning_starters_fraction
            if team.returning_starters_fraction is not None
            else 0.25
        ),
        "evidence_agreement": _evidence_agreement(team.claims),
    }
    components: dict[str, dict[str, float]] = {}
    score = 0.0
    for name, weight in CERTAINTY_COMPONENT_WEIGHTS.items():
        points = 100.0 * weight * values[name]
        components[name] = {
            "value": round(values[name], 4),
            "weight": weight,
            "points": round(points, 2),
        }
        score += points
    components["offensive_staff_continuity"]["coach_count"] = float(staff_count)
    return score, components


def _population_std(values: Iterable[float]) -> float:
    items = tuple(values)
    return statistics.pstdev(items) if len(items) > 1 else 0.0


def _percentile(value: float, reference: Iterable[float]) -> float:
    values = sorted(reference)
    if not values:
        return 0.5
    lower = sum(item < value for item in values)
    equal = sum(item == value for item in values)
    return (lower + 0.5 * equal) / len(values)


def _metric_signal(team: TeamResearch, metric: str) -> tuple[float, float, list[str]]:
    relevant = [claim for claim in team.claims if metric in claim.metric_signals]
    total_weight = sum(claim.evidence_weight for claim in relevant)
    if not total_weight:
        return 0.0, 0.0, []
    signal = sum(
        claim.metric_signals[metric] * claim.evidence_weight for claim in relevant
    ) / total_weight
    return signal, min(total_weight, 1.0), [claim.claim_id for claim in relevant]


def _dimension_effect(team: TeamResearch, dimension: str) -> float:
    relevant = [claim for claim in team.claims if dimension in claim.dimensions]
    total_weight = sum(claim.evidence_weight for claim in relevant)
    if not total_weight:
        return 0.0
    return sum(
        claim.certainty_effect * claim.evidence_weight for claim in relevant
    ) / total_weight


POSITION_METRICS: Mapping[str, tuple[tuple[str, float, int], ...]] = {
    "QB": (
        ("neutral_early_down_pass_rate", 0.25, 1),
        ("pass_rate", 0.15, 1),
        ("plays_per_game", 0.15, 1),
        ("red_zone_pass_rate", 0.10, 1),
        ("deep_attempt_rate", 0.10, 1),
        ("qb_scramble_rate", 0.15, 1),
        ("epa_per_play", 0.10, 1),
    ),
    "RB": (
        ("neutral_early_down_pass_rate", 0.25, -1),
        ("red_zone_pass_rate", 0.20, -1),
        ("plays_per_game", 0.15, 1),
        ("rb_target_share", 0.20, 1),
        ("success_rate", 0.10, 1),
        ("designed_qb_run_share", 0.10, -1),
    ),
    "WR": (
        ("neutral_early_down_pass_rate", 0.25, 1),
        ("pass_rate", 0.10, 1),
        ("plays_per_game", 0.15, 1),
        ("deep_attempt_rate", 0.15, 1),
        ("wr_target_share", 0.25, 1),
        ("epa_per_play", 0.10, 1),
    ),
    "TE": (
        ("neutral_early_down_pass_rate", 0.15, 1),
        ("plays_per_game", 0.15, 1),
        ("te_target_share", 0.40, 1),
        ("red_zone_pass_rate", 0.15, 1),
        ("success_rate", 0.15, 1),
    ),
}


def _position_label(score: float) -> str:
    if score >= 65:
        return "favorable"
    if score >= 55:
        return "slightly_favorable"
    if score >= 45:
        return "mixed_neutral"
    if score >= 35:
        return "slightly_unfavorable"
    return "unfavorable"


def _position_environments(
    metric_forecasts: Mapping[str, Mapping[str, Any]],
    references: Mapping[str, list[float]],
) -> dict[str, dict[str, Any]]:
    environments: dict[str, dict[str, Any]] = {}
    for position, definitions in POSITION_METRICS.items():
        scored: list[tuple[str, float, float, float]] = []
        total_possible = sum(weight for _, weight, _ in definitions)
        for metric, weight, direction in definitions:
            forecast = metric_forecasts.get(metric)
            if not forecast or forecast.get("value") is None or not references.get(metric):
                continue
            percentile = _percentile(float(forecast["value"]), references[metric])
            if direction < 0:
                percentile = 1.0 - percentile
            scored.append((metric, weight, percentile, float(forecast["certainty_score"])))
        available_weight = sum(item[1] for item in scored)
        coverage = available_weight / total_possible if total_possible else 0.0
        if not available_weight:
            environments[position] = {
                "score": 50.0,
                "label": "unknown",
                "certainty_score": 0.0,
                "coverage": 0.0,
                "drivers": [],
            }
            continue
        raw_score = 100.0 * sum(weight * pct for _, weight, pct, _ in scored) / available_weight
        score = 50.0 + (raw_score - 50.0) * coverage
        certainty = (
            sum(weight * metric_certainty for _, weight, _, metric_certainty in scored)
            / available_weight
        ) * coverage
        ranked = sorted(scored, key=lambda item: abs(item[2] - 0.5), reverse=True)[:3]
        drivers = [
            {
                "metric": metric,
                "direction": "positive" if percentile >= 0.5 else "negative",
                "reference_percentile": round(100.0 * percentile, 1),
            }
            for metric, _, percentile, _ in ranked
        ]
        environments[position] = {
            "score": round(score, 1),
            "label": _position_label(score),
            "certainty_score": round(certainty, 1),
            "coverage": round(coverage, 3),
            "drivers": drivers,
        }
    return environments


def build_team_environment_forecast(
    dataset: ResearchDataset,
    observed: Iterable[ObservedStyle],
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build auditable team forecasts from measured anchors and current evidence."""

    generated_at = generated_at or datetime.now(timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at must include a timezone")
    generated_at = generated_at.astimezone(timezone.utc)
    observed_records = tuple(observed)
    observed_index = {(item.team, item.season): item for item in observed_records}
    references = {
        metric: [
            value
            for record in observed_records
            if (value := record.metrics.get(metric)) is not None
        ]
        for metric in METRICS
    }

    results: list[dict[str, Any]] = []
    for team in dataset.teams:
        missing_anchors = [
            f"{anchor.season}:{anchor.team}"
            for anchor in team.historical_anchors
            if (anchor.team, anchor.season) not in observed_index
        ]
        if missing_anchors:
            raise EnvironmentDataError(
                f"{team.team} is missing observed anchors: {', '.join(missing_anchors)}"
            )
        structural_score, components = _certainty_components(team)
        forecasts: dict[str, dict[str, Any]] = {}
        for metric, spec in METRICS.items():
            anchor_values: list[tuple[float, float, HistoricalAnchor]] = []
            for anchor in team.historical_anchors:
                value = observed_index[(anchor.team, anchor.season)].metrics.get(metric)
                if value is not None:
                    anchor_values.append((value, anchor.weight, anchor))
            if not anchor_values:
                forecasts[metric] = {
                    "value": None,
                    "certainty_score": 0.0,
                    "dimension": spec.dimension,
                    "label": spec.label,
                    "reference_percentile": None,
                    "anchor_count": 0,
                    "evidence_claim_ids": [],
                }
                continue
            pairs = [(value, weight) for value, weight, _ in anchor_values]
            base_value = _weighted_mean(pairs)
            anchor_std = _weighted_std(pairs, base_value)
            reference_std = _population_std(references[metric])
            signal, evidence_volume, claim_ids = _metric_signal(team, metric)
            shift = reference_std * 0.20 * signal * evidence_volume
            forecast_value = base_value + shift
            if spec.minimum is not None:
                forecast_value = max(spec.minimum, forecast_value)
            if spec.maximum is not None:
                forecast_value = min(spec.maximum, forecast_value)

            dispersion = 1.0 - min(anchor_std / spec.tolerance, 1.0)
            sample_factor = min(sum(weight for _, weight in pairs) / 3.0, 1.0)
            historical_stability = dispersion * (0.5 + 0.5 * sample_factor)
            dimension_effect = _dimension_effect(team, spec.dimension)
            certainty = _clamp(
                0.80 * structural_score
                + 0.20 * historical_stability * 100.0
                + 5.0 * dimension_effect,
                0.0,
                100.0,
            )
            forecasts[metric] = {
                "value": round(forecast_value, 6),
                "anchor_value": round(base_value, 6),
                "news_shift": round(shift, 6),
                "certainty_score": round(certainty, 1),
                "dimension": spec.dimension,
                "label": spec.label,
                "reference_percentile": round(
                    100.0 * _percentile(forecast_value, references[metric]), 1
                ),
                "anchor_count": len(anchor_values),
                "anchor_dispersion": round(anchor_std, 6),
                "evidence_claim_ids": claim_ids,
            }

        dimensions: dict[str, dict[str, Any]] = {}
        for dimension in sorted(DIMENSIONS):
            dimension_metrics = [
                (name, value)
                for name, value in forecasts.items()
                if value["dimension"] == dimension and value["value"] is not None
            ]
            claims = [claim.claim_id for claim in team.claims if dimension in claim.dimensions]
            dimensions[dimension] = {
                "certainty_score": (
                    round(
                        sum(value["certainty_score"] for _, value in dimension_metrics)
                        / len(dimension_metrics),
                        1,
                    )
                    if dimension_metrics
                    else 0.0
                ),
                "metrics": [name for name, _ in dimension_metrics],
                "evidence_claim_ids": claims,
            }
        populated_certainties = [
            item["certainty_score"] for item in forecasts.values() if item["value"] is not None
        ]
        style_score = (
            sum(populated_certainties) / len(populated_certainties)
            if populated_certainties
            else 0.0
        )
        results.append(
            {
                "team": team.team,
                "scheme_family": team.scheme_family,
                "scheme_rationale": team.scheme_rationale,
                "head_coach": team.head_coach.name,
                "play_caller": team.play_caller.name,
                "staff": [
                    {
                        "name": member.name,
                        "roles": list(member.roles),
                        "continuity": member.continuity,
                        "is_head_coach": member.is_head_coach,
                        "is_play_caller": member.is_play_caller,
                        "influence_dimensions": list(member.influence_dimensions),
                        "source_ids": list(member.source_ids),
                    }
                    for member in team.staff
                ],
                "certainty": {
                    "structural_score": round(structural_score, 1),
                    "style_score": round(style_score, 1),
                    "tier": _tier(style_score),
                    "calibration_status": CALIBRATION_STATUS,
                    "components": components,
                },
                "style_forecast": forecasts,
                "dimensions": dimensions,
                "position_environments": _position_environments(forecasts, references),
                "historical_anchors": [
                    {
                        "team": anchor.team,
                        "season": anchor.season,
                        "weight": anchor.weight,
                        "reason": anchor.reason,
                    }
                    for anchor in team.historical_anchors
                ],
                "claim_ids": [claim.claim_id for claim in team.claims],
                "source_ids": sorted(
                    {
                        *team.scheme_source_ids,
                        *team.personnel_source_ids,
                        *(source_id for member in team.staff for source_id in member.source_ids),
                        *(claim.source_id for claim in team.claims),
                    }
                ),
            }
        )

    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "calibration_status": CALIBRATION_STATUS,
        "warning": (
            "Scores are transparent heuristic indices, not calibrated probabilities or "
            "fantasy-point projections. Historical transition backtesting is required."
        ),
        "limitations": [
            "Position scores describe team-level opportunity environments, not individual player roles.",
            "Current injuries, depth-chart competition, and player-specific usage are not yet joined.",
            "FTN charting supplies motion and concept proxies from 2022 onward, but does not identify zone versus gap run families or full 11/12/21 personnel usage here.",
            "Press and practice evidence can move a metric by at most a small fraction of historical cross-team dispersion.",
        ],
        "season": dataset.season,
        "as_of": dataset.as_of.isoformat(),
        "generated_at": generated_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "methodology": {
            "news_shift_cap": "20% of cross-team historical standard deviation per metric",
            "position_environment": (
                "weighted historical percentiles shrunk to neutral for missing coverage"
            ),
            "certainty_weights": CERTAINTY_COMPONENT_WEIGHTS,
        },
        "sources": {
            source_id: {
                "title": source.title,
                "publisher": source.publisher,
                "source_type": source.source_type,
                "url": source.url,
                "published_at": (
                    source.published_at.isoformat() if source.published_at is not None else None
                ),
                "accessed_at": source.accessed_at.isoformat(),
            }
            for source_id, source in sorted(dataset.sources.items())
        },
        "claims": {
            claim.claim_id: {
                "team": team.team,
                "source_id": claim.source_id,
                "summary": claim.summary,
                "evidence_type": claim.evidence_type,
                "dimensions": list(claim.dimensions),
                "reliability": claim.reliability,
                "strength": claim.strength,
                "certainty_effect": claim.certainty_effect,
                "metric_signals": dict(claim.metric_signals),
            }
            for team in dataset.teams
            for claim in team.claims
        },
        "teams": results,
    }


def _summary_csv(forecast: Mapping[str, Any]) -> bytes:
    fields = [
        "team",
        "head_coach",
        "play_caller",
        "scheme_family",
        "structural_certainty",
        "style_certainty",
        "certainty_tier",
        "qb_environment",
        "qb_certainty",
        "rb_environment",
        "rb_certainty",
        "wr_environment",
        "wr_certainty",
        "te_environment",
        "te_certainty",
        "calibration_status",
    ]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for team in forecast["teams"]:
        positions = team["position_environments"]
        writer.writerow(
            {
                "team": team["team"],
                "head_coach": team["head_coach"],
                "play_caller": team["play_caller"],
                "scheme_family": team["scheme_family"],
                "structural_certainty": team["certainty"]["structural_score"],
                "style_certainty": team["certainty"]["style_score"],
                "certainty_tier": team["certainty"]["tier"],
                "qb_environment": positions["QB"]["score"],
                "qb_certainty": positions["QB"]["certainty_score"],
                "rb_environment": positions["RB"]["score"],
                "rb_certainty": positions["RB"]["certainty_score"],
                "wr_environment": positions["WR"]["score"],
                "wr_certainty": positions["WR"]["certainty_score"],
                "te_environment": positions["TE"]["score"],
                "te_certainty": positions["TE"]["certainty_score"],
                "calibration_status": forecast["calibration_status"],
            }
        )
    return stream.getvalue().encode("utf-8")


def write_environment_snapshot(
    forecast: Mapping[str, Any],
    root: str | Path,
    *,
    research_bytes: bytes,
    observed_style_bytes: bytes,
) -> Path:
    """Atomically publish an immutable environment forecast and its input hashes."""

    root = Path(root)
    generated_at = datetime.fromisoformat(str(forecast["generated_at"]).replace("Z", "+00:00"))
    timestamp = generated_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    parent = root / "team_environment" / str(forecast["season"])
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"environment snapshot already exists: {destination}")

    forecast_bytes = (json.dumps(forecast, indent=2, sort_keys=True) + "\n").encode("utf-8")
    summary_bytes = _summary_csv(forecast)
    manifest = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "model_version": forecast["model_version"],
        "calibration_status": forecast["calibration_status"],
        "season": forecast["season"],
        "as_of": forecast["as_of"],
        "generated_at": forecast["generated_at"],
        "quality": {
            "team_count": len(forecast["teams"]),
            "teams": [team["team"] for team in forecast["teams"]],
        },
        "inputs": {
            "research_sha256": hashlib.sha256(research_bytes).hexdigest(),
            "observed_style_sha256": hashlib.sha256(observed_style_bytes).hexdigest(),
        },
        "artifacts": {
            "forecast": {
                "path": "team_environment.json",
                "bytes": len(forecast_bytes),
                "sha256": hashlib.sha256(forecast_bytes).hexdigest(),
            },
            "summary": {
                "path": "team_environment.csv",
                "bytes": len(summary_bytes),
                "sha256": hashlib.sha256(summary_bytes).hexdigest(),
            },
        },
    }
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
    try:
        (staging / "team_environment.json").write_bytes(forecast_bytes)
        (staging / "team_environment.csv").write_bytes(summary_bytes)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
