# Analytics input design

The optimizer consumes normalized ratings, but the data pipeline must derive those
ratings from auditable raw metrics. Each record should retain its source, retrieval
time, season/week cutoff, sample size, and transformation version.

## Team profiles

### Coaching and offensive identity

Team identity is forecast as a vector, not a single coach-style label. The measured
history currently includes neutral pass tendency/PROE, volume, shotgun, under-center,
pistol, no huddle, motion, play action, screens, RPOs, multi-back looks, target depth,
position target shares, QB runs, red-zone tendency, explosiveness, success, and EPA.

Every 2026 team record must independently identify the head coach, offensive
coordinator, actual play caller, pass/run-game coordinators, and QB/RB/WR/TE/OL
coaches. A title is not proof of play-calling authority. System-tree experience is a
weaker prior than seasons in which the coach actually called plays.

Keep these outputs separate:

- `style_forecast`: expected behavior for each measured dimension;
- `style_certainty`: confidence in those behaviors, with component explanations;
- `position_environment`: team-level opportunity conditions for QB/RB/WR/TE;
- `environment_quality`: efficiency and scoring opportunity, which are not style;
- player role/health uncertainty, which is joined later and must not be inferred from
  a team score.

Generic news sentiment is not an input. Normalize each report into a dated claim
about a staff fact, scheme metric, implementation uncertainty, or observed role,
retain its URL and provenance, and cap its numerical influence until corroborated.

The fixed caller-transition rule now has three time-correct target seasons. It lowers
the aggregate normalized error versus league-shrunk persistence in both early-season
windows in 2023, 2024, and the untouched 2025 holdout. Pooled 95% team-season
intervals exclude zero, and development-calibrated global residual bands achieved
93.2% and 91.9% coverage on 2025 at 90% nominal. The mean rule is therefore
historically supported, but the 2023-24-only intervals cross zero and metric-level
effects remain heterogeneous. No weights were tuned from these results. The current
position scores retain their declared weights and remain experimental.

A separate time-correct diagnostic reconstructs conservative one-year broad-system
and exact-style score bounds for 2023-25 from official staff continuity and confirmed
opening callers. Tiers are fitted on 2023-24 and tested once on 2025. Both lower
bounds have the wrong held-out rank direction; their Week 6 high tier covers only
89.0%, and score-tiered intervals are wider than global per-metric bands. Therefore
the 0-100 values remain explanation indices and may not change numeric uncertainty.
The richer current score still needs time-correct changed-caller scheme/destination
evidence and multi-season anchors before another predeclared holdout test.

### Receiver and quarterback environment

- `pass_volume_rating`: projected eligible PBP pass plays, their strictly prior
  matched-history conversion to official QB dropbacks, neutral-situation pass rate,
  pass rate over expectation, and total offensive play volume.
- `qb_play_rating`: accuracy, efficiency per dropback, pressure-to-sack behavior,
  turnover tendency, and expected availability of the starting quarterback.
- `play_caller_rating`: situation-adjusted passing/rushing tendency, motion/play
  action usage where available, red-zone efficiency, and multi-season stability.
- `pass_blocking_rating`: pressure and sack prevention attributable to protection,
  adjusted for quarterback behavior and opponent quality.
- `pace_rating`: situation-adjusted seconds per snap and projected plays.
- `continuity_rating`: returning quarterback/play caller/line/receiver continuity.

### Running-back environment

- `rush_volume_rating`: projected team attempts, neutral rush tendency, and expected
  rushing share near the goal line.
- `run_blocking_rating`: yards before contact, line-adjusted rushing efficiency,
  success rate, and returning line quality.
- `positive_game_script_rating`: probability of playing ahead, informed by team
  strength and market expectations rather than last season's win total alone.
- `scoring_environment_rating`: projected drives, points, red-zone trips, and
  touchdown opportunity.

## Player profiles

The role-prior layer is implemented from current nflverse IDs/rosters, each team's
latest timestamped depth chart, 2023-25 weekly opportunities, and PFR snap counts.
It allocates QB dropbacks/rushes, RB carries/targets, and WR/TE targets and reconciles
every median room to the caller-aware team pool. A time-correct 2023-25 test selects
depth-only QB roles and the depth/history blend for RB/WR/TE. The choice is
retrospective and is now preserved in the registered pre-outcome v0.4 bundle for
prospective 2026 scoring at Weeks 4, 8, and 18. Version 0.4 corrects a pre-outcome
denominator mismatch: eligible PBP pass/rush plays are converted to official QB
dropbacks, player targets, and RB carries with factors learned from matched 2023-25
team-seasons. It does not change the selected player role shares.

All affiliated players also receive latent role weights. A separate 2021-25
status-cohort model samples weekly availability, applies reviewed rule-backed minimum
absences, and renormalizes available players inside each team resource. Its overall
incremental Brier interval crosses zero, so this is a population scenario layer, not
an individualized injury prognosis. Role low/high bounds still need empirical
coverage calibration.

The ratings below describe the intended canonical player profile, not a claim that
every component is already populated. The current high-value output deliberately
keeps seven tested signals separate. Holdout-selected team rates now convert them to
opportunity counts, but they will not collapse into one rating until current role and
upstream base-volume uncertainty are directly calibrated. A first historical
resource-reference test now supplies provisional residual envelopes for RB carries
and RB/WR/TE targets; those envelopes are transferred around the caller-aware means,
and WR targets missed nominal holdout coverage. A direct six-resource early-window
test now uses the exact production transform. No resource clears its strict mean
gate; QB rush is clearly worse, RB carries undercovers in both windows, and the six
marginal bands do not provide joint coverage. All-player route share, efficiency,
Week-18 component/joint interval calibration, and individualized health remain
missing.

Current-role research is a separate audit layer. It exact-joins dated claims to
flagged GSIS/team/metric rows, ranks unresolved cases by expected-event materiality,
and preserves whether evidence supports, conflicts with, or cannot resolve the
historical prior. Version 0.1 forbids numeric overrides: camp or depth evidence may
change the uncertainty label, but it cannot change a share until a reproducible
evidence-to-prior rule improves time-correct held-out forecasts.

- `opportunity_rating`: position-specific volume—target share now and eventually
  validated route share for WR/TE,
  carry/opportunity share for RB, and projected dropbacks for QB.
- `high_value_usage_rating`: eventual aggregate of supported air-yard/end-zone,
  goal-line, two-minute, and rushing signals; currently represented by seven separate
  conditional-share and opportunity-count priors rather than one opaque score.
- `competition_rating`: clarity of the path to volume after accounting for teammates;
  higher means less credible competition.
- `efficiency_rating`: position-adjusted efficiency after opponent and role context.
- `receiving_role_rating`: route, target, and two-minute work for RBs, especially
  valuable in PPR.
- `rushing_floor_rating`: designed and scramble rushing contribution for QBs.
- `weekly_variance`: normalized dispersion of the player's projected weekly fantasy
  distribution. Lower is more stable. It should incorporate floor probability, role
  stability, injury uncertainty, and dependence on long touchdowns—not just the raw
  standard deviation of a small historical sample.

PFR offensive snap share is preserved as a diagnostic but currently receives no
model weight. Direct targets/carries/dropbacks are closer to the quantities being
allocated, and snap share should be promoted only if it adds held-out predictive
value after current depth and direct opportunity are included.

## Normalization rules

1. Convert raw features to within-position or within-team percentiles from 0 to 1.
2. Use `0.5` as neutral and preserve missingness before applying the neutral fallback.
3. Shrink small samples toward prior-season and league-average estimates.
4. Separate signal date from game date so no future information leaks into backtests.
5. Winsorize extreme inputs and publish coverage/freshness diagnostics.
6. When consensus projections already use a feature, estimate its residual value or
   reduce the context weight to avoid double-counting.
7. Treat the team—not each correlated metric—as the sampling unit when evaluating a
   coaching transition; publish paired team effects and cluster intervals.
8. Do not translate a heuristic 0-100 certainty index into probability language until
   held-out forecast intervals achieve their advertised empirical coverage.
9. Keep availability and conditional role separate; rule-backed zeroes may constrain
   availability, while unknown medical timing cannot be invented from a role report.
10. Keep current-role evidence and numeric modeling separate; no article, quote, or
    unofficial depth chart directly overrides a forecast without a held-out rule.
11. Keep eligible PBP plays and official player-stat opportunities as distinct units;
    conversions must be learned from strictly prior matched data, hash-bound to their
    source, and shared by production and historical evaluation.

## Live draft inputs

After every pick, the engine should receive the player, drafting team, overall pick,
round, and updated rosters. The current deterministic layer immediately recomputes:

- available-player VORP and tier drop;
- each roster's open positions and our lineup urgency;
- recent position-run pressure;
- time until our next snake pick and the ADP wait/value signal;
- effective need, scarcity, ADP, context, upside, and stability weights.

The later simulation layer will add opponent-specific selection probabilities and
compare the expected final roster from drafting each candidate now versus waiting.
