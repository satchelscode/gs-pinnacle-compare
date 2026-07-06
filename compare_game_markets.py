"""Compare GS team/game markets to reference books."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from compare import normalize_team
from gs_game_markets import GSGameMarketLine
from odds_api_client import ReferencePropLine


@dataclass
class GameMarketComparisonRow:
    game: str
    market_type: str
    market_name: str
    selection: str
    line: float | None
    side: str | None
    gs_odds: int
    fanduel_odds: int | None
    pinnacle_odds: int | None
    edge_vs_best: int | None


GAME_MARKET_REFERENCE_TYPES: dict[str, list[str]] = {
    "team_total_hits_t1": ["team_totals", "alternate_team_totals"],
    "team_total_hits_t2": ["team_totals", "alternate_team_totals"],
    "game_total_home_runs": ["alternate_totals", "totals"],
}


def _lookup_team_total(
    indexed: dict[tuple, ReferencePropLine],
    book: str,
    market_types: list[str],
    team_name: str,
    line: float,
    side: str,
) -> ReferencePropLine | None:
    team_key = normalize_team(team_name)
    for market_type in market_types:
        for delta in (0.0, -0.5, 0.5):
            candidate_line = round(line + delta, 2)
            ref = indexed.get((book, market_type, team_key, candidate_line, side))
            if ref is not None:
                return ref
    return None


def compare_game_markets(
    game_label: str,
    away_team: str,
    home_team: str,
    gs_lines: list[GSGameMarketLine],
    reference_lines: list[ReferencePropLine],
) -> list[GameMarketComparisonRow]:
    indexed: dict[tuple, ReferencePropLine] = {}
    for line in reference_lines:
        if line.prop_type not in {"team_totals", "alternate_team_totals", "totals", "alternate_totals"}:
            continue
        team_key = normalize_team(line.player_name or line.selection or "")
        if line.line is None:
            continue
        key = (line.book, line.prop_type, team_key, round(line.line, 2), line.side)
        indexed[key] = line

    rows: list[GameMarketComparisonRow] = []
    for gs_line in gs_lines:
        if gs_line.side is None or gs_line.line is None:
            continue
        ref_types = GAME_MARKET_REFERENCE_TYPES.get(gs_line.market_type)
        if not ref_types:
            continue

        team_name = away_team if gs_line.market_type == "team_total_hits_t1" else home_team
        fanduel = _lookup_team_total(indexed, "fanduel", ref_types, team_name, gs_line.line, gs_line.side)
        pinnacle = _lookup_team_total(indexed, "pinnacle", ref_types, team_name, gs_line.line, gs_line.side)
        if not fanduel and not pinnacle:
            continue

        fd_odds = fanduel.american_odds if fanduel else None
        pin_odds = pinnacle.american_odds if pinnacle else None
        best_odds = None
        for odds in (fd_odds, pin_odds):
            if odds is None:
                continue
            if best_odds is None or odds > best_odds:
                best_odds = odds

        rows.append(
            GameMarketComparisonRow(
                game=game_label,
                market_type=gs_line.market_type,
                market_name=gs_line.market_name,
                selection=gs_line.selection,
                line=gs_line.line,
                side=gs_line.side,
                gs_odds=gs_line.american_odds,
                fanduel_odds=fd_odds,
                pinnacle_odds=pin_odds,
                edge_vs_best=(gs_line.american_odds - best_odds) if best_odds is not None else None,
            )
        )

    rows.sort(key=lambda row: abs(row.edge_vs_best or 0), reverse=True)
    return rows


def rows_to_dicts(rows: list[GameMarketComparisonRow]) -> list[dict]:
    return [asdict(row) for row in rows]
