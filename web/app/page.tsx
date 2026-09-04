'use client';

import {
  Fragment,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react';
import {
  Check,
  Database,
  Download,
  DraftingCompass,
  EyeOff,
  LayoutGrid,
  RefreshCw,
  RotateCcw,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Star,
  Undo2,
  Upload,
  Zap,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  NativeSelect,
  NativeSelectOption,
} from '@/components/ui/native-select';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { PLAYERS, RANKING_METADATA } from '@/data/players';
import {
  lineupStatus,
  opponentAdjustedSurvival,
  opponentDemandForPosition,
  rosterNeeds,
  tierCliffForPlayer,
  type OpponentDemand,
  type PositionCounts,
  type RosterRules,
} from '@/lib/draft-intelligence';

type Position = 'QB' | 'RB' | 'WR' | 'TE' | 'K' | 'DST';
type ModeledPosition = 'QB' | 'RB' | 'WR' | 'TE';
type Metric = 'opportunity' | 'highValue' | 'environment' | 'roleEvidence';
type SortMode = 'draft' | 'opportunity' | 'adp';
type Player = {
  id: string;
  sourceId: string;
  gsisId: string | null;
  name: string;
  position: Position;
  team: string;
  bye: number;
  adp: number;
  adpStdev: number;
  marketHighPick: number;
  marketLowPick: number;
  timesDrafted: number;
  adpRank: number;
  draftScore: number;
  marketBase: number;
  modelRank: number;
  positionRank: number;
  rankDelta: number;
  tier: number;
  context: string;
  playCaller: string | null;
  styleEvidence: number | null;
  styleEvidenceLabel: string | null;
  coverage: 'modeled' | 'market_only';
  status: string;
  currentActive: boolean;
  metrics: Record<Metric, number>;
};
type Pick = { playerId: string; overall: number; teamIndex: number };
type Weights = Record<ModeledPosition, Record<Metric, number>>;
type DraftCache = {
  schemaVersion: 1;
  savedAt: number;
  picks: Pick[];
  weights: Weights;
  teamCount: number;
  draftSlot: number;
  benchCount: number;
  starterCounts: Record<Position, number>;
  flexCount: number;
  teamNames: string[];
  avoidedPlayerIds: string[];
  watchedPlayerIds: string[];
  hideInactivePlayers: boolean;
};
type RosterSlot = Position | 'FLEX' | 'BN';
type InjuryAlert = {
  status: string | null;
  injuryStatus: string | null;
  bodyPart: string | null;
  notes: string | null;
  practiceParticipation: string | null;
  newsUpdated: number | null;
};
type InjuryCache = {
  fetchedAt: number;
  alerts: Record<string, InjuryAlert>;
  matchedPlayers: number;
};
type SleeperPlayer = {
  gsis_id?: string | null;
  full_name?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  team?: string | null;
  position?: string | null;
  status?: string | null;
  injury_status?: string | null;
  injury_body_part?: string | null;
  injury_notes?: string | null;
  practice_participation?: string | null;
  news_updated?: number | null;
};

const players = PLAYERS as unknown as Player[];
const TEAM_LABELS = [
  'Gridiron Ghosts',
  'Sunday Scaries',
  'Fourth & Long',
  'Waiver Wired',
  'Red Zone Radio',
  'Two Minute Drill',
  'Goal Line Stand',
  'Pocket Presence',
  'The Audible',
  'Sunday Film Club',
  'Route Concepts',
  'Clock Managers',
];
const STORAGE_KEY = 'fantasy-football-26:draft-room:v3';
const STORAGE_BACKUP_KEY = 'fantasy-football-26:draft-room:backup:v1';
const LEGACY_STORAGE_KEY = 'fantasy-football-26:draft-room:v2';
const INJURY_CACHE_KEY = 'fantasy-football-26:sleeper-injuries:v1';
const INJURY_REFRESH_MS = 20 * 60 * 60 * 1000;
const DEFAULT_BENCH_COUNT = 6;
const DEFAULT_FLEX_COUNT = 2;
const DEFAULT_STARTER_COUNTS: Record<Position, number> = {
  QB: 1,
  RB: 2,
  WR: 2,
  TE: 1,
  K: 1,
  DST: 1,
};
const MODELED_POSITIONS: ModeledPosition[] = ['QB', 'RB', 'WR', 'TE'];
const ALL_POSITIONS: Position[] = ['QB', 'RB', 'WR', 'TE', 'K', 'DST'];
const ROSTER_POSITION_ORDER: RosterSlot[] = [
  'QB',
  'WR',
  'RB',
  'TE',
  'FLEX',
  'K',
  'DST',
  'BN',
];
const DEFAULT_WEIGHTS: Weights = {
  QB: { opportunity: 100, highValue: 100, environment: 100, roleEvidence: 100 },
  RB: { opportunity: 100, highValue: 100, environment: 100, roleEvidence: 100 },
  WR: { opportunity: 100, highValue: 100, environment: 100, roleEvidence: 100 },
  TE: { opportunity: 100, highValue: 100, environment: 100, roleEvidence: 100 },
};
const FACTORS: Array<{ key: Metric; label: string; hint: string }> = [
  {
    key: 'opportunity',
    label: 'Opportunity',
    hint: 'Availability-adjusted role volume',
  },
  {
    key: 'highValue',
    label: 'High-value usage',
    hint: 'Goal-line and valuable target paths',
  },
  {
    key: 'environment',
    label: 'Team environment',
    hint: 'Raw position opportunity forecast',
  },
  {
    key: 'roleEvidence',
    label: 'Role evidence',
    hint: 'History and depth-chart support',
  },
];
const positionClass: Record<Position, string> = {
  QB: 'position-qb',
  RB: 'position-rb',
  WR: 'position-wr',
  TE: 'position-te',
  K: 'position-k',
  DST: 'position-dst',
};

function defaultTeamNames(draftSlot: number) {
  return TEAM_LABELS.map((name, index) =>
    index === draftSlot - 1 ? 'My Team' : name,
  );
}

function normalizeTeamNames(value: unknown, draftSlot: number) {
  const defaults = defaultTeamNames(draftSlot);
  if (!Array.isArray(value)) return defaults;
  return defaults.map((fallback, index) => {
    const name = value[index];
    return typeof name === 'string' && name.trim()
      ? name.trim().slice(0, 32)
      : fallback;
  });
}

function ownerForPick(overall: number, teamCount: number) {
  const round = Math.floor((overall - 1) / teamCount) + 1;
  const offset = (overall - 1) % teamCount;
  return round % 2 ? offset : teamCount - 1 - offset;
}

function nextPickForTeam(start: number, teamCount: number, teamIndex: number) {
  let pick = start;
  while (ownerForPick(pick, teamCount) !== teamIndex) pick += 1;
  return pick;
}

function pickForRoundAndTeam(
  round: number,
  teamIndex: number,
  teamCount: number,
) {
  const offset = round % 2 ? teamIndex : teamCount - 1 - teamIndex;
  return (round - 1) * teamCount + offset + 1;
}

function isValidWeights(value: unknown): value is Weights {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<Weights>;
  return MODELED_POSITIONS.every((position) =>
    FACTORS.every(({ key }) => {
      const weight = candidate[position]?.[key];
      return (
        typeof weight === 'number' &&
        Number.isFinite(weight) &&
        weight >= 0 &&
        weight <= 200
      );
    }),
  );
}

function normalizeStarterCounts(value: unknown): Record<Position, number> {
  const candidate =
    value && typeof value === 'object'
      ? (value as Partial<Record<Position, unknown>>)
      : {};
  return Object.fromEntries(
    ALL_POSITIONS.map((position) => {
      const count = candidate[position];
      return [
        position,
        typeof count === 'number' &&
        Number.isInteger(count) &&
        count >= 0 &&
        count <= 4
          ? count
          : DEFAULT_STARTER_COUNTS[position],
      ];
    }),
  ) as Record<Position, number>;
}

function buildStarterSlots(
  starterCounts: Record<Position, number>,
  flexCount: number,
) {
  const order: Array<Position | 'FLEX'> = [
    'QB',
    'WR',
    'RB',
    'TE',
    'FLEX',
    'K',
    'DST',
  ];
  return order.flatMap((position) =>
    Array.from(
      {
        length:
          position === 'FLEX' ? flexCount : (starterCounts[position] ?? 0),
      },
      () => position,
    ),
  );
}

function parseDraftCache(raw: string | null): DraftCache | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<DraftCache>;
    const teamCount = [8, 10, 12].includes(parsed.teamCount ?? 0)
      ? parsed.teamCount!
      : 10;
    const draftSlot =
      typeof parsed.draftSlot === 'number' &&
      parsed.draftSlot >= 1 &&
      parsed.draftSlot <= teamCount
        ? parsed.draftSlot
        : Math.min(5, teamCount);
    const benchCount =
      typeof parsed.benchCount === 'number' &&
      parsed.benchCount >= 0 &&
      parsed.benchCount <= 12
        ? parsed.benchCount
        : DEFAULT_BENCH_COUNT;
    const flexCount =
      typeof parsed.flexCount === 'number' &&
      Number.isInteger(parsed.flexCount) &&
      parsed.flexCount >= 0 &&
      parsed.flexCount <= 4
        ? parsed.flexCount
        : DEFAULT_FLEX_COUNT;
    const knownPlayerIds = new Set(players.map((player) => player.id));
    const seen = new Set<string>();
    const picks = Array.isArray(parsed.picks)
      ? parsed.picks.reduce<Pick[]>((valid, pick, index) => {
          const overall = index + 1;
          if (
            valid.length !== index ||
            !pick ||
            !knownPlayerIds.has(pick.playerId) ||
            seen.has(pick.playerId) ||
            pick.overall !== overall ||
            pick.teamIndex !== ownerForPick(overall, teamCount)
          )
            return valid;
          seen.add(pick.playerId);
          valid.push(pick);
          return valid;
        }, [])
      : [];
    return {
      schemaVersion: 1,
      savedAt:
        typeof parsed.savedAt === 'number' && Number.isFinite(parsed.savedAt)
          ? parsed.savedAt
          : 0,
      picks,
      weights: isValidWeights(parsed.weights)
        ? parsed.weights
        : DEFAULT_WEIGHTS,
      teamCount,
      draftSlot,
      benchCount,
      starterCounts: normalizeStarterCounts(parsed.starterCounts),
      flexCount,
      teamNames: normalizeTeamNames(parsed.teamNames, draftSlot),
      avoidedPlayerIds: Array.isArray(parsed.avoidedPlayerIds)
        ? [
            ...new Set(
              parsed.avoidedPlayerIds.filter(
                (playerId): playerId is string =>
                  typeof playerId === 'string' && knownPlayerIds.has(playerId),
              ),
            ),
          ]
        : [],
      watchedPlayerIds: Array.isArray(parsed.watchedPlayerIds)
        ? [
            ...new Set(
              parsed.watchedPlayerIds.filter(
                (playerId): playerId is string =>
                  typeof playerId === 'string' && knownPlayerIds.has(playerId),
              ),
            ),
          ]
        : [],
      hideInactivePlayers: parsed.hideInactivePlayers === true,
    };
  } catch {
    return null;
  }
}

function writeDraftCache(cache: DraftCache) {
  const serialized = JSON.stringify(cache);
  let saved = false;
  try {
    window.localStorage.setItem(STORAGE_KEY, serialized);
    saved = true;
  } catch {
    /* Try the same-tab backup. */
  }
  try {
    window.sessionStorage.setItem(STORAGE_BACKUP_KEY, serialized);
    saved = true;
  } catch {
    /* Report failure only if neither browser store worked. */
  }
  if (!saved) throw new Error('Browser storage is unavailable');
}

function readDraftCache(storage: Storage, key: string) {
  try {
    return parseDraftCache(storage.getItem(key));
  } catch {
    return null;
  }
}

function chanceLasts(
  player: Player,
  targetPick: number,
  demand: OpponentDemand,
) {
  return Math.round(opponentAdjustedSurvival(player, targetPick, demand) * 100);
}

function normalizePlayerName(value: string) {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/\b(jr|sr|ii|iii|iv)\b/g, '')
    .replace(/[^a-z0-9]/g, '');
}

function normalizeTeam(value: string | null | undefined) {
  if (value === 'JAC') return 'JAX';
  if (value === 'LA') return 'LAR';
  return value ?? '';
}

function sleeperIdentity(player: SleeperPlayer) {
  const fullName =
    player.full_name ??
    `${player.first_name ?? ''} ${player.last_name ?? ''}`.trim();
  return `${normalizePlayerName(fullName)}|${normalizeTeam(player.team)}|${player.position ?? ''}`;
}

function buildInjuryCache(payload: Record<string, SleeperPlayer>): InjuryCache {
  const sleeperPlayers = Object.values(payload);
  const byGsis = new Map(
    sleeperPlayers
      .filter((player) => player.gsis_id?.trim())
      .map((player) => [player.gsis_id!.trim(), player]),
  );
  const byIdentity = new Map<string, SleeperPlayer[]>();
  sleeperPlayers.forEach((player) => {
    const key = sleeperIdentity(player);
    byIdentity.set(key, [...(byIdentity.get(key) ?? []), player]);
  });

  const alerts: Record<string, InjuryAlert> = {};
  let matchedPlayers = 0;
  players.forEach((player) => {
    if (player.position === 'K' || player.position === 'DST') return;
    const identity = `${normalizePlayerName(player.name)}|${player.team}|${player.position}`;
    const identityMatches = byIdentity.get(identity) ?? [];
    const match =
      (player.gsisId ? byGsis.get(player.gsisId) : undefined) ??
      (identityMatches.length === 1 ? identityMatches[0] : undefined);
    if (!match) return;
    matchedPlayers += 1;
    const hasAlert =
      Boolean(match.injury_status) ||
      Boolean(match.practice_participation) ||
      (match.status != null && match.status !== 'Active');
    if (!hasAlert) return;
    alerts[player.id] = {
      status: match.status ?? null,
      injuryStatus: match.injury_status ?? null,
      bodyPart: match.injury_body_part ?? null,
      notes: match.injury_notes ?? null,
      practiceParticipation: match.practice_participation ?? null,
      newsUpdated: match.news_updated ?? null,
    };
  });
  return { fetchedAt: Date.now(), alerts, matchedPlayers };
}

function injurySummary(alert: InjuryAlert) {
  return [
    alert.injuryStatus,
    alert.bodyPart,
    alert.practiceParticipation,
    alert.notes,
  ]
    .filter(Boolean)
    .join(' · ');
}

function scorePlayer(
  player: Player,
  weights: Weights,
  rosterCounts: PositionCounts,
  currentRound: number,
  recentPositionPicks: number,
  survival: number,
  demand: OpponentDemand,
  positionPool: Player[],
  picksUntilNext: number,
  myPlayers: Player[],
  rosterRules: RosterRules,
) {
  const position = player.position;
  const modeledPosition = position as ModeledPosition;
  const personalized =
    player.coverage === 'modeled'
      ? FACTORS.reduce(
          (total, factor) =>
            total +
            ((player.metrics[factor.key] - 50) / 50) *
              ((weights[modeledPosition][factor.key] - 100) / 100) *
              2,
          0,
        )
      : 0;
  const status = lineupStatus(position, rosterCounts, rosterRules);
  const draftProgress = Math.min(1, Math.max(0, (currentRound - 1) / 12));
  const need =
    status === 'starter'
      ? 0.45 + draftProgress * 1.2
      : status === 'flex'
        ? 0.25 + draftProgress * 0.65
        : 0;
  const positionShare: Record<Position, number> = {
    QB: 0.11,
    RB: 0.27,
    WR: 0.27,
    TE: 0.11,
    K: 0.12,
    DST: 0.12,
  };
  const expectedGone = Math.max(
    1,
    Math.ceil(picksUntilNext * positionShare[position] * demand.pressure),
  );
  const positionIndex = positionPool.findIndex(
    (candidate) => candidate.id === player.id,
  );
  const comparison =
    positionIndex >= 0
      ? positionPool[
          Math.min(positionPool.length - 1, positionIndex + expectedGone)
        ]
      : undefined;
  const rawDrop = comparison
    ? Math.max(0, player.draftScore - comparison.draftScore)
    : 0;
  const scarcity = Math.min(2.4, rawDrop * 0.55);
  const urgency = Math.max(-1.4, Math.min(1.4, ((50 - survival) / 50) * 1.4));
  const opponent = Math.max(-0.8, Math.min(0.8, (demand.pressure - 1) * 0.9));
  const run = Math.min(1.28, recentPositionPicks * 0.16);
  let penalty = 0;
  if ((position === 'K' || position === 'DST') && currentRound < 12) {
    penalty -= (12 - currentRound) * 0.65;
  }
  if (status === 'bench') {
    const depthAfterPick =
      position === 'RB' || position === 'WR' || position === 'TE'
        ? Math.max(
            1,
            (['RB', 'WR', 'TE'] as Position[]).reduce(
              (total, eligible) =>
                total +
                Math.max(
                  0,
                  (rosterCounts[eligible] ?? 0) -
                    rosterRules.starters[eligible],
                ),
              0,
            ) -
              rosterRules.flexCount +
              1,
          )
        : Math.max(
            1,
            (rosterCounts[position] ?? 0) - rosterRules.starters[position] + 1,
          );
    penalty -= depthAfterPick * 0.8;
  }
  if (myPlayers.length >= 8 && player.bye) {
    penalty -=
      myPlayers.filter(
        (teammate) =>
          teammate.position === position && teammate.bye === player.bye,
      ).length * 0.5;
  }
  const total =
    player.draftScore +
    personalized +
    need +
    scarcity +
    urgency +
    opponent +
    run +
    penalty;
  const signals = [
    `${status} fit`,
    scarcity >= 0.5 ? `${rawDrop.toFixed(1)} rank-point drop` : null,
    demand.label !== 'normal' ? `${demand.label} ${position} demand` : null,
    survival <= 35 ? `${survival}% next-turn estimate` : null,
    recentPositionPicks >= 3 ? `${recentPositionPicks} in last 8` : null,
    penalty <= -2 ? 'roster timing penalty' : null,
  ].filter(Boolean);
  return {
    total,
    status,
    summary: signals.slice(0, 3).join(' · '),
    components: {
      personalized,
      need,
      scarcity,
      urgency,
      opponent,
      run,
      penalty,
    },
  };
}

type WeightControlsProps = {
  activePosition: ModeledPosition;
  currentOwnerIsMine: boolean;
  opponentSignal: string;
  recentRun: string;
  setActivePosition: (position: ModeledPosition) => void;
  setWeights: Dispatch<SetStateAction<Weights>>;
  weights: Weights;
};
function WeightControls({
  activePosition,
  currentOwnerIsMine,
  opponentSignal,
  recentRun,
  setActivePosition,
  setWeights,
  weights,
}: WeightControlsProps) {
  const updateWeight = (metric: Metric, value: number) =>
    setWeights((current) => ({
      ...current,
      [activePosition]: { ...current[activePosition], [metric]: value },
    }));
  return (
    <>
      <div className="position-tabs">
        {MODELED_POSITIONS.map((position) => (
          <button
            type="button"
            key={position}
            onClick={() => setActivePosition(position)}
            className={
              activePosition === position
                ? `is-active ${positionClass[position]}`
                : ''
            }
          >
            {position}
          </button>
        ))}
      </div>
      <div className="weight-intro">
        <strong>{activePosition} priorities</strong>
        <span>1.0× preserves the published ranking.</span>
      </div>
      <div className="factor-list">
        {FACTORS.map((factor) => {
          const value = weights[activePosition][factor.key];
          return (
            <div className="factor-control" key={factor.key}>
              <div className="factor-label">
                <div>
                  <strong>{factor.label}</strong>
                  <small>{factor.hint}</small>
                </div>
                <output>{(value / 100).toFixed(2)}×</output>
              </div>
              <Slider
                min={0}
                max={200}
                step={5}
                value={[value]}
                onValueChange={(next) =>
                  updateWeight(
                    factor.key,
                    typeof next === 'number' ? next : next[0],
                  )
                }
                aria-label={`${activePosition} ${factor.label} weight`}
              />
            </div>
          );
        })}
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="reset-weights"
        onClick={() =>
          setWeights((current) => ({
            ...current,
            [activePosition]: DEFAULT_WEIGHTS[activePosition],
          }))
        }
      >
        <RotateCcw /> Reset {activePosition}
      </Button>
      <div className="live-signals">
        <div className="signal-heading">
          <Zap />
          <strong>Live rank signals</strong>
        </div>
        <div>
          <span>Starter need</span>
          <strong>Active by round</strong>
        </div>
        <div>
          <span>Recent run</span>
          <strong>{recentRun}</strong>
        </div>
        <div>
          <span>Opponent needs</span>
          <strong>{opponentSignal}</strong>
        </div>
        <div>
          <span>Next turn</span>
          <strong>{currentOwnerIsMine ? 'Pick now' : 'Tracking'}</strong>
        </div>
      </div>
    </>
  );
}

export default function Home() {
  const [picks, setPicks] = useState<Pick[]>([]);
  const [weights, setWeights] = useState<Weights>(DEFAULT_WEIGHTS);
  const [activePosition, setActivePosition] = useState<ModeledPosition>('WR');
  const [filter, setFilter] = useState<'ALL' | Position>('ALL');
  const [sortMode, setSortMode] = useState<SortMode>('draft');
  const [query, setQuery] = useState('');
  const [teamCount, setTeamCount] = useState(10);
  const [draftSlot, setDraftSlot] = useState(5);
  const [benchCount, setBenchCount] = useState(DEFAULT_BENCH_COUNT);
  const [starterCounts, setStarterCounts] = useState(DEFAULT_STARTER_COUNTS);
  const [flexCount, setFlexCount] = useState(DEFAULT_FLEX_COUNT);
  const [teamNames, setTeamNames] = useState(() => defaultTeamNames(5));
  const [avoidedPlayerIds, setAvoidedPlayerIds] = useState<string[]>([]);
  const [watchedPlayerIds, setWatchedPlayerIds] = useState<string[]>([]);
  const [hideInactivePlayers, setHideInactivePlayers] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [boardOpen, setBoardOpen] = useState(false);
  const [editingPickOverall, setEditingPickOverall] = useState<number | null>(
    null,
  );
  const [pendingTeamCount, setPendingTeamCount] = useState(10);
  const [pendingDraftSlot, setPendingDraftSlot] = useState(5);
  const [pendingBenchCount, setPendingBenchCount] =
    useState(DEFAULT_BENCH_COUNT);
  const [pendingStarterCounts, setPendingStarterCounts] = useState(
    DEFAULT_STARTER_COUNTS,
  );
  const [pendingFlexCount, setPendingFlexCount] = useState(DEFAULT_FLEX_COUNT);
  const [pendingTeamNames, setPendingTeamNames] = useState(() =>
    defaultTeamNames(5),
  );
  const [hydrated, setHydrated] = useState(false);
  const [storageAvailable, setStorageAvailable] = useState<boolean | null>(
    null,
  );
  const [offlineStatus, setOfflineStatus] = useState<
    'checking' | 'ready' | 'unavailable'
  >('checking');
  const [backupMessage, setBackupMessage] = useState<string | null>(null);
  const importInputRef = useRef<HTMLInputElement>(null);
  const [injuryCache, setInjuryCache] = useState<InjuryCache | null>(null);
  const [injuryCacheIsFresh, setInjuryCacheIsFresh] = useState(false);
  const [injuryLoading, setInjuryLoading] = useState(false);
  const [injuryError, setInjuryError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const candidates = [
          readDraftCache(window.localStorage, STORAGE_KEY),
          readDraftCache(window.sessionStorage, STORAGE_BACKUP_KEY),
          readDraftCache(window.localStorage, LEGACY_STORAGE_KEY),
        ].filter((candidate): candidate is DraftCache => Boolean(candidate));
        const restored = candidates.sort((a, b) => b.savedAt - a.savedAt)[0];
        if (restored) {
          setPicks(restored.picks);
          setWeights(restored.weights);
          setTeamCount(restored.teamCount);
          setDraftSlot(restored.draftSlot);
          setBenchCount(restored.benchCount);
          setStarterCounts(restored.starterCounts);
          setFlexCount(restored.flexCount);
          setTeamNames(restored.teamNames);
          setAvoidedPlayerIds(restored.avoidedPlayerIds);
          setWatchedPlayerIds(restored.watchedPlayerIds);
          setHideInactivePlayers(restored.hideInactivePlayers);
        }
        writeDraftCache(
          restored
            ? { ...restored, savedAt: Date.now() }
            : {
                schemaVersion: 1,
                savedAt: Date.now(),
                picks: [],
                weights: DEFAULT_WEIGHTS,
                teamCount: 10,
                draftSlot: 5,
                benchCount: DEFAULT_BENCH_COUNT,
                starterCounts: DEFAULT_STARTER_COUNTS,
                flexCount: DEFAULT_FLEX_COUNT,
                teamNames: defaultTeamNames(5),
                avoidedPlayerIds: [],
                watchedPlayerIds: [],
                hideInactivePlayers: false,
              },
        );
        setStorageAvailable(true);
      } catch {
        setStorageAvailable(false);
      } finally {
        setHydrated(true);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  useEffect(() => {
    if (!hydrated) return;
    try {
      writeDraftCache({
        schemaVersion: 1,
        savedAt: Date.now(),
        picks,
        weights,
        teamCount,
        draftSlot,
        benchCount,
        starterCounts,
        flexCount,
        teamNames,
        avoidedPlayerIds,
        watchedPlayerIds,
        hideInactivePlayers,
      });
    } catch {
      /* Usable without storage. */
    }
  }, [
    avoidedPlayerIds,
    benchCount,
    draftSlot,
    flexCount,
    hideInactivePlayers,
    hydrated,
    picks,
    teamCount,
    teamNames,
    starterCounts,
    watchedPlayerIds,
    weights,
  ]);

  useEffect(() => {
    if (!hydrated) return;
    const flushDraft = () => {
      try {
        writeDraftCache({
          schemaVersion: 1,
          savedAt: Date.now(),
          picks,
          weights,
          teamCount,
          draftSlot,
          benchCount,
          starterCounts,
          flexCount,
          teamNames,
          avoidedPlayerIds,
          watchedPlayerIds,
          hideInactivePlayers,
        });
      } catch {
        /* Usable without storage. */
      }
    };
    const flushWhenHidden = () => {
      if (document.visibilityState === 'hidden') flushDraft();
    };
    window.addEventListener('pagehide', flushDraft);
    document.addEventListener('visibilitychange', flushWhenHidden);
    return () => {
      window.removeEventListener('pagehide', flushDraft);
      document.removeEventListener('visibilitychange', flushWhenHidden);
    };
  }, [
    avoidedPlayerIds,
    benchCount,
    draftSlot,
    flexCount,
    hideInactivePlayers,
    hydrated,
    picks,
    teamCount,
    teamNames,
    starterCounts,
    watchedPlayerIds,
    weights,
  ]);

  useEffect(() => {
    let cancelled = false;
    if (!('serviceWorker' in navigator)) {
      const timer = window.setTimeout(() => setOfflineStatus('unavailable'), 0);
      return () => window.clearTimeout(timer);
    }
    if (process.env.NODE_ENV !== 'production') {
      void navigator.serviceWorker
        .getRegistrations()
        .then((registrations) =>
          Promise.all(
            registrations.map((registration) => registration.unregister()),
          ),
        );
      const timer = window.setTimeout(() => setOfflineStatus('unavailable'), 0);
      return () => window.clearTimeout(timer);
    }
    navigator.serviceWorker
      .register('/sw.js')
      .then(() => navigator.serviceWorker.ready)
      .then(() => {
        if (!cancelled) setOfflineStatus('ready');
      })
      .catch(() => {
        if (!cancelled) setOfflineStatus('unavailable');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const saved = window.localStorage.getItem(INJURY_CACHE_KEY);
        if (saved) {
          const cache = JSON.parse(saved) as InjuryCache;
          setInjuryCache(cache);
          setInjuryCacheIsFresh(
            Date.now() - cache.fetchedAt < INJURY_REFRESH_MS,
          );
        }
      } catch {
        window.localStorage.removeItem(INJURY_CACHE_KEY);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const refreshInjuries = async () => {
    if (injuryCache && Date.now() - injuryCache.fetchedAt < INJURY_REFRESH_MS) {
      setInjuryError(
        'Sleeper permits this full feed once daily; using today’s cached refresh.',
      );
      return;
    }
    setInjuryLoading(true);
    setInjuryError(null);
    try {
      const response = await fetch('https://api.sleeper.app/v1/players/nfl');
      if (!response.ok)
        throw new Error(`Sleeper returned HTTP ${response.status}`);
      const payload = (await response.json()) as Record<string, SleeperPlayer>;
      const cache = buildInjuryCache(payload);
      if (cache.matchedPlayers < 190)
        throw new Error(
          `Only ${cache.matchedPlayers} ranked players matched; keeping prior data`,
        );
      window.localStorage.setItem(INJURY_CACHE_KEY, JSON.stringify(cache));
      setInjuryCache(cache);
      setInjuryCacheIsFresh(true);
    } catch (error) {
      setInjuryError(
        error instanceof Error ? error.message : 'Injury refresh failed',
      );
    } finally {
      setInjuryLoading(false);
    }
  };

  const myTeamIndex = draftSlot - 1;
  const draftedIds = useMemo(
    () => new Set(picks.map((pick) => pick.playerId)),
    [picks],
  );
  const avoidedIds = useMemo(
    () => new Set(avoidedPlayerIds),
    [avoidedPlayerIds],
  );
  const watchedIds = useMemo(
    () => new Set(watchedPlayerIds),
    [watchedPlayerIds],
  );
  const currentPick = picks.length + 1;
  const currentOwner = ownerForPick(currentPick, teamCount);
  const currentRound = Math.floor((currentPick - 1) / teamCount) + 1;
  const currentOwnerIsMine = currentOwner === myTeamIndex;
  const nextMyPick = nextPickForTeam(
    currentPick + (currentOwnerIsMine ? 1 : 0),
    teamCount,
    myTeamIndex,
  );
  const myPlayers = useMemo(
    () =>
      picks
        .filter((pick) => pick.teamIndex === myTeamIndex)
        .map((pick) => players.find((player) => player.id === pick.playerId))
        .filter((player): player is Player => Boolean(player)),
    [myTeamIndex, picks],
  );
  const rosterCounts = useMemo(
    () =>
      myPlayers.reduce<Partial<Record<Position, number>>>(
        (counts, player) => ({
          ...counts,
          [player.position]: (counts[player.position] ?? 0) + 1,
        }),
        {},
      ),
    [myPlayers],
  );
  const rosterRules = useMemo<RosterRules>(
    () => ({ starters: starterCounts, flexCount }),
    [flexCount, starterCounts],
  );
  const starterSlots = useMemo(
    () => buildStarterSlots(starterCounts, flexCount),
    [flexCount, starterCounts],
  );
  const teamRosters = useMemo(
    () =>
      Array.from({ length: teamCount }, (_, teamIndex) =>
        picks
          .filter((pick) => pick.teamIndex === teamIndex)
          .reduce<PositionCounts>((counts, pick) => {
            const position = players.find(
              (player) => player.id === pick.playerId,
            )?.position;
            if (position) counts[position] = (counts[position] ?? 0) + 1;
            return counts;
          }, {}),
      ),
    [picks, teamCount],
  );
  const firstOpponentPick = currentPick + (currentOwnerIsMine ? 1 : 0);
  const opponentDemands = useMemo(
    () =>
      Object.fromEntries(
        ALL_POSITIONS.map((position) => [
          position,
          opponentDemandForPosition({
            position,
            firstOpponentPick,
            targetPick: nextMyPick,
            teamCount,
            myTeamIndex,
            teamRosters,
            currentRound,
            rosterRules,
          }),
        ]),
      ) as Record<Position, OpponentDemand>,
    [
      currentRound,
      firstOpponentPick,
      myTeamIndex,
      nextMyPick,
      rosterRules,
      teamCount,
      teamRosters,
    ],
  );
  const recentPositionCounts = useMemo(() => {
    const counts: PositionCounts = {};
    picks.slice(-8).forEach((pick) => {
      const position = players.find(
        (player) => player.id === pick.playerId,
      )?.position;
      if (position) counts[position] = (counts[position] ?? 0) + 1;
    });
    return counts;
  }, [picks]);
  const draftablePool = useMemo(
    () =>
      players.filter(
        (player) =>
          !draftedIds.has(player.id) &&
          (!hideInactivePlayers || player.currentActive),
      ),
    [draftedIds, hideInactivePlayers],
  );
  const positionPools = useMemo(
    () =>
      Object.fromEntries(
        ALL_POSITIONS.map((position) => [
          position,
          draftablePool
            .filter((candidate) => candidate.position === position)
            .sort((a, b) => b.draftScore - a.draftScore),
        ]),
      ) as Record<Position, Player[]>,
    [draftablePool],
  );
  const rankedCandidates = useMemo(
    () =>
      draftablePool
        .filter((player) => !avoidedIds.has(player.id))
        .map((player) => {
          const demand = opponentDemands[player.position];
          const survival = chanceLasts(player, nextMyPick, demand);
          return {
            player,
            survival,
            demand,
            score: scorePlayer(
              player,
              weights,
              rosterCounts,
              currentRound,
              recentPositionCounts[player.position] ?? 0,
              survival,
              demand,
              positionPools[player.position],
              Math.max(1, nextMyPick - currentPick),
              myPlayers,
              rosterRules,
            ),
          };
        })
        .sort((a, b) => b.score.total - a.score.total),
    [
      currentRound,
      avoidedIds,
      currentPick,
      draftablePool,
      myPlayers,
      nextMyPick,
      opponentDemands,
      positionPools,
      recentPositionCounts,
      rosterCounts,
      rosterRules,
      weights,
    ],
  );
  const available = useMemo(
    () =>
      rankedCandidates
        .filter((item) => filter === 'ALL' || item.player.position === filter)
        .filter((item) =>
          `${item.player.name} ${item.player.team} ${item.player.position}`
            .toLowerCase()
            .includes(query.trim().toLowerCase()),
        )
        .sort((a, b) =>
          sortMode === 'adp'
            ? a.player.adp - b.player.adp
            : sortMode === 'opportunity'
              ? b.player.metrics.opportunity - a.player.metrics.opportunity ||
                a.player.adp - b.player.adp
              : b.score.total - a.score.total,
        ),
    [filter, query, rankedCandidates, sortMode],
  );
  const watchedTargets = useMemo(
    () =>
      rankedCandidates
        .filter((item) => watchedIds.has(item.player.id))
        .map((item) => {
          const cliff = tierCliffForPlayer({
            player: item.player,
            positionPool: positionPools[item.player.position],
            demand: item.demand,
            picksUntilNext: Math.max(1, nextMyPick - currentPick),
            survivalPercent: item.survival,
          });
          return {
            ...item,
            cliff,
            fallback: cliff.fallbackId
              ? players.find((player) => player.id === cliff.fallbackId)
              : null,
          };
        }),
    [currentPick, nextMyPick, positionPools, rankedCandidates, watchedIds],
  );
  const watchedTargetById = useMemo(
    () => new Map(watchedTargets.map((target) => [target.player.id, target])),
    [watchedTargets],
  );
  const recentRun = useMemo(() => {
    const counts: Partial<Record<Position, number>> = {};
    picks.slice(-4).forEach((pick) => {
      const position = players.find(
        (player) => player.id === pick.playerId,
      )?.position;
      if (position) counts[position] = (counts[position] ?? 0) + 1;
    });
    const leader = (Object.entries(counts) as Array<[Position, number]>).sort(
      (a, b) => b[1] - a[1],
    )[0];
    return leader
      ? `${leader[0]} · ${leader[1]} of last ${Math.min(4, picks.length)}`
      : 'No picks yet';
  }, [picks]);
  const hottestOpponentDemand = useMemo(
    () =>
      MODELED_POSITIONS.map((position) => opponentDemands[position]).sort(
        (a, b) => b.pressure - a.pressure,
      )[0],
    [opponentDemands],
  );
  const opponentSignal = hottestOpponentDemand
    ? `${hottestOpponentDemand.position} · ${hottestOpponentDemand.label}`
    : 'Normal';
  const rosterSlots = useMemo(() => {
    const used = new Set<string>();
    return [
      ...starterSlots,
      ...Array.from({ length: benchCount }, () => 'BN' as const),
    ].map((slot) => {
      const player = myPlayers.find(
        (candidate) =>
          !used.has(candidate.id) &&
          (slot === 'BN' ||
            (slot === 'FLEX'
              ? ['RB', 'WR', 'TE'].includes(candidate.position)
              : slot === candidate.position)),
      );
      if (player) used.add(player.id);
      return { slot, player };
    });
  }, [benchCount, myPlayers, starterSlots]);
  const editingPick =
    editingPickOverall === null ? null : picks[editingPickOverall - 1];
  const editingPlayer = editingPick
    ? players.find((player) => player.id === editingPick.playerId)
    : null;
  const draft = (playerId: string) => {
    if (editingPickOverall !== null) {
      setPicks((current) =>
        current.map((pick) =>
          pick.overall === editingPickOverall ? { ...pick, playerId } : pick,
        ),
      );
      setEditingPickOverall(null);
      return;
    }
    setPicks((current) => [
      ...current,
      {
        playerId,
        overall: current.length + 1,
        teamIndex: ownerForPick(current.length + 1, teamCount),
      },
    ]);
  };
  const draftCacheSnapshot = (): DraftCache => ({
    schemaVersion: 1,
    savedAt: Date.now(),
    picks,
    weights,
    teamCount,
    draftSlot,
    benchCount,
    starterCounts,
    flexCount,
    teamNames,
    avoidedPlayerIds,
    watchedPlayerIds,
    hideInactivePlayers,
  });
  const avoidPlayer = (playerId: string) => {
    setAvoidedPlayerIds((current) =>
      current.includes(playerId) ? current : [...current, playerId],
    );
    setWatchedPlayerIds((current) =>
      current.filter((candidate) => candidate !== playerId),
    );
  };
  const toggleWatchPlayer = (playerId: string) => {
    setWatchedPlayerIds((current) =>
      current.includes(playerId)
        ? current.filter((candidate) => candidate !== playerId)
        : [...current, playerId],
    );
  };
  const restorePlayer = (playerId: string) => {
    setAvoidedPlayerIds((current) =>
      current.filter((candidate) => candidate !== playerId),
    );
  };
  const exportDraftBackup = () => {
    const blob = new Blob([JSON.stringify(draftCacheSnapshot(), null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `fantasy-draft-backup-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
    setBackupMessage('Backup downloaded.');
  };
  const importDraftBackup = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const raw = JSON.parse(text) as Record<string, unknown>;
      if (!Array.isArray(raw.picks) || typeof raw.teamCount !== 'number')
        throw new Error('This is not a draft-room backup.');
      const restored = parseDraftCache(text);
      if (!restored) throw new Error('The backup could not be read.');
      setPicks(restored.picks);
      setWeights(restored.weights);
      setTeamCount(restored.teamCount);
      setDraftSlot(restored.draftSlot);
      setBenchCount(restored.benchCount);
      setStarterCounts(restored.starterCounts);
      setFlexCount(restored.flexCount);
      setTeamNames(restored.teamNames);
      setAvoidedPlayerIds(restored.avoidedPlayerIds);
      setWatchedPlayerIds(restored.watchedPlayerIds);
      setHideInactivePlayers(restored.hideInactivePlayers);
      setEditingPickOverall(null);
      writeDraftCache({ ...restored, savedAt: Date.now() });
      setStorageAvailable(true);
      setBackupMessage(`Restored ${restored.picks.length} picks from backup.`);
    } catch (error) {
      setBackupMessage(
        error instanceof Error ? error.message : 'Backup import failed.',
      );
    } finally {
      event.target.value = '';
    }
  };
  const openSettings = (open: boolean) => {
    if (open) {
      setPendingTeamCount(teamCount);
      setPendingDraftSlot(Math.min(draftSlot, teamCount));
      setPendingBenchCount(benchCount);
      setPendingStarterCounts(starterCounts);
      setPendingFlexCount(flexCount);
      setPendingTeamNames(teamNames);
    }
    setSettingsOpen(open);
  };
  const applyLeagueSettings = () => {
    const teamCountChanged = pendingTeamCount !== teamCount;
    setTeamCount(pendingTeamCount);
    setDraftSlot(Math.min(pendingDraftSlot, pendingTeamCount));
    setBenchCount(pendingBenchCount);
    setStarterCounts(pendingStarterCounts);
    setFlexCount(pendingFlexCount);
    setTeamNames(
      normalizeTeamNames(
        pendingTeamNames,
        Math.min(pendingDraftSlot, pendingTeamCount),
      ),
    );
    if (teamCountChanged) {
      setPicks([]);
      setEditingPickOverall(null);
    }
    setSettingsOpen(false);
  };
  const teamCountWillResetDraft = pendingTeamCount !== teamCount;
  const resetBoard = () => {
    setPicks([]);
    setEditingPickOverall(null);
    setSettingsOpen(false);
  };
  const avgDraftRank = myPlayers.length
    ? Math.round(
        myPlayers.reduce((sum, player) => sum + player.modelRank, 0) /
          myPlayers.length,
      )
    : '—';
  const injuryAlertCount = injuryCache
    ? Object.keys(injuryCache.alerts).length
    : 0;
  const injuryPlayers = injuryCache
    ? Object.entries(injuryCache.alerts)
        .map(([playerId, alert]) => ({
          player: players.find((player) => player.id === playerId),
          alert,
        }))
        .filter(
          (
            item,
          ): item is {
            player: Player;
            alert: InjuryAlert;
          } => Boolean(item.player),
        )
    : [];
  const avoidedPlayers = avoidedPlayerIds
    .map((playerId) => players.find((player) => player.id === playerId))
    .filter((player): player is Player => Boolean(player));
  const draftDayReady =
    storageAvailable === true &&
    offlineStatus === 'ready' &&
    RANKING_METADATA.freshnessStatus === 'fresh' &&
    injuryCacheIsFresh;
  return (
    <main className="draft-shell">
      <header className="app-header">
        <div className="brand-lockup">
          <div className="brand-mark">
            <DraftingCompass aria-hidden="true" />
          </div>
          <div>
            <p className="eyebrow">Fantasy Football 2026</p>
            <h1>Draft Room</h1>
          </div>
        </div>
        <div className="draft-status" aria-label="Current draft status">
          <div>
            <span>Round</span>
            <strong>{currentRound}</strong>
          </div>
          <div>
            <span>Overall</span>
            <strong>{currentPick}</strong>
          </div>
          <div className={currentOwnerIsMine ? 'on-clock is-mine' : 'on-clock'}>
            <span>On the clock</span>
            <strong>{teamNames[currentOwner]}</strong>
          </div>
        </div>
        <div className="header-actions">
          <Dialog>
            <DialogTrigger
              render={
                <Button
                  variant="outline"
                  size="sm"
                  className={
                    draftDayReady ? 'health-trigger is-ready' : 'health-trigger'
                  }
                />
              }
            >
              <ShieldCheck /> <span>{draftDayReady ? 'Ready' : 'Health'}</span>
            </DialogTrigger>
            <DialogContent className="health-dialog sm:max-w-2xl">
              <DialogHeader>
                <DialogTitle>Draft-day reliability</DialogTitle>
                <DialogDescription>
                  Confirm the board, data, and offline fallback before the room
                  opens.
                </DialogDescription>
              </DialogHeader>
              <div className="health-grid">
                <div>
                  <span>Draft state</span>
                  <strong>
                    {storageAvailable === null
                      ? 'Checking'
                      : storageAvailable
                        ? `${picks.length} picks saved`
                        : 'Storage blocked'}
                  </strong>
                  <small>Primary save plus same-tab backup</small>
                </div>
                <div>
                  <span>Offline reload</span>
                  <strong>
                    {offlineStatus === 'checking'
                      ? 'Preparing'
                      : offlineStatus === 'ready'
                        ? 'Ready'
                        : 'Unavailable'}
                  </strong>
                  <small>App shell cached on this device</small>
                </div>
                <div>
                  <span>Rankings</span>
                  <strong>{RANKING_METADATA.freshnessStatus}</strong>
                  <small>
                    {RANKING_METADATA.playerCount} players · ADP through{' '}
                    {RANKING_METADATA.ffcWindow.split(' to ')[1]}
                  </small>
                </div>
                <div>
                  <span>Injury feed</span>
                  <strong>
                    {injuryCacheIsFresh
                      ? `${injuryAlertCount} flags loaded`
                      : 'Refresh needed'}
                  </strong>
                  <small>
                    {injuryCache
                      ? new Date(injuryCache.fetchedAt).toLocaleString()
                      : 'No draft-day refresh yet'}
                  </small>
                </div>
                <div>
                  <span>Availability</span>
                  <strong>Opponent-aware</strong>
                  <small>FFC range + every roster before your turn</small>
                </div>
                <div>
                  <span>Demand pressure</span>
                  <strong>{opponentSignal}</strong>
                  <small>
                    {hottestOpponentDemand?.starterPicks ?? 0} upcoming starter
                    needs
                  </small>
                </div>
              </div>
              <div className="reliability-controls">
                <div className="reliability-toggle">
                  <div>
                    <strong>Hide inactive players</strong>
                    <span>Uses the frozen preseason roster status.</span>
                  </div>
                  <Switch
                    aria-label="Hide inactive players"
                    checked={hideInactivePlayers}
                    onCheckedChange={setHideInactivePlayers}
                  />
                </div>
                <div className="backup-actions">
                  <Button variant="outline" onClick={exportDraftBackup}>
                    <Download /> Download backup
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => importInputRef.current?.click()}
                  >
                    <Upload /> Restore backup
                  </Button>
                  <input
                    ref={importInputRef}
                    type="file"
                    accept="application/json,.json"
                    hidden
                    onChange={importDraftBackup}
                  />
                  {backupMessage && <span>{backupMessage}</span>}
                </div>
              </div>
              <div className="health-player-sections">
                <section>
                  <div className="health-section-heading">
                    <strong>Live injury queue</strong>
                    <span>{injuryPlayers.length}</span>
                  </div>
                  <div className="health-player-list">
                    {injuryPlayers.length ? (
                      injuryPlayers.map(({ player, alert }) => (
                        <div key={player.id}>
                          <div>
                            <strong>{player.name}</strong>
                            <span>{injurySummary(alert)}</span>
                          </div>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              avoidedIds.has(player.id)
                                ? restorePlayer(player.id)
                                : avoidPlayer(player.id)
                            }
                          >
                            {avoidedIds.has(player.id) ? 'Restore' : 'Avoid'}
                          </Button>
                        </div>
                      ))
                    ) : (
                      <p>Refresh injuries to populate this queue.</p>
                    )}
                  </div>
                </section>
                <section>
                  <div className="health-section-heading">
                    <strong>Avoided players</strong>
                    <span>{avoidedPlayers.length}</span>
                  </div>
                  <div className="health-player-list">
                    {avoidedPlayers.length ? (
                      avoidedPlayers.map((player) => (
                        <div key={player.id}>
                          <div>
                            <strong>{player.name}</strong>
                            <span>
                              {player.position} · {player.team}
                            </span>
                          </div>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => restorePlayer(player.id)}
                          >
                            Restore
                          </Button>
                        </div>
                      ))
                    ) : (
                      <p>No players manually avoided.</p>
                    )}
                  </div>
                </section>
              </div>
            </DialogContent>
          </Dialog>
          <Button
            variant="outline"
            size="sm"
            className={
              injuryAlertCount ? 'injury-refresh has-alerts' : 'injury-refresh'
            }
            onClick={refreshInjuries}
            disabled={injuryLoading || injuryCacheIsFresh}
            title={
              injuryError ??
              (injuryCache
                ? `${injuryCache.matchedPlayers} ranked skill players matched · refreshed ${new Date(injuryCache.fetchedAt).toLocaleString()}`
                : 'Pull today’s free Sleeper injury and roster-status feed')
            }
          >
            <RefreshCw className={injuryLoading ? 'is-spinning' : ''} />
            <span>
              {injuryLoading
                ? 'Refreshing'
                : injuryCacheIsFresh
                  ? `${injuryAlertCount} injury flags`
                  : 'Refresh injuries'}
            </span>
          </Button>
          <Dialog>
            <DialogTrigger
              render={
                <Button variant="outline" size="sm" className="data-badge" />
              }
            >
              <Database />{' '}
              <span>
                Fresh · ADP {RANKING_METADATA.ffcWindow.split(' to ')[1]}
              </span>
            </DialogTrigger>
            <DialogContent className="source-dialog sm:max-w-xl">
              <DialogHeader>
                <DialogTitle>What these rankings mean</DialogTitle>
                <DialogDescription>
                  {RANKING_METADATA.playerCount} players ranked for a 10-team
                  PPR draft. {RANKING_METADATA.modeledPlayerCount} have
                  bottom-up NFL opportunity context.
                </DialogDescription>
              </DialogHeader>
              <div className="source-list">
                <div>
                  <Badge variant="secondary">NFL</Badge>
                  <strong>Role + environment</strong>
                  <span>
                    nflverse/PFR history, current depth and availability,
                    official team staff evidence, and measured play-caller
                    tendencies. Team certainty is evidence context and does not
                    inflate the rank.
                  </span>
                </div>
                <div>
                  <Badge variant="secondary">Market</Badge>
                  <strong>Fantasy Football Calculator</strong>
                  <span>
                    {RANKING_METADATA.ffcDrafts.toLocaleString()} recent 10-team
                    PPR drafts from {RANKING_METADATA.ffcWindow}. ADP anchors
                    cross-position timing. The published mean, spread, high/low
                    range, and sample count now feed a bounded market estimate,
                    then the actual roster needs of teams selecting before your
                    next turn adjust it. It remains an estimate—not a calibrated
                    probability or point projection—because the free feed does
                    not expose pick-level outcomes. Freshness gate passed at{' '}
                    {RANKING_METADATA.ffcAgeDays} day old.
                  </span>
                </div>
                <div>
                  <Badge variant="secondary">Freeze</Badge>
                  <strong>{RANKING_METADATA.freezeModel}</strong>
                  <span>
                    Cut off {RANKING_METADATA.freezeCutoff}. Fingerprint{' '}
                    {RANKING_METADATA.freezeFingerprint.slice(0, 12)}… verifies
                    the underlying artifact bytes.
                  </span>
                </div>
                <div>
                  <Badge variant="secondary">Live</Badge>
                  <strong>Sleeper player feed</strong>
                  <span>
                    Free, no-token, browser-readable injury, body-part,
                    practice, roster-status, and news-update fields. Refreshed
                    at most once daily and used only as a warning overlay;
                    verify consequential changes in Yahoo.
                  </span>
                </div>
              </div>
              <p className="source-warning">
                No efficiency, touchdown, or fantasy-point projection. QB
                rushing and RB carry calibration remain higher-risk; K/DST are
                market-only. Manual pick tracking works without a league login.
              </p>
              <DialogFooter showCloseButton>
                <a
                  className="source-link"
                  href="https://github.com/demansou/fantasy-football-26/blob/main/docs/DRAFT_INTELLIGENCE_2026.md"
                  target="_blank"
                  rel="noreferrer"
                >
                  Read the draft-intelligence method
                </a>
              </DialogFooter>
            </DialogContent>
          </Dialog>
          <Dialog open={boardOpen} onOpenChange={setBoardOpen}>
            <DialogTrigger render={<Button variant="outline" size="sm" />}>
              <LayoutGrid /> <span>Board</span>
            </DialogTrigger>
            <DialogContent className="draft-board-dialog">
              <DialogHeader>
                <DialogTitle>League draft board</DialogTitle>
                <DialogDescription>
                  Every pick in snake order. Select a completed pick to correct
                  its player without changing later picks.
                </DialogDescription>
              </DialogHeader>
              <div className="draft-board-scroll">
                <div
                  className="draft-board-grid"
                  style={{
                    gridTemplateColumns: `64px repeat(${teamCount}, minmax(142px, 1fr))`,
                  }}
                >
                  <div className="draft-board-corner">Round</div>
                  {teamNames.slice(0, teamCount).map((teamName, teamIndex) => (
                    <div
                      className={
                        teamIndex === myTeamIndex
                          ? 'draft-team-heading is-mine'
                          : 'draft-team-heading'
                      }
                      key={`team-${teamIndex}`}
                    >
                      <strong>{teamName}</strong>
                      <span>Pick {teamIndex + 1}</span>
                      <small>
                        Needs{' '}
                        {rosterNeeds(
                          teamRosters[teamIndex] ?? {},
                          currentRound,
                          rosterRules,
                        )
                          .slice(0, 4)
                          .join('/') || 'depth'}
                      </small>
                    </div>
                  ))}
                  {Array.from(
                    { length: starterSlots.length + benchCount },
                    (_, roundIndex) => {
                      const round = roundIndex + 1;
                      return (
                        <Fragment key={`round-${round}`}>
                          <div className="draft-round-label">{round}</div>
                          {Array.from({ length: teamCount }, (_, teamIndex) => {
                            const overall = pickForRoundAndTeam(
                              round,
                              teamIndex,
                              teamCount,
                            );
                            const pick = picks[overall - 1];
                            const player = pick
                              ? players.find(
                                  (candidate) => candidate.id === pick.playerId,
                                )
                              : null;
                            const isCurrent = overall === currentPick;
                            return (
                              <button
                                aria-label={
                                  player
                                    ? `Correct pick ${overall}, ${player.name}, ${teamNames[teamIndex]}`
                                    : `Pick ${overall}, ${teamNames[teamIndex]}${isCurrent ? ', currently on the clock' : ''}`
                                }
                                className={[
                                  'draft-board-cell',
                                  player ? 'is-filled' : '',
                                  isCurrent ? 'is-current' : '',
                                  teamIndex === myTeamIndex ? 'is-mine' : '',
                                ]
                                  .filter(Boolean)
                                  .join(' ')}
                                disabled={!player}
                                key={`pick-${overall}`}
                                onClick={() => {
                                  setEditingPickOverall(overall);
                                  setBoardOpen(false);
                                }}
                                type="button"
                              >
                                <span>{overall}</span>
                                {player ? (
                                  <>
                                    <strong>{player.name}</strong>
                                    <small>
                                      {player.position} · {player.team}
                                    </small>
                                  </>
                                ) : (
                                  <strong>
                                    {isCurrent ? 'On clock' : '—'}
                                  </strong>
                                )}
                              </button>
                            );
                          })}
                        </Fragment>
                      );
                    },
                  )}
                </div>
              </div>
            </DialogContent>
          </Dialog>
          <Dialog open={settingsOpen} onOpenChange={openSettings}>
            <DialogTrigger render={<Button variant="outline" size="sm" />}>
              <Settings2 /> <span>League</span>
            </DialogTrigger>
            <DialogContent className="league-dialog sm:max-w-2xl">
              <DialogHeader>
                <DialogTitle>League setup</DialogTitle>
                <DialogDescription>
                  Match your league&apos;s draft order and roster positions.
                  These settings drive roster fit and opponent-demand
                  intelligence.
                </DialogDescription>
              </DialogHeader>
              <div className="settings-grid">
                <div className="settings-field">
                  <Label htmlFor="team-count">Teams</Label>
                  <NativeSelect
                    id="team-count"
                    value={pendingTeamCount}
                    onChange={(event) => {
                      const count = Number(event.target.value);
                      setPendingTeamCount(count);
                      setPendingDraftSlot((slot) => Math.min(slot, count));
                    }}
                  >
                    {[8, 10, 12].map((count) => (
                      <NativeSelectOption key={count} value={count}>
                        {count} teams
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </div>
                <div className="settings-field">
                  <Label htmlFor="draft-slot">Your draft slot</Label>
                  <NativeSelect
                    id="draft-slot"
                    value={pendingDraftSlot}
                    onChange={(event) =>
                      setPendingDraftSlot(Number(event.target.value))
                    }
                  >
                    {Array.from({ length: pendingTeamCount }, (_, index) => (
                      <NativeSelectOption key={index + 1} value={index + 1}>
                        Pick {index + 1}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </div>
              </div>
              <div className="roster-position-settings">
                <div className="team-name-heading">
                  <div>
                    <strong>Roster positions</strong>
                    <span>Yahoo W/R/T maps to FLEX; DEF maps to DST.</span>
                  </div>
                  <span>
                    {Object.values(pendingStarterCounts).reduce(
                      (total, count) => total + count,
                      pendingFlexCount + pendingBenchCount,
                    )}{' '}
                    rounds
                  </span>
                </div>
                <div className="roster-position-grid">
                  {ROSTER_POSITION_ORDER.map((position) => {
                    const value =
                      position === 'BN'
                        ? pendingBenchCount
                        : position === 'FLEX'
                          ? pendingFlexCount
                          : pendingStarterCounts[position];
                    const max = position === 'BN' ? 12 : 4;
                    return (
                      <div className="settings-field" key={position}>
                        <Label htmlFor={`roster-${position}`}>
                          {position === 'FLEX' ? 'W/R/T (FLEX)' : position}
                        </Label>
                        <NativeSelect
                          id={`roster-${position}`}
                          value={value}
                          onChange={(event) => {
                            const count = Number(event.target.value);
                            if (position === 'BN') {
                              setPendingBenchCount(count);
                            } else if (position === 'FLEX') {
                              setPendingFlexCount(count);
                            } else {
                              setPendingStarterCounts((current) => ({
                                ...current,
                                [position]: count,
                              }));
                            }
                          }}
                        >
                          {Array.from({ length: max + 1 }, (_, count) => (
                            <NativeSelectOption key={count} value={count}>
                              {count}
                            </NativeSelectOption>
                          ))}
                        </NativeSelect>
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="team-name-settings">
                <div className="team-name-heading">
                  <div>
                    <strong>Team names</strong>
                    <span>Match the draft order shown in Yahoo.</span>
                  </div>
                  <span>{pendingTeamCount} draft slots</span>
                </div>
                <div className="team-name-grid">
                  {Array.from({ length: pendingTeamCount }, (_, teamIndex) => (
                    <div className="team-name-field" key={teamIndex}>
                      <Label htmlFor={`team-name-${teamIndex}`}>
                        Team {teamIndex + 1}
                        {teamIndex === pendingDraftSlot - 1 && (
                          <span>Your slot</span>
                        )}
                      </Label>
                      <Input
                        id={`team-name-${teamIndex}`}
                        maxLength={32}
                        value={pendingTeamNames[teamIndex] ?? ''}
                        onChange={(event) => {
                          const name = event.target.value;
                          setPendingTeamNames((current) =>
                            current.map((value, index) =>
                              index === teamIndex ? name : value,
                            ),
                          );
                        }}
                      />
                    </div>
                  ))}
                </div>
              </div>
              <div className="persistence-note">
                <Check /> Team names, roster positions, picks, target queue,
                settings, and custom weights save in this browser.
              </div>
              <DialogFooter>
                <DialogClose render={<Button variant="outline" />}>
                  Cancel
                </DialogClose>
                <Button variant="secondary" onClick={resetBoard}>
                  <RotateCcw /> Reset board
                </Button>
                <Button onClick={applyLeagueSettings}>
                  {teamCountWillResetDraft
                    ? 'Apply & start fresh'
                    : 'Save league setup'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
          <Dialog>
            <DialogTrigger
              render={
                <Button
                  variant="outline"
                  size="sm"
                  className="mobile-weight-trigger"
                />
              }
            >
              <SlidersHorizontal /> <span>Weights</span>
            </DialogTrigger>
            <DialogContent className="weight-dialog sm:max-w-md">
              <DialogHeader>
                <DialogTitle>Position weights</DialogTitle>
                <DialogDescription>
                  Tilt the model toward the NFL signals you trust most.
                </DialogDescription>
              </DialogHeader>
              <div className="weight-dialog-scroll">
                <WeightControls
                  activePosition={activePosition}
                  currentOwnerIsMine={currentOwnerIsMine}
                  opponentSignal={opponentSignal}
                  recentRun={recentRun}
                  setActivePosition={setActivePosition}
                  setWeights={setWeights}
                  weights={weights}
                />
              </div>
            </DialogContent>
          </Dialog>
          <Button
            variant="outline"
            size="sm"
            disabled={!picks.length}
            onClick={() => {
              setEditingPickOverall(null);
              setPicks((current) => current.slice(0, -1));
            }}
          >
            <Undo2 /> Undo
          </Button>
        </div>
      </header>
      <section className="pick-ticker" aria-label="Recent draft picks">
        <span className="ticker-label">Last picks</span>
        {picks.length === 0 && (
          <span className="ticker-empty">
            Board is clean—enter picks as they happen.
          </span>
        )}
        {picks.slice(-5).map((pick) => {
          const player = players.find((item) => item.id === pick.playerId);
          return player ? (
            <div className="ticker-pick" key={pick.overall}>
              <span
                className={`position-dot ${positionClass[player.position]}`}
              />
              <strong>{pick.overall}</strong>
              <span>{player.name}</span>
              <small>
                {player.position} · {teamNames[pick.teamIndex]}
              </small>
            </div>
          ) : null;
        })}
        <div className="ticker-save" aria-live="polite">
          <Check />{' '}
          {storageAvailable === null
            ? 'Restoring draft…'
            : storageAvailable
              ? 'Draft saved locally'
              : 'Browser storage blocked'}
        </div>
        <div className="ticker-next">
          <Zap /> Pick {currentPick} · {teamNames[currentOwner]}
        </div>
      </section>
      <div className="workspace-grid">
        <aside className="roster-panel panel-surface">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Roster construction</p>
              <h2>My Team</h2>
            </div>
            <span className="panel-count">
              {myPlayers.length}/{starterSlots.length + benchCount}
            </span>
          </div>
          <div className="roster-summary">
            <div>
              <span>Avg rank</span>
              <strong>{avgDraftRank}</strong>
            </div>
            <div>
              <span>Draft slot</span>
              <strong>{draftSlot}</strong>
            </div>
            <div>
              <span>Bench</span>
              <strong>{benchCount}</strong>
            </div>
          </div>
          <ScrollArea className="roster-scroll">
            <div className="roster-slots">
              {rosterSlots.map(({ slot, player }, index) => (
                <div
                  className={player ? 'roster-slot is-filled' : 'roster-slot'}
                  key={`${slot}-${index}`}
                >
                  <span className="slot-label">{slot}</span>
                  {player ? (
                    <>
                      <div>
                        <strong>{player.name}</strong>
                        <small>
                          {player.team} · Bye {player.bye}
                        </small>
                      </div>
                      <Check className="slot-check" />
                    </>
                  ) : (
                    <span className="empty-slot">
                      {slot === 'BN' ? 'Open bench spot' : 'Open roster slot'}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </ScrollArea>
          <div className="roster-footer">
            <span>{teamCount}-team PPR</span>
            <span>{benchCount} bench · Snake</span>
          </div>
        </aside>
        <section className="player-board panel-surface">
          <div className="board-toolbar">
            <div>
              <p className="eyebrow">Draft-day recommendation</p>
              <h2>Available players</h2>
            </div>
            <div className="board-tools">
              <NativeSelect
                aria-label="Ranking order"
                value={sortMode}
                onChange={(event) =>
                  setSortMode(event.target.value as SortMode)
                }
              >
                <NativeSelectOption value="draft">
                  Draft rank
                </NativeSelectOption>
                <NativeSelectOption value="opportunity">
                  NFL opportunity
                </NativeSelectOption>
                <NativeSelectOption value="adp">Market ADP</NativeSelectOption>
              </NativeSelect>
              <div className="search-wrap">
                <Search />
                <Input
                  aria-label="Search available players"
                  placeholder="Search player or team"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </div>
            </div>
          </div>
          {editingPick && editingPlayer && (
            <output className="pick-correction">
              <div>
                <strong>Correcting pick {editingPick.overall}</strong>
                <span>
                  Replace {editingPlayer.name} for{' '}
                  {teamNames[editingPick.teamIndex]}.
                </span>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setEditingPickOverall(null)}
              >
                Cancel correction
              </Button>
            </output>
          )}
          <div className="position-filters">
            {(['ALL', ...ALL_POSITIONS] as const).map((position) => (
              <button
                key={position}
                type="button"
                className={
                  filter === position ? 'filter-chip is-active' : 'filter-chip'
                }
                onClick={() => setFilter(position)}
              >
                {position}
              </button>
            ))}
            <span className="rank-note">
              Next pick {nextMyPick} · top {available[0]?.player.name ?? '—'} ·{' '}
              {available[0]?.survival ?? 0}% est. to last
            </span>
          </div>
          <section className="target-queue" aria-label="Draft watchlist">
            <div className="target-queue-heading">
              <span className="target-queue-icon">
                <Star />
              </span>
              <div>
                <strong>Target queue</strong>
                <span>
                  {watchedTargets.length
                    ? `${watchedTargets.length} available · sorted by live rank`
                    : 'Star players to track tier risk and fallbacks'}
                </span>
              </div>
            </div>
            {watchedTargets.length > 0 && (
              <div className="target-cards">
                {watchedTargets.map(({ player, survival, cliff, fallback }) => (
                  <div
                    className={`target-card is-${cliff.level}`}
                    key={player.id}
                  >
                    <button
                      className="target-card-main"
                      onClick={() => {
                        setFilter('ALL');
                        setQuery(player.name);
                      }}
                      title={`Show ${player.name} in the player list`}
                      type="button"
                    >
                      <span
                        className={`position-pill ${positionClass[player.position]}`}
                      >
                        {player.position}
                      </span>
                      <span>
                        <strong>{player.name}</strong>
                        <small>
                          {cliff.label} · {survival}% est.
                        </small>
                        <small>
                          {fallback
                            ? `Fallback: ${fallback.name}`
                            : `${cliff.remainingInTier} left in Tier ${player.tier}`}
                        </small>
                      </span>
                    </button>
                    <button
                      aria-label={`Remove ${player.name} from target queue`}
                      className="target-remove"
                      onClick={() => toggleWatchPlayer(player.id)}
                      title="Remove from target queue"
                      type="button"
                    >
                      <Star fill="currentColor" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>
          <div className="opponent-intelligence">
            <div>
              <strong>Opponent roster intelligence</strong>
              <span>
                {opponentDemands.RB.upcomingPicks} selections before pick{' '}
                {nextMyPick}
              </span>
            </div>
            {MODELED_POSITIONS.map((position) => {
              const demand = opponentDemands[position];
              return (
                <span
                  className={`demand-chip is-${demand.label}`}
                  key={position}
                  title={`${demand.starterPicks} teams have an open ${position} starter; ${demand.flexPicks} can use ${position} in flex`}
                >
                  {position} {demand.label} · {demand.starterPicks} need
                </span>
              );
            })}
          </div>
          {injuryError && (
            <div className="injury-notice" role="alert">
              {injuryError}
            </div>
          )}
          <div className="player-table-header">
            <span>Rank / player</span>
            <span>Opp.</span>
            <span>ADP</span>
            <span>Why</span>
            <span />
          </div>
          <ScrollArea className="player-scroll">
            <div className="player-list">
              {available.map(({ player, score, survival, demand }, index) => {
                const liveAlert = injuryCache?.alerts[player.id];
                const watchedTarget = watchedTargetById.get(player.id);
                return (
                  <article
                    className={[
                      'player-row',
                      liveAlert ? 'has-live-injury' : '',
                      !player.currentActive ? 'is-inactive' : '',
                      watchedTarget ? 'is-watched' : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    key={player.id}
                  >
                    <div className="player-identity">
                      <span className="rank-number">{index + 1}</span>
                      <span
                        className={`position-pill ${positionClass[player.position]}`}
                      >
                        {player.position}
                      </span>
                      <div>
                        <strong>{player.name}</strong>
                        <small>
                          {player.team} · Bye {player.bye} · {player.position}
                          {player.positionRank} · Tier {player.tier}
                        </small>
                        {watchedTarget && (
                          <span
                            className={`tier-alert is-${watchedTarget.cliff.level}`}
                            title={`${watchedTarget.cliff.remainingInTier} players remain in Tier ${player.tier}; about ${watchedTarget.cliff.expectedPositionPicks} ${player.position}s may be selected before pick ${nextMyPick}. Next-tier score drop: ${watchedTarget.cliff.scoreDrop.toFixed(1)}.`}
                          >
                            <Star fill="currentColor" />{' '}
                            {watchedTarget.cliff.label}
                          </span>
                        )}
                        {liveAlert && (
                          <span
                            className="injury-pill"
                            title={
                              liveAlert.newsUpdated
                                ? `Sleeper news updated ${new Date(liveAlert.newsUpdated).toLocaleString()}`
                                : 'Sleeper live status'
                            }
                          >
                            {injurySummary(liveAlert)}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="stat-cell">
                      <strong>
                        {player.coverage === 'modeled'
                          ? player.metrics.opportunity.toFixed(0)
                          : '—'}
                      </strong>
                      <small>
                        {player.coverage === 'modeled' ? 'index' : 'market'}
                      </small>
                    </div>
                    <div className="stat-cell">
                      <strong>{player.adp.toFixed(1)}</strong>
                      <small
                        title={`Opponent-adjusted market estimate. FFC observed range ${player.marketHighPick}-${player.marketLowPick} across ${player.timesDrafted} drafts; ${demand.starterPicks} upcoming teams need a ${player.position} starter.`}
                      >
                        {survival}% est. ·{' '}
                        {player.rankDelta > 0
                          ? `↑${player.rankDelta}`
                          : player.rankDelta < 0
                            ? `↓${Math.abs(player.rankDelta)}`
                            : 'even'}
                      </small>
                    </div>
                    <div className="model-cell">
                      <strong>{score.total.toFixed(1)}</strong>
                      <span
                        title={`${score.summary}. ${player.context}. Components: need ${score.components.need.toFixed(1)}, scarcity ${score.components.scarcity.toFixed(1)}, timing ${score.components.urgency.toFixed(1)}, opponents ${score.components.opponent.toFixed(1)}, run ${score.components.run.toFixed(1)}, penalty ${score.components.penalty.toFixed(1)}.`}
                      >
                        {!player.currentActive
                          ? `${player.status} · ${score.summary}`
                          : score.summary || player.context}
                      </span>
                    </div>
                    <div className="player-actions">
                      <Button
                        size="sm"
                        variant={
                          editingPickOverall !== null || currentOwnerIsMine
                            ? 'default'
                            : 'outline'
                        }
                        onClick={() => draft(player.id)}
                      >
                        {editingPickOverall !== null
                          ? `Replace pick ${editingPickOverall}`
                          : currentOwnerIsMine
                            ? 'Draft'
                            : 'Mark gone'}
                      </Button>
                      <Button
                        aria-label={
                          watchedIds.has(player.id)
                            ? `Remove ${player.name} from target queue`
                            : `Add ${player.name} to target queue`
                        }
                        className={
                          watchedIds.has(player.id)
                            ? 'watch-toggle is-active'
                            : 'watch-toggle'
                        }
                        size="icon-sm"
                        title={
                          watchedIds.has(player.id)
                            ? 'Remove from target queue'
                            : 'Add to target queue'
                        }
                        variant="ghost"
                        onClick={() => toggleWatchPlayer(player.id)}
                      >
                        <Star
                          fill={
                            watchedIds.has(player.id) ? 'currentColor' : 'none'
                          }
                        />
                      </Button>
                      <Button
                        aria-label={`Avoid ${player.name}`}
                        size="icon-sm"
                        title={`Hide ${player.name} from recommendations`}
                        variant="ghost"
                        onClick={() => avoidPlayer(player.id)}
                      >
                        <EyeOff />
                      </Button>
                    </div>
                  </article>
                );
              })}
            </div>
          </ScrollArea>
        </section>
        <aside className="weights-panel panel-surface">
          <div className="panel-heading weights-heading">
            <div>
              <p className="eyebrow">Your draft model</p>
              <h2>Position weights</h2>
            </div>
            <SlidersHorizontal />
          </div>
          <WeightControls
            activePosition={activePosition}
            currentOwnerIsMine={currentOwnerIsMine}
            opponentSignal={opponentSignal}
            recentRun={recentRun}
            setActivePosition={setActivePosition}
            setWeights={setWeights}
            weights={weights}
          />
        </aside>
      </div>
    </main>
  );
}
