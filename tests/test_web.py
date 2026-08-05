from __future__ import annotations

from io import BytesIO
import time
import shutil
from pathlib import Path
import zipfile

import qrcode
from PIL import Image
from fastapi.testclient import TestClient

from snapims import db
from snapims.demo import create_demo_batch
from snapims.observability import emit_event
from snapims.import_v0130 import get_job
from snapims.web.app import app


def test_pages_render(data_paths) -> None:
    with TestClient(app) as client:
        for path in ["/", "/import", "/review", "/publish", "/settings", "/diagnostics"]:
            response = client.get(path)
            assert response.status_code == 200
            assert "SnapIMS" in response.text


def test_live_activity_survives_restart_and_support_bundle_is_redacted(
    data_paths, monkeypatch
) -> None:
    secret = "web-support-secret"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    with TestClient(app) as client:
        event_id = emit_event(
            data_paths.db_file,
            component="recognition",
            event_type="recognition.fixture",
            operation_id="OP-LIVE",
            safe_summary=f"provider token={secret}",
            detail={"authorization": f"Bearer {secret}"},
            known_secrets=[secret],
            paths=data_paths,
        )
        page = client.get("/diagnostics")
        assert page.status_code == 200
        assert "LIVE ACTIVITY" in page.text
        assert "recognition.fixture" in page.text
        assert "OP-LIVE" in page.text
        api = client.get("/api/diagnostics/events", params={"after": event_id - 1})
        assert api.status_code == 200
        assert api.json()["events"][-1]["event_id"] == event_id
        bundle = client.post("/diagnostics/support-bundle")
        assert bundle.status_code == 200
        assert bundle.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(BytesIO(bundle.content)) as archive:
            rendered = b"\n".join(archive.read(name) for name in archive.namelist())
        assert secret.encode() not in rendered
    with TestClient(app) as restarted:
        page = restarted.get("/diagnostics", params={"activity_operation": "OP-LIVE"})
        assert page.status_code == 200
        assert "recognition.fixture" in page.text
        assert "OP-LIVE" in page.text


def _wait_import(data_paths, job_id: str, terminal: set[str]) -> dict:
    deadline = time.time() + 15
    while time.time() < deadline:
        job = get_job(data_paths.db_file, job_id)
        assert job is not None
        if job["status"] in terminal:
            return job
        time.sleep(0.02)
    raise AssertionError(f"Import job timed out: {get_job(data_paths.db_file, job_id)}")


def _folder_demo(tmp_path: Path, data_paths, name: str) -> Path:
    destination = data_paths.batches / name
    destination.mkdir(parents=True, exist_ok=True)
    def product(filename: str) -> None:
        Image.new("RGB", (1200, 900), (80, 100, 120)).save(destination / filename, quality=88)
    product("001.jpg")
    product("002.jpg")
    code = qrcode.make("CVHS1:ITEM:NEXT").convert("RGB").resize((620, 620))
    command = Image.new("RGB", (1200, 900), "white")
    command.paste(code, (290, 140))
    command.save(destination / "003.jpg", quality=92)
    product("004.jpg")
    product("005.jpg")
    return destination


def test_preview_has_non_durable_identity_and_import_has_one_id(tmp_path: Path, data_paths) -> None:
    source = _folder_demo(tmp_path, data_paths, "COMEDY")
    with TestClient(app) as client:
        started = client.post(
            "/import/preview",
            data={"folder_path": str(source), "batch_location": "Q1"},
            follow_redirects=False,
        )
        assert started.status_code == 303
        job_id = started.headers["location"].split("job_id=")[1]
        preview_job = _wait_import(data_paths, job_id, {"READY", "NEEDS_ATTENTION", "FAILED"})
        assert preview_job["status"] == "READY"
        assert preview_job["result_batch_id"] == ""
        assert preview_job["preview"]["item_count"] == 2
        assert preview_job["preview"]["product_photo_count"] == 4
        page = client.get(f"/import?job_id={job_id}")
        assert "PREVIEW · NOT YET IMPORTED" in page.text
        committed = client.post("/import/commit", data={"job_id": job_id}, follow_redirects=False)
        assert committed.status_code == 303
        imported_job = _wait_import(data_paths, job_id, {"IMPORTED", "FAILED", "NEEDS_ATTENTION"})
        assert imported_job["status"] == "IMPORTED"
        batches = db.list_batches(data_paths.db_file)
        assert len(batches) == 1
        assert batches[0]["batch_id"] == imported_job["result_batch_id"]


def test_review_fast_path_by_http(tmp_path: Path, data_paths) -> None:
    source = _folder_demo(tmp_path, data_paths, "FAST")
    with TestClient(app) as client:
        started = client.post(
            "/import/preview",
            data={"folder_path": str(source), "batch_location": "Q1"},
            follow_redirects=False,
        )
        job_id = started.headers["location"].split("job_id=")[1]
        assert _wait_import(data_paths, job_id, {"READY", "FAILED"})["status"] == "READY"
        client.post("/import/commit", data={"job_id": job_id}, follow_redirects=False)
        imported = _wait_import(data_paths, job_id, {"IMPORTED", "FAILED", "NEEDS_ATTENTION"})
        assert imported["status"] == "IMPORTED"
        batch_id = imported["result_batch_id"]
        client.post("/review/identify", data={"batch_id": batch_id, "provider": "mock"})
        deadline = time.time() + 5
        while time.time() < deadline and db.get_recognition_job(data_paths.db_file, batch_id)["status"] in {"RUNNING", "IDENTIFYING"}:
            time.sleep(0.02)
        item = db.list_items(data_paths.db_file, batch_id=batch_id)[0]
        response = client.post(
            "/review/approve",
            data={
                "batch_id": batch_id,
                "item_id": item["item_id"],
                "price": "12.99",
                "discount": "5",
                "revision": str(item["record_revision"]),
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        saved = db.get_item(data_paths.db_file, item["item_id"])
        assert saved["review_status"] == "DONE"
        assert saved["price_cents"] == 1299
        assert saved["discount_percent"] == 5

