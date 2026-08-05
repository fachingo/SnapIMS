from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from snapims import db
from snapims.demo import create_demo_batch
from snapims.inventory import export_inventory_csv, preview_inventory_csv
from snapims.processor import process_batch
from snapims.web.app import app


def _import(tmp_path: Path, data_paths, *, count: int = 1):
    return process_batch(create_demo_batch(tmp_path / "camera", item_count=count), paths=data_paths)


def test_import_uses_configured_batch_home_instead_of_native_picker(data_paths) -> None:
    with TestClient(app) as client:
        response = client.get("/import")
    assert response.status_code == 200
    assert "BATCH HOME DIRECTORY" in response.text
    assert str(data_paths.batches) in response.text
    assert "Advanced · Manual path" not in response.text

def test_review_inline_title_override_completes_in_one_request(tmp_path: Path, data_paths) -> None:
    result = _import(tmp_path, data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    with TestClient(app) as client:
        response = client.post(
            "/review/approve",
            data={
                "batch_id": result.batch_id,
                "item_id": item["item_id"],
                    "title": "Manual One Enter Title",
                    "price": "4.00",
                    "discount": "0",
                    "revision": str(item["record_revision"]),
                },
                follow_redirects=False,
            )
    assert response.status_code == 303
    assert "edit=true" not in response.headers["location"]
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert saved["title"] == "Manual One Enter Title"
    assert saved["price_cents"] == 400
    assert saved["review_status"] == "DONE"


def test_exported_csv_round_trips_with_item_id(tmp_path: Path, data_paths) -> None:
    result = _import(tmp_path, data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    db.update_item(data_paths.db_file, item["item_id"], {"title": "Round Trip", "price_cents": 400})
    destination = tmp_path / "inventory.csv"
    export_inventory_csv(data_paths.db_file, result.batch_id, destination)
    rows, summary, errors = preview_inventory_csv(
        data_paths.db_file,
        result.batch_id,
        destination.read_text(encoding="utf-8-sig"),
    )
    assert errors == []
    assert summary["matched"] == 1
    assert rows[0]["item_id"] == item["item_id"]


def test_csv_header_alias_bom_and_semicolon_are_supported(tmp_path: Path, data_paths) -> None:
    result = _import(tmp_path, data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    csv_text = f"\ufeffitem_id ; Title ; Price\r\n{item['item_id']} ; Edited ; 4.00\r\n"
    rows, summary, errors = preview_inventory_csv(data_paths.db_file, result.batch_id, csv_text)
    assert errors == []
    assert summary["matched"] == 1
    assert rows[0]["updates"]["title"] == "Edited"


def test_v061_legacy_recognition_job_items_is_removed_during_schema8_migration(tmp_path: Path) -> None:
    db_file = tmp_path / "legacy.sqlite3"
    db.initialize(db_file)
    connection = sqlite3.connect(db_file)
    connection.executescript(
        """
        PRAGMA foreign_keys=OFF;
        INSERT INTO batches(
            batch_id,source_fingerprint,source_folder,created_at,imported_at,started,ended,status,
            item_count,product_photo_count,command_count,warning_count,warnings_json
        ) VALUES('BATCH-1','legacy-fingerprint','','2026-01-01','2026-01-01',1,1,'COMPLETE',0,0,0,0,'[]');
        DROP TABLE recognition_jobs;
        CREATE TABLE recognition_jobs(
            recognition_job_id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL REFERENCES batches(batch_id),
            provider TEXT NOT NULL,
            model_name TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL,
            completed_at TEXT,
            total INTEGER NOT NULL DEFAULT 0,
            completed INTEGER NOT NULL DEFAULT 0,
            skipped INTEGER NOT NULL DEFAULT 0,
            failed INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'RUNNING',
            last_item_id TEXT,
            only_missing_title INTEGER NOT NULL DEFAULT 0,
            force_reprocess INTEGER NOT NULL DEFAULT 0,
            recognized INTEGER NOT NULL DEFAULT 0,
            current_item_id TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            finished_at TEXT,
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            error_at TEXT,
            last_success_at TEXT
        );
        INSERT INTO recognition_jobs(batch_id,provider,started_at,status)
        VALUES('BATCH-1','openai','2026-01-01','COMPLETE');
        CREATE TABLE recognition_job_items(
            recognition_job_id INTEGER NOT NULL REFERENCES recognition_jobs(recognition_job_id),
            item_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            message TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(recognition_job_id,item_id)
        );
        PRAGMA user_version=7;
        """
    )
    connection.commit()
    connection.close()

    db.initialize(db_file)
    with db.connect(db_file) as migrated:
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
        assert migrated.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='recognition_job_items'"
        ).fetchone()[0] == 0
        job = migrated.execute("SELECT batch_id,status FROM recognition_jobs").fetchone()
        assert tuple(job) == ("BATCH-1", "COMPLETE")
        assert migrated.execute("PRAGMA foreign_key_check").fetchall() == []


def test_keyboard_contract_is_present_in_browser_assets() -> None:
    javascript = Path("snapims/web/static/app.js").read_text(encoding="utf-8")
    template = Path("snapims/web/templates/batch_editor.html").read_text(encoding="utf-8")
    assert "event.code === \"KeyP\"" in javascript
    assert "event.altKey" in javascript
    assert "event.isComposing" in javascript
    assert "moveVertical" in javascript and "moveHorizontal" in javascript
    assert "Digit[1-9]" in javascript
    assert "snapims-quick-actions-v1" in javascript
    assert "Alt+1–9" in template
    assert "data-reset-quick-order" in template


def test_manual_catalog_jobs_use_distinct_negative_identities(tmp_path: Path, data_paths) -> None:
    from snapims.catalog import db as catalog_db
    from snapims.catalog.service import queue_operator_title_correction

    result = _import(tmp_path, data_paths, count=2)
    items = db.list_items(data_paths.db_file, batch_id=result.batch_id)
    job_ids = [
        queue_operator_title_correction(data_paths, item["item_id"], f"Manual Movie {index}", None)
        for index, item in enumerate(items, start=1)
    ]
    assert len(set(job_ids)) == 2
    with catalog_db.connect(data_paths.catalog_db_file, readonly=True) as connection:
        rows = connection.execute(
            "SELECT recognition_result_id,item_id FROM catalog_lookup_jobs ORDER BY job_id"
        ).fetchall()
    identities = [int(row[0]) for row in rows]
    assert len(set(identities)) == 2
    assert all(identity < 0 for identity in identities)
    assert {str(row[1]) for row in rows} == {item["item_id"] for item in items}
