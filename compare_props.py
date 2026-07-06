"""Compare GS player props to FanDuel and Pinnacle."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Iterable

from compare import normalize_team
from gs_props import GSPropLine, normalize_player_name
from odds_api_client import ReferencePropLine
from prop_markets import comparison_prop_types


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


def _reference_player_key(line: ReferencePropLine) -> str:
    if line.player_name:
        return normalize_player_name(line.player_name)
    if line.selection:
        return normalize_team(line.selection)
    return ""


def _index_reference_lines(lines: Iterable[ReferencePropLine]) -> dict[tuple, ReferencePropLine]:
    indexed: dict[tuple, ReferencePropLine] = {}
    for line in lines:
        key = (
            line.book,
            line.prop_type,
            _reference_player_key(line),
            round(line.line, 2) if line.line is not None else None,
            line.side,
        )
        indexed[key] = line
    return indexed


def _gs_prop_key(prop: GSPropLine) -> tuple:
    return (
        prop.prop_type,
        normalize_player_name(prop.player_name),
        round(prop.line, 2),
        prop.side,
    )


def _has_over_under_pair(prop: GSPropLine, all_props: list[GSPropLine]) -> bool:
    opposite_side = "under" if prop.side == "over" else "over"
    for candidate in all_props:
        if (
            candidate.market_id == prop.market_id
            and candidate.player_id == prop.player_id
            and candidate.line == prop.line
            and candidate.side == opposite_side
        ):
            return True
    return False


def _lookup_reference(
    indexed: dict[tuple, ReferencePropLine],
    book: str,
    prop_type: str,
    player_key: str,
    line: float,
    side: str,
) -> ReferencePropLine | None:
    for candidate_type in comparison_prop_types(prop_type):
        for delta in (0.0, -0.5, 0.5, -1.0, 1.0):
            candidate_line = round(line + delta, 2)
            ref = indexed.get((book, candidate_type, player_key, candidate_line, side))
            if ref is not None:
                return ref
    return None


def _reference_odds_for_key(
    indexed: dict[tuple, ReferencePropLine],
    key: tuple,
) -> int | None:
    prop_type, player_key, line, side = key
    for book in ("fanduel", "pinnacle"):
        ref = _lookup_reference(indexed, book, prop_type, player_key, line, side)
        if ref is not None:
            return ref.american_odds
    return None


def deduplicate_gs_props(
    gs_props: list[GSPropLine],
    reference_lines: list[ReferencePropLine] | None = None,
) -> list[GSPropLine]:
    """Collapse duplicate GS rows for the same player/prop/line/side.

    GS often emits multiple selection ids for the same prop (e.g. a main O/U
    market and a longshot yes-style market). Prefer the row closest to a
    reference book when available, otherwise the row with a paired opposite side.
    """
    indexed = _index_reference_lines(reference_lines or [])
    grouped: dict[tuple, list[GSPropLine]] = defaultdict(list)
    for prop in gs_props:
        grouped[_gs_prop_key(prop)].append(prop)

    deduped: list[GSPropLine] = []
    for key, candidates in grouped.items():
        if len(candidates) == 1:
            deduped.append(candidates[0])
            continue

        ref_odds = _reference_odds_for_key(indexed, key)
        if ref_odds is not None:
            deduped.append(min(candidates, key=lambda prop: abs(prop.american_odds - ref_odds)))
            continue

        paired = [prop for prop in candidates if _has_over_under_pair(prop, gs_props)]
        pool = paired or candidates
        deduped.append(
            min(
                pool,
                key=lambda prop: (
                    abs(prop.american_odds + 110) if prop.american_odds < 0 else abs(prop.american_odds - 110),
                    int(prop.player_id),
                ),
            )
        )

    return deduped


def compare_props(
    game_label: str,
    gs_props: list[GSPropLine],
    reference_lines: list[ReferencePropLine],
    line_tolerance: float = 0.01,
) -> list[PropComparisonRow]:
    indexed = _index_reference_lines(reference_lines)
    rows: list[PropComparisonRow] = []

    for gs_prop in deduplicate_gs_props(gs_props, reference_lines):
        player_key = normalize_player_name(gs_prop.player_name)
        fanduel = _lookup_reference(indexed, "fanduel", gs_prop.prop_type, player_key, gs_prop.line, gs_prop.side)
        pinnacle = _lookup_reference(indexed, "pinnacle", gs_prop.prop_type, player_key, gs_prop.line, gs_prop.side)

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
