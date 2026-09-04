# Current-role evidence audit and research queue

Data cutoff: September 3, 2026.

> **Numeric supersession notice:** This qualitative source audit was conducted
> against v0.3 opportunity counts. The evidence classifications, role shares, and
> zero-override decisions remain unchanged, but every exact count quoted in the case
> narratives below is historical context. For current numeric use, read the corrected
> `player-role-prior-v0.4.0` and downstream v0.4 freeze; they convert eligible PBP
> plays to official player-stat opportunities with matched-history factors.

## Decision

Use current official depth, roster, transaction, coach, and role reporting to
**qualify uncertainty**, not to hand-edit player opportunity shares. The first audit
version forbids numeric overrides until a repeatable evidence-to-prior rule passes a
time-correct validation gate.

This preserves three distinct statements:

1. the historical model produced a transparent conditional-share estimate;
2. current evidence may support, conflict with, or fail to resolve that estimate; and
3. only a validated rule may translate that evidence into a different number.

Camp usage is therefore a research lead. It is not silently converted into a
regular-season projection.

## Automated queue

The high-value prior now flags material players whose metric-specific history is
absent or thinner than the primary 24-opportunity shrinkage prior. It also retains
the existing flag for a historical adjustment of at least 10 percentage points.

| Automated reason | Review reasons |
| --- | ---: |
| At least 5% latent role, no player metric history | 139 |
| At least 5% latent role, more than zero but fewer than 24 weighted opportunities | 154 |
| Historical adjustment of at least 10 percentage points | 75 |
| Total reasons | 368 |
| Distinct player/metric rows | 365 |

Three player/metric rows trigger two reasons, which is why the distinct queue is
smaller than the reason count. The final opportunity file carries
`requires_current_role_review`, the exact issue list, metric-history support, and
weighted base-opportunity count on every row.

The queue is sorted by the model's availability-adjusted event count so research can
start with the estimates that can matter most. That ranking is materiality triage,
not a player ranking or a claim that the estimate is correct.

| Metric | Queued player/metric rows | Reviewed through current pass |
| --- | ---: | ---: |
| RB inside-5 carries | 47 | 47 |
| RB inside-10 carries | 41 | 41 |
| RB two-minute targets | 83 | 83 |
| WR end-zone targets | 63 | 63 |
| WR deep targets | 55 | 55 |
| TE deep targets | 36 | 36 |
| TE two-minute targets | 40 | 40 |
| **All** | **365** | **365** |

The 365 reviewed player/metric rows cover all queued Jets, Colts, Chiefs, Dolphins,
Bears, Browns, Lions, Ravens, Packers, Seahawks, Cardinals, Chargers, Steelers,
Titans, Bengals, Saints, Buccaneers, 49ers, Bills, Commanders, Vikings, Cowboys, and
Jaguars, Raiders, Eagles, Patriots, Rams, Giants, Panthers, Texans, Falcons, and
Broncos cases. Two hundred twenty-two rows have evidence that resolves the audit
direction while retaining the model, 143 remain explicitly inconclusive, and zero
stay unreviewed. A completed review is evidence coverage, not a claim that every
player's exact share is known.

## Jets audit

The club's [current depth chart](https://www.newyorkjets.com/team/depth-chart) is
useful current evidence but is explicitly labeled unofficial and compiled by the
communications department. It lists Breece Hall, Braelon Allen, and Isaiah Davis in
the three RB slots, Andrew Beck separately at FB, and Kene Nwangwu at KR.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Kene Nwangwu, inside-5 and inside-10 carries | The club reports 108 special-teams snaps and only 28 offensive snaps in 2025 and currently lists him at KR rather than in the three RB depth slots. [Source](https://www.newyorkjets.com/news/jets-re-sign-running-back-kene-nwangwu-free-agency-03-19-2026) | Current role conflicts with trusting the thin historical goal-line sample. Preserve the frozen number for auditability, mark it low certainty, and apply no manual transfer. |
| Andrew Beck, RB two-minute targets | Beck is listed separately at FB; the club reports 110 offensive and 319 special-teams snaps in 2025 and describes a blocker, special-teams contributor, and occasional receiver. [Source](https://www.newyorkjets.com/news/jets-re-sign-fullback-andrew-beck-free-agency-03-12-2026) | The reviewed evidence does not establish a normal two-minute role. Retain and flag the estimate. |
| Braelon Allen and Isaiah Davis, RB two-minute targets | Aaron Glenn describes Hall, Allen, and Davis as a three-headed backfield and mentions passing-game use for Allen, but no source assigns the two-minute hierarchy. [Source](https://www.newyorkjets.com/news/jets-for-braelon-allen-the-time-is-now-otas-06-11-2026) | Meaningful roles are plausible; the specific conditional shares remain inconclusive. |
| Kenyon Sadiq, TE deep and two-minute targets | Frank Reich has discussed 12- and 13-personnel and Sadiq as a matchup option, but Sadiq missed most of camp after a hernia-surgery setback and only recently returned to position drills. [Sources](https://www.newyorkjets.com/news/jets-2026-training-camp-preview-tight-ends-present-endless-possibilities-mason-taylor), [return update](https://www.newyorkjets.com/news/rookies-kenyon-sadiq--dangelo-ponds-nearing-return-from-injuries-09-02-2026) | There is a path to usage, but no defensible regular-season deep/two-minute allocation yet. |
| Omar Cooper Jr., WR deep and end-zone targets | Cooper is behind Garrett Wilson on the club's two-WR chart and caught a first-team touchdown in one late-camp two-minute drill. [Source](https://www.newyorkjets.com/news/jets-practice-report-geno-smith-2-minute-drill-touchdown-omar-cooper-08-24-2026) | A single practice result is context, not a stable target-share estimate. Keep the no-history prior unadjusted. |

The separate Jets team-rate exception is now reviewed. [Frank Reich called the
preseason plays](https://www.newyorkjets.com/news/notebook-jets-frank-reich-calling-plays-from-the-box-08-28-2026),
but the current reporting supplies no validated 2026 goal-line rate. The model
therefore keeps the holdout-selected 5.19% pooled RB-inside-5 rate instead of the
Jets' 2.01% raw recent rate. A camp report in which Allen took over red-zone work
after Hall exited is injury-conditioned context, not evidence for a stable team
rate. [Source](https://www.newyorkjets.com/news/jets-training-camp-practice-report-breece-hall-injury-08-17-2026)

## Indianapolis audit

The [current Colts depth chart](https://www.colts.com/team/depth-chart) and
[initial 53-man roster](https://www.colts.com/news/colts-announce-initial-53-man-roster-for-2026-nfl-season)
resolve who remains in the immediate role competition, but neither supplies
situational routes, targets, or carries.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Alec Pierce, WR deep and end-zone targets | The club calls Pierce its leading downfield threat and activated him from PUP. [Sources](https://www.colts.com/news/colts-wide-receiver-alec-pierce-indianapolis-nfl-pat-mcafee-show-contract), [PUP transaction](https://www.colts.com/news/colts-remove-wr-alec-pierce-from-active-physically-unable-to-perform-list) | The deep-role direction is supported, but the exact deep count and end-zone allocation are not validated. |
| Josh Downs, WR deep and end-zone targets | The club describes a prominent receiving role, while camp reporting also introduced Keenan Allen and discussed Downs making plays downfield and in the end zone. [Sources](https://www.colts.com/news/josh-downs-michael-pittman-wide-receiver), [Allen fit](https://www.colts.com/news/training-camp-notebook-why-shane-steichen-sees-keenan-allen-as-good-fit-with-daniel-jones-in-colts-offense) | Overall prominence is not a numeric situational share; both estimates remain inconclusive. |
| Seth McGowan, three RB metrics | The current chart places Jonathan Taylor first, DJ Giddens second, and McGowan third. Earlier first- and second-team camp work came while Giddens was hurt, and the club identified pass protection as decisive. [Source](https://www.colts.com/news/the-encouraging-trend-for-colts-offense-laiatu-latu-keeps-flashing-deforest-buckner-trending-in-right-direction-more-from-first-2-weeks-of-training-camp) | Current hierarchy conflicts with the older RB2-sized latent role. Preserve and flag the frozen values until a validated roster update rule exists. |
| DJ Giddens, RB two-minute targets | Giddens is second on the current chart, but the reviewed sources do not identify the receiving-down back. | Retain the limited-history prior; backup rank alone cannot establish two-minute usage. |
| Ashton Dulin, WR deep and end-zone targets | Dulin is rostered and has speed, but the club also describes his core special-teams work and notes extended outside work while Pierce was unavailable. Allen subsequently joined the receiving plan. [Source](https://www.colts.com/news/colts-sign-6-time-pro-bowl-wr-keenan-allen) | Both situational shares remain inconclusive. |
| Drew Ogletree, TE deep and two-minute targets | The club describes a third tight end with an in-line blocking profile and 22 receptions in 44 career games. [Source](https://www.colts.com/news/drew-ogletree-re-signed-nfl-free-agency-2026-run-blocking-pass-catching-career-touchdowns) | Evidence supports the low receiving-role direction, not exact counts. |

## Kansas City audit

The Chiefs' [initial 53-man roster](https://www.chiefs.com/news/here-s-a-look-at-the-chiefs-initial-53-man-roster-x9897)
is the controlling roster snapshot for this pass. The accessible unofficial depth
page still includes players omitted from that roster, so the audit records it as a
stale or ambiguous source rather than treating its ordering as definitive.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Tyquan Thornton, WR deep and end-zone targets | The club expects Thornton to be a significant contributor after his team-leading eight receptions of at least 25 yards in 2025. [Source](https://www.chiefs.com/news/pre-camp-breakdown-examining-the-chiefs-wide-receivers-x6490) | Downfield direction is supported; the exact deep count is not. Touchdowns do not identify end-zone targets, so that metric remains inconclusive. |
| Rashee Rice, WR deep targets | Rice is rostered and described as a top receiving option, but the source does not isolate his downfield role from the other receivers. | Retain the historical prior without turning overall prominence into deep volume. |
| Emmett Johnson, three RB metrics | The rookie made the initial 53 alongside Kenneth Walker III and Brashard Smith, but no reliable current source assigns goal-line or two-minute work. | All three no-history priors remain inconclusive. |
| Jalen Royals and Cyrus Allen, WR deep and end-zone targets | Both made the initial 53. Pre-camp reporting only gave each a chance to carve out a role, while minicamp supplied isolated practice plays. [Source](https://www.chiefs.com/news/chiefs-wrap-up-mandatory-minicamp-at-the-team-facility) | Roster spots and practice highlights do not calibrate situational target shares. |
| Jared Wiley, TE deep and two-minute targets | Wiley made the roster with Travis Kelce, Noah Gray, and Jake Briningstool; the reviewed camp evidence is one seam reception in one practice. [Source](https://www.chiefs.com/news/five-observations-from-wednesday-s-practice-chiefs-training-camp-7-29) | Retain both limited-history priors; package-specific routes remain unknown. |
| EJ Smith, three RB metrics | The club waived Smith with an injury designation, and he is absent from the initial 53. [Source](https://www.chiefs.com/news/chiefs-announce-roster-moves-heading-into-2026-nfl-season) | Current active role conflicts with treating him as a live competitor. Preserve only the tiny frozen reserve-adjusted priors for auditability pending a validated transaction update. |

## Miami audit

The [initial 53-man roster](https://www.miamidolphins.com/news/miami-dolphins-set-initial-53-man-roster-for-2026)
confirms that every flagged player remains on the active roster. The
[current depth page](https://www.miamidolphins.com/team/depth-chart) is useful for
relative roles, but it still displays practice-squad receiver Jalen Reagor and Cole
Turner, who is absent from the initial 53, so the audit does not treat every cell as
authoritative.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Caleb Douglas, WR deep and end-zone targets | Douglas is first at one outside receiver spot. Miami calls him a deep threat who excels on posts, corners, and fades after 30% of his final college targets came at least 20 yards downfield; camp added multiple long and end-zone catches. [Sources](https://www.miamidolphins.com/news/fast-facts-caleb-douglas), [late-camp report](https://www.miamidolphins.com/news/practice-17-2026-miami-dolphins-training-camp-notebook) | The role direction is supported, but neither no-history NFL count is validated. |
| Malik Washington, WR deep and end-zone targets | Washington is first on another receiver line and discussed a larger role and desire for downfield work. Camp supplied intermediate catches and one end-zone play. [Source](https://www.miamidolphins.com/news/transcript-wr-malik-washington-press-conference-jun-9) | Starting opportunity is real; player intent and practice plays do not validate the model's large situational adjustments. |
| Ollie Gordon II, three RB metrics | Gordon is third on the RB line, but the club explicitly says he was its short-yardage back in 2025. [Source](https://www.miamidolphins.com/news/training-camp-preview-2026-running-backs) | Retain the inside-10 and inside-5 directions. Two-minute usage remains inconclusive. |
| Chris Bell, WR deep and end-zone targets | Bell made the roster but opened camp on active/NFI following an ACL injury and recorded his first 11-on-11 camp catches only on August 25. [Sources](https://www.miamidolphins.com/news/dolphins-place-bell-on-active-non-football-injury-list), [practice report](https://www.miamidolphins.com/news/practice-16-2026-miami-dolphins-training-camp-notebook) | The late return and unresolved reserve hierarchy conflict with treating either no-history role as established. |
| Greg Dulcich, TE deep targets | Dulcich leads the TE depth line, and Miami calls him the room's receiving leader after 222 yards on 18 targets over the final five games of 2025. [Source](https://www.miamidolphins.com/news/training-camp-preview-2026-tight-ends) | Retain the meaningful receiving direction; exact deep volume is unvalidated. |
| Kevin Coleman Jr., WR deep and end-zone targets | Coleman is second behind Washington and second at punt returner. Miami describes his college role as slot-oriented; the reviewed explosive and end-zone plays are isolated camp or preseason observations. | Both small no-history priors remain inconclusive. |
| Will Kacmarek, TE deep and two-minute targets | Kacmarek is TE2, but Miami's preview emphasizes him as an elite run blocker while identifying Dulcich as the receiving lead. | Current role archetype conflicts with treating the receiving shares as established. Preserve and flag them. |
| Jaylen Wright, RB two-minute targets | Wright is RB2 and filled in for Achane in 2025, but no current source assigns receiving-down or two-minute work. | Retain the limited-history estimate as inconclusive. |
| Seydou Traore, TE deep and two-minute targets | The rookie is TE3 and described as an explosive passing prospect with varied college blocking duties. | Prospect traits and roster position cannot calibrate NFL situational shares. |
| DJ Herman, RB two-minute targets | Miami explicitly calls Herman a converted-linebacker fullback and lists him on the separate FB/TE line. [Source](https://www.miamidolphins.com/news/dolphins-sign-herman) | This conflicts with treating him as an ordinary RB receiving-share candidate and identifies a future position/package rule. |

## Chicago audit

The [current Bears roster](https://www.chicagobears.com/team/players-roster/)
controls active versus reserve status. The club's [depth chart](https://www.chicagobears.com/team/depth-chart)
is explicitly dated August 26 and still contains players released or moved to reserve
on August 30, so its ordering is retained as dated role evidence rather than treated
as a current roster source.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Rome Odunze, WR deep and end-zone targets | Odunze is active and was first on one August 26 receiver line. Chicago calls him a key playmaker and trusted target, and camp included long and repeated red-zone receptions. [Position preview](https://www.chicagobears.com/news/bears-2026-training-camp-position-preview-receiver), [deep report](https://www.chicagobears.com/news/bears-training-camp-report-sunday-aug-9), [red-zone report](https://www.chicagobears.com/news/bears-training-camp-report-wednesday-aug-19) | The leading role is supported, but the model's p24 shares—45.7% of team WR deep targets and 49.8% of team WR end-zone targets—are too concentrated to call validated from role reports and camp observations. Retain both values as explicitly inconclusive. |
| Luther Burden III, WR end-zone targets | Burden is active and was first on the other receiver line. He produced 652 yards and two touchdowns in 2025, drew strong praise from Ben Johnson, and finished one first-offense two-minute drill with a touchdown. [Offseason report](https://www.chicagobears.com/news/luther-burden-iii-showing-rapid-improvement-during-bears-offseason-program), [camp report](https://www.chicagobears.com/news/bears-training-camp-report-thursday-aug-6) | Overall prominence and one scoring play do not validate a stable end-zone share or the model's large historical adjustment. Retain and mark inconclusive. |
| Zavion Thomas, WR deep and end-zone targets | Thomas made the active roster and was third on one receiver line plus second at both return spots. The club reports 4.28 speed and reps with all three offenses, but the cited touchdowns followed short catches while the staff was still testing assignments and route reliability. [Sources](https://www.chicagobears.com/news/rookie-zavion-thomas-flashing-rare-speed-in-practice), [camp role](https://www.chicagobears.com/news/zavion-thomas-taking-advantage-of-opportunities-during-training-camp) | There is a plausible path to situational work, not a defensible NFL deep or end-zone share. Both no-history priors remain inconclusive. |
| Jahdae Walker, WR deep and end-zone targets | Walker made the active roster, was second behind Burden, rotated with every offensive unit, and was described as able to take the top off. He caught a deep-post touchdown from Caleb Williams and a later No. 1-offense red-zone touchdown. [Role report](https://www.chicagobears.com/news/bears-training-camp-report-thursday-aug-13), [deep report](https://www.chicagobears.com/news/bears-training-camp-report-sunday-aug-9), [red-zone report](https://www.chicagobears.com/news/bears-training-camp-report-wednesday-aug-26) | Repeated role-specific evidence supports retaining both small limited-history directions; exact counts remain unvalidated. |
| Sam Roush, TE deep and two-minute targets | Roush is the active third tight end. Chicago drafted him for a system with heavy 12/13 personnel and described his pass-game athleticism; a late joint practice included a contested downfield catch, but Johnson said his consistency was not yet at the desired level. [Draft role](https://www.chicagobears.com/news/bears-select-stanford-te-sam-roush-69th-overall-2026-nfl-draft), [camp report](https://www.chicagobears.com/news/bears-training-camp-report-joint-practice-with-titans-thursday-aug-27) | Retain the small deep-target direction. No source assigns two-minute routes, so that separate prior remains inconclusive. |
| Brittain Brown, three RB metrics | Chicago placed Brown on Reserve/Injured at final cuts, and the current roster still lists him there. Before the move, the club described a player who spent most of 2025 on the practice squad behind the established Swift-Monangai pair. [Transaction](https://www.chicagobears.com/news/chicago-bears-announce-roster-moves-initial-53-man-2026), [position preview](https://www.chicagobears.com/news/bears-2026-training-camp-position-preview-running-back) | Current status conflicts with treating him as an early-season role competitor. Preserve only the model's tiny reserve-adjusted scenarios; its active share is already zero. |

## Cleveland audit

The Browns' [current roster](https://www.clevelandbrowns.com/team/players-roster/)
and [initial 53-man roster](https://www.clevelandbrowns.com/news/browns-announce-initial-53-man-roster-heading-into-the-2026-season)
establish the active role pool. The club's final receiver review identifies five
solidified roles, while the RB and TE previews describe hierarchy without assigning
complete situational shares.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| KC Concepcion Jr. and Denzel Boston, WR deep and end-zone targets | Both rookies earned prominent first-team roles. Concepcion rotated with the first team and produced contested deep and red-zone plays; Boston moved to first-team X and repeatedly won on boundary and contested routes. [Concepcion role](https://www.clevelandbrowns.com/news/kc-concepcion-jr-carries-confidence-heading-into-the-regular-season), [Boston role](https://www.clevelandbrowns.com/news/denzel-boston-posts-standout-performance-on-day-12-training-camp-observations), [joint practice](https://www.clevelandbrowns.com/news/kc-concepcion-and-spencer-fano-shine-in-browns-joint-practice-with-the-bills-training-camp-observations) | Retain all four directional priors. The reports establish role type and first-team access, not exact regular-season conditional shares. |
| Raheim Sanders, three RB metrics | Sanders is the third back, but caught three first-team-QB passes in one two-minute period and continued to receive backfield targets. Cleveland separately added Michael Burton for short yardage and goal-line use. [RB preview](https://www.clevelandbrowns.com/news/analyzing-the-browns-running-back-room-heading-into-2026-position-preview), [two-minute report](https://www.clevelandbrowns.com/news/browns-defensive-line-continues-strong-camp-on-day-6-training-camp-observations), [role update](https://www.clevelandbrowns.com/news/todd-monken-provides-updates-on-browns-quarterback-competition-news-and-notes) | The small two-minute direction has direct support. Third-back status and Burton's explicit package conflict with Sanders' 24%-29% modeled goal-line shares; preserve and flag both rather than hand-editing them. |
| Dylan Sampson, three RB metrics | Sampson is in the top pair, had 271 receiving yards in 2025, and drew four team-period receptions plus a red-zone receiving touchdown in one camp practice. [Source](https://www.clevelandbrowns.com/news/browns-defense-shows-consistency-with-key-plays-on-day-14-training-camp-observations) | Retain the receiving-down direction. The evidence does not assign inside-5 or inside-10 work, so both goal-line priors remain inconclusive. |
| Blake Whiteheart, TE deep and two-minute targets | Whiteheart is the veteran behind Harold Fannin Jr. and has eight catches for 55 yards across two Browns seasons. He caught a second-team two-minute pass and multiple red-zone practice touchdowns. [TE preview](https://www.clevelandbrowns.com/news/evaluating-the-browns-tight-ends-ahead-of-the-2026-season-position-preview), [two-minute report](https://www.clevelandbrowns.com/news/browns-quarterbacks-show-off-the-deep-ball-in-two-minute-drill-on-day-13-training-camp-observations) | Retain the small two-minute direction; no source establishes his modeled deep share. |
| Tylan Wallace, WR deep and end-zone targets | Cleveland calls Wallace a veteran receiver-room anchor, and camp supplied both a downfield target and a red-zone touchdown. His broader NFL receiving volume remains small. [Receiver review](https://www.clevelandbrowns.com/news/wideouts-part-three-the-core-six), [signing](https://www.clevelandbrowns.com/news/browns-sign-wr-tylan-wallace) | Retain both small directions without increasing them; the evidence is role support, not numeric validation. |
| Quinshon Judkins, RB two-minute targets | Judkins leads the room after 827 rushing yards and seven touchdowns in 2025, but is returning from a dislocated ankle and fractured fibula and no reviewed source assigns two-minute work. [Source](https://www.clevelandbrowns.com/news/analyzing-the-browns-running-back-room-heading-into-2026-position-preview) | Lead-rusher status does not resolve receiving-down deployment; retain the estimate as inconclusive. |
| Carsen Ryan, TE deep and two-minute targets | Ryan made the roster as an active rookie TE3 after 45 catches for 620 college yards. Cleveland describes versatile developmental depth, not a current situational assignment. [Draft profile](https://www.clevelandbrowns.com/news/browns-select-te-carsen-ryan-with-the-no-248-pick-in-the-2026-nfl-draft) | Both no-history situational shares remain inconclusive. |
| Michael Burton, RB two-minute targets | Burton is the fullback, with documented backfield, inline, blocking, and route work; the explicit stated use is short yardage and goal line. [Camp report](https://www.clevelandbrowns.com/news/rookie-wide-receivers-show-out-linebacker-corps-impresses-on-day-3-training-camp-observations), [role update](https://www.clevelandbrowns.com/news/todd-monken-provides-updates-on-browns-quarterback-competition-news-and-notes) | Fullback usage is real, but the reviewed evidence does not establish a two-minute target role. Retain the small prior as inconclusive. |

## Detroit audit

Detroit's [current roster](https://www.detroitlions.com/team/players-roster/) and
[transaction log](https://www.detroitlions.com/team/transactions/) supersede the
cutdown snapshot for this pass: Isiah Pacheco moved to Reserve/Injured and Tyler
Conklin returned on September 1. Those moves change the competing role pools but do
not themselves identify situational shares.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Sam LaPorta, TE two-minute targets | LaPorta remains the lead tight end after 40 catches for 489 yards in nine 2025 games and caught passes in repeated first-team end-of-half or late-game periods. Conklin's return adds experienced receiving depth. [TE preview](https://www.detroitlions.com/news/2026-detroit-lions-training-camp-preview-tight-end-laporta-wright-conklin), [final camp practice](https://www.detroitlions.com/news/twentyman-training-camp-day-19-observations-goff-stbrown-gibbs) | Retain the leading two-minute direction, but do not call the model's 84.0% p24 share validated. |
| Isaac TeSlaa, WR end-zone targets | TeSlaa is the active No. 3 receiver after six touchdowns on 27 rookie targets. Detroit explicitly identifies his size, hands, body control, and catch radius as red-zone assets and documented a contested first-team camp touchdown. [Role report](https://www.detroitlions.com/news/campbell-second-year-wr-teslaa-feels-like-a-veteran-right-now), [red-zone report](https://www.detroitlions.com/news/detroit-lions-training-camp-day-13-observations-hutchinson-gibbs-teslaa) | Retain a leading end-zone direction; the concentrated 47.8% p24 share remains numerically unvalidated. |
| Amon-Ra St. Brown and Jameson Williams, WR end-zone targets | Both active starters have strong production and current scoring evidence. St. Brown finished 2025 with 11 touchdowns and ended camp with a back-of-end-zone score; Williams had seven touchdowns and repeated goal-line or end-zone opportunities. [WR preview](https://www.detroitlions.com/news/2026-training-camp-detroit-lions-wide-receiver-st-brown-williams-teslaa), [St. Brown report](https://www.detroitlions.com/news/twentyman-training-camp-day-19-observations-goff-stbrown-gibbs), [Williams report](https://www.detroitlions.com/news/detroit-lions-training-camp-day-8-observations-hutchinson-stbrown-hunter) | Retain both meaningful directions without treating overall touchdowns or camp plays as validation of the exact history-adjusted shares. |
| Tay Martin, WR deep and end-zone targets | Martin earned one of four active receiver spots with camp and special-teams production and occasional first-team reps. His preseason line was six catches for 41 yards and a two-yard touchdown; the late situational catches cited by Detroit came with the second team. [Role report](https://www.detroitlions.com/news/camp-notes-wide-receiver-battle-heating-up-martin-wilson-black), [late-camp report](https://www.detroitlions.com/news/detroit-lions-training-camp-day-18-observations-gibbs-brown-williams), [preseason recap](https://www.detroitlions.com/news/recap-lions-at-colts-dobbs-meeks-williams) | The WR4 path is real, but no regular deep or end-zone package is established; both priors remain inconclusive. |
| Sione Vaki, three RB metrics | Vaki took substantial first-team reps during Pacheco's absence and caught a pass in a documented first-team end-of-half drive. Detroit still describes him as a developing reserve and top special-teams player, while Gibbs is the bell-cow. [RB preview](https://www.detroitlions.com/news/2026-detroit-lions-training-camp-preview-running-back-gibbs-pacheco-vaki), [Pacheco update](https://www.detroitlions.com/news/camp-notes-campbell-reflects-on-lions-2026-training-camp-hutchinson-pacheco), [situational report](https://www.detroitlions.com/news/detroit-lions-training-camp-day-3-observations-whiteside-mahogany-teslaa) | Retain the secondary receiving-down direction. Pacheco's IR move creates opportunity but does not validate Vaki's roughly 19% modeled inside-10 and inside-5 shares; both remain inconclusive. |
| Jacob Saylors and Jabari Small, three RB metrics each | Both are active after Pacheco moved to reserve. Saylors earned trust on offense and special teams and led Detroit in preseason scrimmage yards; Small made the roster after a good camp and two practice-squad seasons. The reviewed catches and carries do not assign goal-line or two-minute targets. [Cutdown review](https://www.detroitlions.com/news/detroit-lions-nfl-breaking-down-the-initial-53-man-roster), [RB preview](https://www.detroitlions.com/news/2026-detroit-lions-training-camp-preview-running-back-gibbs-pacheco-vaki) | All six situational priors remain inconclusive. Backup membership is not a substitute for package-specific evidence. |
| Brock Wright, TE two-minute targets | Wright remains part of the top duo and is described as versatile but strongest as a run blocker. He caught 14 passes in 11 games in 2025 and a camp red-zone touchdown; Conklin is now back, and no source assigns two-minute work. [TE preview](https://www.detroitlions.com/news/2026-detroit-lions-training-camp-preview-tight-end-laporta-wright-conklin), [camp report](https://www.detroitlions.com/news/detroit-lions-training-camp-day-10-observations-mclaughlin-williams-rakestraw-hassanein) | Retain the estimate as inconclusive rather than translating multiple-TE intent into hurry-up targets. |
| Jackson Meeks, TE deep and two-minute targets | The converted receiver made the roster through consistent second-team receiving and special-teams work, with camp and preseason touchdowns. Conklin's September 1 return creates a four-player active TE room, and no source identifies a regular downfield package. [Camp review](https://www.detroitlions.com/news/10-players-impressed-detroit-lions-training-camp-williams-goff-stbrown), [role report](https://www.detroitlions.com/news/detroit-lions-training-camp-day-16-observations-dobbs-meeks-oneill) | Repeated situational reserve work supports retaining a small two-minute direction; the separate deep prior remains inconclusive. |
| Kendrick Law, WR deep and end-zone targets | Detroit placed Law on Reserve/Injured on June 17, and the current roster still lists him there. [Transaction log](https://www.detroitlions.com/team/transactions/) | Current status conflicts with an early-season role. Preserve only the frozen reserve-adjusted scenarios; current-active shares are already zero. |

## Baltimore audit

The [current Ravens roster](https://www.baltimoreravens.com/team/players-roster/)
confirms the active skill-position pool, while the [initial roster review](https://www.baltimoreravens.com/news/ravens-53-man-roster-cuts-set-announced-2026-initial)
adds unusually specific hierarchy: Henry is the workhorse, Hill the prized backup,
Ali the No. 3 and primary kick returner, Lane and Walker have substantial receiver
roles, and Adam Randall is on Reserve/Injured with a return designation.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Ja'Kobi Lane, WR deep and end-zone targets | Lane emerged as the projected No. 3 receiver and repeatedly won deep, contested, and red-zone opportunities, including work from Lamar Jackson and a preseason touchdown. [Early camp](https://www.baltimoreravens.com/news/jakobi-lane-soaring-catch-ravens-rookie-wide-receiver-practice-report-2026), [late joint practice](https://www.baltimoreravens.com/news/practice-report-ravens-commanders-defense-kyle-hamilton-roquan-smith-marlon-humphrey-jakobi-lane-rashod-bateman-devontez-walker) | Retain both meaningful directions; the no-history 20.5% deep and 21.6% end-zone p24 shares remain numerically unvalidated. |
| Devontez Walker, WR deep and end-zone targets | Baltimore calls Walker a field stretcher and projects a substantial role after four touchdowns on seven 2025 catches. Current camp included repeated deep work and a 62-yard first-team touchdown. [Position preview](https://www.baltimoreravens.com/news/zay-flowers-rashod-bateman-jakobi-lane-elijah-sarratt-devontez-walker-training-camp-competition-wide-receiver-2026), [joint practice](https://www.baltimoreravens.com/news/practice-report-ravens-commanders-defense-kyle-hamilton-roquan-smith-marlon-humphrey-jakobi-lane-rashod-bateman-devontez-walker) | Retain both limited-history directions without claiming the exact shares are validated. |
| Zay Flowers, WR end-zone targets | Flowers is active, a two-time Pro Bowler, and Baltimore's stated No. 1 target. One current 11-on-11 red-zone period produced two Flowers touchdowns. [Source](https://www.baltimoreravens.com/news/practice-report-ravens-play-through-rain-training-camp-2026) | Retain the major end-zone direction; one practice does not validate the history-adjusted 27.6% share. |
| Elijah Sarratt, WR deep and end-zone targets | Sarratt made the roster and caught six passes for 66 yards in the preseason opener, but the cutdown review assigns the substantial current roles to Lane and Walker. [Minicamp role](https://www.baltimoreravens.com/news/rookies-minicamp-elijah-sarratt-zion-young-ryan-eckley-jakobi-lane), [preseason](https://www.baltimoreravens.com/news/jakobi-lane-vega-ioane-jesse-minter-matt-hibner-ravens-eagles-2026-preseason) | Prospect traits and reserve production do not establish NFL deep or end-zone shares; both remain inconclusive. |
| Derrick Henry, inside-5 carries and two-minute targets | Henry remains the workhorse, and Declan Doyle described an immense role and large workload. A first-team camp drive ended with a short Henry touchdown. Baltimore separately identifies Hill as an elite third-down back. [RB preview](https://www.baltimoreravens.com/news/derrick-henry-justice-hill-adam-randall-rasheen-ali-training-camp-competion-preview-ravens-2026), [Doyle transcript](https://www.baltimoreravens.com/news/transcript-press-conferences-8-12-26) | Retain the dominant inside-5 direction. Overall workload does not resolve Henry's 26.8% two-minute target share, which remains inconclusive. |
| Justice Hill, RB two-minute targets | Hill is healthy, active, and described as a versatile runner, receiver, and blocker; position coach Willie Taggart called him one of the league's best third-down backs. [Source](https://www.baltimoreravens.com/news/transcript-press-conferences-8-8-26) | Retain the leading receiving-down direction; third down and two-minute are related but not identical, so the exact 54.7% share remains unvalidated. |
| Rasheen Ali, three RB metrics | Ali is the No. 3 back and primary kick returner behind Henry and Hill, and Baltimore explicitly says his offensive role is unclear. [Cutdown review](https://www.baltimoreravens.com/news/ravens-53-man-roster-cuts-set-announced-2026-initial) | Current role conflicts with treating his thin-history goal-line or 18.5% two-minute share as established. Preserve and flag all three values. |
| Matthew Hibner, TE deep and two-minute targets | Baltimore traded up for Hibner as a field-stretching, Isaiah Likely-type receiving prospect; he caught five passes for 61 yards in the preseason opener, including a 29-yard wheel route. Andrews remains the receiving leader, Smythe the veteran blocker, and no source assigns hurry-up work. [Draft role](https://www.baltimoreravens.com/news/matt-hibner-role-isaiah-likely-eric-decosta-talks-trade-up), [preseason](https://www.baltimoreravens.com/news/jakobi-lane-vega-ioane-jesse-minter-matt-hibner-ravens-eagles-2026-preseason) | Retain the small deep direction; the separate two-minute prior remains inconclusive. |
| Adam Randall, three RB metrics | Randall is on Reserve/Injured with a designation to return and must miss at least four games. Jesse Minter said he needs time to get fully healthy but could help later. [Source](https://www.baltimoreravens.com/news/transcript-press-conferences-8-31-26) | Current status conflicts with early-season work. Preserve only the small return-weighted scenarios; current-active shares are zero. |

## Green Bay audit

The [current Packers roster](https://www.packers.com/team/players-roster/) confirms
Lloyd, Brooks, and Johnson as the three active backs and Jacobs as Commissioner
Exempt. The [current roster review](https://www.packers.com/news/5-things-learned-from-gm-brian-gutekunst-about-packers-roster-sep-1-2026)
says Jacobs cannot practice or play, calls his 2026 timing uncertain, and identifies
Lloyd, Brooks, and the newly acquired Johnson as the Week 1 backfield.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| MarShawn Lloyd, three RB metrics | With Jacobs unavailable, Green Bay calls Lloyd the likely Week 1 feature back and says he was consistently available and improving throughout camp. The same account labels Brooks the third-down back; Lloyd has just six NFL carries and one reception. [Current role](https://www.packers.com/news/rb-marshawn-lloyd-as-ready-as-he-s-ever-been-to-help-packers-sep-2-2026) | Retain Lloyd as the leading inside-10 and inside-5 option without validating the exact 55.5% and 60.7% shares. His separate 37.8% two-minute target share remains inconclusive. |
| Kaleb Johnson, three RB metrics | Green Bay acquired Johnson on August 30. The 224-pound back has college bell-cow production and sees a fit in LaFleur's outside-zone scheme, but he arrived after camp with only 51 NFL offensive snaps and no assigned situational package. [Source](https://www.packers.com/news/it-s-all-go-pack-go-for-new-rb-kaleb-johnson-sep-1-2026) | All three goal-line and two-minute estimates remain inconclusive. Prospect traits and scheme fit do not identify a current conditional share. |
| Chris Brooks, RB inside-5 carries | Brooks is a durable active player trusted in pass protection and on special teams, but the club currently calls him the third-down back and provides no short-yardage assignment. [Camp return](https://www.packers.com/news/5-things-learned-at-packers-training-camp-aug-9-2026), [backfield role](https://www.packers.com/news/rb-marshawn-lloyd-as-ready-as-he-s-ever-been-to-help-packers-sep-2-2026) | Retain the history-adjusted estimate as inconclusive; general roster trust does not validate a 19.8% inside-5 share. |
| Josh Jacobs, RB inside-5 carries | Jacobs is on the commissioner's exempt list and cannot practice or play. Green Bay hopes he returns during 2026 but calls the timing uncertain. [Source](https://www.packers.com/news/5-things-learned-from-gm-brian-gutekunst-about-packers-roster-sep-1-2026) | Retain the model's zero current-active share and expose the small season count only as an availability scenario, not a forecasted return date. |
| Christian Watson, WR end-zone targets | Watson is active in the established top trio and scored three first-team camp touchdowns across the first two practices, including a slant from inside the 5, followed by another goal-line opportunity at Family Night. [Red-zone report](https://www.packers.com/news/5-things-learned-at-packers-training-camp-july-31-2026), [Family Night](https://www.packers.com/news/5-takeaways-from-packers-family-night-aug-7-2026) | Retain the leading end-zone direction; the exact 40.8% p24 share remains unvalidated. |
| Bo Melton, WR deep and end-zone targets | Melton is an active reserve and special-teams regular. He calls deep play his specialty, won a contested downfield opportunity in camp, and had a 45-yard 2025 touchdown; one first-team camp end-zone target did not become a catch. [Camp report](https://www.packers.com/news/5-things-learned-at-packers-training-camp-aug-10-2026), [roster context](https://www.packers.com/news/5-takeaways-from-packers-roster-decisions-2026) | Retain the secondary deep direction. One camp target does not establish a repeatable end-zone package, so that metric remains inconclusive. |
| Skyy Moore, WR deep and end-zone targets | Green Bay identifies Moore primarily as its full-time returner and a reserve receiver, with possible slot or gadget work but no assigned high-value receiving package. [Role report](https://www.packers.com/news/skyy-moore-ready-to-shine-on-packers-return-units-aug-7-2026), [roster review](https://www.packers.com/news/5-takeaways-from-packers-roster-decisions-2026) | Both roughly 6% receiving shares remain inconclusive. Active status and possible offensive touches are not metric-specific evidence. |
| Tucker Kraft, TE two-minute targets | Kraft is the lead tight end and caught all five targets with a touchdown upon returning to team work after an ACL tear. Jonnu Smith then joined as a veteran receiving option, and Green Bay has not assigned the hurry-up split. [Team-drill return](https://www.packers.com/news/5-things-learned-at-packers-training-camp-aug-16-2026), [current room](https://www.packers.com/news/new-packers-tight-ends-give-position-different-look-sep-2-2026) | Retain the history-adjusted 42.3% estimate as inconclusive pending Week 1 restrictions and observed two-minute personnel. |

## Seattle audit

The [current Seahawks depth chart](https://www.seahawks.com/team/depth-chart/)
lists Holani first, Price second, and Wilson third at running back. The club's
[initial roster review](https://www.seahawks.com/news/a-position-by-position-look-at-the-seahawks-initial-2026-53-man-roster)
is more informative than the order alone: Price and Holani figure to split the early
workload, Wilson was limited by injury, and Charbonnet will return from PUP only at an
unspecified point later in the season.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Jadarian Price, three RB metrics | Seattle's first-round rookie is second on the current depth chart after splitting first-team offseason work with Holani, who was usually first up. The club projects an early split, but also planned broad passing-game use and documented varied routes and a deep receiving touchdown. [RB outlook](https://www.seahawks.com/news/training-camp-storylines-does-rookie-jadarian-price-win-the-starting-job), [receiving work](https://www.seahawks.com/news/5-observations-from-day-4-of-2026-seahawks-training-camp) | The explicit split conflicts with Price's modeled 55.2% inside-10 and 58.8% inside-5 dominance. Retain his leading receiving-down direction, but not the exact 48.0% two-minute share. |
| George Holani, three RB metrics | Holani is first on the depth chart, was usually first up during offseason work, and is projected to split the early workload with Price. All three active backs rotated as pass-catchers in camp. [Offseason review](https://www.seahawks.com/news/takeaways-from-the-seahawks-2026-offseason-program-minicamp), [camp rotation](https://www.seahawks.com/news/tory-horton-elijah-arroyo-shine-other-observations-from-day-7-of-seahawks-training-camp) | Current hierarchy conflicts with treating Holani as a clearly minor 18.6% inside-10 and 13.9% inside-5 option. His 24.7% two-minute share remains inconclusive because no hurry-up role is assigned. |
| Emanuel Wilson, RB two-minute targets | Wilson is third on the depth chart, was injury-limited in camp, and is described primarily as a heavy downhill runner, though early camp included pass-catching work for all three backs. [Signing profile](https://www.seahawks.com/news/seahawks-sign-rb-emanuel-wilson), [roster review](https://www.seahawks.com/news/a-position-by-position-look-at-the-seahawks-initial-2026-53-man-roster) | The 21.8% two-minute share remains inconclusive rather than inferred from either general receiving work or rushing style. |
| Zach Charbonnet, RB inside-10 carries | Charbonnet remains on Reserve/PUP after an ACL tear and must miss at least four games. He led Seattle with 12 touchdowns in 2025, but there is no return timetable. [Source](https://www.seahawks.com/news/seahawks-rb-zach-charbonnet-placed-on-pup-list) | Retain zero current-active share and expose the small season count only as a return-eligible scenario; do not infer a return week. |
| Tory Horton, WR deep and end-zone targets | Horton is active in the locked top four after serving as Seattle's No. 3 receiver before injury. He scored twice in one 2025 game, and current camp included multiple touchdowns via a contested back-shoulder win and catch-and-run speed. [Current role](https://www.seahawks.com/news/tory-horton-is-back-and-ready-to-build-on-a-flashing-rookie-season), [camp report](https://www.seahawks.com/news/tory-horton-elijah-arroyo-shine-other-observations-from-day-7-of-seahawks-training-camp) | Retain meaningful deep and end-zone directions without claiming the exact 11.3% and 20.0% shares are validated. |
| Montorie Foster Jr., WR deep and end-zone targets | Foster earned the fifth active receiver spot after making big plays nearly every camp day, including multiple red-zone touchdowns and adjusted deep catches. He added a 5-yard preseason score and separated on a missed potential 68-yard touchdown. [Camp report](https://www.seahawks.com/news/6-observations-from-seahawks-football-fest), [preseason](https://www.seahawks.com/news/montorie-foster-jr-s-great-summer-continues-with-strong-showing-in-seahawks-preseason-opener) | Retain both small directions; repeated metric-specific evidence supports nonzero roles but not either exact roughly 6.7% share. |
| Eric Saubert, TE deep and two-minute targets | Saubert is second on the depth chart in a multiple-TE offense, but Seattle calls Barner the leading receiving threat and Arroyo the ascending pass catcher while emphasizing Saubert's physicality, leadership, and special-teams value. [TE outlook](https://www.seahawks.com/news/2026-seahawks-draft-preview-tight-end), [roster review](https://www.seahawks.com/news/a-position-by-position-look-at-the-seahawks-initial-2026-53-man-roster) | Depth and personnel multiplicity do not establish either roughly 19.3% situational target share; both remain inconclusive. |

## Arizona audit

The [current Cardinals depth chart](https://www.azcardinals.com/team/depth-chart)
lists Allgeier ahead of Love and McBride as the lead tight end. The
[initial roster review](https://www.azcardinals.com/news/the-first-team-and-53-man-roster-aftermath)
adds the important context: Love and Allgeier form a tandem, Benson moved to
Reserve/Injured without a return designation, and Long was acquired primarily to
restore blocking depth.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Jeremiyah Love, three RB metrics | Love is active and second behind Allgeier. Arizona has described the third overall pick as its eventual top back and a likely majority-snap player, while current work showed a first-team rotation, three catches in his preseason debut, and a 9-yard run immediately before a touchdown. He later missed time with an ankle injury. [Role outlook](https://www.azcardinals.com/news/jeremiyah-love-self-expectations-in-lockstep-with-cardinals-needs), [preseason use](https://www.azcardinals.com/news/jeremiyah-love-first-start-cardinals-top-pick-against-raiders-preseason), [injury update](https://www.azcardinals.com/news/jeremiyah-love-to-sit-for-now-with-ankle-injury) | Retain Love's co-leading goal-line and leading receiving-down directions, but do not call the exact roughly 44.6% goal-line or 51.2% two-minute shares validated. |
| Tyler Allgeier, RB two-minute targets | Allgeier is active, first on the depth chart, and rotated with Love in first-team work, but no reviewed source assigns receiving, protection, or hurry-up duties. | The 26.1% two-minute share remains inconclusive. A shared rushing role is not package-specific evidence. |
| Trey Benson, RB two-minute targets | Arizona waived Benson with a knee injury, and he is currently on Reserve/Injured without a designation to return. [Transaction log](https://www.azcardinals.com/team/transactions/) | Retain zero current-active share. The small season count is only a generic availability scenario, not a team-announced return path. |
| Trey McBride, TE deep targets | McBride is the active lead tight end after a 126-catch All-Pro season. LaFleur compares his flexible role to George Kittle's, and camp included a 25-yard touchdown. [Role report](https://www.azcardinals.com/news/mike-lafleur-sky-is-the-limit-for-trey-mcbride-within-new-offense) | Retain the dominant TE deep direction; the exact 77.9% p24 share remains unvalidated in the new offense. |
| Hunter Long, TE deep and two-minute targets | Long arrived August 30, is third behind McBride and Higgins, and was acquired to address the need for a pure blocking tight end while Reiman is unavailable. [Roster context](https://www.azcardinals.com/news/the-first-team-and-53-man-roster-aftermath) | The blocking assignment conflicts with treating either roughly 10% situational receiving share as established. Preserve and flag both frozen values. |
| Jalen Brooks and Reggie Virgil, WR deep and end-zone targets | Both made the active roster. Brooks produced 151 preseason yards and a contested back-shoulder touchdown; Virgil produced 109 yards plus a camp bomb touchdown and a difficult two-minute sideline catch. [Receiver competition](https://www.azcardinals.com/news/camaraderie-supersedes-intense-wide-receiver-battle-for-cardinals), [camp usage](https://www.azcardinals.com/news/running-back-roulette-qb-announcement-coming-and-camp-aftermath) | Repeated metric-specific evidence supports small nonzero directions, not either player's exact share or weekly activation. |
| Marvin Harrison Jr., WR end-zone targets | Harrison leads one receiver line, is moving around more in the new offense, and caught a first-unit 7-yard touchdown at the back of the end zone. [Camp report](https://www.azcardinals.com/news/marvin-harrison-jr-finds-way-to-smile-through-the-noise) | Retain Harrison as the leading WR end-zone direction without validating the exact 42.8% share. |

## Los Angeles Chargers audit

The [current Chargers depth chart](https://www.chargers.com/team/depth-chart)
identifies Hampton as the lead back and a three-player tight-end line, while the
[initial roster](https://www.chargers.com/news/initial-53-man-roster-2026) confirms
that all reviewed players remain active. The evidence is particularly useful here
because new caller Mike McDaniel changes the offense while Ingold brings direct
continuity with his prior system.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Omarion Hampton, three RB metrics | Los Angeles calls Hampton the backfield leader and expects the lion's share. Camp supplied a 4-yard goal-line touchdown and a 10-yard catch during the first offense's two-minute drive. [Role preview](https://www.chargers.com/news/training-camp-preview-omarion-hampton-fantasy), [goal-line work](https://www.chargers.com/news/training-camp-report-joint-practice-49ers-takeaways), [two-minute work](https://www.chargers.com/news/training-camp-report-elijah-molden-day-13) | Retain all three leading directions; the exact 64.4% inside-10, 62.7% inside-5, and 60.2% two-minute shares remain unvalidated. |
| Keaton Mitchell, RB two-minute targets | Mitchell is second on the chart and described as a change-of-pace runner/receiver, but no source assigns him a two-minute role. [Signing profile](https://www.chargers.com/news/agree-to-terms-keaton-mitchell-2026) | The 19.8% two-minute share remains inconclusive. |
| Alec Ingold, RB two-minute targets | Ingold is the starting fullback and reunites with McDaniel after four seasons and 48 starts together in Miami; the club calls him a key weapon with 75 career catches. [Source](https://www.chargers.com/news/agree-to-terms-pro-bowl-fullback-alec-ingold-2026) | System continuity and receiving history support a small direction, but not the exact 6.0% share or confirmed hurry-up personnel. |
| Charlie Kolar, TE deep and two-minute targets | Kolar is listed first in a three-way group and has current receiving evidence, but the club describes him primarily as an elite in-line blocker and secondary receiver, while Gadsden is the movable mismatch and caught a first-offense two-minute touchdown. [Role report](https://www.chargers.com/news/charlie-kolar-free-agency-contract), [camp report](https://www.chargers.com/news/training-camp-report-takeaways-final-practice-2026) | The division conflicts with Kolar owning roughly 46% of either situational TE pool. Preserve both estimates rather than reallocating them manually. |
| Brenen Thompson, WR deep and end-zone targets | Thompson is an active reserve who repeatedly caught long passes with the top offense and is explicitly called a potential deep threat. No reviewed source assigns a scoring-area package. [Role report](https://www.chargers.com/news/brenen-thompson-mike-mcdaniel-fantasy-2026), [deep work](https://www.chargers.com/news/training-camp-report-travis-burke-day-14) | Retain the 9.5% deep direction; the separate 9.9% end-zone share remains inconclusive. |
| KeAndre Lambert-Smith, WR deep and end-zone targets | Lambert-Smith made the active roster after a strong preseason. Harbaugh praised his downfield separation, and he caught a 20-yard pass in a first-offense two-minute drill; no current source assigns him a scoring-area role. [Preseason report](https://www.chargers.com/news/keandre-lambert-smith-amar-johnson-preseason-highlights) | Retain the small deep direction; keep the separate end-zone estimate inconclusive. |

## Pittsburgh audit

The [current Steelers depth chart](https://www.steelers.com/team/depth-chart/app)
puts Wilson on a starting receiver line and orders Freiermuth, Washington, and
Tonyan at tight end. The [initial 53](https://www.steelers.com/news/steelers-initial-2026-53-man-roster)
and its [role analysis](https://www.steelers.com/news/53-man-roster-analysis-steelers-keep-11-rookies-on-a-veteran-team)
supersede the early-camp RB ordering by identifying Heidenreich as the third back.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Roman Wilson, WR deep and end-zone targets | Wilson starts on one receiver line, is Pittsburgh's speed receiver, produced offseason plays over the top, caught a tightly covered deep ball from Rodgers, and drew a first-offense two-minute end-zone target. Rodgers called him a top-five camp performer who must play a big role. [Role context](https://www.steelers.com/news/assessing-versatility-key-for-first-practice), [deep catch](https://www.steelers.com/news/training-camp-report-aug-10), [current assessment](https://www.steelers.com/news/rodgers-reviews-progress-for-pass-catchers-and-fellow-passers) | Retain meaningful deep and end-zone directions; the exact 23.9% and 14.7% p24 shares remain unvalidated behind Metcalf and Pittman. |
| Germie Bernard, WR deep and end-zone targets | Bernard is in the active top four, plays inside and outside, drew a goal-line hurry-up target, and ended the preseason with five catches for 64 yards and a 13-yard touchdown. [Camp usage](https://www.steelers.com/news/training-camp-report-aug-3-x0715), [current assessment](https://www.steelers.com/news/rodgers-reviews-progress-for-pass-catchers-and-fellow-passers) | Retain both small directions without treating the exact 9.4% and 10.2% no-history shares as validated. |
| Eli Heidenreich, three RB metrics | Heidenreich won the No. 3 job and scored from 9 yards in the preseason finale. He also says he worked completely in the RB room and finished all three games with zero targets; the club separately identifies Warren and Dowdle as the top pair and Nowakowski as a possible goal-line carrier. [RB outlook](https://www.steelers.com/news/pre-camp-position-previews-running-back), [current role](https://www.steelers.com/news/steelers-blog-back-to-work) | Retain a small inside-10 direction. Inside-5 usage remains inconclusive, and observed receiving deployment conflicts with the modeled 16.2% two-minute share. |
| Pat Freiermuth, TE two-minute targets | Freiermuth starts and is one half of the projected 1A-1B tandem. A first-team two-minute drive included a fourth-down conversion to him and a 23-yard winning touchdown with nine seconds left. [Source](https://www.steelers.com/news/training-camp-report-aug-1-x3537) | Retain Freiermuth as the leading TE two-minute direction; one drive does not validate the exact 78.2% share. |
| Darnell Washington, TE two-minute targets | Washington is TE2 and the other half of the projected 1A-1B pair; camp included a roughly 20-yard reception from Rodgers during situational work. [Room preview](https://www.steelers.com/news/pre-camp-position-previews-tight-end), [camp report](https://www.steelers.com/news/training-camp-report-aug-8-x9411) | Retain a small two-minute direction without claiming the exact 11.7% share or every hurry-up snap. |
| Robert Tonyan, TE deep and two-minute targets | Tonyan earned TE3 after a productive camp and has prior familiarity with Rodgers, McCarthy, and Angelichio. He caught a 5-yard pass in a backup hurry-up drive, but no current source identifies a deep package. [Hurry-up use](https://www.steelers.com/news/training-camp-report-aug-3-x0715), [roster analysis](https://www.steelers.com/news/53-man-roster-analysis-steelers-keep-11-rookies-on-a-veteran-team) | Retain a small two-minute direction; the separate deep share remains inconclusive. |

## Tennessee audit

The [current Titans roster](https://www.tennesseetitans.com/team/players-roster/)
confirms every reviewed player is active. The club's [August 25 depth chart](https://www.tennesseetitans.com/team/depth-chart)
is explicitly unofficial and predates final cuts, so its ordering is dated evidence;
the [initial 53](https://www.tennesseetitans.com/news/a-position-by-position-look-at-the-titans-initial-53-man-roster-x5666)
controls membership.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Carnell Tate, WR deep and end-zone targets | Tate starts in the three-WR depth set. The fourth overall pick caught a 50-plus-yard first-team OTA ball and a 70-yard camp touchdown, then produced five red-zone touchdowns across two practices and two touchdowns among seven catches in the final joint practice. He also had zero catches on five preseason targets through two games. [Deep work](https://www.tennesseetitans.com/news/titans-rookie-carnell-tate-working-to-make-an-impact-one-practice-at-a-time), [red-zone work](https://www.tennesseetitans.com/news/ten-observations-from-titans-training-camp-on-sunday), [final practice](https://www.tennesseetitans.com/news/titans-rookie-wr-carnell-tate-ends-training-with-a-bang-during-practice-with-bears) | Retain Tate as a major deep and end-zone direction. Repeated practice evidence does not validate the exact 26.9% and 26.8% no-history p24 shares. |
| Tony Pollard, RB inside-5 carries | Pollard is first on the dated chart and one of Saleh's two bell cows. Joint practices included a receiving touchdown near the goal line and a separate run through multiple would-be tacklers for a score. [RB roles](https://www.tennesseetitans.com/news/heading-into-year-4-titans-rb-tyjae-spears-working-to-help-spark-a-change), [scoring work](https://www.tennesseetitans.com/news/ten-observations-from-thursday-s-titans-vs-bears-joint-practice) | Retain Pollard as the leading inside-5 direction without validating the exact 44.5% share. |
| Tyjae Spears, RB two-minute targets | Saleh calls Spears a bell cow and very good third-down back, specifically praising his routes. Spears led the first three camp practices with 12 catches, reached 19 by practice eight, and added five in the final joint practice. [Role report](https://www.tennesseetitans.com/news/heading-into-year-4-titans-rb-tyjae-spears-working-to-help-spark-a-change), [camp receiving](https://www.tennesseetitans.com/news/ten-observations-from-titans-training-camp-on-saturday) | Retain Spears as the leading receiving-down direction; third down does not validate the exact 47.7% two-minute share. |
| Tony Pollard, RB two-minute targets | Saleh calls Pollard an elite pass protector and very good receiver as well as a bell cow; current camp included a contested 50-yard catch. [Role report](https://www.tennesseetitans.com/news/heading-into-year-4-titans-rb-tyjae-spears-working-to-help-spark-a-change), [joint practice](https://www.tennesseetitans.com/news/ten-observations-from-thursday-s-titans-vs-bears-joint-practice) | Retain a substantial secondary receiving-down direction without validating the 34.1% two-minute share or identifying which back opens hurry-up periods. |
| Nicholas Singleton, three RB metrics | Singleton made the roster as the fourth listed back after recovering from an offseason college injury and a one-week camp injury. He showed power plus receiving ability, including a disputed touchdown run and three catches with a short backup-offense score, but Tennessee says it plans to ride Pollard and Spears. [RB preview](https://www.tennesseetitans.com/news/titans-2026-training-camp-preview-a-look-at-the-running-backs), [return practice](https://www.tennesseetitans.com/news/ten-observations-from-titans-training-camp-on-tuesday-x8102) | All three roughly 13%-14% no-history shares remain inconclusive. Reserve production is not an assigned goal-line or two-minute package, while active status does not justify forcing the estimates to zero. |

## Cincinnati audit

The [current Bengals depth chart](https://www.bengals.com/team/depth-chart) and
[initial 53](https://www.bengals.com/news/bengals-initial-2026-53-man-roster-feature)
confirm the roster hierarchy used below. The depth page does not label itself
official or unofficial, so it is treated as current club-published ordering rather
than a binding game-plan declaration.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Colbie Young, WR deep and end-zone targets | Young is active and second behind Tee Higgins on one receiver line. The fourth-round rookie caught a spring deep fade, won a contested deep out plus a red-zone slant touchdown, and later added another deep sideline win and tight-window touchdown. [Spring role](https://www.bengals.com/news/tee-higgins-channels-idol-a-j-green-as-he-mentors-bengals-rookie-wr-colbie-young), [camp usage](https://www.bengals.com/news/quick-hits-d-line-keeps-flexing-rookie-wr-colbie-young-s-big-leap) | Retain small deep and end-zone directions without validating the exact 9.5% and 9.8% no-history shares. |
| Dohnte Meyers, WR deep targets | Meyers made the roster as a reserve and return option after Cincinnati called him its most consistent rookie skill player and the surprise player of camp. He caught a touchdown bomb, a separate 65-yard pass, and stayed after the final open practice for deep work with Joe Burrow. [Role profile](https://www.bengals.com/news/training-camp-report-how-dohnte-meyers-got-here-and-the-rookie-invasion), [vertical work](https://www.bengals.com/news/final-five-observations-2026-bengals-training-camp) | Retain a small vertical direction; the exact 6.0% no-history share and regular-season route volume are not validated. |
| Dohnte Meyers, WR end-zone targets | The stadium practice produced a touchdown bomb, but official reporting does not establish the catch location or assign a red-zone package. [Source](https://www.bengals.com/news/back-with-fans-burrow-and-chase-send-calling-card-to-2026) | Leave the 6.2% no-history end-zone share explicitly inconclusive; a touchdown is not necessarily an end-zone target. |
| Chase Brown, RB two-minute targets | Brown leads the backfield, set a team RB record with 69 catches in 2025, trains as a receiver, and says Zac Taylor challenged him to become reliable on third down. [Backfield outlook](https://www.bengals.com/news/2026-position-preview-running-backs-chase-brown), [receiving role](https://www.bengals.com/news/training-camp-report-2026-day-2-july-30-chase-brown-erick-all) | Retain Brown as a major receiving-down direction; third down does not validate the exact 46.3% two-minute share. |
| Samaje Perine, RB two-minute targets | Perine is RB2; Cincinnati identifies him as a reliable receiver and pass protector, and his current bio records 196 career catches. [Role history](https://www.bengals.com/news/reports-bengals-bring-back-playoff-hero-samaje-perine), [current bio](https://www.bengals.com/team/players-roster/samaje-perine/) | Retain Perine as the other major receiving-down direction without validating the exact 45.3% share or resolving the hurry-up split with Brown. |
| Tahj Brooks, RB inside-5 and inside-10 carries | Brooks is RB3. Cincinnati originally projected the 214-pound back for complementary depth, especially short yardage and pass protection; its 2026 outlook emphasizes special teams and competition for touches. [Projected role](https://www.bengals.com/news/bengals-select-rb-tahj-brooks-with-193rd-overall-pick), [current outlook](https://www.bengals.com/news/2026-position-preview-running-backs-chase-brown) | Retain small goal-line directions without validating the exact 8.6% and 8.1% limited-history shares. |
| Tahj Brooks, RB two-minute targets | Brooks caught a camp touchdown and says his receiving and routes improved, but the club assigns no hurry-up or third-down role and keeps Brown and Perine above him. [Source](https://www.bengals.com/news/five-observations-day-10-bengals-training-camp-2026) | The 8.5% limited-history share remains inconclusive. |
| Mike Gesicki, TE deep targets | Cincinnati calls Gesicki the room's big receiving threat and a receiver-like matchup despite his TE2 chart placement. He caught a 17-yard pass that he called his deep ball in situational work. [TE outlook](https://www.bengals.com/news/2026-position-preview-tight-ends-mike-gesicki-tanner-hudson), [deep use](https://www.bengals.com/news/training-camp-report-josh-newton-ja-marr-chase-2026) | Retain Gesicki as the leading TE deep direction; the exact 74.3% share is not validated in a five-TE room. |
| Erick All, TE deep and two-minute targets | All is active after being cleared following multiple knee surgeries, but he missed all of 2025 and Cincinnati's current outlook emphasizes physical blocking rather than either queued target package. [Health](https://www.bengals.com/news/five-observations-day-2-bengals-training-camp-2026), [role](https://www.bengals.com/news/2026-position-preview-tight-ends-mike-gesicki-tanner-hudson) | Both limited-history shares remain inconclusive. |
| Drew Sample, TE deep targets | Sample is listed first and led the room with 12 starts in 2025, but Cincinnati defines him as a key blocker; he caught 15 passes for 106 yards while Gesicki owns the explicit receiving designation. [Current bio](https://www.bengals.com/team/players-roster/drew-sample/), [room outlook](https://www.bengals.com/news/2026-position-preview-tight-ends-mike-gesicki-tanner-hudson) | The role division conflicts with treating Sample's 10.3% deep share as established. Preserve it for auditability rather than hand-transfer targets. |

## New Orleans audit

The [current roster](https://www.neworleanssaints.com/team/rosters) separates active,
Injured Reserve, and Injured Reserve/Designated to Return players. The club's
[depth chart](https://www.neworleanssaints.com/team/depth-chart) is explicitly
unofficial, so it is useful ordering evidence but not a game-plan declaration. The
[final cut transaction](https://www.neworleanssaints.com/news/new-orleans-saints-53-man-roster-cut-transactions-august-30-2026-nfl-season)
controls where those two sources differ from earlier camp expectations.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Bryce Lance, WR deep and end-zone targets | Lance is one of only four active wideouts. The 6-foot-3, 4.34-speed fourth-rounder caught two long camp touchdowns, then two first-team red-zone touchdowns against the Rams. [Active receiver context](https://www.neworleanssaints.com/news/kicker-daniel-carlson-made-most-of-limited-preseason-time-with-new-orleans-saints), [deep work](https://www.neworleanssaints.com/news/key-takeaways-from-saints-training-camp-day-11), [red-zone work](https://www.neworleanssaints.com/news/new-orleans-saints-complete-grueling-stretch-with-joint-practice-against-rams) | Retain meaningful deep and scoring-zone directions; repeated camp evidence still does not validate the exact 23.4% and 21.3% no-history shares. |
| Barion Brown, WR deep targets | Brown is another of the four active wideouts and first at both return positions. The 4.30-speed field-stretching prospect received early-camp deep shots and caught four passes for 53 yards in the opener. [Prospect role](https://www.neworleanssaints.com/news/barion-brown-saints-draft-pick-2026), [camp use](https://www.neworleanssaints.com/news/key-takeaways-from-saints-training-camp-day-11), [preseason production](https://www.neworleanssaints.com/news/2026-nfl-preseason-week-1-jacksonville-jaguars-vs-new-orleans-saints-game-recap) | Retain a small vertical direction without validating the exact 10.2% no-history share; return responsibilities may constrain routes. |
| Barion Brown, WR end-zone targets | Brown scored on a 7-yard preseason jet sweep, but that was a carry rather than a target; reviewed reporting supplies no thrown end-zone target or red-zone receiving package. [Source](https://www.neworleanssaints.com/news/new-orleans-saints-clean-up-play-in-preseason-finale-prepare-for-roster-cut-sunday) | Leave the 9.3% no-history end-zone share explicitly inconclusive. |
| Jordyn Tyson, WR deep and end-zone targets | The eighth overall pick had a recurrent hamstring issue managed from the offseason onward and is now on Injured Reserve/Designated to Return. [Camp health](https://www.neworleanssaints.com/news/new-orleans-saints-first-round-pick-jordyn-tyson-set-to-open-training-camp), [transaction](https://www.neworleanssaints.com/news/new-orleans-saints-53-man-roster-cut-transactions-august-30-2026-nfl-season) | Current status conflicts with an immediate active role. Preserve the model's zero current-active shares and small return-weighted season counts rather than guessing a return date or post-return role. |
| Oscar Delp, TE deep and two-minute targets | Delp is TE3 behind Juwan Johnson and Noah Fant. His 4.49 speed, multi-spot profile, and third-round investment create receiving upside, but he said he was still trying to find a path onto the field; the reviewed preseason score was a 1-yard touchdown. [Athletic profile](https://www.neworleanssaints.com/news/oscar-delp-saints-draft-pick-2026), [projected role](https://www.neworleanssaints.com/news/new-orleans-saints-add-two-georgia-bulldogs-on-second-day-of-nfl-draft-2026), [camp context](https://www.neworleanssaints.com/news/key-takeaways-from-saints-training-camp-media-availability-day-8) | Both no-history shares remain inconclusive; none of the evidence assigns a deep or two-minute package. |
| Audric Estimé, RB two-minute targets | Estimé is the fourth name across the current RB tiers. He says he can play all three downs and caught three passes for 22 yards in the finale, after which the club called him and Miller worthy reserve options behind Travis Etienne. [Role case](https://www.neworleanssaints.com/news/several-saints-prepare-to-make-a-final-case-for-roster-spots-in-the-preseason-finale), [finale notes](https://www.neworleanssaints.com/news/2026-nfl-preseason-week-3-dallas-cowboys-vs-new-orleans-saints-game-notes) | Retain a small receiving-down direction without treating all-three-down capability as proof of the exact 8.0% two-minute share. |
| Kendre Miller, RB two-minute targets | Miller is the next charted back after Etienne and Alvin Kamara. The club records 20 career catches for 180 yards and expects a larger injury-conditioned role while Kamara is down. [Source](https://www.neworleanssaints.com/news/new-orleans-saints-running-back-kendre-miller-hoping-for-good-health-productive-season-2026) | Retain a small receiving-down direction without validating the exact 8.0% share or assigning Miller the hurry-up package. |
| Devin Neal, RB two-minute targets | Neal is on ordinary Injured Reserve and absent from the current RB chart; the final transaction separately identifies Tyson and Jaylan Ford as designated for return. [Source](https://www.neworleanssaints.com/news/new-orleans-saints-53-man-roster-cut-transactions-august-30-2026-nfl-season) | Current status conflicts with active receiving-down work. Preserve the frozen zero current-active share and negligible 0.10-event availability scenario rather than forcing a manual override. |

## Tampa Bay audit

The [current roster](https://www.buccaneers.com/team/players-roster/) and
[club-published depth chart](https://www.buccaneers.com/team/depth-chart) agree on
the active three-back, six-receiver, and four-tight-end rooms. The
[initial 53-man review](https://www.buccaneers.com/news/bucs-go-heavy-in-trenches-on-first-53-man-roster-of-2026)
adds role context but explicitly notes that the opening roster can still change, so
the chart is treated as current ordering rather than a situational usage guarantee.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Bucky Irving, RB inside-5 and inside-10 carries | Irving is first on the chart and fully cleared. Todd Bowles calls him the clear starter and No. 1 to Kenny Gainwell's 1B; Zac Robinson calls him the focal back and says he can run every concept. [Hierarchy](https://www.buccaneers.com/news/bucs-takeaways-2026-annual-meeting-lb-competition-ahead), [caller fit](https://www.buccaneers.com/news/three-pressing-questions-buccaneers-in-2026), [health](https://www.buccaneers.com/news/bucky-irving-full-go-feeling-stronger-from-adversity) | Retain Irving as a major short-yardage direction without validating the exact 43.3% inside-10 or 32.7% inside-5 shares; no source assigns the goal-line split. |
| Ted Hurst III, WR deep and end-zone targets | Hurst is active and second behind Jalen McMillan on one receiver line. Tampa Bay calls the 6-foot-4 rookie an X, vertical, and red-zone threat; camp produced a back-shoulder fade touchdown and later joint-practice success as the team's vertical threat. [Projected role](https://www.buccaneers.com/news/2026-state-of-the-bucs-post-draft-edition-offense), [red-zone work](https://www.buccaneers.com/news/training-camp-takeaways-practice-day-10-2026), [joint practice](https://www.buccaneers.com/news/takeaways-from-buccaneers-jaguars-joint-practice-day-1-2026) | Retain small deep and end-zone directions without validating the exact 9.9% and 10.6% no-history shares or his weekly route volume. |
| Sean Tucker, RB inside-5 carries | Tucker is RB3, but Tampa Bay explicitly calls him an excellent 2025 goal-line back after seven rushing touchdowns; he added a 1-yard preseason score in 2026. [Role history](https://www.buccaneers.com/news/training-camp-goals-2026-buccaneers-numbers-40-49), [preseason score](https://www.buccaneers.com/news/bucs-chiefs-preseason-week-2-recap-postgame-report-2026) | Retain a meaningful goal-line direction despite general depth order; the exact 33.8% share under Robinson is not validated. |
| Sean Tucker, RB two-minute targets | The club notes improved pass protection but defines Irving and Gainwell as the one-two backfield and assigns Tucker no receiving or hurry-up package. [Source](https://www.buccaneers.com/news/training-camp-goals-2026-buccaneers-numbers-40-49) | Leave the 9.8% limited-history share explicitly inconclusive; better protection is not direct two-minute evidence. |
| Payne Durham, TE deep and two-minute targets | Durham is TE2, but Tampa Bay calls him a valuable blocker and reports one reception across 354 snaps in 2025. Cade Otton routinely owns mid-90% snap shares and roughly 50 catches per season. [Current room](https://www.buccaneers.com/news/bucs-go-heavy-in-trenches-on-first-53-man-roster-of-2026), [2025 role](https://www.buccaneers.com/news/2025-state-of-the-bucs-tight-ends) | The receiving hierarchy conflicts with treating Durham's 23.3% deep and 13.3% two-minute shares as established. Preserve both for auditability. |
| Ko Kieft, TE deep and two-minute targets | Kieft is TE3 and explicitly a blocking specialist with a limited receiving role: no catches before his 2025 injury and one over the prior two seasons. His 2-yard backup-offense preseason touchdown does not establish either queued package. [Role](https://www.buccaneers.com/news/bucs-re-sign-te-ko-kieft-2026-nfl-free-agency), [preseason score](https://www.buccaneers.com/news/bucs-chiefs-preseason-week-2-recap-postgame-report-2026) | The current role conflicts with treating the 8.0% deep and 7.0% two-minute shares as established. Preserve the small frozen estimates without transferring them. |

## San Francisco audit

The [current roster](https://www.49ers.com/team/players-roster/) confirms a three-back
active room and six active wideouts, while the [August 30 transaction](https://www.49ers.com/news/49ers-announce-moves-for-initial-53-man-roster-x1231)
places Isaac Guerendo on Reserve/PUP. The club's [initial-roster review](https://www.49ers.com/news/position-by-position-breakdown-of-the-49ers-2026-initial-roster)
adds context but does not establish package shares.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| De'Zhaun Stribling, WR deep and end-zone targets | The active No. 33 pick has 4.36 speed and a documented downfield profile. He caught multiple deep camp passes and a 32-yard preseason sideline ball against Tennessee's first-team defense, then scored twice in joint-practice red-zone work, including a contested back-corner catch. [Draft profile](https://www.49ers.com/news/49ers-select-de-zhaun-stribling-with-the-no-33-pick-in-the-2026-nfl-draft), [preseason role](https://www.49ers.com/news/breaking-down-wr-de-zhaun-stribling-s-impressive-preseason-debut), [red-zone work](https://www.49ers.com/news/day-14-of-2026-training-camp-kaelon-black-returns-for-joint-practice-with-chargers) | Retain meaningful deep and end-zone directions without validating the exact 21.1% and 20.5% no-history shares in a crowded veteran room. |
| Kaelon Black, RB inside-5 and inside-10 carries | The active 208-pound third-rounder was drafted for natural, physical running and yards after contact. On returning from an adductor injury, he took team and red-zone carries and scored on a goal-line run. [Coach evaluation](https://www.49ers.com/news/lynch-shanahan-break-down-2026-draft-strategy), [direct usage](https://www.49ers.com/news/day-14-of-2026-training-camp-kaelon-black-returns-for-joint-practice-with-chargers) | Retain Black as a meaningful secondary short-yardage direction; one practice does not validate the exact 24.2% inside-10 or 24.1% inside-5 shares behind Christian McCaffrey. |
| Kaelon Black, RB two-minute targets | Black caught 55 passes with six receiving touchdowns in college, but Shanahan says he was not heavily featured as a receiver and describes that skill set as developmental. No reviewed source assigns him hurry-up or protection work. [Profile](https://www.49ers.com/news/5-things-to-know-running-back-kaelon-black), [coach evaluation](https://www.49ers.com/news/lynch-shanahan-break-down-2026-draft-strategy) | Leave the 23.4% no-history share and 4.93-event season count explicitly inconclusive. Receiving upside is not a current two-minute assignment. |
| Jordan James, three RB metrics | James is active but played only three games as a rookie and missed most of 2026 camp with a rib injury. His preseason-finale return produced eight carries for 35 yards and one 20-yard catch; no reviewed source assigns inside-5, inside-10, or two-minute work. [Rookie review](https://www.49ers.com/news/year-one-review-evaluating-the-49ers-2025-draft-class), [preseason return](https://www.49ers.com/news/49ers-defeat-raiders-18-12-in-preseason-finale-5-takeaways-from-sfvslv) | Keep all three no-history shares inconclusive. Active depth and one productive preseason appearance do not establish situational deployment. |
| Isaac Guerendo, RB two-minute targets | Guerendo is on Reserve/PUP and outside the active three-back room. [Transaction](https://www.49ers.com/news/49ers-announce-moves-for-initial-53-man-roster-x1231) | Current status conflicts with immediate two-minute work. Preserve the zero current-active share and 0.79-event return-weighted scenario rather than guessing a return date or transferring opportunity. |

## Buffalo audit

The [current roster](https://www.buffalobills.com/team/players-roster/) and
[dated initial 53](https://www.buffalobills.com/news/position-by-position-look-at-bills-initial-53-man-roster-2026)
confirm a three-back, five-receiver, and four-tight-end active room. Buffalo's
[current depth page](https://www.buffalobills.com/team/depth-chart) explicitly says
the 2026 chart has not yet been announced, so no ordering below is inferred from
that page. Historical receiving totals come from
[Pro Football Reference](https://www.pro-football-reference.com/teams/buf/2025.htm),
not a fantasy projection site.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Khalil Shakir, WR deep and end-zone targets | Shakir follows DJ Moore in the expected receiver pecking order after leading Buffalo with 72 catches and 719 yards in 2025. Joe Brady explicitly contrasts Moore's outside/downfield role with Shakir attacking the middle and inside zones; Shakir also caught touchdowns in two current red-zone practices. [Role definition](https://www.buffalobills.com/news/what-we-learned-from-bills-head-coach-joe-brady-at-nfl-meetings-2026-phoenix), [camp scoring](https://www.buffalobills.com/news/what-we-learned-about-the-bills-on-day-9-of-training-camp-2026) | Retain reduced but nonzero deep and end-zone directions without validating the exact 16.4% and 9.4% history-adjusted shares. |
| Keon Coleman, WR end-zone targets | Buffalo defines Coleman as its physical, contested-catch receiver. After four receiving touchdowns in 2025, he finished a current red-zone period with a toe-tap score in the front-right corner. [Role outlook](https://www.buffalobills.com/news/what-are-the-top-3-training-camp-storylines-for-the-bills-offense), [direct usage](https://www.buffalobills.com/news/what-we-learned-about-the-bills-on-day-9-of-training-camp-2026) | Retain Coleman as the leading WR scoring-area direction; one practice and prior touchdowns do not validate the exact 39.5% share. |
| Skyler Bell, WR deep targets | The active fourth-round rookie is described as an inside-outside separator who can threaten all three levels and explicitly identifies deep-ball work among his skills. He missed several weeks, then caught seven passes for 49 yards in the finale; no reviewed report documents a 20-plus-air-yard target. [Draft profile](https://www.buffalobills.com/news/i-m-explosive-versatile-3-things-to-know-about-bills-2026-nfl-draft-pick-wr-skyler-bell), [preseason return](https://www.buffalobills.com/news/top-3-things-we-learned-bills-vs-steelers-preseason-week-3-2026) | Retain a small deep direction from the roster path and explicit field-stretching profile, but do not treat the exact 6.8% no-history share or weekly routes as validated. |
| Skyler Bell, WR end-zone targets | Bell scored 13 receiving touchdowns in his final college season, but his only reviewed Buffalo touchdown was a jet-sweep carry rather than a target; no current report assigns an end-zone receiving package. [Source](https://www.buffalobills.com/news/top-3-things-we-learned-bills-vs-steelers-preseason-week-3-2026) | Leave the 6.5% no-history end-zone share explicitly inconclusive. |
| Ty Johnson, RB two-minute targets | The same three backs return under Joe Brady. Johnson was previously called Buffalo's best third-down back, caught 25 passes for 284 yards and three scores in 2024, then 24 for 263 and two in 2025; current camp also showed an Allen pressure outlet to him. [Prior role](https://www.buffalobills.com/news/bills-re-sign-rb-ty-johnson-to-two-year-deal-agree-to-terms-with-fb-reggie-gilliam-on-one-year-deal), [current usage](https://www.buffalobills.com/news/what-we-learned-about-the-bills-on-day-3-of-training-camp-2026) | Retain Johnson as a major receiving-down direction; third-down continuity does not prove the exact 41.3% two-minute share or every hurry-up snap. |
| Ray Davis, RB two-minute targets | Davis returns in that room after 10 catches on 13 targets in 2025, but Buffalo's clearest recent role description centers on his All-Pro return work and no current source assigns him hurry-up, third-down, or protection responsibility. [Role evidence](https://www.buffalobills.com/news/2025-buffalo-bills-end-of-season-awards) | Keep the 14.1% history-adjusted share explicitly inconclusive; a small receiving sample and room continuity are insufficient package evidence. |
| Jackson Hawes, TE deep targets | Hawes caught 16 of 19 targets for 187 yards and three scores as a rookie, including a documented 26-yard deep-middle touchdown. Current work added a sideline touchdown and two joint-practice scores while Allen emphasized that Hawes is more than a blocker. [Prior deep result](https://www.buffalobills.com/news/bills-13-dolphins-30-final-score-game-recap-highlights), [current sideline use](https://www.buffalobills.com/news/return-of-blue-red-bills-players-reaction-to-highmark-stadium-practice-observations-and-more) | Retain a small deep direction without validating the exact 10.4% limited-history share in a four-TE room. |
| Jackson Hawes, TE two-minute targets | The joint-practice report documents Hawes' receiving touchdowns outside the named hurry-up period, then identifies Dalton Kincaid as the player with a 55-yard score during the two-minute drill. [Source](https://www.buffalobills.com/news/what-we-learned-from-the-bills-joint-practice-with-the-browns) | Leave Hawes' 9.6% two-minute share explicitly inconclusive; receiving growth does not establish hurry-up deployment. |

## Washington audit

The [initial 53-man review](https://www.commanders.com/news/washington-commanders-roster-2026-breakdown)
controls active membership for this pass: three running backs, seven wide receivers,
and four tight ends. The club's [unofficial depth chart](https://www.commanders.com/team/depth-chart)
supports limited ordering evidence but also lists players outside that initial 53, so
it is not treated as a clean active-roster source. Historical 2025 production comes
from [Pro Football Reference](https://www.pro-football-reference.com/teams/was/2025.htm),
not a fantasy projection site.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Antonio Williams, WR deep targets | Washington identifies the active third-round rookie as its primary slot receiver and says he can also align outside, but explicitly assigns vertical-threat roles to Treylon Burks and Dyami Brown. The unofficial chart places Williams behind Stefon Diggs and Burks on one receiver line, and no reviewed report documents a 20-plus-air-yard Williams target. [Current role](https://www.commanders.com/news/5-takeaways-from-dan-quinn-and-adam-peters-joint-press-conference), [room review](https://www.commanders.com/news/washington-commanders-roster-2026-breakdown) | The slot role supports real routes but conflicts with treating Williams' 20.7% no-history deep share as established ahead of both named vertical threats. Preserve and flag the frozen value. |
| Antonio Williams, WR end-zone targets | Williams caught a two-point conversion, multiple August 11 touchdowns including one in a two-minute drill, and a contested front-corner red-zone score against Miami the next day. [August 11](https://www.commanders.com/news/commanders-training-camp-notebook-jayden-daniels-trey-amos), [Miami joint practice](https://www.commanders.com/news/commanders-dolphins-training-camp-practice-notes) | Repeat scoring-area involvement supports a meaningful direction, not the exact 21.1% share; several reps came with top receivers absent, reserve personnel, or backup quarterbacks. |
| Kaytron Allen, RB inside-5 and inside-10 carries | The rookie made the three-back roster. Washington repeatedly defines his distinct contribution as physical, downhill, dirty-yard running and says he could be most valuable in short-yardage situations. [Projected role](https://www.commanders.com/news/kaytron-allen-five-things-to-know), [cutdown review](https://www.commanders.com/news/washington-commanders-roster-2026-breakdown) | Retain nonzero short-yardage directions without validating the exact 15.9% inside-10 and 15.7% inside-5 shares or declaring Allen the goal-line back. |
| Kaytron Allen, RB two-minute targets | Washington's draft-day summary says Allen appeared to lack third-down value. The cutdown review highlights Rachaad White's receiving history and Croskey-Merritt's improved catching and blocking while defining Allen through short-yardage running. [Draft summary](https://www.commanders.com/news/commanders-kaytron-allen-187-overall-pick) | Current role evidence conflicts with treating the 18.6% no-history two-minute share as established. Preserve it for auditability rather than manually moving it to another back. |
| Jacory Croskey-Merritt, RB two-minute targets | Croskey-Merritt is first on the unofficial RB chart after nine catches on 13 targets and prior protection problems in 2025. Coaches challenged him to become an every-down back; by cutdown, the club reported improved hands and more physical blocking. [Development assignment](https://www.commanders.com/news/commanders-jacory-bill-croskey-merritt-running-back-offseason), [camp progress](https://www.commanders.com/news/jacory-croskey-merritt-pass-catcher) | Retain a substantial receiving-down direction without validating the exact 36.6% history-adjusted share; no reviewed source names the regular-season hurry-up back, and White remains proven receiving competition. |
| Ben Sinnott, TE deep and two-minute targets | Sinnott is second behind Chig Okonkwo on one TE line and has 16 catches across two seasons. Washington reports receiving growth and a motion/in-space fit, plus one camp touchdown while John Bates was absent; it separately identifies Okonkwo as the downfield lead, and a named two-minute period targeted Okonkwo rather than Sinnott. [Position preview](https://www.commanders.com/news/commanders-2026-training-camp-preview-tight-end), [camp touchdown](https://www.commanders.com/news/commanders-training-camp-notebook-jayden-daniels-colson-yankoff), [two-minute observation](https://www.commanders.com/news/commanders-dolphins-training-camp-practice-notes) | Leave the 13.4% deep and 7.2% two-minute shares explicitly inconclusive. General receiving development and an unspecified-distance touchdown do not establish either package. |

## Minnesota audit

The [initial 53-man review](https://www.vikings.com/news/53-man-roster-2026-nfl-initial)
controls the current three-RB, one-FB, six-WR, and four-TE membership. Minnesota's
[current depth page](https://www.vikings.com/team/depth-chart) says the next chart
will be released before Week 1, so the [August 12 chart](https://www.vikings.com/news/preseason-2026-depth-chart-unofficial-nfl)
is retained only as dated ordering evidence. Historical production comes from
[Pro Football Reference](https://www.pro-football-reference.com/teams/min/2025.htm).

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| T.J. Hockenson, TE two-minute targets | Hockenson remains first in the four-TE ordering after 51 catches in 2025. Minnesota says he again threatened seams in camp, and Kyler Murray completed a quick pass to him during a first-team two-minute drill against Baltimore. [Roster review](https://www.vikings.com/news/53-man-roster-2026-nfl-initial), [direct hurry-up use](https://www.vikings.com/news/ravens-joint-practice-2-observations-defending-the-north) | Retain Hockenson as the dominant TE two-minute direction without validating the exact 75.6% history-adjusted share from one named drill. |
| Tai Felton, WR deep and end-zone targets | The active fourth receiver is the first dated-chart backup behind Justin Jefferson. His speed flashed throughout camp; he made a one-handed back-corner end-zone catch in one-on-ones and secured a designed 50-yard downfield reception against Baltimore. [Scoring-area rep](https://www.vikings.com/news/2026-training-camp-observations-defense-padded-practice), [preseason deep result](https://www.vikings.com/news/tai-felton-50-yard-catch-highlights-receivers-competition) | Retain small deep and end-zone directions without validating the exact 6.5% and 6.3% limited-history shares or weekly routes behind three veterans. |
| Demond Claiborne, RB inside-5 and inside-10 carries | Claiborne made the roster as RB3. Despite a light, change-of-pace profile, he received multiple high- and low-red-zone carries against Baltimore, fought through contact for one touchdown, and scored on a short interior run. [Direct usage](https://www.vikings.com/news/ravens-joint-practice-2-observations-defending-the-north) | Retain nonzero short-yardage directions without validating the exact 13.3% inside-10 and 14.2% inside-5 shares or moving him ahead of Aaron Jones and Jordan Mason. |
| Demond Claiborne, RB two-minute targets | Claiborne finished a second-team two-minute drill with a long touchdown run and has created chunks after catches, but current reporting calls his pass protection a work in progress. [Source](https://www.vikings.com/news/previewing-2026-preseason-game-2-ravens) | Keep the 15.1% no-history target share inconclusive. A handoff in a two-minute period is not evidence of two-minute targets. |
| Jordan Mason, RB two-minute targets | Mason is a co-starter with Jones and made one notable camp catch in the flat. The reviewed named first-team two-minute drill used Jones, and no current source assigns Mason the hurry-up package. [Camp reception](https://www.vikings.com/news/2026-training-camp-observations-caleb-banks), [named drill](https://www.vikings.com/news/ravens-joint-practice-2-observations-defending-the-north) | Leave the 22.3% limited-history share inconclusive; co-starter status and one ordinary catch do not establish hurry-up usage. |
| Josh Oliver, TE two-minute targets | Oliver is TE2 and primarily a blocking asset but also a large receiving target. Murray targeted him in a named first-team two-minute period on August 3, although Ivan Pace broke up the pass. [Source](https://www.vikings.com/news/2026-training-camp-observations-defense-padded-practice) | Direct package participation supports a secondary direction, not the exact 10.2% history-adjusted share or Minnesota's use of two tight ends in hurry-up. |
| Ben Yurosek, TE deep targets | The active TE3 caught a second-offense camp pass and later drew a downfield seam attempt that nearly became a diving catch. Minnesota expects him to expand his receiving/blocking role while playing special teams. [Seam usage](https://www.vikings.com/news/2026-training-camp-jamal-adams-observations), [current role](https://www.vikings.com/news/53-man-roster-2026-nfl-initial) | Retain a small deep direction without treating an unspecified-distance incomplete attempt as validation of the exact 7.7% share. |
| Ben Yurosek, TE two-minute targets | No reviewed named two-minute period documents Yurosek as a route runner or target; the observed TE targets went to Hockenson and Oliver. | Leave the 9.9% limited-history share explicitly inconclusive. General receiving development and TE3 rank do not establish a hurry-up package. |
| Max Bredeson, RB two-minute targets | Bredeson made the roster at the separate fullback position and is described as a reliable receiving outlet in the flats with repeated camp catches. [Roster role](https://www.vikings.com/news/53-man-roster-2026-nfl-initial), [camp usage](https://www.vikings.com/news/2026-training-camp-takeaways-so-far) | Keep the 8.1% no-history share inconclusive; a real fullback receiving role does not establish two-minute participation. |
| Jermar Jefferson, three RB metrics | Minnesota waived Jefferson with an injury designation, leaving him outside the active three-back room. [Transaction](https://www.vikings.com/news/53-man-roster-2026-nfl-initial) | Current status conflicts with immediate inside-5, inside-10, or two-minute work. Preserve the already-zero current-active shares and tiny return-weighted scenarios rather than guessing a recovery date. |

## Dallas audit

The [initial 53-man roster](https://www.dallascowboys.com/news/cowboys-release-initial-53-man-roster-for-2026-season)
establishes the retained Williams-Davis-Luepke backfield and Ferguson-Spann-Ford-
Schoonmaker tight-end room. The subsequent [Demercado transaction and role
review](https://www.dallascowboys.com/news/emari-demercado-returns-home-to-dallas-has-reason-to-be-excited-with-cowboys)
controls the current RB ordering: Javonte Williams remains RB1, Malik Davis secured
RB2, and newly claimed Emari Demercado sits behind Davis. The public depth page still
[shows cut players](https://www.dallascowboys.com/team/depth-chart), so it is not
treated as current evidence. Historical production comes from [Pro Football
Reference](https://www.pro-football-reference.com/teams/dal/2025.htm).

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Jake Ferguson, TE two-minute targets | Ferguson remains TE1 after a career-high 82 catches in 2025. Dallas describes underneath opportunity created by its outside receivers, and camp reporting documents Ferguson's established quick-game connection with Dak Prescott plus a seam catch. [Role profile](https://www.dallascowboys.com/news/3-points-jake-ferguson-already-climbing-cowboys-te-charts), [camp usage](https://www.dallascowboys.com/news/practice-points-news-and-notes-from-second-padded-practice) | Retain Ferguson as the dominant TE two-minute direction without validating the exact 70.7% p24 share. The only reviewed named first-team two-minute result identified CeeDee Lamb, not the TE routes. |
| Javonte Williams, RB inside-5 carries | Williams is the returning definitive RB1 after 1,201 rushing yards and 11 touchdowns in the same offense. Dallas extended him for three years, cut larger backup Phil Mafah and Jaydon Blue, and now places Davis and Demercado behind him. [Staff and role continuity](https://www.dallascowboys.com/news/klayton-adams-looking-to-seek-the-edge-for-cowboys-offense), [current room](https://www.dallascowboys.com/news/emari-demercado-returns-home-to-dallas-has-reason-to-be-excited-with-cowboys) | Retain the dominant inside-five direction without validating the exact 68.2% history-adjusted share or assuming every goal-line carry remains his. |
| Javonte Williams, RB two-minute targets | Coordinator Klayton Adams explicitly praises Williams' pass protection, but Davis showed receiving and protection ability while winning RB2. Dallas then added Demercado, a pass-proficient former Adams pupil. The reviewed named first-team two-minute report did not identify the back or a back target. [Williams role](https://www.dallascowboys.com/news/klayton-adams-looking-to-seek-the-edge-for-cowboys-offense), [Davis evidence](https://www.dallascowboys.com/news/starlights-big-play-tracker-for-cowboys-cardinals-preseason-week-2), [Demercado context](https://www.dallascowboys.com/news/emari-demercado-returns-home-to-dallas-has-reason-to-be-excited-with-cowboys) | Leave the 40.5% p24 share inconclusive. All three backs have a credible protection path, but current evidence does not assign the hurry-up package. |
| Brevyn Spann-Ford, TE deep targets | Spann-Ford made the roster and climbed to TE2 after entering the year mainly as a blocker and special-teams player. Dallas calls him a capable downfield target, and he caught two first-team red-zone touchdowns against the Rams. [Camp summary](https://www.dallascowboys.com/news/rank-em-top-20-standouts-from-oxnard-camp), [joint practice](https://www.dallascowboys.com/news/practice-points-cowboys-defense-dominates-rams-in-joint-practice) | Retain a nonzero deep direction without validating the exact 23.9% limited-history share; the scoring-area catches were not identified as deep targets. |
| Brevyn Spann-Ford, TE two-minute targets | The current TE2 has developed as a receiving target, but his established NFL work remains weighted toward blocking and special teams. No reviewed named two-minute period documents a Spann-Ford route or target. [Role history](https://www.dallascowboys.com/news/next-man-up-can-brevyn-spann-ford-get-to-another-level), [named drill](https://www.dallascowboys.com/news/practice-points-news-notes-from-energetic-cowboys-practice) | Leave the 12.5% p24 share inconclusive. TE2 status and red-zone success do not establish two-TE hurry-up personnel. |
| Malik Davis, RB two-minute targets | Davis secured RB2 and produced an eight-yard receiving touchdown plus a documented blitz pickup with the second-team offense against Arizona. Dallas has since placed Demercado directly behind him. [Preseason evidence](https://www.dallascowboys.com/news/starlights-big-play-tracker-for-cowboys-cardinals-preseason-week-2), [current role](https://www.dallascowboys.com/news/emari-demercado-returns-home-to-dallas-has-reason-to-be-excited-with-cowboys) | Leave the 27.8% p24 share inconclusive. Receiving and protection competence make usage plausible but do not establish first-team two-minute targets. |

## Jacksonville audit

The [initial 53-man review](https://www.jaguars.com/news/the-53-breaking-down-the-jaguars-roster)
confirms every queued player is active and identifies Tuten and Rodriguez as projected
co-starters. The [August 11 unofficial chart](https://www.jaguars.com/news/jaguars-2026-training-camp-first-unofficial-depth-chart-released)
also lists the two backs as co-starters, Allen next, and the tight ends in Strange-
Boerkircher-Koziol-Morris order. Historical production comes from [Pro Football
Reference](https://www.pro-football-reference.com/teams/jax/2025.htm); current
package evidence is kept separate from those historical samples.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Josh Cameron, WR deep and end-zone targets | Cameron is one of six active receivers after repeatedly producing downfield. With extended first-team work late in camp, he caught a Lawrence red-zone touchdown and a downfield third-down conversion in an end-of-game drill, then closed camp with another deep sideline catch. [Situational work](https://www.jaguars.com/news/camp-snapshot-day-19-pleased-with-the-progression), [camp finale](https://www.jaguars.com/news/camp-snapshot-day-20-progress-is-exciting) | Retain nonzero deep and end-zone directions without validating the exact 5.9% and 6.2% no-history p24 shares or assuming weekly activation. |
| Bhayshul Tuten, RB two-minute targets | Tuten is a projected co-starter. Coordinator Grant Udinski explicitly said the backfield committee extends to third downs and two-minute offense, then highlighted Tuten's major improvement in pass protection. [Source](https://www.jaguars.com/news/camp-wrap-day-15-we-re-all-ready) | Retain a meaningful receiving-down direction without validating the exact 30.8% limited-history p24 share or assigning Tuten the entire hurry-up package. |
| Chris Rodriguez Jr., RB two-minute targets | Rodriguez is the other projected co-starter, and Udinski's two-minute committee statement includes every back. Jacksonville's clearest differentiated description of Rodriguez is still physical inside running and hidden yardage. [Committee](https://www.jaguars.com/news/camp-wrap-day-15-we-re-all-ready), [role context](https://www.jaguars.com/news/jaguars-experts-final-analysis-of-2026-offseason-running-back-and-other-areas-to-watch) | Retain a nonzero two-minute direction without validating the exact 26.2% limited-history share or inferring routes from rushing status. |
| LeQuint Allen Jr., RB two-minute targets | Udinski's direct statement includes Allen in the passing-game committee, while Jaguars media projected him as the third-down back. Allen caught a Lawrence touchdown after a scramble drill, but that play was outside the separately named two-minute period; he then ended camp with a soft-tissue injury. [Role view](https://www.jaguars.com/news/jaguars-experts-final-analysis-of-2026-offseason-running-back-and-other-areas-to-watch), [practice detail](https://www.jaguars.com/news/jaguars-2026-training-camp-snapshot-day-8-mock-game-a-good-day), [injury](https://www.jaguars.com/news/camp-snapshot-day-15-embracing-the-challenge) | Retain a meaningful receiving-down direction without validating the exact 25.5% share. The injury raises near-term availability uncertainty. |
| LeQuint Allen Jr., inside-5 and inside-10 carries | Tuten and Rodriguez are the co-starters; Jaguars media projected Rodriguez as the short-yardage specialist and Allen as the third-down back. Allen has only 23 NFL carries and missed the end of camp. | Leave both roughly 9.5% p24 shares inconclusive. Current role language and a one-event historical sample do not assign Allen goal-line work. |
| Nate Boerkircher, TE deep and two-minute targets | The second-round rookie is TE2 on the preseason chart, Jacksonville plans more two- and three-TE personnel, and Boerkircher made physical and contested red-zone catches. [Personnel plan](https://www.jaguars.com/news/k000623-2026-draft-ervations-thats-a-wrap), [red-zone work](https://www.jaguars.com/news/camp-snapshot-day-17-sharpening-the-edge) | Leave the 19.2% deep and 20.9% two-minute shares inconclusive. Draft capital, personnel multiplicity, and red-zone success do not establish either distinct target package. |
| Tanner Koziol, TE deep targets | The active TE3 caught an explicitly described deep throw down the middle for one of the offense's biggest gains. [Source](https://www.jaguars.com/news/jaguars-2026-training-camp-snapshot-day-2) | Retain the small deep direction without validating the exact 7.7% no-history share or a weekly route count. |
| Tanner Koziol, TE two-minute targets | An OTA practice contained both two-minute work and a Koziol catch to begin a seven-on-seven period, but the report presents those as separate segments and does not name Koziol in the hurry-up period. [Source](https://www.jaguars.com/news/ota-observations-day-4-strong-day-for-btj) | Leave the 8.4% no-history share inconclusive; proximity within one practice is not package-specific evidence. |
| Quintin Morris, TE deep and two-minute targets | Morris is the active TE4 and described as a solid blocker. His reviewed camp reception was a red-zone touchdown from backup Nick Mullens, not a documented deep or two-minute target. [Roster role](https://www.jaguars.com/news/the-53-breaking-down-the-jaguars-roster), [camp play](https://www.jaguars.com/news/camp-snapshot-day-20-progress-is-exciting) | Leave the 6.3% deep and 7.4% two-minute shares inconclusive. Active depth and a broad multi-TE plan do not identify those packages. |

## Las Vegas audit

The [initial 53-man roster](https://www.raiders.com/news/raiders-initial-53-man-roster-2026-season-position-by-position)
controls current membership: Jeanty, Washington, and Laube at halfback; Heyward at
fullback; Bowers, Mayer, and Thomas at tight end; and Benson among six receivers.
The [August 24 chart](https://www.raiders.com/team/depth-chart) is retained only as
dated, unofficial ordering evidence. Historical production comes from [Pro Football
Reference](https://www.pro-football-reference.com/teams/rai/2025.htm).

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Malik Benson, WR deep targets | The active sixth-round rookie is second behind Jack Bech on one dated receiver line. He earned first-team reps, high-pointed a go route, and caught a would-be 60-yard touchdown that was erased only because the quarterback would have been sacked. [Role profile](https://www.raiders.com/news/malik-benson-well-traveled-path-raiders-2026-training-camp-nfl-draft-pick-oregon-ducks), [downfield work](https://www.raiders.com/news/training-camp-notebook-8-10-offense-firing-on-all-cylinders) | Retain a nonzero deep direction without validating the exact 8.1% no-history share, weekly routes, or an offensive workload alongside return duties. |
| Malik Benson, WR end-zone targets | Benson caught a backup-quarterback slant touchdown during red-zone work, but the report does not specify the target location; all five named first-team scores went to Nailor, Bowers, or Mayer. The post-cutdown review identifies Benson's clearest immediate role as a kick or punt returner. [Red-zone work](https://www.raiders.com/news/training-camp-notebook-8-17-raiders-build-momentum-before-heading-to-houston), [roster observation](https://www.raiders.com/news/raiders-initial-2026-53-man-roster-observations-quarterbacks-2026-draft-class) | Leave the 9.5% no-history share inconclusive. A red-zone touchdown is not automatically an end-zone-origin target, especially with reserve personnel. |
| Ashton Jeanty, RB two-minute targets | Jeanty remains the lead after 55 catches and five receiving touchdowns in 2025. Kubiak wants his best player on the field as much as possible. He avoided injured reserve after an ankle injury, and the club remained optimistic for Week 1, but he had not returned to team practice by September 2 while Washington earned a complementary role. [Lead-role plan](https://www.raiders.com/news/ashton-jeanty-steady-anchor-of-the-raiders-backfield-2026-season-nfl), [September 1 health](https://www.raiders.com/news/4-takeaways-john-spytek-and-brian-stark-raiders-53-man-roster), [September 2 update](https://www.raiders.com/video/klint-kubiak-kirk-cousins-qb1-53-man-roster-nfl-2026) | Retain Jeanty as the leading receiving-down direction without validating the exact 48.7% history-adjusted share. Treat Week 1 availability and the Washington split as live uncertainty. |
| Dylan Laube, inside-5 and inside-10 carries | Laube is the active third back and a major returner, but he received a direct four-yard preseason carry for a touchdown and finished August with 59 yards and one score on 14 carries. [Direct play](https://www.raiders.com/video/dylan-laube-touchdown-run-nfl-preseason-texans-2026), [preseason totals](https://www.raiders.com/news/raiders-2026-preseason-stat-leaders-mike-washington-shedrick-jackson) | Retain nonzero short-yardage directions without validating the exact 9.4% inside-10 and 9.0% inside-5 shares or promoting one reserve-preseason score over Jeanty and Washington. |
| Dylan Laube, RB two-minute targets | Current reporting emphasizes Laube's return work, while Jeanty is the established receiver and Washington produced as a pass catcher when filling in. No reviewed 2026 report assigns Laube a hurry-up route or target. [Current role](https://www.raiders.com/news/2026-position-breakdown-raiders-running-backs-ashton-jeanty-mike-washington-jr-connor-heyward), [camp context](https://www.raiders.com/news/training-camp-notebook-8-17-raiders-build-momentum-before-heading-to-houston) | Leave the increased 22.7% share inconclusive; active RB3 status and four historical opportunities do not establish the package. |
| Connor Heyward, RB two-minute targets | Las Vegas lists Heyward separately at fullback. The H-back matters in Kubiak's system, and Heyward has practiced as both a blocker and pass-game participant while pass protecting on a third-down conversion. [System role](https://www.raiders.com/news/training-camp-notebook-7-30-26-defensive-line-starts-applying-pressure-maxx-crosby-tonka-hemingway), [preseason detail](https://www.raiders.com/news/training-camp-notebook-8-16-versatility-continues-to-shine-through-in-raiders-offense) | Leave the 11.1% no-history share inconclusive. A credible fullback receiving path is not evidence of two-minute targets. |
| Ian Thomas, TE deep and two-minute targets | Thomas is TE3 behind healthy Bowers and Mayer; his 10 starts in 2025 helped cover their injuries. He was one of Mendoza's top targets while the backup offense moved downfield in one practice, but no reviewed report establishes a 20-plus-air-yard target or two-minute use. [Room context](https://www.raiders.com/news/2026-position-breakdown-tight-ends-brock-bowers-michael-mayer-ian-thomas), [practice](https://www.raiders.com/news/training-camp-notebook-8-17-raiders-build-momentum-before-heading-to-houston) | Leave the 9.0% deep and 5.3% two-minute shares inconclusive. TE3 status and broad downfield wording do not identify either package. |
| Chris Collier, three RB metrics | Las Vegas waived Collier with an injury designation on July 31, and he is absent from the active three-back room. [Transaction](https://www.raiders.com/news/raiders-sign-te-zack-kuntz-2026-nfl-transactions-training-camp) | Current status conflicts with immediate inside-5, inside-10, or two-minute work. Preserve zero current-active shares and the tiny return-weighted model scenarios rather than guessing a return date. |

## Philadelphia audit

Philadelphia illustrates why scheme-family certainty and player-package certainty
must stay separate. Sean Mannion is a first-time NFL caller whose background is in
the LaFleur/Shanahan/McVay family, but the club describes a blend with retained
Sirianni-era concepts.
[February overview](https://www.philadelphiaeagles.com/news/eagles-2026-offense-sean-mannion-jalen-hurts-dave-spadaro)
Camp confirmed more motion, under-center work, and a changed blocking structure.
[Camp scheme report](https://www.philadelphiaeagles.com/news/eagles-players-embrace-sean-mannion-and-the-new-look-offense)
That supports the existing 69.2 broad-identity score while preserving the much lower
45.3 exact-rate score. The club's
[current roster](https://www.philadelphiaeagles.com/team/players-roster/) controls
membership; [Pro Football Reference](https://www.pro-football-reference.com/teams/phi/2025.htm)
supplies historical context only.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Makai Lemon, WR deep targets | The active first-round rookie missed most of camp with a hamstring injury. His documented camp work was mostly short, but NFL.com's official preseason review recorded one defended deep shot among five targets in 17 snaps; his three catches totaled three yards. [Health and routes](https://www.philadelphiaeagles.com/news/eagles-makai-lemon-returns-to-full-participation-at-practice), [preseason review](https://www.nfl.com/news/2026-nfl-preseason-week-3-what-we-learned-friday-games) | Retain a nonzero vertical direction because an actual deep attempt exists. Do not treat one reserve-preseason target as validation of the 21.7% no-history share, 21.96 expected events, or weekly routes. |
| Makai Lemon, WR end-zone targets | Lemon scored in a first-team red-zone period by catching a pass in the left flat and running it into the end zone. [Public practice](https://www.philadelphiaeagles.com/news/eagles-public-practice-notes-riq-woolen-leads-the-defense-in-front-of-45-000-fans) | Leave the 21.6% no-history share inconclusive. A red-zone catch carried across the goal line is not an end-zone-origin target. |
| Tank Bigsby, RB two-minute targets | Bigsby made the three-back roster behind primary back Saquon Barkley, rotated frequently with Barkley in first-team camp work, and is described as capable in receiving and pass protection. [Opening practice](https://www.philadelphiaeagles.com/news/eagles-2026-training-camp-notes-highlights-from-the-first-day-of-practice), [role profile](https://www.philadelphiaeagles.com/news/spadaro-tank-bigsby-is-ready-for-whatever-opportunities-come-his-way) Neither reviewed first-team two-minute period assigned him a route or target. | Leave the 20.0% limited-history share inconclusive. An all-around reserve role is not package-specific evidence. |
| Will Shipley, RB two-minute targets | Shipley caught all three RB-linebacker drill passes and later won on a wheel route from Hurts. That wheel came during a move-the-ball period; the subsequent two-minute drill named Wicks for three consecutive catches. [Pads practice](https://www.philadelphiaeagles.com/news/eagles-training-camp-notes-who-shined-with-the-pads-on), [joint practice](https://www.philadelphiaeagles.com/news/practice-notes-saquon-barkley-rushing-attack-set-the-tone-in-new-england) | Leave the 15.3% limited-history share inconclusive. Receiving skill is established, but hurry-up participation is not. |
| Eli Stowers, TE deep targets | The active second-round rookie was drafted for athletic mismatch ability and produced a 20-yard second-team seam reception. [Draft role](https://www.philadelphiaeagles.com/news/eagles-eli-stowers-vanderbilt-nfl-draft-2026), [joint practice](https://www.philadelphiaeagles.com/news/practice-notes-saquon-barkley-rushing-attack-set-the-tone-in-new-england) The report gives gain length, not air yards. | Retain a nonzero downfield direction without claiming the play crossed the 20-air-yard definition or validating the 9.2% no-history share. |
| Eli Stowers, TE two-minute targets | Stowers' seam catch occurred in a second-team second/third-down segment. The later first-team two-minute drill was separate and named Wicks, not Stowers. Another first-team two-minute period ended on an interception without a named TE target. | Leave the 9.3% no-history share inconclusive. Adjacent situational work does not establish hurry-up personnel. |
| Ja'Quinden Jackson, three RB metrics | Philadelphia waived Jackson with an injury designation on August 24 after he was hurt covering a kickoff. He is absent from the current active, reserve, and practice-squad lists. [Transaction](https://www.philadelphiaeagles.com/news/eagles-release-jt-gray-waive-rb-jaquinden-jacksonwith-an-injury-designation), [current roster](https://www.philadelphiaeagles.com/team/players-roster/) | Current status conflicts with immediate inside-5, inside-10, or two-minute work. Preserve zero current-active shares and the small return-weighted scenarios rather than guessing a return. |

## New England audit

New England separates a high-confidence team environment from much less certain
fringe-player packages. Josh McDaniels returns as the regular play caller, and the
historical environment audit gives him a 94.4 broad-identity score and 91.4 exact-rate
score. The [post-cutdown review](https://www.patriots.com/news/analysis-breaking-down-the-patriots-initial-53-man-roster-for-the-2026-season)
again identifies McDaniels as the caller and supplies role context. The club's
[current roster](https://www.patriots.com/team/players-roster/) controls membership;
its [depth chart](https://www.patriots.com/team/depth-chart) is retained only as an
explicitly unofficial ordering snapshot. [Pro Football Reference](https://www.pro-football-reference.com/teams/nwe/2025.htm)
supplies conventional 2025 history, not 2026 package assignments.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Kyle Williams, WR deep targets | The active second-year receiver repeatedly separated vertically, drew an underthrown deep target, caught a long post in joint work, and scored from 69 and 45 yards in the preseason. The roster review calls him a legitimate vertical threat worth game opportunities. [Preseason opener](https://www.patriots.com/news/game-observations-8-takeaways-from-the-patriots-first-preseason-game-vs-the-colts), [roster review](https://www.patriots.com/news/analysis-breaking-down-the-patriots-initial-53-man-roster-for-the-2026-season) | Retain a nonzero vertical direction without validating the exact 7.6% limited-history p24 share, 8.44 season count, or a regular-season route workload behind the veteran receivers. |
| Kyle Williams, WR end-zone targets | Williams won a 12-yard fade for a preseason touchdown, and NFL.com's official highlight explicitly locates the catch inside the end zone. [Team detail](https://www.patriots.com/news/game-observations-8-takeaways-from-the-patriots-first-preseason-game-vs-the-colts), [NFL highlight](https://www.nfl.com/videos/devito-s-12-yard-td-pass-pinpoints-kyle-williams-inside-the-end-zone) | Retain a nonzero end-zone direction without treating one reserve-preseason target as validation of the exact 6.3% share or 2.02 season count. |
| Corey Kiner, inside-5 and inside-10 carries | New England traded a seventh-round pick for Kiner after camp and lists him as RB3. The club describes a between-the-tackles finisher with 180 preseason yards and two scores; Arizona directly documented one score as a one-yard carry. [Current role](https://www.patriots.com/news/analysis-breaking-down-the-patriots-initial-53-man-roster-for-the-2026-season), [one-yard carry](https://www.azcardinals.com/video/highlight-corey-kiner-punches-it-in-for-touchdown) | Retain nonzero short-yardage directions. Evidence earned in Arizona does not assign New England's goal-line package or validate the exact 11.8% inside-10 and 10.9% inside-5 shares. |
| Corey Kiner, RB two-minute targets | Kiner arrived only after New England's situational camp work. His official transaction history includes two catches in four 2025 games, while the current review emphasizes inside running and special teams. [Transaction](https://www.patriots.com/news/patriots-acquire-rb-corey-kiner-in-a-trade-with-arizona-release-rb-hassan-haskins) | Leave the 10.7% limited-history share inconclusive. RB3 status and two prior receptions do not establish protection trust, routes, or hurry-up inclusion. |
| Eli Raridon, TE deep targets | The active TE2 led draft-eligible tight ends with eight college catches on passes over 20 air yards. In Patriots camp he caught a Maye play-action seam pass and was described as adding a big-play, seam-stretching element. [Position review](https://www.patriots.com/news/patriots-position-snapshot-tight-ends-fullbacks), [camp report](https://www.patriots.com/news/rookie-report-camp-observations-from-all-nine-patriots-draft-picks-and-undrafted-rookies) | Retain a nonzero deep direction without validating the exact 22.9% no-history share, 4.75 season count, or rookie route rate behind Hunter Henry. |
| Eli Raridon, TE two-minute targets | Raridon's named joint-practice gains came in early-down play-action work. The separately described final two-minute snap released three receivers and targeted DeMario Douglas; no reviewed source assigns Raridon a hurry-up target. [Joint practice](https://www.patriots.com/news/12-takeaways-from-drake-maye-and-the-patriots-offense-in-joint-practice-vs-colts) | Leave the 19.7% no-history share inconclusive. A seam role is not evidence of two-minute personnel. |
| Cameron Latu, TE deep and two-minute targets | Claimed on September 1, Latu is active but fourth on the unofficial TE chart. He has zero career targets; his 2025 Eagles offense snaps were primarily H-back/lead-blocking work, and New England says any offensive role remains to be monitored. [Claim and role review](https://www.patriots.com/news/analysis-patriots-claim-te-cameron-latu-and-lb-darius-muasau-off-waivers-begin-filling-out-practice-squad) | Leave both small no-history shares inconclusive. A late-arriving TE4 with no career target does not establish deep or hurry-up usage. |
| Reggie Gilliam, RB two-minute targets | Gilliam is the active starting fullback, and New England projects significant 21-personnel. Spring work included routes from multiple alignments and vertical movement on the sideline and seams. [Position review](https://www.patriots.com/news/patriots-position-snapshot-tight-ends-fullbacks) | Leave the 5.4% limited-history share inconclusive. A credible H-back receiving path is not package-specific two-minute evidence. |
| Myles Montgomery, three RB metrics | New England waived Montgomery with an injury designation on August 12, and he is absent from the current active, reserve, and practice-squad lists. [Transaction](https://www.patriots.com/news/patriots-sign-rb-hassan-haskins-waive-injured-rb-myles-montgomery), [current roster](https://www.patriots.com/team/players-roster/) | Current status conflicts with immediate inside-5, inside-10, or two-minute work. Preserve zero current-active shares and the small return-weighted scenarios rather than guessing a recovery or return. |

## Los Angeles Rams audit

Los Angeles demonstrates why a highly certain team environment does not eliminate
player-package uncertainty. Sean McVay explicitly confirmed that he remains the 2026
play caller despite offensive-staff changes. [Caller confirmation](https://www.therams.com/news/top-takeaways-from-sean-mcvay-s-post-2026-nfl-combine-press-conference-finalized-coaching-staff-pending-free-agents-and-more)
The current environment audit assigns his five clean completed seasons a 99.1 broad-
identity score and a 93.9 exact-rate score. The club's
[current roster](https://www.therams.com/team/players-roster/) controls membership;
its [depth chart](https://www.therams.com/team/depth-chart) is explicitly unofficial.
[Pro Football Reference](https://www.pro-football-reference.com/teams/ram/2025.htm)
supplies conventional 2025 history, while the frozen
[nflverse play-by-play](https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2025.csv.gz)
supplies the exact deep, end-zone, and two-minute definitions used by the model.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Davante Adams, WR end-zone targets | Adams is active and first on one receiver line after leading the NFL with 14 receiving touchdowns in 2025. Current Stafford work includes a 10-yard fade caught in the end zone and another over-the-shoulder touchdown. [End-zone fade](https://www.therams.com/news/10-observations-from-2026-rams-training-camp-wr-cb-battles-highlight-day-6), [current rapport](https://www.therams.com/news/matthew-stafford-and-davante-adams-rapport-benefitting-from-training-camp-practices-this-year-that-they-didn-t-have-together-in-2025) | Retain Adams as the primary end-zone direction without validating the exact 38.2% history-adjusted p24 share or 11.36 season count. |
| Konata Mumpfield, WR deep and end-zone targets | Mumpfield is active and second behind Adams on one receiver line. The frozen 2025 history contains eight deep targets and one end-zone target among 23 targets; club reports also document a 2025 deep camp touchdown, his first regular-season touchdown, and a 2026 back-shoulder sideline catch from Stafford. [Deep camp play](https://www.therams.com/news/10-observations-from-day-9-of-2025-rams-training-camp-defense-creating-takeaways-davante-adams-and-davis-allen-s-playmaking-konata-mumpfield-s-response), [first NFL touchdown](https://www.therams.com/news/feature-konata-mumpfield-records-first-career-touchdown-in-rams-week-7-win-over-jaguars), [current camp](https://www.therams.com/news/10-observations-from-day-2-of-2026-rams-training-camp-matthew-stafford-puka-nacua-davante-adams-trent-mcduffie-cam-lampkin) | Retain nonzero deep and end-zone directions. Do not treat 23 prior targets as validation of the exact 9.2% deep and 8.3% end-zone shares, 10.93 and 2.92 season counts, or routes behind Nacua and Adams. |
| Terrance Ferguson, TE deep targets | Ferguson is active on one of two starting TE rows. His 2025 production was disproportionately downfield, and the Rams explicitly recorded a deep completion to him in current camp. The club also returns the four tight ends behind its league-leading 2025 use of 13 personnel and added second-rounder Max Klare. [Current deep play](https://www.therams.com/news/10-observations-day-5-rams-training-camp-2026-myles-garrett-davante-adams-stetson-bennett-ty-simpson), [prior production](https://www.therams.com/news/feature-terrance-ferguson-s-steady-growth-aiding-emergence-as-reliable-piece-to-rams-offense), [room context](https://www.therams.com/news/countdown-to-camp-how-can-deep-and-experienced-te-group-build-on-success-of-2026-season) | Retain a nonzero vertical direction without validating the exact 17.6% limited-history share, 3.24 season count, or route rate in a five-TE room. |
| Terrance Ferguson, TE two-minute targets | Ferguson's receiving versatility is real, but the frozen 2025 history contains only one two-minute target. The first 2026 report of hurry-up installation did not name him, and a later joint practice canceled its planned first-team two-minute period. [First installation](https://www.therams.com/news/10-oberservations-day-4-rams-training-camp-alaric-jackson-justin-dedich-puka-nacua-matthew-stafford-nate-landman), [canceled period](https://www.therams.com/news/10-observations-from-rams-joint-practice-with-saints-matthew-stafford-davante-adams-terrance-ferguson-nate-landman-kobie-turner) | Leave the 10.5% limited-history share inconclusive. Multi-alignment receiving ability is not a documented hurry-up assignment. |
| Blake Corum, RB two-minute targets | Corum is RB2 after 145 carries and eight receptions in 2025, but the frozen history contains zero two-minute targets among 14 total targets. The first 2026 hurry-up-installation report named receiving scores for Kyren Williams with the first team and Ronnie Rivers with the second, in a separate observation, but no Corum route or target. [Backfield context](https://www.therams.com/news/2026-offseason-position-reset-running-back), [situational practice](https://www.therams.com/news/10-oberservations-day-4-rams-training-camp-alaric-jackson-justin-dedich-puka-nacua-matthew-stafford-nate-landman) | Leave the 21.4% limited-history share inconclusive. A major rushing role does not establish the distinct hurry-up target split. |
| Ronnie Rivers, RB two-minute targets | Rivers is the trusted RB3. McVay specifically praises his pass protection and ability as an extension of the pass game. Rivers caught a second-team touchdown during the first practice with two-minute installation, but the report describes the score and situational work separately; the frozen 2025 history contains no Rivers target. [Roster role](https://www.therams.com/news/53-man-roster-takeaways-positional-depth-competitive-culture-jb-long-instant-analysis-rams), [practice](https://www.therams.com/news/10-oberservations-day-4-rams-training-camp-alaric-jackson-justin-dedich-puka-nacua-matthew-stafford-nate-landman) | Leave the 11.7% limited-history share inconclusive. Passing-down trust plus an ambiguously situated reception does not prove a two-minute target role. |

## New York Giants audit

New York demonstrates why broad offensive identity and exact-rate confidence must
stay separate. Matt Nagy answered questions as the 2026 play caller, but the club
expects the offense to blend Nagy, Brian Callahan, and Greg Roman concepts. The
environment audit therefore gives New York a 54.6 broad-identity score and only a
26.1 exact-rate score, with no clean completed season for Nagy as the team's primary
caller. The club is more confident that John Harbaugh, Roman, first-round guard
Francis Mauigoa, fullback Patrick Ricard, and Cam Skattebo produce a run lean.
[Caller confirmation](https://www.giants.com/news/quotes-8-25-dc-dennard-wilson-asst-hc-stc-chris-horton-oc-matt-nagy),
[scheme preview](https://www.giants.com/news/2026-nfl-season-jaxson-dart-matt-nagy-brian-callahan-greg-roman-cam-skattebo-john-harbaugh)

The club's [current roster](https://www.giants.com/team/rosters) controls membership.
Its [depth-chart page](https://www.giants.com/team/depth-chart) is retained only as
an ordering snapshot because it still includes players moved off the active roster
at cutdown. [Pro Football Reference](https://www.pro-football-reference.com/teams/nyg/2025.htm)
supplies conventional 2025 history; frozen
[nflverse play-by-play](https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2025.csv.gz)
supplies the exact inside-5, inside-10, and two-minute definitions.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Cam Skattebo, inside-5 carries | Skattebo is active, appears first in the club's ordering snapshot, and scored on a short rush during a 2026 goal-line practice period. Frozen 2025 history contains nine inside-5 carries among 101 total carries. [Goal-line practice](https://www.giants.com/news/top-plays-practice-jaxson-dart-isaiah-likely-malachi-fields-abdul-carter-malik-nabers-ar-darius-washington-roster-moves) | Retain Skattebo as the primary nonzero direction. Do not treat one current rep and eight games of history as validation of the exact 58.3% p24 share or 10.45 season count in a new offense and four-back room. |
| Malachi Fields, WR deep and end-zone targets | The rookie made the five-receiver roster. Dart hit him deep down the sideline for more than 40 yards on the first play of a camp team period; Fields separately caught a back-corner end-zone touchdown in OTAs and a goal-line touchdown in 11-on-11 camp work. [Deep play](https://www.giants.com/news/back-together-saturday-jaxson-dart-malachi-fields-isaiah-likely-odell-beckham-jr-tremaine-edmunds-jack-kelly-dominic-zvada), [end-zone play](https://www.giants.com/news/practice-report-6-2-sideline-notes-francis-mauigoa-colton-hood-arvell-reese-abdul-carter-spring-workouts), [goal-line play](https://www.giants.com/news/top-plays-training-camp-jaxson-dart-jameis-winston-malachi-fields-tremaine-edmunds-cam-skattebo-abdul-carter) | Retain nonzero directions for both metrics. Multiple direct current reps do not validate the no-history 9.4% deep and 10.4% end-zone shares, 9.90 and 3.13 season counts, or a regular route workload. |
| Tyrone Tracy Jr., inside-10 carries | Frozen 2024-25 history contains 16 inside-10 carries among 368 total carries. The official 2026 preseason-finale gamebook lists Tracy as the starter and records a six-yard rushing touchdown. [NFL gamebook](https://static.www.nfl.com/image/upload/v1788001612/gamecenter/c77f1834-5f68-11f1-b1d0-bb70a4640075.pdf) | Retain a nonzero inside-10 direction without validating the exact 15.1% share or 6.03 season count after the staff change and Najee Harris addition. |
| Tyrone Tracy Jr., inside-5 carries | Frozen history contains seven inside-5 carries, but no reviewed 2026 source assigns Tracy an inside-5 rush. His preseason touchdown began at the six-yard line; Skattebo owns the named current short goal-line score, and New York added downhill runner Harris. [Harris signing](https://www.giants.com/news/najee-harris-signed-juju-smith-schuster-released-roster-move-steelers-chargers) | Leave the large role adjustment inconclusive. A six-yard touchdown supports inside-10 involvement, not the distinct 10.7% inside-5 share or 2.70 season count. |
| Patrick Ricard, RB two-minute targets | Ricard is the active starting fullback and caught a goal-line touchdown in camp, but frozen 2021-25 history contains zero two-minute targets among 40 total targets. A reviewed first-team 2026 two-minute sequence named a deep target to Devin Singletary, not a Ricard route or target. [Goal-line catch](https://www.giants.com/news/top-plays-training-camp-jaxson-dart-jameis-winston-malachi-fields-tremaine-edmunds-cam-skattebo-abdul-carter), [two-minute practice](https://www.giants.com/news/practice-report-greenbrier-jaxson-dart-abdul-carter-chauncey-golston-training-camp-brian-burns-tremaine-edmunds) | Leave the 5.6% limited-history share inconclusive. A real receiving dimension does not establish hurry-up personnel or validate the 0.96 season count. |

## Carolina Panthers audit

Carolina illustrates the difference between system certainty and exact play-caller
certainty. Brad Idzik has been the offensive coordinator since 2024, and the club
describes the handoff from Dave Canales as seamless and the running backs as the
offense's identity. But 2026 will be Idzik's first regular season calling plays after
Canales handled that job for two seasons. The environment audit therefore scores the
broad identity at 81.9 and the exact-rate evidence at 64.2; neither score is a
probability or a player projection. [Role transition](https://www.panthers.com/news/dave-canales-and-brad-idzik-fully-step-into-their-new-roles-for-the-panthers-training-camp),
[caller confirmation](https://www.panthers.com/news/dave-canales-offensive-coordinator-brad-idzik-to-call-plays-in-2026)

The [current roster](https://www.panthers.com/team/players-roster/) controls
membership, while the [current depth chart](https://www.panthers.com/team/depth-chart)
supplies an ordering snapshot: Chuba Hubbard, Jonathon Brooks, then AJ Dillon, with
Jimmy Horn Jr. also first at both return spots. The club's
[initial roster analysis](https://www.panthers.com/news/panthers-initial-53-man-roster-analysis)
places Trevor Etienne on reserve/injured with a return designation and says Hubbard
and Brooks should receive the bulk of the backfield work. Pro Football Reference
supplies conventional [Brooks](https://www.pro-football-reference.com/players/B/BrooJo02.htm),
[Dillon](https://www.pro-football-reference.com/players/D/DillAJ00.htm), and
[Horn](https://www.pro-football-reference.com/players/H/HornJi00.htm) history; frozen
nflverse play-by-play supplies the exact situational definitions.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Jonathon Brooks, inside-5 and inside-10 carries | Brooks received first-team work, was expected to mix with Hubbard, and scored from the one-yard line in the preseason. Frozen 2024 history contains two inside-10 carries and one inside-5 carry among nine total carries. [First-team role](https://www.panthers.com/news/training-camp-observations-jonathon-brooks-to-play-with-ones-in-buffalo), [one-yard touchdown](https://www.panthers.com/news/a-sign-to-my-father-jonathon-brooks-on-his-special-preseason-touchdown) | Retain nonzero directions for both metrics. The evidence does not validate the exact 26.0% inside-10 and 23.8% inside-5 shares, 10.37 and 5.64 season counts, or allocation behind Hubbard. |
| Jonathon Brooks, RB two-minute targets | Brooks caught one pass with the first offense in his preseason debut, but frozen history contains zero two-minute targets among three total targets. He was working to the side with soreness immediately before Week 1, and no reviewed situational report assigns him a hurry-up route. [Current update](https://www.panthers.com/news/four-takeaways-from-wednesday-including-aj-dillon-finding-his-role-and-more) | Leave the 24.6% limited-history share and 3.98 season count inconclusive. General receiving work does not establish a two-minute role. |
| Jimmy Horn Jr., WR deep and end-zone targets | Frozen 2025 history contains three deep targets and no end-zone target among 15 total targets. The official 2026 preseason gamebook adds a deep target from the Arizona 17, and Horn later caught a pass in the middle of the end zone with the second offense in joint practice. [NFL gamebook](https://static.www.nfl.com/image/upload/v1786103049/gamecenter/c66cf251-5f68-11f1-b1d0-bb70a4640075.pdf), [end-zone catch](https://www.panthers.com/news/play-of-the-day-jimmy-horn-comes-up-big-in-joint-practice) | Retain nonzero directions for both metrics. Reserve-offense reps and a likely return-heavy role do not validate the exact 4.9% deep and 3.6% end-zone shares or 5.66 and 1.20 season counts. |
| AJ Dillon, RB two-minute targets | Dillon is the active RB3. He says he has been asked to catch, pass protect, and run, and the gamebook records an 18-yard preseason reception, but the club says his eventual role division remains unsettled. [Current role report](https://www.panthers.com/news/four-takeaways-from-wednesday-including-aj-dillon-finding-his-role-and-more) | Leave the 14.7% share and 2.63 count inconclusive. Broad pass-game ability is not a documented hurry-up assignment. |
| Trevor Etienne, inside-5 and inside-10 carries | Before injury, Etienne split first-team work with Brooks while Hubbard was out. Frozen 2025 history contains three inside-10 carries and one inside-5 carry among 20 total carries. He is now on reserve/injured for at least four games. [Pre-injury work](https://www.panthers.com/news/training-camp-observations-chuba-hubbard-week-to-week-with-hamstring-darren-waller-preseason-bills), [transaction](https://www.panthers.com/news/panthers-make-moves-to-get-to-roster-limit-53-man-roster-transactions-cuts-injured-reserve-pup-nfi) | Retain small, return-weighted nonzero directions. Do not validate the exact 9.6% inside-10 and 8.3% inside-5 shares or 1.83 and 0.96 counts before his return and role are observed. |
| Trevor Etienne, RB two-minute targets | Frozen history contains one two-minute target among three total targets, but no reviewed 2026 source assigns Etienne a hurry-up route and his reserve/injured status delays any current role. | Leave the 7.1% share and 0.58 count inconclusive. One prior event cannot establish a post-return two-minute role. |

## Houston Texans audit

Houston is a relatively stable offensive environment, not a fully certain player-role
environment. [Nick Caley is returning for his second season as the play caller](https://www.houstonchronicle.com/sports/texans/article/nick-caley-cj-stroud-schuplinski-22320553.php),
and the [current staff](https://www.houstontexans.com/team/coaches-roster/) retains
DeMeco Ryans, Caley, RB coach Danny Barrett, WR/pass-game coach Ben McDaniels, and
OL/run-game coach Cole Popovich. The QB and TE responsibilities changed holders, so
five of seven comparable core offensive responsibilities are retained. The broad
system score is 86.1 and the exact-style score is 77.4; both are uncalibrated evidence
indices, not probabilities.

The one-season caller fingerprint is pass-friendly overall: the frozen 2026 forecast
is 66.77 plays per game, a 60.73% pass rate, +0.76 percentage points of neutral
pass-over-expected, a 56.58% red-zone pass rate, and an 18.93% deep-attempt rate. Its
position target split is 62.42% WR, 23.49% TE, and 14.11% RB. That coexists with the
club's year-two camp emphasis on a more aggressive and physical offense rather than
overriding it. [System context](https://www.houstontexans.com/news/so-far-so-good-vanderblog)

The [current roster](https://www.houstontexans.com/team/players-roster/) contains
three active RBs—Woody Marks, David Montgomery, and British Brooks—and five active
WRs including Jared Wayne; Tank Dell is reserve/injured with a return designation.
The club's online [unofficial depth-chart page](https://www.houstontexans.com/team/depth-chart)
exposed no player rows when reviewed on September 3, so it was not used to invent an
ordering.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Jared Wayne, WR deep and end-zone targets | Wayne made his first initial 53 after three practice-squad seasons. Frozen 2025 history contains one deep target and no end-zone target among two total targets. Current reporting documents a first-team red-zone touchdown, another preseason end-zone catch, and multiple downfield completions. [Camp](https://www.houstontexans.com/news/harris-hits-jared-wayne-steals-the-show-at-august-7-texans-training-camp), [preseason](https://www.houstontexans.com/news/a-preseason-opener-that-belonged-to-the-young-guys), [deep shot](https://www.houstontexans.com/news/the-day-the-offense-took-over-in-charlotte) | Retain both nonzero directions. Direct current high-value usage does not validate the exact 6.4% deep and 6.3% end-zone shares, 7.28 and 2.10 season counts, or a regular route share in a five-WR room awaiting Dell. |
| Woody Marks, RB two-minute targets | Frozen 2025 history contains ten two-minute targets among 36 total targets. Current first-team work includes a hot-read completion against a free blitzer and two red-zone receiving touchdowns from C.J. Stroud. [Hot read](https://www.houstontexans.com/news/harris-hits-tank-dell-returns-to-team-drills-as-texans-defense-stays-hot), [joint practice](https://www.houstontexans.com/news/harris-hits-david-montgomery-runs-wild-as-texans-and-raiders-open-joint-practices) | Retain Marks as the leading nonzero two-minute direction. Same-system history and direct first-team receiving work do not validate the exact 51.9% share or 5.47 count. |
| David Montgomery, RB two-minute targets | Frozen 2021-25 history contains 16 two-minute targets among 182 total targets, but only two in 2023-25 and one in 2025. Current first-team work shows a checkdown and short receiving touchdown, while the reviewed two-minute reporting names no Montgomery route or target. [Current receiving work](https://www.houstontexans.com/news/harris-hits-jared-wayne-steals-the-show-at-august-7-texans-training-camp), [two-minute report](https://www.houstontexans.com/news/harris-hits-xavier-hutchinson-has-a-day-as-texans-close-out-houston-camp) | Leave the 37.4% share and 4.33 count inconclusive. General receiving ability in a new offense is not a documented hurry-up assignment. |
| British Brooks, inside-5 and inside-10 carries | Brooks is one of only three active RBs, and frozen history contains two inside-10 and two inside-5 carries among 18 career carries. A broken hand and surgery cost roughly three weeks of August evaluation; current first-party backfield reports center Montgomery and Marks and assign Brooks no short-yardage role. [Availability update](https://www.cbssports.com/fantasy/football/news/texans-british-brooks-back-at-practice/), [backfield report](https://www.houstontexans.com/news/harris-hits-david-montgomery-runs-wild-as-texans-and-raiders-open-joint-practices) | Leave the 12.8% inside-10 and 17.1% inside-5 shares and the 6.01 and 4.33 counts inconclusive. Active-roster membership plus two prior events does not establish the current goal-line order. |
| British Brooks, RB two-minute targets | [Pro Football Reference](https://www.pro-football-reference.com/players/B/BrooBr01.htm) records 71 offensive versus 274 special-teams snaps in 2025; frozen nflverse history records zero targets across his first 20 games. No reviewed current source assigns a hurry-up route or target. | Flag a direct role conflict while preserving the frozen number for auditability. The special-teams-heavy, zero-target record conflicts with a normal 10.7% two-minute share and 1.68 season count. |

## Atlanta Falcons audit

Atlanta has a recognizable offensive architecture but weak evidence for exact 2026
rates. [Kevin Stefanski confirmed Tommy Rees as the play caller](https://www.atlantafalcons.com/news/tommy-rees-offensive-play-caller-kevin-stefanski),
but Rees's only NFL calling sample is nine Cleveland games from Weeks 10-18 of 2025,
so the frozen caller model deliberately gives him no clean full-season anchor. The
[current staff](https://www.atlantafalcons.com/team/coaches-roster/) changes the head
coach, coordinator, quarterback, and receiver responsibilities while retaining RB
coach Michael Pitre, TE coach Kevin Koger, and one OL holder in Nick Jones. That is
three of seven comparable core responsibilities retained, a 42.9% retention share
and 33.9 continuity index. The broad-system evidence score is 67.9; exact style is
only 36.5. Those are uncalibrated evidence indices, not probabilities.

The directional scheme claim is much stronger. Rees identifies under-center
play-action as a core Stefanski principle; Atlanta says the run game will preserve
its wide-zone foundation, add gap complements, and vary the presentation.
[Coordinator introduction](https://www.atlantafalcons.com/news/coordinators-tommy-rees-jeff-ulbrich-craig-aukerman),
[run-game plan](https://www.atlantafalcons.com/news/kevin-stefanski-tommy-rees-run-game-bijan-robinson)
The first camp offense period then opened with three 13-personnel plays. The frozen
forecast is 63.46 plays per game, a 58.78% pass rate, -2.40 percentage points of
neutral pass-over-expected, 32.95% under center, 24.41% play action, and target shares
of 19.46% RB, 57.03% WR, and 23.57% TE. Because Rees has no clean anchor, use these
only as a wide scenario center. The position layer ranks Atlanta's structural
environment more favorably for RB (69.7 broad score, eighth) and TE (61.9, tenth)
than WR (33.4, 22nd), while all three exact-rate scores remain neutral or weaker.

The [current roster](https://www.atlantafalcons.com/team/players-roster/) controls
membership. The [current depth chart](https://www.atlantafalcons.com/team/depth-chart)
places Branch second on one WR line and first at kick returner, Blair second behind
Drake London, and Woerner first on a separate TE line while Pitts, Hooper, and Velling
occupy the other. Frozen nflverse play-by-play supplies the exact situational
definitions; Pro Football Reference supplies conventional player history.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Zachariah Branch, WR deep targets | The active rookie has no NFL target history. Atlanta's draft profile describes a screen-heavy, low-aDOT college role, but the first camp practice supplied a direct vertical-route touchdown behind A.J. Terrell and a safety. [Draft profile](https://www.atlantafalcons.com/news/2026-nfl-draft-falcons-select-zachariah-branch-third-round), [camp rep](https://www.atlantafalcons.com/news/falcons-training-camp-report-michael-penix-jr-limited-practice) | Retain a nonzero deep direction. One rep, rotational WR placement, and return duties do not validate the exact 10.4% no-history share or 10.27 season count. |
| Zachariah Branch, WR end-zone targets | The reviewed touchdown report does not state where the ball was targeted relative to the goal line, and no current source assigns Branch a scoring-area receiving package. | Leave the distinct 8.9% end-zone share and 2.65 count inconclusive. A touchdown result is not automatically an end-zone target under the metric definition. |
| Chris Blair, WR deep and end-zone targets | [Pro Football Reference](https://www.pro-football-reference.com/players/B/BlaiCh00.htm) records only two career targets; frozen nflverse data classifies both as deep and none as end-zone targets. Current camp placed him in bigger packages or behind London, documented a roughly 15-yard in-breaker that does not meet the 20-air-yard definition, and separately recorded a diving, two-feet end-zone touchdown. [Role report](https://www.atlantafalcons.com/news/falcons-camp-report-tua-tagovailoa-jawaan-taylor-tyler-goodson), [end-zone catch](https://www.atlantafalcons.com/news/falcons-camp-report-jack-strand-tua-tagovailoa) | Retain small nonzero directions. Prior exact deep usage and a current exact end-zone target do not validate the 6.5%/4.7% shares or 6.64/1.45 counts from two career targets and reserve work. |
| Charlie Woerner, TE deep targets | [Pro Football Reference](https://www.pro-football-reference.com/players/W/WoerCh00.htm) records 26 catches, no touchdowns, and 565 offensive snaps in 2025. Frozen history has three deep targets among 32 total, none since 2022. Atlanta calls him a highly regarded run blocker, says Hooper has the stronger receiving history, and used Woerner as a checkdown in the first camp practice. [Room preview](https://www.atlantafalcons.com/news/falcons-2026-training-camp-preview-tight-ends) | Flag a direct role conflict while preserving the frozen number. Blocking/checkdown evidence and three straight seasons without a deep target conflict with a normal 11.7% share and 2.96 count. |
| Charlie Woerner, TE two-minute targets | Heavy TE personnel and current checkdown work create a receiving path, but frozen history contains zero two-minute targets among 32 total and no reviewed 2026 report assigns a hurry-up route. | Leave the 12.3% share and 3.21 count inconclusive. Heavy personnel is not proof of two-minute personnel or route assignment. |
| Trey Sermon, RB two-minute targets | Atlanta [placed Sermon on injured reserve August 19](https://www.atlantafalcons.com/news/rb-trey-sermon-injured-reserve), eleven days before final cutdown. The [NFL roster FAQ](https://www.nfl.com/news/nfl-training-camp-roster-faqs-defining-injured-reserve-pup-list-nfi-and-more) makes pre-cutdown IR season-ineligible, and the [2026 calendar](https://operations.nfl.com/calendar-events/nfl-important-dates) limits the special return designation to placements during the August 30 reduction day. | The evidence-backed availability rebuild hard-zeros all 18 weeks and reduces the prior 0.36 season estimate to zero. This is a transaction-rule correction, not a medical forecast or manual share override. |

## Denver Broncos audit

Denver has substantially more system continuity than caller continuity. Sean Payton
[named Davis Webb the primary caller](https://www.denverbroncos.com/news/i-wouldn-t-do-it-if-i-didn-t-think-it-was-going-to-help-our-team-win-hc-sean-payton-announces-oc-davis-webb-to-call-plays-for-broncos-offense),
but Webb has never called a regular-season game. Payton expects to remain involved
and sometimes specify the play he wants. Webb separately says it is the same offense
for the most part, with small adjustments, and calls it a Sean Payton offensive
philosophy. [System continuity](https://www.denverbroncos.com/news/davis-webb-blessed-and-thankful-to-have-hc-sean-payton-as-resource-entering-first-season-as-broncos-oc)
The frozen caller model therefore has no clean full-season Webb anchor despite strong
destination-system continuity.

The [current staff](https://www.denverbroncos.com/team/coaches-roster/) retains Payton,
RB coach Lou Ayeni, TE coach Austin King, and the offensive-line responsibility while
changing offensive coordinator/play caller, quarterbacks coach, and receivers coach.
That is four of seven comparable core responsibilities retained, a 57.1% retention
share and 57.7 continuity index. The broad-system evidence score is 79.6, but exact
style is 59.3. Those are uncalibrated evidence indices, not probabilities. The frozen
forecast centers on 65.24 plays per game, a 62.70% pass rate, 57.40% neutral early-down
pass rate, 34.81% under-center rate, 23.84% play action, and target shares of 19.55%
RB, 59.99% WR, and 20.23% TE. Every exact metric carries only 47.5 certainty because
Webb lacks a regular-season caller sample. The position layer rates RB neutral (48.9,
15th) and TE neutral (45.2, 21st), so player-role claims should not be mistaken for a
strong position-wide recommendation.

The [initial 53](https://www.denverbroncos.com/news/first-look-at-the-broncos-2026-initial-53-man-roster)
keeps Dobbins, Harvey, Coleman, and Badie at RB and Engram, Trautman, Adkins, and
Bentley at TE. Denver's [public depth chart](https://www.denverbroncos.com/team/depth-chart/)
was last updated August 25, before final cuts, and is explicitly unofficial. It is
useful context but not a final Week 1 ordering. The frozen September 2 nflverse depth
snapshot used by the model instead orders Dobbins, Harvey, Coleman, and Badie first
through fourth; both charts remain role evidence rather than guaranteed deployment.
Frozen nflverse play-by-play supplies the exact situational history; Pro Football
Reference supplies conventional player history.

| Case | Source-backed finding | Audit decision |
| --- | --- | --- |
| Jonah Coleman, inside-5 and inside-10 carries | The active rookie has no NFL history. Denver calls him a physical runner who fits its style, and a first-party camp report records a series of strong red-zone plays including a rushing touchdown. The club also frames Dobbins, Harvey, and Coleman as a three-headed run group. [Fit](https://www.denverbroncos.com/news/there-was-a-lot-to-like-with-him-broncos-detail-why-fourth-round-pick-jonah-coleman-stood-out-at-running-back), [red-zone rep](https://www.denverbroncos.com/news/broncos-camp-observations-as-back-and-forth-camp-continues-denver-s-defense-responds-in-scrimmage-setting-on-day-8) | Retain nonzero goal-line directions. The evidence supports a path, not the exact 13.8% inside-10 and 13.9% inside-5 shares or 5.39 and 3.12 season counts. |
| Jonah Coleman, RB two-minute targets | Denver's draft evaluation credits his catching and pass protection, but no reviewed current source assigns him a hurry-up route or target. The published first-offense two-minute drive does not report an RB target. [Two-minute report](https://www.denverbroncos.com/news/broncos-camp-observations-denver-s-offense-shines-in-two-minute-drill-on-day-7) | Leave the no-history 15.4% share and 2.78 count inconclusive. General three-down traits are not a documented two-minute assignment. |
| Tyler Badie, RB two-minute targets | Denver explicitly linked Badie's final active-roster spot to third-down ability. Payton previously called him a good receiver and protector who can play in two-minute situations; frozen 2025 history contains 12 such targets among 31 total. [Roster decision](https://www.denverbroncos.com/news/first-look-at-the-broncos-2026-initial-53-man-roster), [role](https://www.denverbroncos.com/news/broncos-aiming-for-remarkably-different-run-game-as-rb-competition-continues) | Retain the elevated nonzero direction. Direct role language and same-team history support it, but do not validate the exact 25.8% share or 4.35 count. |
| Tyler Badie, inside-5 and inside-10 carries | Frozen history contains one inside-10 and one inside-5 carry among 20 career carries. Current evidence instead emphasizes special teams, protection, and third downs while the physical run-game group centers Dobbins, Harvey, and Coleman. | Flag a direct role conflict while preserving the frozen numbers. The evidence conflicts with treating the 5.3%/6.3% shares and 2.36/1.57 counts as established goal-line roles. |
| RJ Harvey, RB two-minute targets | Harvey had 58 frozen targets in 2025 but only two in the defined two-minute state. Current reporting says his protection and command improved and highlights receiving explosiveness; Badie has the direct hurry-up role evidence. [Year-2 report](https://www.denverbroncos.com/news/i-feel-like-that-s-my-game-rb-rj-harvey-enters-year-2-with-renewed-focus-on-making-big-plays) | Leave the history-adjusted 19.9% share and 3.48 count inconclusive. Harvey has a real passing-down path, but the current hurry-up split is unobserved. |
| Nate Adkins, TE deep targets | [Pro Football Reference](https://www.pro-football-reference.com/players/A/AdkiNa00.htm) records 24 catches, 185 yards, and four touchdowns through 2025. Frozen history has one deep target among 31 total, none in 2025, while Denver calls him a key run-game and special-teams component. [Role](https://www.denverbroncos.com/news/broncos-re-sign-te-nate-adkins-to-1-year-contract) | Flag a direct role conflict while preserving the 6.8% share and 1.65 count. A blocking-first rotation and one career deep target do not establish a vertical role. |
| Nate Adkins, TE two-minute targets | Adkins has conventional receiving experience but zero frozen two-minute targets among 31 total. The published 2026 drive documents two Engram completions but does not document an Adkins route or target. | Leave the 5.1% share and 1.36 count inconclusive. One report cannot fully exclude a small role, and the evidence does not establish one. |

## Reproducible artifacts

- reviewed evidence registry:
  `data/research/2026/player_role_evidence.json`
- reviewed status/rule evidence and 5,000-draw availability rebuild:
  `data/research/2026/player_status_evidence.json` and
  `data/derived/availability/2026/20260903T132328.323948Z/`
- conditional player-share priors and 368 review reasons:
  `data/derived/high_value_priors/2026/20260903T132359.548967Z/`
- player opportunity counts with row-level review flags:
  `data/derived/high_value_volumes/2026/20260903T132405.658654Z/`
- joined evidence audit, ranked queue, team-rate review, source table, and coverage:
  `data/derived/role_research/2026/20260903T132410.884456Z/`
- corrected immutable numeric bundle:
  `data/derived/prospective_freeze/2026/20260903T133149.697043Z/`

The audit snapshot verifies parent and evidence hashes, requires exact GSIS/team/
metric matches, rejects unknown source references, and fails if a record attempts a
numeric override.

## Next research order

1. Archive official roster, status, and role evidence before each game, then test
   whether structured depth/role claims improve the frozen prior out of sample. Only
   then consider a numeric adjustment.
2. Obtain a licensed or user-owned all-player route source; the public participation
   route field only identifies a primary receiver and cannot fill this lane.
3. Extend the completed direct caller-resource test to Week 18, decompose its
   component errors, and jointly calibrate the resource/rate/availability/share
   distribution rather than treating transferred or marginal radii as a calibrated
   forecast.
4. Keep efficiency and touchdowns separate from opportunity, and do not ask camp
   sentiment to proxy for either.
