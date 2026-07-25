from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from fastapi.testclient import TestClient

from snapims import db
from snapims.demo import create_demo_batch
from snapims.inventory import apply_staged_csv, mark_batch_externally_reviewed, preview_inventory_csv
from snapims.processor import process_batch
from snapims.recognition.service import start_batch_recognition
from snapims.web.app import app


def test_empty_folder_submission_returns_operator_error(data_paths) -> None:
    with TestClient(app) as client:
        response = client.post("/import/use-folder", data={}, follow_redirects=True)
    assert response.status_code == 200
    assert "No source folder selected." in response.text
    assert '"detail"' not in response.text


def test_native_folder_picker_cancel_is_recoverable(data_paths, monkeypatch) -> None:
    monkeypatch.setenv("SNAPIMS_TEST_FOLDER_PICKER", "")
    with TestClient(app) as client:
        response = client.post("/import/browse", data={"current_folder": ""}, follow_redirects=True)
    assert response.status_code == 200
    assert "Folder selection cancelled." in response.text


def test_recognition_job_started_at_none_is_safely_defaulted(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    with db.transaction(data_paths.db_file) as connection:
        connection.execute("DELETE FROM recognition_jobs WHERE batch_id=?", (result.batch_id,))
    db.upsert_recognition_job(data_paths.db_file, result.batch_id, provider="mock", started_at=None)
    job = db.get_recognition_job(data_paths.db_file, result.batch_id)
    assert job is not None
    assert job["started_at"]
    db.upsert_recognition_job(data_paths.db_file, result.batch_id, started_at=None, status="PAUSED")
    updated = db.get_recognition_job(data_paths.db_file, result.batch_id)
    assert updated["started_at"] == job["started_at"]
    assert updated["status"] == "PAUSED"


def test_missing_openai_key_creates_durable_failure(tmp_path: Path, data_paths, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    assert start_batch_recognition(data_paths.db_file, result.batch_id, "openai") is False
    job = db.get_recognition_job(data_paths.db_file, result.batch_id)
    assert job["status"] == "BLOCKED"
    assert job["error_code"] == "API_KEY_MISSING"
    assert "API key" in job["error_message"]


def test_review_failure_screen_has_real_recovery_actions(tmp_path: Path, data_paths, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    start_batch_recognition(data_paths.db_file, result.batch_id, "openai")
    with TestClient(app) as client:
        response = client.get(f"/review?batch_id={result.batch_id}")
    assert "RECOGNITION BLOCKED" in response.text
    assert "Continue With Manual Review" in response.text
    assert "Retry Failed Items Only" not in response.text
    assert "Open Diagnostics" in response.text
    assert "OPENAI_API_KEY" in response.text or "API key" in response.text


def test_media_derivatives_are_persisted_and_measured(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    photo = db.get_item_photos(data_paths.db_file, item["item_id"])[0]
    assert Path(photo["original_copy_path"]).is_file()
    assert Path(photo["preview_path"]).is_file()
    assert Path(photo["recognition_path"]).is_file()
    assert int(photo["original_bytes"]) > 0
    assert int(photo["preview_bytes"]) > 0
    assert int(photo["recognition_bytes"]) > 0


def _edited_csv(db_file: Path, batch_id: str, item_id: str, title: str, price: str) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["Item ID", "Batch ID", "Title", "Price"])
    writer.writeheader()
    writer.writerow({"Item ID": item_id, "Batch ID": batch_id, "Title": title, "Price": price})
    return output.getvalue()


def test_csv_diff_preview_and_apply_updates_authoritative_batch(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera", item_count=1), paths=data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    text = _edited_csv(data_paths.db_file, result.batch_id, item["item_id"], "Edited Tape", "4.00")
    rows, summary, errors = preview_inventory_csv(data_paths.db_file, result.batch_id, text)
    assert errors == []
    assert summary["changed"] == 1
    assert summary["field_counts"]["Title"] == 1
    assert summary["field_counts"]["Price"] == 1
    db.save_csv_staging(
        data_paths.db_file,
        token="token",
        batch_id=result.batch_id,
        filename="edited.csv",
        payload=rows,
        diff=summary,
        blocking_errors=errors,
    )
    batch_id, changed, checkpoint_id = apply_staged_csv(data_paths.db_file, "token", paths=data_paths)
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert batch_id == result.batch_id
    assert changed == 1
    assert checkpoint_id > 0
    assert saved["title"] == "Edited Tape"
    assert saved["price_cents"] == 400
    assert saved["working_source"] == "CSV_UPLOAD"


def test_csv_checkpoint_restore_is_transactional(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera", item_count=1), paths=data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    db.update_item(data_paths.db_file, item["item_id"], {"title": "Before", "price_cents": 400})
    checkpoint_id = db.create_batch_checkpoint(data_paths.db_file, result.batch_id, reason="test", source="TEST")
    db.update_item(data_paths.db_file, item["item_id"], {"title": "After", "price_cents": 900})
    restored = db.restore_batch_checkpoint(data_paths.db_file, checkpoint_id)
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert restored == 1
    assert saved["title"] == "Before"
    assert saved["price_cents"] == 400


def test_batch_editor_api_edits_and_detects_stale_revision(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera", item_count=1), paths=data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    with TestClient(app) as client:
        page = client.get(f"/batch-editor?batch_id={result.batch_id}")
        assert page.status_code == 200
        assert "Bulk operator workstation" in page.text
        first = client.post(
            f"/api/items/{item['item_id']}",
            json={"field": "title", "value": "Grid Edit", "revision": item["record_revision"]},
        )
        assert first.status_code == 200
        stale = client.post(
            f"/api/items/{item['item_id']}",
            json={"field": "title", "value": "Stale", "revision": item["record_revision"]},
        )
        assert stale.status_code == 409
        assert "changed in another session" in stale.json()["error"]


def test_bulk_price_creates_checkpoint_and_updates_selected_rows(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera", item_count=2), paths=data_paths)
    item_ids = [item["item_id"] for item in db.list_items(data_paths.db_file, batch_id=result.batch_id)]
    with TestClient(app) as client:
        response = client.post(
            f"/api/batches/{result.batch_id}/bulk",
            json={"item_ids": item_ids, "action": "set_price", "value": "4.00", "reason": "Toonie batch"},
        )
    assert response.status_code == 200
    assert response.json()["changed"] == 2
    assert response.json()["checkpoint_id"] > 0
    assert {db.get_item(data_paths.db_file, item_id)["price_cents"] for item_id in item_ids} == {400}


def test_external_review_requires_valid_records(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera", item_count=1), paths=data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    count, blockers = mark_batch_externally_reviewed(data_paths.db_file, result.batch_id)
    assert count == 0
    assert any("Title is required" in blocker for blocker in blockers)
    db.update_item(data_paths.db_file, item["item_id"], {"title": "Reviewed", "price_cents": 400})
    count, blockers = mark_batch_externally_reviewed(data_paths.db_file, result.batch_id)
    assert blockers == []
    assert count == 1
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert saved["review_source"] == "CSV_EXTERNAL_REVIEW"
    assert saved["review_status"] == "DONE"


def test_batch_metrics_and_confidence_buckets_are_grounded(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera", item_count=1), paths=data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    db.update_item(data_paths.db_file, item["item_id"], {"title": "Metric Tape"}, source="BATCH_EDITOR")
    metrics = db.batch_metrics(data_paths.db_file, result.batch_id)
    buckets = db.confidence_buckets(data_paths.db_file, result.batch_id)
    assert metrics["total_changes"] >= 1
    assert metrics["original_bytes"] > 0
    assert metrics["estimated_api_cost"] == "Not calculated"
    assert buckets["unknown"] == 1


def test_change_history_records_source_and_values(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera", item_count=1), paths=data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    db.update_item(
        data_paths.db_file,
        item["item_id"],
        {"title": "Audited"},
        source="BATCH_EDITOR",
        reason="Operator correction",
    )
    history = db.item_history(data_paths.db_file, item["item_id"])
    assert history[0]["field_name"] == "title"
    assert json.loads(history[0]["new_value_json"]) == "Audited"
    assert history[0]["source"] == "BATCH_EDITOR"
