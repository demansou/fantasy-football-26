# 2026 NFL offensive-environment recommendation

Status: evidence-backed research snapshot as of September 3, 2026. The team-level
style estimates are usable as experimental priors. They are not fantasy-point
projections, and their 0-100 certainty values are not probabilities.

## Recommendation

Build 2026 projections bottom-up from real football opportunity, while keeping the
forecast in three layers:

1. **Broad system identity:** which concepts, terminology, and structural family are
   likely to survive.
2. **Exact team rates:** eligible PBP pass/rush plays, official-unit conversions,
   formation/concept rates, and targets by position, represented as ranges rather
   than single-point truth.
3. **Player role and availability:** dropback, rush, carry, and target shares now
   have a 2023-25 retrospective test and exactly reconcile to team pools. Reviewed
   reserve rules and population availability scenarios are implemented. Seven
   high-value conditional-share adjustments also passed a separate retrospective
   gate. Team high-value event counts now combine those shares with holdout-selected
   rates and caller-aware base pools. Historical resource residuals now widen those
   counts as provisional stress envelopes without moving the point estimates. A
   direct early-window six-resource test is complete but promotes no resource.
   All-player routes, Week-18 component and joint interval calibration,
   individualized health modeling, prospective scoring of reviewed role evidence, and
   efficiency remain open.

Do not buy an opaque fantasy projection and treat it as factual. Use official club
evidence for current responsibility, nflverse for measured play style, Pro Football
Reference as a historical audit, and fantasy ADP only as the market price. External
fantasy projections can later serve as blinded benchmarks.

The fixed three-season historical test now supports keeping caller history in the
mean: it beat a league-shrunk team-persistence baseline in both early-season windows
in 2023, 2024, and the untouched 2025 holdout. The pooled team-season intervals are
below zero, so the declared mean-rule gate passes. The evidence is still fragile to
removing the strong 2025 season, and global residual coverage does not turn the
0-100 certainty scores into probabilities. A separate one-year score reconstruction
also fails its untouched-2025 calibration gate: higher scores do not identify lower
error, and score-tiered bands are wider than global bands. New callers should
therefore continue to receive aggressive shrinkage, while even high-scored returning
callers must keep the same global per-metric uncertainty policy.

The separate player-role test is stronger. Across 576 team/resource rooms per
window, an evaluation-only oracle supplies actual weekly active status so the test
measures conditional role rather than injury availability. The frozen depth/history
blend reduced total-variation error versus both depth-only and history-only in Weeks
1-4, 1-8, and 1-18, with every aggregate paired 90% interval below zero. Resource
analysis nevertheless rejects a universal blend: depth alone did better for QB,
while the blend did best for RB/WR/TE. The 2026 role policy now encodes that split
and is frozen for prospective evaluation.

Availability evidence is weaker. Status-family detail improved overall Brier score
by only 0.000178 versus an active/non-active baseline, and its paired 90% interval
crosses zero. Use this output to preserve scenarios and enforce rule-backed minimum
absences—not to claim an individualized return probability.

The high-value test is narrower but actionable. Seven of 18 candidate conditional
shares passed the fixed 2023-25 gate: RB inside-5/inside-10 carries and two-minute
targets, WR end-zone/deep targets, and TE deep/two-minute targets. They improve how a
known team-position event is divided among players. A subsequent team-rate test found
that no team-specific persistence model cleared the untouched 2025 gate. The primary
count layer therefore uses pooled rates with caller-aware carry/target volume; its
development-calibrated rate bands covered 94.6% of 2025 team-metric outcomes in
aggregate. A separate resource reference test covered 93.0% of 2025 team/resource
outcomes in aggregate, but WR targets covered only 84.4% versus 90% nominal. Its
residual radii are therefore carried as explicitly provisional envelopes around the
caller-aware means, not advertised as calibrated 2026 intervals. First reads remain
quarantined, and the public participation field cannot supply all-player routes.

The direct caller-resource follow-up uses one production-aligned transform for QB
dropbacks/rushes, RB carries/targets, and WR/TE targets. It fixes a pre-outcome unit
mismatch between eligible PBP plays and official player-stat opportunities, but it
does not clear a predictive promotion gate. No resource beats shrunken persistence
under every strict criterion; QB rushing is clearly worse in both 2025 early windows,
RB-carry bands cover only 83.3%/86.7%, and all-six marginal-band containment is only
70.0%/66.7%. Keep the corrected v0.4 counts as registered provisional priors, not as
validated point truth. See
[`CALLER_RESOURCE_BACKTEST_2026.md`](CALLER_RESOURCE_BACKTEST_2026.md).

The current-role audit now exposes 365 distinct thin-history or large-adjustment
player/metric cases. All 365 Jets, Colts, Chiefs, Dolphins, Bears,
Browns, Lions, Ravens, Packers, Seahawks, Cardinals, Chargers, Steelers, Titans,
Bengals, Saints, Buccaneers, 49ers, Bills, Commanders, Vikings, Cowboys, Jaguars,
Raiders, Eagles, Patriots, Rams, Giants, Panthers, Texans, Falcons, and Broncos rows
and the one Jets team-rate exception have dated first-party-first review; zero player/metric
cases remain unreviewed and 143 remain explicitly inconclusive. No article or camp
observation has been allowed
to hand-edit the backtested estimates.

## What is now verified

- All 32 current head coaches, primary offensive coordinators, actual offensive play
  callers, and official offensive staffs are joined without inferring the caller
  from an OC title.
- All 396 current head-coach/offensive staff rows are classified against the 2025
  official NFL Record & Fact Book baseline: 174 new to team, 24 returning with a
  changed responsibility, 62 returning in the same responsibility, and 136 returning
  under the same title. Washington's official current page is the sole core-position
  gap because it does not list a tight-ends coach.
- Official 2022, 2023, 2024, and 2025 Record & Fact Books are independently
  preserved and normalized for time-correct staff continuity. All four contain 32
  teams and 32 head coaches; five omitted historical position-group responsibilities
  remain unavailable rather than being inferred.
- Recent 2021-25 full-season caller episodes are separated from non-calling lineage
  and contaminated/partial seasons. Current callers have 75 clean full-season
  anchors; eight have no clean recent full NFL season.
- Current system evidence is structured for every one of the 18 teams whose 2026
  caller differs from 2025. Each claim has narrow metric signals, rationale, and
  source URLs.
- An all-team current-news discovery snapshot contains 800 source-dated leads. They
  remain metadata-only until the underlying article is reviewed and promoted to a
  narrow claim. Generic positive/negative headline sentiment is deliberately absent.

## What the multi-season backtest actually says

The time-correct evaluation uses preseason opening-caller censuses, prior-season
measured nflverse styles as inputs, and Weeks 1-6/1-8 outcomes as targets for 2023,
2024, and 2025. Officially documented in-window caller changes are excluded at the
team-window level. The unresolved 2025 Giants caller is excluded from both windows
without hindsight resolution. No fantasy projection is an input.

Errors are absolute errors divided by the fixed, metric-specific tolerances declared
before the additional seasons were opened. Efficiency and explosive-play outcomes
are excluded, and the caller weights were not retuned.

| Target | Result | Weeks 1-6 | Weeks 1-8 |
|---:|---|---:|---:|
| 2023 | Relative NMAE improvement | 13.3% | 4.7% |
| 2024 | Relative NMAE improvement | 12.5% | 9.2% |
| 2025 holdout | Relative NMAE improvement | 25.8% | 22.2% |
| Pooled | Anchored team-seasons improved | 11 of 13 | 10 of 12 |
| Pooled | Mean paired NMAE delta | -0.150 | -0.111 |
| Pooled | Destination-team-clustered 95% interval | -0.232 to -0.043 | -0.184 to -0.024 |

Finite-sample 90% residual bands fitted per metric on 2023-24 covered 93.2% of
caller-aware 2025 comparisons through Week 6 and 91.9% through Week 8. They were
modestly narrower than the corresponding shrunken-persistence bands. The fixed
caller-aware mean therefore clears its predeclared historical promotion gate.

The mean result has one important robustness caution:

- Removing 2025 makes both pooled intervals cross zero. The conclusion is supported
  under the declared gate but is not yet insensitive to the choice of season.

The separate certainty diagnostic does test whether the evidence ordering predicts
error. It reconstructs conservative one-year lower bounds for 96 team-seasons, fits
tiers on 2023-24, and opens 2025 once. Both broad and exact scores have positive
holdout rank correlations in both windows—the wrong direction. Their Week 6 high
tiers cover only 88.96%, and every score-tiered mean radius is wider than its global
counterpart. Therefore the scorecard remains an explanation and evidence ordering,
not an error scale. It cannot narrow player-resource or fantasy-point intervals, and
the position ordering remains a watch list rather than a draft ranking.

See [`CALLER_TRANSITION_EVALUATION_2026.md`](CALLER_TRANSITION_EVALUATION_2026.md)
for the mean test and
[`HISTORICAL_CERTAINTY_EVALUATION_2026.md`](HISTORICAL_CERTAINTY_EVALUATION_2026.md)
for the score reconstruction, rank test, interval test, and policy.

## Interpreting the 2026 examples

- **Kansas City:** returning caller Andy Reid, five recent full-season anchors, and
  the same team architecture. Broad identity 97.8; exact-rate evidence 91.8. This is
  the strongest documented evidence case, not permission to give Kansas City a
  narrower numeric error band. Scoring and player availability still require
  separate models.
- **Las Vegas:** Klint Kubiak is the 2026 Raiders head coach and caller, bringing the
  wide-zone family measured in his prior offenses. Broad identity 78.4; exact-rate
  evidence 60.0 because the destination staff, players, and sequencing are new.
- **Seattle:** Brian Fleury is a first-time NFL caller, but the club explicitly says
  it intends to retain as much as possible from Kubiak's 2025 foundation. Broad
  identity 77.4; exact-rate evidence 52.1. “Kubiak-family system” is a stronger claim
  than “same exact play mix.”
- **Philadelphia:** Sean Mannion is a first-time caller in a changed coordination
  structure. Broad identity 69.2; exact-rate evidence 45.3. The returning roster and
  established run identity are anchors, but exact sequencing deserves a wide range.

## All-team caller and certainty scorecard

These values are transparent evidence indices from model
`caller-fingerprint-heuristic-v0.1.0`. They rank relative evidence; they do not mean
“91.8% likely” or promise a calibrated error band. The first held-out lower-bound
test did not validate even monotonic error ordering, so differences between scores
must not be translated into different interval widths.

| Team | 2026 caller | Caller status | Clean recent anchors | Broad system | Exact style |
|---|---|---|---:|---:|---:|
| ARI | Mike LaFleur | new/no 2025 primary | 2 | 71.1 | 50.1 |
| ATL | Tommy Rees | new/no 2025 primary | 0 | 67.9 | 36.5 |
| BAL | Declan Doyle | new/no 2025 primary | 0 | 48.2 | 25.4 |
| BUF | Joe Brady | returning | 2 | 89.5 | 79.8 |
| CAR | Brad Idzik | new/no 2025 primary | 0 | 81.9 | 64.2 |
| CHI | Ben Johnson | returning | 4 | 96.7 | 92.7 |
| CIN | Zac Taylor | returning | 5 | 99.8 | 96.2 |
| CLE | Todd Monken | moved 2025 caller | 3 | 79.6 | 63.2 |
| DAL | Brian Schottenheimer | returning | 1 | 91.0 | 81.6 |
| DEN | Davis Webb | new/no 2025 primary | 0 | 79.6 | 59.3 |
| DET | Drew Petzing | moved 2025 caller | 3 | 90.7 | 79.0 |
| GB | Matt LaFleur | returning | 5 | 98.9 | 94.0 |
| HOU | Nick Caley | returning | 1 | 86.1 | 77.4 |
| IND | Shane Steichen | returning | 4 | 97.5 | 93.3 |
| JAX | Liam Coen | returning | 2 | 94.7 | 92.3 |
| KC | Andy Reid | returning | 5 | 97.8 | 91.8 |
| LAC | Mike McDaniel | moved 2025 caller | 4 | 87.8 | 75.1 |
| LAR | Sean McVay | returning | 5 | 99.1 | 93.9 |
| LV | Klint Kubiak | moved 2025 caller | 3 | 78.4 | 60.0 |
| MIA | Bobby Slowik | new/no 2025 primary | 2 | 77.3 | 61.8 |
| MIN | Kevin O'Connell | returning | 4 | 97.3 | 94.5 |
| NE | Josh McDaniels | returning | 3 | 94.4 | 91.4 |
| NO | Kellen Moore | returning | 5 | 99.6 | 95.0 |
| NYG | Matt Nagy | new/no 2025 primary | 0 | 54.6 | 26.1 |
| NYJ | Frank Reich | new/no 2025 primary | 1 | 70.5 | 51.9 |
| PHI | Sean Mannion | new/no 2025 primary | 0 | 69.2 | 45.3 |
| PIT | Mike McCarthy | new/no 2025 primary | 2 | 73.8 | 51.2 |
| SEA | Brian Fleury | new/no 2025 primary | 0 | 77.4 | 52.1 |
| SF | Kyle Shanahan | returning | 5 | 97.5 | 94.6 |
| TB | Zac Robinson | moved 2025 caller | 2 | 87.5 | 77.5 |
| TEN | Brian Daboll | new/no 2025 primary | 2 | 67.4 | 48.8 |
| WAS | David Blough | new/no 2025 primary | 0 | 67.6 | 50.1 |

The clearest exact-style tier is CHI, CIN, GB, IND, JAX, KC, LAR, MIN, NE, NO,
and SF. The widest exact-style ranges belong to BAL, NYG, ATL, PHI, and TEN. High
broad-system but materially lower exact-rate cases—especially CAR, DEN, LV, and
SEA—should preserve the two-score distinction.

## Preliminary position opportunity watch lists

The current coaching/style-only leaders are:

- QB: DAL, KC, HOU, LAR, CIN
- RB: NYJ, SF, TB, BUF, CHI
- WR: DAL, TEN, JAX, LAR, HOU
- TE: KC, DET, DAL, HOU, PIT

These lists answer “which team position pool could receive favorable opportunity if
the style forecast is right?” They do not answer which player owns that opportunity.
They rank the raw point score. The failed historical certainty gate means the 0-100
evidence index neither shrinks the score nor narrows its interval; certainty remains
a separate review flag.
The selected player-role prior now allocates these pools using current roster/depth
and recent opportunity history, then the availability layer redistributes roles in
weekly status scenarios. Seven separate high-value conditional shares are also
available, and the holdout-gated volume layer converts them to team/player opportunity
counts. The model still excludes individualized health, roster quality,
offensive-line quality, opponent adjustments, and efficiency. No player should move
up a draft board from the team list alone. See
[`AVAILABILITY_AND_ROLE_BACKTEST_2026.md`](AVAILABILITY_AND_ROLE_BACKTEST_2026.md)
[`HIGH_VALUE_ROLE_BACKTEST_2026.md`](HIGH_VALUE_ROLE_BACKTEST_2026.md), and
[`HIGH_VALUE_VOLUME_BACKTEST_2026.md`](HIGH_VALUE_VOLUME_BACKTEST_2026.md).

## Source policy

Use sources by what they can actually prove:

- official NFL club pages and the NFL Record & Fact Book: current/historical titles,
  responsibility statements, transactions, and direct quotes;
- nflverse play-by-play and FTN charting: reproducible formation, concept, volume,
  and position-allocation measurements;
- Pro Football Reference: manual audit of team seasons, head coaches, coordinators,
  and conventional totals—not proof of who held the headset;
- reputable preseason caller censuses and credentialed reporting: actual caller
  identity when the official page does not state it;
- current news: discovery leads that become inputs only after article-level review;
- fantasy ADP: acquisition price only; never an NFL-environment feature.

## Next build and promotion gate

Current nflverse player IDs, rosters, latest depth, historical weekly roster/depth/
opportunity inputs, FFC reconciliation, resource-selected role priors, and weekly
availability scenarios are implemented. The seven selected high-value conditional
shares and their team/player opportunity-count priors are also frozen. The next lane is:

1. archive official roster/status evidence before every 2026 game and prospectively
   score the frozen availability, ordinary-role, and high-value-count rules;
2. obtain a valid all-player route source; the Jets inside-5 case and all 365 flagged
   player/metric rows now have dated review with no numeric override;
3. retain reviewed current-role evidence separately from generic camp sentiment and
   calibrate any evidence-to-prior rule before letting it change player shares;
   extend the completed direct caller-resource test to Week 18, decompose component
   error, and calibrate the combined resource/rate/availability/share distribution
   beyond the current provisional residual envelope;
4. extend identity reconciliation to Yahoo and user-owned projection files;
5. backfill time-correct changed-caller scheme/destination evidence and richer
   multi-season anchors, then predeclare a new holdout test for the current score;
6. add more caller-transition seasons without retuning the fixed weights and test
   whether the result remains below zero when any one season is omitted;
7. benchmark the resulting raw-stat distributions against external fantasy
   projections without using those projections as training truth.

The declared caller-history mean gate now passes: three target seasons exist, every
season/window improves at the point-estimate level, and pooled and held-out
team-season intervals exclude zero in both windows. Promote the fixed mean rule as
historically supported, not as season-insensitive truth; the development-only
intervals still cross zero. The first score-conditional held-out test fails, so keep
the 0-100 evidence indices as labels and use global per-metric residual bands until
a richer reconstruction passes a new test.

## Reproducible local artifacts

- current caller/style fingerprints:
  `data/derived/caller_fingerprints/2026/20260902T223905.016436Z/`
- preliminary team-position environments:
  `data/derived/position_environments/2026/20260903T132013.423720Z/`
- time-correct 2023/2024/2025 transition backtests:
  `data/derived/transition_backtest/2023/20260903T121036.850890Z/`,
  `data/derived/transition_backtest/2024/20260903T121036.865266Z/`, and
  `data/derived/transition_backtest/2025/20260903T121036.644188Z/`
- pooled team-season effects and untouched 2025 residual coverage:
  `data/derived/transition_evaluation/2023-2024-2025/20260903T121042.246945Z/`
- official 2022-25 historical staff books:
  `data/raw/official_nfl_record_fact_book/2022/all/20260903T122042.088343Z/`,
  `data/raw/official_nfl_record_fact_book/2023/all/20260903T122042.088410Z/`,
  `data/raw/official_nfl_record_fact_book/2024/all/20260903T122042.088401Z/`, and
  `data/raw/official_nfl_record_fact_book/2025/all/20260902T220406.854474Z/`
- time-correct 2023-25 staff continuity:
  `data/derived/staff_continuity/2023/20260903T123553.259748Z/`,
  `data/derived/staff_continuity/2024/20260903T123553.260134Z/`, and
  `data/derived/staff_continuity/2025/20260903T123553.261221Z/`
- historical score reconstruction and failed promotion decision:
  `data/derived/historical_certainty_evaluation/2023-2024-2025/20260903T123602.490023Z/`
- all-team news discovery queue:
  `data/raw/google_news_nfl_environment/2026/all/20260902T223012.469970Z/`
- current player identity/roster/depth/usage/PFR-snap snapshot:
  `data/raw/nflverse/player_context/2026/20260903T020013.625464Z/`
- selected current role priors, all-affiliated candidates, and exception queues:
  `data/derived/player_roles/2026/20260903T132156.590720Z/`
- historical weekly player-state source:
  `data/raw/nflverse/player_history/20260903T032645.770207Z/`
- 2023-25 time-correct role backtest:
  `data/derived/role_backtest/2023-2024-2025/20260903T033608.665742Z/`
- 5,000-draw weekly availability and role scenarios:
  `data/derived/availability/2026/20260903T132328.323948Z/`
- audited 2021-25 high-value player history:
  `data/derived/high_value_history/2021-2025/20260903T042311.979334Z/`
- corrected, deterministic 2023-25 high-value backtest:
  `data/derived/high_value_backtest/2023-2024-2025/20260903T042515.139734Z/`
- frozen 2026 high-value conditional shares and weekly scenarios:
  `data/derived/high_value_priors/2026/20260903T132359.548967Z/`
- development/untouched-holdout team event-rate backtest:
  `data/derived/high_value_volume_backtest/2023-2024-2025/20260903T044518.028030Z/`
- time-correct resource reference test and provisional residual calibration:
  `data/derived/resource_backtest/2023-2024-2025/20260903T052616.212410Z/`
- direct denominator-consistent six-resource evaluation:
  `data/derived/caller_resource_backtest/2023-2024-2025/20260903T132151.087878Z/`
- reconciled 2026 team and player high-value opportunity counts:
  `data/derived/high_value_volumes/2026/20260903T132405.658654Z/`
- current-role evidence registry, ranked player queue, and reviewed team batches:
  `data/derived/role_research/2026/20260903T132410.884456Z/`
- corrected immutable pre-outcome v0.4 freeze:
  `data/derived/prospective_freeze/2026/20260903T133149.697043Z/`, fingerprint
  `f16a467087044aa6f4f1385ca8bc4eb86c51a287c13dfe1e3dca08349b96f115`

Every snapshot includes input paths or URLs, SHA-256 hashes, model/schema versions,
counts, and limitations. Raw and derived snapshots are intentionally local and
ignored by Git; the source registries, code, tests, and this interpretation are
versioned.
