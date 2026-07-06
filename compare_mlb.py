#!/usr/bin/env python3
"""Pull GS MLB lines and compare against Pinnacle."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from run_compare import load_settings, run_comparison


def print_table(rows) -> None:
    if not rows:
        print("No comparable main-market rows found.")
        return

    headers = [
        "game",
        "market",
        "gs_selection",
        "gs_odds",
        "pinnacle_selection",
        "pinnacle_odds",
        "diff_american",
        "diff_implied_pct",
    ]
    widths = {header: len(header) for header in headers}
    dict_rows = rows
    for row in dict_rows:
        for header in headers:
            widths[header] = max(widths[header], len(str(row[header])))

    def fmt_row(row: dict) -> str:
        return " | ".join(str(row[header]).ljust(widths[header]) for header in headers)

    print(fmt_row({header: header for header in headers}))
    print("-+-".join("-" * widths[header] for header in headers))
    for row in dict_rows:
        print(fmt_row(row))


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare GS Betting MLB lines to Pinnacle.")
    parser.add_argument("--hours", type=int, default=48, help="Look ahead this many hours for MLB games.")
    parser.add_argument("--event-id", help="Only compare one GS event id.")
    parser.add_argument("--partial-id", help="GS partial/event route id from iframe, e.g. 911.")
    parser.add_argument("--dump-gs", help="Write all GS lines for matched games to this JSON file.")
    parser.add_argument("--csv", help="Write comparison output to CSV.")
    parser.add_argument("--config", default="config.json", help="Optional legacy config file path.")
    args = parser.parse_args()

    settings = load_settings()
    settings["hours"] = args.hours
    settings["partial_id"] = args.partial_id
    settings["event_id"] = args.event_id
    settings["include_full_gs_lines"] = bool(args.dump_gs)

    config_path = Path(args.config)
    if config_path.exists():
        config = json.loads(config_path.read_text())
        gs_cfg = config.get("gs", {})
        pin_cfg = config.get("pinnacle", {})
        settings["gs_base_url"] = gs_cfg.get("base_url", settings["gs_base_url"])
        settings["gs_line_set"] = gs_cfg.get("line_set", settings["gs_line_set"])
        settings["pinnacle_base_url"] = pin_cfg.get("base_url", settings["pinnacle_base_url"])
        settings["pinnacle_mlb_league_id"] = int(pin_cfg.get("mlb_league_id", settings["pinnacle_mlb_league_id"]))

    payload = run_comparison(settings)
    print(f"GS line set: {payload['gs_line_set']}")
    print(f"Found {payload['gs_game_count']} GS MLB games and {payload['pinnacle_game_count']} Pinnacle MLB matchups.")
    print(f"Matched {payload['matched_game_count']} games.")

    all_rows = []
    for game in payload["games"]:
        rows = game["main_market_rows"]
        all_rows.extend(rows)
        print()
        print(
            f"{game['teams'][0]} vs {game['teams'][1]} | "
            f"GS {game['gs_event_id']} (partial {game['gs_partial_id']}) | "
            f"Pinnacle {game['pinnacle_matchup_id']} | "
            f"{game['gs_line_count']} GS lines"
        )
        print_table(rows)

    if args.dump_gs:
        Path(args.dump_gs).write_text(json.dumps(payload["games"], indent=2))
        print(f"\nWrote GS line dump to {args.dump_gs}")

    if args.csv and all_rows:
        with Path(args.csv).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(all_rows[0].keys()))
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"Wrote comparison CSV to {args.csv}")


if __name__ == "__main__":
    main()
