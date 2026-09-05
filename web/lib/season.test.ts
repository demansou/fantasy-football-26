import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  changeOwner,
  parseSeason,
  undoSeason,
  parseUsage,
  csvRows,
  usageSummary,
  parseStats,
  type SeasonState,
} from './season.ts';
const initial: SeasonState = {
  version: 1,
  season: 2026,
  startedAt: 1,
  updatedAt: 1,
  teams: ['Mine', 'Theirs'],
  myTeam: 0,
  capacity: 16,
  draft: [{ playerId: 'rb-1', overall: 1, teamIndex: 0 }],
  owners: { 'rb-1': { team: 0, slot: 'Bench' } },
  history: [],
};
void test('ownership transfer, drop, and undo preserve immutable draft and other players', () => {
  const traded = changeOwner(
    initial,
    'rb-1',
    { team: 1, slot: 'Bench' },
    'Trade',
  );
  assert.equal(initial.owners['rb-1'].team, 0);
  assert.equal(traded.owners['rb-1'].team, 1);
  assert.deepEqual(traded.draft, initial.draft);
  const dropped = changeOwner(traded, 'rb-1', null, 'Drop');
  assert.equal(dropped.owners['rb-1'], undefined);
  assert.deepEqual(undoSeason(dropped).owners, traded.owners);
  assert.deepEqual(undoSeason(traded).owners, initial.owners);
});
void test('backup round trip and malformed ownership rejection', () => {
  assert.deepEqual(parseSeason(JSON.stringify(initial)), initial);
  for (const patch of [
    { version: 2 },
    { owners: { x: { team: 10, slot: 'Bench' } } },
    { owners: { x: null } },
    { history: [null] },
    { draft: [null] },
  ])
    assert.throws(() => parseSeason(JSON.stringify({ ...initial, ...patch })));
});
void test('CSV quoted fields and regular-season filtering', () => {
  assert.deepEqual(csvRows('a,b\n"A, B","C""D"\n'), [
    ['a', 'b'],
    ['A, B', 'C"D'],
  ]);
  const header =
    'player_id,player_display_name,position,season,season_type,week,targets,carries,attempts,team,target_share\n';
  const rows = parseUsage(
    header +
      '00-1,Example,RB,2026,REG,1,4,12,0,SEA,0.2\n00-2,Old,RB,2025,REG,1,9,20,0,SEA,0.4\n00-3,Post,RB,2026,POST,1,4,9,0,SEA,0.1\n',
    2026,
  );
  assert.equal(rows.length, 1);
  assert.equal(rows[0].targets, 4);
  assert.equal(usageSummary(rows, 1).volume, 16);
  assert.equal(usageSummary(rows, 1).confidence, 'Low');
  assert.equal(usageSummary(rows, 5).games, 0);
  assert.throws(() => parseUsage('changed,schema\n1,2', 2026));
});
void test('invalid snapshots cannot replace cached data', () => {
  assert.throws(() => parseStats({ season: 2025, rows: [] }));
  assert.throws(() =>
    parseStats({ season: 2026, fetchedAt: 1, latestWeek: 1, rows: [null] }),
  );
});
