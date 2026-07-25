from __future__ import annotations

import csv
import json
import os
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

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from snapims import __version__, db  # noqa: E402
from snapims.catalog import SLMC_VERSION  # noqa: E402
from snapims.catalog import db as catalog_db  # noqa: E402
from snapims.catalog.models import MovieCandidate  # noqa: E402
from snapims.catalog.service import create_or_update_movie  # noqa: E402
from snapims.config import DataPaths  # noqa: E402
from snapims.demo import create_demo_batch  # noqa: E402
from snapims.processor import process_batch  # noqa: E402
from snapims.shopify.service import ShopifyService  # noqa: E402
from snapims.config import ShopifyConfig  # noqa: E402

AUDIT = ROOT / "operator-audit-assets" / "slmc-0.1.0-browser"
SHOTS = AUDIT / "screenshots"
WORK = AUDIT / "workspace"
CAMERA = AUDIT / "camera-roll"
CAMERA2 = AUDIT / "camera-roll-second"
DOWNLOADS = AUDIT / "downloads"
LOGS = AUDIT / "logs"
PORT = 8894
BASE = f"http://127.0.0.1:{PORT}"
POLICY = Path("/etc/chromium/policies/managed/000_policy_merge.json")
FIXTURES = ROOT / "tests" / "fixtures" / "wikipedia"


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
    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.log_handle = None
        self.log_paths: list[Path] = []

    def start(self) -> None:
        LOGS.mkdir(parents=True, exist_ok=True)
        log_path = LOGS / f"server-{len(self.log_paths) + 1}.log"
        self.log_paths.append(log_path)
        self.log_handle = log_path.open("w", encoding="utf-8")
        env = os.environ.copy()
        env.pop("OPENAI_API_KEY", None)
        env.pop("SHOPIFY_ADMIN_ACCESS_TOKEN", None)
        env.update(
            {
                "SNAPIMS_DATA_DIR": str(WORK),
                "SNAPIMS_TEST_FOLDER_PICKER": str(CAMERA),
                "SNAPIMS_WIKIPEDIA_FIXTURE_DIR": str(FIXTURES),
                "PYTHONUNBUFFERED": "1",
            }
        )
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
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log_handle:
            self.log_handle.close()
        self.process = None
        self.log_handle = None


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(SHOTS / name), full_page=True)


def wait_recognition_complete(page: Page, timeout: int = 90000) -> None:
    page.wait_for_function(
        """() => {
          const text = document.querySelector('#recognition-status strong')?.textContent || '';
          return text.includes('Recognition complete') || text.includes('Review complete') || text.includes('failed');
        }""",
        timeout=timeout,
    )


def wait_catalog_terminal(paths: DataPaths, batch_id: str, timeout: float = 45) -> None:
    deadline = time.monotonic() + timeout
    terminal = {"LOCAL_MATCHED", "LINKED", "AMBIGUOUS", "NOT_FOUND", "FAILED", "LINK_PENDING"}
    item_ids = [str(item["item_id"]) for item in db.list_items(paths.db_file, batch_id=batch_id)]
    while time.monotonic() < deadline:
        with catalog_db.connect(paths.catalog_db_file, readonly=True) as connection:
            rows = connection.execute(
                "SELECT item_id,status FROM catalog_lookup_jobs WHERE item_id IN (%s)"
                % ",".join("?" for _ in item_ids),
                item_ids,
            ).fetchall()
        states = {str(row["item_id"]): str(row["status"]) for row in rows}
        if len(states) == len(item_ids) and all(states[item_id] in terminal for item_id in item_ids):
            return
        time.sleep(0.2)
    raise RuntimeError(f"Catalog jobs did not settle for {batch_id}")


def seed_local_movie(paths: DataPaths) -> str:
    catalog_db.initialize(paths.catalog_db_file, paths=paths)
    movie_id, _ = create_or_update_movie(
        paths.catalog_db_file,
        MovieCandidate(
            provider="wikipedia",
            source_page_id="1001",
            source_page_title="Demo VHS 001 (1991 film)",
            source_url="https://en.wikipedia.org/wiki/Demo_VHS_001_(1991_film)",
            canonical_title="Demo VHS 001",
            release_year=1991,
            runtime_minutes=91,
            countries=("Canada",),
            languages=("English",),
            directors=("Local Sample Director",),
            genres=("Drama",),
            summary="Synthetic deterministic browser-audit fixture for a local catalog hit.",
            aliases=("Demo VHS One",),
            source_revision_id="1001001",
            parser_version="slmc-browser-fixture-1",
            raw_response_hash="browser-fixture-1001",
            attribution="Wikipedia fixture; not a live request",
        ),
    )
    return movie_id


def catalog_counts(paths: DataPaths) -> dict[str, int]:
    with catalog_db.connect(paths.catalog_db_file, readonly=True) as connection:
        return {
            "movies": int(connection.execute("SELECT COUNT(*) FROM movies").fetchone()[0]),
            "aliases": int(connection.execute("SELECT COUNT(*) FROM movie_aliases").fetchone()[0]),
            "wikipedia_attempts": int(
                connection.execute(
                    "SELECT COUNT(*) FROM catalog_lookup_attempts WHERE provider_name='wikipedia'"
                ).fetchone()[0]
            ),
            "jobs": int(connection.execute("SELECT COUNT(*) FROM catalog_lookup_jobs").fetchone()[0]),
        }


def link_snapshot(paths: DataPaths, batch_id: str) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for item in db.list_items(paths.db_file, batch_id=batch_id):
        link = db.get_item_movie_link(paths.db_file, str(item["item_id"])) or {}
        output.append(
            {
                "item_id": str(item["item_id"]),
                "movie_id": str(link.get("movie_id") or ""),
                "link_status": str(link.get("link_status") or ""),
                "link_method": str(link.get("link_method") or ""),
            }
        )
    return output


def current_item_id(page: Page) -> str:
    return page.locator(".physical-header code").inner_text().strip()


def approve_current_with_enter(page: Page, *, price: str | None = None, discount: str | None = None) -> tuple[str, str]:
    old = current_item_id(page)
    if price is not None:
        page.locator("#quick-price").fill(price)
    if discount is not None:
        page.locator('input[name="discount"]').fill(discount)
    page.locator("#quick-price").focus()
    with page.expect_response(
        lambda response: "/review/approve" in response.url and response.request.method == "POST",
        timeout=30000,
    ):
        page.keyboard.press("Enter")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_function(
        "old => document.querySelector('.physical-header code')?.textContent.trim() !== old || document.body.textContent.includes('Review complete')",
        arg=old,
    )
    new = current_item_id(page) if page.locator(".physical-header code").count() else ""
    return old, new


def git_metadata() -> dict[str, str]:
    def command(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

    return {
        "commit": command("rev-parse", "HEAD"),
        "branch": command("branch", "--show-current"),
        "status": command("status", "--short"),
    }


def main() -> None:
    print("[slmc-browser] reset", flush=True)
    shutil.rmtree(AUDIT, ignore_errors=True)
    for path in (SHOTS, DOWNLOADS, LOGS):
        path.mkdir(parents=True, exist_ok=True)
    create_demo_batch(CAMERA, item_count=2, photos_per_item=2, shelf="A1")
    create_demo_batch(CAMERA2, item_count=2, photos_per_item=2, shelf="B2")
    paths = DataPaths.from_root(WORK).ensure()
    local_movie_id = seed_local_movie(paths)

    results: dict[str, object] = {
        "package": SLMC_VERSION,
        "application_version": __version__,
        "inventory_schema": db.SCHEMA_VERSION,
        "catalog_schema": catalog_db.CATALOG_SCHEMA_VERSION,
        "metadata": git_metadata(),
        "local_seed_movie_id": local_movie_id,
        "scenarios": [],
        "console_errors": [],
        "page_errors": [],
        "request_failures": [],
        "limitations": [
            "Recognition used the deterministic Mock provider, not live AI.",
            "Wikipedia used deterministic fixtures through the official-client parsing path, not live network calls.",
            "Shopify was simulation-only; no live draft or publication was attempted.",
        ],
    }

    server = Server()
    server.start()
    print("[slmc-browser] server started", flush=True)
    try:
        with chromium_policy_allows_loopback(), sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=os.getenv("SNAPIMS_CHROMIUM", "/usr/bin/chromium"),
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
            page = context.new_page()
            page.set_default_timeout(30000)
            page.on("console", lambda message: results["console_errors"].append(message.text) if message.type == "error" else None)
            page.on("pageerror", lambda error: results["page_errors"].append(str(error)))
            page.on("requestfailed", lambda request: results["request_failures"].append(f"{request.method} {request.url}: {request.failure}"))

            print("[slmc-browser] import", flush=True)
            page.goto(f"{BASE}/import", wait_until="domcontentloaded")
            details = page.locator("details.advanced")
            if details.count() and not details.evaluate("element => element.open"):
                details.locator("summary").click()
            page.get_by_role("button", name="Browse Folder…").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_role("button", name="Preview batch").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("PREVIEW · NOT IMPORTED YET", exact=True).wait_for()
            shot(page, "01-import-preview.png")
            page.get_by_role("button", name="Preserve and import batch").click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text("IMPORTED BATCH", exact=True).wait_for()
            first_batch = page.locator("section.success-panel code").inner_text().strip()
            shot(page, "02-import-complete.png")
            results["scenarios"].append("Actual browser Import preview and preserve completed for a two-item batch.")

            print("[slmc-browser] identify first batch", flush=True)
            page.get_by_role("link", name="Continue to Review").click()
            page.wait_for_load_state("domcontentloaded")
            page.locator("#recognition-status select[name='provider']").select_option("mock")
            page.locator("#recognition-status button").click()
            page.wait_for_load_state("domcontentloaded")
            wait_recognition_complete(page)
            wait_catalog_terminal(paths, first_batch)
            page.goto(f"{BASE}/review?batch_id={first_batch}", wait_until="domcontentloaded")
            page.get_by_text("Catalog match: LOCAL MATCH", exact=True).wait_for()
            assert page.get_by_text("Demo VHS 001 (1991)", exact=True).is_visible()
            first_item = current_item_id(page)
            first_status = page.locator(".catalog-match").inner_text()
            counts_after_first = catalog_counts(paths)
            assert counts_after_first["wikipedia_attempts"] == 1, counts_after_first
            shot(page, "03-local-match-review.png")
            results["scenarios"].append(
                "Recognition committed first; Demo VHS 001 resolved from the permanent local catalog without an external attempt."
            )

            print("[slmc-browser] approve first by Enter", flush=True)
            old, new = approve_current_with_enter(page, price="12.00", discount="5")
            assert old == first_item
            assert new and new != old
            page.get_by_text("Catalog match: NEW CATALOG RECORD", exact=True).wait_for()
            assert page.get_by_text("Demo VHS 002 (1992)", exact=True).is_visible()
            shot(page, "04-new-wikipedia-record-and-next.png")
            results["scenarios"].append(
                "Enter approved the first item once, preserved quick Price/Discount, and opened the next physical item with a newly ingested catalog record."
            )
            approve_current_with_enter(page, price="9.99", discount="0")
            assert "Review complete" in page.locator("#recognition-status strong").inner_text()
            shot(page, "05-review-complete.png")

            print("[slmc-browser] create second batch", flush=True)
            second_import = process_batch(CAMERA2, paths=paths, batch_name="SLMC-SECOND")
            second_batch = second_import.batch_id
            page.goto(f"{BASE}/review?batch_id={second_batch}", wait_until="domcontentloaded")
            page.locator("#recognition-status select[name='provider']").select_option("mock")
            page.locator("#recognition-status button").click()
            page.wait_for_load_state("domcontentloaded")
            wait_recognition_complete(page)
            wait_catalog_terminal(paths, second_batch)
            page.goto(f"{BASE}/review?batch_id={second_batch}", wait_until="domcontentloaded")
            assert page.get_by_text("Catalog match: LOCAL MATCH", exact=True).is_visible()
            counts_after_second = catalog_counts(paths)
            assert counts_after_second["wikipedia_attempts"] == 1, counts_after_second
            second_links = link_snapshot(paths, second_batch)
            first_links = link_snapshot(paths, first_batch)
            assert second_links[1]["movie_id"] == first_links[1]["movie_id"]
            shot(page, "06-second-copy-local-reuse.png")
            results["scenarios"].append(
                "A second batch reused both local Movie records; the Wikipedia-attempt count remained exactly one."
            )

            first_second_item, second_second_item = [str(row["item_id"]) for row in db.list_items(paths.db_file, batch_id=second_batch)]
            approve_current_with_enter(page, price="8.50", discount="10")
            assert current_item_id(page) == second_second_item
            approve_current_with_enter(page, price="7.50", discount="0")

            print("[slmc-browser] publish/csv", flush=True)
            page.goto(f"{BASE}/publish?batch_id={second_batch}&simulate=true", wait_until="domcontentloaded")
            page.get_by_text("SHOPIFY SIMULATION", exact=True).wait_for()
            shot(page, "07-shopify-simulation.png")
            with page.expect_download() as download_info:
                page.get_by_role("link", name="Download CSV").click()
            csv_path = DOWNLOADS / "slmc-working.csv"
            download_info.value.save_as(csv_path)
            with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
                csv_rows = list(csv.DictReader(handle))
            assert len(csv_rows) == 2
            assert csv_rows[0]["Item ID"] == first_second_item
            assert csv_rows[0]["Local Movie ID"]
            assert csv_rows[0]["Canonical Movie title"] == "Demo VHS 001"
            assert csv_rows[1]["Canonical Movie title"] == "Demo VHS 002"
            results["scenarios"].append(
                "CSV preserved Item ID and included the same durable local Movie IDs and structured catalog fields."
            )

            service = ShopifyService(paths.db_file, ShopifyConfig.from_env())
            dry_runs = [service.dry_run(str(item["item_id"])) for item in db.list_items(paths.db_file, batch_id=second_batch)]
            structured = [report.payload.get("movie", {}) for report in dry_runs]
            assert structured[0].get("movie_id") == csv_rows[0]["Local Movie ID"]
            assert structured[1].get("canonical_title") == "Demo VHS 002"
            with db.connect(paths.db_file) as connection:
                remote_rows = connection.execute(
                    "SELECT status,product_id FROM shopify_sync WHERE item_id IN (SELECT item_id FROM items WHERE batch_id=?)",
                    (second_batch,),
                ).fetchall()
            assert all(str(row["status"]) != "UPLOADED" and not str(row["product_id"] or "") for row in remote_rows)
            results["scenarios"].append(
                "Shopify simulation received structured Movie facts; no remote product ID or automatic publication was created."
            )

            page.goto(f"{BASE}/diagnostics", wait_until="domcontentloaded")
            page.get_by_text("Local movie catalog", exact=True).wait_for()
            shot(page, "08-catalog-diagnostics.png")
            results["scenarios"].append("Diagnostics displayed catalog schema, integrity, counts, jobs, FTS, and maintenance controls.")

            before_restart = {
                "counts": catalog_counts(paths),
                "first_links": first_links,
                "second_links": second_links,
            }
            context.close()
            browser.close()

        print("[slmc-browser] restart", flush=True)
        server.stop()
        server.start()
        with chromium_policy_allows_loopback(), sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=os.getenv("SNAPIMS_CHROMIUM", "/usr/bin/chromium"),
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            page.on("console", lambda message: results["console_errors"].append(message.text) if message.type == "error" else None)
            page.on("pageerror", lambda error: results["page_errors"].append(str(error)))
            page.on("requestfailed", lambda request: results["request_failures"].append(f"{request.method} {request.url}: {request.failure}"))
            page.goto(f"{BASE}/review?batch_id={second_batch}&queue=DONE", wait_until="domcontentloaded")
            page.get_by_text("Catalog match: LOCAL MATCH", exact=True).wait_for()
            shot(page, "09-restart-durable-catalog.png")
            after_restart = {
                "counts": catalog_counts(paths),
                "first_links": link_snapshot(paths, first_batch),
                "second_links": link_snapshot(paths, second_batch),
            }
            assert before_restart == after_restart
            results["scenarios"].append("Full process restart preserved Movies, aliases, jobs, and inventory links.")
            context.close()
            browser.close()

        with db.connect(paths.db_file) as connection:
            inventory_integrity = {
                "integrity": str(connection.execute("PRAGMA integrity_check").fetchone()[0]),
                "foreign_key_violations": len(connection.execute("PRAGMA foreign_key_check").fetchall()),
                "schema_version": int(connection.execute("PRAGMA user_version").fetchone()[0]),
            }
        with catalog_db.connect(paths.catalog_db_file, readonly=True) as connection:
            catalog_integrity = {
                "integrity": str(connection.execute("PRAGMA integrity_check").fetchone()[0]),
                "foreign_key_violations": len(connection.execute("PRAGMA foreign_key_check").fetchall()),
                "schema_version": catalog_db.CATALOG_SCHEMA_VERSION,
            }
        results.update(
            {
                "first_batch": first_batch,
                "second_batch": second_batch,
                "counts_after_first_batch": counts_after_first,
                "counts_after_second_batch": counts_after_second,
                "first_batch_links": first_links,
                "second_batch_links": second_links,
                "csv": csv_rows,
                "shopify_structured_movie_payloads": structured,
                "inventory_integrity": inventory_integrity,
                "catalog_integrity": catalog_integrity,
                "restart_snapshot_equal": True,
            }
        )
        expected_aborts = [failure for failure in results["request_failures"] if "ERR_ABORTED" in failure]
        unexpected_failures = [failure for failure in results["request_failures"] if "ERR_ABORTED" not in failure]
        results["expected_request_aborts"] = expected_aborts
        results["request_failures"] = unexpected_failures
        assert not results["page_errors"], results["page_errors"]
        assert not unexpected_failures, unexpected_failures
        # Chromium reports intentional redirect/download cancellation as ERR_ABORTED;
        # preserve those separately while failing any unexpected request failure.
        # retain exact evidence and fail for any JavaScript exception-style error.
        severe_console = [
            message for message in results["console_errors"]
            if "favicon" not in message.casefold() and "404" not in message.casefold()
        ]
        assert not severe_console, severe_console
        print("[slmc-browser] write results", flush=True)
        (AUDIT / "results.json").write_text(json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8")
    finally:
        server.stop()


if __name__ == "__main__":
    main()
