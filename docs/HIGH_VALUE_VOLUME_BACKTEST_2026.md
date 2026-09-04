# Team high-value event-volume backtest and 2026 opportunity counts

Data cutoff: September 3, 2026.

## Decision

Use the recency-weighted **league conditional event rate** for all seven supported
high-value metrics. Do not apply a team-specific historical-rate adjustment yet.
Team differences enter through the existing caller-aware 2026 RB-carry and
position-target pools:

> median team event pool = caller-aware base resource mean x holdout-selected event rate

The player layer then multiplies that pool by the separately backtested conditional
share and applies the existing weekly availability scenarios. This creates named
opportunity-count priors, not catches, yards, touchdowns, efficiency, or fantasy
points. Low/high scenarios now also carry a separate, provisional base-resource
residual radius; the median remains unchanged.

## Why the pooled rate won

The test uses the seven metrics already promoted by the player-share backtest. For
each target season and team, it predicts a high-value rate conditional on the
relevant base resource:

- RB inside-5/inside-10 carries per RB carry;
- RB two-minute targets per RB target;
- WR end-zone/deep targets per WR target; and
- TE deep/two-minute targets per TE target.

The candidate models are a time-correct recency-weighted league rate, a raw team
rate, and team rates beta-shrunk toward the league by 25, 50, 100, or 200 base
opportunities. The 2023-24 seasons are the development sample. The lowest-error
team candidate for each metric is then evaluated against the league baseline on the
untouched 2025 season at Weeks 4, 8, and 18.

Actual target-window carries or targets are an evaluation-only oracle. This isolates
the conditional event rate from the separate question of forecasting the base
resource pool. Paired 90% intervals resample team-season clusters, using an
independent deterministic seed for every segment, metric, window, and challenger.

The promotion gate requires a candidate to improve all three development windows,
improve all three holdout windows, produce at least two clear holdout interval wins,
and have no clear holdout loss. No team-specific metric passed.

Across all metrics, `team_rate_p200` was the best development candidate, lowering
mean absolute rate error from 0.037062 to 0.036447. That small gain reversed on the
untouched season:

| 2025 window | p200 delta vs league | Paired 90% interval | Decision |
| ---: | ---: | ---: | --- |
| Week 4 | +0.000042 | -0.001597 to +0.001635 | uncertain, slightly worse point estimate |
| Week 8 | +0.000875 | -0.000845 to +0.002665 | uncertain, worse point estimate |
| Week 18 | +0.001190 | -0.000479 to +0.002853 | uncertain, worse point estimate |

Metric results were mixed rather than uniformly anti-persistent. At Week 18, the
team candidate point estimate improved RB inside-5, RB inside-10, RB two-minute, and
WR end-zone rates, but every interval crossed zero. TE deep and two-minute rates
worsened. WR deep persistence clearly worsened in all three holdout windows; at Week
18 its error delta was +0.006154 with a 90% interval of +0.000849 to +0.011179.

The evidence therefore supports pooling, not a claim that every offense has the same
high-value environment. Offenses still differ in forecast carry/target volume. What
is rejected is the extra assertion that a team's noisy past conditional rate should
move the primary 2026 estimate after that base volume is known.

## Rate uncertainty

For each metric, a 90% split-conformal absolute-error radius is calibrated only from
the 2023-24 Week-18 forecasts and evaluated once on 2025. These are retrospective
conditional-rate bands, not complete player projection intervals.

| Metric | 2026 rate | Rate band | 2025 coverage |
| --- | ---: | ---: | ---: |
| RB inside-5 carries | 5.19% | 2.65%-7.72% | 28/32 = 87.5% |
| RB inside-10 carries | 8.95% | 4.68%-13.22% | 32/32 = 100.0% |
| RB two-minute targets | 13.63% | 5.50%-21.76% | 29/32 = 90.6% |
| WR end-zone targets | 8.31% | 3.95%-12.66% | 32/32 = 100.0% |
| WR deep targets | 28.87% | 22.11%-35.64% | 30/32 = 93.8% |
| TE deep targets | 13.62% | 5.16%-22.09% | 31/32 = 96.9% |
| TE two-minute targets | 14.11% | 6.72%-21.49% | 30/32 = 93.8% |

Aggregate holdout coverage is 212 of 224 team-metric outcomes, or 94.6%. The
inside-5 band is the only metric below its nominal 90% target, at 87.5%. This is one
held-out season, so the bands stay explicitly provisional.

## Base-resource uncertainty

A separate time-correct test now measures error in historical reference forecasts for
the four base resources consumed here: RB carries and RB/WR/TE targets. It selects on
2023-24 and opens 2025 only after freezing the gate. No historical team reference
cleared the full promotion rule, so none replaces the caller-aware point mean.

Development-derived per-game residual radii are transferred around that mean as
stress envelopes. Their 2025 coverage was 96.9% for RB carries, 93.8% for RB targets,
84.4% for WR targets, and 96.9% for TE targets, versus 90% nominal. The WR result is
explicitly below target. Moreover, these errors were calibrated around a simpler
historical reference—not the caller-aware mean itself—so even the other three are
provisional rather than direct 2026 coverage claims. See
[`RESOURCE_POOL_BACKTEST_2026.md`](RESOURCE_POOL_BACKTEST_2026.md).

A subsequent direct diagnostic now reconstructs the actual caller-aware resource
builder for six resources through Weeks 6 and 8. Production and evaluation share one
conversion from eligible PBP pass/rush plays to official QB dropbacks, player targets,
and RB carries. No resource clears the strict mean gate; QB rush is clearly worse
than shrunken persistence, RB carries undercovers in both windows, and marginal bands
do not give joint coverage. Because it lacks Week 18 and a joint calibration, it does
not replace these transferred full-season stress radii. See
[`CALLER_RESOURCE_BACKTEST_2026.md`](CALLER_RESOURCE_BACKTEST_2026.md).

The published low/high high-value pools multiply the low/high base-resource scenario
by the low/high conditional-rate scenario. Player outputs then add marginal
availability/share scenarios. These endpoints are intentionally conservative stress
combinations, not a jointly calibrated interval.

## 2026 outputs

The production transform uses only the selected point means. It publishes failed
team candidates and raw team rates as diagnostics, never hidden overrides. The v0.4
pre-outcome definition correction lowers target-based event counts by about 10.4%
and carry-based event counts by about 2.37% relative to v0.3; the conditional player
shares and evidence decisions are unchanged. All corrected player/team/week medians
reconcile exactly.

| Check | Result |
| --- | ---: |
| Team/metric event pools | 224 = 32 teams x 7 metrics |
| Player/metric opportunity priors | 1,502 |
| Weekly player/metric estimates | 27,036 |
| Weekly reconciliations | 4,032 = 32 x 7 x 18 |
| Maximum reconciliation error | 0 |
| Team-rate research flags | 1 |
| Player/metric rows requiring current-role review | 365 |

The sole team-rate flag is the Jets' RB inside-5 rate. Their three-season
recency-weighted raw rate is 2.01%, versus the 5.19% pooled primary rate; the 3.18
percentage-point difference exceeds the 2.53-point calibration radius. That is a
research prompt about current caller, quarterback, personnel, and scoring context—not
permission to restore a team-history adjustment that failed the holdout gate.

The exception has now been source-reviewed. Frank Reich is confirmed as the current
caller, and official roster/depth reporting separates the primary Hall-Allen-Davis
rotation from return specialist Kene Nwangwu and fullback Andrew Beck. None of that
evidence supplies a validated 2026 team goal-line rate, so the pooled primary rate is
retained with zero manual adjustment. See
[`CURRENT_ROLE_RESEARCH_2026.md`](CURRENT_ROLE_RESEARCH_2026.md).

The highest current availability-adjusted opportunity-count priors include:

| Metric | Three highest current priors |
| --- | --- |
| RB inside-5 carries | Ashton Jeanty 13.5; Derrick Henry 12.4; Javonte Williams 11.6 |
| RB inside-10 carries | Ashton Jeanty 23.0; Derrick Henry 20.5; Bijan Robinson 19.8 |
| RB two-minute targets | Christian McCaffrey 8.9; Bijan Robinson 8.1; Jahmyr Gibbs 8.1 |
| WR end-zone targets | Nico Collins 11.4; Rome Odunze 11.3; Chris Olave 10.8 |
| WR deep targets | Chris Olave 38.0; Alec Pierce 37.3; Rome Odunze 36.7 |
| TE deep targets | Sam LaPorta 14.8; Travis Kelce 12.1; Trey McBride 10.9 |
| TE two-minute targets | Sam LaPorta 16.1; Travis Kelce 12.9; Jake Ferguson 12.0 |

These are model outputs to audit, not draft recommendations. A player can still be
materially wrong because the current role, availability, or team base resource pool
is wrong; none of these counts says how efficiently the opportunity becomes fantasy
production.

## Reproducible artifacts

- development/holdout team-rate backtest and calibration:
  `data/derived/high_value_volume_backtest/2023-2024-2025/20260903T044518.028030Z/`
- development/holdout resource reference test and provisional residual radii:
  `data/derived/resource_backtest/2023-2024-2025/20260903T052616.212410Z/`
- direct production-aligned six-resource diagnostic:
  `data/derived/caller_resource_backtest/2023-2024-2025/20260903T132151.087878Z/`
- 2026 team pools, player counts, and weekly availability scenarios:
  `data/derived/high_value_volumes/2026/20260903T132405.658654Z/`
- joined current-role evidence audit:
  `data/derived/role_research/2026/20260903T132410.884456Z/`

All snapshots contain exact parent paths, SHA-256 input/output hashes, schema/model
versions, scored alternatives, reconciliation checks, and limitations.

## Recommendation for the next iteration

1. **Completed foundation:** the Jets inside-5 exception and all 365 flagged Jets, Colts,
   Chiefs, Dolphins, Bears, Browns, Lions, Ravens, Packers, Seahawks, Cardinals,
   Chargers, Steelers, Titans, Bengals, Saints, Buccaneers, 49ers, Bills, Commanders,
   Vikings, Cowboys, Jaguars, Raiders, Eagles, Patriots, Rams, Giants, Panthers,
   Texans, Falcons, and Broncos
   player/metric cases have dated first-party-first review; model values are retained because no validated
   numeric override rule exists. One hundred forty-three rows remain explicitly
   inconclusive despite complete review coverage.
2. Freeze and score the evidence-qualified estimates prospectively; review status is
   not permission to present an exact count as known.
3. **Partial:** the historical reference backtest supplies provisional full-season
   residual envelopes, and the direct caller-aware Weeks 6/8 diagnostic is complete.
   Extend it to Week 18, decompose component errors, and jointly calibrate it with the
   rate/availability/share layers; do not call a transferred or marginal envelope a
   calibrated 2026 interval.
4. Add opponent, offensive-line, scoring-drive, efficiency, and touchdown layers
   separately; do not hide them inside a generic projection adjustment.
5. Score the frozen 2026 counts prospectively without retuning.
