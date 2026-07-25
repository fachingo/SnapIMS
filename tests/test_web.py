from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from snapims import db
from snapims.demo import create_demo_batch
from snapims.web.app import app


def test_pages_render(data_paths) -> None:
    with TestClient(app) as client:
        for path in ["/", "/import", "/review", "/publish", "/settings", "/diagnostics"]:
            response = client.get(path)
            assert response.status_code == 200
            assert "SnapIMS" in response.text


def test_preview_has_non_durable_identity_and_import_has_one_id(tmp_path: Path, data_paths) -> None:
    source = create_demo_batch(tmp_path / "camera")
    with TestClient(app) as client:
        preview = client.post("/import/preview", data={"source_folder": str(source), "batch_name": "COMEDY"})
        assert preview.status_code == 200
        assert "PREVIEW · NOT IMPORTED YET" in preview.text
        assert "<b>2</b><span>Items</span>" in preview.text, preview.text
        assert "<b>4</b><span>Product photos</span>" in preview.text
        imported = client.post("/import/commit", data={"source_folder": str(source), "batch_name": "COMEDY"})
        assert imported.status_code == 200
        assert "IMPORTED BATCH" in imported.text
        batches = db.list_batches(data_paths.db_file)
        assert len(batches) == 1
        assert batches[0]["batch_id"] in imported.text


def test_review_fast_path_by_http(tmp_path: Path, data_paths) -> None:
    source = create_demo_batch(tmp_path / "camera")
    with TestClient(app) as client:
        client.post("/import/commit", data={"source_folder": str(source), "batch_name": "FAST"})
        batch_id = db.list_batches(data_paths.db_file)[0]["batch_id"]
        client.post("/review/identify", data={"batch_id": batch_id, "provider": "mock"})
        deadline = time.time() + 5
        while time.time() < deadline and db.get_recognition_job(data_paths.db_file, batch_id)["status"] in {"RUNNING", "IDENTIFYING"}:
            time.sleep(0.02)
        item = db.list_items(data_paths.db_file, batch_id=batch_id)[0]
        response = client.post("/review/approve", data={"batch_id": batch_id, "item_id": item["item_id"], "price": "12.99", "discount": "5"}, follow_redirects=False)
        assert response.status_code == 303
        saved = db.get_item(data_paths.db_file, item["item_id"])
        assert saved["review_status"] == "DONE"
        assert saved["price_cents"] == 1299
        assert saved["discount_percent"] == 5
