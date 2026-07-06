"""Canonical mappings between GS markets and external prop feeds."""

from __future__ import annotations

import re

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
    # Unnamed in GS metadata but present on MLB events.
    "170": "batter_home_runs",
    "280": "batter_total_bases",
    "285": "batter_runs_scored",
    # Exact-count player markets (GS-specific naming).
    "2840": "batter_exact_hits",
    "2842": "batter_exact_runs",
    "2846": "pitcher_exact_strikeouts",
    "2852": "batter_exact_strikeouts",
    "2853": "batter_exact_walks",
}

# GS game/team market ids -> canonical market type for extraction.
GS_GAME_MARKET_MAP: dict[str, str] = {
    "2232": "team_total_hits_t1",
    "2233": "team_total_hits_t2",
    "884": "game_total_home_runs",
    "882": "game_home_runs_3way",
    "889": "game_home_runs_double_chance",
    "1852": "game_total_hits_runs_errors",
    "423": "first_scoring_team_wins",
    "2811": "runs_on_first_home_run",
}

# GS coefficient period -> Pinnacle period number (when comparable).
GS_PINNACLE_PERIOD_MAP: dict[str, int] = {
    "m": 0,
    "h1": 1,
}

# GS period -> Odds API inning market keys (moneyline / spread / total).
GS_ODDS_API_PERIOD_MARKETS: dict[str, dict[str, str]] = {
    "h1": {
        "moneyline": "h2h_1st_5_innings",
        "spread": "spreads_1st_5_innings",
        "total": "totals_1st_5_innings",
    },
    "s1": {
        "moneyline": "h2h_1st_1_innings",
        "spread": "spreads_1st_1_innings",
        "total": "totals_1st_1_innings",
    },
}

# When comparing GS exact props, also try these Odds API market keys.
PROP_TYPE_COMPARE_ALIASES: dict[str, list[str]] = {
    "batter_exact_hits": ["batter_hits", "batter_hits_alternate"],
    "batter_exact_runs": ["batter_runs_scored", "batter_runs_scored_alternate"],
    "batter_exact_strikeouts": ["batter_strikeouts", "batter_strikeouts_alternate"],
    "batter_exact_walks": ["batter_walks", "batter_walks_alternate"],
    "pitcher_exact_strikeouts": ["pitcher_strikeouts", "pitcher_strikeouts_alternate"],
}

# All MLB player-prop keys supported by The Odds API (plus alternates for line matching).
ODDS_API_PLAYER_MARKETS: list[str] = [
    "batter_home_runs",
    "batter_first_home_run",
    "batter_hits",
    "batter_total_bases",
    "batter_rbis",
    "batter_runs_scored",
    "batter_hits_runs_rbis",
    "batter_singles",
    "batter_doubles",
    "batter_triples",
    "batter_walks",
    "batter_strikeouts",
    "batter_stolen_bases",
    "pitcher_strikeouts",
    "pitcher_record_a_win",
    "pitcher_hits_allowed",
    "pitcher_walks",
    "pitcher_earned_runs",
    "pitcher_outs",
    "batter_home_runs_alternate",
    "batter_hits_alternate",
    "batter_total_bases_alternate",
    "batter_rbis_alternate",
    "batter_runs_scored_alternate",
    "batter_hits_runs_rbis_alternate",
    "batter_singles_alternate",
    "batter_doubles_alternate",
    "batter_triples_alternate",
    "batter_walks_alternate",
    "batter_strikeouts_alternate",
    "batter_stolen_bases_alternate",
    "pitcher_strikeouts_alternate",
    "pitcher_hits_allowed_alternate",
    "pitcher_walks_alternate",
    "pitcher_earned_runs_alternate",
    "pitcher_outs_alternate",
]

ODDS_API_GAME_MARKETS: list[str] = [
    "team_totals",
    "alternate_team_totals",
    "alternate_spreads",
    "alternate_totals",
    "h2h_1st_1_innings",
    "h2h_1st_3_innings",
    "h2h_1st_5_innings",
    "h2h_1st_7_innings",
    "spreads_1st_1_innings",
    "spreads_1st_3_innings",
    "spreads_1st_5_innings",
    "spreads_1st_7_innings",
    "totals_1st_1_innings",
    "totals_1st_3_innings",
    "totals_1st_5_innings",
    "totals_1st_7_innings",
]

ODDS_API_PROP_MARKETS: list[str] = sorted(set(ODDS_API_PLAYER_MARKETS + ODDS_API_GAME_MARKETS))

REFERENCE_BOOKS: tuple[str, ...] = ("fanduel", "pinnacle")

# GS main market ids (moneyline / spread / total).
GS_MAIN_MARKET_IDS: dict[str, str] = {
    "3": "moneyline",
    "6": "spread",
    "5": "total",
}


def slugify_market_name(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return cleaned or "unknown_market"


def resolve_prop_type(market_id: str, market_name: str) -> str:
    mapped = GS_PROP_MARKET_MAP.get(str(market_id))
    if mapped:
        return mapped
    return f"gs_{slugify_market_name(market_name)}"


def comparison_prop_types(prop_type: str) -> list[str]:
    aliases = PROP_TYPE_COMPARE_ALIASES.get(prop_type, [])
    if prop_type.startswith("gs_"):
        return aliases
    return [prop_type, f"{prop_type}_alternate", *aliases]
