# Team-environment research inputs

Files in this directory are curated, dated evidence inputs rather than generated
model output. Each staff assignment and news claim must cite a source record, and a
living web page must use a null `published_at` rather than an invented date.

`2026/team_environment_pilot.json` is the initial KC/SEA/PHI methodology pilot. It
deliberately records Klint Kubiak as absent from Seattle's 2026 staff: Brian Fleury
is the current coordinator and confirmed first-time NFL play caller. The Seattle
continuity prior comes from retained staff/personnel, common Shanahan lineage, and
the team's own documented intent to preserve the 2025 foundation.

Reliability is source credibility for the specific claim. Strength is how directly
the source supports the normalized claim. `certainty_effect` changes confidence,
while `metric_signals` express a small directional update; the forecast caps news
movement so a camp quote cannot overpower measured history.

`2026/playcaller_census.json` is the full-league current caller evidence registry.
It contains all 32 head coaches, primary offensive coordinators, actual callers, and
the separate sources that establish calling responsibility. The
`build-coaching-census` command exact-matches it to a timestamped official-staff
snapshot and refuses to publish if a title differs, a caller is absent, a source is
dangling, a team is missing, or a caller remains unresolved. It deliberately does
not contain unaudited career histories or style-confidence claims.

`2026/player_status_evidence.json` contains the first reviewed player-level
availability/affiliation claims promoted from the automated exception queues. It is
limited to seven FFC-listed cases that were not current-active on September 2. The
claims use official club or NFL sources to resolve status, team affiliation, and
rule-backed minimum absence. After a hard constraint, unknown timing may use only the
explicitly labeled historical status-cohort scenario. The evidence never authorizes
a manually invented player return probability or role share.
