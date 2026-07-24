#!/usr/bin/env python3
"""Rendered-control browser audit for SnapIMS v0.5.0.

The execution environment blocks Chromium loopback HTTP navigation. This harness
therefore renders the exact FastAPI/Jinja responses in local Chromium, performs
operator interactions against visible controls, and submits the captured forms
through FastAPI's in-process TestClient. Database and application code are not
used as substitutes for the operator controls during the measured fast path.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "operator-audit-assets" / "v0.5-browser"
SHOTS = AUDIT / "screenshots"
WORK = Path("/tmp/snapims-v05-browser-final")
CAMERAS = Path("/tmp/snapims-v05-camera-fixtures")

os.environ["SNAPIMS_DATA_DIR"] = str(WORK)

from fastapi.testclient import TestClient  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from snapims import db  # noqa: E402
from snapims.config import DataPaths  # noqa: E402
from snapims.demo import create_demo_batch  # noqa: E402
from snapims.inventory import export_inventory_csv  # noqa: E402
from snapims.processor import process_batch  # noqa: E402
from snapims.web.app import app  # noqa: E402

CSS = (ROOT / "snapims" / "web" / "static" / "app.css").read_text(encoding="utf-8")
INTERCEPT = """
<script>
window.__submitted = null;
document.addEventListener('submit', function(event) {
  event.preventDefault();
  const form = event.target;
  const data = {};
  for (const [key, value] of new FormData(form).entries()) data[key] = value;
  window.__submitted = {action: form.getAttribute('action') || location.pathname,
                        method: (form.getAttribute('method') || 'get').toLowerCase(), data};
});
</script>
"""


def wait_job(paths: DataPaths, batch_id: str, timeout: float = 15) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = db.get_recognition_job(paths.db_file, batch_id)
        if job and job["status"] in {"COMPLETE", "COMPLETE_WITH_FAILURE", "REVIEW_COMPLETE"}:
            return job
        time.sleep(0.02)
    raise RuntimeError(f"Recognition did not finish for {batch_id}")


def response_html(client: TestClient, response) -> str:
    html = response.text
    html = re.sub(r'<link rel="stylesheet"[^>]+>', f"<style>{CSS}</style>", html)
    html = re.sub(r'<script defer[^>]+></script>', "", html)
    photo_ids = sorted({int(value) for value in re.findall(r'/media/(\d+)', html)})
    for photo_id in photo_ids:
        media = client.get(f"/media/{photo_id}")
        encoded = base64.b64encode(media.content).decode("ascii")
        html = html.replace(f'/media/{photo_id}', f'data:image/jpeg;base64,{encoded}')
    return html.replace("</head>", INTERCEPT + "</head>")


def render(page, client: TestClient, response, name: str | None = None):
    page.set_content(response_html(client, response), wait_until="load")
    if name:
        page.screenshot(path=str(SHOTS / name), full_page=True)
    return response


def submit_visible(page, client: TestClient, button_selector: str, *, follow: bool = True):
    page.click(button_selector)
    payload = page.evaluate("window.__submitted")
    if not payload:
        raise RuntimeError(f"No form submission captured from {button_selector}")
    response = client.request(payload["method"], payload["action"], data=payload["data"], follow_redirects=False)
    if follow and response.status_code in {301, 302, 303, 307, 308}:
        response = client.get(response.headers["location"])
    return response


def contact_sheet() -> None:
    from PIL import Image, ImageDraw

    files = sorted(SHOTS.glob("*.png"))
    thumbs = []
    for path in files:
        image = Image.open(path).convert("RGB")
        image.thumbnail((340, 240))
        card = Image.new("RGB", (360, 275), "white")
        card.paste(image, ((360 - image.width) // 2, 25 + (240 - image.height) // 2))
        ImageDraw.Draw(card).text((8, 6), path.name, fill="black")
        thumbs.append(card)
    columns = 3
    rows = (len(thumbs) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * 360, rows * 275), (220, 220, 220))
    for index, card in enumerate(thumbs):
        sheet.paste(card, ((index % columns) * 360, (index // columns) * 275))
    sheet.save(AUDIT / "contact-sheet.png")


def main() -> None:
    shutil.rmtree(WORK, ignore_errors=True)
    shutil.rmtree(CAMERAS, ignore_errors=True)
    shutil.rmtree(SHOTS, ignore_errors=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    paths = DataPaths.from_root(WORK).ensure()
    main_camera = create_demo_batch(CAMERAS / "main-20", item_count=20)

    metrics: list[dict] = []
    clicks = 0
    one_click = 0

    with sync_playwright() as playwright:
        chromium = os.getenv("SNAPIMS_CHROMIUM") or shutil.which("chromium")
        launch_options = {"headless": True, "args": ["--no-sandbox"]}
        if chromium:
            launch_options["executable_path"] = chromium
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        with TestClient(app) as client:
            render(page, client, client.get("/"), "00-home.png")
            render(page, client, client.get("/import"), "01-first-run-import.png")
            preview = client.post("/import/preview", data={"source_folder": str(main_camera), "batch_name": "V050-PILOT"})
            render(page, client, preview, "02-preview-not-imported.png")
            assert page.locator("text=20").count() > 0
            imported = client.post("/import/commit", data={"source_folder": str(main_camera), "batch_name": "V050-PILOT"})
            render(page, client, imported, "03-imported-durable-id.png")
            batch_id = db.list_batches(paths.db_file)[0]["batch_id"]
            review = client.get(f"/review?batch_id={batch_id}")
            render(page, client, review, "04-review-ready-to-identify.png")
            submit_visible(page, client, "form[action='/review/identify'] button")
            wait_job(paths, batch_id)
            review = client.get(f"/review?batch_id={batch_id}")
            render(page, client, review, "05-recognition-complete.png")

            for number in range(1, 21):
                item = db.list_items(paths.db_file, batch_id=batch_id, queue="UNRESOLVED")[0]
                response = client.get(f"/review?batch_id={batch_id}&queue=UNRESOLVED&item_id={item['item_id']}")
                render(page, client, response)
                item_clicks = 1
                if number == 18:
                    page.click("input[name='price']")
                    page.fill("input[name='price']", "18.49")
                    item_clicks += 1
                    page.screenshot(path=str(SHOTS / "06-price-quick-edit.png"), full_page=True)
                elif number == 19:
                    page.click("input[name='discount']")
                    page.fill("input[name='discount']", "10")
                    item_clicks += 1
                    page.screenshot(path=str(SHOTS / "07-discount-quick-edit.png"), full_page=True)
                elif number == 20:
                    page.click("input[name='price']")
                    page.fill("input[name='price']", "21.99")
                    page.click("input[name='discount']")
                    page.fill("input[name='discount']", "15")
                    item_clicks += 2
                    page.screenshot(path=str(SHOTS / "08-price-discount-quick-edit.png"), full_page=True)
                started = time.perf_counter()
                next_response = submit_visible(page, client, "form.quick-approve button.approve")
                render(page, client, next_response)
                elapsed = time.perf_counter() - started
                clicks += item_clicks
                one_click += int(item_clicks == 1)
                metrics.append({"physical_item": number, "clicks": item_clicks, "rendered_cycle_seconds": round(elapsed, 4)})
                if number == 1:
                    page.screenshot(path=str(SHOTS / "09-next-item-opened.png"), full_page=True)
            page.screenshot(path=str(SHOTS / "10-review-complete.png"), full_page=True)

            publish = client.get(f"/publish?batch_id={batch_id}&simulate=true")
            render(page, client, publish, "11-publish-simulation.png")
            export_inventory_csv(paths.db_file, batch_id, AUDIT / "inventory_work-v0.5-browser.csv")

            first = db.list_items(paths.db_file, batch_id=batch_id)[0]
            edit = client.get(f"/review?batch_id={batch_id}&queue=DONE&item_id={first['item_id']}&edit=true")
            render(page, client, edit)
            save_data = {
                "batch_id": batch_id, "item_id": first["item_id"], "queue": "DONE",
                "title": "VHS 001 — Corrected in v0.5", "release_year": "1992", "barcode": "012345678905",
                "distributor": "Demo Distributor", "edition": "Standard VHS", "price": "18.49", "discount": "5",
                "quantity": "1", "condition": "Very Good", "shelf": first["shelf"], "location_reason": "",
                "vendor": "Canada VHS", "product_type": "VHS Tape", "tags": "corrected, pilot",
                "condition_notes": "Corrected after sleeve inspection.", "description": "Corrected browser audit record.",
                "pool_mode": "POOLED", "revision": str(first["record_revision"]),
            }
            saved = client.post("/review/save", data=save_data, follow_redirects=False)
            saved_page = client.get(saved.headers["location"])
            render(page, client, saved_page, "12-completed-item-corrected.png")

            current = db.get_item(paths.db_file, first["item_id"])
            bad = {**save_data, "title": "", "price": "0", "revision": str(current["record_revision"])}
            invalid = client.post("/review/save", data=bad, follow_redirects=False)
            invalid_page = client.get(invalid.headers["location"])
            render(page, client, invalid_page, "13-invalid-edit-blocked.png")

        # New app lifespan proves restart durability and pauses orphaned RUNNING jobs.
        with TestClient(app) as client:
            durable = client.get(f"/review?batch_id={batch_id}&queue=DONE&item_id={first['item_id']}")
            render(page, client, durable, "14-restart-durable-correction.png")

            db.set_setting(paths.db_file, "incoming_folder", str(CAMERAS / "missing-folder"))
            render(page, client, client.get("/import"), "15-missing-folder-recovery.png")

            later_camera = create_demo_batch(CAMERAS / "later-2", item_count=2, shelf="A2")
            later_result = process_batch(later_camera, paths=paths, batch_name="LATER")
            client.post("/review/identify", data={"batch_id": later_result.batch_id, "provider": "mock"})
            wait_job(paths, later_result.batch_id)
            later_item = db.list_items(paths.db_file, batch_id=later_result.batch_id)[0]
            later_response = client.post("/review/later", data={"batch_id": later_result.batch_id, "item_id": later_item["item_id"]}, follow_redirects=False)
            render(page, client, client.get(later_response.headers["location"]), "16-later-preserves-unfinished.png")

            paused_camera = create_demo_batch(CAMERAS / "paused-20", item_count=20, shelf="A3")
            paused_result = process_batch(paused_camera, paths=paths, batch_name="PAUSED")
            db.upsert_recognition_job(paths.db_file, paused_result.batch_id, provider="mock", status="RUNNING", total=20, completed=6, recognized=6, failed=0, current_item_id=db.list_items(paths.db_file, batch_id=paused_result.batch_id)[5]["item_id"], started_at=db.now())
        with TestClient(app) as client:
            paused = client.get(f"/review?batch_id={paused_result.batch_id}")
            render(page, client, paused, "17-recognition-paused-after-restart.png")

            failure_camera = create_demo_batch(CAMERAS / "failure-1", item_count=1)
            failure_result = process_batch(failure_camera, paths=paths, batch_name="FAILURE")
            client.post("/review/identify", data={"batch_id": failure_result.batch_id, "provider": "gemini"})
            wait_job(paths, failure_result.batch_id)
            failed = client.get(f"/review?batch_id={failure_result.batch_id}&queue=FAILED")
            render(page, client, failed, "18-recognition-failure.png")
            failed_item = db.list_items(paths.db_file, batch_id=failure_result.batch_id)[0]
            retry = client.post("/review/retry", data={"batch_id": failure_result.batch_id, "item_id": failed_item["item_id"], "provider": "mock"}, follow_redirects=False)
            render(page, client, client.get(retry.headers["location"]), "19-recognition-failure-recovered.png")
            render(page, client, client.get("/settings"), "20-settings.png")
            render(page, client, client.get("/diagnostics"), "21-diagnostics.png")
        browser.close()

    total_time = sum(row["rendered_cycle_seconds"] for row in metrics)
    output = {
        "version": "0.5.0",
        "viewport": "1440x1000",
        "correctly_recognized_tapes": 20,
        "total_clicks": clicks,
        "average_clicks_per_tape": round(clicks / 20, 2),
        "one_click_tapes": one_click,
        "one_click_percent": round(one_click / 20 * 100, 1),
        "total_rendered_interaction_seconds": round(total_time, 3),
        "average_rendered_cycle_seconds": round(total_time / 20, 3),
        "timing_boundary": "Visible approval click through the next rendered workstation; excludes human photo inspection.",
        "transport_boundary": "Chromium-rendered FastAPI/Jinja responses with visible form interaction; form submissions use in-process TestClient because loopback HTTP navigation is blocked by the execution environment.",
        "items": metrics,
    }
    AUDIT.mkdir(parents=True, exist_ok=True)
    (AUDIT / "browser-metrics.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    contact_sheet()
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
