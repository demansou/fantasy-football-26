# Recommendation methodology

## Objective

For each pick, estimate which available player most improves the manager's final
roster while respecting league scoring, lineup constraints, opportunity cost, and
uncertainty. The current engine is a transparent heuristic baseline that we can
backtest and replace component by component.

## 1. League-adjusted projections

When raw stat projections are available, fantasy points are recomputed with the
league's scoring modifiers. A `projected_points` value is treated as an explicit
override, which is useful for D/ST or sources that do not publish raw components.

Floor and ceiling are separate uncertainty inputs. They do not replace the mean
projection. A small ceiling reward and downside penalty make risk preference
explicit instead of silently baking it into rankings.

## 2. Replacement levels and flex allocation

Fixed starter demand for a position is:

```text
number of teams x fixed starter slots at that position
```

Flex slots are allocated one at a time to the highest-projected next eligible
player after fixed starters have been consumed. The last expected starter at each
position becomes that position's replacement player.

```text
VORP = player projected points - positional replacement points
```

This matters because the same player has different marginal value in a 10-team
one-QB league, a 14-team league, and a superflex league.

## 3. Position-specific context

Team environment is stored independently from player projections. All ratings use
a 0-to-1 percentile scale with `0.5` as neutral.

- **WR and TE:** pass volume, QB play, play caller, pace, scoring environment, pass
  protection, target opportunity, high-value usage, competition, efficiency, role
  security, and upside.
- **RB:** rush volume, run blocking, positive game script, scoring environment,
  backfield opportunity, high-value usage, PPR receiving role, competition, role
  security, and efficiency.
- **QB:** play caller, pass protection, pass volume, pace, scoring environment,
  continuity, efficiency, rushing floor, opportunity, role security, and an
  explicit weekly-variance reward/penalty.

These signals are deliberately bounded so context can resolve meaningful
projection/tier decisions without casually overpowering a large VORP gap. The
weights still require historical calibration, and inputs already present in a
projection model must not be double-counted.

## 4. Live adaptive pick components

The score adds these explainable components to weighted VORP:

- **Roster need:** strongest for an open fixed starter, smaller for an open flex,
  and negative when the player is only depth.
- **Scarcity:** projected drop to the position likely to remain at the next snake
  turn. The number of expected position picks is based on league-wide starter
  demand.
- **ADP timing:** rewards a player who has fallen and penalizes a player whose ADP
  suggests we can wait. ADP influences timing, not intrinsic player quality.
- **Analytics context:** the position-specific team and player model above.
- **Projection range:** a configurable reward for ceiling and penalty for downside.
- **Construction penalties:** position limits, excess depth, same-position bye
  concentration after the roster is half full, and a strong early K/DST penalty.

Effective weights change with the live board:

- Open starter/flex need increases as the draft progresses.
- A recent position run raises that position's scarcity weight, but only the
  measured tier drop creates points, which reduces blind run-chasing.
- ADP timing gets more weight when the manager faces a long wait to the next pick.
- Bench candidates receive a modest upside-weight increase.

The JSON output exposes every contribution, effective weight, and triggering draft
signal. A close score is not presented as a meaningful difference until
calibration supports that conclusion.

## 5. What the baseline does not yet model

- Opponent-specific behavior or roster needs.
- Probability that each player survives to a future pick.
- Correlated weekly outcomes, stacking, best-ball effects, or playoff schedules.
- Keeper prices, auction budgets, traded picks, or non-snake formats.
- Injury news freshness and depth-chart changes.
- Projection-source disagreement and source reliability.
- In-season waivers, trades, and start/sit optimization.

## 6. Calibration plan

The next decision model should simulate full historical drafts rather than tune
weights by feel:

1. Freeze timestamped projections, ADP, injuries, and league settings as they were
   available before each historical draft.
2. Simulate opponent selections as probability distributions around ADP, adjusted
   for roster needs and platform behavior.
3. Compare strategies on starter points, total roster value, replacement-adjusted
   weekly points, playoff qualification, and championship probability.
4. Use rolling seasons for validation so future information never leaks backward.
5. Report uncertainty and sensitivity, not only the best weight set.

The live recommendation should eventually optimize expected final-roster value by
comparing “draft now” with the distribution of players available at every future
pick.
