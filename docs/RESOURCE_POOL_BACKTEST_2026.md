# Team resource-pool backtest and provisional 2026 envelopes

Data cutoff: September 3, 2026.

## Decision

Keep the existing caller-aware 2026 point estimates for RB carries and RB/WR/TE
targets. Do not replace them with a simple historical team-rate forecast.

Use the historical backtest's absolute per-game residual radii only as
**provisional stress envelopes** around those caller-aware means. They are not
directly calibrated intervals for the caller-aware model, and the WR-target radius
missed its nominal coverage target on the untouched 2025 season. A subsequent direct
early-window test does not justify replacing them: no resource clears its strict mean
gate, and the direct RB-carry bands also undercover.

This is a useful reduction in uncertainty: the high-value opportunity output no
longer pretends that its base carry/target pool is fixed. It is not the final
uncertainty solution.

## Test design

The test aggregates GSIS-keyed nflverse weekly opportunities into four resources
that feed the seven supported high-value metrics:

- `RB_CARRIES`;
- `RB_TARGETS`;
- `WR_TARGETS`; and
- `TE_TARGETS`.

For each 2023-25 target season, every forecast uses only earlier seasons, with a
three-season lookback and exponential recency weighting. Candidate forecasts are a
league rate, a raw team rate, and team rates shrunk toward the league by 4, 8, 16,
32, or 64 prior games. Weeks 4, 8, and 18 are scored separately.

The 2023-24 seasons select the best team candidate. The fixed promotion rule then
opens 2025 once and requires that candidate to:

1. beat the league rate in all three development windows;
2. beat it in all three untouched-holdout windows;
3. produce at least two holdout paired 90% intervals wholly below zero; and
4. produce no clear holdout loss.

Paired intervals resample team-season clusters. Actual target-season opportunities
are evaluation-only and never enter that season's forecast.

## Model-selection result

All four development-selected team candidates had lower 2025 point error than the
league rate in all three windows, but none cleared the complete predeclared gate.

| Resource | Development candidate | Development deltas vs league, W4/W8/W18 | Holdout deltas vs league, W4/W8/W18 | Clear holdout wins | Decision |
| --- | --- | ---: | ---: | ---: | --- |
| RB carries | team rate, 64-game prior | +0.004, -0.130, -0.097 | -0.238, -0.175, -0.178 | 1 | retain league reference |
| RB targets | team rate, 64-game prior | +0.014, -0.037, -0.071 | -0.124, -0.116, -0.116 | 3 | retain league reference |
| WR targets | team rate, 64-game prior | -0.006, -0.078, -0.076 | -0.038, -0.148, -0.293 | 1 | retain league reference |
| TE targets | team rate, 32-game prior | +0.042, -0.103, -0.086 | -0.229, -0.074, -0.127 | 1 | retain league reference |

Negative deltas mean lower mean absolute error per game. The result says team
persistence deserves another test; it does not authorize relaxing the gate after
seeing the holdout.

The selected historical reference affects only the residual-radius calculation.
The production mean remains the separate caller-aware 2026 estimate.

## Residual-radius result

A finite-sample 90% split-conformal absolute-error radius is estimated from the
2023-24 Week-18 team-season errors and tested once on 2025.

| Resource | Per-game radius | 2025 covered teams | 2025 coverage | Status |
| --- | ---: | ---: | ---: | --- |
| RB carries | 4.535 carries | 31/32 | 96.9% | met nominal on holdout |
| RB targets | 2.352 targets | 30/32 | 93.8% | met nominal on holdout |
| WR targets | 4.476 targets | 27/32 | 84.4% | **below nominal** |
| TE targets | 3.619 targets | 31/32 | 96.9% | met nominal on holdout |

Aggregate coverage is 119/128, or 93.0%. That aggregate does not rescue the WR
undercoverage: every resource is reported separately, and none is described as
having guaranteed 2026 coverage.

The production transform now forms each base-resource scenario as:

> low = max(0, caller-aware mean - historical residual radius)
>
> median = caller-aware mean
>
> high = caller-aware mean + historical residual radius

For a high-value team event, it multiplies the low resource by the low conditional
rate and the high resource by the high conditional rate. Player envelopes then add
the existing marginal availability and conditional-share scenarios. This is an
outer-product stress envelope, not a joint prediction interval; dependencies among
volume, rate, availability, and share are not learned.

## Direct follow-up completed

The direct follow-up now reconstructs the actual caller-aware resource forecast for
2023-25 and compares it with shrunken persistence through Weeks 6 and 8. Production
and backtest share the same conversion from eligible PBP pass/rush plays to official
QB dropbacks, targets, and RB carries. This audit exposed and corrected the former
mixed-denominator implementation before 2026 outcomes.

No resource clears the strict direct mean gate. On the untouched 2025 holdout, QB
dropbacks have slightly lower point MAE but uncertain intervals; QB rush opportunity
is clearly worse in both windows; and the four remaining resources are mixed or
uncertain. Development-calibrated direct marginal bands miss 90% for RB carries in
both windows and WR targets at Week 8. Simultaneous containment across all six
marginal bands is only 70.0% through Week 6 and 66.7% through Week 8.

That test is an early-window diagnostic, not a Week-18 or joint calibration. Its full
design and results are in
[`CALLER_RESOURCE_BACKTEST_2026.md`](CALLER_RESOURCE_BACKTEST_2026.md).

## Reproducible artifacts

- time-correct resource reference test and residual calibration:
  `data/derived/resource_backtest/2023-2024-2025/20260903T052616.212410Z/`
- direct denominator-consistent caller-aware six-resource test:
  `data/derived/caller_resource_backtest/2023-2024-2025/20260903T132151.087878Z/`
- rebuilt 2026 high-value team/player opportunities:
  `data/derived/high_value_volumes/2026/20260903T132405.658654Z/`
- rebuilt current-role evidence audit:
  `data/derived/role_research/2026/20260903T132410.884456Z/`
- corrected immutable 2026 freeze:
  `data/derived/prospective_freeze/2026/20260903T133149.697043Z/`

The backtest contains 8,064 team/resource/model/window predictions, 210 evaluation
rows, 180 paired comparisons, and four calibration rows. The rebuilt opportunity
snapshot contains 224 team/metric pools, 1,502 player/metric rows, 27,036 weekly
player rows, and 4,032 exact weekly reconciliations. All output hashes verify, and
all 1,502 serialized median values match the preceding build exactly. The direct
snapshot adds 3,312 resource predictions and 1,104 paired effects with nine
hash-declared artifacts.

## What remains before promotion

1. Extend the direct caller-aware test from Weeks 6/8 to Week 18; the existing
   full-season radii remain transferred from a simpler historical reference.
2. Test component errors for plays, PBP pass/rush split, official-unit conversions,
   QB rush components, and position target shares.
3. Calibrate the combined resource x event-rate x availability x player-share
   distribution jointly rather than multiplying marginal endpoints.
4. Score the corrected v0.4 2026 freeze prospectively without retuning.
