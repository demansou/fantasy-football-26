import assert from 'node:assert/strict';
import test from 'node:test';
import {
  lineupStatus,
  marketSurvivalEstimate,
  opponentAdjustedSurvival,
  opponentDemandForPosition,
  ownerForPick,
} from './draft-intelligence.ts';

const market = {
  adp: 25,
  adpStdev: 6,
  marketHighPick: 8,
  marketLowPick: 49,
  timesDrafted: 800,
};

void test('snake ownership reverses every round', () => {
  assert.deepEqual(
    [1, 10, 11, 20, 21, 30].map((pick) => ownerForPick(pick, 10)),
    [0, 9, 9, 0, 0, 9],
  );
});

void test('market survival decreases monotonically with a later target', () => {
  const turns = [15, 25, 35, 45].map((pick) =>
    marketSurvivalEstimate(market, pick),
  );
  assert.ok(
    turns.every((value, index) => index === 0 || value < turns[index - 1]),
  );
  assert.ok(turns.every((value) => value > 0 && value < 1));
});

void test('lineup needs distinguish fixed starters, flex, and bench', () => {
  assert.equal(lineupStatus('RB', { RB: 1, WR: 2 }), 'starter');
  assert.equal(lineupStatus('RB', { RB: 2, WR: 2, TE: 1 }), 'flex');
  assert.equal(lineupStatus('RB', { RB: 3, WR: 2, TE: 1 }), 'bench');
});

void test('needy opponents lower the estimate that an RB survives', () => {
  const teamRosters = Array.from({ length: 10 }, () => ({ RB: 3, WR: 3 }));
  teamRosters[5] = { RB: 0, WR: 3 };
  teamRosters[6] = { RB: 1, WR: 3 };
  teamRosters[7] = { RB: 0, WR: 3 };
  teamRosters[8] = { RB: 1, WR: 3 };
  const demand = opponentDemandForPosition({
    position: 'RB',
    firstOpponentPick: 6,
    targetPick: 10,
    teamCount: 10,
    myTeamIndex: 4,
    teamRosters,
    currentRound: 1,
  });
  assert.equal(demand.starterPicks, 4);
  assert.ok(demand.pressure > 1);
  assert.ok(
    opponentAdjustedSurvival(market, 35, demand) <
      marketSurvivalEstimate(market, 35),
  );
});
