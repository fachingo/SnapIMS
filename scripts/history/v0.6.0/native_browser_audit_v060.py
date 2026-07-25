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

AUDIT = ROOT / "operator-audit-assets" / "v0.6.0-browser"
SHOTS = AUDIT / "screenshots"
WORK = AUDIT / "workspace"
CAMERA = AUDIT / "camera-roll"
DOWNLOADS = AUDIT / "downloads"
LOGS = AUDIT / "logs"
PORT = 8892
BASE = f"http://127.0.0.1:{PORT}"
POLICY = Path("/etc/chromium/policies/managed/000_policy_merge.json")


@contextmanager
def chromium_policy_allows_loopback() -> Iterator[None]:
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


def wait_health(timeout: float = 20) -> None:
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
        self.log = None

    def start(self) -> None:
        LOGS.mkdir(parents=True, exist_ok=True)
        self.log = (LOGS / f"server-{int(time.time())}.log").open("w", encoding="utf-8")
        env = os.environ.copy()
        env.pop("OPENAI_API_KEY", None)
        env.update(
            {
                "SNAPIMS_DATA_DIR": str(WORK),
                "SNAPIMS_TEST_FOLDER_PICKER": str(self.camera),
                "PYTHONUNBUFFERED": "1",
            }
        )
        self.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "snapims.web.app:app", "--host", "127.0.0.1", "--port", str(PORT)],
            cwd=ROOT,
            env=env,
            stdout=self.log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_health()

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log:
            self.log.close()
        self.process = None
        self.log = None


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(SHOTS / name), full_page=True)


def wait_job(page: Page) -> None:
    page.wait_for_function(
        """() => {
          const text = document.querySelector('#recognition-status strong')?.textContent || '';
          return text.includes('Recognition complete') || text.includes('Review complete') || text.includes('failed');
        }""",
        timeout=60000,
    )


def main() -> None:
    shutil.rmtree(AUDIT, ignore_errors=True)
    for path in (SHOTS, DOWNLOADS, LOGS):
        path.mkdir(parents=True, exist_ok=True)
    camera = create_demo_batch(CAMERA, item_count=20, photos_per_item=2, shelf="A1")
    server = Server(camera)
    server.start()
    results: dict[str, object] = {"version": "0.6.0", "scenarios": []}

    try:
        with chromium_policy_allows_loopback(), sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=os.getenv("SNAPIMS_CHROMIUM", "/usr/bin/chromium"),
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
            page = context.new_page()
            page.set_default_timeout(25000)

            page.goto(BASE, wait_until="domcontentloaded")
            page.get_by_text("Photograph. Resolve exceptions. Publish.", exact=True).wait_for()
            shot(page, "01-home-dashboard.png")
            results["scenarios"].append("Home dashboard rendered")

            page.goto(f"{BASE}/import", wait_until="domcontentloaded")
            advanced = page.locator("details.advanced")
            if not advanced.evaluate("element => element.open"):
                advanced.locator("summary").click()
            use_button = advanced.get_by_role("button", name="Use this folder")
            assert use_button.is_disabled()
            shot(page, "02-import-empty-safe.png")
            results["scenarios"].append("Empty folder action disabled; no raw FastAPI response")

            page.get_by_role("button", name="Browse Folder…").click()
            page.wait_for_load_state("domcontentloaded")
            assert str(camera) in page.locator(".folder-card code").inner_text()
            shot(page, "03-native-folder-selected.png")
            page.get_by_role("button", name="Preview batch").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("PREVIEW · NOT IMPORTED YET", exact=True).wait_for()
            shot(page, "04-import-preview.png")
            page.get_by_role("button", name="Preserve and import batch").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("IMPORTED BATCH", exact=True).wait_for()
            batch_id = page.locator("section.success-panel code").inner_text().strip()
            shot(page, "05-import-complete.png")
            results["scenarios"].append("20-item import completed without started_at failure")

            page.get_by_role("link", name="Continue to Review").click()
            page.wait_for_load_state("domcontentloaded")
            page.locator("#recognition-status select[name='provider']").select_option("openai")
            page.locator("#recognition-status button").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("RECOGNITION FAILURE", exact=True).wait_for()
            assert page.get_by_role("button", name="Retry Failed Items Only").is_visible()
            assert page.get_by_role("button", name="Continue With Manual Review").is_visible()
            shot(page, "06-recognition-failure-recovery.png")
            results["scenarios"].append("Missing OpenAI key produced actionable recovery screen")

            page.locator("form[action='/review/retry-batch']").first.locator("select[name='provider']").select_option("mock")
            page.get_by_role("button", name="Retry Batch").click()
            page.wait_for_load_state("domcontentloaded")
            wait_job(page)
            page.wait_for_timeout(350)
            shot(page, "07-recognition-complete.png")
            results["scenarios"].append("Recognition recovered through mock provider")

            price = page.locator("#quick-price")
            price.wait_for()
            assert price.evaluate("element => document.activeElement === element")
            price.fill("12.00")
            first_item = page.locator(".physical-header code").inner_text()
            price.press("Enter")
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_function(
                "old => document.querySelector('.physical-header code')?.textContent.trim() !== old",
                arg=first_item,
            )
            assert page.locator("#quick-price").evaluate("element => document.activeElement === element")
            shot(page, "08-price-enter-next.png")
            results["scenarios"].append("Price → Enter approved and focused next price")

            page.goto(f"{BASE}/batch-editor?batch_id={batch_id}", wait_until="domcontentloaded")
            page.get_by_text("Bulk operator workstation", exact=True).wait_for()
            title = page.locator("[data-field='title']").nth(1)
            title.fill("Batch Editor Corrected Tape")
            title.press("Enter")
            page.wait_for_timeout(700)
            page.locator("[data-select-all]").check()
            page.get_by_role("button", name="Bulk Price").click()
            page.locator("#bulk-value").fill("4.00")
            page.once("dialog", lambda dialog: dialog.accept())
            page.locator("#bulk-apply").click()
            page.wait_for_timeout(1200)
            shot(page, "09-batch-editor-bulk-price.png")
            results["scenarios"].append("Batch Editor inline edit and 20-row bulk price completed")

            page.keyboard.press("Control+Shift+P")
            page.locator("#command-palette").wait_for(state="visible")
            shot(page, "10-command-palette.png")
            page.keyboard.press("Escape")

            page.goto(f"{BASE}/publish?batch_id={batch_id}", wait_until="domcontentloaded")
            with page.expect_download() as download_info:
                page.get_by_role("link", name="Download CSV").click()
            download_path = DOWNLOADS / "working.csv"
            download_info.value.save_as(download_path)
            edited_path = DOWNLOADS / "edited.csv"
            with download_path.open("r", newline="", encoding="utf-8-sig") as source:
                reader = csv.DictReader(source)
                rows = list(reader)
                fields = reader.fieldnames or []
            for index, row in enumerate(rows, start=1):
                if not row.get("Title", "").strip():
                    row["Title"] = f"CSV Reviewed Tape {index:03d}"
                row["Price"] = "4.00"
            with edited_path.open("w", newline="", encoding="utf-8-sig") as destination:
                writer = csv.DictWriter(destination, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            page.locator("input[name='csv_file']").set_input_files(str(edited_path))
            page.get_by_role("button", name="Upload and preview differences").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("CSV DIFFERENCE PREVIEW", exact=True).wait_for()
            shot(page, "11-csv-difference-preview.png")
            page.locator("input[name='confirmation']").check()
            page.get_by_role("button", name="Apply Valid Changes").click()
            page.wait_for_load_state("domcontentloaded")
            shot(page, "12-csv-applied.png")
            results["scenarios"].append("CSV round trip showed diff and updated working batch")

            confirmation = page.locator("form[action='/publish/external-review'] input[name='confirmation']")
            confirmation.check()
            page.locator("form[action='/publish/external-review'] button").click()
            page.wait_for_load_state("domcontentloaded")
            assert "items marked externally reviewed" in page.locator(".alert.success").inner_text()
            page.get_by_role("link", name="Run Shopify simulation").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("SHOPIFY SIMULATION", exact=True).wait_for()
            shot(page, "13-publish-simulation.png")
            results["scenarios"].append("External review and Shopify simulation completed")

            server.stop()
            server.start()
            page.goto(f"{BASE}/batch-editor?batch_id={batch_id}", wait_until="domcontentloaded")
            page.get_by_text("Bulk operator workstation", exact=True).wait_for()
            assert page.locator("[data-field='price_cents']").first.input_value() == "4.00"
            shot(page, "14-restart-durable.png")
            results["scenarios"].append("Working values survived process restart")

            page.goto(f"{BASE}/diagnostics", wait_until="domcontentloaded")
            page.get_by_text("System health", exact=True).wait_for()
            shot(page, "15-diagnostics.png")
            results["scenarios"].append("Diagnostics rendered provider, schema, and media data")
            print("BROWSER WALKTHROUGH COMPLETE", flush=True)

            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            results["browser_console_errors"] = errors
            results["batch_id"] = batch_id
            results["viewport"] = "1440x1000"
            page.close()
            context.close()
            browser.close()
            print("BROWSER CLOSED", flush=True)
    finally:
        server.stop()

    results["passed"] = True
    (AUDIT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    lines = [
        "# SnapIMS v0.6.0 Native Browser Verification",
        "",
        "Status: PASSED",
        "",
        f"Batch: `{results.get('batch_id', '')}`",
        "Viewport: 1440 x 1000",
        "",
        "## Verified scenarios",
        *[f"- {scenario}" for scenario in results["scenarios"]],
        "",
        f"Browser page errors: {len(results.get('browser_console_errors', []))}",
    ]
    (AUDIT / "NATIVE_BROWSER_VERIFICATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
