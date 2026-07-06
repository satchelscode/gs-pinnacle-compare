#!/usr/bin/env python3
"""Render background worker: poll GS vs Pinnacle and emit results."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

import requests

from run_compare import load_settings, run_comparison

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("gs-pinnacle-worker")


def post_webhook(payload: dict[str, Any]) -> None:
    webhook_url = os.getenv("WEBHOOK_URL")
    if not webhook_url:
        return

    response = requests.post(
        webhook_url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=60,
    )
    response.raise_for_status()
    logger.info("Posted results to webhook (%s)", response.status_code)


def run_once() -> dict[str, Any]:
    settings = load_settings()
    logger.info(
        "Starting comparison | hours=%s partial_id=%s event_id=%s include_full_gs_lines=%s compare_props=%s odds_api=%s",
        settings["hours"],
        settings.get("partial_id"),
        settings.get("event_id"),
        settings["include_full_gs_lines"],
        settings["compare_props"],
        bool(settings.get("the_odds_api_key")),
    )
    payload = run_comparison(settings)
    logger.info(
        "Comparison complete | matched=%s main_rows=%s prop_rows=%s game_market_rows=%s odds_api=%s",
        payload["matched_game_count"],
        payload["comparison_row_count"],
        payload["prop_comparison_row_count"],
        payload["game_market_comparison_row_count"],
        payload["reference_books_configured"],
    )
    if payload["top_prop_edges"]:
        logger.info("Top prop edges:")
        for row in payload["top_prop_edges"][:5]:
            logger.info(
                "%s | %s %s %s %.1f %s | GS %s | FD %s | PIN %s | edge %s",
                row["game"],
                row["player"],
                row["market_name"],
                row["side"],
                row["line"],
                row["prop_type"],
                row["gs_odds"],
                row["fanduel_odds"],
                row["pinnacle_odds"],
                row["edge_vs_best"],
            )
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    post_webhook(payload)
    return payload


def main() -> None:
    run_once_flag = os.getenv("RUN_ONCE", "false").lower() in {"1", "true", "yes"}
    interval = max(60, int(os.getenv("POLL_INTERVAL_SECONDS", "900")))

    if run_once_flag:
        run_once()
        return

    logger.info("Worker started | poll_interval_seconds=%s", interval)
    while True:
        started = time.time()
        try:
            run_once()
        except Exception:
            logger.exception("Comparison run failed")
        elapsed = time.time() - started
        sleep_for = max(5, interval - elapsed)
        logger.info("Sleeping %.0f seconds", sleep_for)
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
