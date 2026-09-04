import csv
import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fantasy_draft.sources.nflverse_player_history import (
    NflversePlayerHistoryQuery,
    parse_nflverse_player_history,
    write_nflverse_player_history_snapshot,
)


def csv_bytes(fields, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


ROSTER_FIELDS = [
    "season", "team", "position", "status", "full_name", "gsis_id", "week",
    "game_type", "status_description_abbr",
]
OLD_DEPTH_FIELDS = [
    "season", "club_code", "week", "game_type", "depth_team", "formation",
    "gsis_id", "position", "depth_position", "full_name",
]
NEW_DEPTH_FIELDS = [
    "dt", "team", "player_name", "gsis_id", "pos_grp", "pos_abb", "pos_slot",
    "pos_rank",
]
STATS_FIELDS = [
    "player_id", "player_display_name", "position", "season", "week",
    "season_type", "team", "attempts", "sacks_suffered", "carries", "targets",
]
SCHEDULE_FIELDS = [
    "game_id", "season", "game_type", "week", "gameday", "away_team",
    "home_team",
]


class NflversePlayerHistorySourceTests(unittest.TestCase):
    def make_snapshot(self):
        rosters = {}
        for season in (2024, 2025):
            rosters[season] = csv_bytes(ROSTER_FIELDS, [
                {"season": season, "team": "AAA", "position": "QB", "status": "ACT", "full_name": "Alpha QB", "gsis_id": "q1", "week": 1, "game_type": "REG", "status_description_abbr": "A01"},
                {"season": season, "team": "AAA", "position": "FB", "status": "INA", "full_name": "Beta Back", "gsis_id": "r1", "week": 1, "game_type": "REG", "status_description_abbr": "A01"},
                {"season": season, "team": "AAA", "position": "QB", "status": "ACT", "full_name": "Alpha QB", "gsis_id": "q1", "week": 2, "game_type": "REG", "status_description_abbr": "A01"},
            ])
        old_depth = csv_bytes(OLD_DEPTH_FIELDS, [
            {"season": 2024, "club_code": "AAA", "week": 1, "game_type": "REG", "depth_team": 1, "formation": "Offense", "gsis_id": "q1", "position": "QB", "depth_position": "QB", "full_name": "Alpha QB"},
            {"season": 2024, "club_code": "AAA", "week": 2, "game_type": "REG", "depth_team": 2, "formation": "Offense", "gsis_id": "q1", "position": "QB", "depth_position": "QB", "full_name": "Alpha QB"},
        ])
        new_depth = csv_bytes(NEW_DEPTH_FIELDS, [
            {"dt": "2025-09-03T07:00:00Z", "team": "AAA", "player_name": "Alpha QB", "gsis_id": "q1", "pos_grp": "Offense", "pos_abb": "QB", "pos_slot": 9, "pos_rank": 1},
            {"dt": "2025-09-04T07:00:00Z", "team": "AAA", "player_name": "Late QB", "gsis_id": "q2", "pos_grp": "Offense", "pos_abb": "QB", "pos_slot": 9, "pos_rank": 1},
        ])
        stats = {}
        for season in (2023, 2024, 2025):
            stats[season] = csv_bytes(STATS_FIELDS, [
                {"player_id": "q1", "player_display_name": "Alpha QB", "position": "QB", "season": season, "week": 1, "season_type": "REG", "team": "AAA", "attempts": 30, "sacks_suffered": 2, "carries": 4, "targets": 0},
            ])
        schedule = csv_bytes(SCHEDULE_FIELDS, [
            {"game_id": "2024_01_AAA_BBB", "season": 2024, "game_type": "REG", "week": 1, "gameday": "2024-09-05", "away_team": "AAA", "home_team": "BBB"},
            {"game_id": "2025_01_AAA_BBB", "season": 2025, "game_type": "REG", "week": 1, "gameday": "2025-09-04", "away_team": "AAA", "home_team": "BBB"},
        ])
        return parse_nflverse_player_history(
            NflversePlayerHistoryQuery((2024, 2025), (2024, 2025), 1, 1, 2025),
            weekly_rosters=rosters,
            depth_charts={2024: old_depth, 2025: new_depth},
            weekly_stats=stats,
            schedule=schedule,
            retrieved_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
        )

    def test_normalizes_weekly_rosters_and_opportunities(self):
        snapshot = self.make_snapshot()
        back = next(row for row in snapshot.weekly_rosters if row["gsis_id"] == "r1")
        self.assertEqual(back["position"], "RB")
        qb = next(row for row in snapshot.weekly_opportunities if row["season"] == 2025)
        self.assertEqual(qb["dropbacks"], "32.000000")
        self.assertEqual(len(snapshot.team_schedule), 4)

    def test_uses_week_one_old_schema_and_strict_dated_cutoff(self):
        snapshot = self.make_snapshot()
        old = next(row for row in snapshot.opening_depth if row["season"] == 2024)
        new = next(row for row in snapshot.opening_depth if row["season"] == 2025)
        self.assertEqual(old["temporal_precision"], "week_1_label_only_no_source_timestamp")
        self.assertEqual(new["source_timestamp"], "2025-09-03T07:00:00Z")
        self.assertFalse(any(row["gsis_id"] == "q2" for row in snapshot.opening_depth))

    def test_writes_hash_verified_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_nflverse_player_history_snapshot(self.make_snapshot(), directory)
            manifest = json.loads((path / "manifest.json").read_text())
            raw = (path / "opening_depth.csv").read_bytes()
            self.assertEqual(
                manifest["artifacts"]["normalized"]["opening_depth.csv"]["sha256"],
                hashlib.sha256(raw).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
