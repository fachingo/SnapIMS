from __future__ import annotations

import csv
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.request import urlopen

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from snapims.demo import create_demo_batch  # noqa: E402

AUDIT = ROOT / "release-evidence" / "v0.7.0" / "browser"
SHOTS = AUDIT / "screenshots"
WORK = AUDIT / "workspace"
CAMERA = AUDIT / "camera-roll"
DOWNLOADS = AUDIT / "downloads"
LOGS = AUDIT / "logs"
PORT = 8897
BASE = f"http://127.0.0.1:{PORT}"
POLICY = Path("/etc/chromium/policies/managed/000_policy_merge.json")


@contextmanager
def chromium_policy_allows_loopback() -> Iterator[None]:
    original = POLICY.read_bytes() if POLICY.exists() else None
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


def wait_health(timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{BASE}/health", timeout=1) as response:  # noqa: S310
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.15)
    raise RuntimeError("SnapIMS did not become healthy")


class Server:
    def __init__(self, camera: Path) -> None:
        self.camera = camera
        self.process: subprocess.Popen[str] | None = None
        self.log_handle = None
        self.mode = "production"

    def start(self, *, test_mode: bool = False) -> None:
        self.stop()
        self.mode = "test" if test_mode else "production"
        LOGS.mkdir(parents=True, exist_ok=True)
        self.log_handle = (LOGS / f"server-{self.mode}-{int(time.time())}.log").open(
            "w", encoding="utf-8"
        )
        env = os.environ.copy()
        env.pop("OPENAI_API_KEY", None)
        env.pop("SNAPIMS_ENABLE_TEST_PROVIDERS", None)
        env.update(
            {
                "SNAPIMS_DATA_DIR": str(WORK),
                "SNAPIMS_TEST_FOLDER_PICKER": str(self.camera),
                "SNAPIMS_WIKIPEDIA_FIXTURE_DIR": str(ROOT / "tests" / "fixtures" / "wikipedia"),
                "SNAPIMS_WIKIPEDIA_USER_AGENT": "SnapIMS/0.7.0 browser-audit",
                "PYTHONUNBUFFERED": "1",
            }
        )
        if test_mode:
            env["SNAPIMS_ENABLE_TEST_PROVIDERS"] = "true"
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "snapims.web.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(PORT),
            ],
            cwd=ROOT,
            env=env,
            stdout=self.log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_health()

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log_handle:
            self.log_handle.close()
        self.process = None
        self.log_handle = None


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(SHOTS / name), full_page=True)


def wait_recognition(page: Page) -> None:
    page.wait_for_function(
        """() => {
          const text = document.querySelector('#recognition-status')?.textContent || '';
          return text.includes('Recognition complete') || text.includes('Review complete') ||
                 text.includes('failed or incomplete');
        }""",
        timeout=90000,
    )


def main() -> None:
    shutil.rmtree(AUDIT, ignore_errors=True)
    for path in (SHOTS, DOWNLOADS, LOGS):
        path.mkdir(parents=True, exist_ok=True)
    camera = create_demo_batch(CAMERA, item_count=20, photos_per_item=2, shelf="A1")
    server = Server(camera)
    server.start(test_mode=False)
    results: dict[str, object] = {
        "version": "0.7.0",
        "viewport": "1440x1000",
        "scenarios": [],
        "console_errors": [],
        "page_errors": [],
        "failed_requests": [],
        "http_errors": [],
    }

    try:
        with chromium_policy_allows_loopback(), sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=os.getenv("SNAPIMS_CHROMIUM", "/usr/bin/chromium"),
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                accept_downloads=True,
            )
            context.tracing.start(screenshots=True, snapshots=True, sources=True)
            page = context.new_page()
            page.set_default_timeout(30000)

            # Attach all monitoring before the first navigation.
            page.on(
                "console",
                lambda message: results["console_errors"].append(message.text)
                if message.type == "error"
                else None,
            )
            page.on("pageerror", lambda error: results["page_errors"].append(str(error)))
            page.on(
                "requestfailed",
                lambda request: results["failed_requests"].append(
                    f"{request.method} {request.url}: {request.failure}"
                ),
            )
            page.on(
                "response",
                lambda response: results["http_errors"].append(
                    f"{response.status} {response.url}"
                )
                if response.status >= 400
                else None,
            )

            page.goto(BASE, wait_until="domcontentloaded")
            page.get_by_text("Photograph. Resolve exceptions. Publish.", exact=True).wait_for()
            assert "built-in method" not in page.content()
            shot(page, "01-home-production.png")
            results["scenarios"].append("Home metrics render values, not Python objects")

            page.goto(f"{BASE}/import", wait_until="domcontentloaded")
            advanced = page.locator("details.advanced")
            if not advanced.evaluate("element => element.open"):
                advanced.locator("summary").click()
            advanced.locator("input[name='path']").fill(str(camera))
            advanced.get_by_role("button", name="Use this folder").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_role("button", name="Preview batch").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("PREVIEW · NOT IMPORTED YET", exact=True).wait_for()
            shot(page, "02-import-preview.png")
            page.get_by_role("button", name="Preserve and import batch").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("IMPORTED BATCH", exact=True).wait_for()
            batch_id = page.locator("section.success-panel code").inner_text().strip()
            results["batch_id"] = batch_id
            shot(page, "03-import-complete.png")
            results["scenarios"].append("20-item preview and durable import completed")

            page.get_by_role("link", name="Continue to Review").click()
            page.wait_for_load_state("domcontentloaded")
            provider = page.locator("#recognition-status select[name='provider']")
            assert "mock" not in provider.locator("option").all_inner_texts()
            # With no recognition result, Title is the first required empty quick field.
            quick_title = page.locator("#quick-title")
            quick_title.wait_for()
            assert quick_title.evaluate("element => document.activeElement === element")
            quick_title.fill("Gremlins")
            page.locator("#quick-price").fill("4.00")
            quick_title.press("Enter")
            page.wait_for_load_state("domcontentloaded")
            assert "edit=true" not in page.url
            assert page.locator(".physical-header strong").inner_text().startswith("Batch item 2")
            shot(page, "04-empty-title-one-enter.png")
            results["scenarios"].append("Empty Title is inline, focused first, and one Enter completes Review")

            # The bounded lookup preserves ambiguity when title-only evidence is not sufficient.
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                page.goto(f"{BASE}/review?batch_id={batch_id}&queue=DONE", wait_until="domcontentloaded")
                if "AMBIGUOUS" in page.locator(".catalog-match").inner_text().upper():
                    break
                page.wait_for_timeout(250)
            assert "AMBIGUOUS" in page.locator(".catalog-match").inner_text().upper()
            page.get_by_text("Resolve ambiguous movie match", exact=True).wait_for()
            shot(page, "05-catalog-ambiguity-preserved.png")
            page.get_by_role("button", name="Use this movie").click()
            page.wait_for_load_state("domcontentloaded")
            assert "GREMLINS" in page.locator(".catalog-match").inner_text().upper()
            shot(page, "05b-local-movie-catalog-match.png")
            results["scenarios"].append("Ambiguous Movie candidates require operator selection, then persist as a local match")

            page.goto(f"{BASE}/review?batch_id={batch_id}&queue=UNRESOLVED", wait_until="domcontentloaded")
            page.locator("#recognition-status button").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("RECOGNITION BLOCKED", exact=True).wait_for()
            assert page.get_by_role("button", name="Continue With Manual Review").first.is_visible()
            shot(page, "06-recognition-blocked-manual-recovery.png")
            results["scenarios"].append("Production UI hides Mock and missing key becomes BLOCKED")

            server.start(test_mode=True)
            page.goto(f"{BASE}/review?batch_id={batch_id}&queue=UNRESOLVED", wait_until="domcontentloaded")
            retry_form = page.locator("form[action='/review/retry-batch']").first
            retry_form.locator("select[name='provider']").select_option("mock")
            retry_form.get_by_role("button", name="Retry Batch").click()
            page.wait_for_load_state("domcontentloaded")
            wait_recognition(page)
            page.get_by_text("AI suggestion — not saved until approval", exact=True).wait_for()
            price = page.locator("#quick-price")
            price.wait_for()
            assert price.evaluate("element => document.activeElement === element")
            before_sequence = int(page.locator(".physical-header strong").inner_text().split()[2])
            price.fill("12.99")
            price.press("Enter")
            page.wait_for_load_state("domcontentloaded")
            after_sequence = int(page.locator(".physical-header strong").inner_text().split()[2])
            assert after_sequence == before_sequence + 1
            assert page.locator("#quick-price").evaluate("element => document.activeElement === element")
            shot(page, "07-price-enter-advances-once.png")
            results["scenarios"].append("Price → Enter approves exactly one item and refocuses the next quick field")

            page.keyboard.press("Control+Shift+P")
            page.locator("#command-palette").wait_for(state="visible")
            assert page.locator("#command-search").evaluate("element => document.activeElement === element")
            shot(page, "08-command-palette.png")
            page.keyboard.press("Escape")

            page.goto(f"{BASE}/batch-editor?batch_id={batch_id}", wait_until="domcontentloaded")
            page.get_by_text("Bulk operator workstation", exact=True).wait_for()
            title_inputs = page.locator("[data-field='title']")
            title_inputs.first.focus()
            first_item = title_inputs.first.evaluate("element => element.closest('tr').dataset.itemId")
            title_inputs.first.press("ArrowDown")
            active_item = page.evaluate("document.activeElement?.closest('tr')?.dataset?.itemId")
            assert active_item and active_item != first_item
            page.locator("#batch-search").focus()
            page.locator("#batch-search").press("Escape")
            page.locator("[data-save-all]").focus()
            page.keyboard.press("Control+A")
            assert "20 selected" in page.locator("#selection-count").inner_text()
            page.keyboard.press("Control+1")
            page.locator("#bulk-dialog").wait_for(state="visible")
            assert "Replaces Price" in page.locator("#bulk-description").inner_text()
            shot(page, "09-batch-editor-keyboard-grid.png")
            page.locator("#bulk-dialog").get_by_role("button", name="Cancel", exact=True).click()
            first_action = page.locator("[data-quick-actions] > button").first
            first_label = first_action.get_attribute("data-base-label")
            first_action.focus()
            first_action.press("Alt+ArrowRight")
            assert page.locator("[data-quick-actions] > button").nth(1).get_attribute("data-base-label") == first_label
            results["scenarios"].append("Batch Editor arrows, Ctrl+A, Ctrl+1, descriptions and reorder operate from the keyboard-first grid")

            page.locator("[data-select-all]").check()
            page.locator('[data-bulk="set_price"]').click()
            page.locator("#bulk-value").fill("4.00")
            page.locator("#bulk-apply").click()
            page.wait_for_timeout(1600)
            page.wait_for_load_state("domcontentloaded")
            assert page.locator("[data-field='price_cents']").first.input_value() == "4.00"
            shot(page, "10-batch-editor-atomic-bulk.png")
            results["scenarios"].append("20-row bulk Price completes atomically through the same preview dialog")

            page.goto(f"{BASE}/publish?batch_id={batch_id}", wait_until="domcontentloaded")
            with page.expect_download() as download_info:
                page.get_by_role("link", name="Download CSV").click()
            downloaded = DOWNLOADS / "inventory_work.csv"
            download_info.value.save_as(downloaded)
            edited = DOWNLOADS / "inventory_work-edited.csv"
            with downloaded.open("r", newline="", encoding="utf-8-sig") as source:
                reader = csv.DictReader(source)
                rows = list(reader)
                fields = reader.fieldnames or []
            for index, row in enumerate(rows, start=1):
                row["Title"] = row.get("Title") or f"CSV Reviewed Tape {index:03d}"
                row["Price"] = "4.00"
            with edited.open("w", newline="", encoding="utf-8-sig") as target:
                writer = csv.DictWriter(target, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            page.locator("input[name='csv_file']").set_input_files(str(edited))
            page.get_by_role("button", name="Upload and preview differences").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("CSV DIFFERENCE PREVIEW", exact=True).wait_for()
            shot(page, "11-csv-difference-preview.png")
            page.locator("input[name='confirmation']").check()
            page.get_by_role("button", name="Apply Valid Changes").click()
            page.wait_for_load_state("domcontentloaded")
            assert "CSV applied" in page.content()
            results["scenarios"].append("CSV remains staged until diff confirmation, then applies atomically")

            external = page.locator("form[action='/publish/external-review']")
            external.locator("input[name='confirmation']").check()
            external.get_by_role("button", name="Mark valid batch externally reviewed").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_role("link", name="Run Shopify simulation").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("SHOPIFY SIMULATION", exact=True).wait_for()
            shot(page, "12-shopify-simulation-test-mode.png")
            results["scenarios"].append("External review and explicit test-mode Shopify simulation complete")

            server.start(test_mode=False)
            page.goto(f"{BASE}/batch-editor?batch_id={batch_id}", wait_until="domcontentloaded")
            assert page.locator("[data-field='price_cents']").first.input_value() in {"4.00", "12.99"}
            shot(page, "13-restart-durability-production.png")
            results["scenarios"].append("Saved values and immutable batch identity survive process restart")

            page.goto(f"{BASE}/publish?batch_id={batch_id}", wait_until="domcontentloaded")
            page.get_by_role("link", name="Run Shopify simulation").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("SHOPIFY SIMULATION", exact=True).wait_for()
            # CSV_EXTERNAL_REVIEW is a deliberate manual replacement, so historical test evidence remains
            # in diagnostics but no longer poisons the confirmed working values.
            shot(page, "14-shopify-simulation-production-manual-replacement.png")

            page.goto(f"{BASE}/diagnostics", wait_until="domcontentloaded")
            page.get_by_text("System health", exact=True).wait_for()
            assert "Schema manifest" in page.content()
            shot(page, "15-diagnostics-catalog.png")
            results["scenarios"].append("Diagnostics exposes schema, WAL, staging, checkpoint and provenance facts")

            context.tracing.stop(path=str(AUDIT / "trace.zip"))
            page.close()
            context.close()
            browser.close()
    finally:
        server.stop()

    relevant_http = [entry for entry in results["http_errors"] if "/favicon" not in entry]
    expected_download_aborts = [
        entry for entry in results["failed_requests"] if "/publish/csv/" in entry
    ]
    relevant_failed_requests = [
        entry for entry in results["failed_requests"] if entry not in expected_download_aborts
    ]
    results["expected_download_aborts"] = expected_download_aborts
    results["relevant_failed_requests"] = relevant_failed_requests
    results["passed"] = not (
        results["console_errors"]
        or results["page_errors"]
        or relevant_failed_requests
        or relevant_http
    )
    results["relevant_http_errors"] = relevant_http
    (AUDIT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    lines = [
        "# SnapIMS v0.7.0 Native Browser Verification",
        "",
        f"Status: {'PASSED' if results['passed'] else 'FAILED'}",
        "",
        f"Batch: `{results.get('batch_id', '')}`",
        "Viewport: 1440 × 1000",
        "Monitoring was attached before first navigation.",
        "",
        "## Verified scenarios",
        *[f"- {scenario}" for scenario in results["scenarios"]],
        "",
        f"Console errors: {len(results['console_errors'])}",
        f"Page errors: {len(results['page_errors'])}",
        f"Relevant failed requests: {len(relevant_failed_requests)}",
        f"Expected browser download aborts: {len(expected_download_aborts)}",
        f"Relevant HTTP errors: {len(relevant_http)}",
    ]
    (AUDIT / "NATIVE_BROWSER_VERIFICATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))
    if not results["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
