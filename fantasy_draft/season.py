"""Offline-first season research using interoperable web season backups.

Scores are opportunity screens, not fantasy point forecasts or trade prices.
Every report pins its roster, catalog and observed-data input hashes.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from .sources.nflverse_player_history import WEEKLY_STATS_URL


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_state(path: Path) -> dict:
    state = json.loads(path.read_text())
    if not isinstance(state, dict) or state.get('version') != 1 or state.get('season') != 2026:
        raise ValueError('Expected a version 1, 2026 web season backup')
    teams = state.get('teams')
    if not isinstance(teams, list) or not 2 <= len(teams) <= 20 or not all(isinstance(t, str) and t for t in teams):
        raise ValueError('Invalid team names')
    def team_index(n):
        return type(n) is int and 0 <= n < len(teams)
    if not team_index(state.get('myTeam')) or type(state.get('capacity')) is not int or not 1 <= state['capacity'] <= 50:
        raise ValueError('Invalid team or roster capacity')
    def owners_valid(owners):
        return isinstance(owners, dict) and all(isinstance(k, str) and isinstance(v, dict) and team_index(v.get('team')) and v.get('slot') in ('Starter', 'Bench', 'IR') for k, v in owners.items())
    if not owners_valid(state.get('owners')) or not isinstance(state.get('history'), list) or len(state['history']) > 100:
        raise ValueError('Invalid ownership or history')
    if not all(isinstance(h, dict) and owners_valid(h.get('before')) and isinstance(h.get('label'), str) and isinstance(h.get('at'), (int, float)) for h in state['history']):
        raise ValueError('Invalid history entry')
    if not isinstance(state.get('draft'), list) or not all(isinstance(p, dict) and isinstance(p.get('playerId'), str) and team_index(p.get('teamIndex')) and type(p.get('overall')) is int and p['overall'] > 0 for p in state['draft']):
        raise ValueError('Invalid preserved draft')
    for key in ('startedAt', 'updatedAt'):
        if not isinstance(state.get(key), (int, float)) or not math.isfinite(state[key]) or state[key] <= 0:
            raise ValueError(f'Invalid {key}')
    return state


def update_state(state: dict, player_id: str | None, team: int | None, slot: str, undo: bool = False) -> dict:
    updated = copy.deepcopy(state)
    if undo:
        if not updated['history']:
            raise ValueError('No season transaction to undo')
        updated['owners'] = updated['history'].pop()['before']
    else:
        if not player_id or slot not in ('Starter', 'Bench', 'IR'):
            raise ValueError('Specify a player and valid roster slot')
        if team is not None and not 0 <= team < len(state['teams']):
            raise ValueError('Team number is outside the league')
        label = f'{player_id} → {state["teams"][team] if team is not None else "Free agents"} ({slot})'
        updated['history'] = updated['history'][-99:] + [{'at': now_ms(), 'label': label, 'before': copy.deepcopy(state['owners'])}]
        if team is None:
            if player_id not in updated['owners']:
                raise ValueError('Player is already unowned')
            del updated['owners'][player_id]
        else:
            updated['owners'][player_id] = {'team': team, 'slot': slot}
    updated['updatedAt'] = now_ms()
    return updated


def now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def write_new(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as handle:
        json.dump(data, handle, indent=2, allow_nan=False)
        handle.write('\n')


def parse_usage(raw: bytes, season: int) -> list[dict]:
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    required = {'player_id','player_display_name','position','team','season','season_type','week','targets','carries','attempts'}
    if not required <= set(reader.fieldnames or []):
        raise ValueError('NFL stats schema changed or required columns missing')
    rows = []
    seen = set()
    for row in reader:
        if row['season'] != str(season) or row['season_type'] != 'REG' or row['position'] not in ('QB','RB','WR','TE'):
            continue
        week = int(row['week'])
        if not 1 <= week <= 18 or not row['player_id']:
            raise ValueError('Invalid weekly player identity')
        key = (row['player_id'], week)
        if key in seen:
            raise ValueError(f'Duplicate player-week: {key}')
        seen.add(key)
        values = {k: float(row[k] or 0) for k in ('targets','carries','attempts')}
        if not all(math.isfinite(n) and n >= 0 for n in values.values()):
            raise ValueError('Invalid opportunity count')
        rows.append({'id': row['player_id'], 'name': row['player_display_name'], 'position': row['position'], 'team': row['team'], 'week': week, **values})
    if not rows:
        raise ValueError(f'No {season} regular-season usage; prior snapshots unchanged')
    return rows


def fetch_usage(output: Path, season: int = 2026, source_file: Path | None = None) -> dict:
    url = WEEKLY_STATS_URL.format(season=season)
    source_updated = None
    if source_file:
        raw = source_file.read_bytes()
    else:
        try:
            with urlopen(url, timeout=25) as response:
                raw = response.read(25_000_001)
                source_updated = response.headers.get('Last-Modified')
        except HTTPError as error:
            if error.code == 404:
                raise ValueError(f'{season} stats not published yet; prior snapshots unchanged') from error
            raise
    if len(raw) > 25_000_000:
        raise ValueError('Stats file exceeds size limit')
    rows = parse_usage(raw, season)
    snapshot = {'season': season, 'fetchedAt': now_ms(), 'sourceUpdated': source_updated,
                'source': str(source_file) if source_file else url, 'rawSha256': digest(raw),
                'latestWeek': max(r['week'] for r in rows), 'rows': rows}
    write_new(output, snapshot)
    return snapshot


def load_catalog(path: Path) -> list[dict]:
    text = path.read_text()
    # The checked-in generated catalog is JSON inside a TS constant. No JS execution.
    if path.suffix == '.ts':
        text = text.split('export const PLAYERS = ', 1)[1].rsplit(' as const;', 1)[0].strip()
    players = json.loads(text)
    if not isinstance(players, list) or not all(isinstance(p, dict) and all(k in p for k in ('id','name','position','team')) for p in players):
        raise ValueError('Catalog must be a JSON player array')
    if len({p['id'] for p in players}) != len(players):
        raise ValueError('Duplicate catalog IDs')
    return players


def research(state: dict, catalog: list[dict], snapshot: dict | None, through_week: int | None = None) -> dict:
    if snapshot and snapshot.get('season') != state['season']:
        raise ValueError('Stats season must match roster season')
    latest = through_week if through_week is not None else (snapshot['latestWeek'] if snapshot else 0)
    if type(latest) is not int or not 0 <= latest <= 18:
        raise ValueError('Week must be between 0 and 18')
    rows = snapshot['rows'] if snapshot else []
    if not isinstance(rows, list):
        raise ValueError('Snapshot rows must be a list')
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str) and row[k] for k in ('id','name','position','team')):
            raise ValueError('Invalid stats player identity')
        if type(row.get('week')) is not int or not 1 <= row['week'] <= 18:
            raise ValueError('Invalid stats week')
        key = (row['id'], row['week'])
        if key in seen:
            raise ValueError('Duplicate stats player-week')
        seen.add(key)
        if not all(isinstance(row.get(k), (int,float)) and math.isfinite(row[k]) and row[k] >= 0 for k in ('targets','carries','attempts')):
            raise ValueError('Invalid stats snapshot counts')
    if snapshot and (not isinstance(snapshot.get('fetchedAt'), (int,float)) or not math.isfinite(snapshot['fetchedAt']) or snapshot['fetchedAt'] <= 0):
        raise ValueError('Invalid stats refresh timestamp')
    players = {p['id']: copy.deepcopy(p) for p in catalog}
    for key, info in state.get('playerInfo', {}).items():
        players.setdefault(key, {'id': key, **info})
    by_gsis = {p.get('gsisId'): p for p in players.values() if p.get('gsisId')}
    grouped = {}
    for r in rows:
        if not 1 <= r['week'] <= latest:
            continue
        if not all(isinstance(r[k], (int,float)) and math.isfinite(r[k]) and r[k] >= 0 for k in ('targets','carries','attempts')):
            raise ValueError('Invalid stats snapshot counts')
        grouped.setdefault(r['id'], []).append(r)
        if r['id'] not in by_gsis:
            p = {'id': f'nfl-{r["id"]}', 'gsisId': r['id'], 'name': r['name'], 'position': r['position'], 'team': r['team']}
            players[p['id']] = p
            by_gsis[r['id']] = p
    summaries = {}
    for p in players.values():
        games = grouped.get(p.get('gsisId'), [])
        if games:
            p['team'] = max(games, key=lambda r: r['week'])['team']
        recent = [r for r in games if latest - 3 < r['week'] <= latest]
        prior = [r for r in games if latest - 6 < r['week'] <= latest - 3]
        def average(window):
            return sum((r['attempts'] + r['carries'] if p['position'] == 'QB' else r['carries'] + r['targets'] if p['position'] == 'RB' else r['targets']) for r in window) / len(window) if window else 0
        summaries[p['id']] = {'games': len(recent), 'volume': average(recent), 'trend': average(recent) - average(prior) if recent and prior else None,
                              'confidence': 'Moderate' if len(recent) >= 3 else 'Low'}
    scores = {}
    for p in players.values():
        u = summaries[p['id']]
        peers = [summaries[q['id']]['volume'] for q in players.values() if q['position'] == p['position'] and summaries[q['id']]['games']]
        percentile = 100 * sum(v <= u['volume'] for v in peers) / len(peers) if u['games'] else 0
        prior = float(p.get('metrics', {}).get('opportunity', 0))
        if not math.isfinite(prior) or not 0 <= prior <= 100:
            raise ValueError('Invalid opportunity prior')
        weight = min(.75, u['games'] * .25)
        scores[p['id']] = prior * (1 - weight) + percentile * weight
    mine = [p for p in players.values() if state['owners'].get(p['id'], {}).get('team') == state['myTeam']]
    result = {'waivers': [], 'trades': []}
    for p in players.values():
        owner = state['owners'].get(p['id'])
        if p['position'] not in ('QB','RB','WR','TE') or (owner and owner['team'] == state['myTeam']):
            continue
        peers = [q for q in mine if q['position'] == p['position']]
        baseline = min(peers, key=lambda q: scores[q['id']]) if peers else None
        delta = scores[p['id']] - scores[baseline['id']] if baseline else scores[p['id']]
        result['trades' if owner else 'waivers'].append({
            'player_id': p['id'], 'name': p['name'], 'position': p['position'], 'nfl_team': p['team'],
            'owner': state['teams'][owner['team']] if owner else None, **summaries[p['id']],
            'screen_score': round(scores[p['id']], 2), 'roster_fit_delta': round(delta, 2),
            'compare_with': baseline['name'] if baseline else None,
            'reason': 'Empty position' if not baseline else 'Investigate potential upgrade' if delta > 0 else 'Depth watch only',
        })
    for values in result.values():
        values.sort(key=lambda r: (-r['roster_fit_delta'], -r['screen_score'], r['player_id']))
    return {'season': state['season'], 'through_week': latest, 'roster_updated_at': state['updatedAt'],
            'stats_refreshed_at': snapshot.get('fetchedAt') if snapshot else None,
            'mode': 'usage watchlist' if grouped else 'preseason watchlist',
            'unresolved_owned_ids': sorted(set(state['owners']) - set(players)),
            'limitations': ['Manual ownership; verify Yahoo availability and injuries.',
                'Not calibrated trade values, fantasy projections, or automatic drop advice.',
                'Recorded-game averages exclude missing rows, including injury and bye gaps.',
                'Partial weeks and small samples can distort usage. No snap/red-zone/injury adjustments.',
                'Week cutoff filters stats only; this is not a historical backtest of roster or preseason priors.'], **result}


def render_report(report: dict, top: int) -> str:
    lines = [f'# Season research — {report["season"]}', '', f'Mode: {report["mode"]}; stats through week {report["through_week"]}.', '']
    for kind in ('waivers', 'trades'):
        lines.extend([f'## {kind.title()}', ''])
        for r in report[kind][:top]:
            lines.append(f'- {r["name"]} ({r["position"]}, {r["nfl_team"]}): {r["reason"]}; {r["volume"]:.1f} opportunities/recorded game, {r["games"]} recent games; {r["confidence"]} confidence. Compare: {r["compare_with"] or "empty position"}. Owner: {r["owner"] or "unowned in manual records"}.')
        if not report[kind]:
            lines.append('No matching candidates.')
        lines.append('')
    lines.extend(['## Limitations', '', *[f'- {s}' for s in report['limitations']]])
    if report['unresolved_owned_ids']:
        lines.extend(['', 'Unresolved roster IDs: ' + ', '.join(report['unresolved_owned_ids'])])
    return '\n'.join(lines) + '\n'
