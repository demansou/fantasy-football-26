"""Recent primary-play-caller style fingerprints for the current NFL season.

The builder joins four different facts without conflating them:

* who is verified to call plays now;
* who actually called plays in a historical season;
* what that historical offense did on the field; and
* how much of the destination staff and system remains in place.

The resulting certainty values are transparent evidence scores.  They are not
probabilities and remain uncalibrated until the transition backtest is complete.
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
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

from .environment import METRICS


SCHEMA_VERSION = "1.0.0"
MODEL_VERSION = "caller-fingerprint-heuristic-v0.1.0"
MODEL_STATUS = "uncalibrated_evidence_score"
RECENCY_DECAY = 0.75
STYLE_TEAM_ALIASES = {"LA": "LAR"}

# Efficiency and explosives are outcomes, not play-style identity.  They remain
# in the observed source but are deliberately excluded from this forecast.
STYLE_METRICS = tuple(
    metric
    for metric, spec in METRICS.items()
    if spec.dimension not in {"efficiency", "explosiveness"}
)

EPISODE_FIELDS = (
    "current_season",
    "current_team",
    "play_caller",
    "history_team",
    "history_season",
    "coverage",
    "week_start",
    "week_end",
    "full_team_season_anchor",
    "style_weight",
    "recency_weight",
    "usable_style_weight",
    "origin",
    "source_url",
    "temporal_use",
    "evidence_summary",
)

TEAM_FIELDS = (
    "season",
    "team",
    "head_coach",
    "play_caller",
    "caller_2025_status",
    "same_play_caller",
    "play_caller_on_prior_staff",
    "head_coach_continuity",
    "staff_continuity_index_v0",
    "caller_identity_strength",
    "recent_full_season_anchor_count",
    "recent_anchor_seasons",
    "recent_anchor_teams",
    "effective_anchor_strength",
    "fingerprint_metric_coverage",
    "fingerprint_stability",
    "caller_continuity_component",
    "scheme_family",
    "scheme_identity_score",
    "destination_scheme_continuity",
    "scheme_evidence_sources",
    "scheme_rationale",
    "broad_system_certainty_v0",
    "broad_system_certainty_label",
    "exact_style_certainty_v0",
    "exact_style_certainty_label",
    "model_status",
)

METRIC_FIELDS = (
    "season",
    "team",
    "play_caller",
    "metric",
    "dimension",
    "destination_2025_value",
    "caller_fingerprint_value",
    "league_2025_value",
    "forecast_value_v0",
    "caller_anchor_count",
    "caller_anchor_stability",
    "metric_certainty_v0",
    "caller_weight",
    "destination_weight",
    "league_weight",
    "structured_evidence_signal",
    "model_status",
)


class CallerFingerprintDataError(ValueError):
    """Raised when caller-history inputs do not satisfy the join contract."""


@dataclass(frozen=True)
class CurrentTeam:
    season: int
    team: str
    head_coach: str
    play_caller: str
    identity_strength: float


@dataclass(frozen=True)
class ContinuityTeam:
    team: str
    caller_2025_status: str
    same_play_caller: bool
    caller_on_prior_staff: bool
    head_coach_continuity: bool
    staff_continuity: float


@dataclass(frozen=True)
class Episode:
    current_team: str
    play_caller: str
    history_team: str
    history_season: int
    coverage: str
    week_start: int | None
    week_end: int | None
    full_team_season_anchor: bool
    style_weight: float
    origin: str
    source_url: str
    temporal_use: str
    evidence_summary: str

    @property
    def key(self) -> tuple[int, str, str]:
        return self.history_season, self.history_team, _identity(self.play_caller)


@dataclass(frozen=True)
class SystemEvidence:
    team: str
    play_caller: str
    scheme_family: str
    scheme_identity_score: float
    destination_continuity: float
    rationale: str
    source_urls: tuple[str, ...]
    metric_signals: Mapping[str, float]


@dataclass(frozen=True)
class CallerFingerprintResult:
    season: int
    as_of: date
    input_paths: tuple[Path, ...]
    input_hashes: Mapping[str, str]
    episode_rows: tuple[Mapping[str, Any], ...]
    team_rows: tuple[Mapping[str, Any], ...]
    metric_rows: tuple[Mapping[str, Any], ...]


def _identity(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _resolve_csv(path: str | Path, filename: str) -> Path:
    resolved = Path(path)
    if resolved.is_dir():
        resolved = resolved / filename
    if not resolved.is_file():
        raise CallerFingerprintDataError(f"input does not exist: {resolved}")
    return resolved


def _read_csv(path: Path, required: set[str]) -> tuple[bytes, list[dict[str, str]]]:
    raw = path.read_bytes()
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    except UnicodeDecodeError as error:
        raise CallerFingerprintDataError(f"CSV is not UTF-8: {path}") from error
    if not rows or not required.issubset(rows[0]):
        missing = required - set(rows[0] if rows else ())
        raise CallerFingerprintDataError(
            f"CSV has no rows or is missing fields {sorted(missing)}: {path}"
        )
    return raw, rows


def _integer(value: str, context: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise CallerFingerprintDataError(f"{context} must be an integer") from error
    return parsed


def _float(value: str, context: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise CallerFingerprintDataError(f"{context} must be numeric") from error
    if not math.isfinite(parsed):
        raise CallerFingerprintDataError(f"{context} must be finite")
    return parsed


def _boolean(value: str, context: str) -> bool:
    normalized = value.strip().casefold()
    if normalized not in {"true", "false"}:
        raise CallerFingerprintDataError(f"{context} must be true or false")
    return normalized == "true"


def _url(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CallerFingerprintDataError(f"{context} must be a non-empty URL")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise CallerFingerprintDataError(f"{context} must be an absolute HTTPS URL")
    return value


def _current_teams(path: str | Path) -> tuple[Path, bytes, dict[str, CurrentTeam]]:
    resolved = _resolve_csv(path, "teams.csv")
    raw, rows = _read_csv(
        resolved,
        {"season", "team", "head_coach", "play_caller", "evidence_strength"},
    )
    seasons = {_integer(row["season"], "current season") for row in rows}
    if len(seasons) != 1:
        raise CallerFingerprintDataError("current caller census must contain one season")
    result: dict[str, CurrentTeam] = {}
    for row in rows:
        team = row["team"].strip().upper()
        if not team or team in result:
            raise CallerFingerprintDataError("current caller census has blank/duplicate team")
        strength = _float(row["evidence_strength"], f"{team} evidence_strength")
        if not 0 <= strength <= 1:
            raise CallerFingerprintDataError(f"{team} evidence_strength must be in [0,1]")
        result[team] = CurrentTeam(
            season=next(iter(seasons)),
            team=team,
            head_coach=row["head_coach"].strip(),
            play_caller=row["play_caller"].strip(),
            identity_strength=strength,
        )
    return resolved, raw, result


def _continuity(path: str | Path) -> tuple[Path, bytes, dict[str, ContinuityTeam]]:
    resolved = _resolve_csv(path, "teams.csv")
    raw, rows = _read_csv(
        resolved,
        {
            "team",
            "current_caller_2025_status",
            "same_play_caller",
            "play_caller_on_prior_staff",
            "head_coach_status",
            "staff_continuity_index_v0",
        },
    )
    result: dict[str, ContinuityTeam] = {}
    for row in rows:
        team = row["team"].strip().upper()
        if not team or team in result:
            raise CallerFingerprintDataError("continuity input has blank/duplicate team")
        staff = _float(row["staff_continuity_index_v0"], f"{team} staff continuity") / 100
        if not 0 <= staff <= 1:
            raise CallerFingerprintDataError(f"{team} staff continuity must be in [0,100]")
        result[team] = ContinuityTeam(
            team=team,
            caller_2025_status=row["current_caller_2025_status"].strip(),
            same_play_caller=_boolean(row["same_play_caller"], f"{team} same caller"),
            caller_on_prior_staff=_boolean(
                row["play_caller_on_prior_staff"], f"{team} caller on prior staff"
            ),
            head_coach_continuity=row["head_coach_status"].strip() == "retained_holder",
            staff_continuity=staff,
        )
    return resolved, raw, result


def _observed_styles(
    path: str | Path,
) -> tuple[Path, bytes, dict[tuple[int, str], dict[str, float | None]]]:
    resolved = _resolve_csv(path, "team_style.csv")
    raw, rows = _read_csv(resolved, {"season", "team", *STYLE_METRICS})
    result: dict[tuple[int, str], dict[str, float | None]] = {}
    for row in rows:
        season = _integer(row["season"], "style season")
        observed_team = row["team"].strip().upper()
        team = STYLE_TEAM_ALIASES.get(observed_team, observed_team)
        key = season, team
        if not team or key in result:
            raise CallerFingerprintDataError("observed styles have blank/duplicate team-season")
        result[key] = {
            metric: None if not row[metric].strip() else _float(row[metric], f"{key} {metric}")
            for metric in STYLE_METRICS
        }
    return resolved, raw, result


def _historical_census(
    paths: Iterable[str | Path], current: Mapping[str, CurrentTeam]
) -> tuple[list[Path], dict[str, bytes], list[Episode]]:
    resolved_paths: list[Path] = []
    raw_by_path: dict[str, bytes] = {}
    episodes: list[Episode] = []
    current_by_identity = {_identity(item.play_caller): item for item in current.values()}
    seen_seasons: set[int] = set()
    for supplied in paths:
        resolved = _resolve_csv(supplied, "callers.csv")
        raw, rows = _read_csv(
            resolved,
            {
                "season",
                "team",
                "play_caller",
                "source_url",
                "temporal_use",
                "experience_text",
            },
        )
        seasons = {_integer(row["season"], "historical caller season") for row in rows}
        if len(seasons) != 1:
            raise CallerFingerprintDataError(f"historical census must contain one season: {resolved}")
        season = next(iter(seasons))
        if season in seen_seasons:
            raise CallerFingerprintDataError(f"duplicate historical census season {season}")
        seen_seasons.add(season)
        resolved_paths.append(resolved)
        raw_by_path[str(resolved)] = raw
        for row in rows:
            owner = current_by_identity.get(_identity(row["play_caller"]))
            if owner is None:
                continue
            episodes.append(
                Episode(
                    current_team=owner.team,
                    play_caller=owner.play_caller,
                    history_team=row["team"].strip().upper(),
                    history_season=season,
                    coverage="opening_primary_caller_full_season_candidate",
                    week_start=None,
                    week_end=None,
                    full_team_season_anchor=True,
                    style_weight=1.0,
                    origin="historical_census",
                    source_url=_url(row["source_url"], f"{resolved} source_url"),
                    temporal_use=row["temporal_use"].strip(),
                    evidence_summary=row["experience_text"].strip(),
                )
            )
    return resolved_paths, raw_by_path, episodes


def _load_overrides(
    path: str | Path,
    current: Mapping[str, CurrentTeam],
    census_episodes: list[Episode],
) -> tuple[Path, bytes, date, list[Episode]]:
    resolved = Path(path)
    raw_bytes = resolved.read_bytes()
    try:
        root = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CallerFingerprintDataError(f"invalid override JSON: {resolved}") from error
    if not isinstance(root, Mapping) or root.get("schema_version") != "1.0.0":
        raise CallerFingerprintDataError("episode override schema_version must be '1.0.0'")
    try:
        as_of = date.fromisoformat(str(root.get("as_of")))
    except ValueError as error:
        raise CallerFingerprintDataError("episode override as_of must use YYYY-MM-DD") from error
    current_by_identity = {_identity(item.play_caller): item for item in current.values()}
    episode_by_key = {episode.key: episode for episode in census_episodes}
    exclusions = root.get("exclusions")
    additions = root.get("additions")
    if not isinstance(exclusions, list) or not isinstance(additions, list):
        raise CallerFingerprintDataError("episode exclusions and additions must be lists")

    for index, item in enumerate(exclusions):
        if not isinstance(item, Mapping):
            raise CallerFingerprintDataError(f"exclusions[{index}] must be an object")
        key = (
            int(item.get("season", 0)),
            str(item.get("team", "")).strip().upper(),
            _identity(str(item.get("caller", ""))),
        )
        episode = episode_by_key.get(key)
        if episode is None:
            raise CallerFingerprintDataError(f"exclusion does not match a census episode: {key}")
        reason = str(item.get("reason", "")).strip()
        source_url = _url(item.get("source_url"), f"exclusions[{index}].source_url")
        if not reason:
            raise CallerFingerprintDataError(f"exclusions[{index}].reason is blank")
        replacement = Episode(
            **{
                **episode.__dict__,
                "coverage": "partial_or_changed_during_season",
                "full_team_season_anchor": False,
                "style_weight": 0.0,
                "origin": "historical_census_with_audited_exclusion",
                "source_url": source_url,
                "evidence_summary": reason,
            }
        )
        episode_by_key[key] = replacement

    for index, item in enumerate(additions):
        if not isinstance(item, Mapping):
            raise CallerFingerprintDataError(f"additions[{index}] must be an object")
        caller = str(item.get("caller", "")).strip()
        owner = current_by_identity.get(_identity(caller))
        if owner is None:
            raise CallerFingerprintDataError(
                f"addition caller is not a current caller: {caller!r}"
            )
        season = item.get("season")
        weight = item.get("style_weight")
        usable = item.get("full_team_season_anchor")
        if isinstance(season, bool) or not isinstance(season, int):
            raise CallerFingerprintDataError(f"additions[{index}].season must be an integer")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not 0 <= weight <= 1:
            raise CallerFingerprintDataError(f"additions[{index}].style_weight must be in [0,1]")
        if not isinstance(usable, bool):
            raise CallerFingerprintDataError(
                f"additions[{index}].full_team_season_anchor must be boolean"
            )
        week_start = item.get("week_start")
        week_end = item.get("week_end")
        if week_start is not None and (isinstance(week_start, bool) or not isinstance(week_start, int)):
            raise CallerFingerprintDataError(f"additions[{index}].week_start must be an integer")
        if week_end is not None and (isinstance(week_end, bool) or not isinstance(week_end, int)):
            raise CallerFingerprintDataError(f"additions[{index}].week_end must be an integer")
        if usable and (week_start is not None or week_end is not None or weight <= 0):
            raise CallerFingerprintDataError(
                f"additions[{index}] full-season anchor cannot have weeks and needs positive weight"
            )
        history_team = str(item.get("team", "")).strip().upper()
        coverage = str(item.get("coverage", "")).strip()
        summary = str(item.get("evidence_summary", "")).strip()
        if not history_team or not coverage or not summary:
            raise CallerFingerprintDataError(f"additions[{index}] has blank required values")
        episode = Episode(
            current_team=owner.team,
            play_caller=owner.play_caller,
            history_team=history_team,
            history_season=season,
            coverage=coverage,
            week_start=week_start,
            week_end=week_end,
            full_team_season_anchor=usable,
            style_weight=float(weight),
            origin="audited_addition",
            source_url=_url(item.get("source_url"), f"additions[{index}].source_url"),
            temporal_use=str(item.get("temporal_use", "historical_identity_evidence")).strip(),
            evidence_summary=summary,
        )
        if episode.key in episode_by_key:
            raise CallerFingerprintDataError(f"addition duplicates an existing episode: {episode.key}")
        episode_by_key[episode.key] = episode
    return resolved, raw_bytes, as_of, list(episode_by_key.values())


def _load_system_evidence(
    path: str | Path,
    current: Mapping[str, CurrentTeam],
    continuity: Mapping[str, ContinuityTeam],
) -> tuple[Path, bytes, date, dict[str, SystemEvidence]]:
    resolved = Path(path)
    raw_bytes = resolved.read_bytes()
    try:
        root = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CallerFingerprintDataError(f"invalid system-evidence JSON: {resolved}") from error
    if not isinstance(root, Mapping) or root.get("schema_version") != "1.0.0":
        raise CallerFingerprintDataError("system evidence schema_version must be '1.0.0'")
    try:
        as_of = date.fromisoformat(str(root.get("as_of")))
    except ValueError as error:
        raise CallerFingerprintDataError("system evidence as_of must use YYYY-MM-DD") from error
    raw_teams = root.get("teams")
    if not isinstance(raw_teams, list):
        raise CallerFingerprintDataError("system evidence teams must be a list")
    result: dict[str, SystemEvidence] = {}
    for index, item in enumerate(raw_teams):
        if not isinstance(item, Mapping):
            raise CallerFingerprintDataError(f"system evidence teams[{index}] must be an object")
        team = str(item.get("team", "")).strip().upper()
        caller = str(item.get("play_caller", "")).strip()
        family = str(item.get("scheme_family", "")).strip()
        rationale = str(item.get("rationale", "")).strip()
        if team not in current or team in result or not caller or not family or not rationale:
            raise CallerFingerprintDataError(f"system evidence teams[{index}] is blank, duplicate, or unknown")
        if _identity(caller) != _identity(current[team].play_caller):
            raise CallerFingerprintDataError(f"system evidence caller mismatch for {team}")
        identity_score = item.get("scheme_identity_score")
        destination = item.get("destination_scheme_continuity")
        for name, value in (
            ("scheme_identity_score", identity_score),
            ("destination_scheme_continuity", destination),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise CallerFingerprintDataError(f"{team} {name} must be in [0,1]")
        source_values = item.get("source_urls")
        if not isinstance(source_values, list) or not source_values:
            raise CallerFingerprintDataError(f"{team} source_urls must be a non-empty list")
        source_urls = tuple(
            _url(value, f"system evidence {team}.source_urls") for value in source_values
        )
        raw_signals = item.get("metric_signals", {})
        if not isinstance(raw_signals, Mapping):
            raise CallerFingerprintDataError(f"{team} metric_signals must be an object")
        signals: dict[str, float] = {}
        for metric, value in raw_signals.items():
            if metric not in STYLE_METRICS:
                raise CallerFingerprintDataError(f"{team} has unsupported style signal {metric!r}")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not -1 <= value <= 1:
                raise CallerFingerprintDataError(f"{team} signal {metric} must be in [-1,1]")
            signals[str(metric)] = float(value)
        result[team] = SystemEvidence(
            team=team,
            play_caller=current[team].play_caller,
            scheme_family=family,
            scheme_identity_score=float(identity_score),
            destination_continuity=float(destination),
            rationale=rationale,
            source_urls=source_urls,
            metric_signals=signals,
        )
    expected = {team for team, row in continuity.items() if not row.same_play_caller}
    if set(result) != expected:
        missing = expected - set(result)
        extra = set(result) - expected
        raise CallerFingerprintDataError(
            f"system evidence must cover every changed caller; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    return resolved, raw_bytes, as_of, result


def _weighted_mean(values: Iterable[tuple[float, float]]) -> float | None:
    pairs = [(value, weight) for value, weight in values if weight > 0]
    denominator = sum(weight for _, weight in pairs)
    return None if not denominator else sum(value * weight for value, weight in pairs) / denominator


def _stability(values: list[tuple[float, float]], tolerance: float) -> float:
    if not values:
        return 0.20
    if len(values) == 1:
        return 0.45
    center = _weighted_mean(values)
    assert center is not None
    mad = _weighted_mean((abs(value - center), weight) for value, weight in values)
    assert mad is not None
    return 1.0 / (1.0 + mad / tolerance)


def _label(score: float) -> str:
    if score >= 80:
        return "high"
    if score >= 65:
        return "medium-high"
    if score >= 50:
        return "medium"
    if score >= 35:
        return "low-medium"
    return "low"


def _components(
    continuity: ContinuityTeam,
    *,
    has_anchors: bool,
    has_episode_evidence: bool,
    destination_continuity: float,
) -> tuple[float, tuple[float, float, float]]:
    """Return caller-continuity and caller/destination/league blend weights."""

    if continuity.same_play_caller:
        return 1.0, (0.65, 0.30, 0.05)
    if continuity.caller_2025_status == "moved_2025_caller":
        return 0.75, (0.70, 0.20, 0.10)
    if continuity.caller_on_prior_staff:
        if has_anchors:
            return 0.65, (0.40, 0.50, 0.10)
        return 0.60, (0.00, 0.80, 0.20)
    if has_anchors:
        return 0.50, (0.65, 0.20, 0.15)
    destination_weight = 0.80 if destination_continuity >= 0.75 else (
        0.60 if destination_continuity >= 0.50 else 0.35
    )
    caller_component = 0.35 if has_episode_evidence else 0.15
    return caller_component, (0.00, destination_weight, 1.00 - destination_weight)


def build_caller_fingerprints(
    current_census: str | Path,
    continuity: str | Path,
    historical_callers: Iterable[str | Path],
    observed_styles: str | Path,
    episode_overrides: str | Path,
    system_evidence: str | Path,
) -> CallerFingerprintResult:
    """Build all-current-team caller histories, fingerprints, and evidence scores."""

    current_path, current_raw, current = _current_teams(current_census)
    continuity_path, continuity_raw, continuity_rows = _continuity(continuity)
    style_path, style_raw, styles = _observed_styles(observed_styles)
    historical_paths, historical_raw, census_episodes = _historical_census(
        historical_callers, current
    )
    override_path, override_raw, as_of, episodes = _load_overrides(
        episode_overrides, current, census_episodes
    )
    system_path, system_raw, system_as_of, system_rows = _load_system_evidence(
        system_evidence, current, continuity_rows
    )
    if system_as_of != as_of:
        raise CallerFingerprintDataError(
            "episode overrides and system evidence must use the same as_of date"
        )
    if set(current) != set(continuity_rows):
        raise CallerFingerprintDataError("current census and continuity team sets differ")
    seasons = {item.season for item in current.values()}
    if len(seasons) != 1:
        raise CallerFingerprintDataError("current census must contain one season")
    season = seasons.pop()
    latest_observed = max(year for year, _ in styles)
    if latest_observed != season - 1:
        raise CallerFingerprintDataError(
            f"latest observed season {latest_observed} does not precede target {season}"
        )
    if any(episode.history_season >= season for episode in episodes):
        raise CallerFingerprintDataError("historical episodes must precede target season")

    anchors_by_team: dict[str, list[tuple[Episode, float]]] = defaultdict(list)
    episode_rows: list[Mapping[str, Any]] = []
    for episode in sorted(
        episodes, key=lambda item: (item.current_team, item.history_season, item.history_team)
    ):
        recency = RECENCY_DECAY ** (latest_observed - episode.history_season)
        usable = episode.style_weight * recency if episode.full_team_season_anchor else 0.0
        if episode.full_team_season_anchor:
            if (episode.history_season, episode.history_team) not in styles:
                raise CallerFingerprintDataError(
                    f"missing observed style for anchor {episode.history_season} {episode.history_team}"
                )
            anchors_by_team[episode.current_team].append((episode, usable))
        episode_rows.append(
            {
                "current_season": season,
                "current_team": episode.current_team,
                "play_caller": episode.play_caller,
                "history_team": episode.history_team,
                "history_season": episode.history_season,
                "coverage": episode.coverage,
                "week_start": "" if episode.week_start is None else episode.week_start,
                "week_end": "" if episode.week_end is None else episode.week_end,
                "full_team_season_anchor": str(episode.full_team_season_anchor).lower(),
                "style_weight": round(episode.style_weight, 6),
                "recency_weight": round(recency, 6),
                "usable_style_weight": round(usable, 6),
                "origin": episode.origin,
                "source_url": episode.source_url,
                "temporal_use": episode.temporal_use,
                "evidence_summary": episode.evidence_summary,
            }
        )

    latest_team_values = {
        team: metrics for (year, team), metrics in styles.items() if year == latest_observed
    }
    if set(current) != set(latest_team_values):
        raise CallerFingerprintDataError("latest observed styles do not cover current teams")
    league_values = {
        metric: statistics.median(
            values[metric]
            for values in latest_team_values.values()
            if values[metric] is not None
        )
        for metric in STYLE_METRICS
    }

    team_rows: list[Mapping[str, Any]] = []
    metric_rows: list[Mapping[str, Any]] = []
    for team in sorted(current):
        current_team = current[team]
        cont = continuity_rows[team]
        anchors = anchors_by_team.get(team, [])
        has_anchors = bool(anchors)
        system = system_rows.get(team)
        if system is None:
            scheme_family = "returning caller and measured 2025 team identity"
            scheme_identity = 1.0
            destination_continuity = 1.0
            scheme_sources = "derived:current-census|staff-continuity|2025-style"
            scheme_rationale = (
                "The verified 2026 primary caller is the same person who called this "
                "team's 2025 offense."
            )
            metric_signals: Mapping[str, float] = {}
        else:
            scheme_family = system.scheme_family
            scheme_identity = system.scheme_identity_score
            destination_continuity = system.destination_continuity
            scheme_sources = "|".join(system.source_urls)
            scheme_rationale = system.rationale
            metric_signals = system.metric_signals
        has_episode_evidence = any(
            episode.current_team == team for episode in episodes
        )
        caller_component, blend = _components(
            cont,
            has_anchors=has_anchors,
            has_episode_evidence=has_episode_evidence,
            destination_continuity=destination_continuity,
        )
        anchor_strength = min(1.0, sum(weight for _, weight in anchors) / 2.2)
        metric_stabilities: list[float] = []
        available_fingerprints = 0
        per_metric: dict[str, tuple[float | None, int, float]] = {}
        for metric in STYLE_METRICS:
            values = [
                (value, weight)
                for episode, weight in anchors
                if (value := styles[(episode.history_season, episode.history_team)][metric])
                is not None
            ]
            fingerprint = _weighted_mean(values)
            stability = _stability(values, METRICS[metric].tolerance)
            if fingerprint is not None:
                available_fingerprints += 1
                metric_stabilities.append(stability)
            per_metric[metric] = (fingerprint, len(values), stability)
        coverage = available_fingerprints / len(STYLE_METRICS)
        overall_stability = (
            statistics.mean(metric_stabilities) if metric_stabilities else 0.20
        )
        hc_continuity = 1.0 if cont.head_coach_continuity else 0.0
        # These are deliberately explicit heuristics.  The historical transition
        # backtest will replace their weights and map scores to forecast errors.
        broad = 100 * (
            0.20 * current_team.identity_strength
            + 0.45 * scheme_identity
            + 0.15 * anchor_strength
            + 0.10 * destination_continuity
            + 0.05 * cont.staff_continuity
            + 0.05 * hc_continuity
        )
        exact = 100 * (
            0.10 * current_team.identity_strength
            + 0.15 * caller_component
            + 0.18 * anchor_strength
            + 0.12 * cont.staff_continuity
            + 0.08 * hc_continuity
            + 0.12 * overall_stability
            + 0.15 * destination_continuity
            + 0.10 * scheme_identity
        )
        # A caller/team transition cannot receive the top exact-rate tier before
        # we observe the new combination.  This ceiling is itself provisional
        # and is declared in the manifest for the backtest to challenge.
        if not cont.same_play_caller:
            exact = min(exact, 79.0)
        anchor_seasons = sorted({episode.history_season for episode, _ in anchors})
        anchor_teams = sorted({episode.history_team for episode, _ in anchors})
        team_rows.append(
            {
                "season": season,
                "team": team,
                "head_coach": current_team.head_coach,
                "play_caller": current_team.play_caller,
                "caller_2025_status": cont.caller_2025_status,
                "same_play_caller": str(cont.same_play_caller).lower(),
                "play_caller_on_prior_staff": str(cont.caller_on_prior_staff).lower(),
                "head_coach_continuity": str(cont.head_coach_continuity).lower(),
                "staff_continuity_index_v0": round(cont.staff_continuity * 100, 1),
                "caller_identity_strength": round(current_team.identity_strength, 3),
                "recent_full_season_anchor_count": len(anchors),
                "recent_anchor_seasons": "|".join(map(str, anchor_seasons)),
                "recent_anchor_teams": "|".join(anchor_teams),
                "effective_anchor_strength": round(anchor_strength, 6),
                "fingerprint_metric_coverage": round(coverage, 6),
                "fingerprint_stability": round(overall_stability, 6),
                "caller_continuity_component": round(caller_component, 3),
                "scheme_family": scheme_family,
                "scheme_identity_score": round(scheme_identity, 3),
                "destination_scheme_continuity": round(destination_continuity, 3),
                "scheme_evidence_sources": scheme_sources,
                "scheme_rationale": scheme_rationale,
                "broad_system_certainty_v0": round(broad, 1),
                "broad_system_certainty_label": _label(broad),
                "exact_style_certainty_v0": round(exact, 1),
                "exact_style_certainty_label": _label(exact),
                "model_status": MODEL_STATUS,
            }
        )

        caller_weight, destination_weight, league_weight = blend
        for metric in STYLE_METRICS:
            fingerprint, count, stability = per_metric[metric]
            destination = latest_team_values[team][metric]
            league = league_values[metric]
            components = []
            if fingerprint is not None and caller_weight:
                components.append((fingerprint, caller_weight))
            if destination is not None and destination_weight:
                components.append((destination, destination_weight))
            components.append((league, league_weight))
            forecast = _weighted_mean(components)
            assert forecast is not None
            spec = METRICS[metric]
            structured_signal = metric_signals.get(metric, 0.0)
            # A direct structured claim can move the preliminary mean by at most
            # half of the predeclared metric tolerance.  Backtesting may reduce,
            # remove, or replace this deliberately conservative cap.
            forecast += structured_signal * spec.tolerance * 0.5
            if spec.minimum is not None:
                forecast = max(spec.minimum, forecast)
            if spec.maximum is not None:
                forecast = min(spec.maximum, forecast)
            metric_certainty = 0.70 * exact + 30 * stability
            metric_rows.append(
                {
                    "season": season,
                    "team": team,
                    "play_caller": current_team.play_caller,
                    "metric": metric,
                    "dimension": spec.dimension,
                    "destination_2025_value": "" if destination is None else round(destination, 6),
                    "caller_fingerprint_value": "" if fingerprint is None else round(fingerprint, 6),
                    "league_2025_value": round(league, 6),
                    "forecast_value_v0": round(forecast, 6),
                    "caller_anchor_count": count,
                    "caller_anchor_stability": round(stability, 6),
                    "metric_certainty_v0": round(metric_certainty, 1),
                    "caller_weight": caller_weight if fingerprint is not None else 0.0,
                    "destination_weight": destination_weight,
                    "league_weight": league_weight,
                    "structured_evidence_signal": structured_signal,
                    "model_status": MODEL_STATUS,
                }
            )

    paths = [
        current_path,
        continuity_path,
        style_path,
        *historical_paths,
        override_path,
        system_path,
    ]
    raw_inputs = {
        str(current_path): current_raw,
        str(continuity_path): continuity_raw,
        str(style_path): style_raw,
        **historical_raw,
        str(override_path): override_raw,
        str(system_path): system_raw,
    }
    return CallerFingerprintResult(
        season=season,
        as_of=as_of,
        input_paths=tuple(paths),
        input_hashes={path: hashlib.sha256(raw).hexdigest() for path, raw in raw_inputs.items()},
        episode_rows=tuple(episode_rows),
        team_rows=tuple(team_rows),
        metric_rows=tuple(metric_rows),
    )


def _csv_bytes(rows: Iterable[Mapping[str, Any]], fields: tuple[str, ...]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def write_caller_fingerprint_snapshot(
    result: CallerFingerprintResult, root: str | Path
) -> Path:
    """Atomically publish caller episodes, forecasts, scores, and provenance."""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    parent = Path(root) / "caller_fingerprints" / str(result.season)
    destination = parent / timestamp
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"caller fingerprint snapshot already exists: {destination}")
    payloads = {
        "caller_episodes.csv": _csv_bytes(result.episode_rows, EPISODE_FIELDS),
        "teams.csv": _csv_bytes(result.team_rows, TEAM_FIELDS),
        "metric_forecasts.csv": _csv_bytes(result.metric_rows, METRIC_FIELDS),
    }
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "model_status": MODEL_STATUS,
        "season": result.season,
        "as_of": result.as_of.isoformat(),
        "methodology": {
            "primary_caller_rule": "Only audited primary play-calling episodes may become style anchors; title-only seasons are forbidden.",
            "full_season_rule": "A team-season aggregate is excluded when an audited midseason handoff makes full-season attribution invalid.",
            "recency_decay": RECENCY_DECAY,
            "forecast_blend": "Caller fingerprint, destination 2025 identity, and 2025 league median; weights depend on caller continuity and whether the caller was already on staff.",
            "outcome_exclusion": "EPA, success, and explosive-play rates are not projected as play-style identity.",
            "warning": "All certainty values and blend weights are uncalibrated evidence scores pending time-correct transition backtests.",
            "transition_ceiling": "Changed-caller teams are capped at 79.0 exact-style certainty until the new caller/team combination produces regular-season evidence.",
        },
        "inputs": [
            {"path": str(path), "sha256": result.input_hashes[str(path)]}
            for path in result.input_paths
        ],
        "quality": {
            "team_count": len(result.team_rows),
            "episode_count": len(result.episode_rows),
            "usable_full_season_episode_count": sum(
                row["full_team_season_anchor"] == "true" for row in result.episode_rows
            ),
            "teams_without_recent_full_season_anchor": [
                row["team"]
                for row in result.team_rows
                if int(row["recent_full_season_anchor_count"]) == 0
            ],
            "style_metric_count": len(STYLE_METRICS),
            "metric_forecast_count": len(result.metric_rows),
        },
        "artifacts": {},
    }
    fields_by_name = {
        "caller_episodes.csv": EPISODE_FIELDS,
        "teams.csv": TEAM_FIELDS,
        "metric_forecasts.csv": METRIC_FIELDS,
    }
    for name, payload in payloads.items():
        manifest["artifacts"][name] = {
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "fields": list(fields_by_name[name]),
        }
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
    try:
        for name, payload in payloads.items():
            (staging / name).write_bytes(payload)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
