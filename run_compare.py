"""Shared comparison runner used by CLI and Render worker."""

from __future__ import annotations

import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from compare import compare_main_markets, match_events
from compare_props import compare_props, match_odds_api_event, rows_to_dicts
from gs_client import GSClient
from gs_props import extract_props_for_event
from odds_api_client import OddsApiClient
from pinnacle_client import PinnacleClient


def load_settings() -> dict[str, Any]:
    return {
        "gs_base_url": os.getenv("GS_BASE_URL", "https://ppm.sportswidgets.pro"),
        "gs_line_set": os.getenv("GS_LINE_SET", "U0VWU1NWUkJSMFU9"),
        "pinnacle_base_url": os.getenv("PINNACLE_BASE_URL", "https://guest.api.arcadia.pinnacle.com/0.1"),
        "pinnacle_mlb_league_id": int(os.getenv("PINNACLE_MLB_LEAGUE_ID", "246")),
        "hours": int(os.getenv("HOURS", "48")),
        "partial_id": os.getenv("GS_PARTIAL_ID") or None,
        "event_id": os.getenv("GS_EVENT_ID") or None,
        "include_full_gs_lines": os.getenv("INCLUDE_FULL_GS_LINES", "false").lower() in {"1", "true", "yes"},
        "compare_props": os.getenv("COMPARE_PROPS", "true").lower() in {"1", "true", "yes"},
        "the_odds_api_key": os.getenv("THE_ODDS_API_KEY") or None,
        "max_prop_rows_per_game": int(os.getenv("MAX_PROP_ROWS_PER_GAME", "100")),
    }


def run_comparison(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or load_settings()

    gs = GSClient(
        base_url=settings["gs_base_url"],
        line_set=settings["gs_line_set"],
    )
    pinnacle = PinnacleClient(
        base_url=settings["pinnacle_base_url"],
        mlb_league_id=settings["pinnacle_mlb_league_id"],
    )

    updates = gs.fetch_updates()
    coefficients = updates["coefficients"]
    event_to_partial = {event_id: partial for partial, event_id in updates["partial_map"].items()}
    gs_events = gs.list_mlb_events(hours_ahead=settings["hours"])
    pinnacle_events = pinnacle.list_mlb_matchups()

    if settings.get("partial_id"):
        resolved = gs.event_by_partial_id(str(settings["partial_id"]), updates)
        if not resolved:
            raise RuntimeError(f"Could not resolve partial id {settings['partial_id']}")
        gs_events = [event for event in gs_events if event.event_id == resolved]
        if not gs_events:
            gs_events = [
                event
                for event in gs.list_mlb_events(hours_ahead=24 * 14)
                if event.event_id == resolved
            ]
        if not gs_events:
            raise RuntimeError(f"Resolved event {resolved} is not in the MLB schedule feed")

    if settings.get("event_id"):
        gs_events = [event for event in gs_events if event.event_id == settings["event_id"]]

    matches = match_events(gs_events, pinnacle_events)
    games: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    prop_comparisons: list[dict[str, Any]] = []

    odds_api = None
    odds_events = []
    if settings["compare_props"] and settings.get("the_odds_api_key"):
        odds_api = OddsApiClient(settings["the_odds_api_key"])
        odds_events = odds_api.build_event_index(odds_api.list_mlb_events())

    for match in matches:
        gs_lines = gs.extract_lines(match.gs_event.event_id, updates)
        pinnacle_lines = pinnacle.fetch_markets(match.pinnacle_event.matchup_id)
        rows = compare_main_markets(match, gs_lines, pinnacle_lines)
        comparisons.extend(asdict(row) for row in rows)

        game_label = f"{match.gs_event.team1} @ {match.gs_event.team2}"
        game_props: list[dict[str, Any]] = []
        game_prop_rows: list[dict[str, Any]] = []

        if settings["compare_props"]:
            coeff = coefficients.get(str(match.gs_event.event_id), {})
            gs_props = extract_props_for_event(
                match.gs_event.event_id,
                coeff,
                gs.market_name,
            )
            game_props = [asdict(prop) for prop in gs_props]

            if odds_api and odds_events:
                odds_event = match_odds_api_event(
                    match.pinnacle_event.home_team,
                    match.pinnacle_event.away_team,
                    match.gs_event.start_time,
                    odds_events,
                )
                if odds_event:
                    reference_lines = odds_api.fetch_event_props(odds_event["id"])
                    prop_rows = compare_props(game_label, gs_props, reference_lines)
                    limit = settings["max_prop_rows_per_game"]
                    game_prop_rows = rows_to_dicts(prop_rows[:limit])
                    prop_comparisons.extend(game_prop_rows)

        game_payload: dict[str, Any] = {
            "gs_event_id": match.gs_event.event_id,
            "gs_partial_id": event_to_partial.get(match.gs_event.event_id),
            "pinnacle_matchup_id": match.pinnacle_event.matchup_id,
            "teams": [match.gs_event.team1, match.gs_event.team2],
            "start_time": match.gs_event.start_time.isoformat(),
            "gs_line_count": len(gs_lines),
            "gs_prop_count": len(game_props),
            "prop_comparison_count": len(game_prop_rows),
            "main_market_rows": [asdict(row) for row in rows],
            "prop_rows": game_prop_rows,
        }
        if settings["include_full_gs_lines"]:
            game_payload["gs_lines"] = [asdict(line) for line in gs_lines]
        if settings["compare_props"]:
            game_payload["gs_props"] = game_props

        games.append(game_payload)

    top_prop_edges = sorted(
        prop_comparisons,
        key=lambda row: abs(row.get("edge_vs_best") or 0),
        reverse=True,
    )[:25]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gs_line_set": gs.decode_line_set(gs.line_set),
        "gs_game_count": len(gs_events),
        "pinnacle_game_count": len(pinnacle_events),
        "matched_game_count": len(matches),
        "comparison_row_count": len(comparisons),
        "prop_comparison_row_count": len(prop_comparisons),
        "props_enabled": settings["compare_props"],
        "reference_books_configured": bool(settings.get("the_odds_api_key")),
        "games": games,
        "comparisons": comparisons,
        "prop_comparisons": prop_comparisons,
        "top_prop_edges": top_prop_edges,
    }
