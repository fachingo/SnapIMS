from __future__ import annotations

import json
import shutil
import sqlite3
import time
from pathlib import Path

import qrcode
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
import pytest

from snapims import db
from snapims.bulk import apply_bulk_operation
from snapims.config import DataPaths
from snapims.import_v0130 import (
    NEXT_PAYLOAD,
    apply_correction,
    get_job,
    list_batch_folders,
    normalize_location,
    recover_jobs,
    start_commit,
    start_preview,
    update_batch_display_name,
)
from snapims.web.app import app


def _product(path: Path, label: str = "PRODUCT") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1200, 900), (64, 95, 128))
    ImageDraw.Draw(image).text((60, 60), label, fill="white")
    image.save(path, quality=88)
    return path


def _qr(path: Path, payload: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    code = qrcode.make(payload).convert("RGB").resize((620, 620))
    image = Image.new("RGB", (1200, 900), "white")
    image.paste(code, ((1200 - 620) // 2, (900 - 620) // 2))
    image.save(path, quality=92)
    return path


def _folder(paths: DataPaths, name: str) -> Path:
    folder = paths.batches / name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _wait(paths: DataPaths, job_id: str, terminal: set[str] | None = None, timeout: float = 20) -> dict:
    terminal = terminal or {"READY", "NEEDS_ATTENTION", "FAILED", "IMPORTED"}
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = get_job(paths.db_file, job_id)
        assert job is not None
        if str(job["status"]) in terminal:
            return job
        time.sleep(0.02)
    raise AssertionError(f"Import job did not finish: {get_job(paths.db_file, job_id)}")


def _preview(paths: DataPaths, folder: Path, location: object = None) -> tuple[str, dict]:
    job_id = start_preview(paths, folder, location=location)
    return job_id, _wait(paths, job_id)


def test_location_is_nullable_and_free_text() -> None:
    assert normalize_location("") is None
    assert normalize_location(" none ") is None
    assert normalize_location("None") is None
    assert normalize_location("a6") == "a6"
    assert normalize_location("Processing Table") == "Processing Table"
    with pytest.raises(Exception):
        normalize_location("x" * 121)


@pytest.mark.parametrize(
    ("layout", "items", "warning_fragment"),
    [
        (["P"], 1, None),
        (["P", "N", "P"], 2, None),
        (["N", "P"], 1, "leading NEXT ITEM"),
        (["P", "N"], 1, "trailing NEXT ITEM"),
        (["P", "N", "N", "P"], 2, "consecutive NEXT ITEM"),
        (["N", "N"], 0, "No product photographs"),
    ],
)
def test_exact_next_grouping_and_strange_placement(
    data_paths: DataPaths, layout: list[str], items: int, warning_fragment: str | None
) -> None:
    folder = _folder(data_paths, "case-" + "".join(layout))
    for index, kind in enumerate(layout):
        target = folder / f"PXL_20260803_1200{index:02d}000.jpg"
        _qr(target, NEXT_PAYLOAD) if kind == "N" else _product(target, f"TAPE {index}")
    _, job = _preview(data_paths, folder)
    assert job["preview"]["item_count"] == items
    assert job["preview"]["can_commit"] is (items > 0)
    if warning_fragment:
        assert any(warning_fragment in value for value in job["preview"]["warnings"])


def test_twenty_items_and_end_of_folder_boundary(data_paths: DataPaths) -> None:
    folder = _folder(data_paths, "Twenty Items")
    stream = 0
    for item in range(20):
        _product(folder / f"PXL_20260803_13{stream:04d}.jpg", f"TAPE {item + 1}")
        stream += 1
        if item < 19:
            _qr(folder / f"PXL_20260803_13{stream:04d}.jpg", NEXT_PAYLOAD)
            stream += 1
    _, job = _preview(data_paths, folder, "Warehouse Wall")
    assert job["status"] == "READY"
    assert job["preview"]["item_count"] == 20
    assert job["preview"]["product_photo_count"] == 20
    assert job["preview"]["next_count"] == 19
    assert job["preview"]["location"] == "Warehouse Wall"


def test_legacy_commands_are_ignored_and_consumer_qr_is_product(data_paths: DataPaths) -> None:
    folder = _folder(data_paths, "legacy")
    payloads = [
        "CVHS1:BATCH:START",
        "CVHS1:LOC:A6",
        "CVHS1:LOC:",
        "CVHS1:FLAG:RARE",
        "CVHS1:FLAG:REVIEW",
        "CVHS1:ITEM:CONT",
        "CVHS1:BATCH:END",
    ]
    for index, payload in enumerate(payloads):
        _qr(folder / f"{index:02d}.jpg", payload)
    _qr(folder / "20.jpg", "https://example.com/consumer")
    _product(folder / "21.jpg")
    _, job = _preview(data_paths, folder)
    assert job["preview"]["legacy_count"] == len(payloads)
    assert job["preview"]["item_count"] == 1
    assert job["preview"]["product_photo_count"] == 2
    assert any("legacy SnapIMS command" in value for value in job["preview"]["warnings"])


def test_empty_corrupt_unsupported_unicode_and_spaces(data_paths: DataPaths) -> None:
    empty = _folder(data_paths, "Empty Folder")
    (empty / "notes.txt").write_text("ignore", encoding="utf-8")
    _, empty_job = _preview(data_paths, empty)
    assert empty_job["status"] == "NEEDS_ATTENTION"
    assert empty_job["preview"]["item_count"] == 0

    folder = _folder(data_paths, "Horreur été ünicode")
    _product(folder / "001.jpg")
    (folder / "002.jpg").write_bytes(b"not a jpeg")
    (folder / "archive.zip").write_bytes(b"ignore")
    _, job = _preview(data_paths, folder, "None")
    assert job["preview"]["folder_name"] == "Horreur été ünicode"
    assert job["preview"]["item_count"] == 1
    assert job["preview"]["unreadable_count"] == 1
    assert job["preview"]["location"] is None


def test_folder_listing_is_immediate_and_does_not_open_photos(data_paths: DataPaths) -> None:
    first = _folder(data_paths, "A")
    nested = first / "nested"
    nested.mkdir()
    _product(nested / "hidden.jpg")
    second = _folder(data_paths, "B")
    _product(second / "visible.jpg")
    rows = list_batch_folders(data_paths)
    assert [row["name"] for row in rows] == ["A", "B"]
    assert all(row["state"] == "New" for row in rows)
    with db.connect(data_paths.db_file) as connection:
        assert connection.execute("SELECT COUNT(*) FROM import_photo_cache").fetchone()[0] == 0


def test_corrections_persist_and_do_not_rescan_unrelated_photos(data_paths: DataPaths) -> None:
    folder = _folder(data_paths, "corrections")
    first = _product(folder / "001.jpg", "ONE")
    second = _product(folder / "002.jpg", "TWO")
    job_id, job = _preview(data_paths, folder)
    assert job["preview"]["item_count"] == 1
    changed = apply_correction(data_paths, job_id, str(second), action="product", split_before=True)
    assert changed["item_count"] == 2
    merged = apply_correction(data_paths, job_id, str(second), action="product", merge_previous=True)
    assert merged["item_count"] == 1
    ignored = apply_correction(data_paths, job_id, str(first), action="ignore")
    assert ignored["product_photo_count"] == 1
    with db.connect(data_paths.db_file) as connection:
        assert connection.execute("SELECT COUNT(*) FROM import_photo_corrections").fetchone()[0] == 2
    # The durable same-folder job is reused and rebuilt from cache/corrections after a simulated restart.
    second_job, warm = _preview(data_paths, folder)
    assert second_job == job_id
    assert warm["decode_count"] == 0
    assert warm["qr_scan_count"] == 0
    assert warm["preview"]["product_photo_count"] == 1


def test_only_changed_file_is_invalidated(data_paths: DataPaths) -> None:
    folder = _folder(data_paths, "one-change")
    paths = [_product(folder / f"{index:03d}.jpg", str(index)) for index in range(5)]
    _preview(data_paths, folder)
    time.sleep(0.01)
    _product(paths[2], "CHANGED")
    _, job = _preview(data_paths, folder)
    assert job["cache_hits"] == 4
    assert job["cache_misses"] == 1
    assert job["decode_count"] == 1
    assert job["qr_scan_count"] == 1


def test_location_only_recheck_is_warm_and_zero_scan(data_paths: DataPaths) -> None:
    folder = _folder(data_paths, "metadata")
    _product(folder / "001.jpg")
    _preview(data_paths, folder, "A6")
    _, warm = _preview(data_paths, folder, "Processing Table")
    assert warm["duration_ms"] < 2000
    assert warm["decode_count"] == 0
    assert warm["qr_scan_count"] == 0
    assert warm["preview"]["location"] == "Processing Table"


def test_commit_preserves_sources_hashes_once_and_records_identity(data_paths: DataPaths) -> None:
    folder = _folder(data_paths, "commit batch")
    source = _product(folder / "001.jpg")
    before = source.read_bytes()
    job_id, job = _preview(data_paths, folder, "Processing Table")
    assert job["status"] == "READY"
    start_commit(data_paths, job_id)
    committed = _wait(data_paths, job_id)
    assert committed["status"] == "IMPORTED"
    assert source.read_bytes() == before
    batch = db.get_batch(data_paths.db_file, committed["result_batch_id"])
    assert batch is not None
    assert batch["display_name"] == "commit batch"
    assert batch["source_folder_name"] == "commit batch"
    assert batch["batch_location"] == "Processing Table"
    item = db.list_items(data_paths.db_file, batch_id=batch["batch_id"])[0]
    assert item["location"] == "Processing Table"
    assert item["item_id"].startswith(batch["batch_id"])
    with db.connect(data_paths.db_file) as connection:
        cache = connection.execute("SELECT sha256 FROM import_photo_cache").fetchone()[0]
    assert len(cache) == 64
    _, warm = _preview(data_paths, folder, "None")
    assert warm["decode_count"] == warm["qr_scan_count"] == 0


def test_changed_after_preview_rescans_only_file_and_requires_confirmation(data_paths: DataPaths) -> None:
    folder = _folder(data_paths, "changed-after-preview")
    first = _product(folder / "001.jpg")
    _product(folder / "002.jpg")
    job_id, _ = _preview(data_paths, folder)
    time.sleep(0.01)
    _product(first, "changed")
    start_commit(data_paths, job_id)
    job = _wait(data_paths, job_id)
    assert job["status"] == "NEEDS_ATTENTION"
    assert "Only those files were rescanned" in job["error_message"]
    assert job["preview"]["item_count"] == 1


def test_bulk_editor_name_and_location_overrides_keep_ids_and_audit(data_paths: DataPaths) -> None:
    folder = _folder(data_paths, "source-name")
    _product(folder / "001.jpg")
    job_id, _ = _preview(data_paths, folder, "Q1")
    start_commit(data_paths, job_id)
    imported = _wait(data_paths, job_id)
    batch_id = imported["result_batch_id"]
    item = db.list_items(data_paths.db_file, batch_id=batch_id)[0]
    item_id = item["item_id"]
    update_batch_display_name(data_paths.db_file, batch_id, "Operator Display Name")
    apply_bulk_operation(
        data_paths.db_file,
        batch_id,
        item_ids=[item_id],
        action="set_location",
        value="None",
        reason="Return to unassigned",
        request_id="location-none",
    )
    batch = db.get_batch(data_paths.db_file, batch_id)
    changed = db.get_item(data_paths.db_file, item_id)
    assert batch and batch["display_name"] == "Operator Display Name"
    assert batch["source_folder_name"] == "source-name"
    assert Path(batch["source_folder"]).name == "source-name"
    assert changed and changed["location"] is None
    assert changed["item_id"] == item_id
    with db.connect(data_paths.db_file) as connection:
        event = connection.execute(
            "SELECT from_location,to_location FROM inventory_events WHERE item_id=? AND event_type='LOCATION_CHANGED' ORDER BY inventory_event_id DESC",
            (item_id,),
        ).fetchone()
    assert tuple(event) == ("Q1", None)


def test_duplicate_folder_status_and_resume_after_restart(data_paths: DataPaths) -> None:
    folder = _folder(data_paths, "resume")
    for index in range(8):
        _product(folder / f"{index:03d}.jpg")
    job_id = start_preview(data_paths, folder)
    # Mark as interrupted deterministically, then use startup recovery.
    with db.transaction(data_paths.db_file) as connection:
        connection.execute("UPDATE import_jobs SET status='RUNNING' WHERE job_id=?", (job_id,))
    recovered = recover_jobs(data_paths)
    assert recovered >= 1
    job = _wait(data_paths, job_id)
    assert job["status"] == "READY"
    rows = list_batch_folders(data_paths)
    assert rows[0]["state"] == "Ready to resume"


def test_web_import_returns_immediately_and_polling_endpoint_survives_refresh(data_paths: DataPaths) -> None:
    folder = _folder(data_paths, "web")
    for index in range(12):
        _product(folder / f"{index:03d}.jpg")
    with TestClient(app) as client:
        started = time.perf_counter()
        response = client.post(
            "/import/preview",
            data={"folder_path": str(folder), "batch_location": "Processing Table"},
            follow_redirects=False,
        )
        elapsed = time.perf_counter() - started
        assert response.status_code == 303
        assert elapsed < 1.0
        job_id = response.headers["location"].split("job_id=")[1]
        page = client.get(response.headers["location"])
        assert page.status_code == 200
        assert "CVHS1:ITEM:NEXT" in page.text
        status = client.get(f"/import/job/{job_id}")
        assert status.status_code == 200
        final = _wait(data_paths, job_id)
        refreshed = client.get(f"/import?job_id={job_id}")
        assert final["status"] == "READY"
        assert "Processing Table" in refreshed.text
        assert "BATCH START" not in refreshed.text
        assert "LOCATION QR override" not in refreshed.text


def test_synthetic_100_item_202_photo_batch_is_cached(data_paths: DataPaths) -> None:
    folder = _folder(data_paths, "synthetic-100")
    index = 0
    for item in range(100):
        _product(folder / f"{index:04d}.jpg", str(item)); index += 1
        if item < 99:
            _qr(folder / f"{index:04d}.jpg", NEXT_PAYLOAD); index += 1
    for payload in ("CVHS1:BATCH:START", "CVHS1:BATCH:END", "CVHS1:FLAG:REVIEW"):
        _qr(folder / f"{index:04d}.jpg", payload); index += 1
    assert index == 202
    _, cold = _preview(data_paths, folder, timeout=60) if False else (None, None)
    cold_job_id = start_preview(data_paths, folder)
    cold = _wait(data_paths, cold_job_id, timeout=60)
    assert cold["status"] == "READY"
    assert cold["preview"]["item_count"] == 100
    assert cold["duration_ms"] < 60_000
    warm_job_id = start_preview(data_paths, folder)
    warm = _wait(data_paths, warm_job_id, timeout=10)
    assert warm["preview"]["item_count"] == 100
    assert warm["duration_ms"] < 3_000
    assert warm["decode_count"] == 0
    assert warm["qr_scan_count"] == 0
    assert warm["cache_hits"] == 202


def test_heic_support_when_runtime_is_available(data_paths: DataPaths) -> None:
    pillow_heif = pytest.importorskip("pillow_heif")
    pillow_heif.register_heif_opener()
    folder = _folder(data_paths, "heic")
    image = Image.new("RGB", (640, 480), "navy")
    path = folder / "001.heic"
    image.save(path, format="HEIF")
    _, job = _preview(data_paths, folder)
    assert job["preview"]["item_count"] == 1
