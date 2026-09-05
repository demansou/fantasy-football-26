import { parseUsage } from '@/lib/season';

export async function GET() {
  const season = 2026;
  const url = `https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_${season}.csv`;
  try {
    const response = await fetch(url, {
      signal: AbortSignal.timeout(20000),
      headers: { Accept: 'text/csv' },
    });
    if (response.status === 404)
      return Response.json(
        {
          error:
            '2026 regular-season stats are not published yet. Your saved roster and previous stats are unchanged.',
        },
        { status: 404 },
      );
    if (!response.ok) throw new Error('Source unavailable');
    const csv = await response.text();
    if (csv.length > 15_000_000) throw new Error('Source too large');
    const rows = parseUsage(csv, season);
    if (!rows.length)
      return Response.json(
        { error: 'No 2026 regular-season usage is available yet.' },
        { status: 404 },
      );
    return Response.json(
      {
        season,
        fetchedAt: Date.now(),
        sourceUpdated: response.headers.get('last-modified'),
        latestWeek: Math.max(...rows.map((r) => r.week)),
        rows,
      },
      { headers: { 'Cache-Control': 'private, max-age=900' } },
    );
  } catch {
    return Response.json(
      {
        error:
          'Stats could not be refreshed. Previous stats remain available; please try again later.',
      },
      { status: 502 },
    );
  }
}
