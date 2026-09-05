'use client';

import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  NativeSelect,
  NativeSelectOption,
} from '@/components/ui/native-select';
import { PLAYERS } from '@/data/players';
import {
  changeOwner,
  parseSeason,
  parseStats,
  undoSeason,
  usageSummary,
  type Assignment,
  type SeasonState,
  type StatsSnapshot,
  type WeeklyUsage,
} from '@/lib/season';

const KEY = 'fantasy-football-26:season:v1';
const STATS_KEY = 'fantasy-football-26:season-stats:v1';
type Props = {
  view: 'team' | 'research';
  picks: SeasonState['draft'];
  teams: string[];
  myTeam: number;
  capacity: number;
};
const date = (n: number) => new Date(n).toLocaleString();
function download(s: SeasonState) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(s, null, 2)], { type: 'application/json' }),
  );
  const a = document.createElement('a');
  a.href = url;
  a.download = 'fantasy-2026-season-backup.json';
  a.click();
  URL.revokeObjectURL(url);
}

export function SeasonRoom({ view, picks, teams, myTeam, capacity }: Props) {
  const [season, setSeason] = useState<SeasonState | null>(null);
  const [ready, setReady] = useState(false);
  const [stats, setStats] = useState<StatsSnapshot | null>(null);
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState('');
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState('');
  const [team, setTeam] = useState(myTeam);
  const [pool, setPool] = useState('roster');
  const [position, setPosition] = useState('ALL');
  const [research, setResearch] = useState('waivers');
  const file = useRef<HTMLInputElement>(null);
  useEffect(() => {
    // Hydrate browser-only storage after SSR; never write during hydration.
    const hydrate = () => {
      try {
        const raw = localStorage.getItem(KEY);
        if (raw) {
          const saved = parseSeason(raw);
          setSeason(saved);
          setTeam(saved.myTeam);
        }
      } catch {
        setMessage(
          'Saved season could not be loaded. Import a backup before starting a new season.',
        );
      }
      try {
        const raw = localStorage.getItem(STATS_KEY);
        if (raw) {
          setStats(parseStats(JSON.parse(raw)));
        }
      } catch {
        /* A failed stats cache never prevents roster recovery. */
      }
      setReady(true);
    };
    const timer = window.setTimeout(hydrate, 0);
    return () => window.clearTimeout(timer);
  }, []);
  // Save synchronously with the transaction, not on a deferred render effect.
  function save(next: SeasonState) {
    const enriched = {
      ...next,
      playerInfo: {
        ...next.playerInfo,
        ...Object.fromEntries(
          catalog
            .filter(
              (p) =>
                next.owners[p.id] || next.history.some((h) => h.before[p.id]),
            )
            .map((p) => [
              p.id,
              {
                name: p.name,
                position: p.position,
                team: p.team,
                gsisId: p.gsisId,
              },
            ]),
        ),
      },
    };
    try {
      localStorage.setItem(KEY, JSON.stringify(enriched));
      setSaving('Saved on this device');
    } catch {
      setSaving('Save failed — export a backup now before leaving this page.');
    }
    setSeason(enriched);
  }
  async function refresh() {
    setBusy(true);
    setMessage('');
    try {
      const response = await fetch('/api/season-stats', { cache: 'no-store' });
      const body = await response.json();
      if (!response.ok)
        throw new Error(
          (body as { error?: string }).error || 'Stats unavailable',
        );
      const parsed = parseStats(body);
      setStats(parsed);
      try {
        localStorage.setItem(STATS_KEY, JSON.stringify(parsed));
      } catch {
        setMessage('Stats loaded, but could not be cached on this device.');
      }
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : 'Refresh failed; previous data retained.',
      );
    } finally {
      setBusy(false);
    }
  }
  const knownIds = new Set<string | null>(PLAYERS.map((p) => p.gsisId));
  const extras = Array.from(
    new Map(
      (stats?.rows ?? [])
        .filter((r) => !knownIds.has(r.id))
        .map((r) => [r.id, r]),
    ).values(),
  ).map((r) => ({
    id: `nfl-${r.id}`,
    gsisId: r.id,
    name: r.name,
    position: r.position,
    team: r.team,
    metrics: { opportunity: 0 },
  }));
  const currentCatalog = [...PLAYERS, ...extras];
  const recovered = Object.entries(season?.playerInfo ?? {})
    .filter(([id]) => !currentCatalog.some((p) => p.id === id))
    .map(([id, p]) => ({ ...p, id, metrics: { opportunity: 0 } }));
  const catalog = [...currentCatalog, ...recovered];
  const lookup = new Map(catalog.map((p) => [p.id, p]));
  const roster = catalog.filter((p) => season?.owners[p.id]?.team === team);
  const selectedTeam = season?.teams[team] ?? teams[myTeam];
  function move(
    id: string,
    destination: string,
    slot: Assignment['slot'] = 'Bench',
  ) {
    if (!season) return;
    const assignment =
      destination === 'free' ? null : { team: Number(destination), slot };
    const name = lookup.get(id)?.name ?? id;
    save(
      changeOwner(
        season,
        id,
        assignment,
        `${name} → ${assignment ? `${season.teams[assignment.team]} (${slot})` : 'Free agents'}`,
      ),
    );
  }
  const grouped = new Map<string, WeeklyUsage[]>();
  for (const row of stats?.rows ?? []) {
    const rows = grouped.get(row.id) ?? [];
    rows.push(row);
    grouped.set(row.id, rows);
  }
  const summaries = new Map(
    [...grouped].map(([id, rows]) => [
      id,
      usageSummary(rows, stats?.latestWeek ?? 0),
    ]),
  );
  const usage = (id: string | null) =>
    summaries.get(id ?? '') ?? usageSummary([], 0);
  const myRoster = catalog.filter(
    (p) => season?.owners[p.id]?.team === season?.myTeam,
  );
  const scoreFor = (p: (typeof catalog)[number]) => {
    const u = usage(p.gsisId);
    const peers = catalog
      .filter((other) => other.position === p.position)
      .map((other) => usage(other.gsisId))
      .filter((other) => other.games > 0);
    const percentile = u.games
      ? (100 * peers.filter((other) => other.volume <= u.volume).length) /
        Math.max(1, peers.length)
      : 0;
    const weight = Math.min(0.75, u.games * 0.25);
    return p.metrics.opportunity * (1 - weight) + percentile * weight;
  };
  const candidates = catalog
    .filter((p) => {
      if (!season || !['QB', 'RB', 'WR', 'TE'].includes(p.position))
        return false;
      const owner = season.owners[p.id];
      return (
        (research === 'waivers'
          ? !owner
          : owner && owner.team !== season.myTeam) &&
        (position === 'ALL' || position === p.position)
      );
    })
    .map((p) => {
      const u = usage(p.gsisId);
      const peers = myRoster.filter((other) => other.position === p.position);
      const score = scoreFor(p);
      const fit = peers.length
        ? score - Math.min(...peers.map(scoreFor))
        : score;
      return { p, u, score, fit };
    })
    .sort((a, b) => b.fit - a.fit || b.score - a.score);

  return (
    <section className="season-room">
      <div className="season-heading">
        <div>
          <p className="eyebrow">2026 season workspace</p>
          <h1>{view === 'team' ? 'My Team' : 'Research'}</h1>
        </div>
        <div className="season-actions">
          <Button onClick={refresh} disabled={busy}>
            {busy ? 'Refreshing…' : 'Refresh NFL stats'}
          </Button>
          <Button
            variant="outline"
            disabled={!season}
            onClick={() => season && download(season)}
          >
            Export season
          </Button>
          <Button variant="outline" onClick={() => file.current?.click()}>
            Import season
          </Button>
        </div>
      </div>
      <input
        ref={file}
        type="file"
        accept=".json,application/json"
        hidden
        onChange={async (e) => {
          const input = e.currentTarget;
          const selected = input.files?.[0];
          if (!selected) return;
          try {
            if (selected.size > 5_000_000)
              throw new Error('Backup is too large.');
            const imported = parseSeason(await selected.text());
            if (
              season &&
              !window.confirm(
                'Replace the current season roster? Export a backup first if you need to keep it. Draft history will not change.',
              )
            )
              return;
            save(imported);
            setTeam(imported.myTeam);
            setMessage('Season restored. Draft room unchanged.');
          } catch (error) {
            setMessage(
              error instanceof Error ? error.message : 'Invalid backup',
            );
          } finally {
            input.value = '';
          }
        }}
      />
      <div className="season-status">
        <span>
          Roster updated: {season ? date(season.updatedAt) : 'Not started'}
        </span>
        <span>Stats refreshed: {stats ? date(stats.fetchedAt) : 'Never'}</span>
        <span>
          {stats
            ? `2026 data through week ${stats.latestWeek} (may be partial)`
            : 'No 2026 usage loaded'}
        </span>
      </div>
      <p className="season-note">
        {saving ||
          'Device-local storage · Export a backup for safekeeping or another device.'}{' '}
        Ownership is manually maintained, not synced with Yahoo.
      </p>
      {message && <output className="season-notice">{message}</output>}
      {!ready ? (
        <p>Loading saved season…</p>
      ) : !season ? (
        <div className="panel-surface season-empty">
          <h2>Carry your draft into the season</h2>
          <p>
            Copy {picks.length} recorded picks and {teams.length} team names
            into an independent roster. Later draft edits will not change the
            season roster.
          </p>
          <p>
            You can start with a partial draft and finish assigning players
            here.
          </p>
          <Button
            disabled={!picks.length || capacity < 1}
            onClick={() => {
              const now = Date.now();
              save({
                version: 1,
                season: 2026,
                startedAt: now,
                updatedAt: now,
                teams: [...teams],
                myTeam,
                capacity,
                draft: picks.map((p) => ({ ...p })),
                owners: Object.fromEntries(
                  picks.map((p) => [
                    p.playerId,
                    { team: p.teamIndex, slot: 'Bench' },
                  ]),
                ),
                history: [],
              });
              setTeam(myTeam);
            }}
          >
            Start season from saved draft
          </Button>
        </div>
      ) : view === 'team' ? (
        <>
          <div className="season-toolbar">
            <label>
              Team
              <NativeSelect
                value={team}
                onChange={(e) => setTeam(+e.target.value)}
              >
                {season.teams.map((t, i) => (
                  <NativeSelectOption key={i} value={i}>
                    {t}
                    {i === season.myTeam ? ' (mine)' : ''}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </label>
            <label htmlFor="season-pool">
              Show
              <NativeSelect
                id="season-pool"
                value={pool}
                onChange={(e) => setPool(e.target.value)}
              >
                <NativeSelectOption value="roster">
                  Selected roster
                </NativeSelectOption>
                <NativeSelectOption value="free">
                  Free agents
                </NativeSelectOption>
                <NativeSelectOption value="all">
                  All players / trade transfers
                </NativeSelectOption>
              </NativeSelect>
            </label>
            <Input
              aria-label="Search players"
              placeholder="Search player or NFL team"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <Button
              variant="outline"
              disabled={!season.history.length}
              onClick={() => save(undoSeason(season))}
            >
              Undo last change
            </Button>
          </div>
          <h2>
            {selectedTeam} ·{' '}
            {roster.filter((p) => season.owners[p.id].slot !== 'IR').length}/
            {season.capacity} active + bench ·{' '}
            {roster.filter((p) => season.owners[p.id].slot === 'IR').length} IR
          </h2>
          <p className="season-note">
            Starter/bench/IR are planning labels; verify eligibility and lineup
            limits in Yahoo. Trades are recorded as individual player transfers.
          </p>
          {roster.filter((p) => season.owners[p.id].slot !== 'IR').length >
            season.capacity && (
            <p role="alert">
              Roster exceeds your saved limit. Record the corresponding drop or
              transfer.
            </p>
          )}
          <div className="season-list">
            {catalog
              .filter(
                (p) =>
                  (pool === 'all' ||
                    (pool === 'free'
                      ? !season.owners[p.id]
                      : season.owners[p.id]?.team === team)) &&
                  `${p.name} ${p.team}`
                    .toLowerCase()
                    .includes(query.toLowerCase()),
              )
              .map((p) => (
                <article key={p.id} className="season-player panel-surface">
                  <div>
                    <strong>{p.name}</strong>
                    <p>
                      {p.position} · {p.team} ·{' '}
                      {season.owners[p.id]
                        ? season.teams[season.owners[p.id].team]
                        : 'Free agent (manual records)'}
                    </p>
                  </div>
                  <label>
                    Owner
                    <NativeSelect
                      aria-label={`Owner for ${p.name}`}
                      value={season.owners[p.id]?.team ?? 'free'}
                      onChange={(e) => move(p.id, e.target.value)}
                    >
                      <NativeSelectOption value="free">
                        Free agent
                      </NativeSelectOption>
                      {season.teams.map((t, i) => (
                        <NativeSelectOption key={i} value={i}>
                          {t}
                        </NativeSelectOption>
                      ))}
                    </NativeSelect>
                  </label>
                  {season.owners[p.id] && (
                    <label>
                      Roster status
                      <NativeSelect
                        aria-label={`Roster status for ${p.name}`}
                        value={season.owners[p.id].slot}
                        onChange={(e) =>
                          move(
                            p.id,
                            String(season.owners[p.id].team),
                            e.target.value as Assignment['slot'],
                          )
                        }
                      >
                        {['Starter', 'Bench', 'IR'].map((s) => (
                          <NativeSelectOption key={s} value={s}>
                            {s}
                          </NativeSelectOption>
                        ))}
                      </NativeSelect>
                    </label>
                  )}
                </article>
              ))}
          </div>
          {Object.keys(season.owners).some((id) => !lookup.has(id)) && (
            <p className="season-notice">
              Some saved players are outside the loaded catalog. Refresh stats
              to load additional players; their ownership is preserved.
            </p>
          )}
          <details className="season-history">
            <summary>Transaction history ({season.history.length})</summary>
            {season.history
              .slice()
              .reverse()
              .map((h, i) => (
                <p key={i}>
                  {date(h.at)} · {h.label}
                </p>
              ))}
            {!season.history.length && <p>No season changes yet.</p>}
          </details>
        </>
      ) : (
        <>
          <div className="season-toolbar">
            <label htmlFor="season-research">
              Find
              <NativeSelect
                id="season-research"
                value={research}
                onChange={(e) => setResearch(e.target.value)}
              >
                <NativeSelectOption value="waivers">
                  Waiver watchlist
                </NativeSelectOption>
                <NativeSelectOption value="trades">
                  Trade watchlist
                </NativeSelectOption>
              </NativeSelect>
            </label>
            <label>
              Position
              <NativeSelect
                value={position}
                onChange={(e) => setPosition(e.target.value)}
              >
                {['ALL', 'QB', 'RB', 'WR', 'TE'].map((p) => (
                  <NativeSelectOption value={p} key={p}>
                    {p}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </label>
          </div>
          <p className="season-note">
            {stats
              ? 'Usage screen: recent three-week opportunity, blended with the preseason opportunity index. Games without a stats row are excluded; bye/injury gaps can inflate per-game averages.'
              : 'Preseason watchlist only. Refresh after games to incorporate actual usage.'}{' '}
            Compare within a position. These are research leads, not calibrated
            trade values or automatic drop recommendations.
          </p>
          <p className="season-note">
            Catalog: {catalog.length} players; expands when new players appear
            in NFL usage data. Confirm availability, injuries and transactions
            in Yahoo before acting.
          </p>
          <div className="season-list">
            {candidates.slice(0, 30).map(({ p, u, fit }) => {
              const peers = myRoster.filter(
                (other) => other.position === p.position,
              );
              return (
                <article className="season-player panel-surface" key={p.id}>
                  <div>
                    <strong>{p.name}</strong>
                    <p>
                      {p.position} · {p.team} ·{' '}
                      {season.owners[p.id]
                        ? season.teams[season.owners[p.id].team]
                        : 'Unowned in manual records'}
                    </p>
                    <p>
                      {u.games
                        ? `${u.volume.toFixed(1)} ${p.position === 'QB' ? 'attempts + carries' : p.position === 'RB' ? 'carries + targets' : 'targets'}/recorded game · ${u.games} recent games · ${u.confidence} evidence confidence`
                        : 'No recent usage evidence · Low confidence'}
                    </p>
                    {u.trend !== null && (
                      <p>
                        Usage change: {u.trend >= 0 ? '+' : ''}
                        {u.trend.toFixed(1)} per recorded game versus preceding
                        three-week window.
                      </p>
                    )}
                    <p>
                      Your {p.position} options:{' '}
                      {peers.length
                        ? peers.map((other) => other.name).join(', ')
                        : 'None — positional gap to investigate'}
                      .
                    </p>
                    <p>
                      {!peers.length
                        ? 'Prioritized for an empty position.'
                        : fit > 0
                          ? 'Usage/prior screen ranks above your lowest-rated same-position option; investigate role and availability before replacing anyone.'
                          : 'Depth watch only: this screen does not identify an upgrade over your current same-position options.'}
                    </p>
                  </div>
                </article>
              );
            })}
          </div>
          {!candidates.length && <p>No candidates match this filter.</p>}
          <p className="season-note">
            Source:{' '}
            <a
              href="https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html"
              target="_blank"
              rel="noreferrer"
            >
              nflverse weekly player stats and update schedule
            </a>
            .{' '}
            {stats?.sourceUpdated
              ? `Source modified: ${stats.sourceUpdated}.`
              : ''}{' '}
            Snap counts, red-zone usage and automated injury adjustments are not
            included in this first season screen.
          </p>
        </>
      )}
    </section>
  );
}
