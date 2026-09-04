# 2026 NFL environment and player-opportunity forecast

## Decision

The primary projection will be built from football volume and player opportunity,
not copied from a fantasy-ranking site. External fantasy projections may be retained
as blinded benchmarks, but they do not define the model.

The output should be a distribution of raw football stats for each player. League
settings convert those stats to fantasy points only at the final step. This lets the
same evidence serve PPR, half-PPR, superflex, and custom-scoring leagues without
quietly changing the football assumptions.

## Four-layer model

### 1. Establish current responsibility

For every club, record:

- head coach, offensive coordinator, actual offensive play caller;
- quarterback, running-back, wide-receiver, tight-end, and offensive-line coaches;
- pass-game and run-game coordinators plus senior offensive assistants;
- each person's 2025 role, 2026 role, and whether responsibility changed;
- dated sources and the exact evidence supporting play-calling authority.

Current titles come from official club pages. Play-calling responsibility requires a
separate official statement or reputable report; an offensive-coordinator title is
never enough. The 2026 current-state census already enforces this rule across all 32
teams.

### 2. Estimate coach and system fingerprints

Use nflverse play-by-play and charting to measure seasons in which each coach
actually controlled the offense. Keep style separate from results:

- style: neutral early-down pass rate and PROE, pace, shotgun/under-center/pistol,
  motion, play action, RPO, screen rate, multi-back usage, target allocation, QB-run
  design, and red-zone tendency;
- results: EPA, success, explosive plays, sacks, turnovers, yards, and touchdowns.

Each coach fingerprint is a partially pooled distribution, not a simple career
average. A one-season caller is pulled strongly toward the relevant league and
scheme-family prior; a long-tenured caller such as Andy Reid or Kyle Shanahan is
allowed to retain a much more specific fingerprint. Recent seasons count more, but
the backtest—not taste—sets the decay rate.

The attribution hierarchy is:

1. seasons as primary NFL play caller;
2. seasons with material design responsibility but no calling authority;
3. scheme-tree experience as a weak prior only;
4. college calling history as supporting evidence, kept distinct from NFL history.

This prevents two bad shortcuts: attributing Sean McVay's results wholesale to a
non-calling Rams coordinator, or assuming every Shanahan-tree coach will reproduce
San Francisco's exact rates.

### 3. Forecast the team opportunity envelope

Forecast distributions for eligible team PBP pass/rush plays, their conversion to
official dropbacks/carries/targets, position allocation, red-zone trips, and
touchdowns. The model combines:

- the returning team's recent measured identity;
- the primary caller's historical fingerprint;
- head-coach constraints and offensive-staff continuity;
- quarterback traits and availability;
- offensive-line and skill-personnel continuity;
- opponent and schedule effects only after the schedule model is validated.

The mixing weights are learned from time-correct historical coaching transitions.
For a new caller, the forecast interval widens and the estimate shrinks toward a
scheme-family or league prior. For a returning veteran caller, the caller/team
history receives more weight. Efficiency is regressed more aggressively than style
because scoring and EPA are less stable and more personnel-dependent.

### 4. Allocate opportunity to players

For each position, forecast a role distribution rather than one hand-entered share:

- QB: start probability, dropbacks, designed runs, scramble rate, sack and turnover
  distributions;
- RB: active-game probability, snap/route share, carries, targets, two-minute work,
  short-yardage and goal-line work;
- WR/TE: routes per dropback, target rate per route, air-yard share, progression-read
  and red-zone share, but only when the source semantics and validation support each;
- all players: availability, role volatility, competition, and depth-chart
  uncertainty.

The calculation chain is inspectable:

```text
team plays
  -> eligible PBP pass plays and PBP rush plays
  -> official QB dropbacks, QB rush opportunities, RB carries, and total targets
     using strictly prior matched-history conversion factors
  -> RB/WR/TE target pools
  -> player target/carry shares
  -> supported team high-value event pools x player conditional shares
  -> catches, yards and touchdowns
  -> league-specific fantasy scoring
```

Monte Carlo sampling carries uncertainty through the whole chain. The useful draft
output is median, downside, upside, and probabilities such as `P(top-12 RB)`, not a
false-precision single point total.

## News without generic sentiment

A positive or negative article is not itself predictive evidence. News is converted
to narrow claims such as:

- caller confirmed or responsibility delegated;
- starting job or rotation explicitly described;
- formation, tempo, concept, or personnel-group change observed;
- injury, recovery, availability, or offensive-line combination changed;
- corroborated beat observation about first-team usage.

Each claim stores source, date, directness, reliability, corroboration, affected
metric, direction, and strength. Official team optimism is weak evidence about
effectiveness, but a direct quote naming the caller or an observed first-team role is
strong evidence about responsibility. News adjustments are capped until historical
tests demonstrate incremental value beyond roster and coaching facts.

## Certainty means expected forecast error

Three different questions must not be collapsed:

1. **Identity certainty:** Do we know who holds the job and calls plays?
2. **Style certainty:** How narrow is the expected range for play style?
3. **Outcome certainty:** How narrow is the range for efficiency, scoring, and player
   production?

The current caller evidence-strength values are transparent rubrics, not
probabilities. A fixed three-season transition test now maps caller continuity and
recent caller history to observed Weeks 1-6 and Weeks 1-8 error. The caller-aware
mean clears its pooled and untouched-holdout gate, although the pooled intervals
cross zero when the strong 2025 season is removed.

A separate diagnostic now reconstructs one-year broad-system and exact-style lower
and upper bounds for 96 team-seasons from source-confirmed opening callers and the
official 2022-25 staff books. Score tiers and residual radii are fitted on 2023-24;
2025 is opened once. Both conservative lower bounds reverse the desired rank
direction on the holdout, the Week 6 high tier covers only 89.0%, and score-tiered
bands are wider than global per-metric bands. The result is a failed promotion gate:
use global residual bands and never narrow numeric uncertainty because a current
evidence score is high.

The diagnostic does not recreate the richer current score. Changed-caller
scheme/destination evidence, multi-season anchors, personnel, and evidence-agreement
components still need comparable time-correct reconstruction before a newly
predeclared holdout test. A later published certainty value should represent
calibrated interval width or expected error rather than subjective confidence.

## How the examples should be treated

- **Kansas City:** Andy Reid is the returning primary caller and offensive architect.
  That supports high style certainty even with Eric Bieniemy returning as OC. It does
  not make scoring or player health certain.
- **Seattle:** Klint Kubiak is now Las Vegas's head coach. Seattle's 2026 caller is
  Brian Fleury, a first-time NFL caller. Retained staff/personnel, shared Shanahan
  lineage, and Seattle's stated intent to preserve the 2025 foundation support high
  confidence in the broad system family, but only medium confidence in exact rates
  and game-day sequencing.
- **Philadelphia:** Sean Mannion is a first-time caller, the pass/run coordination
  structure changed, and the long-tenured offensive-line coach changed. Returning
  players and the club's established run/short-yardage strengths remain anchors, but
  exact 2026 style should have a wide interval.

## Source roles

- nflverse play-by-play, rosters, IDs, and FTN charting: computable historical spine;
- official club staff pages, press conferences, media guides, and transactions:
  current responsibility and first-party statements;
- credentialed local reporting and wire services: independent confirmation and
  observed usage;
- Pro Football Reference: manual historical audit and gap detection, not the bulk
  downloadable feature store;
- fantasy ADP: market price only;
- optional licensed/user-owned fantasy projections: benchmark only.

## Multi-season caller-transition result

The frozen caller-aware blend now has time-correct 2023, 2024, and untouched 2025
target cohorts. It improved normalized MAE over league-shrunk team persistence in
both early-season windows in every target season. Across the clean caller-anchor
cohorts, the pooled paired delta is -0.150 for Weeks 1-6 (11 of 13 team-seasons
improved; destination-team-clustered 95% interval -0.232 to -0.043) and -0.111 for
Weeks 1-8 (10 of 12 improved; interval -0.184 to -0.024).

Residual radii were fitted per model/metric/window on 2023-24 only. On 2025, the
caller-aware 90% bands covered 93.2% of 690 comparisons through Week 6 and 91.9% of
690 through Week 8 while remaining modestly narrower than the persistence bands.
The predeclared historical mean gate passes. The result is not fully season-robust:
the intervals cross zero when the strong 2025 holdout is omitted.

Caller history is therefore a supported mean prior, while caller continuity remains
an explanatory uncertainty feature. The one-year score diagnostic fails to rank
held-out error and makes intervals wider, so the current 0-100 scores remain labels
and cannot condition numeric bands. Full methodology is in
[`CALLER_TRANSITION_EVALUATION_2026.md`](CALLER_TRANSITION_EVALUATION_2026.md) and
[`HISTORICAL_CERTAINTY_EVALUATION_2026.md`](HISTORICAL_CERTAINTY_EVALUATION_2026.md);
the all-team scorecard and source recommendation are in
[`NFL_ENVIRONMENT_RECOMMENDATION_2026.md`](NFL_ENVIRONMENT_RECOMMENDATION_2026.md).

## Player-role and availability result

The player layer now has a distinct 2021-25 weekly roster source and a time-correct
2023-25 role test. Actual weekly active status is used only as an evaluation oracle,
so this test isolates conditional role from the separate availability problem. The
universal depth/history blend beats depth-only and history-only overall in every 4-,
8-, and 18-week window, with paired 90% team-season-cluster intervals below zero.
Resource analysis changes the production rule: current depth alone is used for QB
dropbacks/rushes, while RB carries/targets and WR/TE targets keep the blend. That
retrospectively selected policy is frozen as
`player-role-prior-v0.4.0` for prospective 2026 scoring. Version 0.4 leaves the
selected role shares unchanged but fixes the conversion between eligible PBP plays
and official player-stat opportunities.

Weekly availability scenarios also exist, including rule-backed four-game minimums
and exact role redistribution. Their incremental validation is weak: the overall
status-family Brier delta versus an active/non-active baseline is -0.000178 with a
paired 90% interval from -0.000559 to +0.000197. They are therefore scenario priors,
not player-specific medical forecasts. See
[`AVAILABILITY_AND_ROLE_BACKTEST_2026.md`](AVAILABILITY_AND_ROLE_BACKTEST_2026.md).

The high-value layer now derives 18 candidate allocation metrics and evaluates them
time-correctly on 2023-25. Seven pass a conservative retrospective gate and are
frozen for prospective 2026 testing: RB inside-5/inside-10 carries and two-minute
targets, WR end-zone/deep targets, and TE deep/two-minute targets. The output is only
conditional player share at this stage.

A separate team-rate backtest selects on 2023-24 and applies its promotion gate only
after opening the untouched 2025 season. No team-specific conditional-rate model
passes. The current count layer therefore multiplies a recency-weighted pooled rate
by the caller-aware base resource pool, then allocates it with the frozen player share.
Its development-calibrated 90% rate bands cover 94.6% of 2025 team-metric outcomes,
in aggregate. A separate 2023-24/2025 test now adds historical residual radii around
the RB-carry and RB/WR/TE-target means. Those radii are provisional transfers rather
than direct calibration of the caller-aware model; WR-target holdout coverage was
84.4% versus 90% nominal. The output therefore exposes a stress envelope without
claiming joint interval coverage.

A new direct test passes the frozen caller-aware and shrunken-persistence style
forecasts through the exact production resource transform for QB dropbacks/rushes,
RB carries/targets, and WR/TE targets. It fits only on 2023-24 and opens 2025 once.
No resource clears the strict mean gate. QB rush is significantly worse than the
baseline in both early windows; RB-carry marginal bands cover only 83.3% through Week
6 and 86.7% through Week 8; and all six marginal bands jointly contain only 70.0% and
66.7% of teams. The direct diagnostic therefore does not replace the transferred
full-season envelopes or provide a joint interval. See
[`HIGH_VALUE_VOLUME_BACKTEST_2026.md`](HIGH_VALUE_VOLUME_BACKTEST_2026.md) and
[`RESOURCE_POOL_BACKTEST_2026.md`](RESOURCE_POOL_BACKTEST_2026.md), with the direct
test in [`CALLER_RESOURCE_BACKTEST_2026.md`](CALLER_RESOURCE_BACKTEST_2026.md).

A fail-closed current-role audit now propagates 368 thin-history or large-adjustment
reasons onto 365 distinct player/metric estimates, ranks them by expected-event
materiality, and exact-joins dated source claims. Current first-party-first review covers
all 365 Jets, Colts, Chiefs, Dolphins, Bears, Browns, Lions, Ravens, Packers, Seahawks,
Cardinals, Chargers, Steelers, Titans, Bengals, Saints, Buccaneers, 49ers, Bills,
Commanders, Vikings, Cowboys, Jaguars, Raiders, Eagles, Patriots, Rams, Giants,
Panthers, Texans, Falcons, and Broncos rows plus the Jets team-rate exception; zero
player/metric rows remain unreviewed and 143 remain explicitly inconclusive. Evidence can
change the review status but version 0.1 forbids numeric overrides until an
evidence-to-prior rule clears a time-correct test. See
[`CURRENT_ROLE_RESEARCH_2026.md`](CURRENT_ROLE_RESEARCH_2026.md).

The source audit also demonstrates why schema semantics are part of the model. The
current FTN dictionary maps read code `0` to primary, leaves 2022 primary reads
uncoded, and produces too few events for any first-read feature to pass. The public
participation `route` describes only the primary receiver, so it cannot supply all
routes run. See
[`HIGH_VALUE_ROLE_BACKTEST_2026.md`](HIGH_VALUE_ROLE_BACKTEST_2026.md).

## Acceptance gates before draft advice

The model is not ready to recommend real 2026 players until it has:

1. **Complete:** audited 2025-to-2026 staff continuity and recent primary
   play-calling episodes;
2. **Complete:** added 2023 and 2025 time-correct transition cohorts and evaluated
   development-only residual bands on untouched 2025 outcomes;
3. **Complete:** reconstructed conservative one-year historical certainty-score
   bounds and rejected score-conditioned interval narrowing on untouched 2025;
4. **Complete:** ingested current rosters, depth charts, and explicit player-ID joins;
5. scored the registered pre-outcome resource-selected role rule at Weeks 4, 8, and
   18 and calibrated role interval coverage while preserving reconciled team totals;
6. extended the completed early-window direct caller-resource diagnostic to Week 18,
   decomposed component error, jointly calibrated the resource/rate/availability/role
   distribution, and prospectively scored the seven frozen opportunity-count rules
   (the 365-row current-role review is complete);
7. compared against simple baselines and external projections on held-out seasons;
8. published freshness, missingness, provenance, and uncertainty reports.

Current player identity, roster/depth, 2020-25 opportunity history, PFR snaps,
time-correct role evaluation, all-affiliated latent roles, weekly status scenarios,
historical high-value feature testing, and seven frozen conditional shares are
implemented. Holdout-gated team event rates and reconciled team/player opportunity
counts are also implemented. Provisional base-resource residual envelopes are now
propagated without moving the caller-aware means. Every active baseline and
ordinary/high-value scenario reconciles. The current-role audit contract, all 365
player/metric reviews, and the corrected immutable pre-outcome v0.4 evaluation bundle
are implemented. The original v0.3 identity remains auditable but is superseded
before outcomes because it mixed PBP-play and official player-stat denominators. The
fixed caller-aware style mean clears its separate three-season transition gate, but
no complete resource clears the stricter direct-resource gate. The layer remains a
prior, not a fantasy projection: routes, Week-18 component and joint resource
calibration, efficiency, touchdowns, and
prospectively calibrated availability/role intervals are still missing. The present
team and role certainty rubrics remain explicitly limited: the first historical
score-conditional gate failed, and neither may narrow an interval until a richer
reconstruction and prospective coverage support it.
