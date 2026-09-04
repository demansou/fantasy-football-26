# Prospective 2026 evaluation freeze

## Decision

Use the corrected v0.4 preseason bundle as the only forecast eligible for prospective 2026
scoring:

- snapshot: `data/derived/prospective_freeze/2026/20260903T133149.697043Z`;
- model: `prospective-preseason-freeze-v0.4.0`;
- information cutoff: September 3, 2026;
- first scheduled game in the frozen schedule: September 9, 2026;
- pinned fingerprint:
  `f16a467087044aa6f4f1385ca8bc4eb86c51a287c13dfe1e3dca08349b96f115`.

The recommendation is to preserve this bundle unchanged, retrieve outcomes into new
hash-bearing snapshots, and report the predeclared Week 4, Week 8, and Week 18
scores. Do not rebuild these forecasts after games begin. New injuries, depth-chart
changes, or news can inform a separately versioned live forecast, but not this
evaluation baseline.

The original registered v0.3 bundle at
`data/derived/prospective_freeze/2026/20260903T111929.040177Z` remains immutable for
audit, but it is superseded and ineligible for scoring. Before any 2026 outcome, a
direct historical audit found that it treated eligible PBP pass plays as official QB
dropbacks and then applied a target-per-dropback conversion. Version 0.4 corrects
that denominator mismatch with strictly prior matched-history conversion factors.
Team style point forecasts, player role shares, availability policy, evidence
decisions, and scoring windows are unchanged. The manifest carries this correction
notice and the new fingerprint binds it.

Earlier same-day v0.1 and v0.2 engineering bundles predate the final fingerprinted
scoring contract. They are not registered forecasts, and the v0.4 verifier rejects
their schemas or model versions.

## What is frozen

The bundle copies 18 canonical artifacts from seven verified upstream components.
It contains:

- 32 team systems, 736 team-metric forecasts, and 128 QB/RB/WR/TE environment rows;
- 707 season player-role priors, 13,752 weekly availability forecasts, and 19,008
  weekly ordinary-role forecasts;
- 1,502 player high-value conditional-share priors, 224 team event pools, 1,502
  season player opportunity counts, and 27,036 weekly high-value role/count rows;
- all 365 reviewed current-role exceptions and their 476-source evidence registry;
- an input inventory linking every copied artifact to its source snapshot, source
  date, row count, model version, and SHA-256 hash.

The 365 season-level reviews are also exact-joined onto the weekly high-value count
rows. Across those rows, 6,570 carry a reviewed status and 20,466 are explicitly
`not_required`. No evidence row changes a numeric forecast.

## Publication gates

The build fails closed unless all of these hold:

1. Every upstream manifest has the expected model version and season.
2. Every input byte stream matches the SHA-256 in its parent manifest.
3. Every component and every dated evidence record was available on or before the
   information cutoff.
4. The cutoff precedes the first scheduled game.
5. All 32 team sets match, Weeks 1-18 are present, and each team has 17 scheduled
   games.
6. Every QB/RB/WR/TE position environment exists.
7. Current-role review coverage is 100%, every flagged key joins exactly, and no
   numeric override is present.
8. The public fingerprint binds the cutoff, first game, scoring contract, explicit
   v0.3 supersession notice, all 24 parent hashes, and all 18 frozen output hashes.

`verify_prospective_freeze()` recomputes that identity and rejects a changed file,
manifest contract, or pinned fingerprint.

## Predeclared scoring contract

Outcomes must come from newly retrieved and hash-preserved nflverse weekly roster,
opportunity, schedule, and high-value event data. The scorer must use only games
through the declared Week 4, 8, or 18 checkpoint.

- Availability: Brier score of the frozen median active probability against weekly
  `ACT=1` and `INA=0`, with calibration reported by frozen status cohort and
  position.
- Ordinary conditional role: renormalize the frozen latent weight only among actual
  active opening candidates, allocate the observed team resource, and use unweighted
  mean team-position-resource total variation as the primary error. Depth share and
  historical share remain the frozen baselines.
- Ordinary issued counts: score untouched weekly expected dropbacks, carries, and
  targets by player-game mean absolute error; also report RMSE, signed bias, and
  descriptive p10-p90 containment.
- High-value conditional role: apply the same actual-active evaluation oracle to the
  frozen p24 weights and use unweighted mean team-metric total variation. The
  unadjusted base-role share is the frozen baseline.
- High-value issued counts: score the untouched weekly expected event counts by
  player-game mean absolute error; also report RMSE, signed bias, and descriptive
  scenario-envelope containment.
- Team resources: score the frozen weekly team pools by team-game mean absolute
  error and RMSE. Eligible PBP pass/rush plays are converted to official QB
  dropbacks, targets, and RB carries with frozen matched-history factors; scoring
  must not reinterpret one unit as another.
- Certainty: within each directly matchable team metric, report error by the frozen
  certainty tier and its rank association. The 0-100 indices remain evidence scores,
  not probabilities.

The candidate universe is the union of frozen players and actual later entrants.
Later entrants retain zero forecast mass. No outcome, exclusion, metric, evidence,
or code change may retune this registered forecast; any such change creates a new
version alongside it.

## Reproduction

```bash
python3 -m fantasy_draft build-prospective-freeze \
  --caller-fingerprints data/derived/caller_fingerprints/2026/20260902T223905.016436Z \
  --position-environments data/derived/position_environments/2026/20260903T132013.423720Z \
  --player-roles data/derived/player_roles/2026/20260903T132156.590720Z \
  --availability data/derived/availability/2026/20260903T132328.323948Z \
  --high-value-priors data/derived/high_value_priors/2026/20260903T132359.548967Z \
  --high-value-volumes data/derived/high_value_volumes/2026/20260903T132405.658654Z \
  --role-research data/derived/role_research/2026/20260903T132410.884456Z \
  --cutoff 2026-09-03
```

To verify the registered bytes before scoring:

```python
from fantasy_draft.prospective import verify_prospective_freeze

verify_prospective_freeze(
    "data/derived/prospective_freeze/2026/20260903T133149.697043Z",
    expected_fingerprint=(
        "f16a467087044aa6f4f1385ca8bc4eb86c51a287c13dfe1e3dca08349b96f115"
    ),
)
```

## Remaining uncertainty

This freeze is a defensible test of team style, availability, role allocation, and
named opportunity counts. It is not a complete player projection. It excludes
all-player routes, individual efficiency, touchdowns, fantasy points, and a frozen
outcome definition for the composite position-environment score. The current
high-value envelopes are stress scenarios rather than jointly calibrated 2026
prediction intervals. A direct 2023-25 early-window test is complete, but no resource
clears its strict mean gate, QB rush is worse than shrunken persistence, RB-carry
bands undercover, and all-six marginal bands have only 70.0%/66.7% simultaneous
coverage. Week-18 component decomposition and joint calibration remain open. Those
limitations must remain visible when the prospective results are reported; see
[`CALLER_RESOURCE_BACKTEST_2026.md`](CALLER_RESOURCE_BACKTEST_2026.md).
