import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from fantasy_draft.cli import main
from fantasy_draft.season import fetch_usage, load_state, parse_usage, research, update_state, write_new

STATE = {'version': 1, 'season': 2026, 'startedAt': 1, 'updatedAt': 1,
         'teams': ['Mine', 'Other'], 'myTeam': 0, 'capacity': 16,
         'draft': [{'playerId': 'a', 'overall': 1, 'teamIndex': 0}],
         'owners': {'a': {'team': 0, 'slot': 'Bench'}, 'c': {'team': 1, 'slot': 'Starter'}}, 'history': []}
CATALOG = [{'id': i, 'gsisId': i, 'name': i.upper(), 'position': 'WR', 'team': 'SEA', 'metrics': {'opportunity': 40}}
           for i in ('a','b','c')]
CSV = b'player_id,player_display_name,position,team,season,season_type,week,targets,carries,attempts\na,A,WR,SEA,2026,REG,1,2,0,0\nb,B,WR,SEA,2026,REG,1,10,0,0\n'


class SeasonTests(unittest.TestCase):
    def test_moves_and_undo_do_not_change_draft_or_input(self):
        original = copy.deepcopy(STATE)
        moved = update_state(STATE, 'a', 1, 'IR')
        dropped = update_state(moved, 'a', None, 'Bench')
        self.assertEqual(STATE, original)
        self.assertEqual(moved['draft'], STATE['draft'])
        self.assertEqual(update_state(dropped, None, None, 'Bench', True)['owners'], moved['owners'])
        self.assertNotIn('a', dropped['owners'])

    def test_report_separates_ownership_and_reacts_to_usage(self):
        snapshot = {'season': 2026, 'latestWeek': 1, 'fetchedAt': 5, 'rows': parse_usage(CSV, 2026)}
        result = research(STATE, CATALOG, snapshot)
        self.assertEqual([r['player_id'] for r in result['waivers']], ['b'])
        self.assertEqual([r['player_id'] for r in result['trades']], ['c'])
        self.assertGreater(result['waivers'][0]['roster_fit_delta'], 0)
        self.assertEqual(result['waivers'][0]['confidence'], 'Low')
        self.assertEqual(result['roster_updated_at'], 1)
        self.assertEqual(result['stats_refreshed_at'], 5)
        self.assertEqual(research(STATE, CATALOG, snapshot, 0)['waivers'][0]['games'], 0)
        with self.assertRaises(ValueError):
            research(STATE, CATALOG, {**snapshot, 'season': 2025})

    def test_trend_scoring_rewards_rising_usage_over_prior(self):
        def rows(pid, targets_by_week):
            return [{'id': pid, 'name': pid.upper(), 'position': 'WR', 'team': 'SEA',
                     'week': w, 'targets': t, 'carries': 0, 'attempts': 0}
                    for w, t in targets_by_week.items()]
        catalog = [
            {'id': 'mine', 'gsisId': 'mine', 'name': 'MINE', 'position': 'WR', 'team': 'SEA', 'metrics': {'opportunity': 50}},
            {'id': 'riser', 'gsisId': 'riser', 'name': 'RISER', 'position': 'WR', 'team': 'SEA', 'metrics': {'opportunity': 10}},
            {'id': 'fader', 'gsisId': 'fader', 'name': 'FADER', 'position': 'WR', 'team': 'SEA', 'metrics': {'opportunity': 95}},
        ]
        state = {**STATE, 'owners': {'mine': {'team': 0, 'slot': 'Starter'}}, 'draft': []}
        snapshot = {'season': 2026, 'latestWeek': 6, 'fetchedAt': 5,
                    'rows': (rows('mine', {w: 5 for w in range(1, 7)})
                             + rows('riser', {1: 2, 2: 2, 3: 2, 4: 10, 5: 10, 6: 10})
                             + rows('fader', {1: 12, 2: 12, 3: 12, 4: 3, 5: 3, 6: 3}))}
        result = research(state, catalog, snapshot)
        by_id = {r['player_id']: r for r in result['waivers']}
        self.assertGreater(by_id['riser']['screen_score'], by_id['fader']['screen_score'])
        self.assertEqual(result['waivers'][0]['player_id'], 'riser')
        self.assertGreater(by_id['riser']['trend'], 0)
        self.assertLess(by_id['fader']['trend'], 0)

    def test_zero_usage_scores_zero_once_stats_exist(self):
        catalog = [
            {'id': 'mine', 'gsisId': 'mine', 'name': 'MINE', 'position': 'WR', 'team': 'SEA', 'metrics': {'opportunity': 50}},
            {'id': 'ghost', 'gsisId': 'ghost', 'name': 'GHOST', 'position': 'WR', 'team': 'SEA', 'metrics': {'opportunity': 99}},
            {'id': 'live', 'gsisId': 'live', 'name': 'LIVE', 'position': 'WR', 'team': 'SEA', 'metrics': {'opportunity': 5}},
        ]
        state = {**STATE, 'owners': {'mine': {'team': 0, 'slot': 'Starter'}}, 'draft': []}
        snapshot = {'season': 2026, 'latestWeek': 6, 'fetchedAt': 5,
                    'rows': [{'id': pid, 'name': pid.upper(), 'position': 'WR', 'team': 'SEA',
                              'week': w, 'targets': t, 'carries': 0, 'attempts': 0}
                             for pid, t in (('mine', 5), ('live', 4)) for w in range(1, 7)]}
        by_id = {r['player_id']: r for r in research(state, catalog, snapshot)['waivers']}
        self.assertEqual(by_id['ghost']['screen_score'], 0)
        self.assertGreater(by_id['live']['screen_score'], 0)

    def test_early_only_player_is_unavailable_not_scored(self):
        def rows(pid, targets_by_week):
            return [{'id': pid, 'name': pid.upper(), 'position': 'WR', 'team': 'SEA',
                     'week': w, 'targets': t, 'carries': 0, 'attempts': 0}
                    for w, t in targets_by_week.items()]
        catalog = [
            {'id': 'live', 'gsisId': 'live', 'name': 'LIVE', 'position': 'WR', 'team': 'SEA', 'metrics': {'opportunity': 50}},
            {'id': 'out', 'gsisId': 'out', 'name': 'OUT', 'position': 'WR', 'team': 'SEA', 'metrics': {'opportunity': 90}},
            {'id': 'cand', 'gsisId': 'cand', 'name': 'CAND', 'position': 'WR', 'team': 'SEA', 'metrics': {'opportunity': 10}},
            {'id': 'cand_out', 'gsisId': 'cand_out', 'name': 'CAND_OUT', 'position': 'WR', 'team': 'SEA', 'metrics': {'opportunity': 95}},
        ]
        state = {**STATE, 'owners': {'live': {'team': 0, 'slot': 'Starter'}, 'out': {'team': 0, 'slot': 'Bench'}}, 'draft': []}
        snapshot = {'season': 2026, 'latestWeek': 6, 'fetchedAt': 5,
                    'rows': (rows('live', {w: 5 for w in range(1, 7)})
                             + rows('out', {w: 20 for w in range(1, 4)})
                             + rows('cand', {w: 6 for w in range(1, 7)})
                             + rows('cand_out', {w: 20 for w in range(1, 4)}))}
        result = research(state, catalog, snapshot)
        by_id = {r['player_id']: r for r in result['waivers']}
        self.assertEqual(by_id['cand_out']['screen_score'], 0)
        self.assertEqual(by_id['cand_out']['reason'], 'Unavailable: no recorded games in late half')
        self.assertEqual(by_id['cand']['compare_with'], 'LIVE')
        self.assertEqual(result['waivers'][0]['player_id'], 'cand')

    def test_preseason_mode_still_uses_prior(self):
        catalog = [
            {'id': 'low', 'gsisId': 'low', 'name': 'LOW', 'position': 'WR', 'team': 'SEA', 'metrics': {'opportunity': 10}},
            {'id': 'high', 'gsisId': 'high', 'name': 'HIGH', 'position': 'WR', 'team': 'SEA', 'metrics': {'opportunity': 95}},
        ]
        state = {**STATE, 'owners': {}, 'draft': []}
        result = research(state, catalog, None)
        self.assertEqual(result['mode'], 'preseason watchlist')
        self.assertEqual(result['waivers'][0]['player_id'], 'high')

    def test_parser_rejects_duplicates_and_wrong_season(self):
        with self.assertRaises(ValueError):
            parse_usage(CSV + CSV.splitlines(keepends=True)[1], 2026)
        with self.assertRaises(ValueError):
            parse_usage(CSV, 2025)
        with self.assertRaises(ValueError):
            parse_usage(CSV.replace(b',2,0,0', b',NaN,0,0'), 2026)

    def test_offline_cli_roundtrip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state, catalog, raw, stats = [root / n for n in ('state.json','catalog.json','raw.csv','stats.json')]
            write_new(state, STATE)
            catalog.write_text(json.dumps(CATALOG))
            raw.write_bytes(CSV)
            self.assertEqual(main(['fetch-season-usage','--input',str(raw),'--output',str(stats)]), 0)
            out = root / 'report'
            self.assertEqual(main(['season-research','--state',str(state),'--stats',str(stats),'--catalog',str(catalog),'--output',str(out)]), 0)
            report = json.loads((out / 'report.json').read_text())
            self.assertIn('sha256', report['provenance']['roster'])
            moved = root / 'moved.json'
            self.assertEqual(main(['season-update','--state',str(state),'--catalog',str(catalog),'--player','b','--team','1','--output',str(moved)]), 0)
            self.assertEqual(load_state(moved)['owners']['b']['team'], 0)
            self.assertEqual(load_state(state), STATE)
            with self.assertRaises(FileExistsError):
                write_new(state, {})

    def test_unpublished_data_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as tmp, patch('fantasy_draft.season.urlopen', side_effect=HTTPError('url',404,'missing',{},None)):
            path = Path(tmp) / 'stats.json'
            with self.assertRaisesRegex(ValueError, 'not published'):
                fetch_usage(path)
            self.assertFalse(path.exists())

    def test_invalid_state_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.json'
            write_new(path, {**STATE, 'owners': {'a': {'team': 20, 'slot': 'Bench'}}})
            with self.assertRaises(ValueError):
                load_state(path)
