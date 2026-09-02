import tempfile
import unittest
from pathlib import Path

from fantasy_draft.io import load_projections, load_team_profiles


class ProjectionIoTests(unittest.TestCase):
    def test_loads_minimal_projection_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "projections.csv"
            path.write_text(
                "player_id,name,position,team,projected_points,adp\n"
                "player-1,Player One,WR,TST,250.5,14.2\n",
                encoding="utf-8",
            )

            projections = load_projections(path)

        self.assertEqual(len(projections), 1)
        self.assertEqual(projections[0].projected_points, 250.5)
        self.assertEqual(projections[0].adp, 14.2)

    def test_rejects_unknown_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "projections.csv"
            path.write_text(
                "player_id,name,position,team,typo_points\n"
                "player-1,Player One,WR,TST,250.5\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "unknown projection columns"):
                load_projections(path)

    def test_loads_normalized_team_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "teams.csv"
            path.write_text(
                "team,pass_volume_rating,qb_play_rating,run_blocking_rating\n"
                "TST,0.8,0.7,0.6\n",
                encoding="utf-8",
            )

            profiles = load_team_profiles(path)

        self.assertEqual(profiles[0].team, "TST")
        self.assertEqual(profiles[0].pass_volume_rating, 0.8)


if __name__ == "__main__":
    unittest.main()
