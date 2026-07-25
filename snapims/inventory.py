from __future__ import annotations

import csv
import json
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from snapims import db
from snapims.config import DataPaths
from snapims.protocol import LOCATION_RE

CONDITIONS = ("Not Graded", "Fair", "Good", "Very Good", "Like New", "Sealed", "Damaged", "Mold Review")
POOL_MODES = ("POOLED", "UNIQUE")
CSV_FIELDS = (
    "Item ID", "SKU", "Batch ID", "Shelf", "Sequence", "Rare flag", "Review flag",
    "Title", "Release year", "Edition", "Distributor", "Barcode", "Condition",
    "Condition notes", "Price", "Discount percent", "Quantity", "Tags", "Product type",
    "Vendor", "Description", "Image folder", "Image count", "Recognition provider",
    "Recognition confidence", "Review status", "Ready status", "Validation errors",
    "Shopify status", "Shopify product ID", "Shopify variant ID",
    "Shopify inventory item ID", "Shopify admin URL", "Last error", "Retry count",
)


class CSVImportError(ValueError):
    pass


def _bool_text(value: Any) -> str:
    return "TRUE" if bool(value) else "FALSE"


def _parse_bool(value: str) -> int:
    normalized = value.strip().casefold()
    if normalized in {"true", "yes", "y", "1", "ready"}:
        return 1
    if normalized in {"false", "no", "n", "0", "", "not ready"}:
        return 0
    raise CSVImportError(f"Invalid boolean value: {value!r}")


def _price_to_cents(value: str) -> int | None:
    cleaned = value.strip().replace("$", "").replace(",", "")
    if not cleaned:
        return None
    try:
        amount = Decimal(cleaned).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise CSVImportError(f"Invalid price: {value!r}") from exc
    return int(amount * 100)


def _price_text(cents: int | None) -> str:
    return "" if cents is None else f"{Decimal(cents) / 100:.2f}"


def validation_errors(item: dict[str, Any], photos: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if not str(item.get("title") or "").strip():
        errors.append("Title is required")
    if len(str(item.get("title") or "")) > 255:
        errors.append("Title must be 255 characters or fewer")
    if item.get("price_cents") is None or int(item["price_cents"]) <= 0:
        errors.append("Price must be greater than zero")
    discount = float(item.get("discount_percent") or 0)
    if not 0 <= discount <= 100:
        errors.append("Discount must be between 0 and 100 percent")
    if int(item.get("quantity") or 0) < 0:
        errors.append("Quantity cannot be negative")
    if item.get("condition") not in CONDITIONS:
        errors.append(f"Condition must be one of: {', '.join(CONDITIONS)}")
    if item.get("pool_mode") not in POOL_MODES:
        errors.append("Pool mode must be POOLED or UNIQUE")
    if not LOCATION_RE.fullmatch(f"CVHS1:LOC:{item.get('shelf', '')}"):
        errors.append("Shelf must be Q1 or A1 through J10")
    barcode = str(item.get("barcode") or "").strip()
    if barcode and (not barcode.isdigit() or len(barcode) not in {8, 12, 13, 14}):
        errors.append("Barcode must be 8, 12, 13, or 14 digits")
    if item.get("sku") != item.get("item_id"):
        errors.append("SKU must remain equal to immutable Item ID")
    if not photos:
        errors.append("At least one product image is required")
    elif int(photos[0].get("photo_order") or 0) != 1:
        errors.append("Front image F is missing")
    for photo in photos:
        path = Path(photo.get("processed_path") or "")
        if not path.is_file():
            errors.append(f"Missing processed image: {photo.get('proposed_name', 'unknown')}")
    return errors


def validate_items(db_file: Path, identifiers: list[str] | None = None) -> dict[str, list[str]]:
    selected = db.list_items(db_file)
    if identifiers is not None:
        wanted = set(identifiers)
        selected = [item for item in selected if item["item_id"] in wanted]
    prepared: list[tuple[dict[str, Any], list[str], str]] = []
    for item in selected:
        errors = validation_errors(item, db.get_item_photos(db_file, item["item_id"]))
        if item["ready"]:
            status = "READY" if not errors else "BLOCKED"
        else:
            status = "INCOMPLETE"
        prepared.append((item, errors, status))
    results: dict[str, list[str]] = {}
    with db.transaction(db_file) as connection:
        for item, errors, status in prepared:
            connection.execute(
                "UPDATE items SET validation_status=?,validation_errors=?,updated_at=? WHERE item_id=?",
                (status, json.dumps(errors), db.now(), item["item_id"]),
            )
            results[item["item_id"]] = errors
    return results


def export_inventory_csv(db_file: Path, batch_id: str, destination: Path) -> Path:
    rows = db.list_items(db_file, batch_id=batch_id)
    if not rows:
        raise KeyError(f"Unknown or empty batch: {batch_id}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for item in rows:
            image_folder = str(Path(item["front_image"]).parent) if item.get("front_image") else ""
            try:
                errors = "; ".join(json.loads(item["validation_errors"]))
            except (json.JSONDecodeError, TypeError):
                errors = str(item.get("validation_errors") or "")
            writer.writerow({
                "Item ID": item["item_id"], "SKU": item["sku"], "Batch ID": item["batch_id"],
                "Shelf": item["shelf"], "Sequence": item["sequence"],
                "Rare flag": _bool_text(item["rare"]), "Review flag": _bool_text(item["review"]),
                "Title": item["title"], "Release year": item["release_year"] or "",
                "Edition": item["edition"], "Distributor": item["distributor"],
                "Barcode": item["barcode"], "Condition": item["condition"],
                "Condition notes": item["condition_notes"], "Price": _price_text(item["price_cents"]),
                "Discount percent": f"{float(item['discount_percent']):g}", "Quantity": item["quantity"],
                "Tags": item["tags"], "Product type": item["product_type"], "Vendor": item["vendor"],
                "Description": item["description"], "Image folder": image_folder,
                "Image count": item["image_count"], "Recognition provider": item["recognition_provider"],
                "Recognition confidence": item["recognition_confidence"] or "",
                "Review status": item["review_status"], "Ready status": _bool_text(item["ready"]),
                "Validation errors": errors, "Shopify status": item["upload_status"],
                "Shopify product ID": item["shopify_product_id"],
                "Shopify variant ID": item["shopify_variant_id"],
                "Shopify inventory item ID": item["shopify_inventory_item_id"],
                "Shopify admin URL": item["shopify_admin_url"], "Last error": item["last_error"],
                "Retry count": item["retry_count"],
            })
    return destination


COLUMN_MAP: dict[str, tuple[str, Any]] = {
    "Shelf": ("shelf", lambda value: value.strip().upper()),
    "Title": ("title", str.strip),
    "Release year": ("release_year", lambda value: int(value) if value.strip() else None),
    "Edition": ("edition", str.strip),
    "Distributor": ("distributor", str.strip),
    "Barcode": ("barcode", str.strip),
    "Condition": ("condition", lambda value: value.strip() or "Not Graded"),
    "Condition notes": ("condition_notes", str.strip),
    "Price": ("price_cents", _price_to_cents),
    "Discount percent": ("discount_percent", lambda value: float(value.strip() or 0)),
    "Quantity": ("quantity", int),
    "Tags": ("tags", str.strip),
    "Product type": ("product_type", lambda value: value.strip() or "VHS Tape"),
    "Vendor": ("vendor", lambda value: value.strip() or "Canada VHS"),
    "Description": ("description", str.strip),
    "Ready status": ("ready", _parse_bool),
    "Review flag": ("review", _parse_bool),
}


def import_inventory_csv(db_file: Path, csv_path: Path, *, paths: DataPaths | None = None) -> int:
    if paths:
        db.backup_database(paths, "before-csv-import")
    with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        if "Item ID" not in fields:
            raise CSVImportError("Missing required CSV column: Item ID")
        editable_columns = [column for column in fields if column in COLUMN_MAP]
        if not editable_columns:
            raise CSVImportError("CSV contains no editable SnapIMS columns")
        rows = list(reader)
    identifiers = [row["Item ID"].strip() for row in rows]
    if any(not identifier for identifier in identifiers):
        raise CSVImportError("Every CSV row must contain an Item ID.")
    duplicates = {identifier for identifier in identifiers if identifiers.count(identifier) > 1}
    if duplicates:
        raise CSVImportError(f"Duplicate Item ID in CSV: {sorted(duplicates)[0]}")
    current = {item["item_id"]: item for item in db.list_items(db_file)}
    unknown = [identifier for identifier in identifiers if identifier not in current]
    if unknown:
        raise CSVImportError(f"Unknown Item ID: {unknown[0]}")
    prepared: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for row in rows:
        item_id = row["Item ID"].strip()
        updates: dict[str, Any] = {}
        for column in editable_columns:
            try:
                updates[COLUMN_MAP[column][0]] = COLUMN_MAP[column][1](row.get(column, ""))
            except (ValueError, TypeError) as exc:
                raise CSVImportError(f"Invalid {column} for {item_id}") from exc
        prepared.append((item_id, updates, current[item_id]))
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with db.transaction(db_file) as connection:
        for item_id, updates, previous in prepared:
            assignments = ",".join(f"{field}=?" for field in updates)
            connection.execute(
                f"UPDATE items SET {assignments},updated_at=?,record_revision=record_revision+1 WHERE item_id=?",
                [*updates.values(), timestamp, item_id],
            )
            if "shelf" in updates and updates["shelf"] != previous["shelf"]:
                connection.execute(
                    """INSERT INTO inventory_events(item_id,batch_id,occurred_at,event_type,from_location,to_location,source,notes)
                       VALUES(?,?,?,'LOCATION_CHANGED',?,?, 'CSV_IMPORT','CSV import')""",
                    (item_id, previous["batch_id"], timestamp, previous["shelf"], updates["shelf"]),
                )
            if "quantity" in updates and int(updates["quantity"]) != int(previous["quantity"]):
                connection.execute(
                    """INSERT INTO inventory_events(item_id,batch_id,occurred_at,event_type,to_location,quantity_delta,source,notes)
                       VALUES(?,?,?,'QUANTITY_ADJUSTED',?,?,'CSV_IMPORT','CSV import')""",
                    (item_id, previous["batch_id"], timestamp, updates.get("shelf", previous["shelf"]), int(updates["quantity"]) - int(previous["quantity"])),
                )
    validate_items(db_file, identifiers)
    return len(prepared)
