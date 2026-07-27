from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

from playwright.sync_api import sync_playwright

from snapims.config import DataPaths
from snapims.demo import create_demo_batch
from snapims.observability import emit_event

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "release-evidence" / "v0.10.0" / "phase-2-firefox"


def wait_for_health(url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout is not None else ""
            raise RuntimeError(
                "SnapIMS browser-audit server exited before health passed:\n" + output
            )
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError("SnapIMS browser-audit server did not become healthy")


def start_server(
    data_dir: Path, environment: dict[str, str], url: str
) -> subprocess.Popen[str]:
    process = subprocess.Popen(
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
            url.rsplit(":", 1)[-1],
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    wait_for_health(url, process)
    return process


def stop_server(process: subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def main() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="snapims-v010-phase2-firefox-"))
    source = create_demo_batch(workspace / "camera", item_count=3)
    data_dir = workspace / "data"
    secret = "phase2-firefox-secret"
    environment = os.environ.copy()
    environment.update(
        {
            "SNAPIMS_SKIP_DOTENV": "1",
            "SNAPIMS_PROJECT_PATH": str(ROOT),
            "SNAPIMS_DATA_DIR": str(data_dir),
            "SNAPIMS_AUTH_SECRET": "",
            "SNAPIMS_ADMIN_PASSWORD_HASH": "",
            "OPENAI_API_KEY": secret,
            "SHOPIFY_ADMIN_ACCESS_TOKEN": "",
            "CLOUDFLARE_TUNNEL_CONFIG": str(workspace / "missing-cloudflared.yml"),
        }
    )
    subprocess.run(
        [sys.executable, "-m", "snapims.cli", "import", str(source)],
        cwd=ROOT,
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    )
    paths = DataPaths.from_root(data_dir).ensure()
    url = f"http://127.0.0.1:{free_port()}"
    server = start_server(data_dir, environment, url)
    results: dict[str, object] = {
        "browser": "Playwright Firefox",
        "url": url,
        "workspace": str(workspace),
        "checks": {},
        "console_errors": [],
        "page_errors": [],
    }
    try:
        with sync_playwright() as playwright:
            browser = playwright.firefox.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1600, "height": 1100},
                accept_downloads=True,
            )
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

            page.goto(f"{url}/diagnostics#live-activity", wait_until="networkidle")
            results["checks"]["live_activity_visible"] = page.get_by_text(
                "Durable operational events"
            ).is_visible()
            results["checks"]["queue_metrics_visible"] = (
                page.get_by_text("Recognition queue").is_visible()
                and page.get_by_text("Catalog queue").is_visible()
            )
            page.screenshot(path=EVIDENCE / "01-live-activity.png", full_page=True)

            event_id = emit_event(
                paths.db_file,
                component="recognition",
                event_type="recognition.browser_poll_fixture",
                operation_id="OP-FIREFOX-PHASE2",
                status="COMPLETE",
                safe_summary=f"fixture token={secret}",
                detail={"authorization": f"Bearer {secret}", "visible": "polling"},
                known_secrets=[secret],
                paths=paths,
            )
            page.get_by_text("recognition.browser_poll_fixture").wait_for(timeout=8_000)
            results["checks"]["bounded_polling_receives_event"] = (
                page.locator("[data-live-activity] tr").count() <= 100
            )
            row = page.locator(f'[data-event-id="{event_id}"]')
            results["checks"]["safe_detail_redacted"] = (
                secret not in row.text_content()
                and "[REDACTED]" in row.text_content()
            )
            page.evaluate(
                """() => {
                    window.__snapimsCopiedEvent = "";
                    navigator.clipboard.writeText = async (value) => {
                        window.__snapimsCopiedEvent = value;
                    };
                }"""
            )
            row.get_by_role("button", name="Copy event").click()
            results["checks"]["copy_event"] = "recognition.browser_poll_fixture" in (
                page.evaluate("window.__snapimsCopiedEvent")
            )

            page.goto(
                f"{url}/diagnostics?activity_source=recognition#live-activity",
                wait_until="networkidle",
            )
            sources = page.locator("[data-live-activity] tr:not([data-empty-activity]) td:nth-child(2)")
            results["checks"]["source_filter"] = (
                sources.count() > 0
                and all("recognition" in sources.nth(index).text_content() for index in range(sources.count()))
            )
            page.screenshot(path=EVIDENCE / "02-filtered-activity.png", full_page=True)

            with page.expect_download() as download_info:
                page.get_by_role("button", name="Export support bundle").click()
            download = download_info.value
            bundle = EVIDENCE / "support-bundle.zip"
            download.save_as(bundle)
            with zipfile.ZipFile(bundle) as archive:
                bundle_content = b"\n".join(
                    archive.read(name) for name in archive.namelist()
                )
            results["checks"]["support_bundle_redacted"] = (
                secret.encode() not in bundle_content
                and b"schema_manifest" in bundle_content
                and b"recognition.browser_poll_fixture" in bundle_content
            )

            stop_server(server)
            server = start_server(data_dir, environment, url)
            page.goto(
                f"{url}/diagnostics?activity_operation=OP-FIREFOX-PHASE2#live-activity",
                wait_until="networkidle",
            )
            results["checks"]["durable_after_restart"] = page.get_by_text(
                "recognition.browser_poll_fixture"
            ).is_visible()
            page.screenshot(path=EVIDENCE / "03-after-restart.png", full_page=True)
            browser.close()
    finally:
        if server.poll() is None:
            stop_server(server)

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
