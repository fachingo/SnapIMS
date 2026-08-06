from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapims import db
from snapims.config import ShopifyConfig
from snapims.recognition.service import accept_item
from snapims.web.app import app
from tests.helpers import recognized_batch


def _batch(tmp_path: Path, data_paths, count: int = 2) -> tuple[str, list[str]]:
    result = recognized_batch(tmp_path, data_paths, item_count=count)
    item_ids: list[str] = []
    for item in db.list_items(data_paths.db_file, batch_id=result.batch_id):
        assert accept_item(
            data_paths.db_file,
            item["item_id"],
            price_cents=1299,
            discount_percent=0,
        ) == []
        db.update_item(
            data_paths.db_file,
            item["item_id"],
            {"working_source": "INDIVIDUAL_REVIEW", "review_source": "INDIVIDUAL_REVIEW"},
            source="INDIVIDUAL_REVIEW",
        )
        item_ids.append(item["item_id"])
    return result.batch_id, item_ids


def _config() -> ShopifyConfig:
    return ShopifyConfig(
        store_domain="example.myshopify.com",
        access_token="token",
        location_id="gid://shopify/Location/1",
        api_version="2026-07",
        draft_only=True,
        publication_id="gid://shopify/Publication/1",
    )


def test_publish_page_exposes_complete_draft_live_and_management_workflow(
    tmp_path: Path, data_paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    batch_id, _ = _batch(tmp_path, data_paths)
    monkeypatch.setattr("snapims.web.app.ShopifyConfig.from_env", _config)
    with TestClient(app) as client:
        response = client.get(f"/publish?batch_id={batch_id}&simulate=true")
    assert response.status_code == 200
    for expected in (
        "Run Shopify simulation",
        "Create Shopify Drafts",
        "Open Shopify Drafts",
        "Publish Drafts Live",
        "SUBMIT",
        "SUBMIT LIVE",
        "Keep Shopify — overwrite local working values",
        "Merge non-conflicting values",
        "Delete permanently from Shopify",
        "DUPLICATE BATCH",
        "DELETE BATCH",
    ):
        assert expected in response.text
    assert "Shopify simulation" in response.text
    assert "PASSED" in response.text


def test_publish_job_endpoint_returns_pollable_job_redirect(
    tmp_path: Path, data_paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    batch_id, item_ids = _batch(tmp_path, data_paths, count=1)
    captured: dict[str, object] = {}

    def fake_create(paths, **kwargs):
        captured.update(kwargs)
        return "job-123"

    monkeypatch.setattr("snapims.web.app.create_shopify_job", fake_create)
    with TestClient(app) as client:
        response = client.post(
            "/publish/jobs",
            headers={"X-Requested-With": "fetch"},
            data={
                "batch_id": batch_id,
                "action": "CREATE_DRAFTS",
                "selection_scope": "SELECTED",
                "item_id": item_ids[0],
            },
        )
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "job_id": "job-123",
        "redirect": f"/publish?batch_id={batch_id}&job_id=job-123",
    }
    assert captured["action"] == "CREATE_DRAFTS"
    assert captured["item_ids"] == [item_ids[0]]


def test_duplicate_batch_clears_shopify_identity_and_preserves_source(
    tmp_path: Path, data_paths
) -> None:
    batch_id, item_ids = _batch(tmp_path, data_paths, count=1)
    with db.transaction(data_paths.db_file) as connection:
        connection.execute(
            "UPDATE items SET upload_status='PUBLISHED',shopify_product_id='gid://shopify/Product/1' WHERE item_id=?",
            (item_ids[0],),
        )
    with TestClient(app) as client:
        response = client.post(
            "/publish/batch/duplicate",
            data={"batch_id": batch_id, "confirmation": "DUPLICATE BATCH"},
        )
    assert response.status_code == 200
    copies = [row for row in db.list_batches(data_paths.db_file) if row["source_batch_id"] == batch_id]
    assert len(copies) == 1
    copied = db.list_items(data_paths.db_file, batch_id=copies[0]["batch_id"])
    assert len(copied) == 1
    assert copied[0]["shopify_product_id"] == ""
    assert copied[0]["upload_status"] == "NOT_UPLOADED"
    assert copied[0]["sku"] != db.get_item(data_paths.db_file, item_ids[0])["sku"]


def test_local_batch_delete_is_recoverable_soft_delete(tmp_path: Path, data_paths) -> None:
    batch_id, _ = _batch(tmp_path, data_paths, count=1)
    with TestClient(app) as client:
        deleted = client.post(
            "/publish/batch/delete",
            data={"batch_id": batch_id, "confirmation": "DELETE BATCH"},
        )
        assert deleted.status_code == 200
        assert db.get_batch(data_paths.db_file, batch_id)["status"] == "DELETED"
        restored = client.post("/publish/batch/restore", data={"batch_id": batch_id})
        assert restored.status_code == 200
    assert db.get_batch(data_paths.db_file, batch_id)["status"] == "IMPORTED"
