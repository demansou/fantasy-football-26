# 2026 availability scenarios and player-role backtest

Data cutoff: September 3, 2026. Historical inputs cover the 2020-25 seasons;
current player, roster, depth, and status evidence is frozen before 2026 Week 1.

## Bottom line

Use the player-role model, with one resource-specific correction. Do not treat the
availability cohort output as an individualized medical forecast.

- **QB dropbacks and QB rush opportunity:** use current depth only. Adding player
  history made early-season error clearly worse in the frozen retrospective test.
- **RB carries/targets and WR/TE targets:** use the depth/history blend. It had the
  lowest aggregate error for all four resources; the result is strongest for both RB
  resources and against depth-only WR/TE forecasts.
- **Known reserve/PUP/transaction rules:** enforce factual minimum absences, including
  a full-season bar when placement timing makes a player ineligible, as hard constraints.
- **Unknown return dates:** retain broad population scenarios and their uncertainty;
  do not convert them into a confident player-specific return week.

This policy is implemented in `player-role-prior-v0.4.0`. The resource selection was
made retrospectively from 2023-25 and is therefore marked
`not_prospectively_validated`. Version 0.4 leaves role shares unchanged and corrects
the conversion from eligible PBP plays to official player-stat opportunities. It is
now frozen for a genuine 2026 evaluation.

## Data and identity boundary

`fetch-nflverse-player-history` preserves the exact nflverse release assets and
normalizes:

- 68,040 regular-season QB/RB/WR/TE weekly roster rows for 2021-25;
- 1,513 opening depth rows for all 32 teams in each of 2023-25;
- 35,515 weekly player-opportunity rows for 2020-25;
- 3,262 team-game schedule rows for 2021-26, including explicit 2026 byes; and
- 53 source-review rows, all caused by missing GSIS IDs rather than a silent name
  match.

Every player join is GSIS-only. For 2023-24, nflverse's historical depth format has
only a Week 1 label. For 2025, the adapter selects each team's last timestamp strictly
before 00:00 UTC on the first regular-season gameday. Results are reported separately
for those temporal-precision regimes.

The source contract follows nflverse's documented [week-level roster
loader](https://github.com/nflverse/nflreadr/blob/main/R/load_rosters_weekly.R),
[depth-chart schema](https://nflreadr.nflverse.com/articles/dictionary_depth_charts.html),
and [update schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html).
The raw release repository is [nflverse-data](https://github.com/nflverse/nflverse-data).

## Availability result

The availability model groups each player's Week 1 status into active 53-man,
practice squad, return-eligible reserve/PUP, generic injured reserve, NFI, or
exempt/suspended families. It estimates Week 1-18 game-active rates with Laplace
smoothing and publishes 90% Wilson sampling intervals. A leave-one-season-out test
trains on four seasons and predicts the fifth. Historical club byes are excluded
from the denominator; current 2026 byes explicitly force player and team opportunity
to zero.

| Validation segment | Status-family Brier | Active/non-active baseline | Delta | Paired 90% interval |
| --- | ---: | ---: | ---: | ---: |
| All 65,549 game-week observations | 0.156921 | 0.157099 | -0.000178 | -0.000559 to +0.000197 |
| Opening non-active only | 0.126764 | 0.127288 | -0.000524 | -0.001648 to +0.000580 |
| Weeks 1-4 | 0.101645 | 0.101849 | -0.000204 | -0.000335 to -0.000073 |
| Weeks 5-8 | 0.153421 | 0.153319 | +0.000102 | -0.000153 to +0.000401 |
| Weeks 9-18 | 0.181851 | 0.182126 | -0.000276 | -0.000902 to +0.000322 |

Lower is better. Status detail provides a small, clear improvement in Weeks 1-4,
but the overall interval includes zero and Weeks 5-8 are directionally worse. That
does not justify statements such as “Player X has a 47% chance to return by Week
18.” The values are population roster-status marginals, not injury-specific medical
probabilities, and the weekly draws are not correlated recovery paths.

The useful part is narrower:

1. it keeps current non-active players in explicit scenarios rather than deleting
   them or assigning a zero season, unless a reviewed transaction rule makes them
   season-ineligible;
2. it makes weak evidence visible through sample size and interval width;
3. it applies only reviewed rule-backed hard constraints; and
4. it redistributes every team resource under common player-availability draws,
   with an explicit unallocated bucket when no current candidate is active.

The 5,000-draw live run produced 13,752 player-week availability rows, 19,008
player-week-resource scenario rows, and 3,456 team-week-resource reconciliations.
Maximum reconciliation error is zero. All 192 bye-week team/resources have a zero
reconciliation target. The largest scheduled-game unallocated draw rate is 9.02%,
which represents roster churn/replacement players missing from the frozen current
candidate set rather than opportunity that disappears on an NFL field.

### Current reviewed examples

These are cohort estimates after applying the rule constraints. Low/high are
sampling intervals around the historical cohort rate, not individual outcome
quantiles.

| Current case | Weeks 1-4 | Week 5 median (90% interval) | Week 9 | Week 18 |
| --- | ---: | ---: | ---: | ---: |
| PUP or IR-designated-return (Charbonnet, Conner, Dell, Tyson) | 0% hard rule | 18.2% (9.3-28.1%) | 36.2% (24.9-47.8%) | 47.1% (35.7-58.5%) |
| Generic IR RB (Pacheco) | 0% hard rule | 4.5% (1.0-8.9%) | 12.5% (6.2-19.6%) | 13.0% (6.9-20.0%) |
| Pre-cutdown IR, season-ineligible (Sermon) | 0% hard rule | 0% hard rule | 0% hard rule | 0% hard rule |
| Practice-squad RB (Blue) | no rule-backed minimum | 16.2% (11.9-20.8%) | 25.0% (19.7-30.5%) | 28.4% (23.2-33.8%) |
| Exempt/suspended fallback RB (Jacobs) | no fixed return minimum | 13.7% (10.4-17.2%) | 22.1% (18.0-26.4%) | 26.3% (22.1-30.6%) |

The approved 2026 PUP change allows a practice window after the second game but
does not permit activation before four games have elapsed; the underlying proposal
retains that activation boundary. See the [approved 2026 changes](https://nfl-ops-prod-umbraco-author.azurewebsites.net/news-updates/the-game/approved-2026-playing-rules-bylaws-and-resolutions/)
and [proposal text](https://operations.nfl.com/media/dxfj3uak/2026-playing-rules-bylaw-and-resolution-proposals.pdf).
The league's reserve-return explanation likewise states the four-game minimum for
eligible injured-reserve returns ([NFL.com](https://www.nfl.com/news/players-now-eligible-to-return-from-injured-reserve-after-four-games)).
The separate [NFL roster FAQ](https://www.nfl.com/news/nfl-training-camp-roster-faqs-defining-injured-reserve-pup-list-nfi-and-more)
states that players placed on injured reserve before the post-cutdown waiver period
are ineligible to return. The [2026 league calendar](https://operations.nfl.com/calendar-events/nfl-important-dates)
limits the special pre-season return designation to at most two players placed on an
applicable reserve list during the August 30 final-reduction business day. Atlanta
placed [Trey Sermon on injured reserve on August 19](https://www.atlantafalcons.com/news/rb-trey-sermon-injured-reserve),
so the 18-week zero is a roster-rule fact, not a medical recovery estimate.

## Role-share result

For each 2023-25 target season, the role test freezes the player universe to Week 1
`ACT`/`INA` roster rows and uses only the prior three seasons. To isolate conditional
role from availability, evaluation supplies actual weekly `ACT` status as an oracle,
renormalizes each frozen role prior only among that week's active opening candidates,
and weights the weekly allocation by the observed team resource pool. Any later
entrant remains in the scoring set with a forecast of zero. If a positive pool has no
active opening candidate, forecast mass goes to an explicit `__UNALLOCATED__` row and
counts as error. This oracle is an evaluation device, not an input available to a
prospective forecast. Total-variation distance is the primary error: zero is perfect;
one means the predicted and actual role distributions do not overlap.

| Window | Universal blend | Depth only | Prior share only | Blend vs depth, paired 90% interval | Blend top-role accuracy |
| --- | ---: | ---: | ---: | ---: | ---: |
| Weeks 1-4 | 0.175105 | 0.190258 | 0.254084 | -0.018197 to -0.012185 | 85.4% |
| Weeks 1-8 | 0.178610 | 0.195256 | 0.262015 | -0.019672 to -0.013666 | 84.4% |
| Weeks 1-18 | 0.192847 | 0.209370 | 0.282091 | -0.019955 to -0.013179 | 78.5% |

There are 576 team/resource rooms per model in each window, clustered into 96
team-seasons for the paired bootstrap. The blend beats both baselines with intervals
below zero in all three windows. It also beats depth in all three target seasons and
in the genuinely timestamped 2025 subset. Opening-roster candidate coverage declines
from 98.8% through Week 4 to 94.1% through Week 18, correctly exposing the cost of
in-season roster churn. Mean unallocated forecast mass for the blend rises from 0.14%
to 0.63% over those windows; the worst individual room reaches 80.5%, so missing
opening-roster coverage is preserved rather than silently redistributed away.

Aggregation hides a real positional difference:

| Resource | Depth only | Prior share only | Universal blend | Frozen 2026 choice |
| --- | ---: | ---: | ---: | --- |
| QB dropbacks | **0.095567** | 0.266630 | 0.102671 | Depth only |
| QB rush opportunities | **0.104442** | 0.278065 | 0.110767 | Depth only |
| RB carries | 0.220154 | 0.256519 | **0.201680** | Blend |
| RB targets | 0.251453 | 0.293881 | **0.232301** | Blend |
| WR targets | 0.271484 | 0.249280 | **0.223029** | Blend |
| TE targets | 0.246667 | 0.252006 | **0.222674** | Blend |

Values average the three windows. For both RB resources, the blend's paired 90%
interval beats both alternatives in all three windows. For WR targets, it clearly
beats depth in all windows; versus history alone, Week 1-4 is uncertain and Weeks
1-8 and 1-18 are clear wins. For TE targets it clearly beats depth in all windows;
the history-only comparison is uncertain through Week 8 and a clear blend win by
Week 18. For QB, depth is the cleaner conditional-role model and keeps future
injury/backup availability separate.

## What the 2026 pipeline now emits

The selected current role snapshot has 707 active player-resource priors and 192
exactly reconciled team/resource rooms. It also has an all-affiliated latent candidate
table. Removing all non-active candidates exactly reproduces the active baseline;
when an availability draw activates a reserve player, the room is renormalized without
inventing or deleting team opportunity.

For example, Kansas City's depth-only QB-dropback baseline assigns Patrick Mahomes
92.17%, Justin Fields 6.45%, and Garrett Nussmeier 1.38%, conditional on the drawn
active set. Seattle's active-only RB-carry baseline remains Jadarian Price 49.80%,
Emanuel Wilson 23.98%, George Holani 23.47%, and Brady Russell 2.75%. Charbonnet is
zero by rule through Week 4; from Week 5 onward he enters only on draws in which the
status-cohort scenario marks him active.

These are still opportunity shares, not fantasy points. A subsequent backtest now
supports seven separate high-value conditional-share priors, including RB
inside-5/inside-10 work and WR/TE deep or two-minute roles. First reads were corrected
to the current source dictionary and rejected, and routes remain unavailable. Team
high-value opportunity counts are now modeled with pooled conditional rates selected
on an untouched 2025 gate and caller-aware base resource pools. A historical resource
test now contributes provisional carry/target residual envelopes, but does not
calibrate the complete caller-aware mean or the joint player interval. A direct
six-resource early-window diagnostic is now complete; it promotes no resource and
finds RB-carry undercoverage, so it does not replace those full-season envelopes.
Catch/yard
efficiency, touchdowns, opponent effects, and league scoring remain unmodeled. The
role low/high bounds also remain structural heuristics rather than calibrated coverage
intervals.
See [`HIGH_VALUE_ROLE_BACKTEST_2026.md`](HIGH_VALUE_ROLE_BACKTEST_2026.md) and
[`HIGH_VALUE_VOLUME_BACKTEST_2026.md`](HIGH_VALUE_VOLUME_BACKTEST_2026.md), plus
[`RESOURCE_POOL_BACKTEST_2026.md`](RESOURCE_POOL_BACKTEST_2026.md).

## Reproducible artifacts

- historical player-state snapshot:
  `data/raw/nflverse/player_history/20260903T032645.770207Z/`
- availability-conditioned role backtest:
  `data/derived/role_backtest/2023-2024-2025/20260903T033608.665742Z/`
- selected 2026 role prior:
  `data/derived/player_roles/2026/20260903T132156.590720Z/`
- 5,000-draw availability and role scenarios:
  `data/derived/availability/2026/20260903T132328.323948Z/`
- frozen high-value conditional shares and availability scenarios:
  `data/derived/high_value_priors/2026/20260903T132359.548967Z/`
- holdout-gated team rate model and calibration:
  `data/derived/high_value_volume_backtest/2023-2024-2025/20260903T044518.028030Z/`
- resource reference backtest and provisional residual radii:
  `data/derived/resource_backtest/2023-2024-2025/20260903T052616.212410Z/`
- reconciled team/player high-value opportunity counts:
  `data/derived/high_value_volumes/2026/20260903T132405.658654Z/`
- current-role evidence audit and unresolved queue:
  `data/derived/role_research/2026/20260903T132410.884456Z/`
- direct production-aligned caller-resource diagnostic:
  `data/derived/caller_resource_backtest/2023-2024-2025/20260903T132151.087878Z/`

Every directory includes input paths, SHA-256 hashes, schema/model versions,
methodology, reconciliation checks, and limitations. Raw/derived snapshots are local
and ignored by Git; the source adapters, model code, tests, evidence, and this report
are versioned.

## Next promotion gate

Score frozen `player-role-prior-v0.4.0` and the seven selected high-value p24
adjustments during 2026. Archive each weekly roster, depth, role, and official
status update before games, then score probability calibration, ordinary-role TV
error, high-value TV error, and interval coverage without retuning. In parallel,
extend the direct caller-aware resource diagnostic to Week 18 with component and
joint calibration, and obtain an all-route source. Only after those gates should the
model generate catches, yards, touchdowns, and league-specific fantasy-point
distributions.
