from __future__ import annotations

import csv
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.request import urlopen

from playwright.sync_api import Browser, Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from snapims.demo import create_demo_batch  # noqa: E402

AUDIT = ROOT / "operator-audit-assets" / "v0.5.1-browser"
SHOTS = AUDIT / "screenshots"
WORK = AUDIT / "workspace"
CAMERAS = AUDIT / "camera-rolls"
DOWNLOADS = AUDIT / "downloads"
LOGS = AUDIT / "logs"
POLICY = Path("/etc/chromium/policies/managed/000_policy_merge.json")
PORT = 8891
BASE = f"http://127.0.0.1:{PORT}"


def wait_health(timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{BASE}/health", timeout=1) as response:  # noqa: S310 - fixed loopback audit URL
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.15)
    raise RuntimeError("SnapIMS server did not become healthy")


class Server:
    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.log_file = None

    def start(self) -> None:
        if self.process and self.process.poll() is None:
            return
        LOGS.mkdir(parents=True, exist_ok=True)
        self.log_file = (LOGS / f"uvicorn-{int(time.time() * 1000)}.log").open("w", encoding="utf-8")
        env = os.environ.copy()
        env.update({
            "SNAPIMS_DATA_DIR": str(WORK),
            "SNAPIMS_MOCK_DELAY": "0.12",
            "PYTHONUNBUFFERED": "1",
        })
        self.process = subprocess.Popen(
            [os.environ.get("PYTHON", "python"), "-m", "uvicorn", "snapims.web.app:app", "--host", "127.0.0.1", "--port", str(PORT)],
            cwd=ROOT,
            env=env,
            stdout=self.log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_health()

    def stop(self, *, abrupt: bool = False) -> None:
        if not self.process:
            return
        if self.process.poll() is None:
            if abrupt:
                self.process.kill()
            else:
                self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log_file:
            self.log_file.close()
        self.process = None
        self.log_file = None


@contextmanager
def chromium_policy_allows_loopback() -> Iterator[None]:
    """Temporarily remove the container's global Chromium URL block and restore it exactly."""
    original: bytes | None = POLICY.read_bytes() if POLICY.exists() else None
    try:
        if original is not None:
            payload = json.loads(original.decode("utf-8"))
            payload.pop("URLBlocklist", None)
            payload.pop("URLAllowlist", None)
            POLICY.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        yield
    finally:
        if original is None:
            POLICY.unlink(missing_ok=True)
        else:
            POLICY.write_bytes(original)


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(SHOTS / name), full_page=True)


def set_manual_folder(page: Page, path: Path) -> None:
    page.goto(f"{BASE}/import", wait_until="domcontentloaded")
    details = page.locator("details.advanced")
    if not details.evaluate("element => element.open"):
        details.locator("summary").click()
    details.locator("input[name='path']").fill(str(path))
    if not details.locator("input[name='save_as_incoming']").is_checked():
        details.locator("input[name='save_as_incoming']").check()
    details.locator("button", has_text="Use this folder").click()
    page.wait_for_load_state("domcontentloaded")


def import_batch(page: Page, path: Path, name: str, prefix: str) -> str:
    print(f"IMPORT {name}", flush=True)
    set_manual_folder(page, path)
    page.locator("input[name='batch_name']").fill(name)
    page.locator("button", has_text="Preview batch").click()
    page.wait_for_load_state("domcontentloaded")
    page.get_by_text("PREVIEW · NOT IMPORTED YET", exact=True).wait_for()
    shot(page, f"{prefix}-preview-not-imported.png")
    page.locator("button", has_text="Preserve and import batch").click()
    page.wait_for_load_state("domcontentloaded")
    page.get_by_text("IMPORTED BATCH", exact=True).wait_for()
    batch_id = page.locator("section.success-panel code").inner_text().strip()
    shot(page, f"{prefix}-imported-durable-id.png")
    page.locator("a", has_text="Continue to Review").click()
    page.wait_for_load_state("domcontentloaded")
    return batch_id


def identify(page: Page, provider: str = "mock", *, wait_complete: bool = True) -> None:
    status = page.locator("#recognition-status strong")
    page.locator("#recognition-status select[name='provider']").select_option(provider)
    page.locator("#recognition-status button").click()
    page.wait_for_load_state("domcontentloaded")
    if wait_complete:
        status.wait_for(state="visible")
        page.wait_for_function(
            "() => { const e=document.querySelector('#recognition-status strong'); return e && (e.textContent.includes('Recognition complete') || e.textContent.includes('Review complete')); }",
            timeout=60000,
        )
        page.wait_for_load_state("domcontentloaded")


def queue(page: Page, value: str) -> None:
    page.locator("select[name='queue']").select_option(value)
    page.wait_for_load_state("domcontentloaded")


def current_item_id(page: Page) -> str:
    return page.locator("section.physical-header code").inner_text().strip()


def main() -> None:
    for path in (AUDIT,):
        shutil.rmtree(path, ignore_errors=True)
    for path in (SHOTS, CAMERAS, DOWNLOADS, LOGS):
        path.mkdir(parents=True, exist_ok=True)

    fixtures = {
        "main": create_demo_batch(CAMERAS / "main-20", item_count=20),
        "later": create_demo_batch(CAMERAS / "later-2", item_count=2, shelf="A2"),
        "failure": create_demo_batch(CAMERAS / "failure-1", item_count=1, shelf="A4"),
        "interrupt": create_demo_batch(CAMERAS / "interrupt-40", item_count=40, photos_per_item=1, shelf="A3"),
    }

    server = Server()
    server.start()
    approval_metrics: list[dict[str, float | int | str]] = []
    click_total = 0
    one_click = 0
    batches: dict[str, str] = {}
    interruption: dict[str, int | str] = {}

    try:
        with chromium_policy_allows_loopback(), sync_playwright() as playwright:
            browser: Browser = playwright.chromium.launch(
                executable_path=os.environ.get("SNAPIMS_CHROMIUM", "/usr/lib/chromium/chromium"),
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
            page = context.new_page()
            page.set_default_timeout(20000)
            page.set_default_navigation_timeout(40000)

            print("BROWSER START", flush=True)
            # Native HTTP navigation proof and first-run workflow.
            page.goto(BASE, wait_until="domcontentloaded")
            assert page.title() == "Home · SnapIMS"
            shot(page, "00-home.png")
            page.locator("a", has_text="Import new batch").click()
            page.wait_for_load_state("domcontentloaded")
            shot(page, "01-first-run-import.png")

            batches["main"] = import_batch(page, fixtures["main"], "V051-PILOT", "02")
            page.get_by_text("20 items ready to identify", exact=True).wait_for()
            shot(page, "04-review-before-identification.png")
            identify(page, "mock")
            page.get_by_text("Recognition complete · 20 items ready to review", exact=True).wait_for()
            shot(page, "05-recognition-complete.png")
            page.get_by_text("Batch item 1 of 20", exact=True).wait_for()

            print("MAIN RECOGNIZED", flush=True)
            # 17 one-click approvals + Price, Discount, and combined quick-edit cases.
            for number in range(1, 21):
                page.get_by_text(re.compile(rf"Batch item {number} of 20"), exact=False).wait_for()
                item_clicks = 1
                if number == 18:
                    page.locator("form.quick-approve input[name='price']").click()
                    page.locator("form.quick-approve input[name='price']").fill("18.49")
                    item_clicks += 1
                    shot(page, "06-price-quick-edit.png")
                elif number == 19:
                    page.locator("form.quick-approve input[name='discount']").click()
                    page.locator("form.quick-approve input[name='discount']").fill("10")
                    item_clicks += 1
                    shot(page, "07-discount-quick-edit.png")
                elif number == 20:
                    page.locator("form.quick-approve input[name='price']").click()
                    page.locator("form.quick-approve input[name='price']").fill("21.99")
                    page.locator("form.quick-approve input[name='discount']").click()
                    page.locator("form.quick-approve input[name='discount']").fill("15")
                    item_clicks += 2
                    shot(page, "08-price-discount-quick-edit.png")
                before_id = current_item_id(page)
                started = time.perf_counter()
                page.locator("form.quick-approve button.approve").click()
                page.wait_for_load_state("domcontentloaded")
                if number < 20:
                    page.wait_for_function(
                        "old => document.querySelector('section.physical-header code')?.textContent.trim() !== old",
                        arg=before_id,
                        timeout=15000,
                    )
                else:
                    page.get_by_text("Review complete.", exact=True).wait_for()
                elapsed = time.perf_counter() - started
                click_total += item_clicks
                one_click += int(item_clicks == 1)
                approval_metrics.append({"physical_item": number, "clicks": item_clicks, "approval_to_next_render_seconds": round(elapsed, 4)})
                if number == 1:
                    shot(page, "09-next-item-opened.png")
            shot(page, "10-review-complete.png")

            print("MAIN APPROVED", flush=True)
            # Completed-item correction, validation, cancel.
            page.locator("a", has_text="Edit item").click()
            page.wait_for_load_state("domcontentloaded")
            corrected_item_id = current_item_id(page)
            title = page.locator("form.editor-grid input[name='title']")
            title.fill("VHS 001 — Corrected in v0.5.1")
            page.locator("form.editor-grid input[name='price']").fill("18.49")
            page.locator("form.editor-grid button", has_text="Save changes").click()
            page.wait_for_load_state("domcontentloaded")
            assert current_item_id(page) == corrected_item_id
            page.get_by_text("Changes saved to the same immutable Item ID.", exact=True).wait_for()
            shot(page, "11-completed-item-corrected.png")

            page.locator("a", has_text="Edit item").click()
            page.wait_for_load_state("domcontentloaded")
            page.locator("form.editor-grid input[name='title']").fill("")
            page.locator("form.editor-grid input[name='price']").fill("0")
            page.locator("form.editor-grid button", has_text="Save changes").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("Changes not saved", exact=True).wait_for()
            shot(page, "12-invalid-edit-blocked.png")
            page.locator("a", has_text="Cancel changes").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("VHS 001 — Corrected in v0.5.1", exact=True).wait_for()
            shot(page, "13-invalid-edit-cancelled.png")

            # Actual process restart against same workspace.
            current_url = page.url
            server.stop()
            server.start()
            page.goto(current_url, wait_until="domcontentloaded")
            page.get_by_text("VHS 001 — Corrected in v0.5.1", exact=True).wait_for()
            assert current_item_id(page) == corrected_item_id
            shot(page, "14-restart-durable-correction.png")

            # Publish simulation and visible browser CSV download.
            page.goto(f"{BASE}/publish?batch_id={batches['main']}", wait_until="domcontentloaded")
            page.locator("a", has_text="Simulate selected drafts").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("Simulation results", exact=True).wait_for()
            shot(page, "15-publish-simulation.png")
            with page.expect_download() as download_info:
                page.locator("a", has_text="Download inventory CSV").click()
            download = download_info.value
            csv_path = DOWNLOADS / download.suggested_filename
            download.save_as(csv_path)

            print("PUBLISH CSV DONE", flush=True)
            # Later/postpone, return, complete.
            batches["later"] = import_batch(page, fixtures["later"], "LATER", "16")
            identify(page, "mock")
            first_later = current_item_id(page)
            page.locator("form[action='/review/later'] button", has_text="Later").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("Tape postponed and remains unfinished.", exact=True).wait_for()
            assert current_item_id(page) != first_later
            shot(page, "18-later-preserves-unfinished.png")
            page.locator("form.quick-approve button.approve").click()
            page.wait_for_load_state("domcontentloaded")
            assert current_item_id(page) == first_later
            page.locator("form.quick-approve button.approve").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("Review complete.", exact=True).wait_for()

            # Missing folder recovery through UI only.
            missing = CAMERAS / "missing-folder"
            set_manual_folder(page, missing)
            page.get_by_text("Folder not available. Select a valid folder under Advanced.", exact=True).wait_for()
            assert page.locator("button", has_text="Preview batch").is_disabled()
            shot(page, "19-missing-folder-recovery.png")

            print("MISSING FOLDER DONE", flush=True)
            # Recognition failure and visible retry/recovery.
            batches["failure"] = import_batch(page, fixtures["failure"], "FAILURE", "20")
            identify(page, "gemini")
            page.get_by_text("Recognition complete · 0 ready · 1 failed", exact=True).wait_for()
            page.locator("a", has_text="Review failure").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("Recognition failed", exact=True).wait_for()
            shot(page, "22-recognition-failure.png")
            page.locator("form[action='/review/retry'] select[name='provider']").select_option("mock")
            page.locator("form[action='/review/retry'] button", has_text="Retry").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("Recognition recovered. Review the suggestion.", exact=True).wait_for()
            shot(page, "23-recognition-failure-recovered.png")

            print("FAILURE RECOVERY DONE", flush=True)
            # Genuine interruption: browser starts real worker, then server process is killed.
            batches["interrupt"] = import_batch(page, fixtures["interrupt"], "INTERRUPT", "24")
            identify(page, "mock", wait_complete=False)
            page.wait_for_function(
                "() => { const t=document.querySelector('#recognition-status strong')?.textContent || ''; const m=t.match(/Identifying · (\\d+) of 40/); return m && Number(m[1]) >= 5; }",
                timeout=30000,
            )
            active_text = page.locator("#recognition-status strong").inner_text()
            active_completed = int(re.search(r"Identifying · (\d+) of 40", active_text).group(1))
            shot(page, "26-recognition-running-before-kill.png")
            interrupt_url = page.url
            server.stop(abrupt=True)
            server.start()
            page.goto(interrupt_url, wait_until="domcontentloaded")
            paused_text = page.locator("#recognition-status strong").inner_text()
            paused_match = re.search(r"Identification paused · (\d+) of 40 complete · (\d+) remaining", paused_text)
            assert paused_match, paused_text
            paused_completed = int(paused_match.group(1))
            remaining = int(paused_match.group(2))
            assert paused_completed >= active_completed
            assert paused_completed + remaining == 40
            assert page.locator("#recognition-status button", has_text="Continue identification").count() == 1
            interruption.update({"active_completed": active_completed, "paused_completed": paused_completed, "remaining": remaining})
            shot(page, "27-recognition-paused-after-restart.png")
            page.locator("#recognition-status button", has_text="Continue identification").click()
            page.wait_for_load_state("domcontentloaded")
            resumed = False
            for _ in range(120):
                text = page.locator("#recognition-status strong").inner_text()
                if "Recognition complete · 40 items ready to review" in text:
                    resumed = True
                    break
                page.wait_for_timeout(500)
                page.reload(wait_until="domcontentloaded")
            assert resumed, page.locator("#recognition-status strong").inner_text()
            shot(page, "28-recognition-resumed-complete.png")

            print("INTERRUPTION DONE", flush=True)
            # Settings and diagnostics are visibly reachable.
            page.goto(f"{BASE}/settings", wait_until="domcontentloaded")
            shot(page, "29-settings.png")
            page.goto(f"{BASE}/diagnostics", wait_until="domcontentloaded")
            page.get_by_text("System integrity", exact=True).wait_for()
            shot(page, "30-diagnostics.png")
            browser.close()
    finally:
        server.stop()

    # Post-operator reconciliation: database and downloaded CSV, clearly outside operator portion.
    db_file = WORK / "database" / "inventory.sqlite3"
    with sqlite3.connect(db_file) as connection:
        connection.row_factory = sqlite3.Row
        main_items = connection.execute("SELECT item_id,title,review_status FROM items WHERE batch_id=? ORDER BY sequence", (batches["main"],)).fetchall()
        duplicate_attempts = connection.execute(
            "SELECT COUNT(*) FROM (SELECT item_id,COUNT(*) c FROM recognition_results WHERE item_id IN (SELECT item_id FROM items WHERE batch_id=?) GROUP BY item_id HAVING c>1)",
            (batches["interrupt"],),
        ).fetchone()[0]
        interrupt_items = connection.execute("SELECT COUNT(*) FROM items WHERE batch_id=?", (batches["interrupt"],)).fetchone()[0]
        interrupt_results = connection.execute("SELECT COUNT(*) FROM recognition_results WHERE item_id IN (SELECT item_id FROM items WHERE batch_id=?)", (batches["interrupt"],)).fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign = len(connection.execute("PRAGMA foreign_key_check").fetchall())

    csv_files = list(DOWNLOADS.glob("*.csv"))
    if len(csv_files) != 1:
        raise AssertionError(f"Expected one downloaded CSV, found {csv_files}")
    with csv_files[0].open(newline="", encoding="utf-8-sig") as handle:
        csv_rows = list(csv.DictReader(handle))
    assert len(main_items) == 20 and len(csv_rows) == 20
    assert all(row["review_status"] == "DONE" for row in main_items)
    assert interrupt_items == 40 and interrupt_results == 40 and duplicate_attempts == 0
    assert integrity == "ok" and foreign == 0

    average = sum(float(row["approval_to_next_render_seconds"]) for row in approval_metrics) / len(approval_metrics)
    results = {
        "version": "0.5.1",
        "transport": "Chromium navigated to a separately running uvicorn HTTP server",
        "server_url_category": "local loopback HTTP; no TestClient or page.set_content",
        "viewport": "1440x1000",
        "correctly_recognized_tapes": 20,
        "total_counted_clicks": click_total,
        "average_clicks_per_tape": round(click_total / 20, 2),
        "one_click_tapes": one_click,
        "one_click_percent": round(one_click / 20 * 100, 1),
        "average_application_approval_to_next_render_seconds": round(average, 3),
        "real_operator_time_per_tape": "Unmeasured; remains a live-pilot measurement.",
        "genuine_interruption": interruption,
        "post_audit_reconciliation": {
            "main_items": len(main_items),
            "downloaded_csv_rows": len(csv_rows),
            "interrupt_items": interrupt_items,
            "interrupt_results": interrupt_results,
            "duplicate_recognition_attempt_items": duplicate_attempts,
            "sqlite_integrity": integrity,
            "foreign_key_violations": foreign,
        },
        "batches": batches,
        "approval_items": approval_metrics,
    }
    (AUDIT / "browser-metrics.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    (AUDIT / "native-browser-results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
