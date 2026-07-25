from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapims import db
from snapims.bulk import apply_bulk_operation
from snapims.demo import create_demo_batch
from snapims.inventory import (
    apply_staged_csv,
    mark_batch_externally_reviewed,
    preview_inventory_csv,
)
from snapims.money import (
    final_price_cents,
    format_price_cents,
    parse_discount_percent,
    parse_price_cents,
)
from snapims.processor import ImportInterrupted, process_batch, reconcile_import_journals
from snapims.recognition.providers import recognizer_registry
from snapims.recognition.service import accept_item, start_batch_recognition
from snapims.shopify.service import ShopifyService
from snapims.config import ShopifyConfig
from snapims.web.app import app


def _import(tmp_path: Path, data_paths, *, count: int = 2):
    return process_batch(create_demo_batch(tmp_path / f"camera-{count}", item_count=count), paths=data_paths)


def _valid_csv_text(batch_id: str, items: list[dict], *, prefix: str = "Edited") -> str:
    lines = ["Item ID,Batch ID,Title,Price"]
    for index, item in enumerate(items, start=1):
        lines.append(f"{item['item_id']},{batch_id},{prefix} {index},4.00")
    return "\n".join(lines) + "\n"


def test_test_provider_is_disabled_in_production_and_forged_request_is_rejected(
    tmp_path: Path, data_paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _import(tmp_path, data_paths, count=1)
    monkeypatch.delenv("SNAPIMS_ENABLE_TEST_PROVIDERS", raising=False)
    assert "mock" not in recognizer_registry()
    with TestClient(app) as client:
        page = client.get(f"/review?batch_id={result.batch_id}")
        assert page.status_code == 200
        assert '>Mock<' not in page.text
        response = client.post(
            "/review/identify",
            data={"batch_id": result.batch_id, "provider": "mock"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "disabled" in response.text.lower() or "not available" in response.text.lower()
    assert db.latest_recognition(data_paths.db_file, db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]["item_id"]) is None


def test_historical_test_result_is_blocked_until_deliberate_manual_replacement(
    tmp_path: Path, data_paths
) -> None:
    result = _import(tmp_path, data_paths, count=1)
    assert start_batch_recognition(data_paths.db_file, result.batch_id, "mock")
    from tests.helpers import wait_for_job

    wait_for_job(data_paths.db_file, result.batch_id)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    assert accept_item(data_paths.db_file, item["item_id"], price_cents=400, discount_percent=0) == []
    import os
    original_mode = os.environ.pop("SNAPIMS_ENABLE_TEST_PROVIDERS", None)
    service = ShopifyService(data_paths.db_file, ShopifyConfig.from_env())
    blocked = service.dry_run(item["item_id"])
    assert not blocked.ready
    assert any("Test-sourced" in error for error in blocked.errors)
    db.update_item(
        data_paths.db_file,
        item["item_id"],
        {"working_source": "INDIVIDUAL_REVIEW", "review_source": "INDIVIDUAL_REVIEW"},
        source="INDIVIDUAL_REVIEW",
    )
    replaced = service.dry_run(item["item_id"])
    assert not any("Test-sourced" in error for error in replaced.errors)
    if original_mode is not None:
        os.environ["SNAPIMS_ENABLE_TEST_PROVIDERS"] = original_mode


def test_unavailable_live_provider_is_blocked_not_failed(tmp_path: Path, data_paths, monkeypatch) -> None:
    result = _import(tmp_path, data_paths, count=2)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert start_batch_recognition(data_paths.db_file, result.batch_id, "openai") is False
    job = db.get_recognition_job(data_paths.db_file, result.batch_id)
    assert job and job["status"] == "BLOCKED" and int(job["failed"]) == 0
    assert {item["recognition_status"] for item in db.list_items(data_paths.db_file, batch_id=result.batch_id)} == {"BLOCKED"}


def test_staged_csv_failure_is_all_or_nothing_and_stage_remains_recoverable(tmp_path: Path, data_paths) -> None:
    result = _import(tmp_path, data_paths, count=2)
    items = db.list_items(data_paths.db_file, batch_id=result.batch_id)
    rows, summary, errors = preview_inventory_csv(
        data_paths.db_file,
        result.batch_id,
        _valid_csv_text(result.batch_id, items),
    )
    assert errors == []
    db.save_csv_staging(
        data_paths.db_file,
        token="atomic-csv",
        batch_id=result.batch_id,
        filename="atomic.csv",
        payload=rows,
        diff=summary,
        blocking_errors=[],
        upload_bytes=123,
    )
    with pytest.raises(RuntimeError, match="Injected CSV failure"):
        apply_staged_csv(data_paths.db_file, "atomic-csv", paths=data_paths, fail_after=1)
    saved = db.list_items(data_paths.db_file, batch_id=result.batch_id)
    assert [item["title"] for item in saved] == ["", ""]
    stage = db.get_csv_staging(data_paths.db_file, "atomic-csv")
    assert stage and stage["status"] == "STAGED"
    with db.connect(data_paths.db_file) as connection:
        operation = connection.execute(
            "SELECT status,error_message FROM operation_requests WHERE request_id='csv:atomic-csv'"
        ).fetchone()
        assert operation and operation[0] == "FAILED"
        assert connection.execute(
            "SELECT COUNT(*) FROM batch_checkpoints WHERE batch_id=?", (result.batch_id,)
        ).fetchone()[0] == 0


def test_bulk_failure_rolls_back_and_request_is_idempotent(tmp_path: Path, data_paths) -> None:
    result = _import(tmp_path, data_paths, count=2)
    item_ids = [item["item_id"] for item in db.list_items(data_paths.db_file, batch_id=result.batch_id)]
    with pytest.raises(RuntimeError, match="Injected bulk failure"):
        apply_bulk_operation(
            data_paths.db_file,
            result.batch_id,
            item_ids=item_ids,
            action="set_price",
            value="4.00",
            request_id="bulk-fail",
            fail_after=1,
        )
    assert [item["price_cents"] for item in db.list_items(data_paths.db_file, batch_id=result.batch_id)] == [None, None]
    with db.connect(data_paths.db_file) as connection:
        assert connection.execute(
            "SELECT status FROM operation_requests WHERE request_id='bulk-fail'"
        ).fetchone()[0] == "FAILED"
        assert connection.execute(
            "SELECT COUNT(*) FROM batch_checkpoints WHERE batch_id=?", (result.batch_id,)
        ).fetchone()[0] == 0
    first = apply_bulk_operation(
        data_paths.db_file,
        result.batch_id,
        item_ids=item_ids,
        action="set_price",
        value="4.00",
        request_id="bulk-success",
    )
    second = apply_bulk_operation(
        data_paths.db_file,
        result.batch_id,
        item_ids=item_ids,
        action="set_price",
        value="4.00",
        request_id="bulk-success",
    )
    assert first.as_dict() == second.as_dict()
    assert [item["price_cents"] for item in db.list_items(data_paths.db_file, batch_id=result.batch_id)] == [400, 400]


def test_external_review_failure_changes_nothing(tmp_path: Path, data_paths) -> None:
    result = _import(tmp_path, data_paths, count=2)
    items = db.list_items(data_paths.db_file, batch_id=result.batch_id)
    for index, item in enumerate(items, start=1):
        db.update_item(
            data_paths.db_file,
            item["item_id"],
            {"title": f"Tape {index}", "price_cents": 400},
            source="TEST_SETUP",
        )
    with pytest.raises(RuntimeError, match="Injected external-review failure"):
        mark_batch_externally_reviewed(data_paths.db_file, result.batch_id, fail_after=1)
    saved = db.list_items(data_paths.db_file, batch_id=result.batch_id)
    assert {item["review_status"] for item in saved} == {"UNFINISHED"}
    assert db.get_recognition_job(data_paths.db_file, result.batch_id)["status"] != "REVIEW_COMPLETE"
    with db.connect(data_paths.db_file) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM batch_checkpoints WHERE batch_id=?", (result.batch_id,)
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM operation_requests WHERE operation_type='EXTERNAL_REVIEW' AND status='FAILED'"
        ).fetchone()[0] == 1


def test_checkpoint_restore_is_audited_and_does_not_fake_remote_rollback(tmp_path: Path, data_paths) -> None:
    result = _import(tmp_path, data_paths, count=1)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    db.update_item(data_paths.db_file, item["item_id"], {"title": "Before", "price_cents": 400})
    checkpoint = db.create_batch_checkpoint(data_paths.db_file, result.batch_id, reason="Known good", source="TEST")
    db.update_item(
        data_paths.db_file,
        item["item_id"],
        {"title": "After", "price_cents": 900},
    )
    with db.transaction(data_paths.db_file) as connection:
        connection.execute(
            "UPDATE items SET shopify_product_id=?,upload_status='UPLOADED' WHERE item_id=?",
            ("gid://shopify/Product/1", item["item_id"]),
        )
    assert db.restore_batch_checkpoint(data_paths.db_file, checkpoint) == 1
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert saved["title"] == "Before" and saved["price_cents"] == 400
    assert saved["shopify_product_id"] == "gid://shopify/Product/1"
    assert saved["upload_status"] == "UPLOADED"
    with db.connect(data_paths.db_file) as connection:
        changes = connection.execute(
            "SELECT field_name,source FROM item_change_log WHERE item_id=? AND source='CHECKPOINT_RESTORE'",
            (item["item_id"],),
        ).fetchall()
        assert any(row[0] == "title" for row in changes)
        assert all(row[1] == "CHECKPOINT_RESTORE" for row in changes)
        safety = connection.execute(
            "SELECT protected,restored_from_checkpoint_id FROM batch_checkpoints WHERE restored_from_checkpoint_id=?",
            (checkpoint,),
        ).fetchone()
        assert safety and safety[0] == 1


def test_current_schema_with_missing_structure_fails_closed(tmp_path: Path) -> None:
    db_file = tmp_path / "bad-current.sqlite3"
    db.initialize(db_file)
    connection = sqlite3.connect(db_file)
    connection.execute("DROP INDEX idx_items_review")
    connection.commit()
    connection.close()
    with pytest.raises(RuntimeError, match="Missing index: idx_items_review"):
        db.initialize(db_file)


def test_legacy_nonunique_recognition_jobs_rebuilds_to_one_latest_row(tmp_path: Path) -> None:
    db_file = tmp_path / "legacy-jobs.sqlite3"
    db.initialize(db_file)
    with db.connect(db_file) as source:
        source.execute("PRAGMA foreign_keys=OFF")
        source.execute("ALTER TABLE recognition_jobs RENAME TO recognition_jobs_good")
        source.execute(
            "CREATE TABLE recognition_jobs(recognition_job_id INTEGER PRIMARY KEY AUTOINCREMENT,batch_id TEXT NOT NULL,provider TEXT NOT NULL,started_at TEXT NOT NULL,status TEXT NOT NULL)"
        )
        source.execute("INSERT INTO batches(batch_id,source_fingerprint,source_folder,created_at,imported_at,started,ended,status,item_count,product_photo_count,command_count,warning_count,warnings_json) VALUES('B','F','/x','t','t',1,1,'IMPORTED',0,0,0,0,'[]')")
        source.execute("INSERT INTO recognition_jobs(batch_id,provider,started_at,status) VALUES('B','mock','1','RUNNING')")
        source.execute("INSERT INTO recognition_jobs(batch_id,provider,started_at,status) VALUES('B','openai','2','PAUSED')")
        source.execute("DROP TABLE recognition_jobs_good")
        source.execute("PRAGMA user_version=6")
        source.commit()
    db.initialize(db_file)
    with db.connect(db_file) as connection:
        rows = connection.execute("SELECT batch_id,provider,status FROM recognition_jobs").fetchall()
        assert len(rows) == 1
        assert tuple(rows[0]) == ("B", "openai", "PAUSED")
        assert db.schema_manifest_report(connection)["ok"]


def test_interrupted_import_after_media_finalization_recovers_same_identity(tmp_path: Path, data_paths) -> None:
    source = create_demo_batch(tmp_path / "camera-recover", item_count=2)
    with pytest.raises(ImportInterrupted):
        process_batch(source, paths=data_paths, batch_name="RECOVER", interrupt_at="after_media_rename")
    with db.connect(data_paths.db_file) as connection:
        journal = dict(connection.execute("SELECT * FROM import_journal").fetchone())
    expected_batch = journal["batch_id"]
    assert db.get_batch(data_paths.db_file, expected_batch) is None
    repaired = reconcile_import_journals(data_paths)
    assert repaired["completed"] == 1
    batch = db.get_batch(data_paths.db_file, expected_batch)
    assert batch and batch["item_count"] == 2
    assert [item["item_id"] for item in db.list_items(data_paths.db_file, batch_id=expected_batch)] == [
        f"{expected_batch}-B2-001",
        f"{expected_batch}-B2-002",
    ]
    with db.connect(data_paths.db_file) as connection:
        assert connection.execute("SELECT status FROM import_journal").fetchone()[0] == "COMPLETE"


def test_money_policy_is_exact_and_shared() -> None:
    assert parse_price_cents("$4.00", allow_blank=False) == 400
    assert parse_price_cents("4.995", allow_blank=False) == 500
    assert format_price_cents(499) == "4.99"
    assert parse_discount_percent("12.345") == 12.35
    assert final_price_cents(999, "10") == 899
    assert final_price_cents(1, "50") == 1


def test_unresolved_recognition_suggestion_confidence_is_visible_in_editor(tmp_path: Path, data_paths) -> None:
    result = _import(tmp_path, data_paths, count=1)
    assert start_batch_recognition(data_paths.db_file, result.batch_id, "mock")
    from tests.helpers import wait_for_job

    wait_for_job(data_paths.db_file, result.batch_id)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    assert item["review_status"] == "UNFINISHED"
    assert item["suggestion_confidence"] is not None
    assert item["display_confidence"] == item["suggestion_confidence"]
    with TestClient(app) as client:
        page = client.get(f"/batch-editor?batch_id={result.batch_id}")
        assert page.status_code == 200
        assert "AI suggestion" in page.text
        assert str(round(float(item["suggestion_confidence"]) * 100)) in page.text


def test_favicon_and_home_never_expose_python_internals(data_paths) -> None:
    with TestClient(app) as client:
        favicon = client.get("/favicon.ico")
        home = client.get("/")
    assert favicon.status_code == 200
    assert home.status_code == 200
    assert "built-in method" not in home.text
    assert "dict_items" not in home.text
    assert "&lt;bound method" not in home.text
