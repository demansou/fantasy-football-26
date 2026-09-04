# 2026 team-environment pilot

As of: 2026-09-02  
Teams: Kansas City, Philadelphia, Seattle  
Model: `team-environment-heuristic-v0.1.0`  
Status: superseded as the primary interpretation by
[`NFL_ENVIRONMENT_RECOMMENDATION_2026.md`](NFL_ENVIRONMENT_RECOMMENDATION_2026.md).
This document preserves the original three-team research pilot; its scores are not
calibrated probabilities or player projections.

## Evidence and reproducibility

The live source run ingested regular-season play-by-play and same-season rosters for
2021-25 plus FTN charting for every available season (2022-25). It produced 160
unique team-seasons: exactly 32 teams in each year. Receiver/rusher GSIS joins had
zero position conflicts and zero unknown target-position share; FTN rows matched all
eligible plays in its covered seasons.

- Local observed-style snapshot:
  `data/raw/nflverse/team_style/2021-2025/20260902T210900.618565Z`
- Normalized `team_style.csv` SHA-256:
  `c7f1c4701eb010018a1d3eaa02170d809bd24f67ac659455493bb4c28f8c020b`
- Local forecast snapshot:
  `data/derived/team_environment/2026/20260902T210926.190896Z`
- Forecast JSON SHA-256:
  `9230843971b8b1292c92ecd09b5af49372e901f2be5ee07bb5631861568b5a33`
- Curated research-input SHA-256:
  `f766d2a137e530882c1cf86d747c9a3bfa2998ffb4fe4a30a54fe4efee84a04a`

Raw and derived snapshots are intentionally ignored by Git because the raw source
assets are large. The curated staff/news evidence file and all transformation code
are tracked.

## Pilot result

| Team | Verified 2026 caller | Style certainty | QB env. | RB env. | WR env. | TE env. |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| KC | Andy Reid (credentialed report) | 82.7, high | 80.5 | 40.1 | 60.1 | 88.4 |
| SEA | Brian Fleury (official) | 57.8, medium | 34.8 | 58.9 | 41.4 | 47.0 |
| PHI | Sean Mannion (official) | 36.5, low-medium | 38.8 | 53.8 | 46.0 | 37.3 |

Position scores are historical team-opportunity environments on a 0-100 comparative
index. They do not yet know which current player receives the work. A strong TE
environment, for example, is not a projection for the current TE until the 2026
roster, depth, route and health layers are joined.

## Kansas City

Andy Reid enters his 14th Kansas City season, Eric Bieniemy returned as offensive
coordinator, and the current staff retains long-tenured pass-game, quarterback,
tight-end and offensive-line coaches. A credentialed local report says Reid remains
the caller. The official team described Bieniemy's system familiarity as continuity
while also valuing ideas from his three seasons away. Sources: [current staff](https://www.chiefs.com/team/coaches-roster/),
[Bieniemy appointment](https://www.chiefs.com/news/chiefs-name-eric-bieniemy-as-offensive-coordinator),
[scheme discussion](https://www.chiefs.com/news/eric-bieniemy-outlines-his-vision-as-offensive-coordinator),
[play-caller report](https://www.kansascity.com/sports/nfl/kansas-city-chiefs/article314461095.html).

The measured prior is extremely pass-oriented: the forecast lands around the 96th
historical percentile in neutral early-down pass rate and PROE, 91st in overall
dropback rate, and 90th in red-zone dropback rate. It is also high-shotgun/high-RPO,
low-under-center, and historically concentrated toward TE rather than WR targets.

**Current interpretation:** high confidence in the broad Reid architecture. The
strong QB/TE and weak rushing-volume environment readings are useful team priors,
but current personnel continuity is still missing and prevents player-level use.

## Seattle

Klint Kubiak is not Seattle's 2026 coordinator; he became Las Vegas' head coach.
Seattle hired Brian Fleury as its confirmed caller. Fleury is a first-time NFL play
caller, but he comes from the same Shanahan lineage, most of Seattle's offensive
staff returned, and 10 of 11 Super Bowl offensive starters returned. Seattle has
repeatedly said it intends to preserve the 2025 foundation. Sources: [staff announcement](https://www.seahawks.com/news/seattle-seahawks-finalize-2026-coaching-staff),
[Fleury appointment and lineage](https://www.seahawks.com/news/seahawks-hire-offensive-coordinator-brian-fleury),
[continuity and personnel](https://www.seahawks.com/news/offensive-coordinator-brian-fleury-brings-familiarity-fresh-ideas-to-seahawks-offense),
[play-calling responsibility](https://www.seahawks.com/news/takeaways-from-seahawks-coordinators-brian-fleury-aden-durde-jay-harbaugh).

The blended Seattle/49ers prior is under-center (95th percentile), motion-heavy
(88th), multi-back (86th), low-shotgun (9th), and run-leaning: overall dropback rate
is only the 12th percentile and red-zone dropback rate the 19th. Historical success
and explosive-play rates are strong despite the lower volume.

**Current interpretation:** the evidence supports the system family more strongly
than it supports exact weekly play calling. It points to the best RB environment of
the pilot, with lower team-volume priors for QB and WR. Medium certainty is the right
label until Fleury supplies NFL regular-season behavior.

## Philadelphia

Philadelphia hired Sean Mannion to install and call a new offense. It is his first
NFL play-calling job and Nick Sirianni's fifth offensive coordinator in six seasons.
The passing-game and run-game coordinators are new, and Chris Kuper replaced Jeff
Stoutland after Stoutland's 13-season tenure. All five starting linemen return,
Jemal Singleton and Aaron Moorehead remain, and Mannion has explicitly retained the
Saquon Barkley/run-game and quarterback-push anchors. Sources: [current staff](https://www.philadelphiaeagles.com/team/coaches/),
[Mannion appointment](https://www.philadelphiaeagles.com/news/eagles-sean-mannion-offensive-coordinator-hire),
[first-time caller](https://www.nfl.com/news/eagles-coach-nick-sirianni-not-worried-about-putting-inexperienced-sean-mannion-in-charge-of-offense),
[run-game intentions](https://www.nfl.com/news/new-eagles-offensive-coordinator-sean-mannion-will-lean-into-using-tush-push-making-saquon-barkley-focal-point-of-our-offense),
[line change](https://www.philadelphiaeagles.com/news/chris-kuper-players-if-you-can-help-them-are-going-to-listen),
[returning line](https://www.philadelphiaeagles.com/news/eagles-2026-training-camp-position-preview-offensive-line).

The blended Philadelphia/Green Bay prior is run-leaning, low in red-zone passing,
high in quarterback sneaks, pistol and no huddle, with above-average depth of target
and explosive-play history. The numerical style looks coherent, but the confidence
is low because it combines two organizational identities around a caller with no
observed calling season.

**Current interpretation:** retain confidence in only the explicitly documented
anchors—Barkley/run-game emphasis and the quarterback-push package. Treat exact
formation, pass-game structure and target allocation as unresolved until real 2026
usage appears.

## What remains before draft advice

1. Expand the same staff/play-caller/source audit to all 32 teams.
2. Add a coach-career table that distinguishes actual calling seasons from mere
   exposure to a coaching tree.
3. Backtest historical coordinator transitions and calibrate the certainty score.
4. Join the current 2026 roster, depth chart, injuries and player-role evidence.
5. Convert team opportunity into reconciled player opportunity distributions before
   applying league scoring or market ADP.

The immediate recommendation is therefore methodological: preserve these team
identity priors, but do not promote the pilot's position scores into player rankings
until steps 1-4 are complete.
