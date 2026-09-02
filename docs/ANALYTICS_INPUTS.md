# Analytics input design

The optimizer consumes normalized ratings, but the data pipeline must derive those
ratings from auditable raw metrics. Each record should retain its source, retrieval
time, season/week cutoff, sample size, and transformation version.

## Team profiles

### Receiver and quarterback environment

- `pass_volume_rating`: projected dropbacks, neutral-situation pass rate, pass rate
  over expectation, and total offensive play volume.
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

- `opportunity_rating`: position-specific volume—target/routes share for WR/TE,
  carry/opportunity share for RB, and projected dropbacks for QB.
- `high_value_usage_rating`: air yards and end-zone targets for receivers; goal-line,
  two-minute, and target work for backs; red-zone and designed-rush work for QBs.
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

## Normalization rules

1. Convert raw features to within-position or within-team percentiles from 0 to 1.
2. Use `0.5` as neutral and preserve missingness before applying the neutral fallback.
3. Shrink small samples toward prior-season and league-average estimates.
4. Separate signal date from game date so no future information leaks into backtests.
5. Winsorize extreme inputs and publish coverage/freshness diagnostics.
6. When consensus projections already use a feature, estimate its residual value or
   reduce the context weight to avoid double-counting.

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
