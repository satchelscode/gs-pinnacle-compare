"""Compare GS team/game markets to FanDuel, Pinnacle, and Pinnacle guest API."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from compare import normalize_team
from gs_game_markets import GSGameMarketLine
from odds_api_client import ReferencePropLine
from pinnacle_client import PinnacleLine
from prop_markets import GS_ODDS_API_PERIOD_MARKETS, GS_PINNACLE_PERIOD_MAP


@dataclass
class GameMarketComparisonRow:
    game: str
    period: str
    market_type: str
    market_name: str
    selection: str
    line: float | None
    side: str | None
    gs_odds: int
    fanduel_odds: int | None
    pinnacle_odds: int | None
    diff_vs_fanduel: int | None
    diff_vs_pinnacle: int | None
    best_reference_book: str | None
    best_reference_odds: int | None
    edge_vs_best: int | None


def _odds_api_market_keys(period: str, market_type: str) -> list[str]:
    if period == "m":
        if market_type == "moneyline":
            return ["h2h"]
        if market_type == "spread":
            return ["spreads", "alternate_spreads"]
        if market_type == "total":
            return ["totals", "alternate_totals"]
        if market_type in {"team_total_hits_t1", "team_total_hits_t2"}:
            return ["team_totals", "alternate_team_totals"]
        if market_type == "game_total_home_runs":
            return ["totals", "alternate_totals"]
        return []

    period_markets = GS_ODDS_API_PERIOD_MARKETS.get(period, {})
    mapped = period_markets.get(market_type)
    if mapped:
        return [mapped]
    return []


def _team_for_side(
    team_side: str | None,
    away_team: str,
    home_team: str,
    team1_is_home: bool,
) -> str | None:
    if team_side == "1":
        return home_team if team1_is_home else away_team
    if team_side == "2":
        return away_team if team1_is_home else home_team
    return None


def _signed_spread_for_side(spread_line: float, team_side: str | None, team1_is_home: bool) -> float | None:
    if team_side not in {"1", "2"}:
        return spread_line
    is_team1 = team_side == "1"
    is_home = is_team1 == team1_is_home
    return spread_line if is_home else -spread_line


def _index_reference_lines(
    reference_lines: list[ReferencePropLine],
    away_team: str,
    home_team: str,
) -> dict[tuple, ReferencePropLine]:
    indexed: dict[tuple, ReferencePropLine] = {}
    for line in reference_lines:
        if line.prop_type in {"team_totals", "alternate_team_totals"}:
            team_key = normalize_team(line.player_name or line.selection or "")
            if line.line is None:
                continue
            key = (line.book, line.prop_type, team_key, round(line.line, 2), line.side)
            indexed[key] = line
            continue

        if line.prop_type.startswith("totals"):
            if line.line is None:
                continue
            key = (line.book, line.prop_type, round(line.line, 2), line.side)
            indexed[key] = line
            continue

        if line.prop_type.startswith("spreads"):
            team_key = normalize_team(line.selection or line.player_name or "")
            if line.line is None:
                continue
            key = (line.book, line.prop_type, team_key, round(line.line, 2))
            indexed[key] = line
            continue

        if line.prop_type.startswith("h2h"):
            team_key = normalize_team(line.selection or line.player_name or "")
            key = (line.book, line.prop_type, team_key)
            indexed[key] = line
    return indexed


def _index_pinnacle_lines(pinnacle_lines: list[PinnacleLine]) -> dict[tuple, PinnacleLine]:
    indexed: dict[tuple, PinnacleLine] = {}
    for line in pinnacle_lines:
        if line.market_type == "moneyline":
            key = ("pinnacle", line.period, "moneyline", line.designation)
        elif line.market_type == "spread":
            if line.line is None:
                continue
            key = ("pinnacle", line.period, "spread", line.designation, round(line.line, 2))
        elif line.market_type == "total":
            if line.line is None:
                continue
            key = ("pinnacle", line.period, "total", round(line.line, 2), line.designation)
        else:
            continue
        indexed[key] = line
    return indexed


def _lookup_odds_api(
    indexed: dict[tuple, ReferencePropLine],
    book: str,
    market_keys: list[str],
    gs_line: GSGameMarketLine,
    away_team: str,
    home_team: str,
    team1_is_home: bool,
) -> ReferencePropLine | None:
    if gs_line.market_type == "moneyline":
        team = _team_for_side(gs_line.team_side, away_team, home_team, team1_is_home)
        if not team:
            return None
        team_key = normalize_team(team)
        for market_key in market_keys:
            ref = indexed.get((book, market_key, team_key))
            if ref:
                return ref
        return None

    if gs_line.market_type == "spread":
        team = _team_for_side(gs_line.team_side, away_team, home_team, team1_is_home)
        if not team or gs_line.line is None:
            return None
        signed = _signed_spread_for_side(gs_line.line, gs_line.team_side, team1_is_home)
        if signed is None:
            return None
        team_key = normalize_team(team)
        for market_key in market_keys:
            for delta in (0.0, -0.5, 0.5):
                ref = indexed.get((book, market_key, team_key, round(signed + delta, 2)))
                if ref:
                    return ref
        return None

    if gs_line.market_type in {"total", "game_total_home_runs"} or gs_line.side in {"over", "under"}:
        if gs_line.line is None or not gs_line.side:
            return None
        for market_key in market_keys:
            for delta in (0.0, -0.5, 0.5):
                ref = indexed.get((book, market_key, round(gs_line.line + delta, 2), gs_line.side))
                if ref:
                    return ref
        return None

    if gs_line.market_type in {"team_total_hits_t1", "team_total_hits_t2"}:
        if gs_line.line is None or not gs_line.side:
            return None
        team = away_team if gs_line.market_type == "team_total_hits_t1" else home_team
        team_key = normalize_team(team)
        for market_key in market_keys:
            for delta in (0.0, -0.5, 0.5):
                ref = indexed.get((book, market_key, team_key, round(gs_line.line + delta, 2), gs_line.side))
                if ref:
                    return ref
        return None

    return None


def _lookup_pinnacle(
    indexed: dict[tuple, PinnacleLine],
    gs_line: GSGameMarketLine,
    team1_is_home: bool,
) -> PinnacleLine | None:
    period = GS_PINNACLE_PERIOD_MAP.get(gs_line.period, 0)

    if gs_line.market_type == "moneyline":
        if gs_line.team_side == "1":
            designation = "home" if team1_is_home else "away"
        elif gs_line.team_side == "2":
            designation = "away" if team1_is_home else "home"
        else:
            return None
        return indexed.get(("pinnacle", period, "moneyline", designation))

    if gs_line.market_type == "spread":
        if gs_line.team_side == "1":
            designation = "home" if team1_is_home else "away"
        elif gs_line.team_side == "2":
            designation = "away" if team1_is_home else "home"
        else:
            return None
        signed = _signed_spread_for_side(gs_line.line or 0.0, gs_line.team_side, team1_is_home)
        if signed is None:
            return None
        for delta in (0.0, -0.5, 0.5):
            ref = indexed.get(("pinnacle", period, "spread", designation, round(signed + delta, 2)))
            if ref:
                return ref
        return None

    if gs_line.market_type == "total" and gs_line.line is not None and gs_line.side:
        for delta in (0.0, -0.5, 0.5):
            ref = indexed.get(("pinnacle", period, "total", round(gs_line.line + delta, 2), gs_line.side))
            if ref:
                return ref
    return None


def compare_game_markets(
    game_label: str,
    away_team: str,
    home_team: str,
    team1_is_home: bool,
    gs_lines: list[GSGameMarketLine],
    reference_lines: list[ReferencePropLine],
    pinnacle_lines: list[PinnacleLine] | None = None,
) -> list[GameMarketComparisonRow]:
    odds_index = _index_reference_lines(reference_lines, away_team, home_team)
    pin_index = _index_pinnacle_lines(pinnacle_lines or [])
    rows: list[GameMarketComparisonRow] = []

    comparable_types = {
        "moneyline",
        "spread",
        "total",
        "team_total_hits_t1",
        "team_total_hits_t2",
        "game_total_home_runs",
    }

    for gs_line in gs_lines:
        if gs_line.market_type not in comparable_types:
            continue

        market_keys = _odds_api_market_keys(gs_line.period, gs_line.market_type)
        fanduel = (
            _lookup_odds_api(odds_index, "fanduel", market_keys, gs_line, away_team, home_team, team1_is_home)
            if market_keys
            else None
        )
        odds_api_pinnacle = (
            _lookup_odds_api(odds_index, "pinnacle", market_keys, gs_line, away_team, home_team, team1_is_home)
            if market_keys
            else None
        )
        guest_pinnacle = _lookup_pinnacle(pin_index, gs_line, team1_is_home)

        fd_odds = fanduel.american_odds if fanduel else None
        pin_odds = None
        pin_source = None
        if odds_api_pinnacle:
            pin_odds = odds_api_pinnacle.american_odds
            pin_source = "pinnacle"
        elif guest_pinnacle:
            pin_odds = guest_pinnacle.american_odds
            pin_source = "pinnacle_guest"

        if fd_odds is None and pin_odds is None:
            continue

        best_book = None
        best_odds = None
        for book, odds in (("fanduel", fd_odds), (pin_source, pin_odds)):
            if odds is None:
                continue
            if best_odds is None or odds > best_odds:
                best_odds = odds
                best_book = book

        rows.append(
            GameMarketComparisonRow(
                game=game_label,
                period=gs_line.period,
                market_type=gs_line.market_type,
                market_name=gs_line.market_name,
                selection=gs_line.selection,
                line=gs_line.line,
                side=gs_line.side or gs_line.team_side,
                gs_odds=gs_line.american_odds,
                fanduel_odds=fd_odds,
                pinnacle_odds=pin_odds,
                diff_vs_fanduel=(gs_line.american_odds - fd_odds) if fd_odds is not None else None,
                diff_vs_pinnacle=(gs_line.american_odds - pin_odds) if pin_odds is not None else None,
                best_reference_book=best_book,
                best_reference_odds=best_odds,
                edge_vs_best=(gs_line.american_odds - best_odds) if best_odds is not None else None,
            )
        )

    rows.sort(key=lambda row: (abs(row.edge_vs_best or 0), row.market_type), reverse=True)
    return rows


def rows_to_dicts(rows: list[GameMarketComparisonRow]) -> list[dict]:
    return [asdict(row) for row in rows]
