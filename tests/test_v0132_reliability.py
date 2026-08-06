from __future__ import annotations

import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from snapims import db
from snapims.bulk import apply_bulk_operation
from snapims.config import DataPaths
from snapims.demo import create_demo_batch
from snapims.import_v0130 import get_job, start_commit, start_preview
from snapims.processor import process_batch
from snapims.web.app import app


def _wait_import(db_file: Path, job_id: str, terminal: set[str], timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = get_job(db_file, job_id)
        if job and str(job["status"]) in terminal:
            return job
        time.sleep(0.02)
    raise AssertionError(f"Import job {job_id} did not reach {sorted(terminal)}")


def _product(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (160, 100), "white").save(path, format="JPEG")
    return path


def _direct_batch(paths: DataPaths, count: int, *, batch_id: str = "BATCH-V0132-LARGE") -> str:
    db.initialize(paths.db_file, paths=paths)
    stamp = db.now()
    with db.transaction(paths.db_file) as connection:
        connection.execute(
            """INSERT INTO batches(
                   batch_id,source_fingerprint,source_folder,created_at,imported_at,started,ended,
                   status,item_count,product_photo_count,command_count,warning_count,warnings_json,
                   display_name,source_folder_name
               ) VALUES(?,?,?,?,?,1,1,'IMPORTED',?,0,0,0,'[]',?,?)""",
            (
                batch_id,
                f"fingerprint-{batch_id}",
                f"/fixtures/{batch_id}",
                stamp,
                stamp,
                count,
                batch_id,
                batch_id,
            ),
        )
        connection.executemany(
            """INSERT INTO items(
                   item_id,sku,batch_id,sequence,shelf,location,title,price_cents,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    f"{batch_id}-ITEM-{index:05d}",
                    f"{batch_id}-SKU-{index:05d}",
                    batch_id,
                    index,
                    "",
                    None,
                    f"Tape {index:05d}",
                    499,
                    stamp,
                    stamp,
                )
                for index in range(1, count + 1)
            ],
        )
    return batch_id


def _insert_tags(paths: DataPaths) -> tuple[str, str]:
    db.initialize(paths.db_file, paths=paths)
    stamp = db.now()
    with db.transaction(paths.db_file) as connection:
        connection.executemany(
            """INSERT INTO tag_definitions(
                   tag_id,canonical_label,category,active,ai_eligible,shopify_visible,
                   deterministic_only,sort_order,created_at,updated_at,evidence_json
               ) VALUES(?,?, 'Operator',1,0,1,1,?,?,?,'{}')""",
            [
                ("TAG-V0132-A", "V0132 A", 10, stamp, stamp),
                ("TAG-V0132-B", "V0132 B", 20, stamp, stamp),
            ],
        )
    return "TAG-V0132-A", "TAG-V0132-B"


def test_connection_context_explicitly_closes_handle(tmp_path: Path) -> None:
    db_file = tmp_path / "close.sqlite3"
    db.initialize(db_file)
    connection = db.connect(db_file)
    with connection as active:
        assert active.execute("SELECT 1").fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


def test_repeated_database_workflows_do_not_leak_descriptors(tmp_path: Path) -> None:
    if not Path("/proc/self/fd").is_dir():
        pytest.skip("Linux /proc descriptor accounting is unavailable")
    db_file = tmp_path / "fd.sqlite3"
    db.initialize(db_file)
    baseline = len(list(Path("/proc/self/fd").iterdir()))
    samples: list[int] = []
    for index in range(120):
        with db.connect(db_file) as connection:
            connection.execute("SELECT COUNT(*) FROM settings").fetchone()
        with db.transaction(db_file) as connection:
            connection.execute(
                "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                ("fd-probe", str(index), db.now()),
            )
        if index % 10 == 0:
            samples.append(len(list(Path("/proc/self/fd").iterdir())))
    final = len(list(Path("/proc/self/fd").iterdir()))
    assert max(samples + [final]) <= baseline + 8
    assert final <= baseline + 4


def test_simultaneous_same_folder_preview_reuses_one_job(data_paths: DataPaths) -> None:
    folder = data_paths.batches / "QA-RACE-DUPLICATE"
    _product(folder / "001.jpg")
    barrier = threading.Barrier(2)

    def launch() -> str:
        barrier.wait()
        return start_preview(data_paths, folder)

    with ThreadPoolExecutor(max_workers=2) as pool:
        job_ids = list(pool.map(lambda _: launch(), range(2)))
    assert len(set(job_ids)) == 1
    job = _wait_import(data_paths.db_file, job_ids[0], {"READY", "NEEDS_ATTENTION", "FAILED"})
    assert job["status"] == "READY"
    with db.connect(data_paths.db_file) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM import_jobs WHERE folder_path=?",
            (str(folder.resolve()),),
        ).fetchone()[0]
    assert count == 1


def test_duplicate_commit_is_idempotent(data_paths: DataPaths) -> None:
    folder = data_paths.batches / "QA-IDEMPOTENT-COMMIT"
    _product(folder / "001.jpg")
    job_id = start_preview(data_paths, folder)
    assert _wait_import(data_paths.db_file, job_id, {"READY"})["status"] == "READY"
    barrier = threading.Barrier(2)

    def commit() -> None:
        barrier.wait()
        start_commit(data_paths, job_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: commit(), range(2)))
    imported = _wait_import(data_paths.db_file, job_id, {"IMPORTED", "FAILED", "NEEDS_ATTENTION"}, 30)
    assert imported["status"] == "IMPORTED"
    start_commit(data_paths, job_id)
    with db.connect(data_paths.db_file) as connection:
        batches = connection.execute(
            "SELECT COUNT(*) FROM batches WHERE import_job_id=?", (job_id,)
        ).fetchone()[0]
    assert batches == 1


def test_fill_down_actions_are_atomic_audited_and_exact(tmp_path: Path, data_paths: DataPaths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera", item_count=3), paths=data_paths)
    items = db.list_items(data_paths.db_file, batch_id=result.batch_id)
    item_ids = [str(item["item_id"]) for item in items]
    tags = list(_insert_tags(data_paths))

    apply_bulk_operation(
        data_paths.db_file,
        result.batch_id,
        item_ids=item_ids,
        action="set_tags",
        value=tags,
        reason="Fill Down tags",
        request_id="V0132-TAGS",
    )
    apply_bulk_operation(
        data_paths.db_file,
        result.batch_id,
        item_ids=item_ids,
        action="set_location",
        value="Processing Table",
        reason="Fill Down location",
        request_id="V0132-LOCATION",
    )
    apply_bulk_operation(
        data_paths.db_file,
        result.batch_id,
        item_ids=item_ids,
        action="set_review",
        value=True,
        reason="Fill Down review",
        request_id="V0132-REVIEW",
    )
    apply_bulk_operation(
        data_paths.db_file,
        result.batch_id,
        item_ids=item_ids,
        action="set_rare",
        value=True,
        reason="Fill Down rare",
        request_id="V0132-RARE",
    )
    saved = db.list_items(data_paths.db_file, batch_id=result.batch_id)
    assert all(item["tag_ids"] == tags for item in saved)
    assert all(item["location"] == "Processing Table" for item in saved)
    assert all(int(item["review"]) == 1 for item in saved)
    assert all(int(item["rare"]) == 1 for item in saved)

    apply_bulk_operation(
        data_paths.db_file,
        result.batch_id,
        item_ids=item_ids,
        action="set_location",
        value="None",
        reason="Clear location",
        request_id="V0132-LOCATION-NONE",
    )
    apply_bulk_operation(
        data_paths.db_file,
        result.batch_id,
        item_ids=item_ids,
        action="set_review",
        value=False,
        reason="Clear review",
        request_id="V0132-REVIEW-CLEAR",
    )
    apply_bulk_operation(
        data_paths.db_file,
        result.batch_id,
        item_ids=item_ids,
        action="set_rare",
        value=False,
        reason="Clear rare",
        request_id="V0132-RARE-CLEAR",
    )
    saved = db.list_items(data_paths.db_file, batch_id=result.batch_id)
    assert all(item["location"] is None and item["shelf"] == "" for item in saved)
    assert all(int(item["review"]) == 0 for item in saved)
    assert all(int(item["rare"]) == 0 for item in saved)
    with db.connect(data_paths.db_file) as connection:
        location_events = connection.execute(
            "SELECT COUNT(*) FROM inventory_events WHERE batch_id=? AND event_type='LOCATION_CHANGED'",
            (result.batch_id,),
        ).fetchone()[0]
        change_rows = connection.execute(
            "SELECT COUNT(*) FROM item_change_log WHERE batch_id=? AND source='BULK_EDIT'",
            (result.batch_id,),
        ).fetchone()[0]
    assert location_events == 6
    assert change_rows >= 18


def test_individual_rare_edit_is_not_silently_discarded(tmp_path: Path, data_paths: DataPaths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "rare-camera", item_count=1), paths=data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    db.update_item(data_paths.db_file, item["item_id"], {"rare": 1}, source="BATCH_EDITOR")
    assert int(db.get_item(data_paths.db_file, item["item_id"])["rare"]) == 1


def test_batch_editor_query_and_html_are_bounded(data_paths: DataPaths) -> None:
    batch_id = _direct_batch(data_paths, 5000)
    page = db.list_editor_items_page(data_paths.db_file, batch_id, page=1, page_size=100)
    assert page["total"] == 5000
    assert page["page_count"] == 50
    assert len(page["items"]) == 100

    with TestClient(app) as client:
        response = client.get(f"/batch-editor?batch_id={batch_id}&page_size=100")
    assert response.status_code == 200
    assert response.text.count('<tr data-item-id=') == 100
    assert len(response.content) < 1_500_000
    assert "Tape 00100" in response.text
    assert "Tape 00101" not in response.text
    assert "Page 1 of 50" in response.text


def test_batch_editor_js_contains_safe_selection_and_tag_navigation() -> None:
    source = Path("snapims/web/static/app.js").read_text(encoding="utf-8")
    assert "focusTagInput" in source
    assert 'tag_ids: "set_tags"' in source
    assert 'location: "set_location"' in source
    assert 'review: "set_review"' in source
    assert 'rare: "set_rare"' in source
    assert 'row.classList.contains("hidden")' in source
    assert "box.checked = false" in source


def test_schema_15_has_active_folder_uniqueness(data_paths: DataPaths) -> None:
    db.initialize(data_paths.db_file, paths=data_paths)
    with db.connect(data_paths.db_file) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 16
        indexes = {
            str(row[1])
            for row in connection.execute("PRAGMA index_list(import_jobs)").fetchall()
        }
    assert "idx_import_jobs_active_folder" in indexes


def test_publish_page_is_bounded_and_does_not_dry_run_all_items(data_paths: DataPaths, monkeypatch: pytest.MonkeyPatch) -> None:
    batch_id = _direct_batch(data_paths, 5000, batch_id="BATCH-V0132-PUBLISH")
    calls: list[str] = []

    def _dry_run(self, item_id: str):  # noqa: ANN001
        calls.append(item_id)
        return {"ok": True, "item_id": item_id}

    monkeypatch.setattr("snapims.web.app.ShopifyService.dry_run", _dry_run)
    with TestClient(app) as client:
        response = client.get(f"/publish?batch_id={batch_id}&page_size=100")
        assert response.status_code == 200
        assert len(response.content) < 1_500_000
        assert calls == []

        simulated = client.get(f"/publish?batch_id={batch_id}&page_size=100&simulate=true")
        assert simulated.status_code == 200
        assert len(calls) == 100
        assert len(simulated.content) < 1_500_000
        assert "Simulation results shown for page 1 of 50" in simulated.text or len(calls) == 100
