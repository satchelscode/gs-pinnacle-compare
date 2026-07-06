"""Extract player props from GS coefficient payloads."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable

from gs_client import decimal_to_american
from prop_markets import resolve_prop_type


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
    cleaned = re.sub(r"\s+\d+$", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9 ]+", "", cleaned)
    return cleaned


def _parse_player_name(raw_name: str) -> tuple[str, float | None]:
    name = str(raw_name).strip()
    exact_match = re.match(r"^(?P<name>.+?)\s+(?P<count>\d+)$", name)
    if exact_match:
        return exact_match.group("name").strip(), float(exact_match.group("count"))
    return name, None


def _is_player_prop_market(market_data: dict[str, Any]) -> bool:
    return bool(market_data.get("d")) and bool(market_data.get("t")) and bool(market_data.get("o"))


def extract_props_for_event(
    event_id: str,
    coefficient_payload: dict[str, Any],
    market_name_lookup: Callable[[str], str],
    periods: list[str] | None = None,
) -> list[GSPropLine]:
    period_data = coefficient_payload.get("c", {})
    selected_periods = periods or list(period_data.keys())
    props: list[GSPropLine] = []

    for period in selected_periods:
        markets = period_data.get(period, {})
        for market_id, market_data in markets.items():
            if not _is_player_prop_market(market_data):
                continue

            market_name = market_name_lookup(str(market_id))
            prop_type = resolve_prop_type(str(market_id), market_name)
            names = market_data.get("d", {})
            thresholds = market_data.get("t", {})
            outcomes = market_data.get("o", {})

            for selection_id, prices in outcomes.items():
                if not isinstance(prices, list) or len(prices) != 2:
                    continue

                raw_player_name = names.get(str(selection_id))
                if not raw_player_name:
                    continue

                player_name, exact_count = _parse_player_name(str(raw_player_name))
                threshold = thresholds.get(str(selection_id))
                if threshold is not None:
                    line = float(threshold)
                elif exact_count is not None:
                    line = exact_count
                else:
                    line = 1.0

                for side, decimal_odds in zip(("over", "under"), prices):
                    if decimal_odds <= 1.00002:
                        continue
                    props.append(
                        GSPropLine(
                            event_id=str(event_id),
                            period=str(period),
                            market_id=str(market_id),
                            market_name=market_name,
                            prop_type=prop_type,
                            player_id=str(selection_id),
                            player_name=player_name,
                            line=line,
                            side=side,
                            decimal_odds=float(decimal_odds),
                            american_odds=decimal_to_american(float(decimal_odds)),
                        )
                    )

    return props
