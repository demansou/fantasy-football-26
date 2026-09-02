import unittest

from fantasy_draft.models import PlayerProjection, ScoringSettings
from fantasy_draft.scoring import projected_fantasy_points


class ScoringTests(unittest.TestCase):
    def test_full_ppr_points_are_recomputed_from_stats(self) -> None:
        player = PlayerProjection(
            player_id="wr-1",
            name="Receiver One",
            position="WR",
            team="TST",
            receptions=100,
            receiving_yards=1_000,
            receiving_touchdowns=10,
            fumbles_lost=2,
        )

        points = projected_fantasy_points(player, ScoringSettings(receptions=1.0))

        self.assertAlmostEqual(points, 256.0)

    def test_scoring_change_changes_projection(self) -> None:
        player = PlayerProjection(
            player_id="wr-1",
            name="Receiver One",
            position="WR",
            team="TST",
            receptions=100,
            receiving_yards=1_000,
        )

        full_ppr = projected_fantasy_points(player, ScoringSettings(receptions=1.0))
        half_ppr = projected_fantasy_points(player, ScoringSettings(receptions=0.5))

        self.assertEqual(full_ppr - half_ppr, 50.0)

    def test_explicit_points_override_raw_stats(self) -> None:
        player = PlayerProjection(
            player_id="dst-1",
            name="Defense One",
            position="DST",
            team="TST",
            projected_points=137.5,
        )

        self.assertEqual(projected_fantasy_points(player, ScoringSettings()), 137.5)


if __name__ == "__main__":
    unittest.main()
