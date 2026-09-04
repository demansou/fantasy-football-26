# Multi-season caller-transition evaluation

Status: completed September 3, 2026 against fixed 2023-25 target-season
cohorts. The result supports the existing caller-aware **mean rule** as a
historically useful prior. It does not calibrate the current 0-100 broad-system
or exact-style evidence indices, and it does not change the registered 2026
prospective freeze.

## Decision

Keep the fixed `caller_aware_v0` mean rule as historically supported for future
forecast builds:

- returning caller: 95% prior destination team plus 5% prior league median;
- changed caller with a clean prior-year caller-team anchor: 70% caller prior
  team plus 20% destination team plus 10% prior league median;
- changed caller without a clean anchor: 60% destination team plus 40% prior
  league median.

The comparison baseline is fixed at 80% prior destination team plus 20% prior
league median. Neither the weights nor the metric tolerances were retuned while
adding seasons. The candidate improved the point estimate in both windows in
each of 2023, 2024, and the untouched 2025 holdout. Its pooled team-season
interval is below zero in both windows.

This is a deliberately narrow promotion. It says caller identity and clean
caller history improve an early-season style mean relative to shrunken team
persistence. It does not say a coach independently caused every observed
difference, that exact style is known, or that the current certainty score is a
probability.

## Time-correct evidence contract

Measured football outcomes come from the preserved nflverse play-by-play,
roster, and FTN charting snapshot. Caller identity is a separate researched
fact because a coordinator title does not prove who held the headset.

[Pro Football Reference's 2022 coaches table](https://www.pro-football-reference.com/years/2022/coaches.htm)
remains useful for auditing coaches, teams, games, and records. It does not
consistently distinguish the actual offensive play caller from the head coach or
listed coordinator, so it cannot safely replace the caller-identity registry.

- The 2022 prior census uses only the factual `Offensive Playcaller` column on
  physical page 65 of [Mike Clay's 2022 NFL guide](https://g.espncdn.com/s/ffldraftkit/22/NFLDK2022_CS_ClayProjections2022.pdf).
  The file is a fantasy guide, but no player projection, team projection,
  ranking, opinion, or fantasy score enters this pipeline. It is permitted only
  as historical identity evidence for later target seasons.
- The 2023 and 2024 target censuses use preseason all-team ESPN caller reports.
- The 2025 target census transcribes only the 32 numbered caller headings from
  [PFSN's June 25 preseason census](https://www.profootballnetwork.com/2025-nfl-offensive-play-caller-rankings/).
  Its rankings and qualitative opinions are ignored. The page's Giants heading
  names Brian Daboll/Mike Kafka and the text leaves the assignment unresolved,
  so New York is excluded from every window without choosing the eventual
  caller with hindsight.
- The 2025 registry stores SHA-256
  `36aeab6584bf44ce0c3aafdf2fc30cec88d95c8b4e1f695de453d375729a0803`
  over the canonical 32-heading list. This is a normalized-heading fingerprint,
  not a claim that raw HTML was archived.

Every target caller source predates its season cutoff. Target-season results are
used only for scoring. Official handoff evidence excludes a team-window when a
replacement first called on or before its endpoint: Carolina in Week 8 of 2023,
the Jets in Week 6 and Cleveland in Week 8 of 2024, and Tennessee beginning Week
4 of 2025. For example, the [Panthers identify Thomas Brown's Week 8 debut](https://www.panthers.com/news/notebook-thomas-brown-focused-on-winning-his-first-game-as-play-caller)
and the [Titans document Bo Hardegree's Week 4 handoff](https://www.tennesseetitans.com/news/titans-hc-brian-callahan-hands-off-play-calling-duties-to-qbs-coach-bo-hardegree).

## Mean-effect results

Normalized MAE is absolute error divided by the metric-specific tolerance frozen
in `fantasy_draft.environment.METRICS`. The paired delta is the team-level mean
normalized error for `caller_aware_v0` minus shrunken persistence, so negative is
better. Efficiency and explosive-play outcomes are excluded.

| Target | Window | Anchored transitions | Caller-aware NMAE | Baseline NMAE | Relative improvement | Team wins | Team-bootstrap 95% interval |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2023 | Weeks 1-6 | 4 | 0.768 | 0.886 | 13.3% | 3/4 | -0.306 to +0.094 |
| 2023 | Weeks 1-8 | 3 | 0.729 | 0.766 | 4.7% | 2/3 | -0.167 to +0.099 |
| 2024 | Weeks 1-6 | 5 | 0.770 | 0.880 | 12.5% | 4/5 | -0.252 to +0.054 |
| 2024 | Weeks 1-8 | 5 | 0.800 | 0.881 | 9.2% | 4/5 | -0.202 to +0.049 |
| 2025 holdout | Weeks 1-6 | 4 | 0.667 | 0.900 | 25.8% | 4/4 | -0.337 to -0.095 |
| 2025 holdout | Weeks 1-8 | 4 | 0.721 | 0.927 | 22.2% | 4/4 | -0.285 to -0.121 |

Pooling the team-season effects while resampling destination-team clusters gives:

| Window | Team-seasons | Team clusters | Caller-aware wins | Mean paired delta | Team-clustered bootstrap 95% interval |
|---:|---:|---:|---:|---:|---:|
| Weeks 1-6 | 13 | 11 | 11 | -0.150 | -0.232 to -0.043 |
| Weeks 1-8 | 12 | 11 | 10 | -0.111 | -0.184 to -0.024 |

The predeclared gate required three target seasons, point improvement in every
season/window, pooled intervals below zero in both windows, and holdout intervals
below zero in both windows. All four conditions pass.

The robustness audit is less decisive. If the strong 2025 holdout is removed,
the 2023-24 intervals are -0.225 to +0.029 through Week 6 and -0.161 to +0.036
through Week 8. The rule is historically supported under the declared gate, but
the evidence is not yet insensitive to which season is omitted.

## Held-out residual coverage

For each model, metric, and window, a finite-sample 90% absolute-residual radius
was fitted using 2023-24 only and opened once on 2025. These are global
style-metric bands, not player-resource or fantasy-point intervals.

| Model | Window | 2025 comparisons | Coverage | Wilson 95% interval | Mean normalized radius |
|---|---:|---:|---:|---:|---:|
| Shrunken persistence | Weeks 1-6 | 690 | 93.3% | 91.2%-95.0% | 1.761 |
| Caller-aware v0 | Weeks 1-6 | 690 | 93.2% | 91.1%-94.8% | 1.704 |
| Shrunken persistence | Weeks 1-8 | 690 | 91.3% | 89.0%-93.2% | 1.631 |
| Caller-aware v0 | Weeks 1-8 | 690 | 91.9% | 89.6%-93.7% | 1.585 |

The caller-aware bands are modestly narrower while retaining at least nominal
aggregate coverage. Within the small anchored changed-caller holdout cohort,
caller-aware coverage is 92.4% through Week 6 and 90.2% through Week 8.

Aggregate coverage hides metric variation. Nineteen of 23 caller-aware metrics
met or exceeded 90% coverage through Week 6, and 17 of 23 did so through Week 8.
The weakest Week 8 result was under-center rate at 80%. The comparison-level
Wilson intervals in the summary are descriptive because observations within a
team and across related metrics are correlated; they are not a substitute for a
larger multi-season calibration sample.

A separate diagnostic now reconstructs conservative one-year broad-system and
exact-style score bounds for all 96 team-seasons from the official 2022-25 staff
books. It fits tiers and residual radii on 2023-24, then opens 2025 once. Both score
lower bounds have the wrong held-out rank direction, the Week 6 high tier covers
only 88.96%, and score-tiered intervals are wider than the global per-metric bands.
That negative result confirms that the global coverage above cannot calibrate the
current 0-100 indices. See
[`HISTORICAL_CERTAINTY_EVALUATION_2026.md`](HISTORICAL_CERTAINTY_EVALUATION_2026.md).

## Operational recommendation

1. Preserve the existing caller-aware mean rule in future model versions; do not
   retune it on these same three seasons.
2. Leave the registered 2026 prospective bundle and fingerprint unchanged. This
   result is external historical support, not permission to rewrite a forecast
   after its outcome window began.
3. Keep the global residual bands separate from player opportunity and fantasy
   scoring uncertainty.
4. Keep the broad/exact values as explanatory evidence indices only. Do not narrow
   the global bands for high scores. Next, backfill time-correct changed-caller
   scheme/destination evidence and multi-season anchors before predeclaring another
   score test. Add week-level caller attribution before using partial episodes.

## Reproducible artifacts

The core commands are:

```bash
python3 -m fantasy_draft build-playcaller-evidence \
  --registry data/research/backtests/2022_opening_callers.json

python3 -m fantasy_draft build-playcaller-evidence \
  --registry data/research/backtests/2025_opening_callers.json

python3 -m fantasy_draft build-transition-backtest \
  --nflverse data/raw/nflverse/team_style/2021-2025/<timestamp> \
  --prior-callers data/raw/espn_nfl_playcallers/2024/all/<timestamp> \
  --target-callers data/raw/researched_nfl_playcallers/2025/all/<timestamp> \
  --changes data/research/backtests/2025_opening_caller_changes.json

python3 -m fantasy_draft evaluate-transition-backtests \
  --backtest data/derived/transition_backtest/2023/<timestamp> \
  --backtest data/derived/transition_backtest/2024/<timestamp> \
  --backtest data/derived/transition_backtest/2025/<timestamp> \
  --development-season 2023 --development-season 2024 \
  --holdout-season 2025

python3 -m fantasy_draft evaluate-historical-certainty \
  --backtest data/derived/transition_backtest/2023/<timestamp> \
  --backtest data/derived/transition_backtest/2024/<timestamp> \
  --backtest data/derived/transition_backtest/2025/<timestamp> \
  --continuity data/derived/staff_continuity/2023/<timestamp> \
  --continuity data/derived/staff_continuity/2024/<timestamp> \
  --continuity data/derived/staff_continuity/2025/<timestamp>
```

- 2022 factual caller evidence:
  `data/raw/researched_nfl_playcallers/2022/all/20260903T115222.182439Z/`
- 2025 preseason caller evidence:
  `data/raw/researched_nfl_playcallers/2025/all/20260903T115037.711474Z/`
- target-season backtests:
  `data/derived/transition_backtest/2023/20260903T121036.850890Z/`,
  `data/derived/transition_backtest/2024/20260903T121036.865266Z/`, and
  `data/derived/transition_backtest/2025/20260903T121036.644188Z/`
- pooled effects and held-out coverage:
  `data/derived/transition_evaluation/2023-2024-2025/20260903T121042.246945Z/`
- official-book staff continuity:
  `data/derived/staff_continuity/2023/20260903T123553.259748Z/`,
  `data/derived/staff_continuity/2024/20260903T123553.260134Z/`, and
  `data/derived/staff_continuity/2025/20260903T123553.261221Z/`
- historical score diagnostic:
  `data/derived/historical_certainty_evaluation/2023-2024-2025/20260903T123602.490023Z/`

Every published snapshot is atomic and binds its inputs and artifacts by
SHA-256. Backtest v0.3 verifies and binds each caller snapshot manifest; the
pooled evaluator rechecks every source bound by each parent backtest before it
scores anything. The source registries, ambiguity decisions, in-window caller
changes, model weights, scoring contract, and random seed remain inspectable.
