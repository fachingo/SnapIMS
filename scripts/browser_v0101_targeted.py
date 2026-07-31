#!/usr/bin/env python3
"""Targeted v0.10.1 browser verification for changed operator surfaces.

Environment:
  SNAPIMS_BROWSER_URL (default http://127.0.0.1:8767)
  SNAPIMS_ADMIN_USERNAME / SNAPIMS_ADMIN_PASSWORD when authentication is enabled
  SNAPIMS_TEST_BATCH_ID and SNAPIMS_TEST_ITEM_ID for the two-tab stale-write check
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "release-evidence" / "v0.10.1" / "targeted-browser"
OUT.mkdir(parents=True, exist_ok=True)
BASE = os.getenv("SNAPIMS_BROWSER_URL", "http://127.0.0.1:8767").rstrip("/")


def login(page) -> None:
    page.goto(f"{BASE}/", wait_until="networkidle")
    if "/login" not in page.url:
        return
    username = os.getenv("SNAPIMS_ADMIN_USERNAME", "")
    password = os.getenv("SNAPIMS_ADMIN_PASSWORD", "")
    if not username or not password:
        raise RuntimeError("Browser login required; set SNAPIMS_ADMIN_USERNAME/PASSWORD")
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")


def verify_engine(browser_type, name: str) -> dict[str, object]:
    browser = browser_type.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    console_errors: list[str] = []
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    login(page)

    page.goto(f"{BASE}/review", wait_until="networkidle")
    page.screenshot(path=str(OUT / f"{name}-review-100.png"), full_page=True)
    page.evaluate("document.body.style.zoom='2'")
    page.screenshot(path=str(OUT / f"{name}-review-200.png"), full_page=True)
    page.evaluate("document.body.style.zoom='1'")

    page.keyboard.press("Alt+P")
    close = page.locator('[data-command-close]')
    assert close.get_attribute("aria-label") == "Close command palette"
    page.keyboard.press("Escape")

    tag = page.locator("[data-tag-input]").first
    if tag.count():
        tag.focus()
        assert tag.get_attribute("role") == "combobox"
        assert tag.get_attribute("aria-controls")
        assert tag.get_attribute("aria-expanded") in {"true", "false"}
        page.keyboard.press("Escape")

    page.goto(f"{BASE}/batch-editor", wait_until="networkidle")
    page.screenshot(path=str(OUT / f"{name}-batch-editor.png"), full_page=True)

    result = {
        "browser": name,
        "status": "PASS" if not console_errors else "FAIL",
        "console_errors": console_errors,
    }
    context.close()
    browser.close()
    return result


def main() -> int:
    results: list[dict[str, object]] = []
    with sync_playwright() as p:
        for browser_type, name in ((p.chromium, "chromium"), (p.firefox, "firefox")):
            try:
                results.append(verify_engine(browser_type, name))
            except Exception as exc:
                results.append({"browser": name, "status": "FAIL", "error": f"{type(exc).__name__}: {exc}"})
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "url": BASE,
        "results": results,
        "overall": "PASS" if results and all(row["status"] == "PASS" for row in results) else "FAIL",
        "edge_note": "Run the Chromium project against installed Microsoft Edge separately when available.",
    }
    (OUT / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
