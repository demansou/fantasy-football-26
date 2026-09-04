export type DraftPosition = 'QB' | 'RB' | 'WR' | 'TE' | 'K' | 'DST';
export type PositionCounts = Partial<Record<DraftPosition, number>>;
export type LineupStatus = 'starter' | 'flex' | 'bench';

export type MarketRange = {
  adp: number;
  adpStdev: number;
  marketHighPick: number;
  marketLowPick: number;
  timesDrafted: number;
};

export type OpponentDemand = {
  position: DraftPosition;
  upcomingPicks: number;
  starterPicks: number;
  flexPicks: number;
  pressure: number;
  label: 'light' | 'normal' | 'elevated' | 'high';
};

export type TierCandidate = {
  id: string;
  position: DraftPosition;
  tier: number;
  draftScore: number;
};

export type TierCliff = {
  level: 'safe' | 'warning' | 'critical';
  label: 'Can wait' | 'Tier at risk' | 'Tier likely gone';
  remainingInTier: number;
  expectedPositionPicks: number;
  scoreDrop: number;
  fallbackId: string | null;
};

const FIXED_STARTERS: Record<DraftPosition, number> = {
  QB: 1,
  RB: 2,
  WR: 2,
  TE: 1,
  K: 1,
  DST: 1,
};
const FLEX_POSITIONS = new Set<DraftPosition>(['RB', 'WR', 'TE']);
const POSITION_PICK_SHARE: Record<DraftPosition, number> = {
  QB: 0.11,
  RB: 0.27,
  WR: 0.27,
  TE: 0.11,
  K: 0.12,
  DST: 0.12,
};

function normalCdf(value: number) {
  const sign = value < 0 ? -1 : 1;
  const x = Math.abs(value) / Math.sqrt(2);
  const t = 1 / (1 + 0.3275911 * x);
  const erf =
    sign *
    (1 -
      ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) *
        t +
        0.254829592) *
        t *
        Math.exp(-x * x));
  return 0.5 * (1 + erf);
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.max(minimum, Math.min(maximum, value));
}

export function ownerForPick(overall: number, teamCount: number) {
  const round = Math.floor((overall - 1) / teamCount) + 1;
  const offset = (overall - 1) % teamCount;
  return round % 2 ? offset : teamCount - 1 - offset;
}

export function lineupStatus(
  position: DraftPosition,
  counts: PositionCounts,
): LineupStatus {
  if ((counts[position] ?? 0) < FIXED_STARTERS[position]) return 'starter';
  if (!FLEX_POSITIONS.has(position)) return 'bench';

  const flexPlayers = (['RB', 'WR', 'TE'] as DraftPosition[]).reduce(
    (total, eligible) =>
      total + Math.max(0, (counts[eligible] ?? 0) - FIXED_STARTERS[eligible]),
    0,
  );
  return flexPlayers < 1 ? 'flex' : 'bench';
}

function demandWeight(
  position: DraftPosition,
  counts: PositionCounts,
  currentRound: number,
) {
  const status = lineupStatus(position, counts);
  if (status === 'starter') {
    if ((position === 'K' || position === 'DST') && currentRound < 11)
      return 0.2;
    return 1.6;
  }
  if (status === 'flex') return 1.15;
  if (position === 'RB' || position === 'WR') return 0.8;
  if (position === 'QB' || position === 'TE') return 0.55;
  return currentRound >= 11 ? 0.35 : 0.12;
}

/**
 * Fits the published FFC mean/spread inside the observed high/low pick range.
 * This is an evidence-bounded estimate, not an empirical calibration: the free
 * feed does not expose the underlying pick-by-pick outcomes.
 */
export function marketSurvivalEstimate(
  player: MarketRange,
  targetPick: number,
) {
  const deviation = Math.max(1, player.adpStdev);
  const high = Math.max(
    1,
    Math.min(player.marketHighPick, player.marketLowPick),
  );
  const low = Math.max(
    high,
    Math.max(player.marketHighPick, player.marketLowPick),
  );
  const targetBoundary = targetPick - 0.5;
  const unbounded = 1 - normalCdf((targetBoundary - player.adp) / deviation);
  const lowerCdf = normalCdf((high - 0.5 - player.adp) / deviation);
  const upperCdf = normalCdf((low + 0.5 - player.adp) / deviation);
  const denominator = Math.max(0.000001, upperCdf - lowerCdf);
  const bounded = clamp(
    (upperCdf - normalCdf((targetBoundary - player.adp) / deviation)) /
      denominator,
    0,
    1,
  );
  const sampleReliability = player.timesDrafted / (player.timesDrafted + 50);
  return clamp(
    sampleReliability * bounded + (1 - sampleReliability) * unbounded,
    0.005,
    0.995,
  );
}

export function opponentDemandForPosition({
  position,
  firstOpponentPick,
  targetPick,
  teamCount,
  myTeamIndex,
  teamRosters,
  currentRound,
}: {
  position: DraftPosition;
  firstOpponentPick: number;
  targetPick: number;
  teamCount: number;
  myTeamIndex: number;
  teamRosters: PositionCounts[];
  currentRound: number;
}): OpponentDemand {
  const owners: number[] = [];
  for (let overall = firstOpponentPick; overall < targetPick; overall += 1) {
    const owner = ownerForPick(overall, teamCount);
    if (owner !== myTeamIndex) owners.push(owner);
  }
  const baseline =
    teamRosters.reduce(
      (total, counts) => total + demandWeight(position, counts, currentRound),
      0,
    ) / Math.max(1, teamRosters.length);
  const exposure = owners.reduce(
    (total, owner) =>
      total + demandWeight(position, teamRosters[owner] ?? {}, currentRound),
    0,
  );
  const pressure = owners.length
    ? clamp(exposure / owners.length / Math.max(0.1, baseline), 0.45, 1.9)
    : 1;
  const statuses = owners.map((owner) =>
    lineupStatus(position, teamRosters[owner] ?? {}),
  );
  return {
    position,
    upcomingPicks: owners.length,
    starterPicks: statuses.filter((status) => status === 'starter').length,
    flexPicks: statuses.filter((status) => status === 'flex').length,
    pressure,
    label:
      pressure >= 1.4
        ? 'high'
        : pressure >= 1.15
          ? 'elevated'
          : pressure <= 0.78
            ? 'light'
            : 'normal',
  };
}

export function opponentAdjustedSurvival(
  player: MarketRange,
  targetPick: number,
  demand: OpponentDemand,
) {
  const market = marketSurvivalEstimate(player, targetPick);
  return clamp(Math.pow(market, demand.pressure), 0.005, 0.995);
}

export function rosterNeeds(counts: PositionCounts, currentRound: number) {
  return (['QB', 'RB', 'WR', 'TE', 'K', 'DST'] as DraftPosition[]).filter(
    (position) =>
      lineupStatus(position, counts) === 'starter' &&
      !((position === 'K' || position === 'DST') && currentRound < 11),
  );
}

export function tierCliffForPlayer({
  player,
  positionPool,
  demand,
  picksUntilNext,
  survivalPercent,
}: {
  player: TierCandidate;
  positionPool: TierCandidate[];
  demand: OpponentDemand;
  picksUntilNext: number;
  survivalPercent: number;
}): TierCliff {
  const currentTier = positionPool.filter(
    (candidate) => candidate.tier === player.tier,
  );
  const tierFloor = currentTier.reduce(
    (lowest, candidate) => Math.min(lowest, candidate.draftScore),
    player.draftScore,
  );
  const nextTier = positionPool.find(
    (candidate) => candidate.tier > player.tier,
  );
  const playerIndex = positionPool.findIndex(
    (candidate) => candidate.id === player.id,
  );
  const fallback =
    playerIndex >= 0 ? (positionPool[playerIndex + 1] ?? nextTier) : nextTier;
  const scoreDrop = nextTier ? Math.max(0, tierFloor - nextTier.draftScore) : 0;
  const expectedPositionPicks = Math.max(
    1,
    Math.ceil(
      picksUntilNext * POSITION_PICK_SHARE[player.position] * demand.pressure,
    ),
  );
  const tierExhaustion = expectedPositionPicks >= currentTier.length;
  const level =
    survivalPercent <= 25 || (tierExhaustion && scoreDrop >= 1)
      ? 'critical'
      : survivalPercent <= 50 || tierExhaustion
        ? 'warning'
        : 'safe';
  return {
    level,
    label:
      level === 'critical'
        ? 'Tier likely gone'
        : level === 'warning'
          ? 'Tier at risk'
          : 'Can wait',
    remainingInTier: currentTier.length,
    expectedPositionPicks,
    scoreDrop,
    fallbackId: fallback?.id ?? null,
  };
}
