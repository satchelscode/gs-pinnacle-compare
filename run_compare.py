"""Shared comparison runner used by CLI and Render worker."""

from __future__ import annotations

import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from compare import compare_main_markets, match_events
from gs_client import GSClient
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

    for match in matches:
        gs_lines = gs.extract_lines(match.gs_event.event_id, updates)
        pinnacle_lines = pinnacle.fetch_markets(match.pinnacle_event.matchup_id)
        rows = compare_main_markets(match, gs_lines, pinnacle_lines)
        comparisons.extend(asdict(row) for row in rows)

        game_payload: dict[str, Any] = {
            "gs_event_id": match.gs_event.event_id,
            "gs_partial_id": event_to_partial.get(match.gs_event.event_id),
            "pinnacle_matchup_id": match.pinnacle_event.matchup_id,
            "teams": [match.gs_event.team1, match.gs_event.team2],
            "start_time": match.gs_event.start_time.isoformat(),
            "gs_line_count": len(gs_lines),
            "main_market_rows": [asdict(row) for row in rows],
        }
        if settings["include_full_gs_lines"]:
            game_payload["gs_lines"] = [asdict(line) for line in gs_lines]

        games.append(game_payload)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gs_line_set": gs.decode_line_set(gs.line_set),
        "gs_game_count": len(gs_events),
        "pinnacle_game_count": len(pinnacle_events),
        "matched_game_count": len(matches),
        "comparison_row_count": len(comparisons),
        "games": games,
        "comparisons": comparisons,
    }
