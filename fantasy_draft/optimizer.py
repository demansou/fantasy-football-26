"""Explainable value-based draft recommendations."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import ceil
from typing import Iterable

from .models import ALL_POSITIONS, DraftState, LeagueSettings, PlayerProjection, TeamProfile
from .scoring import projected_fantasy_points, projected_range


@dataclass(frozen=True)
class Recommendation:
    player: PlayerProjection
    projected_points: float
    replacement_points: float
    vorp: float
    vorp_component: float
    need_component: float
    scarcity_component: float
    adp_component: float
    analytics_component: float
    range_component: float
    roster_penalty: float
    adaptive_weights: dict[str, float]
    draft_signals: dict[str, float]
    score: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "player_id": self.player.player_id,
            "name": self.player.name,
            "position": self.player.position,
            "team": self.player.team,
            "bye_week": self.player.bye_week,
            "adp": self.player.adp,
            "projected_points": round(self.projected_points, 2),
            "replacement_points": round(self.replacement_points, 2),
            "vorp": round(self.vorp, 2),
            "components": {
                "vorp": round(self.vorp_component, 2),
                "need": round(self.need_component, 2),
                "scarcity": round(self.scarcity_component, 2),
                "adp": round(self.adp_component, 2),
                "analytics": round(self.analytics_component, 2),
                "range": round(self.range_component, 2),
                "roster_penalty": round(self.roster_penalty, 2),
            },
            "adaptive_weights": {
                name: round(value, 4) for name, value in self.adaptive_weights.items()
            },
            "draft_signals": {
                name: round(value, 4) for name, value in self.draft_signals.items()
            },
            "score": round(self.score, 2),
            "reasons": list(self.reasons),
        }


class DraftOptimizer:
    """Rank available players for one pick in a snake draft.

    The model is intentionally deterministic and decomposable. It combines
    value over a league-specific replacement player (VORP), current roster
    need, positional drop-off before the manager's next pick, ADP timing,
    position-specific player/team analytics, live draft pressure, and
    projection uncertainty.
    """

    def __init__(
        self,
        league: LeagueSettings,
        projections: Iterable[PlayerProjection],
        team_profiles: Iterable[TeamProfile] = (),
    ) -> None:
        self.league = league
        self.projections = tuple(projections)
        self.players_by_id = {player.player_id: player for player in self.projections}
        if len(self.players_by_id) != len(self.projections):
            raise ValueError("projection player_id values must be unique")
        profile_list = tuple(team_profiles)
        self.team_profiles = {profile.team: profile for profile in profile_list}
        if len(self.team_profiles) != len(profile_list):
            raise ValueError("team profile abbreviations must be unique")
        self.points_by_id = {
            player.player_id: projected_fantasy_points(player, league.scoring)
            for player in self.projections
        }
        self.players_by_position = {
            position: tuple(
                sorted(
                    (player for player in self.projections if player.position == position),
                    key=lambda player: (-self.points_by_id[player.player_id], player.name),
                )
            )
            for position in ALL_POSITIONS
        }
        self.starter_demand, self.replacement_levels = self._replacement_model()

    def recommend(
        self,
        state: DraftState,
        *,
        limit: int | None = None,
    ) -> list[Recommendation]:
        self._validate_state(state)
        roster = tuple(self.players_by_id[player_id] for player_id in state.my_player_ids)
        roster_counts = Counter(player.position for player in roster)
        available = [
            player
            for player in self.projections
            if player.player_id not in state.drafted_player_ids
            and self._position_is_used(player.position)
            and self._under_position_limit(player.position, roster_counts)
        ]
        next_pick = self._next_pick_after(state.current_pick, state.draft_slot)
        available_by_position = {
            position: tuple(
                sorted(
                    (player for player in available if player.position == position),
                    key=lambda player: (-self.points_by_id[player.player_id], player.name),
                )
            )
            for position in ALL_POSITIONS
        }

        recommendations = [
            self._score_player(
                player,
                state=state,
                roster=roster,
                roster_counts=roster_counts,
                available_by_position=available_by_position,
                next_pick=next_pick,
            )
            for player in available
        ]
        recommendations.sort(key=lambda item: (-item.score, -item.vorp, item.player.name))
        return recommendations if limit is None else recommendations[:limit]

    def _replacement_model(self) -> tuple[dict[str, int], dict[str, float]]:
        """Allocate league-wide fixed and flex starters, then find baselines."""

        demand = {
            position: self.league.teams * self.league.roster.starters.get(position, 0)
            for position in ALL_POSITIONS
        }

        for flex_slot in self.league.roster.flex:
            for _ in range(self.league.teams * flex_slot.count):
                candidates: list[tuple[float, str]] = []
                for position in flex_slot.eligible:
                    position_players = self.players_by_position[position]
                    next_index = demand[position]
                    if next_index < len(position_players):
                        next_player = position_players[next_index]
                        candidates.append((self.points_by_id[next_player.player_id], position))
                if not candidates:
                    break
                _, selected_position = max(candidates, key=lambda item: (item[0], item[1]))
                demand[selected_position] += 1

        levels: dict[str, float] = {}
        for position in ALL_POSITIONS:
            players = self.players_by_position[position]
            expected_starters = demand[position]
            if not players or expected_starters <= 0:
                levels[position] = 0.0
                continue
            replacement_index = min(expected_starters, len(players)) - 1
            levels[position] = self.points_by_id[players[replacement_index].player_id]
        return demand, levels

    def _score_player(
        self,
        player: PlayerProjection,
        *,
        state: DraftState,
        roster: tuple[PlayerProjection, ...],
        roster_counts: Counter[str],
        available_by_position: dict[str, tuple[PlayerProjection, ...]],
        next_pick: int,
    ) -> Recommendation:
        points = self.points_by_id[player.player_id]
        replacement = self.replacement_levels[player.position]
        vorp = points - replacement

        lineup_status = self._lineup_status(player.position, roster_counts)
        position_run_pressure = self._position_run_pressure(player.position, state)
        adaptive_weights, draft_signals = self._adaptive_weights(
            state=state,
            next_pick=next_pick,
            lineup_status=lineup_status,
            position_run_pressure=position_run_pressure,
        )
        vorp_component = vorp * adaptive_weights["vorp"]
        if lineup_status == "starter":
            need_raw = max(vorp, 0.0)
        elif lineup_status == "flex":
            need_raw = max(vorp, 0.0) * 0.65
        else:
            need_raw = -max(2.0, max(vorp, 0.0) * 0.12)
        need_component = need_raw * adaptive_weights["need"]

        scarcity_raw = self._scarcity(
            player,
            available_by_position[player.position],
            picks_until_next=max(1, next_pick - state.current_pick),
        )
        scarcity_component = scarcity_raw * adaptive_weights["scarcity"]

        adp_raw = self._adp_signal(player.adp, state.current_pick, next_pick)
        adp_component = adp_raw * adaptive_weights["adp"]

        context_signal, profile_reasons = self._position_context(player)
        analytics_component = context_signal * adaptive_weights["analytics"]
        if player.position == "QB":
            analytics_component += (
                0.5 - player.weekly_variance
            ) * adaptive_weights["qb_stability"]

        floor, ceiling = projected_range(player, points)
        range_component = (
            (ceiling - points) * adaptive_weights["upside"]
            - (points - floor) * adaptive_weights["downside"]
        )

        roster_penalty = self._roster_penalty(
            player,
            state=state,
            roster=roster,
            roster_counts=roster_counts,
            lineup_status=lineup_status,
        )
        score = (
            vorp_component
            + need_component
            + scarcity_component
            + adp_component
            + analytics_component
            + range_component
            + roster_penalty
        )
        reasons = self._reasons(
            player,
            points=points,
            vorp=vorp,
            lineup_status=lineup_status,
            scarcity=scarcity_raw,
            adp_signal=adp_raw,
            state=state,
            next_pick=next_pick,
            analytics_component=analytics_component,
            roster_penalty=roster_penalty,
            profile_reasons=profile_reasons,
            adaptive_weights=adaptive_weights,
            draft_signals=draft_signals,
        )
        return Recommendation(
            player=player,
            projected_points=points,
            replacement_points=replacement,
            vorp=vorp,
            vorp_component=vorp_component,
            need_component=need_component,
            scarcity_component=scarcity_component,
            adp_component=adp_component,
            analytics_component=analytics_component,
            range_component=range_component,
            roster_penalty=roster_penalty,
            adaptive_weights=adaptive_weights,
            draft_signals=draft_signals,
            score=score,
            reasons=reasons,
        )

    def _adaptive_weights(
        self,
        *,
        state: DraftState,
        next_pick: int,
        lineup_status: str,
        position_run_pressure: float,
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Adjust ranking weights from the live board without hiding the change."""

        strategy = self.league.strategy
        current_round = ceil(state.current_pick / self.league.teams)
        total_rounds = max(1, self.league.roster.draft_rounds)
        draft_progress = min(1.0, (current_round - 1) / max(1, total_rounds - 1))
        need_multiplier = (
            1.0 + strategy.late_need_boost * draft_progress
            if lineup_status in {"starter", "flex"}
            else 1.0
        )
        scarcity_multiplier = 1.0 + strategy.position_run_boost * position_run_pressure
        turn_fraction = min(
            1.0,
            max(0.0, (next_pick - state.current_pick - 1) / max(1, self.league.teams)),
        )
        adp_multiplier = 1.0 + strategy.long_turn_adp_boost * turn_fraction
        upside_multiplier = 1.2 if lineup_status == "bench" else 1.0
        weights = {
            "vorp": strategy.vorp_weight,
            "need": strategy.starter_need_weight * need_multiplier,
            "scarcity": strategy.scarcity_weight * scarcity_multiplier,
            "adp": strategy.adp_weight * adp_multiplier,
            "analytics": strategy.analytics_weight,
            "upside": strategy.upside_weight * upside_multiplier,
            "downside": strategy.downside_weight,
            "qb_stability": strategy.qb_variance_penalty,
        }
        signals = {
            "current_round": float(current_round),
            "draft_progress": draft_progress,
            "picks_until_next": float(max(1, next_pick - state.current_pick)),
            "position_run_pressure": position_run_pressure,
            "need_multiplier": need_multiplier,
            "scarcity_multiplier": scarcity_multiplier,
            "adp_multiplier": adp_multiplier,
        }
        return weights, signals

    def _position_run_pressure(self, position: str, state: DraftState) -> float:
        if not state.drafted:
            return 0.0
        window_size = min(len(state.drafted), max(6, self.league.teams))
        recent_picks = state.drafted[-window_size:]
        recent_positions = [self.players_by_id[pick.player_id].position for pick in recent_picks]
        observed_share = recent_positions.count(position) / len(recent_positions)
        expected_share = self.starter_demand[position] / max(1, sum(self.starter_demand.values()))
        relative_excess = (observed_share - expected_share) / max(0.05, expected_share)
        return min(1.0, max(0.0, relative_excess))

    def _position_context(self, player: PlayerProjection) -> tuple[float, tuple[str, ...]]:
        """Return a centered context signal and position-specific explanations."""

        team = self._team_profile(player)
        reasons: list[str] = []

        if player.position in {"WR", "TE"}:
            team_signal = self._weighted_centered(
                (team.pass_volume_rating, 0.30),
                (team.qb_play_rating, 0.27),
                (team.play_caller_rating, 0.18),
                (team.pace_rating, 0.10),
                (team.scoring_environment_rating, 0.10),
                (team.pass_blocking_rating, 0.05),
            )
            player_signal = self._weighted_centered(
                (player.opportunity_rating, 0.32),
                (player.high_value_usage_rating, 0.20),
                (player.efficiency_rating, 0.14),
                (player.competition_rating, 0.12),
                (player.role_security, 0.14),
                (player.upside_rating, 0.08),
            )
            context_signal = 0.55 * team_signal + 0.45 * player_signal
            if team.pass_volume_rating >= 0.65 and team.qb_play_rating >= 0.65:
                reasons.append("high pass volume paired with strong QB play")
            elif team.pass_volume_rating <= 0.35 or team.qb_play_rating <= 0.35:
                reasons.append("weak passing volume/QB environment lowers the grade")
            if team.play_caller_rating >= 0.70:
                reasons.append("strong OC/play-caller profile")
            if player.opportunity_rating >= 0.70:
                reasons.append("strong target-volume profile")

        elif player.position == "RB":
            team_signal = self._weighted_centered(
                (team.rush_volume_rating, 0.30),
                (team.run_blocking_rating, 0.28),
                (team.positive_game_script_rating, 0.16),
                (team.scoring_environment_rating, 0.12),
                (team.play_caller_rating, 0.09),
                (team.pace_rating, 0.05),
            )
            player_signal = self._weighted_centered(
                (player.opportunity_rating, 0.33),
                (player.high_value_usage_rating, 0.20),
                (player.receiving_role_rating, 0.16),
                (player.competition_rating, 0.11),
                (player.role_security, 0.12),
                (player.efficiency_rating, 0.08),
            )
            context_signal = 0.55 * team_signal + 0.45 * player_signal
            if team.rush_volume_rating >= 0.65 and team.run_blocking_rating >= 0.65:
                reasons.append("high rushing volume behind a strong run-blocking line")
            elif team.rush_volume_rating <= 0.35 or team.run_blocking_rating <= 0.35:
                reasons.append("weak rushing volume/line environment lowers the grade")
            if player.opportunity_rating >= 0.70:
                reasons.append("strong projected backfield share")
            if player.receiving_role_rating >= 0.70:
                reasons.append("valuable receiving role for PPR scoring")

        elif player.position == "QB":
            team_signal = self._weighted_centered(
                (team.play_caller_rating, 0.24),
                (team.pass_blocking_rating, 0.19),
                (team.pass_volume_rating, 0.18),
                (team.pace_rating, 0.14),
                (team.scoring_environment_rating, 0.14),
                (team.continuity_rating, 0.11),
            )
            player_signal = self._weighted_centered(
                (player.efficiency_rating, 0.25),
                (player.rushing_floor_rating, 0.22),
                (player.opportunity_rating, 0.18),
                (player.role_security, 0.15),
                (player.high_value_usage_rating, 0.10),
                (player.upside_rating, 0.10),
            )
            context_signal = 0.52 * team_signal + 0.48 * player_signal
            if player.weekly_variance <= 0.35:
                reasons.append("low projected weekly variance strengthens the QB grade")
            elif player.weekly_variance >= 0.65:
                reasons.append("high projected weekly variance lowers the QB grade")
            if team.play_caller_rating >= 0.65 and team.pass_blocking_rating >= 0.65:
                reasons.append("stable play-caller and pass-protection environment")
            if player.rushing_floor_rating >= 0.70:
                reasons.append("rushing production supports the weekly floor")

        else:
            context_signal = self._weighted_centered(
                (team.scoring_environment_rating, 0.50),
                (player.role_security, 0.30),
                (player.efficiency_rating, 0.20),
            )

        context_signal -= 0.35 * player.injury_risk
        return context_signal, tuple(reasons)

    def _team_profile(self, player: PlayerProjection) -> TeamProfile:
        profile = self.team_profiles.get(player.team.upper())
        if profile is not None:
            return profile
        # Backward-compatible fallback for projection files created before team
        # profiles were separated. Neutral values remain neutral.
        return TeamProfile(
            team=player.team,
            pass_volume_rating=player.team_offense_rating,
            rush_volume_rating=player.team_offense_rating,
            qb_play_rating=player.team_offense_rating,
            pass_blocking_rating=player.offensive_line_rating,
            run_blocking_rating=player.offensive_line_rating,
            scoring_environment_rating=player.team_offense_rating,
        )

    @staticmethod
    def _weighted_centered(*ratings: tuple[float, float]) -> float:
        return sum((value - 0.5) * weight for value, weight in ratings)

    def _scarcity(
        self,
        player: PlayerProjection,
        available_at_position: tuple[PlayerProjection, ...],
        *,
        picks_until_next: int,
    ) -> float:
        if len(available_at_position) <= 1:
            return 0.0
        total_demand = max(1, sum(self.starter_demand.values()))
        position_share = self.starter_demand[player.position] / total_demand
        expected_position_picks = max(1, ceil(picks_until_next * position_share))
        player_index = available_at_position.index(player)
        comparison_index = min(
            len(available_at_position) - 1,
            player_index + expected_position_picks,
        )
        comparison = available_at_position[comparison_index]
        return max(0.0, self.points_by_id[player.player_id] - self.points_by_id[comparison.player_id])

    @staticmethod
    def _adp_signal(adp: float | None, current_pick: int, next_pick: int) -> float:
        if adp is None:
            return 0.0
        turn_gap = max(1.0, float(next_pick - current_pick))
        if adp <= current_pick:
            return min(8.0, 2.0 + 6.0 * (current_pick - adp) / turn_gap)
        if adp <= next_pick:
            return 2.0 * (next_pick - adp) / turn_gap
        return -min(8.0, 6.0 * (adp - next_pick) / turn_gap)

    def _lineup_status(self, position: str, counts: Counter[str]) -> str:
        if counts[position] < self.league.roster.starters.get(position, 0):
            return "starter"

        for flex_slot in self.league.roster.flex:
            if position not in flex_slot.eligible:
                continue
            excess = sum(
                max(0, counts[eligible] - self.league.roster.starters.get(eligible, 0))
                for eligible in flex_slot.eligible
            )
            if excess < flex_slot.count:
                return "flex"
        return "bench"

    def _roster_penalty(
        self,
        player: PlayerProjection,
        *,
        state: DraftState,
        roster: tuple[PlayerProjection, ...],
        roster_counts: Counter[str],
        lineup_status: str,
    ) -> float:
        strategy = self.league.strategy
        current_round = ceil(state.current_pick / self.league.teams)
        penalty = 0.0
        if player.position in {"K", "DST"} and current_round < strategy.specialist_round:
            penalty -= (strategy.specialist_round - current_round) * strategy.early_specialist_penalty
        if lineup_status == "bench":
            starter_capacity = self.league.roster.starters.get(player.position, 0) + sum(
                slot.count for slot in self.league.roster.flex if player.position in slot.eligible
            )
            surplus = max(0, roster_counts[player.position] - starter_capacity + 1)
            penalty -= 2.0 * surplus

        if len(roster) >= max(1, self.league.roster.draft_rounds // 2) and player.bye_week:
            same_position_bye = sum(
                teammate.position == player.position and teammate.bye_week == player.bye_week
                for teammate in roster
            )
            penalty -= 1.5 * same_position_bye
        return penalty

    def _reasons(
        self,
        player: PlayerProjection,
        *,
        points: float,
        vorp: float,
        lineup_status: str,
        scarcity: float,
        adp_signal: float,
        state: DraftState,
        next_pick: int,
        analytics_component: float,
        roster_penalty: float,
        profile_reasons: tuple[str, ...],
        adaptive_weights: dict[str, float],
        draft_signals: dict[str, float],
    ) -> tuple[str, ...]:
        reasons = [f"{points:.1f} projected points; {vorp:+.1f} versus {player.position} replacement"]
        if lineup_status == "starter":
            reasons.append(f"fills an open {player.position} starter")
        elif lineup_status == "flex":
            reasons.append("fills an open flex slot")
        else:
            reasons.append("would currently be bench depth")
        if scarcity >= 3.0:
            reasons.append(f"{scarcity:.1f}-point positional drop before the next turn")
        if player.adp is not None:
            if adp_signal >= 2.0:
                reasons.append(f"ADP {player.adp:.1f} indicates value/urgency at pick {state.current_pick}")
            elif adp_signal < 0:
                reasons.append(f"ADP {player.adp:.1f} suggests the player may reach pick {next_pick}")
        reasons.extend(profile_reasons)
        if analytics_component >= 1.5 and not profile_reasons:
            reasons.append("positive position-specific team and player context")
        elif analytics_component <= -1.5 and not any("lowers" in reason for reason in profile_reasons):
            reasons.append("risk/context inputs reduce the grade")
        if draft_signals["position_run_pressure"] >= 0.25:
            boost = (
                adaptive_weights["scarcity"] / self.league.strategy.scarcity_weight - 1.0
                if self.league.strategy.scarcity_weight
                else 0.0
            )
            reasons.append(f"recent {player.position} run raised scarcity weight {boost:.0%}")
        if draft_signals["need_multiplier"] >= 1.25 and lineup_status in {"starter", "flex"}:
            reasons.append(
                f"round {draft_signals['current_round']:.0f} raises open-lineup urgency"
            )
        if roster_penalty <= -8.0 and player.position in {"K", "DST"}:
            reasons.append("K/DST timing penalty applies this early")
        return tuple(reasons)

    def _position_is_used(self, position: str) -> bool:
        if self.league.roster.starters.get(position, 0) > 0:
            return True
        return any(position in slot.eligible for slot in self.league.roster.flex)

    def _under_position_limit(self, position: str, counts: Counter[str]) -> bool:
        limit = self.league.roster.position_limits.get(position)
        return limit is None or counts[position] < limit

    def _next_pick_after(self, current_pick: int, draft_slot: int) -> int:
        for round_number in range(1, self.league.roster.draft_rounds + 2):
            if round_number % 2:
                pick = (round_number - 1) * self.league.teams + draft_slot
            else:
                pick = round_number * self.league.teams - draft_slot + 1
            if pick > current_pick:
                return pick
        return current_pick + self.league.teams

    def _validate_state(self, state: DraftState) -> None:
        if not 1 <= state.my_team <= self.league.teams:
            raise ValueError(f"my_team must be between 1 and {self.league.teams}")
        if not 1 <= state.draft_slot <= self.league.teams:
            raise ValueError(f"draft_slot must be between 1 and {self.league.teams}")
        unknown = sorted(state.drafted_player_ids - self.players_by_id.keys())
        if unknown:
            raise ValueError(f"draft state contains unknown player_id values: {', '.join(unknown)}")
        invalid_teams = sorted({pick.team for pick in state.drafted if pick.team > self.league.teams})
        if invalid_teams:
            raise ValueError(f"draft state contains team numbers above {self.league.teams}")
