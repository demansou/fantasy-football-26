# Data source and adapter plan

Status: selected architecture for the 2026 Yahoo PPR draft assistant. The browser
preview still uses synthetic players; this document defines the path to attributable,
refreshable production data.

## Decision

No single source covers league state, market price, projections, and the team/player
context this optimizer needs. The production dataset will join three adapters:

| Role | Selected source | What we use | Key constraint |
| --- | --- | --- | --- |
| League and draft state | [Yahoo Fantasy Sports API](https://sports.yahoo.com/developer/docs/) | League settings, teams, eligible players, draft results, and Yahoo draft analysis | OAuth 2.0 and [application review](https://sports.yahoo.com/developer/access/) are required |
| Team and player context | [nflverse](https://github.com/nflverse/nflverse-data) | Play-by-play, player/team stats, participation, depth, injuries, schedules, IDs, and expected opportunity | Attribute the CC-BY 4.0 data and preserve source dates |
| Baseline projections and market | A licensed projections feed or a user-owned CSV export | Projected stats/points, consensus rank, positional rank, and ADP | Do not redistribute a commercial feed without an appropriate license |

The initial projection adapter supports a user-supplied CSV because it is portable
and keeps the project useful before commercial access is chosen. A licensed
FantasyPros integration is the leading hosted option. For a personal/offline build,
[nflreadr's fantasy ranking loader](https://nflreadr.nflverse.com/reference/load_ff_rankings.html)
can also provide current ECR/ADP fields and Yahoo IDs through DynastyProcess, subject
to the upstream terms that apply to the intended use.

## Why each adapter exists

### `YahooLeagueAdapter`

Yahoo is authoritative for this league, not for the full predictive model. The
adapter will retrieve the actual scoring/roster configuration, franchises, eligible
player pool, completed picks, and Yahoo market fields. Yahoo documents league,
team, player, and `draftresults` resources in its
[Fantasy Sports API](https://sports.yahoo.com/developer/docs/).

Yahoo API access is not assumed to be available on draft day. The current access
page says applications are reviewed, so manual pick placement remains a supported
workflow rather than an emergency-only fallback. OAuth client secrets and refresh
tokens must stay in a server-side secret store; they must never be shipped to the
browser, committed, or logged.

### `NflverseProfileAdapter`

nflverse is the open analytical spine. Its loaders cover
[player and team statistics](https://nflreadr.nflverse.com/reference/index.html),
[expected fantasy opportunity](https://nflreadr.nflverse.com/reference/load_ff_opportunity.html),
[player identity data](https://nflreadr.nflverse.com/reference/load_players.html),
and [cross-platform fantasy IDs](https://nflreadr.nflverse.com/reference/load_ff_playerids.html).
The published [data schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html)
is used to set freshness expectations instead of treating every field as real-time.

This adapter produces dated, normalized 0-to-1 profile features:

- WR/TE: route participation, target share, targets per route, high-value target
  share, team dropbacks, pass efficiency, pace, scoring environment, role stability,
  and competition.
- RB: carry and opportunity share, targets, goal-line share, expected fantasy points,
  team rush volume, rush success/EPA, yards-before-contact proxies, positive game
  script, and role stability.
- QB: weekly fantasy-point variance, adjusted efficiency, completion over expectation,
  pressure/sack proxies, pass volume, pace, rushing floor, supporting-cast quality,
  and continuity.

Offensive coordinator and play-caller assignments are a separate, versioned manual
input initially. Each team row must record the coach/play caller, role, source URL,
and `verified_at` date from an official team announcement or other authoritative
source. This avoids inventing a reliable automated feed where we do not yet have one.

### `ProjectionAdapter`

The model needs a neutral baseline before applying the user's context preferences.
The adapter accepts either raw projected stats, which the Python engine scores under
the actual Yahoo rules, or already-scored fantasy points. It also accepts ADP and
rank uncertainty. A hosted commercial adapter must be licensed; otherwise the user
imports a file they are entitled to use. The current public
[FantasyPros ADP page](https://www.fantasypros.com/nfl/adp/overall.php) is useful for
human verification but is not treated as permission to scrape and republish it.

## Join key and snapshot contract

The canonical player table stores `gsis_id` when available plus Yahoo, ESPN, Sleeper,
FantasyPros, and other source IDs from the nflverse fantasy ID mapping. Name/team
matching is only a logged fallback and must never silently merge ambiguous players.

Every browser snapshot will contain:

- `schema_version`, `season`, `generated_at`, and per-source `as_of` timestamps;
- the exact league/scoring/roster configuration;
- players with source IDs, projections, ADP, injury/availability state, and normalized
  player-context features;
- team profiles with the raw metric, normalization window, normalized value, source,
  and verification date;
- provenance for every input family and warnings for stale or missing inputs.

The browser consumes the snapshot through one stable interface. That keeps ranking
and draft interaction independent from whether the snapshot came from local CSVs,
an offline nflverse build, or a Yahoo-authenticated server refresh.

## Refresh and failure behavior

1. Fetch each source into an immutable, source-dated raw cache.
2. Validate schema, season, IDs, duplicates, ranges, and freshness before joining.
3. Normalize within position or team using documented rolling windows; do not replace
   missing values with optimistic assumptions.
4. Publish a versioned snapshot atomically only after validation succeeds.
5. Keep the last valid snapshot when a refresh fails and display its age in the UI.
6. Poll Yahoo draft results when approved, but let the user immediately correct or
   enter any pick manually. Reconcile by Yahoo player ID and overall pick number.

## Implementation order

1. Add snapshot JSON import/export to the browser and generate the same schema from
   the existing CSV/JSON Python inputs.
2. Build the nflverse ingestion and profile-normalization job with attribution and
   historical calibration tests.
3. Add the projection adapter selected by the user: licensed API or owned CSV export.
4. Register the Yahoo application, implement server-side OAuth, read actual league
   configuration, and reconcile draft results.
5. Backtest weight families and expose uncertainty/freshness in the recommendation
   explanation before treating small rank differences as meaningful.

Until steps 1-3 are complete with current 2026 inputs, the demo player names and
scores are interaction fixtures, not draft advice.
