# Roadmap

## Phase 1 — Offline decision core (current)

- [x] Configurable roster, flex, scoring, and position limits.
- [x] Raw-stat scoring and fantasy-points override.
- [x] Flex-aware replacement levels and VORP.
- [x] Roster need, scarcity, ADP timing, context, risk, and construction signals.
- [x] Separate normalized team profiles and position-specific WR/RB/QB/TE context.
- [x] Explicit low-variance QB preference.
- [x] Live weight adaptation for draft phase, roster need, snake turns, and runs.
- [x] Explainable table/JSON output.
- [x] Synthetic end-to-end example and unit tests.

Exit criterion: one command deterministically recommends from a known draft state,
and every material score component is inspectable.

## Phase 2 — Trustworthy 2026 analytics pipeline

- Select projection, platform ADP, injury, depth-chart, offensive-line, pace, and
  team scoring-environment sources after reviewing access and redistribution terms.
- Preserve source, retrieval timestamp, season, model version, and player identity
  on every record.
- Build player-ID reconciliation across Yahoo and analytics sources.
- Create consensus projections with source disagreement and uncertainty bands.
- Add freshness checks that fail closed for stale or incomplete draft-day data.

Exit criterion: a reproducible command creates a dated 2026 projection snapshot,
with coverage and provenance reports, without manual spreadsheet cleanup.

## Phase 3 — Yahoo league integration

- Register a local Yahoo application and implement the authorization-code flow.
- Store secrets/tokens outside Git with restrictive local permissions.
- Import the actual league's scoring, roster positions, teams, keepers, and draft
  results through the official API where supported.
- Keep a manual CSV/JSON fallback so draft-day recommendations do not depend on one
  remote service.

Exit criterion: a read-only sync reproduces Yahoo league settings and current draft
state, and discrepancies against a manual export are surfaced.

## Phase 4 — Draft simulation and calibration

- Model selection probability from Yahoo ADP, rank, opponent rosters, and pick turn.
- Monte Carlo the rest of the draft for every candidate at the current pick.
- Optimize expected final starting lineup and bench option value.
- Backtest with time-correct historical snapshots; tune weights only on training
  seasons and publish validation metrics.
- Add keeper, superflex, auction, and traded-pick support as required by the league.

Exit criterion: the simulator beats static ADP and static projection baselines on
held-out historical drafts under predeclared metrics.

## Phase 5 — Live draft board

- Fast local web UI with available players, roster grid, tiers, next-turn survival
  probability, and recommendation explanations.
- One-click draft event entry plus Yahoo refresh/reconciliation.
- Draft-day health panel for data age, API state, and local fallback readiness.
- Precompute expensive simulations so a new recommendation arrives within seconds.

Exit criterion: complete mock drafts can be run without editing files or touching a
terminal, including loss of network access mid-draft.

## Phase 6 — In-season team optimizer

- Weekly lineup optimization using opponent, weather, injury, and role uncertainty.
- Waiver prioritization by expected lineup gain and rest-of-season option value.
- Trade evaluation with positional replacement effects and playoff schedules.
- Transparent alerts for material news or projection changes.

Exit criterion: every recommendation shows the expected improvement, uncertainty,
data timestamp, and relevant constraints.

## League facts needed before Phase 2 output is actionable

- Yahoo league identifier or a settings export.
- Team count and exact scoring modifiers.
- Roster slots, flex/superflex rules, bench/IR, and position caps.
- Snake, auction, or salary-cap format; draft slot and draft date/time.
- Keepers and pick costs, if any.
- Preferred risk posture and whether correlated stacks should be valued.
