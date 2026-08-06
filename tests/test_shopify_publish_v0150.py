from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from snapims import db
from snapims.config import ShopifyConfig
from snapims.recognition.service import accept_item
from snapims.shopify.client import ShopifyAPIError
from snapims.shopify.jobs import (
    ShopifyJobError,
    _run_job,
    create_job,
    get_job,
    recover_jobs,
)
from snapims.shopify.service import ShopifyDryRun
from tests.helpers import recognized_batch


class FakePublishService:
    calls: Counter[str] = Counter()
    failures_left = 0

    def __init__(self, db_file: Path, config: ShopifyConfig) -> None:
        self.db_file = db_file
        self.config = config

    def dry_run(self, item_id: str, *, remote_check: bool = False) -> ShopifyDryRun:
        item = db.get_item(self.db_file, item_id)
        assert item is not None
        return ShopifyDryRun(
            item_id=item_id,
            ready=True,
            action="CREATE_DRAFT",
            errors=(),
            warnings=(),
            image_count=1,
            payload={"sku": item["sku"]},
        )

    def upload_draft(self, item_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        self.calls["upload_draft"] += 1
        if self.failures_left:
            type(self).failures_left -= 1
            raise ShopifyAPIError("temporary", status_code=503)
        product_id = f"gid://shopify/Product/{item_id.rsplit('-', 1)[-1]}"
        with db.transaction(self.db_file) as connection:
            connection.execute(
                "UPDATE items SET upload_status='UPLOADED',shopify_product_id=?,shopify_admin_url=? WHERE item_id=?",
                (product_id, f"https://example.myshopify.com/admin/products/{product_id.rsplit('/',1)[-1]}", item_id),
            )
            connection.execute(
                "UPDATE shopify_sync SET status='UPLOADED',product_id=?,product_status='DRAFT',sync_state='IN_SYNC' WHERE item_id=?",
                (product_id, item_id),
            )
        return {"status": "UPLOADED_AS_DRAFT", "product_id": product_id}

    def publish_live(self, item_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        self.calls["publish_live"] += 1
        with db.transaction(self.db_file) as connection:
            connection.execute("UPDATE items SET upload_status='PUBLISHED' WHERE item_id=?", (item_id,))
        return {"status": "PUBLISHED", "product_id": db.get_item(self.db_file, item_id)["shopify_product_id"]}

    def sync_product(self, item_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        self.calls["sync_product"] += 1
        return {"status": "SYNCED"}

    def reconcile_product(self, item_id: str) -> dict[str, Any]:
        self.calls["reconcile_product"] += 1
        return {"status": "IN_SYNC"}

    def archive_product(self, item_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        self.calls["archive_product"] += 1
        with db.transaction(self.db_file) as connection:
            connection.execute("UPDATE items SET upload_status='ARCHIVED' WHERE item_id=?", (item_id,))
        return {"status": "ARCHIVED"}

    def restore_draft(self, item_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        self.calls["restore_draft"] += 1
        with db.transaction(self.db_file) as connection:
            connection.execute("UPDATE items SET upload_status='UPLOADED' WHERE item_id=?", (item_id,))
        return {"status": "DRAFT"}

    def delete_product(self, item_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        self.calls["delete_product"] += 1
        with db.transaction(self.db_file) as connection:
            connection.execute("UPDATE items SET upload_status='DELETED' WHERE item_id=?", (item_id,))
        return {"status": "DELETED"}


def _ready_batch(tmp_path: Path, data_paths, *, count: int = 3) -> tuple[str, list[str]]:
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


@pytest.fixture(autouse=True)
def _reset_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    FakePublishService.calls.clear()
    FakePublishService.failures_left = 0
    config = ShopifyConfig(
        store_domain="example.myshopify.com",
        access_token="token",
        location_id="gid://shopify/Location/1",
        api_version="2026-07",
        draft_only=True,
        publication_id="gid://shopify/Publication/1",
    )
    monkeypatch.setattr("snapims.shopify.jobs.ShopifyConfig.from_env", lambda: config)


def test_create_drafts_job_runs_all_items_and_persists_progress(tmp_path: Path, data_paths) -> None:
    batch_id, item_ids = _ready_batch(tmp_path, data_paths)
    job_id = create_job(
        data_paths,
        batch_id=batch_id,
        action="CREATE_DRAFTS",
        selection_scope="ALL",
        service_factory=FakePublishService,
        start=False,
    )
    _run_job(data_paths, job_id, FakePublishService)
    job = get_job(data_paths.db_file, job_id)
    assert job is not None
    assert job["status"] == "COMPLETE"
    assert job["completed"] == len(item_ids)
    assert job["succeeded"] == len(item_ids)
    assert job["progress_percent"] == 100
    assert FakePublishService.calls["upload_draft"] == len(item_ids)


def test_live_and_direct_publish_require_exact_confirmation(tmp_path: Path, data_paths) -> None:
    batch_id, item_ids = _ready_batch(tmp_path, data_paths, count=1)
    with pytest.raises(ShopifyJobError, match="SUBMIT exactly"):
        create_job(
            data_paths,
            batch_id=batch_id,
            action="PUBLISH_LIVE",
            item_ids=item_ids,
            confirmation="submit",
            service_factory=FakePublishService,
            start=False,
        )
    with pytest.raises(ShopifyJobError, match="SUBMIT LIVE exactly"):
        create_job(
            data_paths,
            batch_id=batch_id,
            action="DIRECT_PUBLISH",
            item_ids=item_ids,
            confirmation="SUBMIT",
            service_factory=FakePublishService,
            start=False,
        )


def test_direct_publish_creates_draft_then_publishes(tmp_path: Path, data_paths) -> None:
    batch_id, item_ids = _ready_batch(tmp_path, data_paths, count=1)
    job_id = create_job(
        data_paths,
        batch_id=batch_id,
        action="DIRECT_PUBLISH",
        item_ids=item_ids,
        confirmation="SUBMIT LIVE",
        service_factory=FakePublishService,
        start=False,
    )
    _run_job(data_paths, job_id, FakePublishService)
    job = get_job(data_paths.db_file, job_id)
    assert job and job["status"] == "COMPLETE"
    assert FakePublishService.calls["upload_draft"] == 1
    assert FakePublishService.calls["publish_live"] == 1
    assert db.get_item(data_paths.db_file, item_ids[0])["upload_status"] == "PUBLISHED"


def test_transient_failure_retries_but_does_not_loop_forever(tmp_path: Path, data_paths) -> None:
    batch_id, item_ids = _ready_batch(tmp_path, data_paths, count=1)
    FakePublishService.failures_left = 2
    job_id = create_job(
        data_paths,
        batch_id=batch_id,
        action="CREATE_DRAFTS",
        item_ids=item_ids,
        service_factory=FakePublishService,
        start=False,
    )
    _run_job(data_paths, job_id, FakePublishService)
    job = get_job(data_paths.db_file, job_id)
    assert job and job["status"] == "COMPLETE"
    assert FakePublishService.calls["upload_draft"] == 3
    assert job["items"][0]["attempt_count"] == 1


def test_recovery_requeues_interrupted_job_without_reprocessing_success(tmp_path: Path, data_paths) -> None:
    batch_id, item_ids = _ready_batch(tmp_path, data_paths, count=2)
    job_id = create_job(
        data_paths,
        batch_id=batch_id,
        action="CREATE_DRAFTS",
        selection_scope="ALL",
        service_factory=FakePublishService,
        start=False,
    )
    with db.transaction(data_paths.db_file) as connection:
        connection.execute("UPDATE shopify_publish_jobs SET status='RUNNING' WHERE job_id=?", (job_id,))
        connection.execute(
            "UPDATE shopify_publish_job_items SET status='SUCCESS' WHERE job_id=? AND item_id=?",
            (job_id, item_ids[0]),
        )
        connection.execute(
            "UPDATE shopify_publish_job_items SET status='RUNNING' WHERE job_id=? AND item_id=?",
            (job_id, item_ids[1]),
        )
    assert recover_jobs(data_paths, start_workers=False) == 1
    job = get_job(data_paths.db_file, job_id)
    assert job and job["status"] == "QUEUED"
    states = {row["item_id"]: row["status"] for row in job["items"]}
    assert states[item_ids[0]] == "SUCCESS"
    assert states[item_ids[1]] == "QUEUED"


def test_duplicate_active_job_is_rejected(tmp_path: Path, data_paths) -> None:
    batch_id, item_ids = _ready_batch(tmp_path, data_paths, count=1)
    create_job(
        data_paths,
        batch_id=batch_id,
        action="CREATE_DRAFTS",
        item_ids=item_ids,
        service_factory=FakePublishService,
        start=False,
    )
    with pytest.raises(ShopifyJobError, match="already active"):
        create_job(
            data_paths,
            batch_id=batch_id,
            action="CREATE_DRAFTS",
            item_ids=item_ids,
            service_factory=FakePublishService,
            start=False,
        )
