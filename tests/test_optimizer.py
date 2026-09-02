import unittest

from fantasy_draft.models import (
    DraftPick,
    DraftState,
    LeagueSettings,
    PlayerProjection,
    TeamProfile,
)
from fantasy_draft.optimizer import DraftOptimizer


def player(player_id: str, position: str, points: float, *, adp: float | None = None) -> PlayerProjection:
    return PlayerProjection(
        player_id=player_id,
        name=player_id.upper(),
        position=position,
        team="TST",
        projected_points=points,
        adp=adp,
    )


class OptimizerTests(unittest.TestCase):
    def test_flex_demand_is_allocated_to_best_remaining_players(self) -> None:
        league = LeagueSettings.from_dict(
            {
                "teams": 2,
                "roster": {
                    "starters": {"RB": 1, "WR": 1},
                    "flex": [{"name": "FLEX", "count": 1, "eligible": ["RB", "WR"]}],
                    "bench": 0,
                    "ir": 0,
                },
            }
        )
        projections = [
            player("rb-1", "RB", 300),
            player("rb-2", "RB", 280),
            player("rb-3", "RB", 250),
            player("rb-4", "RB", 200),
            player("wr-1", "WR", 290),
            player("wr-2", "WR", 270),
            player("wr-3", "WR", 260),
            player("wr-4", "WR", 240),
        ]

        optimizer = DraftOptimizer(league, projections)

        self.assertEqual(optimizer.starter_demand["RB"], 3)
        self.assertEqual(optimizer.starter_demand["WR"], 3)
        self.assertEqual(optimizer.replacement_levels["RB"], 250)
        self.assertEqual(optimizer.replacement_levels["WR"], 260)

    def test_open_starter_need_beats_more_depth(self) -> None:
        league = LeagueSettings.from_dict(
            {
                "teams": 2,
                "roster": {
                    "starters": {"RB": 1, "WR": 1},
                    "bench": 1,
                    "ir": 0,
                },
            }
        )
        projections = [
            player("rb-1", "RB", 300, adp=1),
            player("rb-2", "RB", 250, adp=4),
            player("rb-3", "RB", 200, adp=6),
            player("wr-1", "WR", 290, adp=2),
            player("wr-2", "WR", 240, adp=5),
            player("wr-3", "WR", 190, adp=7),
        ]
        state = DraftState(
            my_team=1,
            draft_slot=1,
            drafted=(DraftPick(player_id="rb-1", team=1),),
        )

        recommendations = DraftOptimizer(league, projections).recommend(state)

        self.assertEqual(recommendations[0].player.player_id, "wr-1")
        self.assertIn("fills an open WR starter", recommendations[0].reasons)

    def test_early_kicker_penalty_is_visible(self) -> None:
        league = LeagueSettings.from_dict(
            {
                "teams": 2,
                "roster": {
                    "starters": {"RB": 1, "K": 1},
                    "bench": 0,
                    "ir": 0,
                },
                "strategy": {
                    "specialist_round": 3,
                    "early_specialist_penalty": 30,
                },
            }
        )
        projections = [
            player("rb-1", "RB", 220),
            player("rb-2", "RB", 200),
            player("k-1", "K", 170),
            player("k-2", "K", 140),
        ]

        recommendations = DraftOptimizer(league, projections).recommend(
            DraftState(my_team=1, draft_slot=1)
        )
        kicker = next(item for item in recommendations if item.player.player_id == "k-1")

        self.assertEqual(kicker.roster_penalty, -60)
        self.assertIn("K/DST timing penalty applies this early", kicker.reasons)

    def test_receiver_prefers_pass_volume_qb_and_play_caller_environment(self) -> None:
        league = LeagueSettings.from_dict(
            {
                "teams": 2,
                "roster": {"starters": {"WR": 1}, "bench": 0, "ir": 0},
            }
        )
        projections = [
            PlayerProjection("wr-good", "WR Good", "WR", "GOOD", projected_points=240),
            PlayerProjection("wr-bad", "WR Bad", "WR", "BAD", projected_points=240),
        ]
        profiles = [
            TeamProfile(
                "GOOD",
                pass_volume_rating=0.9,
                qb_play_rating=0.9,
                play_caller_rating=0.85,
            ),
            TeamProfile(
                "BAD",
                pass_volume_rating=0.2,
                qb_play_rating=0.2,
                play_caller_rating=0.25,
            ),
        ]

        recommendations = DraftOptimizer(league, projections, profiles).recommend(
            DraftState(my_team=1, draft_slot=1)
        )

        self.assertEqual(recommendations[0].player.player_id, "wr-good")
        self.assertIn(
            "high pass volume paired with strong QB play",
            recommendations[0].reasons,
        )

    def test_runner_prefers_rushing_volume_and_run_blocking(self) -> None:
        league = LeagueSettings.from_dict(
            {
                "teams": 2,
                "roster": {"starters": {"RB": 1}, "bench": 0, "ir": 0},
            }
        )
        projections = [
            PlayerProjection("rb-good", "RB Good", "RB", "GOOD", projected_points=235),
            PlayerProjection("rb-bad", "RB Bad", "RB", "BAD", projected_points=235),
        ]
        profiles = [
            TeamProfile("GOOD", rush_volume_rating=0.9, run_blocking_rating=0.9),
            TeamProfile("BAD", rush_volume_rating=0.2, run_blocking_rating=0.2),
        ]

        recommendations = DraftOptimizer(league, projections, profiles).recommend(
            DraftState(my_team=1, draft_slot=1)
        )

        self.assertEqual(recommendations[0].player.player_id, "rb-good")
        self.assertIn(
            "high rushing volume behind a strong run-blocking line",
            recommendations[0].reasons,
        )

    def test_low_variance_qb_wins_equal_projection_comparison(self) -> None:
        league = LeagueSettings.from_dict(
            {
                "teams": 2,
                "roster": {"starters": {"QB": 1}, "bench": 0, "ir": 0},
            }
        )
        projections = [
            PlayerProjection(
                "qb-stable",
                "QB Stable",
                "QB",
                "AAA",
                projected_points=320,
                weekly_variance=0.2,
            ),
            PlayerProjection(
                "qb-volatile",
                "QB Volatile",
                "QB",
                "BBB",
                projected_points=320,
                weekly_variance=0.8,
            ),
        ]

        recommendations = DraftOptimizer(league, projections).recommend(
            DraftState(my_team=1, draft_slot=1)
        )

        self.assertEqual(recommendations[0].player.player_id, "qb-stable")
        self.assertIn(
            "low projected weekly variance strengthens the QB grade",
            recommendations[0].reasons,
        )

    def test_recent_position_run_increases_live_scarcity_weight(self) -> None:
        league = LeagueSettings.from_dict(
            {
                "teams": 4,
                "roster": {
                    "starters": {"RB": 1, "WR": 1},
                    "bench": 1,
                    "ir": 0,
                },
            }
        )
        projections = [
            *(player(f"rb-{index}", "RB", 260 - 10 * index) for index in range(1, 6)),
            *(player(f"wr-{index}", "WR", 260 - 10 * index) for index in range(1, 6)),
        ]
        state = DraftState(
            my_team=4,
            draft_slot=4,
            drafted=(
                DraftPick("rb-1", 1),
                DraftPick("rb-2", 2),
                DraftPick("rb-3", 3),
                DraftPick("wr-1", 4),
            ),
        )

        recommendations = DraftOptimizer(league, projections).recommend(state)
        running_back = next(item for item in recommendations if item.player.position == "RB")

        self.assertGreater(
            running_back.adaptive_weights["scarcity"],
            league.strategy.scarcity_weight,
        )
        self.assertGreater(running_back.draft_signals["position_run_pressure"], 0)
        self.assertTrue(any("recent RB run" in reason for reason in running_back.reasons))


if __name__ == "__main__":
    unittest.main()
