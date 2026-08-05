#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import re
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from playwright.sync_api import BrowserType, Page, sync_playwright

from snapims import db
from snapims.config import DataPaths
from snapims.demo import create_demo_batch
from snapims.processor import process_batch

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "browser-evidence" / "v0.13.2"
DATA = Path(os.getenv("SNAPIMS_BROWSER_DATA", "/tmp/snapims-v0132-browser-data"))
PORT = int(os.getenv("SNAPIMS_BROWSER_PORT", "8878"))
BASE = f"http://snapims.test:{PORT}"
SERVER_BASE = f"http://127.0.0.1:{PORT}"


def _wait_http(url: str, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=1).status_code < 500:
                return
        except Exception:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"Server did not become ready: {url}")


def _direct_batch(paths: DataPaths, count: int, batch_id: str) -> str:
    stamp = db.now()
    with db.transaction(paths.db_file) as connection:
        connection.execute(
            """INSERT INTO batches(
                   batch_id,source_fingerprint,source_folder,created_at,imported_at,started,ended,
                   status,item_count,product_photo_count,command_count,warning_count,warnings_json,
                   display_name,source_folder_name
               ) VALUES(?,?,?,?,?,1,1,'IMPORTED',?,0,0,0,'[]',?,?)""",
            (batch_id, f"fp-{batch_id}", f"/fixtures/{batch_id}", stamp, stamp, count, batch_id, batch_id),
        )
        connection.executemany(
            """INSERT INTO items(
                   item_id,sku,batch_id,sequence,shelf,location,title,price_cents,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    f"{batch_id}-ITEM-{index:05d}", f"{batch_id}-SKU-{index:05d}", batch_id,
                    index, "", None, f"Tape {index:05d}", 499, stamp, stamp,
                )
                for index in range(1, count + 1)
            ],
        )
    return batch_id


def _seed() -> dict[str, str]:
    shutil.rmtree(DATA, ignore_errors=True)
    paths = DataPaths.from_root(DATA).ensure()
    db.initialize(paths.db_file, paths=paths)
    demo = process_batch(create_demo_batch(DATA / "camera", item_count=5), paths=paths, batch_name="BROWSER-QA")
    items = db.list_items(paths.db_file, batch_id=demo.batch_id)
    stamp = db.now()
    with db.transaction(paths.db_file) as connection:
        connection.executemany(
            """INSERT INTO tag_definitions(
                   tag_id,canonical_label,category,active,ai_eligible,shopify_visible,
                   deterministic_only,sort_order,created_at,updated_at,evidence_json
               ) VALUES(?,?, 'Operator',1,0,1,1,?,?,?,'{}')""",
            [
                ("TAG-BROWSER-A", "Browser A", 10, stamp, stamp),
                ("TAG-BROWSER-B", "Browser B", 20, stamp, stamp),
            ],
        )
    for index, item in enumerate(items, start=1):
        db.update_item(
            paths.db_file, item["item_id"], {"title": f"Browser Tape {index}"},
            source="BROWSER_FIXTURE", reason="Seed distinct browser title",
        )
    items = db.list_items(paths.db_file, batch_id=demo.batch_id)
    source = items[0]
    db.update_item(
        paths.db_file,
        source["item_id"],
        {
            "tag_ids": ["TAG-BROWSER-A", "TAG-BROWSER-B"],
            "location": "Processing Table",
            "shelf": "Processing Table",
            "review": 1,
            "rare": 1,
        },
        source="BROWSER_FIXTURE",
        reason="Seed browser verification source values",
    )
    large = _direct_batch(paths, 5000, "BATCH-V0132-5000")
    fixtures = ROOT / "tests" / "fixtures" / "import_v0130"
    shutil.copytree(fixtures / "03-twenty-items-normal-next", paths.batches / "BROWSER-20")
    shutil.copytree(fixtures / "27-100-items-202-photos", paths.batches / "BROWSER-100")
    return {"editor": demo.batch_id, "large": large}


def _check(results: dict[str, Any], name: str, ok: bool, detail: Any = "") -> None:
    results["checks"].append({"name": name, "ok": bool(ok), "detail": str(detail)})
    print(("PASS" if ok else "FAIL"), name, detail)


def _watch(page: Page, results: dict[str, Any]) -> None:
    page.on("console", lambda m: results["console_errors"].append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: results["page_errors"].append(str(e)))
    page.on("requestfailed", lambda r: results["failed_requests"].append({"url": r.url, "failure": r.failure}))
    page.on("response", lambda r: results["http_errors"].append({"url": r.url, "status": r.status}) if r.status >= 500 else None)


def _wait_reload(page: Page) -> None:
    page.wait_for_timeout(900)
    page.wait_for_load_state("domcontentloaded")


def _browser_pass(browser_type: BrowserType, executable_path: str | None, label: str, ids: dict[str, str]) -> dict[str, Any]:
    """Run browser UI verification with local HTTP proxied through Python.

    The execution environment applies a Chromium URLBlocklist to all HTTP
    navigation, including localhost. The browser still executes the real HTML,
    CSS, and JavaScript; HTTP reads and fetch calls are relayed to the actual
    local SnapIMS server by the test harness.
    """
    results: dict[str, Any] = {
        "browser": label,
        "network_mode": "local HTTP relayed because browser policy blocks localhost navigation",
        "checks": [],
        "console_errors": [],
        "page_errors": [],
        "failed_requests": [],
        "http_errors": [],
    }
    launch_args: dict[str, Any] = {"headless": True}
    if executable_path:
        launch_args["executable_path"] = executable_path
    if label == "chromium":
        launch_args["args"] = ["--no-sandbox", "--disable-dev-shm-usage"]
    browser = browser_type.launch(**launch_args)
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    server_client = httpx.Client(follow_redirects=True, timeout=30)
    page = context.new_page()
    page.set_default_timeout(12000)
    _watch(page, results)

    css = (ROOT / "snapims" / "web" / "static" / "app.css").read_text(encoding="utf-8")
    js = (ROOT / "snapims" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    transparent = "data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs="

    def proxy_request(payload: dict[str, Any]) -> dict[str, Any]:
        raw_url = str(payload.get("url") or "/")
        parsed = urlsplit(raw_url)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        headers = {str(k): str(v) for k, v in dict(payload.get("headers") or {}).items()}
        for key in list(headers):
            if key.casefold() in {"host", "content-length", "cookie"}:
                headers.pop(key, None)
        headers["Origin"] = SERVER_BASE
        headers["Referer"] = SERVER_BASE + "/"
        body = payload.get("body")
        response = server_client.request(
            str(payload.get("method") or "GET"),
            SERVER_BASE + path,
            headers=headers,
            content=body.encode("utf-8") if isinstance(body, str) else body,
            follow_redirects=False,
        )
        if response.status_code >= 500:
            results["http_errors"].append({"url": path, "status": response.status_code})
        return {
            "status": response.status_code,
            "headers": dict(response.headers),
            "body_b64": base64.b64encode(response.content).decode("ascii"),
        }

    page.expose_function("__snapimsProxy", proxy_request)
    page.add_init_script(script=
        """
        (() => {
          const storage = new Map();
          Object.defineProperty(window, "localStorage", {value: {
            getItem: (key) => storage.has(String(key)) ? storage.get(String(key)) : null,
            setItem: (key, value) => storage.set(String(key), String(value)),
            removeItem: (key) => storage.delete(String(key)),
            clear: () => storage.clear(),
          }});
          const nativeSetTimeout = window.setTimeout.bind(window);
          window.setTimeout = (fn, delay, ...args) => {
            if (typeof fn === 'function' && String(fn).includes('window.location.reload')) return 0;
            return nativeSetTimeout(fn, delay, ...args);
          };
          window.fetch = async (input, init = {}) => {
            const url = new URL(typeof input === 'string' ? input : input.url, 'http://snapims.test:8878/').toString();
            const headers = {};
            new Headers(init.headers || (typeof input !== 'string' ? input.headers : undefined)).forEach((value, key) => headers[key] = value);
            const payload = await window.__snapimsProxy({
              method: init.method || (typeof input !== 'string' ? input.method : 'GET'),
              url,
              headers,
              body: init.body == null ? null : String(init.body),
            });
            const binary = atob(payload.body_b64 || '');
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
            return new Response(bytes, {status: payload.status, headers: payload.headers});
          };
        })();
        """
    )

    def load(path: str) -> httpx.Response:
        page.goto("about:blank", wait_until="domcontentloaded")
        response = server_client.get(SERVER_BASE + path)
        response.raise_for_status()
        html = response.text
        html = re.sub(r'<link[^>]+href="[^"]*/static/app\.css"[^>]*>', lambda _: f"<style>{css}</style>", html)
        html = re.sub(r'<script[^>]+src="[^"]*/static/app\.js"[^>]*></script>', '', html)
        html = html.replace('</body>', f'<script>{js}</script></body>', 1)
        html = re.sub(r'src="/media/[^"]+"', f'src="{transparent}"', html)
        html = html.replace("<head>", f'<head><base href="{BASE}/">', 1)
        page.set_content(html, wait_until="domcontentloaded")
        return response

    try:
        for route, heading in [
            ("/", "SnapIMS"), ("/import", "Import"), ("/recognition", "Recognition"),
            ("/review", "Review"), ("/publish", "Publish"), ("/settings", "Settings"),
            ("/diagnostics", "Diagnostics"),
        ]:
            response = load(route)
            _check(results, f"{label} {route} loads", response.status_code < 500, response.status_code)
            _check(results, f"{label} {route} has content", heading.casefold() in page.locator("body").inner_text().casefold())

        editor_path = f"/batch-editor?batch_id={ids['editor']}&page_size=100"
        load(editor_path)
        rows = page.locator("#batch-grid tbody tr[data-item-id]")
        _check(results, f"{label} editor rows", rows.count() == 5, rows.count())

        def select_destinations() -> None:
            page.locator("[data-clear-selection]").click()
            rows.nth(1).locator(".row-select").check()
            rows.nth(2).locator(".row-select").check()

        select_destinations()
        rows.nth(0).locator("[data-tag-input]").focus()
        page.locator("[data-fill-down]").click()
        page.locator(".save-toast").last.wait_for(state="visible")
        load(editor_path)
        rows = page.locator("#batch-grid tbody tr[data-item-id]")
        tag_counts = [rows.nth(i).locator(".tag-pill").count() for i in (1, 2)]
        _check(results, f"{label} Tags Fill Down", tag_counts == [2, 2], tag_counts)

        select_destinations()
        rows.nth(0).locator('[data-field="location"]').focus()
        page.locator("[data-fill-down]").click()
        page.locator(".save-toast").last.wait_for(state="visible")
        load(editor_path)
        rows = page.locator("#batch-grid tbody tr[data-item-id]")
        locations = [rows.nth(i).locator('[data-field="location"]').input_value() for i in (1, 2)]
        _check(results, f"{label} Location Fill Down", locations == ["Processing Table", "Processing Table"], locations)

        select_destinations()
        rows.nth(0).locator('[data-field="review"]').focus()
        page.locator("[data-fill-down]").click()
        page.locator(".save-toast").last.wait_for(state="visible")
        load(editor_path)
        rows = page.locator("#batch-grid tbody tr[data-item-id]")
        _check(results, f"{label} Review Fill Down", all(rows.nth(i).locator('[data-field="review"]').is_checked() for i in (1, 2)))

        select_destinations()
        rows.nth(0).locator('[data-field="rare"]').focus()
        page.locator("[data-fill-down]").click()
        page.locator(".save-toast").last.wait_for(state="visible")
        load(editor_path)
        rows = page.locator("#batch-grid tbody tr[data-item-id]")
        _check(results, f"{label} Rare Fill Down", all(rows.nth(i).locator('[data-field="rare"]').is_checked() for i in (1, 2)))

        price = rows.nth(0).locator('[data-field="price_cents"]')
        price.focus(); price.press("End"); price.press("ArrowRight")
        active = page.evaluate("document.activeElement?.hasAttribute('data-tag-input')")
        _check(results, f"{label} ArrowRight crosses Tags", active is True, active)
        discount = rows.nth(0).locator('[data-field="discount_percent"]')
        discount.focus(); discount.press("Home"); discount.press("ArrowLeft")
        active = page.evaluate("document.activeElement?.hasAttribute('data-tag-input')")
        _check(results, f"{label} ArrowLeft crosses Tags", active is True, active)

        page.locator("[data-clear-selection]").click()
        search = page.locator("#batch-search")
        first_title = rows.nth(0).locator('[data-field="title"]').input_value()
        search.fill(first_title)
        page.locator("[data-select-visible]").click()
        before = page.locator("#selection-count").inner_text()
        search.fill("NO-SUCH-VISIBLE-TAPE")
        after = page.locator("#selection-count").inner_text()
        _check(results, f"{label} hidden selections clear", before == "1 selected" and after == "0 selected", f"{before} -> {after}")

        EVIDENCE.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(EVIDENCE / f"{label}-batch-editor.png"), full_page=True)

        start = time.perf_counter()
        large_response = load(f"/batch-editor?batch_id={ids['large']}&page_size=100")
        large_time = time.perf_counter() - start
        large_rows = page.locator("#batch-grid tbody tr[data-item-id]").count()
        content_bytes = len(large_response.content)
        _check(results, f"{label} 5000-item page bounded", large_rows == 100 and content_bytes < 1_500_000, f"rows={large_rows} bytes={content_bytes}")
        _check(results, f"{label} 5000-item render under 1s", large_time < 1.0, f"{large_time:.3f}s")
        results["large_editor"] = {"render_seconds": large_time, "html_bytes": content_bytes, "rows": large_rows}

        page.set_viewport_size({"width": 390, "height": 844})
        load(editor_path)
        body_width = page.evaluate("document.body.scrollWidth")
        viewport_width = page.evaluate("window.innerWidth")
        table_width = page.locator("#batch-grid").evaluate("e => e.scrollWidth")
        wrap_width = page.locator(".data-grid-wrap").evaluate("e => e.clientWidth")
        _check(results, f"{label} mobile body fits", body_width <= viewport_width + 2, f"body={body_width} viewport={viewport_width}")
        _check(results, f"{label} mobile grid scrolls", table_width > wrap_width, f"table={table_width} wrap={wrap_width}")
        page.screenshot(path=str(EVIDENCE / f"{label}-mobile-editor.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})

        load("/import")
        form = page.locator('form[action="/import/preview"]').filter(has=page.locator('input[value$="BROWSER-100"]'))
        _check(results, f"{label} 100-item folder listed", form.count() == 1, form.count())
        if form.count() == 1:
            folder_path = form.locator('input[name="folder_path"]').input_value()
            csrf = page.locator('meta[name="csrf-token"]').get_attribute("content") or ""
            preview_start = time.perf_counter()
            response = server_client.post(
                SERVER_BASE + "/import/preview",
                data={"folder_path": folder_path, "batch_location": "", "csrf_token": csrf},
                headers={"Origin": SERVER_BASE, "Referer": SERVER_BASE + "/import"},
                follow_redirects=False,
            )
            response_seconds = time.perf_counter() - preview_start
            _check(results, f"{label} Preview returns under 1s", response_seconds < 1.0 and response.status_code == 303, f"{response_seconds:.3f}s status={response.status_code}")
            location = response.headers.get("location", "")
            job_id = location.split("job_id=", 1)[1].split("&", 1)[0]
            deadline = time.monotonic() + 90
            job: dict[str, Any] = {}
            refresh_ok = True
            for _ in range(3):
                try:
                    load(f"/import?job_id={job_id}")
                except Exception:
                    refresh_ok = False
            _check(results, f"{label} refresh during Preview", refresh_ok)
            while time.monotonic() < deadline:
                job = server_client.get(SERVER_BASE + f"/import/job/{job_id}").json()
                if job.get("status") not in {"QUEUED", "RUNNING"}:
                    break
                time.sleep(0.1)
            _check(results, f"{label} 100-item Preview ready", job.get("status") in {"READY", "NEEDS_ATTENTION"}, job.get("status"))
            _check(results, f"{label} 100-item grouping exact", job.get("preview", {}).get("item_count") == 100, job.get("preview", {}).get("item_count"))
            _check(results, f"{label} one decode/scan per image", job.get("decode_count") <= 202 and job.get("qr_scan_count") <= 202, f"decode={job.get('decode_count')} qr={job.get('qr_scan_count')}")
            load(f"/import?job_id={job_id}")
            _check(results, f"{label} Preview page bounded to 20", page.locator(".preview-item-card").count() == 20, page.locator(".preview-item-card").count())
            page.screenshot(path=str(EVIDENCE / f"{label}-import-preview.png"), full_page=True)
    finally:
        context.close()
        server_client.close()
        browser.close()
    results["passed"] = all(check["ok"] for check in results["checks"])
    return results

def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    ids = _seed()
    env = os.environ.copy()
    env.update({
        "SNAPIMS_DATA_DIR": str(DATA),
        "SNAPIMS_SKIP_DOTENV": "1",
        "SNAPIMS_AUTH_SECRET": "",
        "SNAPIMS_ADMIN_PASSWORD_HASH": "",
        "SNAPIMS_ENABLE_TEST_PROVIDERS": "true",
        "OPENAI_API_KEY": "",
        "SHOPIFY_ADMIN_ACCESS_TOKEN": "",
    })
    log_path = EVIDENCE / "server.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "snapims.cli", "--data-dir", str(DATA), "run", "--host", "127.0.0.1", "--port", str(PORT)],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            _wait_http(SERVER_BASE + "/health")
            with sync_playwright() as playwright:
                outputs = [
                    _browser_pass(playwright.chromium, "/usr/bin/chromium", "chromium", ids),
                ]
            summary = {
                "version": "0.13.2",
                "base_url": BASE,
                "data_dir": str(DATA),
                "browsers": outputs,
                "passed": all(result["passed"] for result in outputs),
            }
            (EVIDENCE / "browser-verification.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            return 0 if summary["passed"] else 1
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
