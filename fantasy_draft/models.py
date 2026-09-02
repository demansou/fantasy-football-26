"""Domain models and configuration validation for the draft optimizer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


OFFENSIVE_POSITIONS = ("QB", "RB", "WR", "TE")
ALL_POSITIONS = (*OFFENSIVE_POSITIONS, "K", "DST")


def normalize_position(position: str) -> str:
    normalized = position.strip().upper().replace("D/ST", "DST").replace("DEF", "DST")
    if normalized not in ALL_POSITIONS:
        raise ValueError(f"unsupported position {position!r}; expected one of {ALL_POSITIONS}")
    return normalized


def _number(mapping: Mapping[str, Any], key: str, default: float) -> float:
    value = mapping.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    return float(value)


def _integer(mapping: Mapping[str, Any], key: str, default: int) -> int:
    value = mapping.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


@dataclass(frozen=True)
class ScoringSettings:
    """Point modifiers for projected player statistics."""

    passing_yards: float = 0.04
    passing_touchdowns: float = 4.0
    interceptions: float = -1.0
    rushing_yards: float = 0.1
    rushing_touchdowns: float = 6.0
    receptions: float = 1.0
    receiving_yards: float = 0.1
    receiving_touchdowns: float = 6.0
    two_point_conversions: float = 2.0
    fumbles_lost: float = -2.0
    return_touchdowns: float = 6.0
    field_goals_0_39: float = 3.0
    field_goals_40_49: float = 4.0
    field_goals_50_plus: float = 5.0
    extra_points: float = 1.0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ScoringSettings":
        defaults = cls()
        return cls(
            **{
                name: _number(data, name, getattr(defaults, name))
                for name in cls.__dataclass_fields__
            }
        )


@dataclass(frozen=True)
class FlexSlot:
    name: str
    count: int
    eligible: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FlexSlot":
        name = str(data.get("name", "FLEX")).strip().upper()
        count = _integer(data, "count", 1)
        raw_eligible = data.get("eligible", ["RB", "WR", "TE"])
        if not isinstance(raw_eligible, list) or not raw_eligible:
            raise ValueError(f"{name}.eligible must be a non-empty list")
        eligible = tuple(normalize_position(str(position)) for position in raw_eligible)
        if count < 0:
            raise ValueError(f"{name}.count cannot be negative")
        return cls(name=name, count=count, eligible=eligible)


@dataclass(frozen=True)
class RosterSettings:
    starters: Mapping[str, int]
    flex: tuple[FlexSlot, ...] = ()
    bench: int = 6
    ir: int = 2
    position_limits: Mapping[str, int] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RosterSettings":
        raw_starters = data.get("starters", {})
        if not isinstance(raw_starters, Mapping):
            raise ValueError("roster.starters must be an object")
        starters: dict[str, int] = {}
        for raw_position, raw_count in raw_starters.items():
            position = normalize_position(str(raw_position))
            if isinstance(raw_count, bool) or not isinstance(raw_count, int) or raw_count < 0:
                raise ValueError(f"starter count for {position} must be a non-negative integer")
            starters[position] = raw_count

        raw_flex = data.get("flex", [])
        if not isinstance(raw_flex, list):
            raise ValueError("roster.flex must be a list")
        flex = tuple(FlexSlot.from_dict(item) for item in raw_flex)

        raw_limits = data.get("position_limits", {})
        if not isinstance(raw_limits, Mapping):
            raise ValueError("roster.position_limits must be an object")
        position_limits: dict[str, int] = {}
        for raw_position, raw_limit in raw_limits.items():
            position = normalize_position(str(raw_position))
            if isinstance(raw_limit, bool) or not isinstance(raw_limit, int) or raw_limit < 0:
                raise ValueError(f"position limit for {position} must be a non-negative integer")
            position_limits[position] = raw_limit

        bench = _integer(data, "bench", 6)
        ir = _integer(data, "ir", 2)
        if bench < 0 or ir < 0:
            raise ValueError("bench and IR counts cannot be negative")
        return cls(
            starters=starters,
            flex=flex,
            bench=bench,
            ir=ir,
            position_limits=position_limits,
        )

    @property
    def draft_rounds(self) -> int:
        return sum(self.starters.values()) + sum(slot.count for slot in self.flex) + self.bench

    @property
    def total_flex_slots(self) -> int:
        return sum(slot.count for slot in self.flex)


@dataclass(frozen=True)
class StrategySettings:
    """Weights for the explainable recommendation model."""

    vorp_weight: float = 1.0
    starter_need_weight: float = 0.40
    scarcity_weight: float = 0.30
    adp_weight: float = 0.35
    analytics_weight: float = 10.0
    upside_weight: float = 0.10
    downside_weight: float = 0.08
    late_need_boost: float = 1.0
    position_run_boost: float = 0.75
    long_turn_adp_boost: float = 0.35
    qb_variance_penalty: float = 16.0
    specialist_round: int = 13
    early_specialist_penalty: float = 8.0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "StrategySettings":
        defaults = cls()
        values: dict[str, float | int] = {}
        for name in cls.__dataclass_fields__:
            default = getattr(defaults, name)
            if isinstance(default, int):
                values[name] = _integer(data, name, default)
            else:
                values[name] = _number(data, name, default)
        if values["specialist_round"] < 1:
            raise ValueError("strategy.specialist_round must be positive")
        return cls(**values)


@dataclass(frozen=True)
class LeagueSettings:
    name: str
    teams: int
    roster: RosterSettings
    scoring: ScoringSettings
    strategy: StrategySettings = field(default_factory=StrategySettings)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LeagueSettings":
        teams = _integer(data, "teams", 10)
        if teams < 2:
            raise ValueError("a league must contain at least two teams")
        roster_data = data.get("roster", {})
        scoring_data = data.get("scoring", {})
        strategy_data = data.get("strategy", {})
        if not all(isinstance(item, Mapping) for item in (roster_data, scoring_data, strategy_data)):
            raise ValueError("roster, scoring, and strategy must be objects")
        return cls(
            name=str(data.get("name", "Fantasy league")),
            teams=teams,
            roster=RosterSettings.from_dict(roster_data),
            scoring=ScoringSettings.from_dict(scoring_data),
            strategy=StrategySettings.from_dict(strategy_data),
        )


@dataclass(frozen=True)
class TeamProfile:
    """Normalized team environment inputs.

    Ratings are percentiles on a 0-to-1 scale. A value of 0.5 is neutral, so a
    missing profile never silently helps or hurts a player.
    """

    team: str
    pass_volume_rating: float = 0.5
    rush_volume_rating: float = 0.5
    qb_play_rating: float = 0.5
    play_caller_rating: float = 0.5
    pass_blocking_rating: float = 0.5
    run_blocking_rating: float = 0.5
    pace_rating: float = 0.5
    scoring_environment_rating: float = 0.5
    positive_game_script_rating: float = 0.5
    continuity_rating: float = 0.5

    def __post_init__(self) -> None:
        object.__setattr__(self, "team", self.team.strip().upper())
        if not self.team:
            raise ValueError("team profile needs a team abbreviation")
        for field_name in self.__dataclass_fields__:
            if field_name == "team":
                continue
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} for {self.team} must be between 0 and 1")


@dataclass(frozen=True)
class PlayerProjection:
    player_id: str
    name: str
    position: str
    team: str
    bye_week: int | None = None
    adp: float | None = None
    projected_points: float | None = None
    floor_points: float | None = None
    ceiling_points: float | None = None
    passing_yards: float = 0.0
    passing_touchdowns: float = 0.0
    interceptions: float = 0.0
    rushing_yards: float = 0.0
    rushing_touchdowns: float = 0.0
    receptions: float = 0.0
    receiving_yards: float = 0.0
    receiving_touchdowns: float = 0.0
    two_point_conversions: float = 0.0
    fumbles_lost: float = 0.0
    return_touchdowns: float = 0.0
    field_goals_0_39: float = 0.0
    field_goals_40_49: float = 0.0
    field_goals_50_plus: float = 0.0
    extra_points: float = 0.0
    team_offense_rating: float = 0.5
    offensive_line_rating: float = 0.5
    role_security: float = 0.5
    injury_risk: float = 0.0
    upside_rating: float = 0.5
    opportunity_rating: float = 0.5
    high_value_usage_rating: float = 0.5
    competition_rating: float = 0.5
    efficiency_rating: float = 0.5
    receiving_role_rating: float = 0.5
    rushing_floor_rating: float = 0.5
    weekly_variance: float = 0.5

    def __post_init__(self) -> None:
        object.__setattr__(self, "position", normalize_position(self.position))
        object.__setattr__(self, "team", self.team.strip().upper())
        if not self.player_id.strip() or not self.name.strip() or not self.team:
            raise ValueError("player_id, name, and team are required")
        if self.bye_week is not None and not 1 <= self.bye_week <= 18:
            raise ValueError(f"bye week for {self.name} must be between 1 and 18")
        for field_name in (
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
        ):
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} for {self.name} must be between 0 and 1")
        if self.floor_points is not None and self.ceiling_points is not None:
            if self.floor_points > self.ceiling_points:
                raise ValueError(f"floor exceeds ceiling for {self.name}")


@dataclass(frozen=True)
class DraftPick:
    player_id: str
    team: int

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DraftPick":
        team = _integer(data, "team", 0)
        player_id = str(data.get("player_id", "")).strip()
        if not player_id:
            raise ValueError("every drafted player needs a player_id")
        if team < 1:
            raise ValueError("drafted team numbers are one-based")
        return cls(player_id=player_id, team=team)


@dataclass(frozen=True)
class DraftState:
    my_team: int
    draft_slot: int
    drafted: tuple[DraftPick, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DraftState":
        raw_drafted = data.get("drafted", [])
        if not isinstance(raw_drafted, list):
            raise ValueError("drafted must be a list")
        return cls(
            my_team=_integer(data, "my_team", 1),
            draft_slot=_integer(data, "draft_slot", 1),
            drafted=tuple(DraftPick.from_dict(item) for item in raw_drafted),
        )

    @property
    def current_pick(self) -> int:
        return len(self.drafted) + 1

    @property
    def my_player_ids(self) -> tuple[str, ...]:
        return tuple(pick.player_id for pick in self.drafted if pick.team == self.my_team)

    @property
    def drafted_player_ids(self) -> frozenset[str]:
        return frozenset(pick.player_id for pick in self.drafted)
