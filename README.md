# Fantasy Football 2026 Draft Optimizer

This repository is the foundation for a Yahoo PPR draft assistant that ranks a
player **for this league, roster, and pick** instead of copying a static expert
list. The first working slice is an offline, deterministic recommendation engine.

It currently supports:

- a responsive browser draft room with click-to-place picks, snake-draft tracking,
  roster construction, undo, local persistence, and adjustable position weights;
- configurable teams, starters, flex eligibility, bench, and position limits;
- full-PPR, half-PPR, or custom stat scoring;
- raw-stat projections or a source-provided fantasy-points override;
- league-specific value over replacement player (VORP), including flex demand;
- separate team profiles for passing volume, rushing volume, QB play, play caller,
  line quality, pace, scoring environment, game script, and continuity;
- position-specific player context, including target/backfield opportunity, valuable
  usage, competition, efficiency, receiving role, rushing floor, and QB variance;
- live roster need, positional runs, scarcity, ADP timing, projection ranges, bye
  overlap, and K/DST timing with adaptive weights;
- an explainable CLI with table or JSON output.

The included player data is intentionally synthetic. No 2026 player recommendation
should be trusted until we connect current, attributable projection and ADP inputs.

## Try it

### Browser draft room

The browser app lives in `web/` and requires Node.js. It starts with clearly labeled
synthetic data; use **League** to choose 8, 10, or 12 teams and your draft slot, then
click **Draft** on your turn or **Mark gone** for every other selection. Picks and
weights persist in the current browser.

```bash
cd web
npm install
npm run dev
```

The selected live-data architecture and its licensing/freshness constraints are in
[`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md).

### Python recommendation engine

No third-party Python packages are required for the existing CLI.

```bash
python3 -m unittest discover -s tests -v
python3 -m fantasy_draft recommend \
  --league examples/demo_league.json \
  --projections examples/demo_projections.csv \
  --team-profiles examples/demo_team_profiles.csv \
  --state examples/demo_draft_state.json \
  --top 10
```

For machine-readable output, add `--json`. To rank an untouched player pool,
use `rank` without a draft-state file:

```bash
python3 -m fantasy_draft rank \
  --league config/yahoo_full_ppr.json \
  --projections path/to/your-projections.csv \
  --top 50
```

An editable input header is in
[`examples/projections_template.csv`](examples/projections_template.csv).

## Yahoo baseline

Yahoo's current official default is a 10-team, 15-player roster with one QB,
two RB, two WR, one TE, one flex, one K, one D/ST, and six bench players. Its
default reception value is **0.5**, not 1.0. Commissioners can change these
settings. See [Yahoo's default league settings](https://help.yahoo.com/kb/default-league-settings-scoring-stats-fantasy-football-sln6489.html).

Accordingly, this repository keeps two presets:

- [`config/yahoo_default_half_ppr.json`](config/yahoo_default_half_ppr.json)
  mirrors the documented Yahoo default.
- [`config/yahoo_full_ppr.json`](config/yahoo_full_ppr.json) changes receptions
  to 1.0 for the requested full-PPR starting point.

Your actual league settings override both. Before producing a real draft board,
we need the league's team count, roster/scoring settings, draft slot, draft type,
keepers, and any position caps.

## How a recommendation is built

The engine first calculates projected points under the selected league scoring.
It then allocates every league-wide fixed starter and flex starter to determine a
replacement baseline at each position. Each available player gets a decomposed
score:

```text
VORP
+ open-starter/flex need
+ expected positional drop before our next snake pick
+ ADP value or wait signal
+ position-specific team and player profile adjustments
+ ceiling reward - downside penalty
- roster-construction and early-K/DST penalties
```

The score is recalculated after every pick. An observed position run increases that
position's scarcity weight; open-lineup need becomes more urgent as the draft gets
later; ADP timing matters more before a long snake turn; and bench candidates get a
slightly larger upside weight. Every effective weight, live signal, and score
component is returned in JSON and summarized in the CLI.

The context model follows different rules by position:

- **WR/TE:** passing volume, QB play, OC/play caller, pace, scoring environment,
  target opportunity, valuable targets, competition, and role security.
- **RB:** rushing volume, run blocking, likely positive game script, scoring
  environment, backfield share, goal-line/high-value work, and PPR receiving role.
- **QB:** play caller, pass protection, passing volume, pace, efficiency, rushing
  floor, continuity, and an explicit penalty/reward for weekly variance.

The model is a starting hypothesis, not a hidden claim of predictive accuracy.
Weights must be calibrated through historical draft simulations before we rely on
small score differences. See [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## Projection input

The CSV accepts either of these modes per player:

1. Supply `projected_points` from a source already scored for this league.
2. Leave `projected_points` blank and supply raw projected stats such as
   `receptions`, `receiving_yards`, and `receiving_touchdowns`; the engine will
   recompute points from the league JSON.

Mode 2 is preferable when league scoring differs from the source's defaults.
Optional player-level 0-to-1 analytics fields are neutral at `0.5` unless noted:

- `role_security`
- `upside_rating`
- `opportunity_rating`
- `high_value_usage_rating`
- `competition_rating` (higher means a clearer path to volume)
- `efficiency_rating`
- `receiving_role_rating`
- `rushing_floor_rating`
- `weekly_variance` (lower is more stable)
- `injury_risk` (neutral risk is `0.0`)

Team inputs live in a separate CSV; see
[`examples/team_profiles_template.csv`](examples/team_profiles_template.csv). It
contains passing/rushing volume, QB play, OC/play caller, pass/run blocking, pace,
scoring environment, positive game script, and continuity ratings. Pass it with
`--team-profiles`.

All analytics inputs should be normalized, source-dated, and calibrated in the
future data pipeline. Context must not be counted twice if the base projection
already incorporates the same signal. Raw metric definitions and normalization
rules are in [`docs/ANALYTICS_INPUTS.md`](docs/ANALYTICS_INPUTS.md).

## Planned live workflow

Yahoo's official Fantasy Sports API can retrieve game, league, team, and player
resources and uses OAuth for private league data. See the
[Fantasy Sports API guide](https://developer.yahoo.com/fantasysports/guide/) and
[Yahoo OAuth guide](https://developer.yahoo.com/oauth2/guide/).

The next milestones are current 2026 data ingestion, historical calibration, Yahoo
league sync, pick-availability simulation, and a fast live draft board. The full
sequence and acceptance criteria are in [`docs/ROADMAP.md`](docs/ROADMAP.md).

Yahoo credentials and refresh tokens belong only in ignored local storage. Never
put them in configuration files, projection exports, commits, or logs.
