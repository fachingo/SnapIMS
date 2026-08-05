from __future__ import annotations

import csv
from pathlib import Path

from snapims import db
from snapims.demo import create_demo_batch
from snapims.inventory import export_inventory_csv, import_inventory_csv
from snapims.processor import process_batch


def test_partial_csv_updates_only_present_columns(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    db.update_item(data_paths.db_file, item["item_id"], {"title": "Keep me", "edition": "Clamshell", "price_cents": 1299})
    partial = tmp_path / "partial.csv"
    with partial.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Item ID", "Price"])
        writer.writeheader()
        writer.writerow({"Item ID": item["item_id"], "Price": "15.99"})
    import_inventory_csv(data_paths.db_file, partial, paths=data_paths)
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert saved["title"] == "Keep me"
    assert saved["edition"] == "Clamshell"
    assert saved["price_cents"] == 1599


def test_export_contains_release_year_and_discount(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    destination = tmp_path / "out.csv"
    export_inventory_csv(data_paths.db_file, result.batch_id, destination)
    header = destination.read_text(encoding="utf-8-sig").splitlines()[0]
    assert "Release year" in header
    assert "Discount percent" in header
