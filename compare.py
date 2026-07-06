"""Match GS events to Pinnacle and compare main markets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable

from gs_client import GSLine, GSEvent, implied_probability
from pinnacle_client import PinnacleEvent, PinnacleLine
from prop_markets import GS_PINNACLE_PERIOD_MAP


TEAM_ALIASES = {
    "athletics": "oakland athletics",
    "a's": "oakland athletics",
}


@dataclass
class MatchedEvent:
    gs_event: GSEvent
    pinnacle_event: PinnacleEvent
    team1_is_home: bool


@dataclass
class ComparisonRow:
    game: str
    market: str
    gs_selection: str
    gs_odds: int
    pinnacle_selection: str
    pinnacle_odds: int
    diff_american: int
    diff_implied_pct: float


def normalize_team(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9 ]+", "", name.lower()).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return TEAM_ALIASES.get(cleaned, cleaned)


def match_events(gs_events: Iterable[GSEvent], pinnacle_events: Iterable[PinnacleEvent], max_delta_minutes: int = 20) -> list[MatchedEvent]:
    matches: list[MatchedEvent] = []
    pinnacle_list = list(pinnacle_events)

    for gs_event in gs_events:
        gs_teams = {normalize_team(gs_event.team1), normalize_team(gs_event.team2)}
        best: tuple[timedelta, PinnacleEvent, bool] | None = None

        for pinnacle_event in pinnacle_list:
            home = normalize_team(pinnacle_event.home_team)
            away = normalize_team(pinnacle_event.away_team)
            if {home, away} != gs_teams:
                continue

            delta = abs(gs_event.start_time - pinnacle_event.start_time)
            if delta > timedelta(minutes=max_delta_minutes):
                continue

            team1_is_home = normalize_team(gs_event.team1) == home
            if best is None or delta < best[0]:
                best = (delta, pinnacle_event, team1_is_home)

        if best is not None:
            _, pinnacle_event, team1_is_home = best
            matches.append(MatchedEvent(gs_event=gs_event, pinnacle_event=pinnacle_event, team1_is_home=team1_is_home))

    return matches


def _pick_main_total(gs_lines: list[GSLine]) -> GSLine | None:
    overs = [line for line in gs_lines if line.market_id == "5" and line.selection.endswith(":over")]
    if not overs:
        return None

    best_pair = None
    for over_line in overs:
        total_line = over_line.selection.split(":", 1)[0]
        try:
            total_value = float(total_line)
        except ValueError:
            continue
        under_line = next((line for line in gs_lines if line.selection == f"{total_value}:under"), None)
        if not under_line:
            continue
        spread = abs(over_line.decimal_odds - under_line.decimal_odds)
        if best_pair is None or spread < best_pair[0]:
            best_pair = (spread, over_line)

    return best_pair[1] if best_pair else None


def compare_main_markets(
    match: MatchedEvent,
    gs_lines: list[GSLine],
    pinnacle_lines: list[PinnacleLine],
    gs_period: str = "m",
) -> list[ComparisonRow]:
    pinnacle_period = GS_PINNACLE_PERIOD_MAP.get(gs_period, 0)
    period_lines = [line for line in gs_lines if line.period == gs_period]
    if not period_lines:
        return []

    rows: list[ComparisonRow] = []
    game_label = f"{match.gs_event.team1} @ {match.gs_event.team2}"
    period_label = "" if gs_period == "m" else f" [{gs_period}]"

    gs_moneyline = {line.selection: line for line in period_lines if line.market_id == "3"}
    for gs_side, label in [("1", match.gs_event.team1), ("2", match.gs_event.team2)]:
        gs_line = gs_moneyline.get(gs_side)
        if not gs_line:
            continue
        pin_designation = "home" if (gs_side == "1") == match.team1_is_home else "away"
        pin_line = next(
            (
                line
                for line in pinnacle_lines
                if line.market_type == "moneyline"
                and line.period == pinnacle_period
                and line.designation == pin_designation
                and not line.is_alternate
            ),
            None,
        )
        if not pin_line:
            continue
        rows.append(_build_row(game_label, f"Moneyline{period_label}", gs_line, label, pin_line, pin_line.designation))

    spread_pairs: dict[float, dict[str, GSLine]] = {}
    for line in period_lines:
        if line.market_id != "6" or ":" not in line.selection:
            continue
        spread_key, side = line.selection.split(":", 1)
        if side not in {"1", "2"}:
            continue
        try:
            spread_val = float(spread_key)
        except ValueError:
            continue
        spread_pairs.setdefault(spread_val, {})[side] = line

    best_spread = None
    for spread_val, sides in spread_pairs.items():
        if "1" not in sides or "2" not in sides:
            continue
        spread = abs(sides["1"].decimal_odds - sides["2"].decimal_odds)
        if best_spread is None or spread < best_spread[0]:
            best_spread = (spread, spread_val, sides)

    if best_spread:
        _, spread_val, sides = best_spread
        for gs_side, label in [("1", match.gs_event.team1), ("2", match.gs_event.team2)]:
            gs_line = sides[gs_side]
            signed_line = spread_val if gs_side == "1" else -spread_val
            pin_designation = "home" if ((gs_side == "1") == match.team1_is_home) else "away"
            pin_line = next(
                (
                    line
                    for line in pinnacle_lines
                    if line.market_type == "spread"
                    and line.period == pinnacle_period
                    and not line.is_alternate
                    and line.line == signed_line
                    and line.designation == pin_designation
                ),
                None,
            )
            if pin_line:
                rows.append(_build_row(game_label, f"Spread {signed_line:+.1f}{period_label}", gs_line, label, pin_line, f"{pin_line.designation} {signed_line:+.1f}"))

    over_line = _pick_main_total(period_lines)
    if over_line:
        total_line = float(over_line.selection.split(":")[0])
        under_line = next((line for line in period_lines if line.selection == f"{total_line}:under"), None)
        for gs_line, label, designation in [
            (over_line, f"Over {total_line}", "over"),
            (under_line, f"Under {total_line}", "under"),
        ]:
            if not gs_line:
                continue
            pin_line = next(
                (
                    line
                    for line in pinnacle_lines
                    if line.market_type == "total"
                    and line.period == pinnacle_period
                    and not line.is_alternate
                    and line.line == total_line
                    and line.designation == designation
                ),
                None,
            )
            if pin_line:
                rows.append(_build_row(game_label, f"Total {total_line}{period_label}", gs_line, label, pin_line, label))

    return rows


def compare_all_main_markets(
    match: MatchedEvent,
    gs_lines: list[GSLine],
    pinnacle_lines: list[PinnacleLine],
) -> list[ComparisonRow]:
    rows: list[ComparisonRow] = []
    periods = sorted({line.period for line in gs_lines if line.period in GS_PINNACLE_PERIOD_MAP})
    if "m" not in periods:
        periods = ["m", *periods]
    for period in periods:
        rows.extend(compare_main_markets(match, gs_lines, pinnacle_lines, gs_period=period))
    return rows


def _build_row(game: str, market: str, gs_line: GSLine, gs_label: str, pin_line: PinnacleLine, pin_label: str) -> ComparisonRow:
    gs_prob = implied_probability(gs_line.decimal_odds)
    pin_prob = implied_probability(pin_line.decimal_odds)
    return ComparisonRow(
        game=game,
        market=market,
        gs_selection=gs_label,
        gs_odds=gs_line.american_odds,
        pinnacle_selection=pin_label,
        pinnacle_odds=pin_line.american_odds,
        diff_american=gs_line.american_odds - pin_line.american_odds,
        diff_implied_pct=round((gs_prob - pin_prob) * 100, 2),
    )
