'use client';

import {
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react';
import {
  Check,
  Database,
  DraftingCompass,
  RefreshCw,
  RotateCcw,
  Search,
  Settings2,
  SlidersHorizontal,
  Undo2,
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
import { PLAYERS, RANKING_METADATA } from '@/data/players';

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
const STORAGE_KEY = 'fantasy-football-26:draft-room:v2';
const INJURY_CACHE_KEY = 'fantasy-football-26:sleeper-injuries:v1';
const INJURY_REFRESH_MS = 20 * 60 * 60 * 1000;
const DEFAULT_BENCH_COUNT = 6;
const STARTER_SLOTS: RosterSlot[] = [
  'QB',
  'RB',
  'RB',
  'WR',
  'WR',
  'TE',
  'FLEX',
  'K',
  'DST',
];
const MODELED_POSITIONS: ModeledPosition[] = ['QB', 'RB', 'WR', 'TE'];
const ALL_POSITIONS: Position[] = ['QB', 'RB', 'WR', 'TE', 'K', 'DST'];
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

function chanceLasts(player: Player, targetPick: number) {
  const deviation = Math.max(1, player.adpStdev);
  const survival = 1 - normalCdf((targetPick - 0.5 - player.adp) / deviation);
  return Math.round(Math.max(0.01, Math.min(0.99, survival)) * 100);
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
  picks: Pick[],
  rosterCounts: Partial<Record<Position, number>>,
  currentRound: number,
) {
  if (player.coverage === 'market_only') return player.draftScore;
  const position = player.position as ModeledPosition;
  const personalized = FACTORS.reduce(
    (total, factor) =>
      total +
      ((player.metrics[factor.key] - 50) / 50) *
        ((weights[position][factor.key] - 100) / 100) *
        2,
    0,
  );
  const run = picks
    .slice(-8)
    .filter(
      (pick) =>
        players.find((item) => item.id === pick.playerId)?.position ===
        position,
    ).length;
  const needs: Record<ModeledPosition, number> = { QB: 1, RB: 2, WR: 2, TE: 1 };
  const openStarter = (rosterCounts[position] ?? 0) < needs[position];
  const needBoost =
    openStarter &&
    currentRound >= (position === 'QB' || position === 'TE' ? 5 : 2)
      ? 0.8
      : 0;
  return player.draftScore + personalized + run * 0.16 + needBoost;
}

type WeightControlsProps = {
  activePosition: ModeledPosition;
  currentOwnerIsMine: boolean;
  recentRun: string;
  setActivePosition: (position: ModeledPosition) => void;
  setWeights: Dispatch<SetStateAction<Weights>>;
  weights: Weights;
};
function WeightControls({
  activePosition,
  currentOwnerIsMine,
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
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [pendingTeamCount, setPendingTeamCount] = useState(10);
  const [pendingDraftSlot, setPendingDraftSlot] = useState(5);
  const [pendingBenchCount, setPendingBenchCount] =
    useState(DEFAULT_BENCH_COUNT);
  const [hydrated, setHydrated] = useState(false);
  const [injuryCache, setInjuryCache] = useState<InjuryCache | null>(null);
  const [injuryCacheIsFresh, setInjuryCacheIsFresh] = useState(false);
  const [injuryLoading, setInjuryLoading] = useState(false);
  const [injuryError, setInjuryError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const saved = window.localStorage.getItem(STORAGE_KEY);
        if (saved) {
          const parsed = JSON.parse(saved) as {
            picks?: Pick[];
            weights?: Weights;
            teamCount?: number;
            draftSlot?: number;
            benchCount?: number;
          };
          if (Array.isArray(parsed.picks))
            setPicks(
              parsed.picks.filter((pick) =>
                players.some((player) => player.id === pick.playerId),
              ),
            );
          if (parsed.weights) setWeights(parsed.weights);
          const savedTeamCount = [8, 10, 12].includes(parsed.teamCount ?? 0)
            ? parsed.teamCount!
            : 10;
          setTeamCount(savedTeamCount);
          if (
            typeof parsed.draftSlot === 'number' &&
            parsed.draftSlot >= 1 &&
            parsed.draftSlot <= savedTeamCount
          )
            setDraftSlot(parsed.draftSlot);
          if (
            typeof parsed.benchCount === 'number' &&
            parsed.benchCount >= 0 &&
            parsed.benchCount <= 12
          )
            setBenchCount(parsed.benchCount);
        }
      } catch {
        window.localStorage.removeItem(STORAGE_KEY);
      } finally {
        setHydrated(true);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ picks, weights, teamCount, draftSlot, benchCount }),
      );
    } catch {
      /* Usable without storage. */
    }
  }, [benchCount, draftSlot, hydrated, picks, teamCount, weights]);

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
  const teamNames = useMemo(
    () =>
      Array.from({ length: teamCount }, (_, index) =>
        index === myTeamIndex ? 'My Team' : TEAM_LABELS[index],
      ),
    [myTeamIndex, teamCount],
  );
  const draftedIds = useMemo(
    () => new Set(picks.map((pick) => pick.playerId)),
    [picks],
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
  const available = useMemo(
    () =>
      players
        .filter((player) => !draftedIds.has(player.id))
        .filter((player) => filter === 'ALL' || player.position === filter)
        .filter((player) =>
          `${player.name} ${player.team} ${player.position}`
            .toLowerCase()
            .includes(query.trim().toLowerCase()),
        )
        .map((player) => ({
          player,
          score: scorePlayer(
            player,
            weights,
            picks,
            rosterCounts,
            currentRound,
          ),
        }))
        .sort((a, b) =>
          sortMode === 'adp'
            ? a.player.adp - b.player.adp
            : sortMode === 'opportunity'
              ? b.player.metrics.opportunity - a.player.metrics.opportunity ||
                a.player.adp - b.player.adp
              : b.score - a.score,
        ),
    [
      currentRound,
      draftedIds,
      filter,
      picks,
      query,
      rosterCounts,
      sortMode,
      weights,
    ],
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
  const rosterSlots = useMemo(() => {
    const used = new Set<string>();
    return [
      ...STARTER_SLOTS,
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
  }, [benchCount, myPlayers]);
  const draft = (playerId: string) =>
    setPicks((current) => [
      ...current,
      {
        playerId,
        overall: current.length + 1,
        teamIndex: ownerForPick(current.length + 1, teamCount),
      },
    ]);
  const openSettings = (open: boolean) => {
    if (open) {
      setPendingTeamCount(teamCount);
      setPendingDraftSlot(Math.min(draftSlot, teamCount));
      setPendingBenchCount(benchCount);
    }
    setSettingsOpen(open);
  };
  const applyLeagueSettings = () => {
    setTeamCount(pendingTeamCount);
    setDraftSlot(Math.min(pendingDraftSlot, pendingTeamCount));
    setBenchCount(pendingBenchCount);
    setPicks([]);
    setSettingsOpen(false);
  };
  const resetBoard = () => {
    setPicks([]);
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
              <Database /> <span>Fresh · ADP Sep 2</span>
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
                    cross-position timing, and its observed spread powers the
                    normal-curve estimate of whether a player lasts to your next
                    pick. That heuristic is not a calibrated probability or a
                    point projection. Freshness gate passed at{' '}
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
                  href="https://github.com/demansou/fantasy-football-26/blob/main/docs/NFL_ENVIRONMENT_RECOMMENDATION_2026.md"
                  target="_blank"
                  rel="noreferrer"
                >
                  Read the methodology
                </a>
              </DialogFooter>
            </DialogContent>
          </Dialog>
          <Dialog open={settingsOpen} onOpenChange={openSettings}>
            <DialogTrigger render={<Button variant="outline" size="sm" />}>
              <Settings2 /> <span>League</span>
            </DialogTrigger>
            <DialogContent className="league-dialog sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>League setup</DialogTitle>
                <DialogDescription>
                  Set the snake draft shape. Rankings use 10-team PPR market
                  timing, while pick ownership adapts to 8, 10, or 12 teams.
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
                <div className="settings-field">
                  <Label htmlFor="bench-count">Bench spots</Label>
                  <NativeSelect
                    id="bench-count"
                    value={pendingBenchCount}
                    onChange={(event) =>
                      setPendingBenchCount(Number(event.target.value))
                    }
                  >
                    {Array.from({ length: 13 }, (_, count) => (
                      <NativeSelectOption key={count} value={count}>
                        {count} {count === 1 ? 'spot' : 'spots'}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </div>
              </div>
              <div className="persistence-note">
                <Check /> Picks, settings, and custom weights save in this
                browser.
              </div>
              <DialogFooter>
                <DialogClose render={<Button variant="outline" />}>
                  Cancel
                </DialogClose>
                <Button variant="secondary" onClick={resetBoard}>
                  <RotateCcw /> Reset board
                </Button>
                <Button onClick={applyLeagueSettings}>
                  Apply &amp; start fresh
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
            onClick={() => setPicks((current) => current.slice(0, -1))}
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
              <small>{player.position}</small>
            </div>
          ) : null;
        })}
        <div className="ticker-next">
          <Zap /> Pick {currentPick} ready
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
              {myPlayers.length}/{STARTER_SLOTS.length + benchCount}
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
              {available[0] ? chanceLasts(available[0].player, nextMyPick) : 0}%
              lasts
            </span>
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
              {available.map(({ player, score }, index) => {
                const liveAlert = injuryCache?.alerts[player.id];
                return (
                  <article
                    className={
                      liveAlert
                        ? 'player-row has-live-injury'
                        : !player.currentActive
                          ? 'player-row is-inactive'
                          : 'player-row'
                    }
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
                        title={`Observed pick range ${player.marketHighPick}-${player.marketLowPick} across ${player.timesDrafted} drafts`}
                      >
                        {chanceLasts(player, nextMyPick)}% lasts ·{' '}
                        {player.rankDelta > 0
                          ? `↑${player.rankDelta}`
                          : player.rankDelta < 0
                            ? `↓${Math.abs(player.rankDelta)}`
                            : 'even'}
                      </small>
                    </div>
                    <div className="model-cell">
                      <strong>{score.toFixed(1)}</strong>
                      <span title={player.context}>
                        {!player.currentActive
                          ? `${player.status} · ${player.context}`
                          : player.context}
                      </span>
                    </div>
                    <Button
                      size="sm"
                      variant={currentOwnerIsMine ? 'default' : 'outline'}
                      onClick={() => draft(player.id)}
                    >
                      {currentOwnerIsMine ? 'Draft' : 'Mark gone'}
                    </Button>
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
