from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapims import db
from snapims.recognition.service import accept_item, postpone_item
from snapims.web.app import app, physical_context, recognition_status
from tests.helpers import recognized_batch


def test_unified_current_record_prefers_saved_values(tmp_path: Path, data_paths) -> None:
    result = recognized_batch(tmp_path, data_paths, item_count=1)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    db.update_item(data_paths.db_file, item["item_id"], {"title": "Saved title", "price_cents": 1299})
    with TestClient(app) as client:
        page = client.get(f"/review?batch_id={result.batch_id}&item_id={item['item_id']}")
    assert "Saved title" in page.text
    assert "Demo VHS 001" in page.text  # historical details remain available


def test_physical_position_independent_of_filtered_queue(tmp_path: Path, data_paths) -> None:
    result = recognized_batch(tmp_path, data_paths, item_count=3)
    items = db.list_items(data_paths.db_file, batch_id=result.batch_id)
    accept_item(data_paths.db_file, items[0]["item_id"], price_cents=999, discount_percent=0)
    unresolved = db.list_items(data_paths.db_file, batch_id=result.batch_id, queue="UNRESOLVED")
    current = unresolved[0]
    context = physical_context(unresolved, current)
    assert context == {"position": 2, "total": 3, "unfinished": 2}


def test_unfinished_count_decrements_once(tmp_path: Path, data_paths) -> None:
    result = recognized_batch(tmp_path, data_paths, item_count=2)
    items = db.list_items(data_paths.db_file, batch_id=result.batch_id)
    before = physical_context(items, items[0])
    assert before["unfinished"] == 2
    accept_item(data_paths.db_file, items[0]["item_id"], price_cents=999, discount_percent=0)
    remaining = db.list_items(data_paths.db_file, batch_id=result.batch_id, queue="UNRESOLVED")
    after = physical_context(remaining, remaining[0])
    assert after["position"] == 2
    assert after["unfinished"] == 1


@pytest.mark.parametrize(
    ("price", "discount", "expected_price", "expected_discount"),
    [(1299, 0, 1299, 0), (999, 15, 999, 15), (2099, 20, 2099, 20)],
)
def test_quick_edit_variants(tmp_path: Path, data_paths, price, discount, expected_price, expected_discount) -> None:
    result = recognized_batch(tmp_path, data_paths, item_count=1)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    assert accept_item(data_paths.db_file, item["item_id"], price_cents=price, discount_percent=discount) == []
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert saved["price_cents"] == expected_price
    assert saved["discount_percent"] == expected_discount
    assert saved["review_status"] == "DONE"


def test_no_second_confirmation_in_http_flow(tmp_path: Path, data_paths) -> None:
    result = recognized_batch(tmp_path, data_paths, item_count=1)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    with TestClient(app) as client:
        response = client.post(
            "/review/approve",
            data={"batch_id": result.batch_id, "item_id": item["item_id"], "price": "9.99", "discount": "0"},
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert "confirm" not in response.headers["location"].lower()
    assert db.get_item(data_paths.db_file, item["item_id"])["review_status"] == "DONE"


def test_later_preserves_item_and_cursor(tmp_path: Path, data_paths) -> None:
    result = recognized_batch(tmp_path, data_paths, item_count=2)
    items = db.list_items(data_paths.db_file, batch_id=result.batch_id)
    db.set_cursor(data_paths.db_file, result.batch_id, "UNRESOLVED", items[0]["item_id"])
    postpone_item(data_paths.db_file, items[0]["item_id"])
    saved = db.get_item(data_paths.db_file, items[0]["item_id"])
    assert saved["review_status"] == "UNFINISHED"
    assert db.get_cursor(data_paths.db_file, result.batch_id, "UNRESOLVED") == items[0]["item_id"]


def test_completed_item_correction_same_id_and_no_advance(tmp_path: Path, data_paths) -> None:
    result = recognized_batch(tmp_path, data_paths, item_count=2)
    items = db.list_items(data_paths.db_file, batch_id=result.batch_id)
    accept_item(data_paths.db_file, items[0]["item_id"], price_cents=999, discount_percent=0)
    revision = db.get_item(data_paths.db_file, items[0]["item_id"])["record_revision"]
    db.update_item(
        data_paths.db_file,
        items[0]["item_id"],
        {"title": "Corrected", "price_cents": 1499},
        expected_revision=revision,
    )
    saved = db.get_item(data_paths.db_file, items[0]["item_id"])
    assert saved["item_id"] == items[0]["item_id"]
    assert saved["title"] == "Corrected"
    assert saved["review_status"] == "DONE"


def test_optimistic_revision_conflict(tmp_path: Path, data_paths) -> None:
    result = recognized_batch(tmp_path, data_paths, item_count=1)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    revision = item["record_revision"]
    db.update_item(data_paths.db_file, item["item_id"], {"title": "First"}, expected_revision=revision)
    with pytest.raises(RuntimeError, match="another session"):
        db.update_item(data_paths.db_file, item["item_id"], {"title": "Stale"}, expected_revision=revision)
    assert db.get_item(data_paths.db_file, item["item_id"])["title"] == "First"


def test_location_change_requires_reason_and_is_atomic(tmp_path: Path, data_paths) -> None:
    result = recognized_batch(tmp_path, data_paths, item_count=1)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    with pytest.raises(ValueError, match="reason"):
        db.update_item(data_paths.db_file, item["item_id"], {"shelf": "Q1"})
    assert db.get_item(data_paths.db_file, item["item_id"])["shelf"] == "B2"


def test_location_and_quantity_events(tmp_path: Path, data_paths) -> None:
    result = recognized_batch(tmp_path, data_paths, item_count=1)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    db.update_item(data_paths.db_file, item["item_id"], {"shelf": "Q1", "quantity": 2}, reason="Moved for audit")
    with db.connect(data_paths.db_file) as connection:
        rows = connection.execute("SELECT event_type,notes FROM inventory_events WHERE item_id=? ORDER BY inventory_event_id", (item["item_id"],)).fetchall()
    assert [row[0] for row in rows][-2:] == ["LOCATION_CHANGED", "QUANTITY_ADJUSTED"]
    assert rows[-1][1] == "Moved for audit"


def test_restart_restores_active_batch_and_cursor(tmp_path: Path, data_paths) -> None:
    result = recognized_batch(tmp_path, data_paths, item_count=2)
    items = db.list_items(data_paths.db_file, batch_id=result.batch_id)
    db.set_setting(data_paths.db_file, "active_batch", result.batch_id)
    db.set_cursor(data_paths.db_file, result.batch_id, "UNRESOLVED", items[1]["item_id"])
    db.initialize(data_paths.db_file, paths=data_paths)
    assert db.get_setting(data_paths.db_file, "active_batch") == result.batch_id
    assert db.get_cursor(data_paths.db_file, result.batch_id, "UNRESOLVED") == items[1]["item_id"]


def test_twenty_item_physical_orientation(tmp_path: Path, data_paths) -> None:
    result = recognized_batch(tmp_path, data_paths, item_count=20)
    items = db.list_items(data_paths.db_file, batch_id=result.batch_id)
    context = physical_context(items, items[-1])
    assert context == {"position": 20, "total": 20, "unfinished": 20}


def test_recognition_status_contracts(tmp_path: Path, data_paths) -> None:
    result = recognized_batch(tmp_path, data_paths, item_count=2)
    paths = data_paths
    job = db.get_recognition_job(paths.db_file, result.batch_id)
    assert recognition_status(paths, result.batch_id, job)[0] == "Recognition complete · 2 items ready to review"
    db.upsert_recognition_job(paths.db_file, result.batch_id, status="PAUSED", total=2, completed=1, recognized=1, failed=0)
    text, action = recognition_status(paths, result.batch_id, db.get_recognition_job(paths.db_file, result.batch_id))
    assert text == "Identification paused · 1 of 2 complete · 1 remaining"
    assert action == "continue"
