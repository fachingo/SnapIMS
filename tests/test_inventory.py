from __future__ import annotations

import csv

import pytest

from snapims import db
from snapims.demo import create_demo_batch
from snapims.inventory import (
    CSVImportError,
    import_inventory_csv,
    validate_items,
)
from snapims.processor import process_batch


def _import_demo(tmp_path, data_paths):
    return process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)


def _read_csv(path):
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def test_csv_row_reordering_updates_only_by_item_id(tmp_path, data_paths) -> None:
    result = _import_demo(tmp_path, data_paths)
    rows = list(reversed(_read_csv(result.work_csv)))
    titles = {}
    for index, row in enumerate(rows, start=1):
        row["Title"] = f"Confirmed title {index}"
        row["Price"] = f"{10 + index}.99"
        row["Condition"] = "Good"
        row["Ready status"] = "TRUE"
        titles[row["Item ID"]] = row["Title"]
    edited = tmp_path / "edited.csv"
    _write_csv(edited, rows)
    assert import_inventory_csv(data_paths.db_file, edited, paths=data_paths) == 2
    items = db.list_items(data_paths.db_file)
    assert {item["item_id"]: item["title"] for item in items} == titles
    assert all(item["validation_status"] == "READY" for item in items)
    assert list(data_paths.backups.glob("*.sqlite3"))


def test_unknown_item_id_rejects_entire_csv_transaction(tmp_path, data_paths) -> None:
    result = _import_demo(tmp_path, data_paths)
    rows = _read_csv(result.work_csv)
    original_title = db.list_items(data_paths.db_file)[0]["title"]
    rows[0]["Title"] = "Should not persist"
    rows[1]["Item ID"] = "UNKNOWN-ID"
    edited = tmp_path / "bad.csv"
    _write_csv(edited, rows)
    with pytest.raises(CSVImportError, match="Unknown Item ID"):
        import_inventory_csv(data_paths.db_file, edited, paths=data_paths)
    assert db.list_items(data_paths.db_file)[0]["title"] == original_title


def test_duplicate_item_id_is_rejected(tmp_path, data_paths) -> None:
    result = _import_demo(tmp_path, data_paths)
    rows = _read_csv(result.work_csv)
    rows[1]["Item ID"] = rows[0]["Item ID"]
    edited = tmp_path / "duplicate.csv"
    _write_csv(edited, rows)
    with pytest.raises(CSVImportError, match="Duplicate Item ID"):
        import_inventory_csv(data_paths.db_file, edited)


def test_csv_import_cannot_modify_an_item_outside_selected_batch(tmp_path, data_paths) -> None:
    first = process_batch(create_demo_batch(tmp_path / "first"), paths=data_paths)
    second_source = create_demo_batch(tmp_path / "second")
    product = sorted(second_source.glob("*.jpg"))[2]
    product.write_bytes(product.read_bytes() + b"distinct-batch")
    second = process_batch(second_source, paths=data_paths)
    rows = _read_csv(first.work_csv)
    foreign_item = db.list_items(data_paths.db_file, batch_id_value=second.batch_id)[0]
    rows[0]["Item ID"] = foreign_item["item_id"]
    rows[0]["Title"] = "Must not cross batch boundary"
    edited = tmp_path / "cross-batch.csv"
    _write_csv(edited, rows)

    with pytest.raises(CSVImportError, match="does not belong to selected batch"):
        import_inventory_csv(
            data_paths.db_file,
            edited,
            expected_batch_id=first.batch_id,
        )

    assert db.get_item(data_paths.db_file, foreign_item["item_id"])["title"] != rows[0]["Title"]


def test_validation_catches_bad_title_price_quantity_barcode_and_shelf(tmp_path, data_paths) -> None:
    _import_demo(tmp_path, data_paths)
    item = db.list_items(data_paths.db_file)[0]
    db.update_item(
        data_paths.db_file, item["item_id"],
        {"title": "", "price_cents": 0, "quantity": -1, "barcode": "ABC", "shelf": "K1", "ready": 1},
    )
    errors = validate_items(data_paths.db_file, [item["item_id"]])[item["item_id"]]
    assert {"Title is required", "Price must be greater than zero", "Quantity cannot be negative"} <= set(errors)
    assert any("Barcode" in error for error in errors)
    assert any("Shelf" in error for error in errors)
    refreshed = db.get_item(data_paths.db_file, item["item_id"])
    assert refreshed["validation_status"] == "BLOCKED"


def test_database_transaction_rolls_back(tmp_path, data_paths) -> None:
    _import_demo(tmp_path, data_paths)
    item = db.list_items(data_paths.db_file)[0]
    with pytest.raises(RuntimeError):
        with db.transaction(data_paths.db_file) as connection:
            connection.execute("UPDATE items SET title='temporary' WHERE item_id=?", (item["item_id"],))
            raise RuntimeError("interrupt transaction")
    assert db.get_item(data_paths.db_file, item["item_id"])["title"] != "temporary"


def test_database_integrity_and_required_tables(tmp_path, data_paths) -> None:
    _import_demo(tmp_path, data_paths)
    with db.connect(data_paths.db_file) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "schema_migrations", "batches", "items", "photos", "command_events",
        "recognition_results", "catalog_products", "inventory_events", "shopify_sync", "settings",
    } <= tables
