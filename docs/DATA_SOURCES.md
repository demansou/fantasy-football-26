# Data source and adapter plan

Status: selected architecture for the 2026 Yahoo PPR draft assistant. The browser
preview still uses synthetic players; this document defines the path to attributable,
refreshable production data.

## Decision

No single source covers league state, market price, projections, and the team/player
context this optimizer needs. The production dataset will join these source roles:

| Role | Selected source | What we use | Key constraint |
| --- | --- | --- | --- |
| League and draft state | [Yahoo Fantasy Sports API](https://sports.yahoo.com/developer/docs/) | League settings, teams, eligible players, draft results, and Yahoo draft analysis | OAuth 2.0 and [application review](https://sports.yahoo.com/developer/access/) are required |
| Primary market price | Yahoo draft analysis when access is approved | Platform-specific average pick, average round, and percent drafted | Live-draft refresh latency must be measured before relying on it |
| Immediate and fallback market price | [Fantasy Football Calculator](https://help.fantasyfootballcalculator.com/article/42-adp-rest-api) | Daily human-mock ADP, pick range, dispersion, and sample size | Not Yahoo-specific and not a projection; attribution is requested |
| Measured NFL environment | [nflverse](https://github.com/nflverse/nflverse-data) and FTN charting | Play-by-play, formation/concept tendencies, target allocation, current rosters/depth, schedules, and IDs | FTN charting begins in 2022; live injuries and participation are not dependable here |
| 2026 staff and scheme evidence | Official team staff pages and press conferences, then reputable reporting | HC/OC/play caller, every offensive position coach, continuity, stated system changes, and camp evidence | Living pages need access dates; team optimism is not evidence of effectiveness |
| Historical audit | [Pro Football Reference](https://www.pro-football-reference.com/) | Team seasons, head coaches, listed coordinators, rosters, conventional totals, and gap checks | Coordinator labels do not prove actual play-calling authority; use as an audit, not the granular feature store |
| Optional projection benchmark | A licensed feed or user-owned export | Compare the transparent opportunity model against an external consensus | Never make an opaque fantasy projection the factual NFL-environment layer |

The existing projection adapter supports a user-supplied CSV so the deterministic
optimizer remains testable, but no hosted fantasy projection has been selected as a
model input. If a licensed feed or user-owned export is added later, it will be a
blinded benchmark. For a personal/offline build,
[nflreadr's fantasy ranking loader](https://nflreadr.nflverse.com/reference/load_ff_rankings.html)
can provide ECR/ADP fields and Yahoo IDs through DynastyProcess, subject to upstream
terms; those fields remain market/benchmark data rather than NFL-environment truth.

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

### `NflverseStyleAdapter` — implemented

nflverse is the open analytical spine. Its loaders cover
[player and team statistics](https://nflreadr.nflverse.com/reference/index.html),
[expected fantasy opportunity](https://nflreadr.nflverse.com/reference/load_ff_opportunity.html),
[player identity data](https://nflreadr.nflverse.com/reference/load_players.html),
and [cross-platform fantasy IDs](https://nflreadr.nflverse.com/reference/load_ff_playerids.html).
The published [data schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html)
is used to set freshness expectations instead of treating every field as real-time.

As of September 3, 2026, 2026 roster and depth-chart release assets are current,
but no 2026 injury asset is published. Participation data from 2023 onward is
sourced after the postseason rather than during the season. Neither dataset may be
labeled as a live draft-day signal until its actual update behavior changes and is
reverified.

`fetch-nflverse-style` currently snapshots 2021-25 play-by-play and rosters plus
2022-25 FTN charting, joins plays by nflverse game/play ID and receivers/rushers by
GSIS ID, then produces one observed team-season record. The implemented metrics are:

- overall and neutral early-down eligible PBP pass-play rate, neutral pass rate over
  expectation, red-zone PBP pass-play rate, plays per game, shotgun, no huddle, and
  target depth;
- under-center, pistol, pre-snap motion, play action, screen, RPO, multi-back,
  out-of-pocket, and quarterback-sneak rates from FTN charting;
- RB/WR/TE target shares, scramble and designed-QB-run rates, explosive-play rate,
  success rate, and EPA per play.

The output preserves exact raw assets, source URLs, HTTP metadata, SHA-256 hashes,
source fields, calculation definitions, team counts, roster-position conflicts, and
target-position coverage. Style and outcomes remain distinct; historical EPA does
not become a fantasy projection.

The player-role adapter now produces dated current-roster role ranges for:

- WR/TE target share within the forecast position pool;
- RB carries and targets within the forecast RB pools; and
- QB dropbacks and forecast rush opportunities.

Weekly status-cohort availability and rule-backed minimum absences are now a separate
scenario layer. A second tested layer freezes seven player shares conditional on a
named high-value team-position event. A third development/holdout-tested layer now
multiplies holdout-selected conditional rates by the caller-aware base resource pools
to produce team and player opportunity counts. A fourth test supplies provisional
historical residual envelopes for the four carry/target resources used by those
counts; WR-target holdout coverage is below nominal. A fifth direct test passes six
caller-aware and persistence resources through production's exact conversion from
eligible PBP plays to official dropbacks, targets, and RB carries. It promotes no
resource, identifies clearly worse QB-rush performance and RB-carry undercoverage,
and does not supply joint coverage. All-player routes, Week-18 component/joint
calibration, efficiency, and individualized medical return forecasts remain
subsequent layers.

### Player context, history, role, and availability adapters — implemented priors

`fetch-nflverse-players` preserves the current nflverse player table, full roster,
and timestamp-appended depth release plus 2023-25 weekly player stats and PFR snap
counts. It emits full current-roster IDs, each team's latest depth rows, aggregated
player-team-season usage, and a source review. `roster_team`/`roster_status` retain
the raw roster-release values; `team`/`current_status` use the independently refreshed
player catalog when it identifies an ongoing club affiliation. Every disagreement
remains visible in the review file. nflverse/PFR joins use GSIS, ESPN, and PFR
identifiers only; names are never used.

`build-player-roles` joins those inputs to the caller-aware team position pools. It
uses a transparent recency/depth/transfer rule to publish marginal role ranges and
requires median shares and allocated opportunities to reconcile exactly in all 192
team/resource rooms. FFC is joined only as market metadata. Unique canonicalized
name+team+position matches resolve automatically; every mismatch or collision goes
to `identity_review.csv`. The command also requires the exact observed-style
snapshot, verifies its manifest/hash binding through the caller input, and estimates
three matched 2023-25 conversion factors: official QB dropbacks per eligible PBP pass
play, targets per eligible PBP pass play, and RB carries per non-QB PBP rush play.

`fetch-nflverse-player-history` separately preserves 2021-25 weekly rosters,
2023-25 opening depth, 2020-25 weekly opportunities, and the schedule cutoffs needed
for retrospective tests. Pre-2025 depth retains its weaker Week-1-only label; 2025+
uses the last team timestamp strictly before the opening gameday. All joins are GSIS
only.

`build-role-backtest` evaluates depth-only, prior-share-only, and the frozen universal
blend on 2023-25 Weeks 1-4, 1-8, and 1-18. It uses actual weekly active status only
as an evaluation oracle, isolating conditional role from the separate availability
problem. The blend clearly improves aggregate total-variation error, but resource
analysis selects depth-only for QB and the blend for RB/WR/TE. `build-availability`
then learns population Week-1-status curves,
applies reviewed hard constraints, and redistributes all-affiliated latent roles in
common team-level draws with exact reconciliation.

The September 2 live run resolved all 216 FFC QB/RB/WR/TE identities automatically.
It produced 707 active player-resource rows, 1,056 all-affiliated candidate rows, and
zero reconciliation error. Seven FFC-listed players were non-active; reviewed
first-party facts and rule links are preserved in
`data/research/2026/player_status_evidence.json`. A September 3 review added Trey
Sermon's non-market Atlanta case: official placement before final cutdown plus league
timing rules impose an 18-game hard constraint. The availability model's overall
Brier improvement is not statistically clear, so the output remains a scenario prior,
not a health, efficiency, or fantasy projection. See
[`AVAILABILITY_AND_ROLE_BACKTEST_2026.md`](AVAILABILITY_AND_ROLE_BACKTEST_2026.md).

`build-role-research-audit` now joins a dated, first-party-first evidence registry to
the 365 distinct high-value player/metric exceptions and the separate team-rate
queue. Joins require exact team, GSIS ID, and metric; referenced sources must exist;
parent artifacts are hash-verified; and the schema forbids manual numeric overrides.
Current first-party-first review covers all 365 queued Jets, Colts, Chiefs, Dolphins, Bears,
Browns, Lions, Ravens, Packers, Seahawks, Cardinals, Chargers, Steelers, Titans,
Bengals, Saints, Buccaneers, 49ers, Bills, Commanders, Vikings, Cowboys, Jaguars,
Raiders, Eagles, Patriots, Rams, Giants, Panthers, Texans, Falcons, and Broncos
player/metric exceptions and the Jets inside-5 team-rate case. No queued row remains
unreviewed; 143 reviewed rows remain explicitly inconclusive. See
[`CURRENT_ROLE_RESEARCH_2026.md`](CURRENT_ROLE_RESEARCH_2026.md).

### `OfficialStaffAdapter` and `PlayCallerRegistry` — all 32 implemented

`fetch-official-staff` downloads the current staff page for every club, preserves
the raw HTML, and normalizes titles and offensive responsibility categories. A live
September 2 run produced 953 staff-title rows, including 396 head-coach/offense
rows. The living pages establish names and titles only.

`data/research/2026/playcaller_census.json` separately records the actual 2026
offensive caller for every club with dated evidence. `build-coaching-census` requires
exact agreement with the official snapshot, verifies that the caller is a current
staff member, and publishes joined `teams.csv`, `offensive_staff.csv`, `sources.json`,
and a hash-bearing manifest. The current registry has 21 official-explicit, 10
official-contextual, and one credentialed-explicit assignment; none is inferred from
an OC title. Evidence strength is not style certainty.

The continuity pass compares every current head-coach/offense title against the 2025
official NFL Record & Fact Book. All 396 current rows are classified, and core
responsibilities are retained, changed, or explicitly unavailable. The same official
adapter now preserves and normalizes the 2022, 2023, 2024, and 2025 books for
time-correct historical continuity. Every season validates all 32 teams and head
coaches. Omitted position responsibilities remain explicit—three in 2022 and one in
each of 2023 and 2024—rather than being filled from later knowledge.

The caller fingerprint pass separately joins 75 clean recent full-season
primary-calling episodes to observed 2021-25 style; partial and contaminated
team-seasons remain visible but cannot donate a full-season style. See
[`FORECAST_PIPELINE_2026.md`](FORECAST_PIPELINE_2026.md) for how those histories
become partially pooled style fingerprints and player-opportunity distributions.

### `GoogleNewsEnvironmentDiscoveryAdapter` — all 32 implemented

`fetch-team-news` builds a source-dated discovery queue for every team using the
verified current caller in each query. It preserves the exact RSS payload, normalized
article metadata, topic hints, query, retrieval time, and hashes. Headline tone is
not scored. Every result remains `metadata_only_unreviewed_not_model_evidence` until
the underlying article supports a narrow responsibility, scheme, line, injury, or
role claim. This prevents generic team optimism and syndicated headline duplication
from masquerading as predictive sentiment.

### `CallerFingerprintBuilder` and transition evaluation — mean supported, scores experimental

The fingerprint builder joins caller identity, recent clean primary-calling seasons,
destination team style, staff continuity, and structured official system evidence.
It publishes separate broad-system and exact-rate evidence scores plus every metric
blend. The scores remain `uncalibrated_evidence_score`.

The fixed-weight backtest now spans 2023, 2024, and 2025 targets with time-correct
opening-caller censuses and audited in-window handoffs. The 2022 prior identity table
comes from one factual staff page in an ESPN guide; none of its fantasy projections
or opinions is ingested. The 2025 census transcribes only caller headings from a June
all-team football report, preserves the unresolved Giants assignment, and excludes
that team without hindsight selection.

Caller-aware forecasts improved over league-shrunk persistence in every season and
both windows. The pooled 95% team-season intervals exclude zero, and 90% residual
bands fitted only on 2023-24 covered 93.2% and 91.9% of all 2025 style comparisons.
The mean rule clears its declared historical gate, but the 2023-24-only intervals
cross zero.

A separate diagnostic reconstructs conservative one-year broad-system and exact-style
score bounds for all 96 team-seasons using those official staff books. It fits score
tiers and residual radii on 2023-24 and opens 2025 once. Both score lower bounds have
the wrong held-out rank direction, their Week 6 high tiers cover only 89.0%, and
their tiered bands are wider than global per-metric bands. The machine-readable
decision is `do_not_condition_2026_style_intervals_on_v0_certainty_scores`. This
tests the reconstructible lower bound, not the richer current multi-season score;
changed-caller scheme and destination evidence still require time-correct backfill.
See
[`CALLER_TRANSITION_EVALUATION_2026.md`](CALLER_TRANSITION_EVALUATION_2026.md) and
[`HISTORICAL_CERTAINTY_EVALUATION_2026.md`](HISTORICAL_CERTAINTY_EVALUATION_2026.md),
as well as
[`NFL_ENVIRONMENT_RECOMMENDATION_2026.md`](NFL_ENVIRONMENT_RECOMMENDATION_2026.md).

### `TeamEnvironmentResearch` — KC/SEA/PHI pilot implemented

`data/research/2026/team_environment_pilot.json` contains versioned manual evidence.
It records head coach, coordinator, actual play caller, run/pass-game coordinators,
QB/RB/WR/TE/OL coaches, role continuity, historical team-season anchors, official
sources, and normalized news claims. Living staff pages use an access date with a
null publication date rather than a fabricated timestamp.

The builder separates three outputs: expected style, certainty about style, and
position-level opportunity environment. News is stored as metric-specific evidence
instead of generic positive/negative sentiment. Each claim records source type,
reliability, directness, affected dimensions, confidence effect, and a capped
directional signal. No single camp quote can overpower measured history.

The current certainty rubric is deliberately labeled uncalibrated. It exposes
play-caller verification, continuity, calling experience, HC/system/staff/personnel
continuity, and evidence agreement as separate contributions. The first held-out
historical lower-bound diagnostic failed, so no score may be interpreted as a
probability or used to shrink an interval. A future attempt must reconstruct the
richer score with time-correct evidence and pass a new predeclared holdout gate.

### `FfcAdpAdapter` — implemented

Fantasy Football Calculator is the first credential-free adapter because it lets us
exercise the complete fetch/validate/snapshot boundary without committing to a paid
projection vendor. The API is documented as daily ADP derived from human mock drafts,
with computer selections excluded. Its output is market evidence about when a player
may be selected, not evidence about how many fantasy points that player will score.

Run it with:

```bash
python3 -m fantasy_draft fetch-ffc-adp \
  --season 2026 --teams 10 --scoring ppr
```

The adapter validates response status, requested scoring and team count, schema,
positions, ranges, duplicate source IDs, and non-empty player coverage. It maps
FFC's `DEF` and `PK` positions to canonical `DST` and `K`, then atomically writes the
exact raw JSON, normalized CSV, and a hash-bearing manifest. A timestamp collision
fails rather than overwriting an existing snapshot.

FFC player IDs remain namespaced source IDs. The current role stage maps a source
row to the nflverse identity spine only when canonicalized name, current team, and
position yield one candidate; all other rows enter an explicit review queue. The
same fail-closed contract still must be extended to projection and Yahoo IDs.

### Optional `ProjectionAdapter`

The transparent team-volume and player-role model is the primary forecasting path.
An optional adapter may accept raw projected stats or already-scored fantasy points
as an external benchmark. A hosted commercial adapter must be licensed; otherwise
the user imports a file they are entitled to use. The current public
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

1. **Complete:** establish immutable, validated, hash-bearing source snapshots with
   the FFC ADP and nflverse observed-style adapters.
2. **Pilot complete:** establish the coaching/staff/news evidence schema and
   transparent style-certainty/position-environment builder for KC, SEA, and PHI.
3. **Current staff/caller continuity and recent-history pass complete:** all-team
   responsibility continuity, clean 2021-25 caller anchors, changed-caller system
   evidence, and a metadata-only current-news discovery queue are published.
4. **Multi-season transition gate complete:** fixed 2023-25 cohorts support the
   caller-aware mean, and 2023-24 residual bands have an untouched 2025 coverage
   result. A first one-year historical score reconstruction is also complete and
   rejects score-conditioned interval narrowing; the richer current score remains
   uncalibrated.
5. **Retrospectively evaluated prior complete:** current player IDs, rosters, depth,
   weekly usage, PFR snaps, FFC reconciliation, exact role allocation, 2023-25 role
   baselines, and resource-specific model selection.
6. **Population scenario layer complete:** 2021-25 status-family availability,
   reviewed reserve-rule constraints, all-affiliated role candidates, and exact
   team-week-resource redistribution. Individual medical timing remains out of scope.
7. **Retrospective high-value screen complete:** derive 18 candidate player-allocation
   metrics, correct the FTN primary-read semantics, promote seven conditional shares,
   and publish reconciled 2026 availability scenarios without inventing team volume.
8. **Team high-value volume gate complete:** select models on 2023-24, gate them on
   untouched 2025, reject all team-rate persistence adjustments, calibrate pooled-rate
   bands, and publish reconciled 2026 team/player opportunity counts.
9. **Current-role audit foundation complete:** propagate thin-history reasons, build
   a materiality-ranked source-review queue, and resolve the Jets, Colts, Chiefs,
   Dolphins, Bears, Browns, Lions, Ravens, Packers, Seahawks, Cardinals, Chargers,
   Steelers, Titans, Bengals, Saints, Buccaneers, 49ers, Bills, Commanders, Vikings,
   Cowboys, Jaguars, Raiders, Eagles, Patriots, Rams, Giants, Panthers, Texans, and
   Falcons, and Broncos batches without an unvalidated numeric override. All 365
   player/metric rows are reviewed; 143 remain explicitly inconclusive.
10. **Initial resource-error envelope complete:** backtest historical reference
   forecasts for RB carries and RB/WR/TE targets, preserve the caller-aware point
   means, and expose transferred residual radii plus the WR undercoverage warning.
11. **Direct early-window resource diagnostic complete:** share one denominator-
   consistent transform between production and historical evaluation, add both QB
   resources, and test 2023-24 development against untouched 2025. No resource clears
   the strict mean gate; marginal bands are not a joint interval.
12. Score the corrected v0.4 role, availability, high-value, and evidence-qualified
   rules prospectively during 2026; extend the resource test to Week 18, decompose
   component error, calibrate joint intervals, and obtain a valid all-player route
   source.
13. Backfill time-correct changed-caller scheme/destination evidence and multi-season
   anchors, then attempt a richer score calibration on a newly predeclared holdout.
   Until that passes, keep global metric bands and treat certainty as explanation
   only; extend seasons and test every environment component out of sample.
14. Join environment, roles, health, market ADP, and league settings into a versioned
   canonical snapshot consumed by Python and the browser.
15. Register the Yahoo application, implement server-side OAuth, read actual league
   configuration, and reconcile draft results.

Until prospective availability/role calibration and the remaining efficiency layers
are complete, the demo players and current opportunity priors are research outputs,
not final player draft advice.
