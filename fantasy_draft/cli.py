"""Command-line interface for rankings and in-draft recommendations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .io import load_draft_state, load_league, load_projections, load_team_profiles
from .models import DraftState
from .optimizer import DraftOptimizer, Recommendation


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ff-draft",
        description="Explainable Yahoo PPR fantasy-football draft recommendations",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    rank = subparsers.add_parser("rank", help="rank an undrafted player pool")
    _add_inputs(rank, state_required=False)

    recommend = subparsers.add_parser("recommend", help="recommend the next pick from draft state")
    _add_inputs(recommend, state_required=True)
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
