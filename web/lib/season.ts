export type Assignment = { team: number; slot: 'Starter' | 'Bench' | 'IR' };
export type SeasonState = {
  version: 1;
  season: 2026;
  startedAt: number;
  updatedAt: number;
  teams: string[];
  myTeam: number;
  capacity: number;
  draft: { playerId: string; overall: number; teamIndex: number }[];
  owners: Record<string, Assignment>;
  history: { at: number; label: string; before: Record<string, Assignment> }[];
  playerInfo?: Record<
    string,
    { name: string; position: string; team: string; gsisId: string | null }
  >;
};
export type WeeklyUsage = {
  id: string;
  name: string;
  position: string;
  team: string;
  week: number;
  targets: number;
  carries: number;
  attempts: number;
  targetShare: number | null;
};
export type StatsSnapshot = {
  season: number;
  fetchedAt: number;
  sourceUpdated: string | null;
  latestWeek: number;
  rows: WeeklyUsage[];
};

export function parseSeason(raw: string): SeasonState {
  const s = JSON.parse(raw);
  const validTime = (n: unknown) =>
    typeof n === 'number' && Number.isFinite(n) && n > 0;
  if (
    s?.version !== 1 ||
    s.season !== 2026 ||
    !Array.isArray(s.teams) ||
    s.teams.length < 2 ||
    s.teams.length > 20 ||
    !s.teams.every(
      (t: unknown) => typeof t === 'string' && t.length > 0 && t.length <= 100,
    ) ||
    !Number.isInteger(s.myTeam) ||
    s.myTeam < 0 ||
    s.myTeam >= s.teams.length ||
    !Number.isInteger(s.capacity) ||
    s.capacity < 1 ||
    s.capacity > 50 ||
    !validTime(s.startedAt) ||
    !validTime(s.updatedAt) ||
    !Array.isArray(s.draft) ||
    !Array.isArray(s.history) ||
    s.history.length > 100
  )
    throw new Error(
      'Invalid season backup. Your current roster has not changed.',
    );
  const validOwners = (owners: unknown) =>
    owners &&
    typeof owners === 'object' &&
    !Array.isArray(owners) &&
    Object.entries(owners).length <= 3000 &&
    Object.entries(owners).every(
      ([id, a]: [string, Assignment]) =>
        /^[a-zA-Z0-9_-]{1,80}$/.test(id) &&
        a &&
        Number.isInteger(a.team) &&
        a.team >= 0 &&
        a.team < s.teams.length &&
        ['Starter', 'Bench', 'IR'].includes(a.slot),
    );
  if (
    !validOwners(s.owners) ||
    !s.history.every(
      (h: SeasonState['history'][number]) =>
        h &&
        validTime(h.at) &&
        typeof h.label === 'string' &&
        h.label.length <= 300 &&
        validOwners(h.before),
    ) ||
    !s.draft.every(
      (p: SeasonState['draft'][number]) =>
        p &&
        typeof p.playerId === 'string' &&
        Number.isInteger(p.overall) &&
        p.overall > 0 &&
        Number.isInteger(p.teamIndex) &&
        p.teamIndex >= 0 &&
        p.teamIndex < s.teams.length,
    )
  )
    throw new Error('Invalid roster assignments in backup.');
  if (
    s.playerInfo &&
    (typeof s.playerInfo !== 'object' ||
      Array.isArray(s.playerInfo) ||
      !Object.values(s.playerInfo).every((value) => {
        const p = value as NonNullable<SeasonState['playerInfo']>[string];
        return (
          p &&
          typeof p.name === 'string' &&
          p.name.length <= 100 &&
          typeof p.team === 'string' &&
          p.team.length <= 50 &&
          ['QB', 'RB', 'WR', 'TE', 'K', 'DST'].includes(p.position) &&
          (p.gsisId === null || typeof p.gsisId === 'string')
        );
      }))
  )
    throw new Error('Invalid player metadata.');
  return s;
}

export function changeOwner(
  s: SeasonState,
  id: string,
  assignment: Assignment | null,
  label: string,
): SeasonState {
  const owners = { ...s.owners };
  if (assignment) owners[id] = assignment;
  else delete owners[id];
  const now = Date.now();
  return {
    ...s,
    owners,
    updatedAt: now,
    history: [...s.history.slice(-99), { at: now, label, before: s.owners }],
  };
}
export function undoSeason(s: SeasonState): SeasonState {
  const last = s.history.at(-1);
  return last
    ? {
        ...s,
        owners: last.before,
        updatedAt: Date.now(),
        history: s.history.slice(0, -1),
      }
    : s;
}

// RFC-style quoted fields; source values are data, never executable markup.
export function csvRows(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"') {
      if (quoted && text[i + 1] === '"') {
        field += '"';
        i++;
      } else quoted = !quoted;
    } else if (!quoted && (c === ',' || c === '\n')) {
      row.push(field.replace(/\r$/, ''));
      field = '';
      if (c === '\n') {
        rows.push(row);
        row = [];
      }
    } else field += c;
  }
  if (quoted) throw new Error('Incomplete stats file');
  if (field || row.length) {
    row.push(field.replace(/\r$/, ''));
    rows.push(row);
  }
  return rows;
}
export function parseUsage(csv: string, season: number): WeeklyUsage[] {
  const [header, ...data] = csvRows(csv);
  for (const field of [
    'player_id',
    'player_display_name',
    'position',
    'season',
    'season_type',
    'week',
    'targets',
    'carries',
    'attempts',
  ])
    if (!header?.includes(field))
      throw new Error('Stats source schema changed');
  const result: WeeklyUsage[] = [];
  for (const row of data) {
    const get = (key: string) => row[header.indexOf(key)] ?? '';
    if (
      +get('season') !== season ||
      get('season_type') !== 'REG' ||
      !['QB', 'RB', 'WR', 'TE'].includes(get('position'))
    )
      continue;
    const week = +get('week');
    if (!Number.isInteger(week) || week < 1 || week > 18 || !get('player_id'))
      continue;
    const num = (key: string) => {
      const n = Number(get(key));
      return Number.isFinite(n) ? n : 0;
    };
    result.push({
      id: get('player_id'),
      name: get('player_display_name'),
      position: get('position'),
      team: get('team'),
      week,
      targets: num('targets'),
      carries: num('carries'),
      attempts: num('attempts'),
      targetShare: get('target_share') ? num('target_share') : null,
    });
  }
  return result;
}
export function usageSummary(rows: WeeklyUsage[], latestWeek: number) {
  const recent = rows.filter((r) => r.week > latestWeek - 3);
  const previous = rows.filter(
    (r) => r.week <= latestWeek - 3 && r.week > latestWeek - 6,
  );
  const volume = (r: WeeklyUsage) =>
    r.position === 'QB'
      ? r.attempts + r.carries
      : r.position === 'RB'
        ? r.carries + r.targets
        : r.targets;
  const avg = (r: WeeklyUsage[]) =>
    r.reduce((sum, v) => sum + volume(v), 0) / Math.max(r.length, 1);
  return {
    games: recent.length,
    volume: avg(recent),
    trend:
      previous.length && recent.length ? avg(recent) - avg(previous) : null,
    confidence: recent.length >= 3 ? 'Moderate' : 'Low',
  };
}

export function parseStats(value: unknown): StatsSnapshot {
  const s = value as StatsSnapshot;
  if (
    !s ||
    s.season !== 2026 ||
    !Number.isFinite(s.fetchedAt) ||
    !Number.isInteger(s.latestWeek) ||
    s.latestWeek < 1 ||
    s.latestWeek > 18 ||
    !Array.isArray(s.rows) ||
    s.rows.length > 30000 ||
    !s.rows.every(
      (r) =>
        r &&
        typeof r.id === 'string' &&
        typeof r.name === 'string' &&
        typeof r.position === 'string' &&
        typeof r.team === 'string' &&
        Number.isInteger(r.week) &&
        r.week >= 1 &&
        r.week <= 18 &&
        [r.targets, r.carries, r.attempts].every(Number.isFinite),
    )
  )
    throw new Error('Stats data is invalid; previous data retained.');
  return s;
}
