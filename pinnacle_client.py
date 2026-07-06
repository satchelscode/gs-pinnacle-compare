"""Pinnacle guest API client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from gs_client import american_to_decimal, decimal_to_american


@dataclass
class PinnacleEvent:
    matchup_id: int
    home_team: str
    away_team: str
    start_time: datetime


@dataclass
class PinnacleLine:
    matchup_id: int
    market_type: str
    period: int
    designation: str
    line: float | None
    american_odds: int
    decimal_odds: float
    is_alternate: bool
    key: str


class PinnacleClient:
    def __init__(self, base_url: str = "https://guest.api.arcadia.pinnacle.com/0.1", mlb_league_id: int = 246, session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self.mlb_league_id = mlb_league_id
        self.session = session or requests.Session()
        self.session.headers.update({"accept": "application/json"})

    def _get(self, path: str, **kwargs) -> Any:
        response = self.session.get(f"{self.base_url}{path}", timeout=60, **kwargs)
        response.raise_for_status()
        return response.json()

    def list_mlb_matchups(self) -> list[PinnacleEvent]:
        matchups = self._get(f"/leagues/{self.mlb_league_id}/matchups", params={"brandId": 0})
        events: list[PinnacleEvent] = []

        for matchup in matchups:
            if matchup.get("parentId") is not None:
                continue
            participants = matchup.get("participants", [])
            if len(participants) != 2:
                continue
            home = next((p for p in participants if p.get("alignment") == "home"), None)
            away = next((p for p in participants if p.get("alignment") == "away"), None)
            if not home or not away:
                continue
            events.append(
                PinnacleEvent(
                    matchup_id=int(matchup["id"]),
                    home_team=str(home["name"]),
                    away_team=str(away["name"]),
                    start_time=datetime.fromisoformat(matchup["startTime"].replace("Z", "+00:00")),
                )
            )
        events.sort(key=lambda event: event.start_time)
        return events

    def fetch_markets(self, matchup_id: int) -> list[PinnacleLine]:
        markets = self._get(f"/matchups/{matchup_id}/markets/related/straight")
        lines: list[PinnacleLine] = []

        for market in markets:
            market_type = str(market.get("type", ""))
            period = int(market.get("period", 0))
            is_alternate = bool(market.get("isAlternate", False))
            for price in market.get("prices", []):
                designation = str(price.get("designation", ""))
                american_odds = int(price["price"])
                lines.append(
                    PinnacleLine(
                        matchup_id=matchup_id,
                        market_type=market_type,
                        period=period,
                        designation=designation,
                        line=price.get("points"),
                        american_odds=american_odds,
                        decimal_odds=american_to_decimal(american_odds),
                        is_alternate=is_alternate,
                        key=str(market.get("key", "")),
                    )
                )
        return lines
