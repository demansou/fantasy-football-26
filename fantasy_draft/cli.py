"""Command-line interface for rankings and in-draft recommendations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .availability import (
    AvailabilityDataError,
    build_weekly_availability,
    write_availability_snapshot,
)
from .caller_fingerprints import (
    CallerFingerprintDataError,
    build_caller_fingerprints,
    write_caller_fingerprint_snapshot,
)
from .caller_resource_backtest import (
    CallerResourceBacktestDataError,
    build_caller_resource_backtest,
    write_caller_resource_backtest_snapshot,
)
from .coaching import (
    CoachingDataError,
    build_coaching_census,
    load_playcaller_registry,
    write_coaching_census_snapshot,
)
from .continuity import (
    ContinuityDataError,
    build_staff_continuity,
    write_staff_continuity_snapshot,
)
from .environment import (
    EnvironmentDataError,
    build_team_environment_forecast,
    load_observed_styles,
    load_research_dataset,
    write_environment_snapshot,
)
from .high_value_history import (
    HighValueHistoryDataError,
    build_high_value_history,
    write_high_value_history_snapshot,
)
from .high_value_backtest import (
    HighValueBacktestDataError,
    build_high_value_backtest,
    write_high_value_backtest_snapshot,
)
from .high_value_priors import (
    HighValuePriorDataError,
    build_high_value_priors,
    write_high_value_prior_snapshot,
)
from .high_value_volume_backtest import (
    HighValueVolumeBacktestDataError,
    build_high_value_volume_backtest,
    write_high_value_volume_backtest_snapshot,
)
from .high_value_volumes import (
    HighValueVolumeDataError,
    build_high_value_volumes,
    write_high_value_volume_snapshot,
)
from .historical_certainty import (
    HistoricalCertaintyDataError,
    build_historical_certainty_evaluation,
    write_historical_certainty_snapshot,
)
from .io import load_draft_state, load_league, load_projections, load_team_profiles
from .models import DraftState
from .optimizer import DraftOptimizer, Recommendation
from .position_environments import (
    MODEL_STATUS as POSITION_ENVIRONMENT_MODEL_STATUS,
    PositionEnvironmentDataError,
    build_position_environments,
    write_position_environment_snapshot,
)
from .player_roles import (
    MODEL_STATUS as PLAYER_ROLE_MODEL_STATUS,
    PlayerRoleDataError,
    build_player_roles,
    write_player_role_snapshot,
)
from .playcaller_evidence import (
    PlaycallerEvidenceDataError,
    load_playcaller_evidence_registry,
    write_playcaller_evidence_snapshot,
)
from .prospective import (
    ProspectiveFreezeDataError,
    build_prospective_freeze,
    write_prospective_freeze,
)
from .role_backtest import (
    RoleBacktestDataError,
    build_role_backtest,
    write_role_backtest_snapshot,
)
from .role_research import (
    RoleResearchDataError,
    build_role_research_audit,
    write_role_research_snapshot,
)
from .resource_backtest import (
    ResourceBacktestDataError,
    build_resource_backtest,
    write_resource_backtest_snapshot,
)
from .transition_backtest import (
    TransitionBacktestDataError,
    build_transition_backtest,
    write_transition_backtest_snapshot,
)
from .transition_evaluation import (
    TransitionEvaluationDataError,
    build_transition_evaluation,
    write_transition_evaluation_snapshot,
)
from .sources.espn_playcallers import (
    EspnPlaycallerQuery,
    EspnPlaycallerSourceError,
    fetch_espn_playcallers,
    write_espn_playcaller_snapshot,
)
from .sources.ffc import FfcAdpQuery, FfcSourceError, fetch_ffc_adp, write_ffc_snapshot
from .sources.google_news import (
    GoogleNewsQuery,
    GoogleNewsSourceError,
    fetch_google_news,
    load_current_callers,
    write_google_news_snapshot,
)
from .sources.nflverse import (
    NflverseSourceError,
    NflverseStyleQuery,
    fetch_nflverse_style,
    write_nflverse_style_snapshot,
)
from .sources.nflverse_players import (
    NflversePlayerQuery,
    NflversePlayerSourceError,
    fetch_nflverse_player_context,
    write_nflverse_player_context_snapshot,
)
from .sources.nflverse_player_history import (
    NflversePlayerHistoryError,
    NflversePlayerHistoryQuery,
    fetch_nflverse_player_history,
    write_nflverse_player_history_snapshot,
)
from .sources.nfl_record_book import (
    NflRecordBookQuery,
    NflRecordBookSourceError,
    fetch_nfl_record_book_staff,
    write_nfl_record_book_snapshot,
)
from .sources.official_staff import (
    OFFICIAL_STAFF_URLS,
    OfficialStaffQuery,
    OfficialStaffSourceError,
    fetch_official_staff,
    write_official_staff_snapshot,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ff-draft",
        description="Explainable Yahoo PPR fantasy-football draft recommendations",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    season_fetch = subparsers.add_parser('fetch-season-usage', help='snapshot free regular-season NFL usage')
    season_fetch.add_argument('--season', type=int, default=2026)
    season_fetch.add_argument('--input', type=Path, help='offline nflverse weekly stats CSV; omit to fetch')
    season_fetch.add_argument('--output', type=Path, required=True, help='new JSON snapshot path (never overwritten)')

    season_update = subparsers.add_parser('season-update', help='update an interoperable season roster backup')
    season_update.add_argument('--state', type=Path, required=True)
    season_update.add_argument('--output', type=Path, required=True, help='new backup path; input is preserved')
    season_update.add_argument('--player', help='catalog player ID to add, move, or drop')
    destination = season_update.add_mutually_exclusive_group(required=True)
    destination.add_argument('--team', type=int, help='destination team number, 1-based')
    destination.add_argument('--drop', action='store_true')
    destination.add_argument('--undo', action='store_true')
    season_update.add_argument('--slot', choices=('Starter','Bench','IR'), default='Bench')
    season_update.add_argument('--catalog', type=Path, default=Path('web/data/players.ts'))

    season_report = subparsers.add_parser('season-research', help='roster-aware waiver and trade opportunity watchlists')
    season_report.add_argument('--state', type=Path, required=True, help='web season backup JSON')
    season_report.add_argument('--stats', type=Path, help='fetch-season-usage snapshot; omit for preseason-only research')
    season_report.add_argument('--catalog', type=Path, default=Path('web/data/players.ts'), help='player JSON array or generated TS catalog')
    season_report.add_argument('--through-week', type=int, help='exclude stats after this week; not a backtest')
    season_report.add_argument('--top', type=int, default=20)
    season_report.add_argument('--output', type=Path, required=True, help='new output directory containing report.json and report.md')

    rank = subparsers.add_parser("rank", help="rank an undrafted player pool")
    _add_inputs(rank, state_required=False)

    recommend = subparsers.add_parser("recommend", help="recommend the next pick from draft state")
    _add_inputs(recommend, state_required=True)

    fetch_ffc = subparsers.add_parser(
        "fetch-ffc-adp",
        help="fetch and snapshot Fantasy Football Calculator ADP",
    )
    fetch_ffc.add_argument("--season", required=True, type=int, help="NFL season, such as 2026")
    fetch_ffc.add_argument("--teams", type=int, default=10, help="league size (default: 10)")
    fetch_ffc.add_argument(
        "--scoring",
        choices=("standard", "half-ppr", "ppr"),
        default="ppr",
        help="FFC draft format (default: ppr)",
    )
    fetch_ffc.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw"),
        help="raw snapshot root (default: data/raw)",
    )
    fetch_ffc.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="HTTP timeout in seconds (default: 20)",
    )
    fetch_ffc.add_argument("--json", action="store_true", help="emit machine-readable summary")

    fetch_nflverse = subparsers.add_parser(
        "fetch-nflverse-style",
        help="derive observed team styles from nflverse play-by-play and rosters",
    )
    fetch_nflverse.add_argument(
        "--season",
        action="append",
        required=True,
        type=int,
        help="historical NFL season; repeat for multiple seasons",
    )
    fetch_nflverse.add_argument(
        "--season-type",
        choices=("REG", "POST"),
        default="REG",
        help="game type (default: REG)",
    )
    fetch_nflverse.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw"),
        help="raw snapshot root (default: data/raw)",
    )
    fetch_nflverse.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="per-asset HTTP timeout in seconds (default: 60)",
    )
    fetch_nflverse.add_argument(
        "--without-ftn-charting",
        action="store_true",
        help="skip FTN charting enrichments (motion, play action, RPO, and related rates)",
    )
    fetch_nflverse.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    fetch_players = subparsers.add_parser(
        "fetch-nflverse-players",
        help="snapshot current player IDs/rosters/depth plus historical usage and PFR snaps",
    )
    fetch_players.add_argument(
        "--season", required=True, type=int, help="current NFL season, such as 2026"
    )
    fetch_players.add_argument(
        "--history-season",
        action="append",
        type=int,
        help="historical usage season; repeat as needed (default: prior three seasons)",
    )
    fetch_players.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw"),
        help="raw snapshot root (default: data/raw)",
    )
    fetch_players.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="per-asset HTTP timeout in seconds (default: 60)",
    )
    fetch_players.add_argument(
        "--workers", type=int, default=6, help="parallel downloads (default: 6)"
    )
    fetch_players.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    fetch_player_history = subparsers.add_parser(
        "fetch-nflverse-player-history",
        help="snapshot weekly rosters, opening depth, and weekly opportunities for held-out tests",
    )
    fetch_player_history.add_argument(
        "--availability-season",
        action="append",
        type=int,
        help="weekly-roster season; repeat as needed (default: 2021-2025)",
    )
    fetch_player_history.add_argument(
        "--role-target-season",
        action="append",
        type=int,
        help="opening-depth target season; repeat as needed (default: 2023-2025)",
    )
    fetch_player_history.add_argument(
        "--role-history-lookback",
        type=int,
        default=3,
        help="prior stat seasons supplied to each role target (default: 3)",
    )
    fetch_player_history.add_argument(
        "--forecast-season",
        type=int,
        help="season whose team schedule drives current scenarios (default: latest target + 1)",
    )
    fetch_player_history.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw"),
        help="raw snapshot root (default: data/raw)",
    )
    fetch_player_history.add_argument(
        "--timeout",
        type=float,
        default=90.0,
        help="per-asset HTTP timeout in seconds (default: 90)",
    )
    fetch_player_history.add_argument(
        "--workers", type=int, default=6, help="parallel downloads (default: 6)"
    )
    fetch_player_history.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    build_high_value = subparsers.add_parser(
        "build-high-value-history",
        help="derive player goal-line, two-minute, air-yard, and FTN read usage",
    )
    build_high_value.add_argument(
        "--nflverse",
        required=True,
        type=Path,
        help="preserved nflverse team-style snapshot with raw PBP/rosters/FTN data",
    )
    build_high_value.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    build_high_value.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    fetch_staff = subparsers.add_parser(
        "fetch-official-staff",
        help="snapshot current coaching titles from official NFL club pages",
    )
    fetch_staff.add_argument(
        "--season", required=True, type=int, help="NFL season, such as 2026"
    )
    fetch_staff.add_argument(
        "--team",
        action="append",
        choices=tuple(OFFICIAL_STAFF_URLS),
        help="team abbreviation; repeat as needed (default: all 32 teams)",
    )
    fetch_staff.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw"),
        help="raw snapshot root (default: data/raw)",
    )
    fetch_staff.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="per-team HTTP timeout in seconds (default: 30)",
    )
    fetch_staff.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    fetch_record_book = subparsers.add_parser(
        "fetch-nfl-record-book-staff",
        help="snapshot historical coaching staffs from an official NFL record book",
    )
    fetch_record_book.add_argument(
        "--season", required=True, type=int, help="record-book season (2022-2025)"
    )
    fetch_record_book.add_argument(
        "--team",
        action="append",
        choices=tuple(OFFICIAL_STAFF_URLS),
        help="team abbreviation; repeat as needed (default: all 32 teams)",
    )
    fetch_record_book.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw"),
        help="raw snapshot root (default: data/raw)",
    )
    fetch_record_book.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP timeout in seconds (default: 60)",
    )
    fetch_record_book.add_argument(
        "--extraction-timeout",
        type=float,
        default=120.0,
        help="PDF text-extraction timeout in seconds (default: 120)",
    )
    fetch_record_book.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    fetch_historical_callers = subparsers.add_parser(
        "fetch-historical-playcallers",
        help="snapshot ESPN's all-team historical play-caller census",
    )
    fetch_historical_callers.add_argument(
        "--season", required=True, type=int, help="census season (2023-2025)"
    )
    fetch_historical_callers.add_argument(
        "--team",
        action="append",
        choices=tuple(OFFICIAL_STAFF_URLS),
        help="team abbreviation; repeat as needed (default: all 32 teams)",
    )
    fetch_historical_callers.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw"),
        help="raw snapshot root (default: data/raw)",
    )
    fetch_historical_callers.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds (default: 30)",
    )
    fetch_historical_callers.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    build_historical_caller_evidence = subparsers.add_parser(
        "build-playcaller-evidence",
        help="publish a complete source-dated researched play-caller registry",
    )
    build_historical_caller_evidence.add_argument(
        "--registry",
        required=True,
        type=Path,
        help="reviewed all-team play-caller evidence registry JSON",
    )
    build_historical_caller_evidence.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw"),
        help="snapshot root (default: data/raw)",
    )
    build_historical_caller_evidence.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    fetch_news = subparsers.add_parser(
        "fetch-team-news",
        help="snapshot an all-team offensive-environment news discovery queue",
    )
    fetch_news.add_argument("--season", required=True, type=int, help="target NFL season")
    fetch_news.add_argument(
        "--callers",
        required=True,
        type=Path,
        help="current coaching-census snapshot directory or teams.csv",
    )
    fetch_news.add_argument(
        "--team",
        action="append",
        choices=tuple(OFFICIAL_STAFF_URLS),
        help="team abbreviation; repeat as needed (default: all 32 teams)",
    )
    fetch_news.add_argument(
        "--lookback-days",
        type=int,
        default=45,
        help="Google News lookback window (default: 45)",
    )
    fetch_news.add_argument(
        "--max-articles-per-team",
        type=int,
        default=25,
        help="maximum RSS results retained for each team (default: 25)",
    )
    fetch_news.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw"),
        help="raw snapshot root (default: data/raw)",
    )
    fetch_news.add_argument(
        "--timeout", type=float, default=30.0, help="per-request timeout (default: 30)"
    )
    fetch_news.add_argument(
        "--workers", type=int, default=8, help="parallel requests (default: 8)"
    )
    fetch_news.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    build_census = subparsers.add_parser(
        "build-coaching-census",
        help="cross-check sourced play callers against an official staff snapshot",
    )
    build_census.add_argument(
        "--registry",
        type=Path,
        default=Path("data/research/2026/playcaller_census.json"),
        help="curated play-caller registry JSON",
    )
    build_census.add_argument(
        "--official-staff",
        required=True,
        type=Path,
        help="official staff snapshot directory or staff.csv",
    )
    build_census.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    build_census.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    build_continuity = subparsers.add_parser(
        "build-staff-continuity",
        help="measure official year-over-year offensive staff continuity",
    )
    build_continuity.add_argument(
        "--prior-staff",
        required=True,
        type=Path,
        help="prior official record-book snapshot directory or staff.csv",
    )
    build_continuity.add_argument(
        "--current-staff",
        required=True,
        type=Path,
        help="current official club snapshot directory or staff.csv",
    )
    build_continuity.add_argument(
        "--callers",
        required=True,
        type=Path,
        help="current coaching-census snapshot directory or teams.csv",
    )
    build_continuity.add_argument(
        "--prior-callers",
        required=True,
        type=Path,
        help="historical play-caller snapshot directory or callers.csv",
    )
    build_continuity.add_argument(
        "--aliases",
        type=Path,
        help="optional audited coach identity aliases JSON",
    )
    build_continuity.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    build_continuity.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    build_fingerprints = subparsers.add_parser(
        "build-caller-fingerprints",
        help="join audited play-caller seasons to observed offensive styles",
    )
    build_fingerprints.add_argument(
        "--current-census",
        required=True,
        type=Path,
        help="current coaching-census snapshot directory or teams.csv",
    )
    build_fingerprints.add_argument(
        "--continuity",
        required=True,
        type=Path,
        help="staff-continuity snapshot directory or teams.csv",
    )
    build_fingerprints.add_argument(
        "--historical-callers",
        required=True,
        action="append",
        type=Path,
        help="historical caller snapshot or callers.csv; repeat by season",
    )
    build_fingerprints.add_argument(
        "--styles",
        required=True,
        type=Path,
        help="nflverse style snapshot directory or team_style.csv",
    )
    build_fingerprints.add_argument(
        "--episode-overrides",
        type=Path,
        default=Path("data/research/2026/caller_episode_overrides.json"),
        help="audited historical episode additions/exclusions JSON",
    )
    build_fingerprints.add_argument(
        "--system-evidence",
        type=Path,
        default=Path("data/research/2026/system_evidence.json"),
        help="structured scheme identity and continuity evidence JSON",
    )
    build_fingerprints.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    build_fingerprints.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    build_position = subparsers.add_parser(
        "build-position-environments",
        help="rank team-level QB/RB/WR/TE opportunity from style forecasts",
    )
    build_position.add_argument(
        "--caller-fingerprints",
        required=True,
        type=Path,
        help="caller-fingerprint snapshot directory",
    )
    build_position.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    build_position.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    build_roles = subparsers.add_parser(
        "build-player-roles",
        help="allocate team opportunity pools into identity-audited player role ranges",
    )
    build_roles.add_argument(
        "--players",
        required=True,
        type=Path,
        help="nflverse player-context snapshot directory",
    )
    build_roles.add_argument(
        "--position-environments",
        required=True,
        type=Path,
        help="position-environment snapshot directory or CSV",
    )
    build_roles.add_argument(
        "--caller-fingerprints",
        required=True,
        type=Path,
        help="caller-fingerprint snapshot directory or metric_forecasts.csv",
    )
    build_roles.add_argument(
        "--observed-styles",
        required=True,
        type=Path,
        help="hash-bound nflverse team-style snapshot used by the caller model",
    )
    build_roles.add_argument(
        "--ffc-adp",
        type=Path,
        help="optional FFC snapshot directory or adp.csv for an audited market crosswalk",
    )
    build_roles.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    build_roles.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    build_availability = subparsers.add_parser(
        "build-availability",
        help="fit weekly status cohorts and simulate reconciled player-role scenarios",
    )
    build_availability.add_argument(
        "--player-history",
        required=True,
        type=Path,
        help="nflverse player-history snapshot directory",
    )
    build_availability.add_argument(
        "--players",
        required=True,
        type=Path,
        help="current nflverse player-context snapshot directory",
    )
    build_availability.add_argument(
        "--player-roles",
        required=True,
        type=Path,
        help="player-role snapshot containing all-affiliated candidate weights",
    )
    build_availability.add_argument(
        "--evidence",
        type=Path,
        default=Path("data/research/2026/player_status_evidence.json"),
        help="reviewed first-party status and rules evidence JSON",
    )
    build_availability.add_argument(
        "--simulation-draws",
        type=int,
        default=1000,
        help="Monte Carlo draws per team/week (default: 1000)",
    )
    build_availability.add_argument(
        "--random-seed", type=int, default=20260902, help="simulation seed"
    )
    build_availability.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    build_availability.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    build_role_test = subparsers.add_parser(
        "build-role-backtest",
        help="compare opening depth, prior usage, and the frozen role blend",
    )
    build_role_test.add_argument(
        "--player-history",
        required=True,
        type=Path,
        help="nflverse player-history snapshot directory",
    )
    build_role_test.add_argument(
        "--target-season",
        action="append",
        type=int,
        help="held-out target season; repeat as needed (default: all depth seasons)",
    )
    build_role_test.add_argument(
        "--history-lookback",
        type=int,
        default=3,
        help="strictly prior seasons used for player history (default: 3)",
    )
    build_role_test.add_argument(
        "--bootstrap-samples",
        type=int,
        default=2000,
        help="team-season cluster bootstrap samples (default: 2000)",
    )
    build_role_test.add_argument(
        "--random-seed", type=int, default=20260902, help="bootstrap seed"
    )
    build_role_test.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    build_role_test.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    build_high_value_test = subparsers.add_parser(
        "build-high-value-backtest",
        help="test whether prior high-value rates improve ordinary player role",
    )
    build_high_value_test.add_argument(
        "--player-history",
        required=True,
        type=Path,
        help="nflverse player-history snapshot directory",
    )
    build_high_value_test.add_argument(
        "--high-value-history",
        required=True,
        type=Path,
        help="derived high-value-history snapshot directory",
    )
    build_high_value_test.add_argument(
        "--target-season",
        action="append",
        type=int,
        help="held-out target season; repeat as needed",
    )
    build_high_value_test.add_argument(
        "--history-lookback",
        type=int,
        default=3,
        help="strictly prior seasons used for history (default: 3)",
    )
    build_high_value_test.add_argument(
        "--bootstrap-samples",
        type=int,
        default=2000,
        help="team-season cluster bootstrap samples (default: 2000)",
    )
    build_high_value_test.add_argument(
        "--random-seed", type=int, default=20260902, help="bootstrap seed"
    )
    build_high_value_test.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    build_high_value_test.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    build_high_value_volume_test = subparsers.add_parser(
        "build-high-value-volume-backtest",
        help="test team high-value event rates against a pooled league baseline",
    )
    build_high_value_volume_test.add_argument(
        "--high-value-history",
        required=True,
        type=Path,
        help="derived high-value-history snapshot directory",
    )
    build_high_value_volume_test.add_argument(
        "--high-value-role-backtest",
        required=True,
        type=Path,
        help="frozen player high-value-share backtest snapshot directory",
    )
    build_high_value_volume_test.add_argument(
        "--development-season",
        action="append",
        type=int,
        help="model-selection season; repeat as needed (default: 2023 and 2024)",
    )
    build_high_value_volume_test.add_argument(
        "--holdout-season",
        type=int,
        default=2025,
        help="untouched promotion-gate season (default: 2025)",
    )
    build_high_value_volume_test.add_argument(
        "--history-lookback",
        type=int,
        default=3,
        help="strictly prior seasons used for rates (default: 3)",
    )
    build_high_value_volume_test.add_argument(
        "--bootstrap-samples",
        type=int,
        default=2000,
        help="team-season cluster bootstrap samples (default: 2000)",
    )
    build_high_value_volume_test.add_argument(
        "--random-seed", type=int, default=20260903, help="bootstrap seed"
    )
    build_high_value_volume_test.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    build_high_value_volume_test.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    build_high_value_prior = subparsers.add_parser(
        "build-high-value-priors",
        help="freeze supported high-value signals into current conditional shares",
    )
    build_high_value_prior.add_argument(
        "--player-roles",
        required=True,
        type=Path,
        help="derived current player-role snapshot directory",
    )
    build_high_value_prior.add_argument(
        "--high-value-history",
        required=True,
        type=Path,
        help="derived high-value-history snapshot directory",
    )
    build_high_value_prior.add_argument(
        "--high-value-backtest",
        required=True,
        type=Path,
        help="frozen high-value backtest snapshot directory",
    )
    build_high_value_prior.add_argument(
        "--availability",
        required=True,
        type=Path,
        help="weekly availability snapshot built from the same player roles",
    )
    build_high_value_prior.add_argument(
        "--random-seed", type=int, default=20260902, help="scenario seed"
    )
    build_high_value_prior.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    build_high_value_prior.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    build_high_value_volume = subparsers.add_parser(
        "build-high-value-volumes",
        help="combine gated team event rates with player conditional shares",
    )
    build_high_value_volume.add_argument(
        "--player-roles",
        required=True,
        type=Path,
        help="derived current player-role snapshot directory",
    )
    build_high_value_volume.add_argument(
        "--high-value-history",
        required=True,
        type=Path,
        help="derived high-value-history snapshot directory",
    )
    build_high_value_volume.add_argument(
        "--high-value-priors",
        required=True,
        type=Path,
        help="frozen player high-value-share prior snapshot directory",
    )
    build_high_value_volume.add_argument(
        "--high-value-volume-backtest",
        required=True,
        type=Path,
        help="frozen team event-rate backtest snapshot directory",
    )
    build_high_value_volume.add_argument(
        "--resource-backtest",
        required=True,
        type=Path,
        help="frozen team resource-pool backtest and residual calibration snapshot",
    )
    build_high_value_volume.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    build_high_value_volume.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    build_role_research = subparsers.add_parser(
        "build-role-research-audit",
        help="join sourced current-role claims to flagged opportunity estimates",
    )
    build_role_research.add_argument(
        "--high-value-volumes",
        required=True,
        type=Path,
        help="derived high-value opportunity snapshot directory",
    )
    build_role_research.add_argument(
        "--evidence",
        type=Path,
        default=Path("data/research/2026/player_role_evidence.json"),
        help="reviewed current-role evidence JSON",
    )
    build_role_research.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    build_role_research.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    build_prospective = subparsers.add_parser(
        "build-prospective-freeze",
        help="freeze issued preseason forecasts for leakage-safe later scoring",
    )
    build_prospective.add_argument(
        "--caller-fingerprints",
        required=True,
        type=Path,
        help="derived caller-fingerprint snapshot directory",
    )
    build_prospective.add_argument(
        "--position-environments",
        required=True,
        type=Path,
        help="derived position-environment snapshot directory",
    )
    build_prospective.add_argument(
        "--player-roles",
        required=True,
        type=Path,
        help="derived player-role prior snapshot directory",
    )
    build_prospective.add_argument(
        "--availability",
        required=True,
        type=Path,
        help="derived weekly availability snapshot directory",
    )
    build_prospective.add_argument(
        "--high-value-priors",
        required=True,
        type=Path,
        help="derived conditional high-value role snapshot directory",
    )
    build_prospective.add_argument(
        "--high-value-volumes",
        required=True,
        type=Path,
        help="derived high-value opportunity-count snapshot directory",
    )
    build_prospective.add_argument(
        "--role-research",
        required=True,
        type=Path,
        help="complete current-role research audit snapshot directory",
    )
    build_prospective.add_argument(
        "--cutoff",
        required=True,
        help="forecast information cutoff as YYYY-MM-DD",
    )
    build_prospective.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    build_prospective.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    build_resource_test = subparsers.add_parser(
        "build-resource-backtest",
        help="backtest and provisionally calibrate team carry/target resource pools",
    )
    build_resource_test.add_argument(
        "--player-history",
        required=True,
        type=Path,
        help="nflverse player-history snapshot directory",
    )
    build_resource_test.add_argument(
        "--development-season",
        action="append",
        type=int,
        help="model-selection season; repeat as needed (default: 2023 and 2024)",
    )
    build_resource_test.add_argument(
        "--holdout-season",
        type=int,
        default=2025,
        help="untouched promotion-gate season (default: 2025)",
    )
    build_resource_test.add_argument(
        "--history-lookback",
        type=int,
        default=3,
        help="strictly prior seasons used for team resource rates (default: 3)",
    )
    build_resource_test.add_argument(
        "--bootstrap-samples",
        type=int,
        default=2000,
        help="team-season cluster bootstrap samples (default: 2000)",
    )
    build_resource_test.add_argument(
        "--random-seed", type=int, default=20260903, help="bootstrap seed"
    )
    build_resource_test.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    build_resource_test.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    evaluate_caller_resources = subparsers.add_parser(
        "evaluate-caller-resources",
        help="directly test caller-aware team opportunity pools",
    )
    evaluate_caller_resources.add_argument(
        "--backtest",
        action="append",
        required=True,
        type=Path,
        help="transition-backtest snapshot directory; repeat for every target season",
    )
    evaluate_caller_resources.add_argument(
        "--player-history",
        required=True,
        type=Path,
        help="nflverse player-history snapshot directory",
    )
    evaluate_caller_resources.add_argument(
        "--observed-styles",
        required=True,
        type=Path,
        help="hash-bound nflverse team-style snapshot used by every transition input",
    )
    evaluate_caller_resources.add_argument(
        "--development-season",
        action="append",
        type=int,
        help="calibration season; repeat as needed (default: 2023 and 2024)",
    )
    evaluate_caller_resources.add_argument(
        "--holdout-season",
        type=int,
        default=2025,
        help="untouched evaluation season (default: 2025)",
    )
    evaluate_caller_resources.add_argument(
        "--history-lookback",
        type=int,
        default=3,
        help="strictly prior seasons for conversion factors (default: 3)",
    )
    evaluate_caller_resources.add_argument(
        "--bootstrap-samples",
        type=int,
        default=5000,
        help="destination-team cluster bootstrap samples (default: 5000)",
    )
    evaluate_caller_resources.add_argument(
        "--random-seed", type=int, default=20260903, help="bootstrap seed"
    )
    evaluate_caller_resources.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    evaluate_caller_resources.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    build_backtest = subparsers.add_parser(
        "build-transition-backtest",
        help="test caller-aware style forecasts on time-correct transition cohorts",
    )
    build_backtest.add_argument(
        "--nflverse",
        required=True,
        type=Path,
        help="nflverse snapshot directory containing raw PBP, rosters, and FTN charting",
    )
    build_backtest.add_argument(
        "--prior-callers",
        required=True,
        type=Path,
        help="prior-season preseason play-caller snapshot or callers.csv",
    )
    build_backtest.add_argument(
        "--target-callers",
        required=True,
        type=Path,
        help="target-season preseason play-caller snapshot or callers.csv",
    )
    build_backtest.add_argument(
        "--changes",
        type=Path,
        default=Path("data/research/backtests/2024_opening_caller_changes.json"),
        help="audited in-window play-caller change registry JSON",
    )
    build_backtest.add_argument(
        "--week-end",
        action="append",
        type=int,
        help="target window end; repeat as needed (default: 6 and 8)",
    )
    build_backtest.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    build_backtest.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )

    evaluate_transitions = subparsers.add_parser(
        "evaluate-transition-backtests",
        help="pool fixed caller-transition cohorts and test held-out residual bands",
    )
    evaluate_transitions.add_argument(
        "--backtest",
        action="append",
        required=True,
        type=Path,
        help="transition-backtest snapshot directory; repeat for every target season",
    )
    evaluate_transitions.add_argument(
        "--development-season",
        action="append",
        type=int,
        help="interval-calibration season; repeat as needed (default: 2023 and 2024)",
    )
    evaluate_transitions.add_argument(
        "--holdout-season",
        type=int,
        default=2025,
        help="untouched interval-evaluation season (default: 2025)",
    )
    evaluate_transitions.add_argument(
        "--bootstrap-samples",
        type=int,
        default=20000,
        help="destination-team cluster bootstrap samples (default: 20000)",
    )
    evaluate_transitions.add_argument(
        "--random-seed", type=int, default=20260903, help="bootstrap seed"
    )
    evaluate_transitions.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    evaluate_transitions.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )
    evaluate_certainty = subparsers.add_parser(
        "evaluate-historical-certainty",
        help="test reconstructed style-evidence score bounds on held-out errors",
    )
    evaluate_certainty.add_argument(
        "--backtest",
        action="append",
        required=True,
        type=Path,
        help="transition-backtest snapshot directory; repeat for every target season",
    )
    evaluate_certainty.add_argument(
        "--continuity",
        action="append",
        required=True,
        type=Path,
        help="matching staff-continuity snapshot directory; repeat by target season",
    )
    evaluate_certainty.add_argument(
        "--development-season",
        action="append",
        type=int,
        help="score/interval development season; repeat (default: 2023 and 2024)",
    )
    evaluate_certainty.add_argument(
        "--holdout-season",
        type=int,
        default=2025,
        help="untouched score-evaluation season (default: 2025)",
    )
    evaluate_certainty.add_argument(
        "--bootstrap-samples",
        type=int,
        default=5000,
        help="team-season Spearman bootstrap samples (default: 5000)",
    )
    evaluate_certainty.add_argument(
        "--random-seed", type=int, default=20260903, help="bootstrap seed"
    )
    evaluate_certainty.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    evaluate_certainty.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )
    build_environment = subparsers.add_parser(
        "build-team-environment",
        help="combine measured history with sourced staff/news research",
    )
    build_environment.add_argument(
        "--research",
        type=Path,
        default=Path("data/research/2026/team_environment_pilot.json"),
        help="curated staff/news JSON",
    )
    build_environment.add_argument(
        "--styles",
        type=Path,
        required=True,
        help="team_style.csv from fetch-nflverse-style, or its snapshot directory",
    )
    build_environment.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived"),
        help="derived snapshot root (default: data/derived)",
    )
    build_environment.add_argument(
        "--json", action="store_true", help="emit machine-readable summary"
    )
    return parser


def _add_inputs(parser: argparse.ArgumentParser, *, state_required: bool) -> None:
    parser.add_argument("--league", required=True, type=Path, help="league settings JSON")
    parser.add_argument("--projections", required=True, type=Path, help="player projections CSV")
    parser.add_argument(
        "--team-profiles",
        type=Path,
        help="optional normalized team environment CSV",
    )
    parser.add_argument("--state", required=state_required, type=Path, help="current draft state JSON")
    parser.add_argument("--top", type=int, default=15, help="number of players to return (default: 15)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def _render_table(recommendations: list[Recommendation]) -> str:
    headers = ("#", "PLAYER", "POS", "TEAM", "PROJ", "VORP", "ADP", "SCORE", "PRIMARY REASON")
    rows: list[tuple[str, ...]] = []
    for rank, item in enumerate(recommendations, start=1):
        rows.append(
            (
                str(rank),
                item.player.name,
                item.player.position,
                item.player.team,
                f"{item.projected_points:.1f}",
                f"{item.vorp:+.1f}",
                "-" if item.player.adp is None else f"{item.player.adp:.1f}",
                f"{item.score:.1f}",
                item.reasons[1] if len(item.reasons) > 1 else item.reasons[0],
            )
        )
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]

    def render(row: tuple[str, ...]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))

    return "\n".join((render(headers), render(tuple("-" * width for width in widths)), *(render(row) for row in rows)))


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    if args.command in ('fetch-season-usage', 'season-update', 'season-research'):
        from .season import digest, fetch_usage, load_catalog, load_state, research, render_report, update_state, write_new
        try:
            if args.command == 'fetch-season-usage':
                result = fetch_usage(args.output, args.season, args.input)
                print(f'Saved {len(result["rows"])} player-weeks to {args.output}')
            elif args.command == 'season-update':
                state = load_state(args.state)
                if args.undo and args.player:
                    raise ValueError('--undo cannot be combined with --player')
                if not args.undo and not args.player:
                    raise ValueError('--player is required for a roster change')
                known = {p['id']: p for p in load_catalog(args.catalog)}
                known.update(state.get('playerInfo', {}))
                if not args.undo and args.player not in known and args.player not in state['owners']:
                    raise ValueError('Unknown player ID; provide a catalog including the player')
                updated = update_state(state, args.player, args.team - 1 if args.team is not None else None, args.slot, args.undo)
                if args.player in known:
                    player = known[args.player]
                    updated.setdefault('playerInfo', {})[args.player] = {k: player.get(k) for k in ('name','position','team','gsisId')}
                write_new(args.output, updated)
                print(f'Saved season roster to {args.output}; draft and input backup unchanged')
            else:
                if args.top < 1:
                    raise ValueError('--top must be positive')
                state = load_state(args.state)
                snapshot = json.loads(args.stats.read_text()) if args.stats else None
                report = research(state, load_catalog(args.catalog), snapshot, args.through_week)
                report['provenance'] = {name: {'path': str(path), 'sha256': digest(path.read_bytes())} for name, path in
                    [('roster', args.state), ('catalog', args.catalog), ('stats', args.stats)] if path}
                args.output.mkdir(parents=True, exist_ok=False)
                write_new(args.output / 'report.json', report)
                with (args.output / 'report.md').open('x') as handle:
                    handle.write(render_report(report, args.top))
                print(f'Saved {report["mode"]} to {args.output}')
            return 0
        except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
            print(f'error: {error}', file=sys.stderr)
            return 2

    if args.command == "fetch-ffc-adp":
        try:
            query = FfcAdpQuery(season=args.season, teams=args.teams, scoring=args.scoring)
            snapshot = fetch_ffc_adp(query, timeout=args.timeout)
            snapshot_path = write_ffc_snapshot(snapshot, args.output)
        except (FfcSourceError, OSError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2

        summary = {
            "snapshot": str(snapshot_path),
            "source": "Fantasy Football Calculator",
            "season": snapshot.query.season,
            "teams": snapshot.query.teams,
            "scoring": snapshot.query.scoring,
            "records": len(snapshot.records),
            "total_drafts": snapshot.total_drafts,
            "source_window": {
                "start": snapshot.window_start.isoformat(),
                "end": snapshot.window_end.isoformat(),
            },
            "retrieved_at": snapshot.retrieved_at.isoformat().replace("+00:00", "Z"),
            "raw_sha256": snapshot.raw_sha256,
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['records']} FFC ADP records from "
                f"{summary['total_drafts']:,} drafts to {snapshot_path}"
            )
            print(
                "Source window: "
                f"{summary['source_window']['start']} through {summary['source_window']['end']}"
            )
            print("ADP data from Fantasy Football Calculator; this feed is not a projection.")
        return 0

    if args.command == "fetch-nflverse-style":
        try:
            query = NflverseStyleQuery(
                tuple(args.season),
                season_type=args.season_type,
                include_ftn_charting=not args.without_ftn_charting,
            )
            snapshot = fetch_nflverse_style(query, timeout=args.timeout)
            snapshot_path = write_nflverse_style_snapshot(snapshot, args.output)
        except (NflverseSourceError, OSError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2

        summary = {
            "snapshot": str(snapshot_path),
            "source": "nflverse",
            "seasons": list(snapshot.query.seasons),
            "season_type": snapshot.query.season_type,
            "include_ftn_charting": snapshot.query.include_ftn_charting,
            "team_seasons": len(snapshot.records),
            "teams_per_season": {
                str(season): len(
                    {record.team for record in snapshot.records if record.season == season}
                )
                for season in snapshot.query.seasons
            },
            "retrieved_at": snapshot.retrieved_at.isoformat().replace("+00:00", "Z"),
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['team_seasons']} observed nflverse team-seasons "
                f"to {snapshot_path}"
            )
            print(
                "These are measured NFL style/outcome features, not fantasy projections."
            )
        return 0

    if args.command == "fetch-nflverse-players":
        try:
            history_seasons = tuple(args.history_season) if args.history_season else tuple(
                range(args.season - 3, args.season)
            )
            query = NflversePlayerQuery(
                season=args.season,
                history_seasons=history_seasons,
            )
            snapshot = fetch_nflverse_player_context(
                query,
                timeout=args.timeout,
                workers=args.workers,
            )
            snapshot_path = write_nflverse_player_context_snapshot(snapshot, args.output)
        except (NflversePlayerSourceError, OSError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2

        summary = {
            "snapshot": str(snapshot_path),
            "source": "nflverse player/roster/depth/stats plus PFR snaps",
            "season": snapshot.query.season,
            "history_seasons": list(snapshot.query.history_seasons),
            "roster_rows": len(snapshot.current_roster),
            "roster_team_count": len({row["team"] for row in snapshot.current_roster}),
            "latest_depth_rows": len(snapshot.current_depth_chart),
            "depth_team_count": len(snapshot.latest_depth_by_team),
            "historical_usage_rows": len(snapshot.historical_usage),
            "identity_review_rows": len(snapshot.identity_review),
            "retrieved_at": snapshot.retrieved_at.isoformat().replace("+00:00", "Z"),
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['roster_rows']} current roster rows, "
                f"{summary['latest_depth_rows']} latest depth rows, and "
                f"{summary['historical_usage_rows']} historical player-team seasons "
                f"to {snapshot_path}"
            )
            print(
                f"Source-review records: {summary['identity_review_rows']}; no source "
                "families were joined by player name."
            )
        return 0

    if args.command == "fetch-nflverse-player-history":
        try:
            query = NflversePlayerHistoryQuery(
                availability_seasons=tuple(args.availability_season or range(2021, 2026)),
                role_target_seasons=tuple(args.role_target_season or range(2023, 2026)),
                role_history_lookback=args.role_history_lookback,
                forecast_season=args.forecast_season,
            )
            snapshot = fetch_nflverse_player_history(
                query, timeout=args.timeout, workers=args.workers
            )
            snapshot_path = write_nflverse_player_history_snapshot(snapshot, args.output)
        except (NflversePlayerHistoryError, OSError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2

        summary = {
            "snapshot": str(snapshot_path),
            "source": "nflverse weekly rosters, depth charts, weekly stats, and schedule",
            "availability_seasons": list(snapshot.query.availability_seasons),
            "role_target_seasons": list(snapshot.query.role_target_seasons),
            "stat_seasons": list(snapshot.query.stat_seasons),
            "weekly_roster_rows": len(snapshot.weekly_rosters),
            "opening_depth_rows": len(snapshot.opening_depth),
            "weekly_opportunity_rows": len(snapshot.weekly_opportunities),
            "team_schedule_rows": len(snapshot.team_schedule),
            "source_review_rows": len(snapshot.source_review),
            "retrieved_at": snapshot.retrieved_at.isoformat().replace("+00:00", "Z"),
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['weekly_roster_rows']} weekly roster rows, "
                f"{summary['opening_depth_rows']} opening-depth rows, and "
                f"{summary['weekly_opportunity_rows']} player-week opportunity rows "
                f"to {snapshot_path}"
            )
            print(
                "Every cross-source player join is GSIS-only; pre-2025 depth rows retain "
                "their weaker Week-1-only temporal label."
            )
        return 0

    if args.command == "build-high-value-history":
        try:
            result = build_high_value_history(args.nflverse)
            snapshot_path = write_high_value_history_snapshot(result, args.output)
        except (HighValueHistoryDataError, OSError, ValueError, json.JSONDecodeError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        summary = {
            "snapshot": str(snapshot_path),
            "source": "nflverse play-by-play and FTN charting joined by game/play ID",
            "seasons": list(result.seasons),
            "player_week_rows": len(result.weekly_rows),
            "team_week_rows": len(result.team_week_rows),
            "source_review_rows": len(result.source_review),
            "coverage": list(result.coverage_rows),
            "model_status": "descriptive high-value opportunity; not a fantasy projection",
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['player_week_rows']} player-week high-value usage rows "
                f"for {result.seasons[0]}-{result.seasons[-1]} to {snapshot_path}"
            )
            print(
                "True route participation is not available in this source; the output "
                "keeps target reads, high-leverage targets, and carries separate."
            )
        return 0

    if args.command == "fetch-official-staff":
        try:
            query = OfficialStaffQuery(
                season=args.season,
                teams=tuple(args.team) if args.team else tuple(OFFICIAL_STAFF_URLS),
            )
            snapshot = fetch_official_staff(query, timeout=args.timeout)
            snapshot_path = write_official_staff_snapshot(snapshot, args.output)
        except (OfficialStaffSourceError, OSError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2

        summary = {
            "snapshot": str(snapshot_path),
            "source": "official NFL club coaching pages",
            "season": snapshot.query.season,
            "teams": list(snapshot.query.teams),
            "team_count": len(snapshot.query.teams),
            "records": len(snapshot.records),
            "offensive_records": sum(
                record.side == "offense" for record in snapshot.records
            ),
            "retrieved_at": snapshot.retrieved_at.isoformat().replace("+00:00", "Z"),
            "play_callers_inferred": False,
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['records']} official coaching-title records across "
                f"{summary['team_count']} teams to {snapshot_path}"
            )
            print(
                "These pages verify staff names and titles; actual play callers require "
                "separate sourced confirmation."
            )
        return 0

    if args.command == "fetch-nfl-record-book-staff":
        try:
            query = NflRecordBookQuery(
                season=args.season,
                teams=tuple(args.team) if args.team else tuple(OFFICIAL_STAFF_URLS),
            )
            snapshot = fetch_nfl_record_book_staff(
                query,
                timeout=args.timeout,
                extraction_timeout=args.extraction_timeout,
            )
            snapshot_path = write_nfl_record_book_snapshot(snapshot, args.output)
        except (NflRecordBookSourceError, OSError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2

        summary = {
            "snapshot": str(snapshot_path),
            "source": "Official NFL Record & Fact Book",
            "season": snapshot.query.season,
            "teams": list(snapshot.query.teams),
            "team_count": len(snapshot.query.teams),
            "records": len(snapshot.records),
            "offensive_records": sum(
                record.side == "offense" for record in snapshot.records
            ),
            "retrieved_at": snapshot.retrieved_at.isoformat().replace("+00:00", "Z"),
            "play_callers_inferred": False,
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['records']} historical coaching-title records across "
                f"{summary['team_count']} teams to {snapshot_path}"
            )
            print(
                "The record book freezes staff names and titles; actual play callers "
                "still require separate sourced confirmation."
            )
        return 0

    if args.command == "fetch-historical-playcallers":
        try:
            query = EspnPlaycallerQuery(
                season=args.season,
                teams=tuple(args.team) if args.team else tuple(OFFICIAL_STAFF_URLS),
            )
            snapshot = fetch_espn_playcallers(query, timeout=args.timeout)
            snapshot_path = write_espn_playcaller_snapshot(snapshot, args.output)
        except (EspnPlaycallerSourceError, OSError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2

        temporal_use = snapshot.records[0].to_row()["temporal_use"]
        summary = {
            "snapshot": str(snapshot_path),
            "source": "ESPN NFL Nation all-team play-caller census",
            "season": snapshot.query.season,
            "team_count": len(snapshot.records),
            "published_at": snapshot.published_at.isoformat(),
            "retrieved_at": snapshot.retrieved_at.isoformat().replace("+00:00", "Z"),
            "temporal_use": temporal_use,
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['team_count']} historical play-caller records "
                f"to {snapshot_path}"
            )
            if temporal_use == "historical_identity_only_not_preseason_backtest_evidence":
                print(
                    "The article is retrospective for this season and is excluded "
                    "from that season's preseason backtest inputs."
                )
            else:
                print("The article was available as preseason caller-identity evidence.")
        return 0

    if args.command == "fetch-team-news":
        try:
            caller_season, callers = load_current_callers(args.callers)
            if caller_season != args.season:
                raise GoogleNewsSourceError(
                    f"caller census season {caller_season} does not match {args.season}"
                )
            query = GoogleNewsQuery(
                season=args.season,
                teams=tuple(args.team) if args.team else tuple(OFFICIAL_STAFF_URLS),
                lookback_days=args.lookback_days,
                max_articles_per_team=args.max_articles_per_team,
            )
            snapshot = fetch_google_news(
                query,
                callers,
                timeout=args.timeout,
                workers=args.workers,
            )
            snapshot_path = write_google_news_snapshot(snapshot, args.output)
        except (GoogleNewsSourceError, OSError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2

        counts = {
            team: sum(article.team == team for article in snapshot.articles)
            for team in query.teams
        }
        summary = {
            "snapshot": str(snapshot_path),
            "season": query.season,
            "team_count": len(query.teams),
            "article_count": len(snapshot.articles),
            "articles_per_team": counts,
            "research_status": "metadata_only_unreviewed_not_model_evidence",
            "sentiment_used": False,
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['article_count']} discovery results across "
                f"{summary['team_count']} teams to {snapshot_path}"
            )
            print(
                "Headlines are research leads only; promote a read article into a "
                "structured claim before it can affect a forecast."
            )
        return 0

    if args.command == "build-playcaller-evidence":
        try:
            registry = load_playcaller_evidence_registry(args.registry)
            snapshot_path = write_playcaller_evidence_snapshot(registry, args.output)
        except (
            PlaycallerEvidenceDataError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        summary = {
            "snapshot": str(snapshot_path),
            "season": registry.season,
            "team_count": len(registry.teams),
            "confirmed_count": sum(
                team.identity_status == "confirmed" for team in registry.teams
            ),
            "ambiguous_count": sum(
                team.identity_status == "ambiguous" for team in registry.teams
            ),
            "temporal_use": registry.temporal_use,
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['team_count']} source-dated caller rows "
                f"to {snapshot_path}"
            )
            print(
                f"Confirmed: {summary['confirmed_count']}; ambiguous and retained "
                f"without hindsight resolution: {summary['ambiguous_count']}."
            )
        return 0

    if args.command == "build-coaching-census":
        try:
            registry_bytes = args.registry.read_bytes()
            registry = load_playcaller_registry(args.registry)
            census = build_coaching_census(registry, args.official_staff)
            snapshot_path = write_coaching_census_snapshot(
                census,
                args.output,
                registry_bytes=registry_bytes,
            )
        except (CoachingDataError, OSError, ValueError, json.JSONDecodeError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2

        summary = {
            "snapshot": str(snapshot_path),
            "season": registry.season,
            "as_of": registry.as_of.isoformat(),
            "team_count": len(registry.teams),
            "play_callers": {
                entry.team: entry.play_caller for entry in registry.teams
            },
            "status": "identity_census_only",
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['team_count']} verified play-caller assignments "
                f"to {snapshot_path}"
            )
            print(
                "Caller identities were cross-checked against official staff titles; "
                "this snapshot does not yet forecast style."
            )
        return 0

    if args.command == "build-staff-continuity":
        try:
            continuity = build_staff_continuity(
                args.prior_staff,
                args.current_staff,
                args.callers,
                args.prior_callers,
                aliases=args.aliases,
            )
            snapshot_path = write_staff_continuity_snapshot(
                continuity, args.output
            )
        except (ContinuityDataError, OSError, ValueError, json.JSONDecodeError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2

        summary = {
            "snapshot": str(snapshot_path),
            "season": continuity.season,
            "prior_season": continuity.prior_season,
            "team_count": len(continuity.team_rows),
            "model_status": "descriptive_not_style_certainty",
            "teams": [
                {
                    "team": row["team"],
                    "head_coach_status": row["head_coach_status"],
                    "offensive_coordinator_status": row[
                        "offensive_coordinator_status"
                    ],
                    "play_caller_on_prior_staff": row[
                        "play_caller_on_prior_staff"
                    ],
                    "staff_continuity_index_v0": row[
                        "staff_continuity_index_v0"
                    ],
                }
                for row in continuity.team_rows
            ],
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['team_count']} team staff-continuity records "
                f"to {snapshot_path}"
            )
            print(
                "The index is descriptive staff continuity, not calibrated style "
                "certainty or proof of prior-season play-calling responsibility."
            )
        return 0

    if args.command == "build-caller-fingerprints":
        try:
            result = build_caller_fingerprints(
                args.current_census,
                args.continuity,
                args.historical_callers,
                args.styles,
                args.episode_overrides,
                args.system_evidence,
            )
            snapshot_path = write_caller_fingerprint_snapshot(result, args.output)
        except (CallerFingerprintDataError, OSError, ValueError, json.JSONDecodeError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2

        summary = {
            "snapshot": str(snapshot_path),
            "season": result.season,
            "team_count": len(result.team_rows),
            "usable_full_season_episodes": sum(
                row["full_team_season_anchor"] == "true"
                for row in result.episode_rows
            ),
            "teams_without_recent_full_season_anchor": [
                row["team"]
                for row in result.team_rows
                if int(row["recent_full_season_anchor_count"]) == 0
            ],
            "model_status": "uncalibrated_evidence_score",
            "teams": [
                {
                    "team": row["team"],
                    "play_caller": row["play_caller"],
                    "broad_system_certainty_v0": row["broad_system_certainty_v0"],
                    "exact_style_certainty_v0": row["exact_style_certainty_v0"],
                    "recent_full_season_anchor_count": row[
                        "recent_full_season_anchor_count"
                    ],
                }
                for row in result.team_rows
            ],
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['team_count']} caller fingerprints and style "
                f"evidence scores to {snapshot_path}"
            )
            print(
                "Scores are uncalibrated evidence rubrics until the historical "
                "transition backtest maps them to forecast error."
            )
        return 0

    if args.command == "build-transition-backtest":
        try:
            result = build_transition_backtest(
                args.nflverse,
                args.prior_callers,
                args.target_callers,
                args.changes,
                windows=tuple(args.week_end) if args.week_end else (6, 8),
            )
            snapshot_path = write_transition_backtest_snapshot(result, args.output)
        except (
            TransitionBacktestDataError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        summary = {
            "snapshot": str(snapshot_path),
            "prior_season": result.prior_season,
            "target_season": result.target_season,
            "windows": list(result.windows),
            "prediction_rows": len(result.prediction_rows),
            "evaluation": result.evaluation,
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['prediction_rows']} time-correct forecast comparisons "
                f"to {snapshot_path}"
            )
            for comparison in result.evaluation["results"]["window_comparisons"]:
                print(
                    f"Weeks 1-{comparison['week_end']}: anchored caller-aware NMAE "
                    f"{comparison['anchored_caller_aware_nmae']:.3f} vs "
                    f"{comparison['anchored_shrunken_persistence_nmae']:.3f}; "
                    f"{comparison['anchored_team_win_count']}/"
                    f"{comparison['anchored_team_effect_count']} teams improved"
                )
            print(
                "This one-cohort result is exploratory and does not calibrate the "
                "0-100 certainty scores as probabilities."
            )
        return 0

    if args.command == "evaluate-transition-backtests":
        try:
            result = build_transition_evaluation(
                args.backtest,
                development_seasons=tuple(args.development_season or (2023, 2024)),
                holdout_season=args.holdout_season,
                bootstrap_samples=args.bootstrap_samples,
                random_seed=args.random_seed,
            )
            snapshot_path = write_transition_evaluation_snapshot(result, args.output)
        except (
            TransitionEvaluationDataError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        summary = {
            "snapshot": str(snapshot_path),
            "target_seasons": list(result.target_seasons),
            "development_seasons": list(result.development_seasons),
            "holdout_season": result.holdout_season,
            "evaluation": result.evaluation,
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            gate = result.evaluation["caller_mean_promotion_gate"]
            print(
                f"Saved the {len(result.target_seasons)}-season transition evaluation "
                f"to {snapshot_path}"
            )
            print(f"Caller-aware mean decision: {gate['decision']}.")
            for row in result.evaluation["heldout_interval_coverage"][
                "caller_aware_all_team_windows"
            ]:
                print(
                    f"2025 Weeks 1-{row['week_end']} caller-aware 90% residual-band "
                    f"coverage: {100 * row['coverage_rate']:.1f}% "
                    f"({row['covered_count']}/{row['comparison_count']})."
                )
            print(
                "The current 0-100 evidence scores remain uncalibrated because these "
                "bands are not conditional on historical evidence scores."
            )
        return 0

    if args.command == "evaluate-historical-certainty":
        try:
            result = build_historical_certainty_evaluation(
                args.backtest,
                args.continuity,
                development_seasons=tuple(
                    args.development_season or (2023, 2024)
                ),
                holdout_season=args.holdout_season,
                bootstrap_samples=args.bootstrap_samples,
                random_seed=args.random_seed,
            )
            snapshot_path = write_historical_certainty_snapshot(
                result, args.output
            )
        except (
            HistoricalCertaintyDataError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        summary = {
            "snapshot": str(snapshot_path),
            "target_seasons": list(result.target_seasons),
            "development_seasons": list(result.development_seasons),
            "holdout_season": result.holdout_season,
            "target_windows": list(result.windows),
            "team_score_count": len(result.team_score_rows),
            "excluded_score_count": sum(
                row["score_status"]
                != "eligible_one_year_lower_bound_diagnostic"
                for row in result.team_score_rows
            ),
            "promotion_gate": result.evaluation["promotion_gate"],
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['team_score_count']} historical score rows and "
                f"held-out diagnostics to {snapshot_path}"
            )
            for decision in summary["promotion_gate"]["score_results"]:
                print(
                    f"{decision['score_kind']}: promotion gate "
                    f"{'passed' if decision['promotion_gate_pass'] else 'failed'}."
                )
            print(
                "Recommendation: keep the current 0-100 values as evidence indices; "
                "do not use them to narrow 2026 style intervals."
            )
        return 0

    if args.command == "build-position-environments":
        try:
            result = build_position_environments(args.caller_fingerprints)
            snapshot_path = write_position_environment_snapshot(result, args.output)
        except (PositionEnvironmentDataError, OSError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        leaders = {
            position: [
                row["team"]
                for row in result.rows
                if row["position"] == position and int(row["league_rank"]) <= 5
            ]
            for position in ("QB", "RB", "WR", "TE")
        }
        summary = {
            "snapshot": str(snapshot_path),
            "season": result.season,
            "team_count": len({row["team"] for row in result.rows}),
            "row_count": len(result.rows),
            "top_five_by_position": leaders,
            "model_status": POSITION_ENVIRONMENT_MODEL_STATUS,
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['row_count']} team-position opportunity records "
                f"to {snapshot_path}"
            )
            print(
                "These are coaching/style opportunity pools, not player projections; "
                "roles, health, personnel quality, schedule, and efficiency are absent."
            )
        return 0

    if args.command == "build-player-roles":
        try:
            result = build_player_roles(
                args.players,
                args.position_environments,
                args.caller_fingerprints,
                observed_styles=args.observed_styles,
                ffc_adp=args.ffc_adp,
            )
            snapshot_path = write_player_role_snapshot(result, args.output)
        except (PlayerRoleDataError, OSError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        ffc_statuses: dict[str, int] = {}
        for row in result.ffc_crosswalk:
            status = str(row["match_status"])
            ffc_statuses[status] = ffc_statuses.get(status, 0) + 1
        summary = {
            "snapshot": str(snapshot_path),
            "season": result.season,
            "team_count": len({row["team"] for row in result.reconciliation}),
            "role_rows": len(result.roles),
            "resource_rooms": len(result.reconciliation),
            "maximum_reconciliation_error": max(
                (float(row["reconciliation_error"]) for row in result.reconciliation),
                default=0.0,
            ),
            "ffc_match_status_counts": dict(sorted(ffc_statuses.items())),
            "identity_review_rows": len(result.identity_review),
            "availability_review_rows": len(result.availability_review),
            "model_status": PLAYER_ROLE_MODEL_STATUS,
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['role_rows']} player-resource role priors across "
                f"{summary['resource_rooms']} reconciled team rooms to {snapshot_path}"
            )
            print(
                f"Identity review: {summary['identity_review_rows']} rows; availability "
                f"review: {summary['availability_review_rows']} non-ACT players."
            )
            print(
                "These are reconciled-current-ACT opportunity priors, not health, "
                "efficiency, touchdown, or fantasy-point projections."
            )
        return 0

    if args.command == "build-availability":
        try:
            result = build_weekly_availability(
                args.player_history,
                args.players,
                args.player_roles,
                args.evidence,
                simulation_draws=args.simulation_draws,
                random_seed=args.random_seed,
            )
            snapshot_path = write_availability_snapshot(result, args.output)
        except (AvailabilityDataError, OSError, ValueError, json.JSONDecodeError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        summary = {
            "snapshot": str(snapshot_path),
            "season": result.season,
            "availability_rows": len(result.weekly_availability),
            "expected_role_rows": len(result.weekly_expected_roles),
            "team_week_resource_rows": len(result.reconciliation),
            "maximum_reconciliation_error": max(
                (float(row["reconciliation_error"]) for row in result.reconciliation),
                default=0.0,
            ),
            "maximum_unallocated_draw_rate": max(
                (float(row["unallocated_draw_rate"]) for row in result.reconciliation),
                default=0.0,
            ),
            "evaluation": dict(result.evaluation),
            "simulation_draws": result.simulation_draws,
            "model_status": "population status prior, not individual medical forecast",
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['availability_rows']} weekly availability rows and "
                f"{summary['expected_role_rows']} reconciled role-scenario rows to "
                f"{snapshot_path}"
            )
            print(
                "Held-out overall Brier delta versus an active/non-active flag baseline: "
                f"{summary['evaluation']['overall_delta_vs_active_flag_baseline']:+.6f}."
            )
            print(
                "Probabilities are historical status-cohort marginals, not individualized "
                "medical return forecasts."
            )
        return 0

    if args.command == "build-role-backtest":
        try:
            result = build_role_backtest(
                args.player_history,
                target_seasons=(
                    tuple(args.target_season) if args.target_season else None
                ),
                history_lookback=args.history_lookback,
                bootstrap_samples=args.bootstrap_samples,
                random_seed=args.random_seed,
            )
            snapshot_path = write_role_backtest_snapshot(result, args.output)
        except (RoleBacktestDataError, OSError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        summary = {
            "snapshot": str(snapshot_path),
            "target_seasons": list(result.target_seasons),
            "prediction_rows": len(result.prediction_rows),
            "room_rows": len(result.room_rows),
            "comparison_rows": len(result.comparison_rows),
            "source_review_rows": len(result.source_review),
            "recommendation": dict(result.recommendation),
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['room_rows']} model-room evaluations for "
                f"{', '.join(map(str, result.target_seasons))} to {snapshot_path}"
            )
            means = result.recommendation["mean_total_variation_by_model"]
            print(
                "Aggregate mean total-variation error: "
                + ", ".join(f"{model}={value:.3f}" for model, value in means.items())
            )
            print(
                "Decision: "
                f"{'adopt' if result.recommendation['adopt_blend_v0_as_universal_model'] else 'do not adopt'} "
                "the current depth/history blend as one universal resource model."
            )
        return 0

    if args.command == "build-high-value-backtest":
        try:
            result = build_high_value_backtest(
                args.player_history,
                args.high_value_history,
                target_seasons=(
                    tuple(args.target_season) if args.target_season else None
                ),
                history_lookback=args.history_lookback,
                bootstrap_samples=args.bootstrap_samples,
                random_seed=args.random_seed,
            )
            snapshot_path = write_high_value_backtest_snapshot(result, args.output)
        except (
            HighValueBacktestDataError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        summary = {
            "snapshot": str(snapshot_path),
            "target_seasons": list(result.target_seasons),
            "prediction_rows": len(result.prediction_rows),
            "room_rows": len(result.room_rows),
            "comparison_rows": len(result.comparison_rows),
            "source_review_rows": len(result.source_review),
            "recommendation": dict(result.recommendation),
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['room_rows']} high-value model-room evaluations "
                f"to {snapshot_path}"
            )
            print(
                "Metrics passing the conservative retrospective gate: "
                + ", ".join(result.recommendation["supported_metrics"])
            )
            print(
                "Passing metrics still require a frozen prospective 2026 test; "
                "routes remain unavailable from the public source."
            )
        return 0

    if args.command == "build-high-value-volume-backtest":
        try:
            result = build_high_value_volume_backtest(
                args.high_value_history,
                args.high_value_role_backtest,
                development_seasons=(
                    tuple(args.development_season)
                    if args.development_season else (2023, 2024)
                ),
                holdout_season=args.holdout_season,
                history_lookback=args.history_lookback,
                bootstrap_samples=args.bootstrap_samples,
                random_seed=args.random_seed,
            )
            snapshot_path = write_high_value_volume_backtest_snapshot(
                result, args.output
            )
        except (
            HighValueVolumeBacktestDataError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        summary = {
            "snapshot": str(snapshot_path),
            "development_seasons": list(result.development_seasons),
            "holdout_season": result.holdout_season,
            "supported_metrics": list(result.supported_metrics),
            "prediction_rows": len(result.prediction_rows),
            "comparison_rows": len(result.comparison_rows),
            "calibration_rows": len(result.calibration_rows),
            "team_specific_metrics": result.recommendation[
                "team_specific_metrics"
            ],
            "recommendation": result.recommendation["recommendation"],
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['prediction_rows']} team-rate predictions and "
                f"{summary['calibration_rows']} rate calibrations to {snapshot_path}"
            )
            print(
                "Team-specific conditional rates passing the untouched holdout gate: "
                + (", ".join(summary["team_specific_metrics"]) or "none")
            )
            print(f"Decision: {summary['recommendation']}")
        return 0

    if args.command == "build-high-value-priors":
        try:
            result = build_high_value_priors(
                args.player_roles,
                args.high_value_history,
                args.high_value_backtest,
                args.availability,
                random_seed=args.random_seed,
            )
            snapshot_path = write_high_value_prior_snapshot(result, args.output)
        except (
            HighValuePriorDataError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        summary = {
            "snapshot": str(snapshot_path),
            "season": result.season,
            "supported_metrics": list(result.supported_metrics),
            "prior_rows": len(result.prior_rows),
            "team_metric_rows": len(result.room_rows),
            "weekly_rows": len(result.weekly_rows),
            "weekly_reconciliation_rows": len(result.weekly_reconciliation),
            "source_review_rows": len(result.source_review),
            "model_status": "conditional high-value share; not event volume or fantasy points",
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['prior_rows']} frozen high-value player priors and "
                f"{summary['weekly_rows']} availability-adjusted weekly shares to "
                f"{snapshot_path}"
            )
            print(
                "Scope: conditional share of a named team-position event only; "
                "team event volume and production remain unmodeled."
            )
        return 0

    if args.command == "build-high-value-volumes":
        try:
            result = build_high_value_volumes(
                args.player_roles,
                args.high_value_history,
                args.high_value_priors,
                args.high_value_volume_backtest,
                args.resource_backtest,
            )
            snapshot_path = write_high_value_volume_snapshot(result, args.output)
        except (
            HighValueVolumeDataError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        summary = {
            "snapshot": str(snapshot_path),
            "season": result.season,
            "supported_metrics": list(result.supported_metrics),
            "team_metric_rows": len(result.team_pool_rows),
            "player_metric_rows": len(result.player_rows),
            "weekly_player_metric_rows": len(result.weekly_rows),
            "weekly_reconciliation_rows": len(result.reconciliation_rows),
            "source_review_rows": len(result.source_review),
            "team_specific_rate_metrics": result.backtest_recommendation[
                "team_specific_metrics"
            ],
            "model_status": "high-value opportunity counts; not production or fantasy points",
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['team_metric_rows']} team event pools and "
                f"{summary['player_metric_rows']} player opportunity priors to "
                f"{snapshot_path}"
            )
            print(
                "Team-specific conditional-rate models used: "
                + (", ".join(summary["team_specific_rate_metrics"]) or "none; pooled league rates passed the gate")
            )
            print("Scope: named opportunity counts only; no efficiency or fantasy points.")
        return 0

    if args.command == "build-role-research-audit":
        try:
            result = build_role_research_audit(
                args.high_value_volumes,
                args.evidence,
            )
            snapshot_path = write_role_research_snapshot(result, args.output)
        except (
            RoleResearchDataError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        player_reviewed = sum(
            row["review_status"] != "unreviewed"
            for row in result.player_review_rows
        )
        team_reviewed = sum(
            row["review_status"] != "unreviewed"
            for row in result.team_review_rows
        )
        summary = {
            "snapshot": str(snapshot_path),
            "season": result.season,
            "as_of": result.as_of.isoformat(),
            "evidence_sources": len(result.source_rows),
            "player_review_queue_rows": len(result.player_review_rows),
            "player_evidence_reviewed_rows": player_reviewed,
            "player_unreviewed_rows": len(result.player_review_rows) - player_reviewed,
            "team_rate_review_queue_rows": len(result.team_review_rows),
            "team_rate_evidence_reviewed_rows": team_reviewed,
            "numeric_overrides_applied": 0,
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['player_review_queue_rows']} flagged player/metric "
                f"rows and {summary['team_rate_review_queue_rows']} team-rate rows "
                f"to {snapshot_path}"
            )
            print(
                f"Evidence reviewed: {player_reviewed} player rows and "
                f"{team_reviewed} team-rate rows; numeric overrides applied: 0."
            )
        return 0

    if args.command == "build-prospective-freeze":
        try:
            result = build_prospective_freeze(
                args.caller_fingerprints,
                args.position_environments,
                args.player_roles,
                args.availability,
                args.high_value_priors,
                args.high_value_volumes,
                args.role_research,
                cutoff=args.cutoff,
            )
            snapshot_path = write_prospective_freeze(result, args.output)
        except (
            ProspectiveFreezeDataError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        summary = {
            "snapshot": str(snapshot_path),
            "season": result.season,
            "forecast_cutoff": result.cutoff.isoformat(),
            "first_scheduled_game": result.first_scheduled_game.isoformat(),
            "freeze_fingerprint": result.freeze_fingerprint,
            "team_count": result.quality["team_count"],
            "artifact_count": len(result.artifacts),
            "weekly_availability_rows": result.quality[
                "weekly_availability_rows"
            ],
            "weekly_role_rows": result.quality["weekly_role_rows"],
            "weekly_high_value_count_rows": result.quality[
                "weekly_high_value_count_rows"
            ],
            "role_review_queue_rows": result.quality["role_review_queue_rows"],
            "role_review_unreviewed_rows": result.quality[
                "role_review_unreviewed_rows"
            ],
            "numeric_overrides_applied": result.quality[
                "numeric_overrides_applied"
            ],
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Frozen {summary['artifact_count']} forecast artifacts for "
                f"{summary['team_count']} teams at {snapshot_path}"
            )
            print(
                f"Cutoff {summary['forecast_cutoff']} precedes the first scheduled "
                f"game on {summary['first_scheduled_game']}."
            )
            print(f"Freeze fingerprint: {summary['freeze_fingerprint']}")
        return 0

    if args.command == "build-resource-backtest":
        try:
            result = build_resource_backtest(
                args.player_history,
                development_seasons=(
                    tuple(args.development_season)
                    if args.development_season else (2023, 2024)
                ),
                holdout_season=args.holdout_season,
                history_lookback=args.history_lookback,
                bootstrap_samples=args.bootstrap_samples,
                random_seed=args.random_seed,
            )
            snapshot_path = write_resource_backtest_snapshot(result, args.output)
        except (
            ResourceBacktestDataError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        summary = {
            "snapshot": str(snapshot_path),
            "development_seasons": list(result.development_seasons),
            "holdout_season": result.holdout_season,
            "resources": [row["resource"] for row in result.calibration_rows],
            "prediction_rows": len(result.prediction_rows),
            "comparison_rows": len(result.comparison_rows),
            "calibration_rows": len(result.calibration_rows),
            "team_reference_resources": result.recommendation[
                "team_reference_resources"
            ],
            "minimum_holdout_coverage": min(
                float(row["holdout_coverage"]) for row in result.calibration_rows
            ),
            "current_mean_status": "caller-aware mean retained; empirical radius transfer is provisional",
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['prediction_rows']} resource forecasts and "
                f"{summary['calibration_rows']} error radii to {snapshot_path}"
            )
            print(
                "Team-history references passing the untouched holdout gate: "
                + (", ".join(summary["team_reference_resources"]) or "none")
            )
            print(summary["current_mean_status"])
        return 0

    if args.command == "evaluate-caller-resources":
        try:
            result = build_caller_resource_backtest(
                args.backtest,
                args.player_history,
                args.observed_styles,
                development_seasons=tuple(
                    args.development_season or (2023, 2024)
                ),
                holdout_season=args.holdout_season,
                history_lookback=args.history_lookback,
                bootstrap_samples=args.bootstrap_samples,
                random_seed=args.random_seed,
            )
            snapshot_path = write_caller_resource_backtest_snapshot(
                result, args.output
            )
        except (
            CallerResourceBacktestDataError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        mean_gate = result.evaluation["caller_aware_mean_gate"]
        interval_gate = result.evaluation["caller_aware_interval_gate"]
        summary = {
            "snapshot": str(snapshot_path),
            "target_seasons": list(result.target_seasons),
            "development_seasons": list(result.development_seasons),
            "holdout_season": result.holdout_season,
            "target_windows": list(result.windows),
            "resource_count": len({row["resource"] for row in result.prediction_rows}),
            "prediction_count": len(result.prediction_rows),
            "mean_decision": mean_gate["decision"],
            "promoted_resources": mean_gate["promoted_resources"],
            "interval_decision": interval_gate["decision"],
            "undercovered_resource_windows": interval_gate[
                "undercovered_resource_windows"
            ],
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"Saved {summary['prediction_count']} direct resource predictions "
                f"to {snapshot_path}"
            )
            print(f"Caller-aware mean decision: {summary['mean_decision']}.")
            print(f"Interval decision: {summary['interval_decision']}.")
        return 0

    if args.command == "build-team-environment":
        style_path = args.styles / "team_style.csv" if args.styles.is_dir() else args.styles
        try:
            research_bytes = args.research.read_bytes()
            style_bytes = style_path.read_bytes()
            research = load_research_dataset(args.research)
            styles = load_observed_styles(style_path)
            forecast = build_team_environment_forecast(research, styles)
            snapshot_path = write_environment_snapshot(
                forecast,
                args.output,
                research_bytes=research_bytes,
                observed_style_bytes=style_bytes,
            )
        except (EnvironmentDataError, OSError, ValueError, json.JSONDecodeError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2

        summary = {
            "snapshot": str(snapshot_path),
            "season": forecast["season"],
            "as_of": forecast["as_of"],
            "calibration_status": forecast["calibration_status"],
            "teams": [
                {
                    "team": team["team"],
                    "play_caller": team["play_caller"],
                    "style_certainty": team["certainty"]["style_score"],
                    "certainty_tier": team["certainty"]["tier"],
                    "position_environments": {
                        position: values["score"]
                        for position, values in team["position_environments"].items()
                    },
                }
                for team in forecast["teams"]
            ],
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(f"Saved {len(summary['teams'])} team environment forecasts to {snapshot_path}")
            for team in summary["teams"]:
                print(
                    f"{team['team']}: {team['play_caller']} — style certainty "
                    f"{team['style_certainty']:.1f} ({team['certainty_tier']})"
                )
            print("Warning: certainty and environment scores are uncalibrated heuristic v0 indices.")
        return 0

    if args.top < 1:
        parser.error("--top must be positive")

    try:
        league = load_league(args.league)
        projections = load_projections(args.projections)
        team_profiles = load_team_profiles(args.team_profiles) if args.team_profiles else ()
        state = (
            load_draft_state(args.state)
            if args.state
            else DraftState(my_team=1, draft_slot=1)
        )
        recommendations = DraftOptimizer(league, projections, team_profiles).recommend(
            state,
            limit=args.top,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.json:
        payload = {
            "league": league.name,
            "current_pick": state.current_pick,
            "recommendations": [item.to_dict() for item in recommendations],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(f"{league.name} — recommendation at overall pick {state.current_pick}\n")
        print(_render_table(recommendations))
        if recommendations:
            best = recommendations[0]
            print(f"\nWhy {best.player.name}: " + "; ".join(best.reasons))
            weights = best.adaptive_weights
            signals = best.draft_signals
            print(
                "Live weights: "
                f"VORP {weights['vorp']:.2f}, need {weights['need']:.2f}, "
                f"scarcity {weights['scarcity']:.2f}, ADP {weights['adp']:.2f}, "
                f"context {weights['analytics']:.2f} "
                f"(round {signals['current_round']:.0f}, "
                f"run pressure {signals['position_run_pressure']:.0%})"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
