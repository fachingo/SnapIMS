from __future__ import annotations

import time
from pathlib import Path

from snapims import db
from snapims.demo import create_demo_batch
from snapims.processor import process_batch
from snapims.recognition.service import accept_item, postpone_item, start_batch_recognition


def wait_for_job(db_file: Path, batch_id: str) -> dict:
    deadline = time.time() + 5
    while time.time() < deadline:
        job = db.get_recognition_job(db_file, batch_id)
        if job and job["status"] in {"COMPLETE", "COMPLETE_WITH_FAILURE"}:
            return job
        time.sleep(0.02)
    raise AssertionError("recognition did not finish")


def prepared(tmp_path: Path, data_paths):
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    start_batch_recognition(data_paths.db_file, result.batch_id, "mock")
    wait_for_job(data_paths.db_file, result.batch_id)
    return result


def test_fast_approval_accepts_suggestion_and_quick_edits(tmp_path: Path, data_paths) -> None:
    result = prepared(tmp_path, data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    errors = accept_item(data_paths.db_file, item["item_id"], price_cents=1849, discount_percent=10)
    assert errors == []
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert saved["title"] == "Demo VHS 001"
    assert saved["price_cents"] == 1849
    assert saved["discount_percent"] == 10
    assert saved["review_status"] == "DONE"
    assert saved["validation_status"] == "READY"


def test_manual_value_precedence_survives_approval(tmp_path: Path, data_paths) -> None:
    result = prepared(tmp_path, data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    db.update_item(data_paths.db_file, item["item_id"], {"title": "Manual title", "price_cents": 1299})
    assert accept_item(data_paths.db_file, item["item_id"], price_cents=None, discount_percent=0) == []
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert saved["title"] == "Manual title"
    assert saved["price_cents"] == 1299


def test_invalid_approval_returns_blocker(tmp_path: Path, data_paths) -> None:
    result = prepared(tmp_path, data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    errors = accept_item(data_paths.db_file, item["item_id"], price_cents=0, discount_percent=0)
    assert "Price must be greater than zero" in errors
    assert db.get_item(data_paths.db_file, item["item_id"])["review_status"] == "UNFINISHED"


def test_later_preserves_unfinished(tmp_path: Path, data_paths) -> None:
    result = prepared(tmp_path, data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    postpone_item(data_paths.db_file, item["item_id"])
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert saved["review_status"] == "UNFINISHED"
    assert saved["postponed_at"]


def test_running_job_becomes_paused_after_restart_marker(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera", item_count=3), paths=data_paths)
    db.upsert_recognition_job(data_paths.db_file, result.batch_id, status="RUNNING", total=3, completed=1, recognized=1, failed=0)
    assert db.mark_interrupted_jobs_paused(data_paths.db_file) == 1
    assert db.get_recognition_job(data_paths.db_file, result.batch_id)["status"] == "PAUSED"
