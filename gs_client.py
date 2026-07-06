"""GS Betting (sportswidgets) API client."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

MLB_LEAGUE_ID = "8"
BASEBALL_SPORT_ID = "1"


@dataclass
class GSEvent:
    event_id: str
    partial_id: str | None
    team1: str
    team2: str
    start_time: datetime
    league_id: str
    pitchers: tuple[str | None, str | None]


@dataclass
class GSLine:
    event_id: str
    period: str
    market_id: str
    market_name: str
    selection: str
    line: float | None
    decimal_odds: float
    american_odds: int
    source: str = "gs"


class GSClient:
    def __init__(self, base_url: str = "https://ppm.sportswidgets.pro", line_set: str = "U0VWU1NWUkJSMFU9", session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self.line_set = line_set
        self.session = session or requests.Session()
        self._metadata: dict[str, Any] | None = None
        self._partial_map: dict[str, str] = {}
        self._event_map: dict[str, str] = {}

    @staticmethod
    def decode_line_set(line_set: str) -> str:
        decoded = base64.b64decode(line_set).decode()
        if decoded.endswith("="):
            return base64.b64decode(decoded).decode()
        return decoded

    def _get(self, path: str, **kwargs) -> Any:
        response = self.session.get(f"{self.base_url}{path}", timeout=60, **kwargs)
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        response = self.session.post(
            f"{self.base_url}{path}",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def load_metadata(self) -> dict[str, Any]:
        if self._metadata is None:
            self._metadata = self._get(
                "/betLobbyV2/eventsMetadata/",
                params={"leagues": "true", "allSports": "true", "countries": "true", "wagertypes": "true"},
            )
        return self._metadata

    def market_name(self, market_id: str) -> str:
        meta = self.load_metadata()
        entry = meta.get("wagertypes", {}).get(str(market_id), {})
        return entry.get("n", f"market_{market_id}")

    def fetch_updates(self) -> dict[str, Any]:
        updates = self._get(
            "/betLobbyV2/getUpdates/",
            params={"store": self.line_set, "includeNotStarted": "true"},
        )
        coefficients: dict[str, Any] = {}
        partial_map: dict[str, str] = {}
        event_map: dict[str, str] = {}

        for chunk in updates:
            if "c" in chunk:
                coefficients.update(chunk["c"])
            if "db" in chunk:
                for partial_id, event_id in chunk["db"].items():
                    partial_map[str(partial_id)] = str(event_id)
                    event_map[str(event_id)] = str(partial_id)

        self._partial_map = partial_map
        self._event_map = event_map
        return {"coefficients": coefficients, "partial_map": partial_map, "raw_updates": updates}

    def list_mlb_events(self, hours_ahead: int = 48) -> list[GSEvent]:
        schedule = self._get("/live/allEvents")
        now = datetime.now(timezone.utc).timestamp()
        cutoff = now + hours_ahead * 3600
        events: list[GSEvent] = []

        def walk(node: Any, path: tuple[str, ...] = ()) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, path + (str(key),))
                return
            if not isinstance(node, list) or len(node) < 3 or not isinstance(node[0], list):
                return

            league_id = path[-2] if len(path) >= 2 else ""
            event_id = path[-1]
            if league_id != MLB_LEAGUE_ID:
                return

            start_ts = node[2]
            if not isinstance(start_ts, (int, float)) or start_ts < now or start_ts > cutoff:
                return

            pitcher1 = node[3].get("name") if len(node) > 3 and isinstance(node[3], dict) else None
            pitcher2 = node[4].get("name") if len(node) > 4 and isinstance(node[4], dict) else None
            events.append(
                GSEvent(
                    event_id=str(event_id),
                    partial_id=self._event_map.get(str(event_id)),
                    team1=str(node[0][0]),
                    team2=str(node[1][0]),
                    start_time=datetime.fromtimestamp(start_ts, timezone.utc),
                    league_id=league_id,
                    pitchers=(pitcher1, pitcher2),
                )
            )

        walk(schedule.get("s", {}))
        events.sort(key=lambda event: event.start_time)
        return events

    def event_by_partial_id(self, partial_id: str, updates: dict[str, Any] | None = None) -> str | None:
        if updates is None:
            updates = self.fetch_updates()
        return updates["partial_map"].get(str(partial_id))

    def extract_lines(self, event_id: str, updates: dict[str, Any] | None = None) -> list[GSLine]:
        if updates is None:
            updates = self.fetch_updates()

        payload = updates["coefficients"].get(str(event_id))
        if not payload or "c" not in payload:
            return []

        lines: list[GSLine] = []
        for period, markets in payload["c"].items():
            for market_id, market_data in markets.items():
                market_name = self.market_name(str(market_id))
                outcomes = market_data.get("o", {})
                for selection, price in outcomes.items():
                    for side_label, decimal_odds in _expand_price(str(market_id), selection, price):
                        lines.append(
                            GSLine(
                                event_id=str(event_id),
                                period=str(period),
                                market_id=str(market_id),
                                market_name=market_name,
                                selection=side_label,
                                line=_parse_line(str(market_id), selection, price),
                                decimal_odds=decimal_odds,
                                american_odds=decimal_to_american(decimal_odds),
                            )
                        )
        return lines


def _parse_line(market_id: str, selection: str, price: Any) -> float | None:
    if market_id == "6":
        try:
            return float(selection)
        except ValueError:
            return None
    if isinstance(price, list):
        try:
            return float(selection)
        except ValueError:
            return None
    return None


def _expand_price(market_id: str, selection: str, price: Any) -> list[tuple[str, float]]:
    if market_id == "6" and isinstance(price, list) and len(price) == 2:
        return [(f"{selection}:1", float(price[0])), (f"{selection}:2", float(price[1]))]
    if isinstance(price, (int, float)):
        return [(str(selection), float(price))]
    if isinstance(price, list):
        labels = ("over", "under") if len(price) == 2 else tuple(str(index + 1) for index in range(len(price)))
        return [(f"{selection}:{label}", float(value)) for label, value in zip(labels, price)]
    return []


def decimal_to_american(decimal_odds: float) -> int:
    if decimal_odds <= 1:
        return 0
    if decimal_odds >= 2:
        return int(round((decimal_odds - 1) * 100))
    return int(round(-100 / (decimal_odds - 1)))


def american_to_decimal(american_odds: int) -> float:
    if american_odds == 0:
        return 1.0
    if american_odds > 0:
        return 1 + american_odds / 100
    return 1 + 100 / abs(american_odds)


def implied_probability(decimal_odds: float) -> float:
    if decimal_odds <= 1:
        return 1.0
    return 1 / decimal_odds
