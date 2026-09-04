# Browser draft intelligence

## Scope

The browser now uses the same decision categories as the Python optimizer where
they are supported by the production opportunity ranking: open-lineup need,
next-turn positional drop-off, ADP timing, recent position runs, and roster
construction penalties. It deliberately does not port fantasy-point VORP because
the browser ranking is an NFL opportunity model, not a fantasy-point projection.

The browser score is inspectable in each player's explanation tooltip. Its live
components are bounded so they can reorder close players without overwhelming the
pinned production rank:

- fixed-starter or flex fit, increasing as the draft progresses;
- the drop in production-rank score to the same-position option expected to remain;
- market urgency from the next-turn availability estimate;
- opponent positional pressure before the next turn;
- position-run pressure from the last eight selections;
- early K/DST, excess-depth, and late same-position bye penalties.

## Availability estimate

Fantasy Football Calculator's free ADP response provides each player's mean pick,
standard deviation, observed high/low pick, and sample count. It does not provide
the underlying pick-by-pick draft outcomes. Therefore, the browser must not label
its output an empirically calibrated probability.

The new estimate fits the published normal approximation inside the observed pick
range, uses a half-pick continuity correction, and shrinks toward the unbounded
curve when the sample is small:

```text
bounded survival = P(pick >= target | observed high <= pick <= observed low)
sample weight = drafts / (drafts + 50)
market estimate = weight * bounded survival + (1 - weight) * raw survival
```

The result is constrained to 0.5%-99.5%. This removes impossible mass outside the
published market range and makes the sample-size assumption explicit. It is an
evidence-bounded market estimate, not a claim about true selection probability.

## Opponent roster intelligence

For every completed pick, the browser tracks the selecting team's positional
counts. Before the user's next snake turn it enumerates the actual pick owners,
including a team twice when the turn gives that team two selections. Each owner is
classified for the candidate position as:

- open fixed starter;
- open RB/WR/TE flex;
- bench/depth;
- deferred K/DST demand before Round 11.

The upcoming owners' average position demand is compared with the current league
average. That relative pressure adjusts market survival:

```text
opponent-adjusted estimate = market estimate ^ relative demand pressure
```

Pressure is bounded from 0.45x to 1.90x. Needy upcoming opponents lower the chance
that a player lasts; saturated opponents raise it. The league-average comparison
is important because ADP already contains ordinary roster demand and should not be
counted twice.

The interface exposes this state in three places: demand chips above the player
list, per-team needs in the league board, and each player's estimate tooltip.

## Verification and remaining calibration gap

`npm run test:intelligence` checks snake ownership, monotonic market survival,
starter/flex/depth classification, and the direction of the opponent adjustment.
The production build and lint also gate publication.

True calibration still requires timestamped, pick-level historical drafts. When a
legally usable source is available, bucket predicted probabilities, measure actual
survival frequency, and fit the reliability mapping on development drafts before
opening a held-out set. Until then, the UI retains the word `est.` and the source
dialog states the limitation.
