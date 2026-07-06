"""Extract team/game-level markets from GS coefficient payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from gs_client import decimal_to_american
from prop_markets import GS_GAME_MARKET_MAP, GS_MAIN_MARKET_IDS, slugify_market_name


@dataclass
class GSGameMarketLine:
    event_id: str
    period: str
    market_id: str
    market_name: str
    market_type: str
    selection: str
    team_side: str | None
    line: float | None
    side: str | None
    decimal_odds: float
    american_odds: int


def _resolve_game_market_type(market_id: str, market_name: str) -> str:
    if str(market_id) in GS_MAIN_MARKET_IDS:
        return GS_MAIN_MARKET_IDS[str(market_id)]
    mapped = GS_GAME_MARKET_MAP.get(str(market_id))
    if mapped:
        return mapped
    return f"gs_{slugify_market_name(market_name)}"


def _expand_game_prices(
    market_id: str,
    selection_key: str,
    price: Any,
) -> list[tuple[str, str | None, float | None, str | None, float]]:
    if market_id == "3" and isinstance(price, (int, float)) and price > 1.00002:
        return [(str(selection_key), str(selection_key), None, None, float(price))]

    if market_id == "6" and isinstance(price, list) and len(price) == 2:
        try:
            spread_line = float(selection_key)
        except ValueError:
            return []
        rows: list[tuple[str, str | None, float | None, str | None, float]] = []
        for team_side, decimal_odds in zip(("1", "2"), price):
            if decimal_odds <= 1.00002:
                continue
            rows.append((f"{spread_line}:{team_side}", team_side, spread_line, None, float(decimal_odds)))
        return rows

    if isinstance(price, list) and len(price) == 2:
        try:
            line = float(selection_key)
        except ValueError:
            line = None
        rows = []
        for side, decimal_odds in zip(("over", "under"), price):
            if decimal_odds <= 1.00002:
                continue
            rows.append((f"{selection_key}:{side}", None, line, side, float(decimal_odds)))
        return rows

    if isinstance(price, (int, float)) and price > 1.00002:
        return [(str(selection_key), None, None, None, float(price))]

    return []


def extract_game_markets_for_event(
    event_id: str,
    coefficient_payload: dict[str, Any],
    market_name_lookup: Callable[[str], str],
    periods: list[str] | None = None,
) -> list[GSGameMarketLine]:
    period_data = coefficient_payload.get("c", {})
    selected_periods = periods or list(period_data.keys())
    lines: list[GSGameMarketLine] = []

    for period in selected_periods:
        markets = period_data.get(period, {})
        for market_id, market_data in markets.items():
            if market_data.get("d"):
                continue

            market_name = market_name_lookup(str(market_id))
            market_type = _resolve_game_market_type(str(market_id), market_name)
            outcomes = market_data.get("o", {})

            for selection_key, price in outcomes.items():
                for selection, team_side, line, side, decimal_odds in _expand_game_prices(
                    str(market_id),
                    str(selection_key),
                    price,
                ):
                    lines.append(
                        GSGameMarketLine(
                            event_id=str(event_id),
                            period=str(period),
                            market_id=str(market_id),
                            market_name=market_name,
                            market_type=market_type,
                            selection=selection,
                            team_side=team_side,
                            line=line,
                            side=side,
                            decimal_odds=decimal_odds,
                            american_odds=decimal_to_american(decimal_odds),
                        )
                    )

    return lines
