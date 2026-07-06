"""Compare GS player props to FanDuel and Pinnacle."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Iterable

from compare import normalize_team
from gs_props import GSPropLine, normalize_player_name
from odds_api_client import ReferencePropLine


@dataclass
class PropComparisonRow:
    game: str
    prop_type: str
    market_name: str
    player: str
    line: float
    side: str
    gs_odds: int
    fanduel_odds: int | None
    pinnacle_odds: int | None
    diff_vs_fanduel: int | None
    diff_vs_pinnacle: int | None
    best_reference_book: str | None
    best_reference_odds: int | None
    edge_vs_best: int | None


def match_odds_api_event(gs_home: str, gs_away: str, gs_start, odds_events: list[dict]) -> dict | None:
    gs_teams = {normalize_team(gs_home), normalize_team(gs_away)}
    best = None
    for event in odds_events:
        if event["teams"] != gs_teams:
            continue
        delta = abs(gs_start - event["start_time"])
        if delta > timedelta(minutes=30):
            continue
        if best is None or delta < best[0]:
            best = (delta, event)
    return best[1] if best else None


def _index_reference_lines(lines: Iterable[ReferencePropLine]) -> dict[tuple, ReferencePropLine]:
    indexed: dict[tuple, ReferencePropLine] = {}
    for line in lines:
        key = (
            line.book,
            line.prop_type,
            normalize_player_name(line.player_name),
            round(line.line, 2),
            line.side,
        )
        indexed[key] = line
    return indexed


def compare_props(
    game_label: str,
    gs_props: list[GSPropLine],
    reference_lines: list[ReferencePropLine],
    line_tolerance: float = 0.01,
) -> list[PropComparisonRow]:
    indexed = _index_reference_lines(reference_lines)
    rows: list[PropComparisonRow] = []

    for gs_prop in gs_props:
        player_key = normalize_player_name(gs_prop.player_name)
        match_key_base = (gs_prop.prop_type, player_key, round(gs_prop.line, 2), gs_prop.side)

        fanduel = indexed.get(("fanduel", *match_key_base))
        pinnacle = indexed.get(("pinnacle", *match_key_base))

        if not fanduel and not pinnacle:
            # Try adjacent half-lines (GS sometimes stores integer thresholds).
            for delta in (-0.5, 0.5):
                alt_line = round(gs_prop.line + delta, 2)
                alt_base = (gs_prop.prop_type, player_key, alt_line, gs_prop.side)
                fanduel = fanduel or indexed.get(("fanduel", *alt_base))
                pinnacle = pinnacle or indexed.get(("pinnacle", *alt_base))
                if fanduel or pinnacle:
                    break

        if not fanduel and not pinnacle:
            continue

        fd_odds = fanduel.american_odds if fanduel else None
        pin_odds = pinnacle.american_odds if pinnacle else None
        best_book = None
        best_odds = None
        for book, odds in (("fanduel", fd_odds), ("pinnacle", pin_odds)):
            if odds is None:
                continue
            if best_odds is None or odds > best_odds:
                best_odds = odds
                best_book = book

        rows.append(
            PropComparisonRow(
                game=game_label,
                prop_type=gs_prop.prop_type,
                market_name=gs_prop.market_name,
                player=gs_prop.player_name,
                line=gs_prop.line,
                side=gs_prop.side,
                gs_odds=gs_prop.american_odds,
                fanduel_odds=fd_odds,
                pinnacle_odds=pin_odds,
                diff_vs_fanduel=(gs_prop.american_odds - fd_odds) if fd_odds is not None else None,
                diff_vs_pinnacle=(gs_prop.american_odds - pin_odds) if pin_odds is not None else None,
                best_reference_book=best_book,
                best_reference_odds=best_odds,
                edge_vs_best=(gs_prop.american_odds - best_odds) if best_odds is not None else None,
            )
        )

    rows.sort(key=lambda row: (abs(row.edge_vs_best or 0), row.player), reverse=True)
    return rows


def rows_to_dicts(rows: list[PropComparisonRow]) -> list[dict]:
    return [asdict(row) for row in rows]
