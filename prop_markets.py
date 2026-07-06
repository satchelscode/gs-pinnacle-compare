"""Canonical mappings between GS markets and external prop feeds."""

from __future__ import annotations

# GS wager type id -> canonical prop type used for matching.
GS_PROP_MARKET_MAP: dict[str, str] = {
    "1515": "batter_hits",
    "1023": "batter_rbis",
    "2304": "batter_hits_runs_rbis",
    "2657": "batter_strikeouts",
    "2658": "batter_walks",
    "282": "batter_singles",
    "283": "batter_doubles",
    "284": "batter_triples",
    "281": "batter_stolen_bases",
    "286": "pitcher_strikeouts",
    "287": "pitcher_earned_runs",
    "921": "pitcher_record_a_win",
    "948": "pitcher_hits_allowed",
    "2470": "pitcher_walks",
    "1073": "pitcher_outs",
}

# The Odds API markets to request for MLB props.
ODDS_API_PROP_MARKETS: list[str] = sorted(set(GS_PROP_MARKET_MAP.values()))

# Books to compare against GS.
REFERENCE_BOOKS: tuple[str, ...] = ("fanduel", "pinnacle")
