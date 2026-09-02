'use client';

import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from 'react';
import {
  Check,
  Database,
  DraftingCompass,
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
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Slider } from '@/components/ui/slider';

type Position = 'QB' | 'RB' | 'WR' | 'TE';
type Metric = 'opportunity' | 'environment' | 'coaching' | 'line' | 'stability' | 'upside';
type Player = {
  id: string;
  name: string;
  position: Position;
  team: string;
  bye: number;
  projection: number;
  adp: number;
  baseScore: number;
  tier: number;
  context: string;
  metrics: Record<Metric, number>;
};
type Pick = { playerId: string; overall: number; teamIndex: number };
type Weights = Record<Position, Record<Metric, number>>;
type RosterSlot = Position | 'FLEX' | 'K' | 'DST' | 'BN';

const TEAM_LABELS = [
  'Gridiron Ghosts', 'Sunday Scaries', 'Fourth & Long', 'Waiver Wired', 'Red Zone Radio',
  'Two Minute Drill', 'Goal Line Stand', 'Pocket Presence', 'The Audible', 'Sunday Film Club',
  'Route Concepts', 'Clock Managers',
];
const STORAGE_KEY = 'fantasy-football-26:draft-room:v1';
const DEFAULT_BENCH_COUNT = 6;
const STARTER_SLOTS: RosterSlot[] = ['QB', 'RB', 'RB', 'WR', 'WR', 'TE', 'FLEX', 'K', 'DST'];

const DEFAULT_WEIGHTS: Weights = {
  WR: { opportunity: 135, environment: 125, coaching: 110, line: 75, stability: 105, upside: 110 },
  RB: { opportunity: 140, environment: 105, coaching: 85, line: 130, stability: 110, upside: 95 },
  QB: { opportunity: 90, environment: 105, coaching: 110, line: 105, stability: 145, upside: 85 },
  TE: { opportunity: 130, environment: 120, coaching: 100, line: 70, stability: 115, upside: 105 },
};

const FACTORS: Record<Position, Array<{ key: Metric; label: string; hint: string }>> = {
  WR: [
    { key: 'opportunity', label: 'Target volume', hint: 'Routes, share, valuable targets' },
    { key: 'environment', label: 'QB + pass offense', hint: 'Accuracy and projected dropbacks' },
    { key: 'coaching', label: 'OC / play caller', hint: 'Pass tendency, pace, continuity' },
    { key: 'stability', label: 'Role stability', hint: 'Weekly floor and competition' },
    { key: 'upside', label: 'Ceiling', hint: 'Explosive and touchdown paths' },
  ],
  RB: [
    { key: 'opportunity', label: 'Backfield volume', hint: 'Carries, targets, goal-line work' },
    { key: 'line', label: 'Run blocking', hint: 'Line quality and yards before contact' },
    { key: 'environment', label: 'Game environment', hint: 'Scoring chances and positive scripts' },
    { key: 'stability', label: 'Role stability', hint: 'Competition and three-down security' },
    { key: 'upside', label: 'Ceiling', hint: 'Breakaway and touchdown paths' },
  ],
  QB: [
    { key: 'stability', label: 'Low weekly variance', hint: 'Floor probability and continuity' },
    { key: 'environment', label: 'Passing environment', hint: 'Weapons, pace, scoring chances' },
    { key: 'coaching', label: 'Play caller', hint: 'Efficiency and scheme continuity' },
    { key: 'line', label: 'Pass protection', hint: 'Pressure and sack prevention' },
    { key: 'upside', label: 'Rushing / ceiling', hint: 'Designed runs and scrambles' },
  ],
  TE: [
    { key: 'opportunity', label: 'Route + target volume', hint: 'Participation and target share' },
    { key: 'environment', label: 'QB + pass offense', hint: 'Accuracy and scoring environment' },
    { key: 'stability', label: 'Role stability', hint: 'Competition and weekly routes' },
    { key: 'coaching', label: 'Scheme fit', hint: 'Middle-field and red-zone usage' },
    { key: 'upside', label: 'Ceiling', hint: 'End-zone and explosive usage' },
  ],
};

const players: Player[] = [
  { id: 'wr-1', name: 'Avery Collins', position: 'WR', team: 'HOU', bye: 7, projection: 292, adp: 1.8, baseScore: 96.2, tier: 1, context: 'Elite share · high-volume pass offense', metrics: { opportunity: 94, environment: 91, coaching: 84, line: 74, stability: 91, upside: 93 } },
  { id: 'rb-1', name: 'Marcus Reed', position: 'RB', team: 'ATL', bye: 5, projection: 286, adp: 2.4, baseScore: 95.4, tier: 1, context: 'Three-down role · top line profile', metrics: { opportunity: 95, environment: 84, coaching: 78, line: 93, stability: 90, upside: 88 } },
  { id: 'wr-2', name: 'Jordan Hayes', position: 'WR', team: 'MIN', bye: 6, projection: 281, adp: 3.1, baseScore: 94.6, tier: 1, context: 'Target earner · stable QB/OC pairing', metrics: { opportunity: 93, environment: 87, coaching: 88, line: 70, stability: 93, upside: 87 } },
  { id: 'rb-2', name: 'Darius Brooks', position: 'RB', team: 'DET', bye: 8, projection: 276, adp: 4.2, baseScore: 93.8, tier: 1, context: 'Efficient line · strong receiving role', metrics: { opportunity: 88, environment: 94, coaching: 91, line: 96, stability: 84, upside: 94 } },
  { id: 'wr-3', name: 'Malik Turner', position: 'WR', team: 'CIN', bye: 10, projection: 271, adp: 5.5, baseScore: 92.7, tier: 1, context: 'High-value targets · aggressive profile', metrics: { opportunity: 90, environment: 92, coaching: 82, line: 68, stability: 88, upside: 92 } },
  { id: 'rb-3', name: 'Theo Grant', position: 'RB', team: 'PHI', bye: 9, projection: 264, adp: 7.2, baseScore: 90.8, tier: 2, context: 'Goal-line engine · elite rush environment', metrics: { opportunity: 90, environment: 92, coaching: 88, line: 97, stability: 86, upside: 90 } },
  { id: 'wr-4', name: 'Cameron Price', position: 'WR', team: 'LAR', bye: 8, projection: 258, adp: 8.8, baseScore: 89.9, tier: 2, context: 'Condensed targets · proven play caller', metrics: { opportunity: 91, environment: 86, coaching: 94, line: 72, stability: 82, upside: 86 } },
  { id: 'te-1', name: 'Eli Mercer', position: 'TE', team: 'LV', bye: 10, projection: 246, adp: 11.4, baseScore: 88.4, tier: 1, context: 'Primary read share · mismatch usage', metrics: { opportunity: 94, environment: 78, coaching: 81, line: 69, stability: 89, upside: 93 } },
  { id: 'wr-5', name: 'Xavier Stone', position: 'WR', team: 'GB', bye: 5, projection: 244, adp: 13.6, baseScore: 86.9, tier: 2, context: 'Fast offense · target competition', metrics: { opportunity: 76, environment: 90, coaching: 88, line: 79, stability: 67, upside: 91 } },
  { id: 'rb-4', name: 'Nolan Pierce', position: 'RB', team: 'BAL', bye: 7, projection: 241, adp: 14.2, baseScore: 86.3, tier: 2, context: 'Heavy rush script · limited receiving', metrics: { opportunity: 89, environment: 91, coaching: 86, line: 90, stability: 87, upside: 78 } },
  { id: 'qb-1', name: 'Cole Bennett', position: 'QB', team: 'BUF', bye: 12, projection: 354, adp: 19.5, baseScore: 84.8, tier: 1, context: 'Stable floor · elite rushing leverage', metrics: { opportunity: 94, environment: 88, coaching: 86, line: 82, stability: 92, upside: 96 } },
  { id: 'te-2', name: 'Mason Cole', position: 'TE', team: 'ARI', bye: 11, projection: 231, adp: 21.8, baseScore: 83.9, tier: 1, context: 'Route leader · consistent middle role', metrics: { opportunity: 90, environment: 81, coaching: 83, line: 68, stability: 91, upside: 84 } },
  { id: 'qb-2', name: 'Jalen Cross', position: 'QB', team: 'BAL', bye: 7, projection: 346, adp: 23.2, baseScore: 82.7, tier: 1, context: 'Rushing floor · wider pass variance', metrics: { opportunity: 92, environment: 86, coaching: 88, line: 84, stability: 84, upside: 97 } },
  { id: 'wr-6', name: 'Devin Ross', position: 'WR', team: 'TB', bye: 9, projection: 232, adp: 24.6, baseScore: 81.5, tier: 3, context: 'Reliable routes · modest explosives', metrics: { opportunity: 86, environment: 79, coaching: 76, line: 73, stability: 92, upside: 72 } },
  { id: 'rb-5', name: 'Andre Foster', position: 'RB', team: 'IND', bye: 11, projection: 228, adp: 27.3, baseScore: 80.8, tier: 3, context: 'Clear lead role · average blocking', metrics: { opportunity: 90, environment: 72, coaching: 70, line: 66, stability: 85, upside: 82 } },
  { id: 'qb-3', name: 'Grant Ellis', position: 'QB', team: 'KC', bye: 6, projection: 331, adp: 31.1, baseScore: 79.7, tier: 2, context: 'Low turnover risk · elite play caller', metrics: { opportunity: 89, environment: 91, coaching: 97, line: 78, stability: 94, upside: 84 } },
];

const initialPicks: Pick[] = [
  { playerId: 'wr-1', overall: 1, teamIndex: 0 },
  { playerId: 'rb-1', overall: 2, teamIndex: 1 },
  { playerId: 'wr-2', overall: 3, teamIndex: 2 },
  { playerId: 'rb-2', overall: 4, teamIndex: 3 },
];

function ownerForPick(overall: number, teamCount: number) {
  const round = Math.floor((overall - 1) / teamCount) + 1;
  const offset = (overall - 1) % teamCount;
  return round % 2 ? offset : teamCount - 1 - offset;
}

function scorePlayer(player: Player, weights: Weights, picks: Pick[]) {
  const context = FACTORS[player.position].reduce((total, factor) => {
    return total + ((player.metrics[factor.key] - 50) / 50) * (weights[player.position][factor.key] / 100) * 2.2;
  }, 0);
  const run = picks.slice(-8).filter((pick) => players.find((item) => item.id === pick.playerId)?.position === player.position).length;
  return player.baseScore + context + run * 0.22;
}

const positionClass: Record<Position, string> = { QB: 'position-qb', RB: 'position-rb', WR: 'position-wr', TE: 'position-te' };

type WeightControlsProps = {
  activePosition: Position;
  currentOwnerIsMine: boolean;
  myPlayerCount: number;
  recentRun: string;
  setActivePosition: (position: Position) => void;
  setWeights: Dispatch<SetStateAction<Weights>>;
  weights: Weights;
};

function WeightControls({
  activePosition,
  currentOwnerIsMine,
  myPlayerCount,
  recentRun,
  setActivePosition,
  setWeights,
  weights,
}: WeightControlsProps) {
  const updateWeight = (metric: Metric, value: number) => setWeights((current) => ({
    ...current,
    [activePosition]: { ...current[activePosition], [metric]: value },
  }));

  return <>
    <div className="position-tabs">
      {(['QB', 'RB', 'WR', 'TE'] as const).map((position) => <button type="button" key={position} onClick={() => setActivePosition(position)} className={activePosition === position ? `is-active ${positionClass[position]}` : ''}>{position}</button>)}
    </div>
    <div className="weight-intro"><strong>{activePosition} priorities</strong><span>1.0× is neutral. Rankings update immediately.</span></div>
    <div className="factor-list">
      {FACTORS[activePosition].map((factor) => {
        const value = weights[activePosition][factor.key];
        return <div className="factor-control" key={factor.key}>
          <div className="factor-label"><div><strong>{factor.label}</strong><small>{factor.hint}</small></div><output>{(value / 100).toFixed(2)}×</output></div>
          <Slider min={0} max={200} step={5} value={[value]} onValueChange={(next) => updateWeight(factor.key, typeof next === 'number' ? next : next[0])} aria-label={`${activePosition} ${factor.label} weight`} />
        </div>;
      })}
    </div>
    <Button variant="ghost" size="sm" className="reset-weights" onClick={() => setWeights((current) => ({ ...current, [activePosition]: DEFAULT_WEIGHTS[activePosition] }))}><RotateCcw /> Reset {activePosition}</Button>
    <div className="live-signals">
      <div className="signal-heading"><Zap /><strong>Live rank signals</strong></div>
      <div><span>Roster need</span><strong>{myPlayerCount ? 'Rebalancing' : 'Open starters'}</strong></div>
      <div><span>Recent run</span><strong>{recentRun}</strong></div>
      <div><span>Next turn</span><strong>{currentOwnerIsMine ? 'Pick now' : 'Tracking'}</strong></div>
    </div>
  </>;
}

export default function Home() {
  const [picks, setPicks] = useState<Pick[]>(initialPicks);
  const [weights, setWeights] = useState<Weights>(DEFAULT_WEIGHTS);
  const [activePosition, setActivePosition] = useState<Position>('WR');
  const [filter, setFilter] = useState<'ALL' | Position>('ALL');
  const [query, setQuery] = useState('');
  const [teamCount, setTeamCount] = useState(10);
  const [draftSlot, setDraftSlot] = useState(5);
  const [benchCount, setBenchCount] = useState(DEFAULT_BENCH_COUNT);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [pendingTeamCount, setPendingTeamCount] = useState(10);
  const [pendingDraftSlot, setPendingDraftSlot] = useState(5);
  const [pendingBenchCount, setPendingBenchCount] = useState(DEFAULT_BENCH_COUNT);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const saved = window.localStorage.getItem(STORAGE_KEY);
        if (saved) {
          const parsed = JSON.parse(saved) as { picks?: Pick[]; weights?: Weights; teamCount?: number; draftSlot?: number; benchCount?: number };
          if (Array.isArray(parsed.picks)) setPicks(parsed.picks);
          if (parsed.weights) setWeights(parsed.weights);
          const savedTeamCount = [8, 10, 12].includes(parsed.teamCount ?? 0) ? parsed.teamCount! : 10;
          setTeamCount(savedTeamCount);
          if (typeof parsed.draftSlot === 'number' && parsed.draftSlot >= 1 && parsed.draftSlot <= savedTeamCount) setDraftSlot(parsed.draftSlot);
          if (typeof parsed.benchCount === 'number' && Number.isInteger(parsed.benchCount) && parsed.benchCount >= 0 && parsed.benchCount <= 12) setBenchCount(parsed.benchCount);
        }
      } catch {
        try {
          window.localStorage.removeItem(STORAGE_KEY);
        } catch {
          // Storage can be unavailable in privacy modes.
        }
      } finally {
        setHydrated(true);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ picks, weights, teamCount, draftSlot, benchCount }));
    } catch {
      // The draft remains usable when browser storage is unavailable.
    }
  }, [benchCount, draftSlot, hydrated, picks, teamCount, weights]);

  const myTeamIndex = draftSlot - 1;
  const teamNames = useMemo(() => Array.from({ length: teamCount }, (_, index) => index === myTeamIndex ? 'My Team' : TEAM_LABELS[index]), [myTeamIndex, teamCount]);
  const draftedIds = useMemo(() => new Set(picks.map((pick) => pick.playerId)), [picks]);
  const currentPick = picks.length + 1;
  const currentOwner = ownerForPick(currentPick, teamCount);
  const currentRound = Math.floor((currentPick - 1) / teamCount) + 1;

  const available = useMemo(() => players
    .filter((player) => !draftedIds.has(player.id))
    .filter((player) => filter === 'ALL' || player.position === filter)
    .filter((player) => `${player.name} ${player.team} ${player.position}`.toLowerCase().includes(query.trim().toLowerCase()))
    .map((player) => ({ player, score: scorePlayer(player, weights, picks) }))
    .sort((a, b) => b.score - a.score), [draftedIds, filter, picks, query, weights]);

  const myPlayers = useMemo(() => picks
    .filter((pick) => pick.teamIndex === myTeamIndex)
    .map((pick) => players.find((player) => player.id === pick.playerId))
    .filter((player): player is Player => Boolean(player)), [myTeamIndex, picks]);

  const recentRun = useMemo(() => {
    const counts: Partial<Record<Position, number>> = {};
    picks.slice(-4).forEach((pick) => {
      const position = players.find((player) => player.id === pick.playerId)?.position;
      if (position) counts[position] = (counts[position] ?? 0) + 1;
    });
    const leader = (Object.entries(counts) as Array<[Position, number]>).sort((a, b) => b[1] - a[1])[0];
    return leader ? `${leader[0]} · ${leader[1]} of last ${Math.min(4, picks.length)}` : 'No picks yet';
  }, [picks]);

  const rosterSlots = useMemo(() => {
    const used = new Set<string>();
    const slots: RosterSlot[] = [...STARTER_SLOTS, ...Array.from({ length: benchCount }, () => 'BN' as const)];
    return slots.map((slot) => {
      const player = myPlayers.find((candidate) => {
        if (used.has(candidate.id)) return false;
        if (slot === 'BN') return true;
        if (slot === 'FLEX') return ['RB', 'WR', 'TE'].includes(candidate.position);
        return slot === candidate.position;
      });
      if (player) used.add(player.id);
      return { slot, player };
    });
  }, [benchCount, myPlayers]);

  const draft = (playerId: string) => setPicks((current) => [
    ...current,
    { playerId, overall: current.length + 1, teamIndex: ownerForPick(current.length + 1, teamCount) },
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

  const loadDemo = () => {
    setTeamCount(10);
    setDraftSlot(5);
    setBenchCount(DEFAULT_BENCH_COUNT);
    setPicks(initialPicks);
    setSettingsOpen(false);
  };

  const currentOwnerIsMine = currentOwner === myTeamIndex;
  const totalRosterSpots = STARTER_SLOTS.length + benchCount;

  return (
    <main className="draft-shell">
      <header className="app-header">
        <div className="brand-lockup">
          <div className="brand-mark"><DraftingCompass aria-hidden="true" /></div>
          <div><p className="eyebrow">Fantasy Football 2026</p><h1>Draft Room</h1></div>
        </div>
        <div className="draft-status" aria-label="Current draft status">
          <div><span>Round</span><strong>{currentRound}</strong></div>
          <div><span>Overall</span><strong>{currentPick}</strong></div>
          <div className={currentOwnerIsMine ? 'on-clock is-mine' : 'on-clock'}>
            <span>On the clock</span><strong>{teamNames[currentOwner]}</strong>
          </div>
        </div>
        <div className="header-actions">
          <Dialog>
            <DialogTrigger render={<Button variant="outline" size="sm" className="data-badge" />}><Database /> <span>Demo snapshot</span></DialogTrigger>
            <DialogContent className="source-dialog sm:max-w-xl">
              <DialogHeader>
                <DialogTitle>Data source plan</DialogTitle>
                <DialogDescription>This preview uses synthetic players so the draft workflow can be tested safely. The production board will join three source adapters by player ID.</DialogDescription>
              </DialogHeader>
              <div className="source-list">
                <div><Badge variant="secondary">League</Badge><strong>Yahoo Fantasy Sports API</strong><span>Settings, teams, player eligibility, draft results and Yahoo market data. OAuth 2.0 and approved app access are required.</span></div>
                <div><Badge variant="secondary">Context</Badge><strong>nflverse</strong><span>Player and team stats, play-by-play, depth, injuries and cross-platform IDs for volume, line and QB/OC profiles.</span></div>
                <div><Badge variant="secondary">Baseline</Badge><strong>Licensed projections or your CSV</strong><span>FantasyPros API when licensed, or a user-supplied export, for projections, expert consensus and ADP.</span></div>
              </div>
              <p className="source-warning">Manual pick entry remains first-class, so draft tracking works even if Yahoo sync is delayed or unavailable.</p>
              <DialogFooter showCloseButton>
                <a className="source-link" href="https://github.com/demansou/fantasy-football-26/blob/main/docs/DATA_SOURCES.md" target="_blank" rel="noreferrer">Read the adapter plan</a>
              </DialogFooter>
            </DialogContent>
          </Dialog>
          <Dialog open={settingsOpen} onOpenChange={openSettings}>
            <DialogTrigger render={<Button variant="outline" size="sm" className="settings-trigger" />}><Settings2 /> <span>League</span></DialogTrigger>
            <DialogContent className="league-dialog sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>League setup</DialogTitle>
                <DialogDescription>Set the snake draft shape before entering live picks. Applying a new setup starts a clean board.</DialogDescription>
              </DialogHeader>
              <div className="settings-grid">
                <div className="settings-field">
                  <Label htmlFor="team-count">Teams</Label>
                  <NativeSelect id="team-count" value={pendingTeamCount} onChange={(event) => {
                    const count = Number(event.target.value);
                    setPendingTeamCount(count);
                    setPendingDraftSlot((slot) => Math.min(slot, count));
                  }}>
                    {[8, 10, 12].map((count) => <NativeSelectOption key={count} value={count}>{count} teams</NativeSelectOption>)}
                  </NativeSelect>
                </div>
                <div className="settings-field">
                  <Label htmlFor="draft-slot">Your draft slot</Label>
                  <NativeSelect id="draft-slot" value={pendingDraftSlot} onChange={(event) => setPendingDraftSlot(Number(event.target.value))}>
                    {Array.from({ length: pendingTeamCount }, (_, index) => <NativeSelectOption key={index + 1} value={index + 1}>Pick {index + 1}</NativeSelectOption>)}
                  </NativeSelect>
                </div>
                <div className="settings-field">
                  <Label htmlFor="bench-count">Bench spots</Label>
                  <NativeSelect id="bench-count" value={pendingBenchCount} onChange={(event) => setPendingBenchCount(Number(event.target.value))}>
                    {Array.from({ length: 13 }, (_, count) => <NativeSelectOption key={count} value={count}>{count} {count === 1 ? 'spot' : 'spots'}</NativeSelectOption>)}
                  </NativeSelect>
                </div>
              </div>
              <div className="persistence-note"><Check /> Picks, all league settings and positional weights save in this browser.</div>
              <DialogFooter>
                <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
                <Button variant="secondary" onClick={loadDemo}><RotateCcw /> Load demo</Button>
                <Button onClick={applyLeagueSettings}>Apply &amp; start fresh</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
          <Dialog>
            <DialogTrigger render={<Button variant="outline" size="sm" className="mobile-weight-trigger" />}><SlidersHorizontal /> <span>Weights</span></DialogTrigger>
            <DialogContent className="weight-dialog sm:max-w-md">
              <DialogHeader><DialogTitle>Position weights</DialogTitle><DialogDescription>Adjust the signals that matter most at each position. Rankings react immediately.</DialogDescription></DialogHeader>
              <div className="weight-dialog-scroll">
                <WeightControls activePosition={activePosition} currentOwnerIsMine={currentOwnerIsMine} myPlayerCount={myPlayers.length} recentRun={recentRun} setActivePosition={setActivePosition} setWeights={setWeights} weights={weights} />
              </div>
            </DialogContent>
          </Dialog>
          <Button variant="outline" size="sm" disabled={!picks.length} onClick={() => setPicks((current) => current.slice(0, -1))}>
            <Undo2 /> Undo
          </Button>
        </div>
      </header>

      <section className="pick-ticker" aria-label="Recent draft picks">
        <span className="ticker-label">Last picks</span>
        {picks.slice(-5).map((pick) => {
          const player = players.find((item) => item.id === pick.playerId);
          return player ? <div className="ticker-pick" key={pick.overall}><span className={`position-dot ${positionClass[player.position]}`} /><strong>{pick.overall}</strong><span>{player.name}</span><small>{player.position}</small></div> : null;
        })}
        <div className="ticker-next"><Zap /> Pick {currentPick} ready</div>
      </section>

      <div className="workspace-grid">
        <aside className="roster-panel panel-surface">
          <div className="panel-heading"><div><p className="eyebrow">Roster construction</p><h2>My Team</h2></div><span className="panel-count">{myPlayers.length}/{totalRosterSpots}</span></div>
          <div className="roster-summary">
            <div><span>Projected</span><strong>{myPlayers.reduce((sum, player) => sum + player.projection, 0)}</strong></div>
            <div><span>Draft slot</span><strong>{draftSlot}</strong></div>
            <div><span>Bench</span><strong>{benchCount}</strong></div>
          </div>
          <ScrollArea className="roster-scroll">
            <div className="roster-slots">
              {rosterSlots.map(({ slot, player: rosterPlayer }, index) => {
                return <div className={rosterPlayer ? 'roster-slot is-filled' : 'roster-slot'} key={`${slot}-${index}`}>
                  <span className="slot-label">{slot}</span>
                  {rosterPlayer ? <><div><strong>{rosterPlayer.name}</strong><small>{rosterPlayer.team} · Bye {rosterPlayer.bye}</small></div><Check className="slot-check" /></> : <span className="empty-slot">{slot === 'BN' ? 'Open bench spot' : 'Open roster slot'}</span>}
                </div>;
              })}
            </div>
          </ScrollArea>
          <div className="roster-footer"><span>{teamCount}-team Yahoo PPR</span><span>{benchCount} bench · Snake</span></div>
        </aside>

        <section className="player-board panel-surface">
          <div className="board-toolbar">
            <div><p className="eyebrow">Live optimized rank</p><h2>Available players</h2></div>
            <div className="search-wrap"><Search /><Input aria-label="Search available players" placeholder="Search player or team" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
          </div>
          <div className="position-filters">
            {(['ALL', 'QB', 'RB', 'WR', 'TE'] as const).map((position) => <button key={position} type="button" className={filter === position ? 'filter-chip is-active' : 'filter-chip'} onClick={() => setFilter(position)}>{position}</button>)}
            <span className="rank-note">Ranks react to picks + preferences</span>
          </div>
          <div className="player-table-header"><span>Rank / player</span><span>Proj.</span><span>ADP</span><span>Model</span><span /></div>
          <ScrollArea className="player-scroll">
            <div className="player-list">
              {available.map(({ player, score }, index) => <article className="player-row" key={player.id}>
                <div className="player-identity"><span className="rank-number">{index + 1}</span><span className={`position-pill ${positionClass[player.position]}`}>{player.position}</span><div><strong>{player.name}</strong><small>{player.team} · Bye {player.bye} · Tier {player.tier}</small></div></div>
                <div className="stat-cell"><strong>{player.projection}</strong><small>pts</small></div>
                <div className="stat-cell"><strong>{player.adp.toFixed(1)}</strong><small>market</small></div>
                <div className="model-cell"><strong>{score.toFixed(1)}</strong><span>{player.context}</span></div>
                <Button size="sm" variant={currentOwnerIsMine ? 'default' : 'outline'} onClick={() => draft(player.id)}>{currentOwnerIsMine ? 'Draft' : 'Mark gone'}</Button>
              </article>)}
            </div>
          </ScrollArea>
        </section>

        <aside className="weights-panel panel-surface">
          <div className="panel-heading weights-heading"><div><p className="eyebrow">Your draft model</p><h2>Position weights</h2></div><SlidersHorizontal /></div>
          <WeightControls activePosition={activePosition} currentOwnerIsMine={currentOwnerIsMine} myPlayerCount={myPlayers.length} recentRun={recentRun} setActivePosition={setActivePosition} setWeights={setWeights} weights={weights} />
        </aside>
      </div>
    </main>
  );
}
