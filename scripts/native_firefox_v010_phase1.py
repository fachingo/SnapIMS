from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

from snapims.demo import create_demo_batch

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "release-evidence" / "v0.10.0" / "phase-1-firefox"


def wait_for_health(url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("SnapIMS browser-audit server exited before health passed")
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError("SnapIMS browser-audit server did not become healthy")


def main() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="snapims-v010-firefox-"))
    source = create_demo_batch(workspace / "camera", item_count=3)
    data_dir = workspace / "data"
    env = os.environ.copy()
    env.update(
        {
            "SNAPIMS_SKIP_DOTENV": "1",
            "SNAPIMS_PROJECT_PATH": str(ROOT),
            "SNAPIMS_DATA_DIR": str(data_dir),
            "SNAPIMS_AUTH_SECRET": "",
            "SNAPIMS_ADMIN_PASSWORD_HASH": "",
            "OPENAI_API_KEY": "",
            "SHOPIFY_ADMIN_ACCESS_TOKEN": "",
            "CLOUDFLARE_TUNNEL_CONFIG": str(workspace / "missing-cloudflared.yml"),
        }
    )
    subprocess.run(
        [sys.executable, "-m", "snapims.cli", "import", str(source)],
        cwd=ROOT,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    url = "http://127.0.0.1:8891"
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "snapims.cli",
            "--data-dir",
            str(data_dir),
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            "8891",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    results: dict[str, object] = {
        "browser": "Playwright Firefox",
        "url": url,
        "workspace": str(workspace),
        "checks": {},
        "console_errors": [],
        "page_errors": [],
    }
    try:
        wait_for_health(url, server)
        with sync_playwright() as playwright:
            browser = playwright.firefox.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            page.on(
                "console",
                lambda message: (
                    results["console_errors"].append(message.text)
                    if message.type == "error"
                    else None
                ),
            )
            page.on("pageerror", lambda error: results["page_errors"].append(str(error)))

            page.goto(f"{url}/batch-editor", wait_until="networkidle")
            page.screenshot(path=EVIDENCE / "01-batch-editor.png", full_page=True)

            page.keyboard.press("Alt+P")
            page.locator("#command-palette").wait_for(state="visible")
            results["checks"]["alt_p_palette"] = True
            page.keyboard.press("Escape")

            title = page.locator('#batch-grid [data-field="title"]').first
            title.focus()
            page.keyboard.press("Alt+1")
            results["checks"]["alt_1_ignored_while_typing"] = (
                not page.locator("#bulk-dialog").is_visible()
            )

            page.locator(".row-select").first.check()
            page.locator("body").click(position={"x": 20, "y": 20})
            page.keyboard.press("Alt+1")
            page.locator("#bulk-dialog").wait_for(state="visible")
            results["checks"]["alt_1_opens_first_visible_action"] = (
                page.locator("#bulk-title").text_content() == "Bulk Price"
            )
            page.locator('#bulk-dialog button[value="cancel"]').last.click()

            picker = page.locator("[data-editor-tags]").first
            tag_input = picker.locator("[data-tag-input]")
            tag_input.fill("Toonie")
            results["checks"]["tag_suggestions_open"] = (
                not picker.locator("[data-tag-suggestions]").is_hidden()
            )
            page.keyboard.press("Escape")
            results["checks"]["escape_closes_suggestions_first"] = (
                picker.locator("[data-tag-suggestions]").is_hidden()
                and page.url.startswith(f"{url}/batch-editor")
            )
            tag_input.fill("")
            tag_input.fill("Toonie")
            page.keyboard.press("Enter")
            page.locator("#editor-save-state").filter(has_text="Saved").wait_for()
            page.wait_for_timeout(600)
            results["checks"]["tag_enter_accepts_approved_id"] = (
                picker.locator(".tag-pill", has_text="Toonie Tapes").count() == 1
            )
            page.screenshot(path=EVIDENCE / "02-controlled-tag.png", full_page=True)
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=8)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)

    checks = results["checks"]
    results["passed"] = (
        all(checks.values())
        and not results["console_errors"]
        and not results["page_errors"]
    )
    (EVIDENCE / "results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not results["passed"]:
        raise SystemExit(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
