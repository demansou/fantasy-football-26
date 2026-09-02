"""Translate stat projections into league-specific fantasy points."""

from __future__ import annotations

from .models import PlayerProjection, ScoringSettings


SCORING_FIELDS = (
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
)


def projected_fantasy_points(
    player: PlayerProjection,
    scoring: ScoringSettings,
) -> float:
    """Return season points under ``scoring``.

    ``projected_points`` is an explicit override for sources that publish only
    fantasy-point projections (most useful for DST). Otherwise points are
    recomputed from raw projected statistics so league scoring changes flow
    through the rankings.
    """

    if player.projected_points is not None:
        return player.projected_points
    return sum(getattr(player, field) * getattr(scoring, field) for field in SCORING_FIELDS)


def projected_range(player: PlayerProjection, points: float) -> tuple[float, float]:
    """Return an explicit uncertainty range, or a conservative neutral range."""

    floor = player.floor_points if player.floor_points is not None else points
    ceiling = player.ceiling_points if player.ceiling_points is not None else points
    return floor, ceiling
