import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fantasy_draft.resource_transform import (
    ResourceTransformError,
    derive_conversion_factors,
    load_verified_team_style,
    resource_forecasts,
)


class ResourceTransformTests(unittest.TestCase):
    def test_uses_pbp_denominators_and_normalizes_only_overflow(self) -> None:
        estimate = derive_conversion_factors(
            {
                (2025, "LAR"): {
                    "qb_dropbacks": 540,
                    "targets": 480,
                    "rb_carries": 360,
                }
            },
            [
                {
                    "season": "2025",
                    "team": "LA",
                    "plays": "1000",
                    "pass_rate": "0.6",
                    "designed_qb_run_share": "0.1",
                }
            ],
            training_seasons=(2025,),
            latest_season=2025,
        )
        self.assertEqual(estimate.team_season_count, 1)
        self.assertAlmostEqual(
            estimate.factors["qb_dropbacks_per_pass_play"], 0.9
        )
        self.assertAlmostEqual(estimate.factors["target_per_pass_play"], 0.8)
        self.assertAlmostEqual(
            estimate.factors["rb_carries_per_non_qb_rush_play"], 1.0
        )
        forecast = resource_forecasts(
            {
                "plays_per_game": 60,
                "pass_rate": 0.6,
                "qb_scramble_rate": 0.05,
                "designed_qb_run_share": 0.1,
                "rb_target_share": 0.21,
                "wr_target_share": 0.60,
                "te_target_share": 0.20,
            },
            estimate.factors,
        )
        self.assertAlmostEqual(forecast["QB_DROPBACKS"], 32.4)
        self.assertAlmostEqual(forecast["QB_RUSH_OPPORTUNITIES"], 4.2)
        self.assertAlmostEqual(forecast["RB_CARRIES"], 21.6)
        self.assertAlmostEqual(
            forecast["RB_TARGETS"]
            + forecast["WR_TARGETS"]
            + forecast["TE_TARGETS"],
            28.8,
        )

    def test_verified_style_loader_rejects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = (
                b"season,team,plays,pass_rate,designed_qb_run_share\n"
                b"2025,AAA,1000,0.6,0.1\n"
            )
            (root / "team_style.csv").write_bytes(raw)
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "artifacts": {
                            "normalized": {
                                "path": "team_style.csv",
                                "sha256": hashlib.sha256(raw).hexdigest(),
                            }
                        }
                    }
                )
            )
            loaded = load_verified_team_style(root)
            self.assertEqual(loaded.rows[0]["team"], "AAA")
            with (root / "team_style.csv").open("ab") as handle:
                handle.write(b"tampered")
            with self.assertRaisesRegex(ResourceTransformError, "hash mismatch"):
                load_verified_team_style(root)


if __name__ == "__main__":
    unittest.main()
