#!/usr/bin/env python3
"""Capture authenticated iframe network traffic for AD1426."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


INTERESTING_PATHS = (
    "/betLobbyV2/getUpdates/",
    "/betLobbyV2/logic/",
    "/betLobbyV2/eventsMetadata/",
    "/betFactoryV2/api/fastLogin.php",
    "/live/allEvents",
)


def is_interesting(url: str) -> bool:
    return any(path in url for path in INTERESTING_PATHS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture GS iframe network responses.")
    parser.add_argument("--url", required=True, help="Full iframe src URL with customerId/hash/tstamp.")
    parser.add_argument("--output", default="output/captured_session.json", help="Where to save captured responses.")
    parser.add_argument("--wait", type=int, default=15, help="Seconds to wait after page load.")
    parser.add_argument("--headless", action="store_true", help="Run browser headless.")
    args = parser.parse_args()

    captured = {
        "iframe_url": args.url,
        "responses": [],
        "cookies": [],
        "local_storage": {},
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=args.headless)
        context = browser.new_context()
        page = context.new_page()

        def handle_response(response):
            if not is_interesting(response.url):
                return
            try:
                body = response.json()
            except Exception:
                body = response.text()
            captured["responses"].append(
                {
                    "url": response.url,
                    "status": response.status,
                    "headers": dict(response.headers),
                    "body": body,
                }
            )

        page.on("response", handle_response)
        page.goto(args.url, wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(args.wait * 1000)

        captured["cookies"] = context.cookies()
        captured["local_storage"] = page.evaluate("() => Object.assign({}, window.localStorage)")
        captured["final_url"] = page.url
        captured["title"] = page.title()

        browser.close()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(captured, indent=2))

    print(f"Captured {len(captured['responses'])} responses to {output_path}")
    hosts = sorted({urlparse(item["url"]).netloc for item in captured["responses"]})
    print(f"Hosts seen: {', '.join(hosts)}")


if __name__ == "__main__":
    main()
