"""Extract player props from GS coefficient payloads."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable

from gs_client import decimal_to_american
from prop_markets import GS_PROP_MARKET_MAP


@dataclass
class GSPropLine:
    event_id: str
    period: str
    market_id: str
    market_name: str
    prop_type: str
    player_id: str
    player_name: str
    line: float
    side: str
    decimal_odds: float
    american_odds: int


def normalize_player_name(name: str) -> str:
    cleaned = unicodedata.normalize("NFKD", name)
    cleaned = "".join(ch for ch in cleaned if not unicodedata.combining(ch))
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    cleaned = re.sub(r"\s*-\s*[lr]\s*$", "", cleaned, flags=re.I)
    cleaned = re.sub(r"[^a-z0-9 ]+", "", cleaned)
    return cleaned


def extract_props_for_event(
    event_id: str,
    coefficient_payload: dict[str, Any],
    market_name_lookup: Callable[[str], str],
    period: str = "m",
) -> list[GSPropLine]:
    markets = coefficient_payload.get("c", {}).get(period, {})
    props: list[GSPropLine] = []

    for market_id, market_data in markets.items():
        prop_type = GS_PROP_MARKET_MAP.get(str(market_id))
        if not prop_type:
            continue

        names = market_data.get("d", {})
        thresholds = market_data.get("t", {})
        outcomes = market_data.get("o", {})
        market_name = market_name_lookup(str(market_id))

        for selection_id, prices in outcomes.items():
            if not isinstance(prices, list) or len(prices) != 2:
                continue

            player_name = names.get(str(selection_id))
            if not player_name:
                continue

            line = float(thresholds.get(str(selection_id), 1))
            for side, decimal_odds in zip(("over", "under"), prices):
                if decimal_odds <= 1.00002:
                    continue
                props.append(
                    GSPropLine(
                        event_id=str(event_id),
                        period=period,
                        market_id=str(market_id),
                        market_name=market_name,
                        prop_type=prop_type,
                        player_id=str(selection_id),
                        player_name=str(player_name).strip(),
                        line=line,
                        side=side,
                        decimal_odds=float(decimal_odds),
                        american_odds=decimal_to_american(float(decimal_odds)),
                    )
                )

    return props
