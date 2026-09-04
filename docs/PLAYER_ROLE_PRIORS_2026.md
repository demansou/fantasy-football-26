# 2026 player identity and role-prior checkpoint

Data cutoff: September 2, 2026. The final source refresh was retrieved at
September 3 02:00 UTC, still September 2 in the project timezone.

## Decision

Promote this pipeline as the player-identity and current-role **prior** beneath the
NFL environment model. The role formula now has a three-season retrospective test;
weekly availability scenarios are implemented. Do not promote either layer as a
full-season player projection yet.

The important boundary is now explicit:

```text
caller-aware team opportunity pool
  -> resource-selected role shares for every affiliated player (implemented)
  -> weekly status-cohort availability and role redistribution (implemented, limited)
  -> seven tested high-value conditional shares (implemented, retrospective/frozen)
  -> holdout-gated team/player high-value opportunity counts (implemented, limited)
  -> current-role evidence audit (implemented; 365 of 365 rows reviewed)
  -> routes, Week-18 component/joint base-volume calibration and efficiency (not implemented)
  -> league-specific fantasy points (not implemented)
```

This is materially better than importing a fantasy projection because every current
player, team, roster status, depth position, historical opportunity, and PFR snap is
traceable to a preserved source asset. It is also honest about the remaining gap:
population status histories can frame scenarios for players on PUP, injured reserve,
the commissioner's exempt list, or a practice squad, but they cannot supply
individualized medical return probabilities.

## What is implemented

`fetch-nflverse-players` now downloads and immutably snapshots:

- the nflverse player identity table, whose primary key is GSIS ID;
- the complete 2026 roster release;
- the full timestamp history in the 2026 depth-chart release, from which the latest
  timestamp is selected independently for every team;
- 2023-25 weekly player opportunities; and
- 2023-25 Pro Football Reference offensive snap counts via nflverse.

The normalized outputs are `current_roster.csv`, `current_depth_chart.csv`,
`historical_usage.csv`, and `source_identity_review.csv`. The adapter never joins
these source families by player name. Depth records use GSIS ID first and a unique
ESPN-ID bridge second; conflicts and missing IDs go to review. The raw roster release
and the independently refreshed player catalog can briefly disagree around roster
cuts. The normalized table therefore preserves `roster_team`/`roster_status` while
using `team`/`current_status` for the catalog's newer affiliated state. Every such
reconciliation is also written to review rather than hidden.

For this live snapshot, the preserved HTTP metadata timestamps `players.csv` at
12:54:49 UTC and `roster_2026.csv` at 11:54:20 UTC on September 2. The catalog
precedence is therefore based on the newer source artifact, not a name match or a
manual assumption.

`build-player-roles` then:

- reconciles FFC's market-only rows to the nflverse identity spine only when a
  canonicalized name, current team, and position produce one candidate;
- creates resource-specific priors for QB dropbacks and rushes, RB carries and
  targets, and WR/TE targets;
- hash-binds the observed team-style snapshot and converts its eligible PBP
  pass/rush plays to official player-stat units with matched 2023-25 history;
- uses depth only for QB resources and blends recent observed share with current
  depth for RB/WR/TE, with less carryover when a player changed teams;
- allocates only players carrying the current `ACT` status;
- preserves all affiliated non-active players as latent candidates and in an
  availability review instead of projecting them at zero; and
- requires median player shares to sum to exactly one for every team/resource room.

The companion availability layer estimates historical status-family marginals,
applies reviewed four-game minimums, draws one common availability state per player
across every team resource, and renormalizes surviving latent role weights. Its
overall Brier improvement over an active/non-active baseline is only 0.000178, with
a paired 90% interval of -0.000559 to +0.000197, so it remains a scenario layer.

## Live coverage and integrity

| Check | September 2 result |
| --- | ---: |
| Current roster rows | 2,902 |
| Teams represented in roster and latest depth | 32 / 32 |
| Latest depth rows | 2,213 |
| Latest depth timestamp for every team | 2026-09-02 11:55:28 UTC |
| Historical player-team-season usage rows | 1,857 |
| Automated source review rows | 229 |
| Roster/catalog reconciliations retained for audit | 209 |
| Remaining source-ID/mapping issues | 20 |
| FFC QB/RB/WR/TE identities resolved automatically | 216 / 216 |
| Active players receiving a role prior | 505 |
| Player-resource role rows | 707 |
| All-affiliated player-resource candidate rows | 1,056 |
| Team/resource reconciliation rows | 192 |
| Maximum median reconciliation error | 0 |
| Broad non-active availability review | 164 |
| FFC-listed non-active availability cases | 7 |
| Weekly availability / expected-role rows | 13,752 / 19,008 |
| Team-week-resource scenario reconciliations | 3,456; zero maximum error |

Of the 229 source-review rows, 209 are explicit roster/catalog audit records: 68
newer affiliated-team assignments and 141 newer status classifications. Those are
resolved through the shared GSIS ID, with both source values retained. The remaining
20 are narrow and inspectable: ten depth rows lack a resolvable ID, two roster ESPN
IDs disagree with the player catalog, one roster player lacks a GSIS ID, and seven
unique PFR snap identities do not map through the current player table. Repeated
game-level PFR misses are collapsed to one player/team/season review item.

All 216 FFC skill-position identities resolve to one current catalog affiliation;
209 are current active players and therefore appear in the role output. Seven have
a valid identity but a non-active status. Jaydon Blue now resolves to Philadelphia
through the shared GSIS player catalog while the raw Dallas/CUT roster value remains
visible in the audit record.

## What the priors say—and what they do not

These examples show the output's granularity. Ranges are uncalibrated marginal role
bounds, not probabilities and not additive across players.

| Team/resource | Player | Low | Median | High | Median opportunities/game |
| --- | --- | ---: | ---: | ---: | ---: |
| KC QB dropbacks | Patrick Mahomes | 87.5% | 92.2% | 96.8% | 35.78 |
| KC QB dropbacks | Justin Fields | 0.0% | 6.5% | 15.2% | 2.50 |
| SEA RB carries | Jadarian Price | 34.8% | 49.8% | 64.8% | 12.71 |
| SEA RB carries | Emanuel Wilson | 11.6% | 24.0% | 36.4% | 6.12 |
| SEA RB carries | George Holani | 15.3% | 23.5% | 31.7% | 5.99 |
| PHI RB carries | Saquon Barkley | 55.9% | 62.5% | 69.2% | 13.31 |
| SEA WR targets | Jaxon Smith-Njigba | 31.0% | 36.9% | 42.8% | 6.18 |

The Kansas City example is a role allocation, not a claim that Mahomes will play 17
games. The Seattle active baseline excludes Zach Charbonnet while he is on PUP, but
the scenario output retains his latent role and enforces zero availability through
Week 4. It also exposes where a reviewed current-role claim
should improve the mechanical prior: Seattle says Price and Holani figure to split
the early workload, while Wilson had been limited in camp. That evidence should be
encoded and tested before manually moving shares.

## The seven draft-market availability cases

The structured evidence is in
`data/research/2026/player_status_evidence.json`. These are facts, not sentiment:

| Player | Automated state | Reviewed first-party finding | Current model treatment |
| --- | --- | --- | --- |
| Josh Jacobs | GB `EXE`; ADP 43.2 | Commissioner's exempt list; cannot practice or play while listed; club hopes for a return but gives no timetable | Retained as an exempt/suspended-fallback scenario; no fixed return minimum |
| Zach Charbonnet | SEA `RES/PUP`; ADP 134.6 | Opens on PUP after an ACL injury; no timetable; Seattle identifies Price/Holani as the early pair | Zero Weeks 1-4; return-eligible-reserve cohort thereafter |
| Isiah Pacheco | DET raw `ACT`, current `RES`; ADP 156.4 | Detroit placed him on reserve/injured September 1 | Zero Weeks 1-4; generic-IR cohort thereafter |
| Jordyn Tyson | NO `RES/RSR`; ADP 157.2 | Reserve/injured, designated for return | Zero Weeks 1-4; return-eligible-reserve cohort thereafter |
| James Conner | ARI `RES/RSR`; ADP 160.7 | Reserve/injured, designated for return | Zero Weeks 1-4; return-eligible-reserve cohort thereafter |
| Tank Dell | HOU `RES/RSR`; ADP 162.1 | Reserve/PUP | Zero Weeks 1-4; return-eligible-reserve cohort thereafter |
| Jaydon Blue | PHI `DEV` with raw DAL `CUT`; ADP 163.7 | Philadelphia signed him to its practice squad | Retained in practice-squad activation scenarios |

Primary evidence: [Packers initial roster](https://www.packers.com/news/packers-keep-six-receivers-seven-defensive-linemen-here-s-the-initial-2026-roster),
[NFL/AP Jacobs update](https://www.nfl.com/news/packers-express-hope-rb-josh-jacobs-currently-on-exempt-list-can-play-sometime-this-season),
[Seahawks initial roster](https://www.seahawks.com/news/a-position-by-position-look-at-the-seahawks-initial-2026-53-man-roster),
[Seahawks Charbonnet PUP notice](https://www.seahawks.com/news/seahawks-rb-zach-charbonnet-placed-on-pup-list),
[Lions transactions](https://www.detroitlions.com/team/transactions/),
[Saints roster](https://www.neworleanssaints.com/team/rosters),
[Cardinals roster](https://www.azcardinals.com/team/players-roster/),
[Texans roster](https://www.houstontexans.com/team/players-roster/), and
[Eagles Blue transaction](https://www.philadelphiaeagles.com/news/eagles-sign-t-kiran-amegadjie-rb-jaydon-blue-wr-danny-gray-and-cb-robert-longerbeam-to-practice-squad).

A separate non-market Atlanta exception now uses the same policy. The Falcons
[placed Trey Sermon on injured reserve August 19](https://www.atlantafalcons.com/news/rb-trey-sermon-injured-reserve),
before the August 30 final reduction. The [NFL roster FAQ](https://www.nfl.com/news/nfl-training-camp-roster-faqs-defining-injured-reserve-pup-list-nfi-and-more)
and [2026 important dates](https://operations.nfl.com/calendar-events/nfl-important-dates)
make that placement season-ineligible, so all 18 weeks are zeroed as a reviewed
transaction rule rather than a medical guess.

## Remaining uncertainty

1. `ACT` is current eligibility, not a 17-game health forecast. The implemented
   status curves are population marginals and weeks are independent, not correlated
   player recovery paths.
2. The 2025+ depth chart is an ESPN-derived daily source with a changed schema. It
   is useful evidence, but an unofficial depth rank is not guaranteed deployment.
3. Direct targets and carries are stronger role evidence than raw snaps. PFR snap
   share is therefore published as a diagnostic but receives no weight until a
   held-out test shows incremental value.
4. The frozen universal depth/history blend reduced total-variation role error in
   every 2023-25 target season, but resource analysis rejected it for QB. That test
   supplies actual weekly active status and team resource volume as evaluation-only
   oracles to isolate conditional role; it does not validate deployable availability.
   The selected v0.4 policy is retrospective, and marginal role widths still lack
   coverage tests.
5. Routes, first reads, two-minute work, goal-line work, and red-zone roles are not
   interchangeable. Seven historical conditional-share signals are now allocated and
   frozen: RB inside-5/inside-10 carries and two-minute targets, WR end-zone/deep
   targets, and TE deep/two-minute targets. A subsequent holdout gate now supplies
   pooled-rate team/player opportunity counts. First reads and routes remain
   quarantined. Historical residual envelopes now cover the four base resources used
   by those high-value counts. The 365-row current-role review is complete, but its
   evidence labels remain unvalidated inputs until prospectively scored. The direct
   caller-aware early-window test promotes no resource; Week-18 component and joint
   interval calibration remain incomplete.
6. nflverse documents that its injury source died after 2024. Current availability
   must therefore come from official transactions, club injury reports, and dated
   first-party or credentialed reports rather than an assumed live nflverse feed.

## Recommendation for the next iteration

Score the corrected frozen v0.4 role rule, the seven screened high-value shares, and
the completed evidence audit prospectively during 2026. Extend the completed direct
caller-resource test to Week 18, decompose component error, jointly calibrate the
full count distribution, and obtain a valid all-route source. The Jets inside-5
exception and all
365 flagged Jets, Colts, Chiefs, Dolphins, Bears,
Browns, Lions, Ravens, Packers, Seahawks, Cardinals, Chargers, Steelers, Titans, and
Bengals, Saints, Buccaneers, 49ers, Bills, Commanders, Vikings, Cowboys, Jaguars,
Raiders, Eagles, Patriots, Rams, Giants, Panthers, Texans, Falcons, and Broncos rows
now have dated first-party-first review with no numeric override. One hundred forty-three
rows remain explicitly inconclusive, which should be preserved as uncertainty rather
than converted into a point adjustment.
Keep first reads out:
the corrected canonical code mapping produces a sparse sample and none of the three
position features passed the gate. Collect official weekly transaction and injury
evidence before every game so availability can move from broad population scenarios
toward player-specific, time-correct updates. Only after those gates should role
samples become catches, yards, touchdowns, and league scoring. See
[`HIGH_VALUE_ROLE_BACKTEST_2026.md`](HIGH_VALUE_ROLE_BACKTEST_2026.md).
The downstream volume gate and opportunity-count outputs are documented in
[`HIGH_VALUE_VOLUME_BACKTEST_2026.md`](HIGH_VALUE_VOLUME_BACKTEST_2026.md).
The resource test and its transfer limitation are documented in
[`RESOURCE_POOL_BACKTEST_2026.md`](RESOURCE_POOL_BACKTEST_2026.md).
The direct production-aligned resource diagnostic is documented in
[`CALLER_RESOURCE_BACKTEST_2026.md`](CALLER_RESOURCE_BACKTEST_2026.md).
The fail-closed evidence registry and ranked queue are documented in
[`CURRENT_ROLE_RESEARCH_2026.md`](CURRENT_ROLE_RESEARCH_2026.md).

The complete backtest, availability curves, rule constraints, limitations, and
reproducible artifact paths are in
[`AVAILABILITY_AND_ROLE_BACKTEST_2026.md`](AVAILABILITY_AND_ROLE_BACKTEST_2026.md).
