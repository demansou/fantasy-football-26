"""JSON and CSV adapters for league, projection, and draft-state data."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .models import DraftState, LeagueSettings, PlayerProjection, TeamProfile


OPTIONAL_FLOAT_FIELDS = {"adp", "projected_points", "floor_points", "ceiling_points"}
FLOAT_FIELDS = {
    "passing_yards",
    "passing_touchdowns",
    "interceptions",
    "rushing_yards",
    "rushing_touchdowns",
    "receptions",
    "receiving_yards",
    "receiving_touchdowns",
    "two_point_conversions",
    "fumbles_lost",
    "return_touchdowns",
    "field_goals_0_39",
    "field_goals_40_49",
    "field_goals_50_plus",
    "extra_points",
    "team_offense_rating",
    "offensive_line_rating",
    "role_security",
    "injury_risk",
    "upside_rating",
    "opportunity_rating",
    "high_value_usage_rating",
    "competition_rating",
    "efficiency_rating",
    "receiving_role_rating",
    "rushing_floor_rating",
    "weekly_variance",
}
INTEGER_FIELDS = {"bye_week"}
STRING_FIELDS = {"player_id", "name", "position", "team"}
PROJECTION_FIELDS = STRING_FIELDS | INTEGER_FIELDS | FLOAT_FIELDS | OPTIONAL_FLOAT_FIELDS
TEAM_PROFILE_FLOAT_FIELDS = {
    "pass_volume_rating",
    "rush_volume_rating",
    "qb_play_rating",
    "play_caller_rating",
    "pass_blocking_rating",
    "run_blocking_rating",
    "pace_rating",
    "scoring_environment_rating",
    "positive_game_script_rating",
    "continuity_rating",
}
TEAM_PROFILE_FIELDS = {"team"} | TEAM_PROFILE_FLOAT_FIELDS


def _load_json(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def load_league(path: str | Path) -> LeagueSettings:
    data = _load_json(path)
    if not isinstance(data, dict):
        raise ValueError("league JSON must contain an object")
    return LeagueSettings.from_dict(data)


def load_draft_state(path: str | Path) -> DraftState:
    data = _load_json(path)
    if not isinstance(data, dict):
        raise ValueError("draft-state JSON must contain an object")
    return DraftState.from_dict(data)


def load_projections(path: str | Path) -> list[PlayerProjection]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("projection CSV is missing a header")
        unknown_fields = set(reader.fieldnames) - PROJECTION_FIELDS
        if unknown_fields:
            raise ValueError(f"unknown projection columns: {', '.join(sorted(unknown_fields))}")
        missing_required = {"player_id", "name", "position", "team"} - set(reader.fieldnames)
        if missing_required:
            raise ValueError(f"missing projection columns: {', '.join(sorted(missing_required))}")

        projections: list[PlayerProjection] = []
        for row_number, row in enumerate(reader, start=2):
            values: dict[str, object] = {}
            try:
                for field_name, raw_value in row.items():
                    value = (raw_value or "").strip()
                    if field_name in STRING_FIELDS:
                        values[field_name] = value
                    elif not value:
                        if field_name in OPTIONAL_FLOAT_FIELDS or field_name in INTEGER_FIELDS:
                            values[field_name] = None
                    elif field_name in INTEGER_FIELDS:
                        values[field_name] = int(value)
                    else:
                        values[field_name] = float(value)
                projections.append(PlayerProjection(**values))
            except (TypeError, ValueError) as error:
                raise ValueError(f"invalid projection row {row_number}: {error}") from error
    if not projections:
        raise ValueError("projection CSV contains no players")
    return projections


def load_team_profiles(path: str | Path) -> list[TeamProfile]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("team-profile CSV is missing a header")
        unknown_fields = set(reader.fieldnames) - TEAM_PROFILE_FIELDS
        if unknown_fields:
            raise ValueError(f"unknown team-profile columns: {', '.join(sorted(unknown_fields))}")
        if "team" not in reader.fieldnames:
            raise ValueError("team-profile CSV is missing the team column")

        profiles: list[TeamProfile] = []
        for row_number, row in enumerate(reader, start=2):
            values: dict[str, object] = {"team": (row.get("team") or "").strip()}
            try:
                for field_name in TEAM_PROFILE_FLOAT_FIELDS:
                    value = (row.get(field_name) or "").strip()
                    if value:
                        values[field_name] = float(value)
                profiles.append(TeamProfile(**values))
            except (TypeError, ValueError) as error:
                raise ValueError(f"invalid team-profile row {row_number}: {error}") from error
    if not profiles:
        raise ValueError("team-profile CSV contains no teams")
    return profiles
