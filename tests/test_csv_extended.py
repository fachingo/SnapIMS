from __future__ import annotations

import csv
from pathlib import Path

import pytest

from snapims import db
from snapims.demo import create_demo_batch
from snapims.inventory import CSVImportError, export_inventory_csv, import_inventory_csv
from snapims.processor import process_batch


def make_item(tmp_path: Path, data_paths):
    result = process_batch(create_demo_batch(tmp_path / "camera", item_count=2), paths=data_paths)
    return result, db.list_items(data_paths.db_file, batch_id=result.batch_id)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_row_reordering_uses_item_id(tmp_path: Path, data_paths) -> None:
    result, items = make_item(tmp_path, data_paths)
    path = tmp_path / "rows.csv"
    write_csv(path, ["Item ID", "Title"], [
        {"Item ID": items[1]["item_id"], "Title": "Second"},
        {"Item ID": items[0]["item_id"], "Title": "First"},
    ])
    assert import_inventory_csv(data_paths.db_file, path) == 2
    saved = db.list_items(data_paths.db_file, batch_id=result.batch_id)
    assert [row["title"] for row in saved] == ["First", "Second"]


@pytest.mark.parametrize(
    ("fields", "rows", "message"),
    [
        (["Title"], [{"Title": "x"}], "Item ID"),
        (["Item ID"], [{"Item ID": "x"}], "no editable"),
        (["Item ID", "Title"], [{"Item ID": "", "Title": "x"}], "Every CSV row"),
    ],
)
def test_csv_structure_errors(tmp_path: Path, data_paths, fields, rows, message) -> None:
    path = tmp_path / "bad.csv"
    write_csv(path, fields, rows)
    with pytest.raises(CSVImportError, match=message):
        import_inventory_csv(data_paths.db_file, path)


def test_unknown_item_rejects_transaction(tmp_path: Path, data_paths) -> None:
    _, items = make_item(tmp_path, data_paths)
    path = tmp_path / "bad.csv"
    write_csv(path, ["Item ID", "Title"], [
        {"Item ID": items[0]["item_id"], "Title": "Would change"},
        {"Item ID": "UNKNOWN", "Title": "No"},
    ])
    with pytest.raises(CSVImportError, match="Unknown Item ID"):
        import_inventory_csv(data_paths.db_file, path)
    assert db.get_item(data_paths.db_file, items[0]["item_id"])["title"] == ""


def test_duplicate_item_rejected(tmp_path: Path, data_paths) -> None:
    _, items = make_item(tmp_path, data_paths)
    path = tmp_path / "duplicate.csv"
    write_csv(path, ["Item ID", "Title"], [
        {"Item ID": items[0]["item_id"], "Title": "A"},
        {"Item ID": items[0]["item_id"], "Title": "B"},
    ])
    with pytest.raises(CSVImportError, match="Duplicate Item ID"):
        import_inventory_csv(data_paths.db_file, path)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("Price", "not-money"),
        ("Quantity", "abc"),
        ("Release year", "year"),
        ("Discount percent", "none"),
        ("Ready status", "perhaps"),
    ],
)
def test_invalid_values_reject_all_updates(tmp_path: Path, data_paths, column: str, value: str) -> None:
    _, items = make_item(tmp_path, data_paths)
    path = tmp_path / "invalid.csv"
    write_csv(path, ["Item ID", "Title", column], [
        {"Item ID": items[0]["item_id"], "Title": "Should not save", column: value},
    ])
    with pytest.raises(CSVImportError):
        import_inventory_csv(data_paths.db_file, path)
    assert db.get_item(data_paths.db_file, items[0]["item_id"])["title"] == ""


def test_explicit_blank_clears_text_but_absent_columns_are_preserved(tmp_path: Path, data_paths) -> None:
    _, items = make_item(tmp_path, data_paths)
    item = items[0]
    db.update_item(data_paths.db_file, item["item_id"], {"title": "Clear me", "edition": "Preserve me", "price_cents": 1000})
    path = tmp_path / "blank.csv"
    write_csv(path, ["Item ID", "Title"], [{"Item ID": item["item_id"], "Title": ""}])
    import_inventory_csv(data_paths.db_file, path)
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert saved["title"] == ""
    assert saved["edition"] == "Preserve me"
    assert saved["price_cents"] == 1000


def test_release_year_discount_round_trip(tmp_path: Path, data_paths) -> None:
    result, items = make_item(tmp_path, data_paths)
    item = items[0]
    db.update_item(data_paths.db_file, item["item_id"], {"release_year": 1997, "discount_percent": 12.5, "price_cents": 2000})
    exported = export_inventory_csv(data_paths.db_file, result.batch_id, tmp_path / "export.csv")
    rows = list(csv.DictReader(exported.open(encoding="utf-8-sig")))
    assert rows[0]["Release year"] == "1997"
    assert rows[0]["Discount percent"] == "12.5"
    rows[0]["Release year"] = "1998"
    rows[0]["Discount percent"] = "20"
    write_csv(tmp_path / "edit.csv", list(rows[0]), rows)
    import_inventory_csv(data_paths.db_file, tmp_path / "edit.csv")
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert saved["release_year"] == 1998
    assert saved["discount_percent"] == 20


def test_shelf_and_quantity_events_are_written(tmp_path: Path, data_paths) -> None:
    _, items = make_item(tmp_path, data_paths)
    item = items[0]
    path = tmp_path / "events.csv"
    write_csv(path, ["Item ID", "Shelf", "Quantity"], [{"Item ID": item["item_id"], "Shelf": "Q1", "Quantity": "3"}])
    import_inventory_csv(data_paths.db_file, path)
    with db.connect(data_paths.db_file) as connection:
        events = connection.execute("SELECT event_type FROM inventory_events WHERE item_id=? ORDER BY inventory_event_id", (item["item_id"],)).fetchall()
    assert [row[0] for row in events][-2:] == ["LOCATION_CHANGED", "QUANTITY_ADJUSTED"]
