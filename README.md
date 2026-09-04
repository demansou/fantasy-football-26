# Fantasy Football 2026 Draft Optimizer

This repository is the foundation for a Yahoo PPR draft assistant that ranks a
player **for this league, roster, and pick** instead of copying a static expert
list. The first working slice is an offline, deterministic recommendation engine.

It currently supports:

- a responsive browser draft room with click-to-place picks, a full league-wide
  snake-draft matrix, past-pick correction, roster construction, undo, local
  persistence, downloadable/importable backups, offline reload support, avoid/hide
  controls, a draft-day health panel, and adjustable position weights;
- 267 current draft rankings that use FFC ADP only for cross-position market timing,
  then adjust QB/RB/WR/TE with pinned opportunity, high-value usage, team environment,
  and role evidence while labeling K/DST as market-only;
- next-snake-turn market survival estimates using each player's observed ADP spread,
  labeled as an uncalibrated normal-curve heuristic and excluded from the football rank;
- configurable teams, starters, flex eligibility, bench, and position limits;
- full-PPR, half-PPR, or custom stat scoring;
- raw-stat projections or a source-provided fantasy-points override;
- league-specific value over replacement player (VORP), including flex demand;
- separate team profiles for passing volume, rushing volume, QB play, play caller,
  line quality, pace, scoring environment, game script, and continuity;
- position-specific player context, including target/backfield opportunity, valuable
  usage, competition, efficiency, receiving role, rushing floor, and QB variance;
- immutable current and historical nflverse player/roster/depth snapshots, explicit
  FFC identity reconciliation, retrospectively tested role priors, and reconciled
  weekly availability scenarios;
- a fail-closed current-role evidence audit that joins dated source claims to every
  flagged player/metric estimate without allowing unvalidated manual overrides;
- a pre-outcome 2026 forecast bundle whose fingerprint binds the scoring contract,
  all parent hashes, and all frozen team/player/weekly artifacts;
- live roster need, positional runs, scarcity, ADP timing, projection ranges, bye
  overlap, and K/DST timing with adaptive weights;
- an explainable CLI with table or JSON output.

The browser consumes the hash-verified 2026 production freeze and a freshness-gated
10-team PPR market snapshot. These are opportunity rankings, not fantasy-point
projections: efficiency and touchdowns are excluded, QB rushing and RB carry
calibration remain higher-risk, and K/DST use market timing only. The generated
artifact preserves those limitations in its metadata and the browser exposes them.

## Try it

### Browser draft room

The browser app lives in `web/` and requires Node.js. Use **League** to choose 8, 10,
or 12 teams, your draft slot, and 0-12 bench spots, then click **Draft** on your turn
or **Mark gone** for every other selection. Picks, league settings, and weights
persist in the current browser. The deployed owner-only board is at
<https://fantasy-football-26.vista-verde-6860.chatgpt.site>.

Use **Refresh injuries** once on draft day to pull Sleeper's free, no-token player
status feed. The browser caches it for 20 hours, matches it to the 217 modeled skill
players, and adds visible injury/practice/roster warnings without changing their
frozen ranks. Confirm any consequential alert against Yahoo before selecting a player.

```bash
python3 scripts/build_web_rankings.py --as-of 2026-09-03
python3 scripts/build_web_rankings.py --as-of 2026-09-03 --check
cd web
npm install
npm run dev
```

The builder refuses an FFC source window more than four days old, unexpected position
coverage, duplicate source IDs, altered hashes, or a changed freeze fingerprint.

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

### Fetch current ADP

The first production data adapter snapshots
[Fantasy Football Calculator](https://help.fantasyfootballcalculator.com/article/42-adp-rest-api)
ADP. It uses only the Python standard library and requires no API key:

```bash
python3 -m fantasy_draft fetch-ffc-adp \
  --season 2026 \
  --teams 10 \
  --scoring ppr
```

Each run creates an immutable timestamped directory under
`data/raw/fantasy_football_calculator/adp/<season>/` containing:

- `raw.json`: the exact source response;
- `adp.csv`: validated canonical fields with `DEF`/`PK` normalized to `DST`/`K`;
- `manifest.json`: query parameters, retrieval/source dates, schema fingerprints,
  HTTP provenance, record counts, and SHA-256 hashes.

Use `--output` to choose a different snapshot root and `--json` for a
machine-readable run summary. Local raw snapshots are ignored by Git because daily
collection can accumulate quickly.

FFC provides market ADP, not fantasy-point projections. Its output remains separate
from football opportunity; the player-role build now reconciles it to the nflverse
identity spine for market comparison without allowing ADP to set a role.

### Build the NFL environment pilot

The actual-football pipeline measures every offense from 2021 through 2025 using
nflverse play-by-play, same-season roster IDs, and FTN charting. It derives pass/run
tendency, neutral pass rate over expectation, formation, motion, play action, RPO,
target allocation by position, quarterback runs, volume, explosiveness, and outcome
metrics:

```bash
python3 -m fantasy_draft fetch-nflverse-style \
  --season 2021 --season 2022 --season 2023 --season 2024 --season 2025
```

Each run preserves the exact source assets and writes a normalized
`team_style.csv` plus a hash-bearing manifest under
`data/raw/nflverse/team_style/`. Use the resulting snapshot directory to combine
measured history with the dated KC/SEA/PHI coaching and news pilot:

```bash
python3 -m fantasy_draft build-team-environment \
  --styles data/raw/nflverse/team_style/2021-2025/<timestamp> \
  --research data/research/2026/team_environment_pilot.json
```

The derived snapshot contains the complete source/staff/claim graph, forecast style
metrics with league-relative percentiles, an explainable certainty breakdown, and
QB/RB/WR/TE team-environment scores. These are explicitly labeled
`uncalibrated_heuristic`: they are neither fantasy-point projections nor empirical
probabilities yet. See [`docs/TEAM_ENVIRONMENT_PILOT_2026.md`](docs/TEAM_ENVIRONMENT_PILOT_2026.md).

### Verify the 2026 coaching census

Snapshot all current official club staff pages, then exact-join the independently
sourced play-caller registry:

```bash
python3 -m fantasy_draft fetch-official-staff --season 2026
python3 -m fantasy_draft build-coaching-census \
  --official-staff data/raw/official_nfl_club_staff/2026/all/<timestamp>
```

The second command will not publish unless all 32 head coaches and primary OCs match
the official snapshot and every separately sourced caller is on that club's current
staff. Its output contains all current offensive position coaches and caller flags;
it does not claim that caller identity alone predicts 2026 style.

The next commands join the official 2025 baseline, audited caller episodes, current
system evidence, and observed NFL styles. Official Record & Fact Books from 2022-25
also supply time-correct staff baselines for the historical transition and certainty
tests:

```bash
for season in 2022 2023 2024 2025; do
  python3 -m fantasy_draft fetch-nfl-record-book-staff --season "$season"
done

python3 -m fantasy_draft build-staff-continuity \
  --prior-staff data/raw/official_nfl_record_fact_book/2025/all/<timestamp> \
  --current-staff data/raw/official_nfl_club_staff/2026/all/<timestamp> \
  --callers data/derived/coaching_census/2026/<timestamp> \
  --prior-callers data/raw/espn_nfl_playcallers/2025/all/<timestamp>

python3 -m fantasy_draft build-caller-fingerprints \
  --current-census data/derived/coaching_census/2026/<timestamp> \
  --continuity data/derived/staff_continuity/2026/<timestamp> \
  --historical-callers data/raw/espn_nfl_playcallers/2023/all/<timestamp> \
  --historical-callers data/raw/espn_nfl_playcallers/2024/all/<timestamp> \
  --historical-callers data/raw/espn_nfl_playcallers/2025/all/<timestamp> \
  --styles data/raw/nflverse/team_style/2021-2025/<timestamp>

python3 -m fantasy_draft build-transition-backtest \
  --nflverse data/raw/nflverse/team_style/2021-2025/<timestamp> \
  --prior-callers data/raw/researched_nfl_playcallers/2022/all/<timestamp> \
  --target-callers data/raw/espn_nfl_playcallers/2023/all/<timestamp> \
  --changes data/research/backtests/2023_opening_caller_changes.json

python3 -m fantasy_draft build-playcaller-evidence \
  --registry data/research/backtests/2025_opening_callers.json

python3 -m fantasy_draft evaluate-transition-backtests \
  --backtest data/derived/transition_backtest/2023/<timestamp> \
  --backtest data/derived/transition_backtest/2024/<timestamp> \
  --backtest data/derived/transition_backtest/2025/<timestamp> \
  --development-season 2023 --development-season 2024 \
  --holdout-season 2025

python3 -m fantasy_draft build-staff-continuity \
  --prior-staff data/raw/official_nfl_record_fact_book/2022/all/<timestamp> \
  --current-staff data/raw/official_nfl_record_fact_book/2023/all/<timestamp> \
  --callers data/raw/espn_nfl_playcallers/2023/all/<timestamp>/callers.csv \
  --prior-callers data/raw/researched_nfl_playcallers/2022/all/<timestamp>

python3 -m fantasy_draft build-staff-continuity \
  --prior-staff data/raw/official_nfl_record_fact_book/2023/all/<timestamp> \
  --current-staff data/raw/official_nfl_record_fact_book/2024/all/<timestamp> \
  --callers data/raw/espn_nfl_playcallers/2024/all/<timestamp>/callers.csv \
  --prior-callers data/raw/espn_nfl_playcallers/2023/all/<timestamp>

python3 -m fantasy_draft build-staff-continuity \
  --prior-staff data/raw/official_nfl_record_fact_book/2024/all/<timestamp> \
  --current-staff data/raw/official_nfl_record_fact_book/2025/all/<timestamp> \
  --callers data/raw/researched_nfl_playcallers/2025/all/<timestamp>/callers.csv \
  --prior-callers data/raw/espn_nfl_playcallers/2024/all/<timestamp>

python3 -m fantasy_draft evaluate-historical-certainty \
  --backtest data/derived/transition_backtest/2023/<timestamp> \
  --backtest data/derived/transition_backtest/2024/<timestamp> \
  --backtest data/derived/transition_backtest/2025/<timestamp> \
  --continuity data/derived/staff_continuity/2023/<timestamp> \
  --continuity data/derived/staff_continuity/2024/<timestamp> \
  --continuity data/derived/staff_continuity/2025/<timestamp>

python3 -m fantasy_draft build-position-environments \
  --caller-fingerprints data/derived/caller_fingerprints/2026/<timestamp>
```

The fixed 2023-25 test found lower caller-aware error in every season and both early
windows. Pooled paired deltas are -0.150 through Week 6 and -0.111 through Week 8,
with destination-team-clustered 95% intervals of -0.232 to -0.043 and -0.184 to
-0.024; 2023-24-calibrated global residual
bands covered 93.2% and 91.9% on untouched 2025 data. The mean rule therefore clears
its declared historical gate, although the intervals cross zero when 2025 is removed.
The separate one-year certainty reconstruction fails its promotion gate: both score
lower bounds have the wrong rank direction on 2025, the Week 6 high tier covers only
89.0%, and score-tiered intervals are wider than global per-metric bands. All 0-100
certainty values therefore remain evidence indices, not probabilities, and they must
not narrow numeric 2026 uncertainty. The evaluations are in
[`docs/CALLER_TRANSITION_EVALUATION_2026.md`](docs/CALLER_TRANSITION_EVALUATION_2026.md)
and
[`docs/HISTORICAL_CERTAINTY_EVALUATION_2026.md`](docs/HISTORICAL_CERTAINTY_EVALUATION_2026.md);
the complete source recommendation and all-team scorecard are in
[`docs/NFL_ENVIRONMENT_RECOMMENDATION_2026.md`](docs/NFL_ENVIRONMENT_RECOMMENDATION_2026.md);
the bottom-up design is in
[`docs/FORECAST_PIPELINE_2026.md`](docs/FORECAST_PIPELINE_2026.md).

### Build current player role priors

Fetch the current player identity table, 2026 roster and timestamped depth history,
2023-25 weekly opportunity, and Pro Football Reference snaps:

```bash
python3 -m fantasy_draft fetch-nflverse-players \
  --season 2026 \
  --history-season 2023 \
  --history-season 2024 \
  --history-season 2025
```

Then allocate the caller-aware team pools to current active players and audit the
FFC market crosswalk:

```bash
python3 -m fantasy_draft build-player-roles \
  --players data/raw/nflverse/player_context/2026/<timestamp> \
  --position-environments data/derived/position_environments/2026/<timestamp> \
  --caller-fingerprints data/derived/caller_fingerprints/2026/<timestamp> \
  --observed-styles data/raw/nflverse/team_style/2021-2025/<timestamp> \
  --ffc-adp data/raw/fantasy_football_calculator/adp/2026/<timestamp>
```

The derived snapshot contains resource-specific role ranges, exact median
team-pool reconciliation, the complete FFC crosswalk, source review records,
an all-affiliated latent-role table, and a separate non-active availability queue.

Build the historical player-state source, compare the frozen role formula with
depth/history baselines, and create weekly availability/redistribution scenarios:

```bash
python3 -m fantasy_draft fetch-nflverse-player-history

python3 -m fantasy_draft build-role-backtest \
  --player-history data/raw/nflverse/player_history/<timestamp> \
  --target-season 2023 --target-season 2024 --target-season 2025

python3 -m fantasy_draft build-availability \
  --player-history data/raw/nflverse/player_history/<timestamp> \
  --players data/raw/nflverse/player_context/2026/<timestamp> \
  --player-roles data/derived/player_roles/2026/<timestamp>
```

The 2023-25 role test selects depth-only QB shares and the depth/history blend for
RB/WR/TE. It uses actual weekly active status only as an evaluation oracle, keeping
conditional role separate from injury availability. Availability status detail does
not clearly beat a simpler active/non-active baseline overall, so those probabilities
remain broad population scenarios. The pipeline does not turn generic reserve-list
players into zero season projections or invent return dates; a reviewed league rule
may still force zero when a transaction makes a player season-ineligible. Results and limitations are in
[`docs/AVAILABILITY_AND_ROLE_BACKTEST_2026.md`](docs/AVAILABILITY_AND_ROLE_BACKTEST_2026.md).

Build audited high-value history, test every candidate signal time-correctly, and
apply only the metrics that clear the frozen gate:

```bash
python3 -m fantasy_draft build-high-value-history \
  --nflverse data/raw/nflverse/team_style/2021-2025/<timestamp>

python3 -m fantasy_draft build-high-value-backtest \
  --player-history data/raw/nflverse/player_history/<timestamp> \
  --high-value-history data/derived/high_value_history/2021-2025/<timestamp> \
  --target-season 2023 --target-season 2024 --target-season 2025 \
  --bootstrap-samples 5000

python3 -m fantasy_draft build-high-value-priors \
  --player-roles data/derived/player_roles/2026/<timestamp> \
  --high-value-history data/derived/high_value_history/2021-2025/<timestamp> \
  --high-value-backtest data/derived/high_value_backtest/2023-2024-2025/<timestamp> \
  --availability data/derived/availability/2026/<timestamp>

python3 -m fantasy_draft build-high-value-volume-backtest \
  --high-value-history data/derived/high_value_history/2021-2025/<timestamp> \
  --high-value-role-backtest data/derived/high_value_backtest/2023-2024-2025/<timestamp> \
  --development-season 2023 --development-season 2024 \
  --holdout-season 2025 --bootstrap-samples 5000

python3 -m fantasy_draft build-resource-backtest \
  --player-history data/raw/nflverse/player_history/<timestamp> \
  --development-season 2023 --development-season 2024 \
  --holdout-season 2025 --bootstrap-samples 5000

python3 -m fantasy_draft evaluate-caller-resources \
  --backtest data/derived/transition_backtest/2023/<timestamp> \
  --backtest data/derived/transition_backtest/2024/<timestamp> \
  --backtest data/derived/transition_backtest/2025/<timestamp> \
  --player-history data/raw/nflverse/player_history/<timestamp> \
  --observed-styles data/raw/nflverse/team_style/2021-2025/<timestamp> \
  --development-season 2023 --development-season 2024 \
  --holdout-season 2025 --bootstrap-samples 5000

python3 -m fantasy_draft build-high-value-volumes \
  --player-roles data/derived/player_roles/2026/<timestamp> \
  --high-value-history data/derived/high_value_history/2021-2025/<timestamp> \
  --high-value-priors data/derived/high_value_priors/2026/<timestamp> \
  --high-value-volume-backtest data/derived/high_value_volume_backtest/2023-2024-2025/<timestamp> \
  --resource-backtest data/derived/resource_backtest/2023-2024-2025/<timestamp>

python3 -m fantasy_draft build-role-research-audit \
  --high-value-volumes data/derived/high_value_volumes/2026/<timestamp> \
  --evidence data/research/2026/player_role_evidence.json

python3 -m fantasy_draft build-prospective-freeze \
  --caller-fingerprints data/derived/caller_fingerprints/2026/<timestamp> \
  --position-environments data/derived/position_environments/2026/<timestamp> \
  --player-roles data/derived/player_roles/2026/<timestamp> \
  --availability data/derived/availability/2026/<timestamp> \
  --high-value-priors data/derived/high_value_priors/2026/<timestamp> \
  --high-value-volumes data/derived/high_value_volumes/2026/<timestamp> \
  --role-research data/derived/role_research/2026/<timestamp> \
  --cutoff 2026-09-03
```

The corrected source audit follows nflreadr's current `read_thrown` definition,
leaves 2022 primary reads structurally missing, and rejects every first-read feature.
Seven signals are frozen for prospective 2026 conditional-share scoring: RB
inside-5/inside-10 carries and two-minute targets, WR end-zone/deep targets, and TE
deep/two-minute targets. A separate development/untouched-holdout test rejects
team-specific conditional-rate persistence for all seven, then multiplies pooled
rates by the caller-aware carry/target pools to produce reconciled team and player
opportunity counts. A separate time-correct reference test supplies explicitly
provisional full-season residual envelopes. The direct six-resource test now shares
production's conversion of eligible PBP plays to official dropbacks, targets, and RB
carries, but no resource clears its strict mean-promotion gate. QB rush is clearly
worse than shrunken persistence; RB carries undercovers in both early windows, WR
targets undercovers at Week 8, and all-six marginal-band coverage is only 70.0%/66.7%.
Those counts therefore remain provisional and still exclude efficiency, touchdowns,
and fantasy points.
The current-role audit ranks 365 player/metric exceptions, carries exact
thin-history and large-adjustment reasons, and source-reviews all 365 Jets,
Colts, Chiefs, Dolphins, Bears, Browns, Lions, Ravens, Packers, Seahawks, Cardinals,
Chargers, Steelers, Titans, Bengals, Saints, Buccaneers, 49ers, Bills, Commanders,
Vikings, Cowboys, Jaguars, Raiders, Eagles, Patriots, Rams, Giants, Panthers, Texans,
Falcons, and Broncos cases plus the Jets team-rate exception with zero numeric
overrides. See
[`docs/HIGH_VALUE_ROLE_BACKTEST_2026.md`](docs/HIGH_VALUE_ROLE_BACKTEST_2026.md)
[`docs/HIGH_VALUE_VOLUME_BACKTEST_2026.md`](docs/HIGH_VALUE_VOLUME_BACKTEST_2026.md),
[`docs/RESOURCE_POOL_BACKTEST_2026.md`](docs/RESOURCE_POOL_BACKTEST_2026.md),
[`docs/CALLER_RESOURCE_BACKTEST_2026.md`](docs/CALLER_RESOURCE_BACKTEST_2026.md),
and [`docs/CURRENT_ROLE_RESEARCH_2026.md`](docs/CURRENT_ROLE_RESEARCH_2026.md).
The v0.4 immutable pre-outcome bundle supersedes v0.3 solely for a
denominator-definition correction; its pinned fingerprint and Week 4/8/18 scoring
rules are in
[`docs/PROSPECTIVE_EVALUATION_2026.md`](docs/PROSPECTIVE_EVALUATION_2026.md).

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

The next milestones are scoring the registered forecast at Weeks 4/8/18, extending
the direct caller-resource test to Week 18 with component and joint calibration,
backfilling time-correct changed-caller scheme/destination
evidence and richer multi-season anchors before attempting another certainty-score
calibration, obtaining a valid all-route source, Yahoo league sync, and
pick-availability simulation. The full sequence and acceptance criteria are in
[`docs/ROADMAP.md`](docs/ROADMAP.md).

Yahoo credentials and refresh tokens belong only in ignored local storage. Never
put them in configuration files, projection exports, commits, or logs.
