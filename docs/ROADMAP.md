# Roadmap

## Phase 1 — Offline decision core (current)

- [x] Configurable roster, flex, scoring, and position limits.
- [x] Raw-stat scoring and fantasy-points override.
- [x] Flex-aware replacement levels and VORP.
- [x] Roster need, scarcity, ADP timing, context, risk, and construction signals.
- [x] Separate normalized team profiles and position-specific WR/RB/QB/TE context.
- [x] Explicit low-variance QB preference.
- [x] Live weight adaptation for draft phase, roster need, snake turns, and runs.
- [x] Explainable table/JSON output.
- [x] Synthetic end-to-end example and unit tests.

Exit criterion: one command deterministically recommends from a known draft state,
and every material score component is inspectable.

## Phase 2 — Trustworthy 2026 analytics pipeline

- [x] Select an initial source stack after reviewing access, methodology, freshness,
  and redistribution constraints.
- [x] Implement credential-free Fantasy Football Calculator ADP ingestion with exact
  raw responses, canonical CSV output, atomic publication, schema fingerprints,
  SHA-256 hashes, retrieval/source windows, and coverage counts.
- [x] Implement 2021-25 nflverse observed-style ingestion for all 32 teams per year,
  including roster-ID target attribution and 2022-25 FTN formation/concept charting.
- [x] Build and live-verify a source-backed KC/SEA/PHI staff, play-caller, coaching
  continuity, structured-news, style-certainty, and position-environment pilot.
- [x] Snapshot the current official staffs and independently source actual offensive
  play callers for all 32 teams; exact-join all 953 titles and 396 head-coach/offense
  records without inferring callers from coordinator titles.
- [x] Audit every 2025-to-2026 offensive position-coach and responsibility change;
  classify all 396 current head-coach/offense rows and expose the one official-page
  core-role gap instead of filling it speculatively.
- [x] Build recent 2021-25 histories for every current caller that distinguish clean
  full-season primary-calling anchors from partial/contaminated seasons and
  non-calling system-tree evidence.
- [ ] Extend current-caller histories before 2021 where material and add week-level
  style attribution for audited partial calling episodes.
- [x] Run the first time-correct transition test against 2024 Weeks 1-6/1-8, with
  frozen metric tolerances and in-window caller-change exclusions.
- [x] Add 2023 and 2025 time-correct target seasons to the fixed 2024 caller test;
  pool team-season effects and open 2025 only after fitting 2023-24 residual bands.
  The caller-aware mean clears its historical promotion gate and aggregate held-out
  bands cover at least 90%, with a documented leave-2025-out robustness caveat.
- [ ] Reconstruct time-correct historical broad-system and exact-style evidence
  scores, then test whether each score predicts held-out error or required interval
  width. Global residual coverage does not calibrate the current 0-100 indices.
  - [x] Reconstruct conservative one-year lower/upper score bounds for 2023-25 from
    source-confirmed callers and official staff books. On the untouched 2025 holdout,
    both lower bounds fail the rank-direction gate, the Week 6 high tier covers only
    89.0%, and score-tiered bands are wider than global per-metric bands. Do not
    condition 2026 numeric uncertainty on these scores.
  - [ ] Backfill time-correct changed-caller scheme/destination evidence and richer
    multi-season anchors, add target seasons, and predeclare another held-out test
    before attempting to calibrate the current 2026 score.
- [x] Build an all-team current-news discovery queue that preserves exact RSS,
  source/date metadata, topic hints, and review status without using headline tone
  as sentiment evidence.
- [x] Add nflverse player-ID, current roster, current depth-chart, 2023-25 weekly
  usage, and Pro Football Reference snap-count ingestion.
- [x] Build explicit FFC-to-nflverse player reconciliation with a review queue for
  every ambiguous, stale-team, inactive, or unmatched candidate.
- [ ] Extend ID reconciliation to user projections and eventually Yahoo; never
  silently resolve ambiguous name matches.
- [x] Build preliminary bottom-up team QB/RB/WR/TE opportunity pools from forecast
  eligible PBP pass/rush plays, matched-history conversions to official dropbacks,
  carries, and targets, position allocation, and passing style, with uncertainty
  shrinkage and an explicit team-only scope warning.
- [x] Build first-pass current-active QB/RB/WR/TE role-share ranges and reconcile all
  median allocations exactly to the 192 team/resource opportunity pools; keep FFC
  as market metadata rather than ground truth.
- [x] Backtest preseason depth/history role priors on 2023-25 time-correct seasons
  against depth-only and history-only baselines; condition the evaluation on actual
  weekly active status, retain later roster entrants as zero-share forecasts, and
  report team-season-cluster uncertainty.
- [x] Model weekly availability/return scenarios from 2021-25 roster-status cohorts,
  enforce reviewed rule-backed minimum absences including season-ineligible
  transaction timing, and reconcile every simulated team resource with an explicit
  unallocated bucket.
- [x] Publish a tamper-evident preseason freeze of the resource-selected role,
  availability, team-environment, and high-value count rules before the first 2026
  game. The authoritative v0.4 bundle binds its scoring contract, explicit pre-outcome
  denominator correction, and every parent/output hash under fingerprint
  `f16a467087044aa6f4f1385ca8bc4eb86c51a287c13dfe1e3dca08349b96f115`.
  The original v0.3 identity is retained for audit but superseded before outcomes.
- [ ] Score that registered forecast at Weeks 4, 8, and 18, then calibrate role and
  availability interval coverage without retrospective retuning.
- [x] Derive GSIS-keyed deep/end-zone/two-minute/goal-line/read usage from preserved
  nflverse assets, correct structural read-code missingness, run a time-correct
  2023-25 feature test, and freeze the seven passing conditional-share signals into
  availability-adjusted 2026 priors.
- [x] Backtest team high-value rates on 2023-24 development and an untouched 2025
  holdout, reject every unsupported team-history adjustment, calibrate conditional-rate
  bands, and publish reconciled 2026 team/player event-count priors.
- [x] Build a fail-closed current-role evidence registry and ranked audit queue, carry
  row-level thin-history reasons into the final counts, and source-review all 365 Jets,
  Colts, Chiefs, Dolphins, Bears, Browns, Lions, Ravens, Packers, Seahawks,
  Cardinals, Chargers, Steelers, Titans, Bengals, Saints, Buccaneers, 49ers, Bills,
  Commanders, Vikings, Cowboys, Jaguars, Raiders, Eagles, Patriots, Rams, Giants,
  Panthers, Texans, Falcons, and Broncos
  player/metric cases plus the Jets inside-5 team-rate exception without a manual
  numeric override.
- [ ] Obtain a valid all-route source and keep first reads quarantined until the upstream
  code semantics and a sufficient time-correct sample are confirmed.
- [x] Build a time-correct 2023-24 development/2025 holdout reference test for the
  four carry/target resources feeding high-value counts, publish per-resource residual
  radii, and propagate them as explicitly provisional stress envelopes without moving
  the caller-aware point estimates.
- [ ] Finish caller-aware resource validation and jointly calibrate the final count
  intervals; the current transferred full-season radii are not direct 2026 coverage.
  - [x] Share one denominator-consistent transform between historical and production
    builds; directly test QB dropbacks/rush opportunities, RB carries/targets, and
    WR/TE targets through Weeks 6 and 8 on 2023-24 development and untouched 2025.
    No resource clears the strict mean gate; QB rush is clearly worse, RB carries
    undercovers in both windows, and six-resource simultaneous coverage is 70.0%/66.7%.
  - [ ] Decompose uncertainty in plays, pass/run split, QB run components, and position
    target shares; add Week 18 and calibrate the combined resource/rate/availability/
    role distribution rather than treating marginal bands as joint coverage.
- [x] Join the current team, player, availability, high-value, and reviewed-evidence
  families into one dated, hash-verified Python snapshot with a pinned identity.
- [x] Make the browser consume the pinned production snapshot rather than synthetic
  player data. The 267-player draft board joins verified FFC IDs to the frozen
  QB/RB/WR/TE opportunity, high-value, role-evidence, and team-environment artifacts;
  K/DST remain explicitly market-only.
- [x] Add freshness checks that fail closed for stale or incomplete draft-day data.
  The web-ranking build verifies both manifests and hashes, exact reviewed position
  coverage, duplicate IDs, and a maximum four-day ADP source-window age.
- [ ] Treat injury, offensive-line, pace, coaching, and team-environment signals as
  experimental until their independent residual value is demonstrated.

Exit criterion: a reproducible command creates a dated 2026 NFL-environment and
player-opportunity snapshot with calibrated uncertainty, coverage and provenance
reports, without manual spreadsheet cleanup.

## Phase 3 — Yahoo league integration

- Register a local Yahoo application and implement the authorization-code flow.
- Store secrets/tokens outside Git with restrictive local permissions.
- Import the actual league's scoring, roster positions, teams, keepers, and draft
  results through the official API where supported.
- Keep a manual CSV/JSON fallback so draft-day recommendations do not depend on one
  remote service.

Exit criterion: a read-only sync reproduces Yahoo league settings and current draft
state, and discrepancies against a manual export are surfaced.

## Phase 4 — Draft simulation and calibration

- Model selection probability from Yahoo ADP, rank, opponent rosters, and pick turn.
- Monte Carlo the rest of the draft for every candidate at the current pick.
- Optimize expected final starting lineup and bench option value.
- Backtest with time-correct historical snapshots; tune weights only on training
  seasons and publish validation metrics.
- Add keeper, superflex, auction, and traded-pick support as required by the league.

Exit criterion: the simulator beats static ADP and static projection baselines on
held-out historical drafts under predeclared metrics.

## Phase 5 — Live draft board

- Fast local web UI with available players, roster grid, tiers, next-turn survival
  probability, and recommendation explanations.
  - [x] Ship the available-player, roster, tier, and explanation workflow plus an
    evidence-bounded, sample-weighted next-turn market estimate from observed ADP
    range and spread. Adjust it for the actual starter/flex needs of every opponent
    selecting before the next turn and keep it labeled `est.` until pick-level
    outcomes support empirical calibration.
  - [x] Port supported Python decision categories into the opportunity-based browser
    rank: lineup fit, positional drop-off, ADP urgency, live runs, and construction
    penalties. Do not port fantasy-point VORP into a model that intentionally has no
    point projections.
  - [x] Expose opponent roster intelligence through league-board needs, before-turn
    demand pressure, and per-player availability explanations without simulating the
    remainder of the draft.
  - [x] Add a browser-persisted target queue that follows live recommendation order,
    identifies tier exhaustion risk before the next turn, and names the next
    same-position fallback.
- One-click draft event entry plus Yahoo refresh/reconciliation.
  - [x] Add a free, no-token, once-daily Sleeper injury/roster-status refresh with
    local caching, complete current skill-player reconciliation, visible source age,
    and no automatic rank mutation. Yahoo draft-result reconciliation remains open.
  - [x] Add a league-wide snake-draft matrix keyed by custom team names, with
    current-pick highlighting and non-destructive correction of any completed pick.
- [x] Draft-day health panel for ranking/injury age, browser-save state, offline
  fallback readiness, backup import/export, and reversible player avoidance.
- Precompute expensive simulations so a new recommendation arrives within seconds.

Exit criterion: complete mock drafts can be run without editing files or touching a
terminal, including loss of network access mid-draft.

## Phase 6 — In-season team optimizer

- Weekly lineup optimization using opponent, weather, injury, and role uncertainty.
- Waiver prioritization by expected lineup gain and rest-of-season option value.
- Trade evaluation with positional replacement effects and playoff schedules.
- Transparent alerts for material news or projection changes.

Exit criterion: every recommendation shows the expected improvement, uncertainty,
data timestamp, and relevant constraints.

## League facts needed before Phase 2 output is actionable

- Yahoo league identifier or a settings export.
- Team count and exact scoring modifiers.
- Roster slots, flex/superflex rules, bench/IR, and position caps.
- Snake, auction, or salary-cap format; draft slot and draft date/time.
- Keepers and pick costs, if any.
- Preferred risk posture and whether correlated stacks should be valued.
