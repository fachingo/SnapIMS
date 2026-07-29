from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import ConsoleMessage, Error, sync_playwright

from snapims import db
from snapims.config import DataPaths
from snapims.demo import create_demo_batch
from snapims.processor import process_batch
from snapims.recognition.base import BaseRecognizer, RecognitionResult
from snapims.recognition.providers import MockRecognizer
from snapims.recognition.service import accept_item, run_recognition

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "release-evidence" / "v0.10.0" / "phase-4-firefox"


class UnknownRecognizer(BaseRecognizer):
    name = "fixture-unknown"

    def model_name(self) -> str:
        return "fixture-unknown-v1"

    def recognize(self, item, images):
        return RecognitionResult(
            suggested_title="UNKNOWN",
            confidence=0.08,
            uncertainty_reasons=("Title evidence is insufficient",),
            title_evidence=(),
            contradiction_flags=("LOW_CONTRAST",),
            provider_name=self.name,
        )


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_for_health(url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout is not None else ""
            raise RuntimeError("Phase 4 browser server exited:\n" + output)
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError("Phase 4 browser server did not become healthy")


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


def wait_for_request(db_file: Path, request_id: str) -> str:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with db.connect(db_file) as connection:
            row = connection.execute(
                "SELECT status FROM recognition_requests WHERE request_id=?",
                (request_id,),
            ).fetchone()
        if row and str(row[0]) in {"COMPLETE", "FAILED", "PAUSED"}:
            return str(row[0])
        time.sleep(0.05)
    raise TimeoutError(f"Recognition request did not finish: {request_id}")


def main() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="snapims-v010-phase4-firefox-"))
    data_dir = workspace / "data"
    paths = DataPaths.from_root(data_dir).ensure()
    source = create_demo_batch(workspace / "camera", item_count=2)

    environment = os.environ.copy()
    environment.update(
        {
            "SNAPIMS_SKIP_DOTENV": "1",
            "SNAPIMS_PROJECT_PATH": str(ROOT),
            "SNAPIMS_DATA_DIR": str(data_dir),
            "SNAPIMS_ENABLE_TEST_PROVIDERS": "true",
            "SNAPIMS_AUTH_SECRET": "",
            "SNAPIMS_ADMIN_PASSWORD_HASH": "",
            "OPENAI_API_KEY": "",
            "SHOPIFY_ADMIN_ACCESS_TOKEN": "",
            "CLOUDFLARE_TUNNEL_CONFIG": str(
                workspace / "missing-cloudflared.yml"
            ),
        }
    )
    os.environ.update(
        {
            "SNAPIMS_SKIP_DOTENV": "1",
            "SNAPIMS_PROJECT_PATH": str(ROOT),
            "SNAPIMS_DATA_DIR": str(data_dir),
            "SNAPIMS_ENABLE_TEST_PROVIDERS": "true",
        }
    )
    imported = process_batch(source, paths=paths)
    items = db.list_items(paths.db_file, batch_id=imported.batch_id)
    first_id, _ = run_recognition(
        paths.db_file, items[0]["item_id"], MockRecognizer()
    )
    assert accept_item(
        paths.db_file,
        items[0]["item_id"],
        price_cents=999,
        discount_percent=0,
    ) == []
    run_recognition(
        paths.db_file, items[1]["item_id"], UnknownRecognizer()
    )

    url = f"http://127.0.0.1:{free_port()}"
    server = start_server(data_dir, environment, url)
    console_errors: list[str] = []
    page_errors: list[str] = []
    results: dict[str, Any] = {
        "browser": "Playwright Firefox",
        "url": url,
        "workspace": str(workspace),
        "checks": {},
        "console_errors": console_errors,
        "page_errors": page_errors,
    }
    try:
        with sync_playwright() as playwright:
            browser = playwright.firefox.launch(headless=True)
            context = browser.new_context(viewport={"width": 1600, "height": 1100})
            page = context.new_page()

            def record_console(message: ConsoleMessage) -> None:
                if message.type == "error":
                    console_errors.append(message.text)

            def record_page_error(error: Error) -> None:
                page_errors.append(str(error))

            page.on("console", record_console)
            page.on("pageerror", record_page_error)

            page.goto(
                f"{url}/recognition?batch_id={imported.batch_id}",
                wait_until="networkidle",
            )
            source_text = page.content()
            results["checks"]["recognition_workspace"] = all(
                value in source_text
                for value in (
                    "Recognition",
                    "CONFIGURED LADDER",
                    "Force Rerun All",
                    "Estimated CAD",
                    "Owner-labelled comparison report",
                )
            )
            page.screenshot(
                path=EVIDENCE / "01-recognition-workspace.png", full_page=True
            )

            first_item = items[0]["item_id"]
            page.goto(
                f"{url}/review?batch_id={imported.batch_id}&queue=ALL&item_id={first_item}",
                wait_until="networkidle",
            )
            results["checks"]["successful_item_rerun_controls"] = (
                "Run Recognition Again" in page.content()
                and "Queue immutable attempt" in page.content()
                and "Accept into working fields" in page.content()
            )
            request_id = page.locator(
                'form[action="/recognition/run-item"] [name="request_id"]'
            ).input_value()
            body = urllib.parse.urlencode(
                {
                    "batch_id": imported.batch_id,
                    "item_id": first_item,
                    "request_id": request_id,
                    "provider": "mock",
                    "model_name": "",
                    "tier": "baseline",
                    "image_profile": "standard",
                }
            ).encode()
            for _ in range(2):
                with urllib.request.urlopen(
                    urllib.request.Request(
                        f"{url}/recognition/run-item",
                        data=body,
                        method="POST",
                        headers={
                            "Content-Type": "application/x-www-form-urlencoded"
                        },
                    ),
                    timeout=5,
                ) as response:
                    response.read()
            results["checks"]["duplicate_force_click_idempotent"] = (
                wait_for_request(paths.db_file, request_id) == "COMPLETE"
            )
            with db.connect(paths.db_file) as connection:
                request_count = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM recognition_requests WHERE request_id=?",
                        (request_id,),
                    ).fetchone()[0]
                )
            results["checks"]["duplicate_force_click_idempotent"] &= (
                request_count == 1
            )
            approved_after = db.get_item(paths.db_file, first_item)
            results["checks"]["approved_fields_unchanged_after_rerun"] = (
                approved_after is not None
                and approved_after["title"] == "Demo VHS 001"
                and approved_after["review_status"] == "DONE"
                and len(db.recognition_history(paths.db_file, first_item)) == 2
            )

            page.goto(
                f"{url}/review?batch_id={imported.batch_id}&queue=ALL&item_id={first_item}",
                wait_until="networkidle",
            )
            results["checks"]["attempt_cost_latency_visible"] = all(
                value in page.content()
                for value in ("tokens", "ms", "estimated CA$", "Current suggestion")
            )
            page.screenshot(
                path=EVIDENCE / "02-rerun-attempt-history.png",
                full_page=True,
            )

            second_item = items[1]["item_id"]
            page.goto(
                f"{url}/review?batch_id={imported.batch_id}&queue=ALL&item_id={second_item}",
                wait_until="networkidle",
            )
            unknown_item = db.get_item(paths.db_file, second_item)
            results["checks"]["unknown_visible_and_unfinished"] = bool(
                "UNKNOWN" in page.content()
                and unknown_item
                and unknown_item["ready"] == 0
            )

            page.goto(
                f"{url}/import?source_folder={urllib.parse.quote(str(source))}",
                wait_until="networkidle",
            )
            page.get_by_role("button", name="Preview batch").click()
            page.get_by_text("Duplicate source fingerprint").wait_for()
            duplicate_source = page.content()
            results["checks"]["duplicate_options_visible"] = all(
                value in duplicate_source
                for value in (
                    "Open Existing Batch",
                    "Rerun Unfinished",
                    "Rerun All",
                    "Isolated Test Copy",
                    "Cancel",
                )
            )
            page.locator('[name="duplicate_action"]').select_option("test_copy")
            page.get_by_role("button", name="Apply duplicate action").click()
            page.get_by_text(
                "Isolated test copy created with separate IDs", exact=False
            ).wait_for()
            with db.connect(paths.db_file) as connection:
                copy = connection.execute(
                    """SELECT * FROM batches WHERE source_batch_id=?
                       ORDER BY imported_at DESC LIMIT 1""",
                    (imported.batch_id,),
                ).fetchone()
            results["checks"]["test_copy_quarantined"] = bool(
                copy
                and copy["is_test_copy"] == 1
                and copy["publish_eligible"] == 0
                and copy["reservation_eligible"] == 0
            )
            page.screenshot(
                path=EVIDENCE / "03-test-copy-quarantine.png",
                full_page=True,
            )

            with db.transaction(paths.db_file) as connection:
                connection.execute(
                    """INSERT INTO recognition_requests(
                           request_id,idempotency_key,item_id,batch_id,provider,
                           status,created_at,updated_at
                       ) VALUES('restart-fixture','restart-fixture',?,?,'mock',
                                'RUNNING',?,?)""",
                    (first_item, imported.batch_id, db.now(), db.now()),
                )
            stop_server(server)
            server = start_server(data_dir, environment, url)
            page.goto(
                f"{url}/recognition?batch_id={imported.batch_id}",
                wait_until="networkidle",
            )
            results["checks"]["restart_pauses_interrupted_request"] = (
                "PAUSED" in page.content()
                and "Resume safely" in page.content()
            )
            with db.connect(paths.db_file) as connection:
                restart_state = connection.execute(
                    """SELECT status FROM recognition_requests
                       WHERE request_id='restart-fixture'"""
                ).fetchone()[0]
            results["checks"]["restart_pauses_interrupted_request"] &= (
                restart_state == "PAUSED"
            )

            page.goto(
                f"{url}/review?batch_id={imported.batch_id}&queue=ALL&item_id={first_item}",
                wait_until="networkidle",
            )
            older_form = page.locator(
                f'form[action="/recognition/select"] input[value="{first_id}"]'
            )
            if older_form.count():
                older_form.locator("xpath=..").get_by_role(
                    "button", name="Select for review"
                ).click()
                page.wait_for_load_state("networkidle")
            selected = db.selected_recognition(paths.db_file, first_item)
            approved_item = db.get_item(paths.db_file, first_item)
            results["checks"]["older_attempt_selectable"] = bool(
                selected
                and selected["recognition_result_id"] == first_id
                and approved_item
                and approved_item["title"] == "Demo VHS 001"
            )
            browser.close()
    finally:
        if server.poll() is None:
            stop_server(server)

    results["checks"]["schema_integrity_after_restart"] = False
    with db.connect(paths.db_file) as connection:
        results["checks"]["schema_integrity_after_restart"] = (
            connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            and not connection.execute("PRAGMA foreign_key_check").fetchall()
            and db.schema_manifest_report(connection)["ok"]
        )
    results["passed"] = (
        all(results["checks"].values())
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
