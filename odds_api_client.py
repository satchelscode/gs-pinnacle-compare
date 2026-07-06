"""The Odds API client for FanDuel and Pinnacle player props."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from compare import normalize_team
from prop_markets import ODDS_API_GAME_MARKETS, ODDS_API_PLAYER_MARKETS, REFERENCE_BOOKS


@dataclass
class ReferencePropLine:
    book: str
    event_id: str
    home_team: str
    away_team: str
    prop_type: str
    player_name: str
    line: float | None
    side: str
    american_odds: int
    selection: str | None = None


class OddsApiClient:
    def __init__(self, api_key: str, base_url: str = "https://api.the-odds-api.com/v4"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def _get(self, path: str, **params: Any) -> Any:
        response = self.session.get(
            f"{self.base_url}{path}",
            params={"apiKey": self.api_key, **params},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def list_mlb_events(self) -> list[dict[str, Any]]:
        return self._get("/sports/baseball_mlb/events")

    def fetch_event_props(self, event_id: str) -> list[ReferencePropLine]:
        player_lines = self._fetch_event_markets(event_id, ODDS_API_PLAYER_MARKETS)
        game_lines = self._fetch_event_markets(event_id, ODDS_API_GAME_MARKETS)
        return player_lines + game_lines

    def _fetch_event_markets(self, event_id: str, markets: list[str]) -> list[ReferencePropLine]:
        if not markets:
            return []
        payload = self._get(
            f"/sports/baseball_mlb/events/{event_id}/odds",
            regions="us",
            oddsFormat="american",
            markets=",".join(markets),
            bookmakers=",".join(REFERENCE_BOOKS),
        )
        return self._parse_event_props(payload)

    def _parse_event_props(self, payload: dict[str, Any]) -> list[ReferencePropLine]:
        home = payload.get("home_team", "")
        away = payload.get("away_team", "")
        event_id = str(payload.get("id", ""))
        lines: list[ReferencePropLine] = []

        for bookmaker in payload.get("bookmakers", []):
            book = str(bookmaker.get("key", "")).lower()
            if book not in REFERENCE_BOOKS:
                continue
            for market in bookmaker.get("markets", []):
                prop_type = str(market.get("key", ""))
                for outcome in market.get("outcomes", []):
                    label = str(outcome.get("name", ""))
                    side = label.lower()
                    if side not in {"over", "under", "yes", "no"} and prop_type.startswith(("h2h", "spreads")):
                        lines.append(
                            ReferencePropLine(
                                book=book,
                                event_id=event_id,
                                home_team=home,
                                away_team=away,
                                prop_type=prop_type,
                                player_name="",
                                line=outcome.get("point"),
                                side=side,
                                american_odds=int(outcome["price"]),
                                selection=label,
                            )
                        )
                        continue
                    if side not in {"over", "under", "yes", "no"}:
                        continue
                    point = outcome.get("point")
                    if point is None and side in {"yes", "no"}:
                        point = 0.5
                    if point is None and prop_type not in {"pitcher_record_a_win", "batter_first_home_run"}:
                        continue
                    if point is None:
                        point = 0.5
                    player_name = outcome.get("description") or ""
                    if not player_name and prop_type in {"team_totals", "alternate_team_totals"}:
                        player_name = label
                    lines.append(
                        ReferencePropLine(
                            book=book,
                            event_id=event_id,
                            home_team=home,
                            away_team=away,
                            prop_type=prop_type,
                            player_name=str(player_name),
                            line=float(point),
                            side="over" if side in {"over", "yes"} else "under",
                            american_odds=int(outcome["price"]),
                            selection=label if not player_name else None,
                        )
                    )
        return lines

    def build_event_index(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        indexed = []
        for event in events:
            commence = event.get("commence_time")
            if not commence:
                continue
            indexed.append(
                {
                    "id": str(event["id"]),
                    "home_team": event.get("home_team", ""),
                    "away_team": event.get("away_team", ""),
                    "start_time": datetime.fromisoformat(commence.replace("Z", "+00:00")),
                    "teams": {
                        normalize_team(event.get("home_team", "")),
                        normalize_team(event.get("away_team", "")),
                    },
                }
            )
        return indexed
