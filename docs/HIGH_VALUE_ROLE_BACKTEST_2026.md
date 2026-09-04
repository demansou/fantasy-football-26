# High-value role history, backtest, and 2026 priors

Data cutoff: September 2, 2026. Final artifacts were built September 3 UTC,
still September 2 in the project timezone.

## Decision

Use seven historically adjusted player-share features as **frozen, prospective
2026 conditional-role priors**:

- RB carries inside the 5-yard line;
- RB carries inside the 10-yard line;
- RB targets in the final two minutes of either half;
- WR end-zone targets;
- WR deep targets, defined as at least 15 air yards;
- TE deep targets; and
- TE two-minute targets.

Do not use the other 11 tested features to move 2026 player shares. In particular,
do not use the current public data as a first-read projection and do not infer routes
run from the participation `route` column.

This decision is narrower than a player projection. Each selected output answers:

> If this team-position event occurs and this availability scenario occurs, what
> share belongs to each player?

It does not forecast how many such events the offense will create, catches, yards,
touchdowns, efficiency, or fantasy points.

## Source audit and definitions

The history builder reads the already preserved 2021-25 nflverse regular-season
play-by-play, roster, and FTN charting files. It joins FTN to play-by-play by
`nflverse_game_id` and `nflverse_play_id`, and player attribution remains on GSIS ID.
Names are never join keys.

The [current nflreadr FTN dictionary](https://nflreadr.nflverse.com/articles/dictionary_ftn_charting.html)
defines `read_thrown` as `0 = primary`, `1 = second`, `2 = third or later`, plus
`CHK`, `DES`, and `SD`; it also says 2022 primary reads were not coded. That mapping
was added in the upstream
[August 31 dictionary change](https://github.com/nflverse/nflreadr/commit/b32d4340123ead6b67cf7508e5e04495f9bdd882).
The pipeline therefore leaves every 2022 `first_read_targets` value blank rather
than zero.

That audit changed the initial result materially. The older issue shorthand had
suggested that code `1` was first read. After applying the current canonical
definition, code `0` appears on only 0.63%-1.61% of mapped 2023-25 targets. The
pipeline publishes a source-review warning for each season, and all three
first-read features fail the downstream gate. No first-read adjustment reaches the
2026 prior.

The public [participation dictionary](https://nflreadr.nflverse.com/articles/dictionary_participation.html)
says `route` describes only the primary receiver's route on a play. It cannot be
expanded into player routes run, so no route-share field is emitted. This also
matters operationally: [nflverse's schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html)
says FTN charting updates during the season, while 2023+ participation data arrives
only after the postseason. Participation is therefore unsuitable as a live route
feed even apart from the field-definition problem.

The non-read definitions are mechanical and source-visible:

| Feature | Definition |
| --- | --- |
| Deep target | `air_yards >= 15` |
| End-zone target | `air_yards >= yardline_100` |
| Red-zone target/carry | `yardline_100 <= 20` |
| Inside-10 target/carry | `yardline_100 <= 10` |
| Inside-5 carry | `yardline_100 <= 5` |
| Two-minute target/carry | Q2 or Q4, `half_seconds_remaining <= 120` |
| Short-yardage carry | `0 < ydstogo <= 2` |
| Designed QB carry | QB carry not marked as a scramble; kneels excluded upstream |

## Historical coverage

All player counts reconcile exactly to team-position-week counts.

| Season | Teams | Weeks | Targets | Carries | GSIS-mapped | FTN target match | Primary-read state |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2021 | 32 | 18 | 18,058 | 13,183 | 100% | unavailable | blank |
| 2022 | 32 | 18 | 17,306 | 13,442 | 100% | 100% | structurally unavailable |
| 2023 | 32 | 18 | 17,483 | 13,141 | 100% | 100% | 233 code-0 targets; 1.33% |
| 2024 | 32 | 18 | 17,013 | 13,219 | 100% | 100% | 274; 1.61% |
| 2025 | 32 | 18 | 16,609 | 13,077 | 100% | 100% | 105; 0.63% |

The derived history contains 25,345 player-week rows and 9,950
team-position-week rows, with zero player-to-team reconciliation error. FTN read
labels cover 98.84% of 2022 mapped targets and 100% in 2023-25, but label coverage
does not cure the sparse dictionary-defined primary-read category.

## Time-correct test

The backtest holds out 2023, 2024, and 2025 in turn. For each target season it:

1. creates the candidate room from the target-season Week 1 roster and depth state;
2. builds the ordinary role share using the already selected policy—depth only for
   QB and the frozen depth/history blend for RB, WR, and TE;
3. uses only seasons strictly before the target season for a player's high-value
   event rate;
4. shrinks that rate toward the player's historical peer team-position rate using
   beta-equivalent priors of 12, 24, and 48 base opportunities;
5. applies the existing prior-team and transfer shrinkage and bounds the multiplier
   from 0.25 to 4.0; and
6. scores 4-, 8-, and 18-week player allocations by team-room total-variation
   distance.

The primary model is the 24-opportunity shrink. Actual weekly active status and the
actual team metric-event pool are evaluation-only oracles. They isolate player share
from the separate availability and team-volume problems; they are not available to
a real preseason projection. Later roster entrants remain explicit zero-share
forecasts, and a room with no actual metric event is omitted because its share is
undefined.

Paired 90% bootstrap intervals resample team-season clusters. Every comparison has
an independent deterministic seed derived from its metric, window, and model, so an
unrelated metric cannot change a promotion decision.

The predeclared gate requires all three windows, at least 500 Week-18 events across
at least 80 rooms, at least two primary-model intervals wholly below zero, no clear
loss, and negative mean error deltas for all three shrink strengths.

## Results

Negative deltas mean less allocation error than the ordinary role prior. The mean
columns average the three evaluation windows equally.

| Promoted metric | Base mean TV | p24 mean TV | Delta | Clear wins / 3 | Week-18 events |
| --- | ---: | ---: | ---: | ---: | ---: |
| RB inside-5 carries | 0.3419 | 0.3319 | -0.0101 | 2 | 1,738 |
| RB inside-10 carries | 0.2864 | 0.2765 | -0.0099 | 2 | 3,029 |
| RB two-minute targets | 0.4126 | 0.3983 | -0.0143 | 3 | 1,235 |
| WR end-zone targets | 0.3555 | 0.3457 | -0.0098 | 2 | 2,402 |
| WR deep targets | 0.2793 | 0.2676 | -0.0116 | 3 | 8,360 |
| TE deep targets | 0.2969 | 0.2879 | -0.0089 | 2 | 1,527 |
| TE two-minute targets | 0.3438 | 0.3239 | -0.0199 | 3 | 1,587 |

The most stable signals are WR deep targets and TE/RB two-minute targets: their p24
intervals are below zero in all three windows. RB inside-5, WR end-zone, and TE deep
target adjustments have two clear windows but one uncertain window, so they pass the
rule without being called universally better.

Rejected or diagnostic-only results are equally important:

| Metric family | Result |
| --- | --- |
| QB designed carries at the 20/10/5 | no clear win; inside-10 and inside-5 mean error increased |
| RB short-yardage carries | tiny mean improvement, no clear win, and p12 sensitivity worsened |
| RB/WR/TE first reads | only 100/343/139 Week-18 events; none passed; WR mean error increased and had one clear loss |
| WR red-zone targets | small uncertain improvement; no clear win |
| WR two-minute targets | mean error increased by 0.0057 and one window was a clear loss |
| TE red-zone/end-zone targets | mean error increased; no clear win |

This is retrospective feature selection on overlapping windows, not a causal result
or independent prospective validation. The seven selected metrics are now frozen;
2026 scoring must not retune them in response to early outcomes.

## 2026 output and review queue

The current builder applies only the seven selected p24 adjustments to the
all-affiliated latent player-role rooms, preserves p12/p48 as a sensitivity envelope,
and then reruns the 5,000-draw weekly availability redistribution with one common
player availability state across every metric in a team-week.

| Check | Result |
| --- | ---: |
| Current player-metric priors | 1,502 |
| Team/metric rooms | 224 = 32 teams x 7 metrics |
| Weekly player-metric shares | 27,036 |
| Weekly reconciliations | 4,032 = 32 x 7 x 18 |
| Bye team/metric rows | 224 |
| Max current-room error | 0 |
| Max weekly error | 0 |
| Max no-active-player draw rate | 4.28% |
| Current-role review reasons | 368 |
| Distinct player/metric rows requiring review | 365 |

The 368 reasons are not hidden failures: 139 flag a player with at least 5% latent
role but no player-level history for that metric, 154 flag a material role with more
than zero but fewer than the primary 24 weighted base opportunities, and 75 flag an
absolute historical adjustment of at least 10 percentage points. Three rows trigger
two reasons, leaving 365 distinct player/metric cases. Until reviewed, a large change
or a thin-sample estimate is model output, not a claim that the 2026 coaching staff
will deploy the player that way.

## Reproducible artifacts

- high-value history:
  `data/derived/high_value_history/2021-2025/20260903T042311.979334Z/`
- corrected, deterministic 2023-25 backtest:
  `data/derived/high_value_backtest/2023-2024-2025/20260903T042515.139734Z/`
- frozen 2026 conditional shares and weekly scenarios:
  `data/derived/high_value_priors/2026/20260903T132359.548967Z/`
- joined current-role evidence audit and ranked reviewed queue:
  `data/derived/role_research/2026/20260903T132410.884456Z/`

Each snapshot contains its schema/model version, exact parent paths, SHA-256 input
and output hashes, definitions, counts, reconciliation checks, and limitations.

## Recommendation for the next iteration

1. Freeze the completed preseason audit. Dated first-party-first evidence now covers all 365
   Jets, Colts, Chiefs, Dolphins, Bears, Browns, Lions, Ravens, Packers, Seahawks,
   Cardinals, Chargers, Steelers, Titans, Bengals, Saints, Buccaneers, 49ers, Bills,
   Commanders, Vikings, Cowboys, Jaguars, Raiders, Eagles, Patriots, Rams, Giants,
   Panthers, Texans, Falcons, and Broncos player/metric exceptions. Of those, 143
   remain explicitly inconclusive rather than being forced into false certainty.
   Archive narrow dated claims before each game and apply no numeric override until
   a translation rule passes a time-correct test. See
   [`CURRENT_ROLE_RESEARCH_2026.md`](CURRENT_ROLE_RESEARCH_2026.md).
2. **Completed downstream:** the team-rate development/holdout gate rejects unsupported
   team persistence and publishes pooled-rate, caller-aware event counts. A separate
   resource reference test adds provisional full-season residual envelopes. The
   direct six-resource early-window diagnostic corrects denominator definitions but
   promotes no resource and supplies no joint interval. See
   [`HIGH_VALUE_VOLUME_BACKTEST_2026.md`](HIGH_VALUE_VOLUME_BACKTEST_2026.md),
   [`RESOURCE_POOL_BACKTEST_2026.md`](RESOURCE_POOL_BACKTEST_2026.md), and
   [`CALLER_RESOURCE_BACKTEST_2026.md`](CALLER_RESOURCE_BACKTEST_2026.md).
3. Find a licensed or user-owned all-route source; do not manufacture route share
   from the public primary-receiver route field.
4. Freeze and score all seven shares prospectively in 2026, including calibration
   and later-entrant coverage, before they affect final draft rankings.
5. Keep first reads quarantined until the upstream code-0 behavior is confirmed and
   a time-correct sample clears the same gate.
