import csv
import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fantasy_draft.sources.nflverse_players import (
    NflversePlayerQuery,
    parse_nflverse_player_context,
    write_nflverse_player_context_snapshot,
)


def csv_bytes(fields: list[str], rows: list[dict[str, object]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


PLAYERS_FIELDS = [
    "gsis_id",
    "display_name",
    "pfr_id",
    "espn_id",
    "birth_date",
    "latest_team",
    "status",
]
ROSTER_FIELDS = [
    "season",
    "team",
    "position",
    "depth_chart_position",
    "status",
    "full_name",
    "first_name",
    "last_name",
    "football_name",
    "gsis_id",
    "espn_id",
    "pfr_id",
    "yahoo_id",
    "sleeper_id",
    "pff_id",
    "rotowire_id",
    "fantasy_data_id",
    "birth_date",
    "years_exp",
    "week",
    "game_type",
    "status_description_abbr",
]
DEPTH_FIELDS = [
    "dt",
    "team",
    "player_name",
    "espn_id",
    "gsis_id",
    "pos_grp",
    "pos_name",
    "pos_abb",
    "pos_slot",
    "pos_rank",
]
STATS_FIELDS = [
    "player_id",
    "player_display_name",
    "position",
    "season",
    "week",
    "season_type",
    "game_id",
    "team",
    "attempts",
    "sacks_suffered",
    "carries",
    "targets",
    "receptions",
    "receiving_air_yards",
]
SNAP_FIELDS = [
    "game_id",
    "season",
    "game_type",
    "week",
    "player",
    "pfr_player_id",
    "position",
    "team",
    "offense_snaps",
]


class NflversePlayerSourceTests(unittest.TestCase):
    def make_snapshot(self):
        players = csv_bytes(
            PLAYERS_FIELDS,
            [
                {"gsis_id": "q1", "display_name": "Alpha QB", "pfr_id": "QBAl00", "espn_id": "1", "latest_team": "AAA", "status": "ACT"},
                {"gsis_id": "r1", "display_name": "Beta Back", "pfr_id": "BackBe00", "espn_id": "2", "latest_team": "AAA", "status": "ACT"},
                {"gsis_id": "r2", "display_name": "Moved Back", "pfr_id": "", "espn_id": "3", "latest_team": "BBB", "status": "DEV"},
            ],
        )
        roster = csv_bytes(
            ROSTER_FIELDS,
            [
                {"season": 2026, "team": "AAA", "position": "QB", "status": "ACT", "full_name": "Alpha QB", "first_name": "Alpha", "last_name": "QB", "football_name": "Alpha", "gsis_id": "q1", "espn_id": "1", "pfr_id": "QBAl00", "week": 1, "game_type": "REG"},
                {"season": 2026, "team": "AAA", "position": "RB", "status": "ACT", "full_name": "Beta Back", "first_name": "Beta", "last_name": "Back", "football_name": "Beta", "gsis_id": "r1", "espn_id": "2", "pfr_id": "BackBe00", "week": 1, "game_type": "REG"},
                {"season": 2026, "team": "OLD", "position": "RB", "status": "CUT", "full_name": "Moved Back", "first_name": "Moved", "last_name": "Back", "football_name": "Moved", "gsis_id": "r2", "espn_id": "3", "week": 1, "game_type": "REG"},
            ],
        )
        depth = csv_bytes(
            DEPTH_FIELDS,
            [
                {"dt": "2026-08-01T10:00:00Z", "team": "AAA", "player_name": "Alpha QB", "espn_id": "1", "gsis_id": "q1", "pos_grp": "Offense", "pos_name": "Quarterback", "pos_abb": "QB", "pos_slot": 9, "pos_rank": 2},
                {"dt": "2026-09-02T10:00:00Z", "team": "AAA", "player_name": "Alpha QB", "espn_id": "1", "gsis_id": "q1", "pos_grp": "Offense", "pos_name": "Quarterback", "pos_abb": "QB", "pos_slot": 9, "pos_rank": 1},
                {"dt": "2026-09-02T10:00:00Z", "team": "AAA", "player_name": "Beta Back", "espn_id": "2", "gsis_id": "", "pos_grp": "Offense", "pos_name": "Running Back", "pos_abb": "RB", "pos_slot": 11, "pos_rank": 1},
                {"dt": "2026-09-02T10:00:00Z", "team": "AAA", "player_name": "Unknown", "espn_id": "", "gsis_id": "", "pos_grp": "Offense", "pos_name": "Tight End", "pos_abb": "TE", "pos_slot": 10, "pos_rank": 4},
            ],
        )
        stats = csv_bytes(
            STATS_FIELDS,
            [
                {"player_id": "q1", "player_display_name": "Alpha QB", "position": "QB", "season": 2025, "week": 1, "season_type": "REG", "game_id": "g1", "team": "AAA", "attempts": 30, "sacks_suffered": 2, "carries": 4, "targets": 0, "receptions": 0, "receiving_air_yards": 0},
                {"player_id": "r1", "player_display_name": "Beta Back", "position": "RB", "season": 2025, "week": 1, "season_type": "REG", "game_id": "g1", "team": "AAA", "attempts": 0, "sacks_suffered": 0, "carries": 20, "targets": 5, "receptions": 4, "receiving_air_yards": -2},
            ],
        )
        snaps = csv_bytes(
            SNAP_FIELDS,
            [
                {"game_id": "g1", "season": 2025, "game_type": "REG", "week": 1, "player": "Alpha QB", "pfr_player_id": "QBAl00", "position": "QB", "team": "AAA", "offense_snaps": 60},
                {"game_id": "g1", "season": 2025, "game_type": "REG", "week": 1, "player": "Beta Back", "pfr_player_id": "BackBe00", "position": "RB", "team": "AAA", "offense_snaps": 36},
            ],
        )
        return parse_nflverse_player_context(
            NflversePlayerQuery(2026, (2025,)),
            players=players,
            roster=roster,
            depth_charts=depth,
            weekly_stats={2025: stats},
            snap_counts={2025: snaps},
            retrieved_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
        )

    def test_selects_latest_depth_and_joins_only_by_ids(self) -> None:
        snapshot = self.make_snapshot()
        self.assertEqual(snapshot.latest_depth_by_team["AAA"], "2026-09-02T10:00:00Z")
        beta = next(row for row in snapshot.current_depth_chart if row["player_name"] == "Beta Back")
        self.assertEqual(beta["canonical_gsis_id"], "r1")
        self.assertEqual(beta["identity_method"], "unique_espn_id")
        self.assertTrue(any(row["issue"] == "missing_resolvable_player_id" for row in snapshot.identity_review))

    def test_aggregates_box_score_opportunity_and_pfr_snaps(self) -> None:
        snapshot = self.make_snapshot()
        qb = next(row for row in snapshot.historical_usage if row["gsis_id"] == "q1")
        rb = next(row for row in snapshot.historical_usage if row["gsis_id"] == "r1")
        self.assertEqual(qb["dropbacks"], "32")
        self.assertEqual(qb["offense_snap_share"], "1.000000")
        self.assertEqual(rb["carry_share_within_position"], "1.000000")
        self.assertEqual(rb["offense_snap_share"], "0.600000")

    def test_preserves_raw_roster_values_and_reconciles_current_affiliation(self) -> None:
        snapshot = self.make_snapshot()
        moved = next(row for row in snapshot.current_roster if row["gsis_id"] == "r2")
        self.assertEqual(moved["roster_team"], "OLD")
        self.assertEqual(moved["roster_status"], "CUT")
        self.assertEqual(moved["team"], "BBB")
        self.assertEqual(moved["current_status"], "DEV")
        review = next(
            row
            for row in snapshot.identity_review
            if row["source_player_id"] == "r2"
        )
        self.assertEqual(review["issue"], "roster_catalog_affiliation_disagreement")

    def test_writes_hashed_normalized_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = write_nflverse_player_context_snapshot(self.make_snapshot(), Path(directory))
            manifest = json.loads((path / "manifest.json").read_text())
            payload = (path / "historical_usage.csv").read_bytes()
            self.assertEqual(
                manifest["artifacts"]["normalized"]["historical_usage.csv"]["sha256"],
                hashlib.sha256(payload).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
