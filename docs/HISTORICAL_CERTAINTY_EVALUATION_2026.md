# Historical coaching-certainty evaluation

Status: completed September 3, 2026 with 2023-24 used for development and
2025 opened once as the holdout. The result rejects using the current coaching
evidence scores to narrow numeric 2026 style intervals. It does not change the
registered 2026 prospective freeze.

## Decision

Keep broad-system and exact-style values as transparent evidence indices. Do not
interpret them as probabilities, expected error, or interval width, and do not
give a high-scored team a narrower style band. For numeric style uncertainty, use
the development-calibrated, per-metric global residual bands from the caller-aware
transition model until a richer score passes a new held-out calibration test.

This is a useful negative result. Caller history improved the **mean forecast** in
the separate transition evaluation, but the available historical certainty score
did not identify which team forecasts would be more accurate.

## What was reconstructed

The diagnostic combines three independently frozen input families:

- opening-caller identity and early-season errors from the time-correct 2023,
  2024, and 2025 transition backtests;
- official offensive staff titles from the
  [2022 NFL Record & Fact Book](https://static.www.nfl.com/image/upload/league/apps/league-site/media-guides/2022/2022_NFL_Record_and_Fact_Book.pdf),
  [2023 NFL Record & Fact Book](https://static.clubs.nfl.com/image/upload/patriots/wlpvln9lfdtvfqc5gu40.pdf),
  [2024 NFL Record & Fact Book](https://static.www.nfl.com/image/upload/league/apps/league-site/media-guides/2024/2024_Record_and_Fact_Book_incl_Supplemental.pdf),
  and
  [2025 NFL Record & Fact Book](https://static.clubs.nfl.com/image/upload/patriots/fvc6qgwyqlztq1muztpi.pdf);
- the same component weights and transition ceiling used by
  `caller-fingerprint-heuristic-v0.1.0`.

The official-book adapter preserves the PDFs and extracted text, validates all 32
teams and head coaches, and exposes rather than invents omitted position-group
titles. The books omit CAR running backs, LV tight ends, and NE quarterbacks in
2022; ATL quarterbacks in 2023; and NYJ quarterbacks in 2024. Those responsibilities
remain unavailable when continuity is calculated.

The resulting table contains 96 team-season score rows. Only source-confirmed
opening callers are eligible. The unresolved 2025 Giants assignment remains
ambiguous and is excluded rather than resolved with hindsight.

## Conservative score contract

This first reconstruction is intentionally narrower than the current 2026 model:

- it uses only the immediately prior opening-caller season;
- one available anchor contributes `1 / 2.2` effective anchor strength and `0.45`
  fingerprint stability; no anchor receives `0.20` stability;
- returning callers receive reconstructible same-caller scheme identity and
  destination continuity components;
- time-correct scheme-family and destination-continuity research was not backfilled
  for changed callers;
- missing changed-caller components are represented as lower and upper score bounds,
  never as a neutral midpoint; and
- the conservative lower bound is the only value used for the promotion test.

That contract can test whether even the known part of the existing rubric orders
forecast error. It cannot validate the richer multi-season 2026 values or determine
how much the missing changed-caller evidence should be worth.

## Evaluation design

The 2023-24 team-seasons define score tertiles and finite-sample 90% absolute-residual
radii separately for each score, metric, and Weeks 1-6/1-8 window. The 2025 outcomes
are then opened once. The score must pass all three gates in both windows:

1. higher certainty has a negative Spearman association with team mean normalized
   absolute error, with a team-resampled 95% interval below zero;
2. every held-out score tier and the aggregate achieve at least 90% marginal metric
   coverage; and
3. the score-tiered mean radius is no wider than the per-metric global radius.

The unit of resampling is the team-season. Coverage is marginal across team-metric
rows; it is not simultaneous team-level coverage.

## Rank result

Higher scores should correspond to lower error, so a negative correlation is the
desired direction.

| Score | Sample | Window | Team-seasons | Spearman rho | Team-bootstrap 95% interval |
|---|---|---:|---:|---:|---:|
| Broad lower bound | 2023-24 development | Weeks 1-6 | 63 | -0.130 | -0.361 to +0.103 |
| Broad lower bound | 2025 holdout | Weeks 1-6 | 30 | +0.250 | -0.130 to +0.576 |
| Broad lower bound | 2023-24 development | Weeks 1-8 | 61 | -0.084 | -0.311 to +0.168 |
| Broad lower bound | 2025 holdout | Weeks 1-8 | 30 | +0.125 | -0.265 to +0.484 |
| Exact lower bound | 2023-24 development | Weeks 1-6 | 63 | -0.141 | -0.367 to +0.107 |
| Exact lower bound | 2025 holdout | Weeks 1-6 | 30 | +0.264 | -0.110 to +0.595 |
| Exact lower bound | 2023-24 development | Weeks 1-8 | 61 | -0.091 | -0.328 to +0.156 |
| Exact lower bound | 2025 holdout | Weeks 1-8 | 30 | +0.152 | -0.245 to +0.507 |

Neither score separates lower-error from higher-error teams in held-out data. The
holdout point estimates reverse the desired direction, and every interval includes
zero. High-scored returning-caller teams can still miss materially: Pittsburgh and
Indianapolis had broad lower bounds of 91.8 but the two largest 2025 team-average
errors in both windows.

## Coverage and interval-width result

| Score | Window | Tiered coverage | Tiered mean radius | Global coverage | Global mean radius |
|---|---:|---:|---:|---:|---:|
| Broad lower bound | Weeks 1-6 | 92.6% (639/690) | 1.782 | 93.2% (643/690) | 1.704 |
| Broad lower bound | Weeks 1-8 | 93.2% (643/690) | 1.732 | 91.9% (634/690) | 1.585 |
| Exact lower bound | Weeks 1-6 | 92.2% (636/690) | 1.765 | 93.2% (643/690) | 1.704 |
| Exact lower bound | Weeks 1-8 | 93.3% (644/690) | 1.727 | 91.9% (634/690) | 1.585 |

Aggregate tiered coverage is above 90%, but that is not enough. The high tier covers
only 88.96% in Week 6 for both scores, and the tiered intervals are wider than the
global per-metric bands in every comparison. Conditioning on the score therefore
adds complexity without producing narrower, reliably covered intervals.

Both score promotion gates fail. The machine-readable decision is
`do_not_condition_2026_style_intervals_on_v0_certainty_scores`.

## Operational policy

1. Keep the fixed caller-aware mean rule; its separate three-season transition gate
   passed.
2. Display broad-system and exact-style scores only with an explicit evidence-index
   label and component explanation.
3. Use global per-metric residual bands for numeric style uncertainty. Never narrow
   a 2026 band merely because its evidence score is high.
4. Preserve the registered 2026 prospective freeze unchanged, so Weeks 4/8/18 and
   postseason results can evaluate the richer current score honestly.
5. Before another score-promotion attempt, backfill time-correct changed-caller
   scheme and destination evidence, reconstruct multi-season anchors, add more target
   seasons, and predeclare the next holdout test.

## Reproducible artifacts

The evaluation command is:

```bash
python3 -m fantasy_draft evaluate-historical-certainty \
  --backtest data/derived/transition_backtest/2023/20260903T121036.850890Z \
  --backtest data/derived/transition_backtest/2024/20260903T121036.865266Z \
  --backtest data/derived/transition_backtest/2025/20260903T121036.644188Z \
  --continuity data/derived/staff_continuity/2023/20260903T123553.259748Z \
  --continuity data/derived/staff_continuity/2024/20260903T123553.260134Z \
  --continuity data/derived/staff_continuity/2025/20260903T123553.261221Z \
  --json
```

Published inputs and output:

- official staff snapshots:
  `data/raw/official_nfl_record_fact_book/2022/all/20260903T122042.088343Z/`,
  `data/raw/official_nfl_record_fact_book/2023/all/20260903T122042.088410Z/`,
  `data/raw/official_nfl_record_fact_book/2024/all/20260903T122042.088401Z/`, and
  `data/raw/official_nfl_record_fact_book/2025/all/20260902T220406.854474Z/`;
- historical continuity snapshots:
  `data/derived/staff_continuity/2023/20260903T123553.259748Z/`,
  `data/derived/staff_continuity/2024/20260903T123553.260134Z/`, and
  `data/derived/staff_continuity/2025/20260903T123553.261221Z/`;
- score reconstruction, rank tests, tier calibration, coverage predictions, and
  decision:
  `data/derived/historical_certainty_evaluation/2023-2024-2025/20260903T123602.490023Z/`.

The evaluator verifies the parent manifests, every upstream input hash bound by
those parents, and its own output hashes before publication. Its eight artifacts
preserve team scores, team errors, rank diagnostics, development-only tier cutoffs,
metric-tier calibration radii, row-level coverage predictions, summaries, and the
machine-readable decision.

## Limitations

- Three target seasons remain a small sample, and 2025 is the only holdout.
- The one-year score is not the richer multi-season 2026 score.
- Changed-caller scheme and destination evidence is bounded rather than fully
  reconstructed.
- Official record books occasionally omit one position-group title.
- A score failing to rank early-season style error does not mean coaching evidence
  is useless. It means this score has not earned a quantitative uncertainty claim.
