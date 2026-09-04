# Direct caller-aware team-resource backtest

Data cutoff: September 3, 2026.

## Recommendation

Use the denominator-consistent resource transform in the corrected 2026 freeze, but
do **not** claim that this test validates the caller-aware resource means or their
intervals. No one of the six resources clears the predeclared strict mean-promotion
gate. Keep the already issued caller-aware point estimates as provisional priors,
retain the older full-season stress envelopes, and flag QB rushing and RB carries as
the clearest current risks.

This result does not reverse the separate conclusion that caller-aware *team style
metrics* beat the persistence blend in the pooled transition test. It answers a
harder downstream question: after converting style rates into official player-stat
opportunities, does each complete resource forecast beat shrunken persistence and
does a development-calibrated interval cover an untouched season?

## Unit-definition correction

The audit found that the original player-role builder mixed two denominators:

- team `pass_rate` counts eligible nflverse play-by-play pass plays, including
  scrambles and excluding kneels and spikes;
- player-history QB dropbacks are official attempts plus sacks suffered, excluding
  scrambles; and
- targets and RB carries are player-stat events rather than play-by-play pass/rush
  play counts.

Treating play-by-play pass plays as official dropbacks and then applying a
target-per-dropback factor overstated both QB dropbacks and targets. Production and
backtest now call the same six-resource transform:

```text
PBP pass plays = plays/game x pass rate
PBP rush plays = plays/game x (1 - pass rate)

QB dropbacks = PBP pass plays x official-dropbacks/PBP-pass-play factor
QB rush opportunities = PBP pass plays x scramble rate
                      + PBP rush plays x designed-QB-run share
RB carries = PBP rush plays x (1 - designed-QB-run share)
           x RB-carries/non-QB-PBP-rush-play factor
position targets = PBP pass plays x targets/PBP-pass-play factor
                 x position target share
```

RB/WR/TE shares may legitimately sum below one because QBs and other positions can
receive targets, so the transform never scales them upward. If independently blended
shares exceed one by no more than five percentage points, it closes them downward to
one; a larger overflow fails the build instead of hiding an incoherent forecast.

Each factor is estimated from up to three strictly prior, matched nflverse
team-seasons with 0.65 annual recency weighting. The production 2026 factors use 96
team-seasons from 2023-25:

| Conversion | 2026 factor |
| --- | ---: |
| Official QB dropbacks / eligible PBP pass play | 0.896295 |
| Player targets / eligible PBP pass play | 0.795461 |
| RB carries / non-QB PBP rush play | 0.935958 |

The 2023 historical target has only 2021-22 conversion training because the preserved
team-style series begins in 2021. The factor is still strictly prior; it is simply
based on two seasons rather than three.

## Evaluation design

- Target seasons: 2023, 2024, and 2025.
- Windows: Weeks 1-6 and Weeks 1-8, matching the frozen caller-transition inputs.
- Development: 2023-24.
- Untouched holdout: 2025; it is not used to select a model or interval radius.
- Candidate: the frozen caller-aware style forecast passed through the shared
  denominator-consistent transform.
- Primary baseline: shrunken team persistence passed through the same transform.
- Outcomes: GSIS-keyed nflverse weekly player opportunities.
- Uncertainty: 5,000 bootstrap samples clustered by destination team across target
  seasons.

The strict mean gate requires lower MAE than shrunken persistence in both development
windows and both holdout windows, with both holdout 95% bootstrap intervals for the
paired difference below zero. The interval gate requires every resource/window band,
calibrated only on 2023-24, to reach 90% marginal coverage on 2025.

## Untouched 2025 mean results

Negative MAE difference favors the caller-aware candidate.

| Resource | W6 MAE difference (95% CI) | W8 MAE difference (95% CI) | Decision |
| --- | ---: | ---: | --- |
| QB dropbacks | -0.126 (-0.513, +0.261) | -0.037 (-0.485, +0.372) | uncertain; no promotion |
| QB rush opportunities | +0.169 (+0.015, +0.358) | +0.170 (+0.004, +0.362) | caller-aware is worse |
| RB carries | +0.265 (-0.105, +0.720) | +0.307 (-0.052, +0.715) | point estimate worse; uncertain |
| RB targets | -0.018 (-0.217, +0.147) | +0.023 (-0.190, +0.203) | no promotion |
| WR targets | +0.021 (-0.167, +0.197) | +0.070 (-0.109, +0.242) | no promotion |
| TE targets | +0.016 (-0.141, +0.175) | +0.085 (-0.086, +0.261) | no promotion |

No resource clears the strict gate. QB rush opportunity is the one resource where
both holdout intervals exclude zero in the wrong direction: the caller-aware
candidate is about 0.17 opportunities per team-game worse than shrunken persistence
in each early window.

The corrected transform also removes the largest systematic unit bias. On 2025 Weeks
1-6, mean signed error is +0.38 QB dropbacks per team-game rather than the +4.29 seen
under the mixed denominator. Target biases fall from +2.75 to +0.67 for WRs and from
+0.77 to -0.02 for TEs. This is a definition correction, not evidence that the model
now clears a predictive gate.

## Marginal and simultaneous coverage

| Resource | W6 holdout coverage | W8 holdout coverage |
| --- | ---: | ---: |
| QB dropbacks | 100.0% | 100.0% |
| QB rush opportunities | 96.7% | 93.3% |
| RB carries | **83.3%** | **86.7%** |
| RB targets | 90.0% | 90.0% |
| WR targets | 100.0% | **86.7%** |
| TE targets | 100.0% | 100.0% |

RB carries miss nominal coverage in both windows; WR targets miss at Week 8. A team
is inside all six separately calibrated marginal bands only 21/30 times through Week
6 (70.0%) and 20/30 through Week 8 (66.7%). Those figures are descriptive and are
not a joint 90% guarantee.

## 2026 decision and remaining uncertainty

The direct test supports four actions:

1. Keep the corrected play-to-opportunity conversions in
   `player-role-prior-v0.4.0` and the v0.4 prospective freeze.
2. Do not promote any resource-specific caller-aware mean over shrunken persistence
   from this test. The frozen means remain provisional inputs pending prospective
   scoring.
3. Do not replace the existing full-season transferred stress envelopes with these
   early-window marginal radii.
4. Next, decompose error into plays, pass/run split, QB run components, and position
   target shares; add a Week-18 target and calibrate the complete resource x event-rate
   x availability x role-share distribution jointly.

## Reproduction and artifacts

```bash
python3 -m fantasy_draft evaluate-caller-resources \
  --backtest data/derived/transition_backtest/2023/20260903T121036.850890Z \
  --backtest data/derived/transition_backtest/2024/20260903T121036.865266Z \
  --backtest data/derived/transition_backtest/2025/20260903T121036.644188Z \
  --player-history data/raw/nflverse/player_history/20260903T032645.770207Z \
  --observed-styles data/raw/nflverse/team_style/2021-2025/20260902T210900.618565Z \
  --development-season 2023 --development-season 2024 \
  --holdout-season 2025 --bootstrap-samples 5000
```

Authoritative output:
`data/derived/caller_resource_backtest/2023-2024-2025/20260903T132151.087878Z/`.
It contains 3,312 resource predictions, 1,104 paired effects, twelve marginal
calibration rows, 360 holdout coverage rows, two simultaneous-coverage diagnostics,
and hash declarations for all nine artifacts and every consumed input.
