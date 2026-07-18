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

CONDITIONS = (
    "Not Graded", "Fair", "Good", "Very Good", "Like New", "Sealed", "Damaged", "Mold Review"
)
POOL_MODES = ("POOLED", "UNIQUE")
CSV_FIELDS = (
    "Item ID", "SKU", "Batch ID", "Shelf", "Sequence", "Rare flag", "Review flag",
    "Title", "Edition", "Distributor", "Barcode", "Condition", "Condition notes",
    "Price", "Quantity", "Tags", "Product type", "Vendor", "Description",
    "Image folder", "Image count", "Recognition provider", "Recognition confidence",
    "Ready status", "Validation errors", "Shopify status", "Shopify product ID",
    "Shopify variant ID", "Shopify inventory item ID", "Shopify admin URL",
    "Last error", "Retry count",
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


def export_inventory_csv(db_file: Path, batch_id: str, destination: Path) -> Path:
    rows = db.list_items(db_file, batch_id_value=batch_id)
    if not rows:
        raise KeyError(f"Unknown or empty batch: {batch_id}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for item in rows:
            image_folder = str(Path(item["front_image"]).parent) if item.get("front_image") else ""
            try:
                validation_errors = "; ".join(json.loads(item["validation_errors"]))
            except (json.JSONDecodeError, TypeError):
                validation_errors = str(item["validation_errors"] or "")
            writer.writerow(
                {
                    "Item ID": item["item_id"], "SKU": item["sku"],
                    "Batch ID": item["batch_id"], "Shelf": item["shelf"],
                    "Sequence": item["sequence"], "Rare flag": _bool_text(item["rare"]),
                    "Review flag": _bool_text(item["review"]), "Title": item["title"],
                    "Edition": item["edition"], "Distributor": item["distributor"],
                    "Barcode": item["barcode"], "Condition": item["condition"],
                    "Condition notes": item["condition_notes"],
                    "Price": _price_text(item["price_cents"]), "Quantity": item["quantity"],
                    "Tags": item["tags"], "Product type": item["product_type"],
                    "Vendor": item["vendor"], "Description": item["description"],
                    "Image folder": image_folder, "Image count": item["image_count"],
                    "Recognition provider": item["recognition_provider"],
                    "Recognition confidence": item["recognition_confidence"] or "",
                    "Ready status": _bool_text(item["ready"]),
                    "Validation errors": validation_errors,
                    "Shopify status": item["upload_status"],
                    "Shopify product ID": item["shopify_product_id"],
                    "Shopify variant ID": item["shopify_variant_id"],
                    "Shopify inventory item ID": item["shopify_inventory_item_id"],
                    "Shopify admin URL": item["shopify_admin_url"],
                    "Last error": item["last_error"], "Retry count": item["retry_count"],
                }
            )
    return destination


def import_inventory_csv(
    db_file: Path,
    csv_path: Path,
    *,
    paths: DataPaths | None = None,
    expected_batch_id: str | None = None,
) -> int:
    if paths:
        db.backup_database(paths, "before-csv-import")
    with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [field for field in ("Item ID",) if field not in (reader.fieldnames or [])]
        if missing:
            raise CSVImportError(f"Missing required CSV column: {missing[0]}")
        rows = list(reader)

    identifiers = [row["Item ID"].strip() for row in rows]
    if any(not identifier for identifier in identifiers):
        raise CSVImportError("Every CSV row must contain an Item ID.")
    duplicates = sorted({identifier for identifier in identifiers if identifiers.count(identifier) > 1})
    if duplicates:
        raise CSVImportError(f"Duplicate Item ID in CSV: {duplicates[0]}")

    current = {item["item_id"]: item for item in db.list_items(db_file)}
    unknown = [identifier for identifier in identifiers if identifier not in current]
    if unknown:
        raise CSVImportError(f"Unknown Item ID: {unknown[0]}")
    if expected_batch_id is not None:
        wrong_batch = [
            identifier
            for identifier in identifiers
            if current[identifier]["batch_id"] != expected_batch_id
        ]
        if wrong_batch:
            raise CSVImportError(
                f"Item ID does not belong to selected batch {expected_batch_id}: "
                f"{wrong_batch[0]}"
            )

    prepared: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
    for row in rows:
        item_id_value = row["Item ID"].strip()
        try:
            quantity = int(row.get("Quantity", current[item_id_value]["quantity"]))
        except ValueError as exc:
            raise CSVImportError(f"Invalid quantity for {item_id_value}") from exc
        values = {
            "shelf": row.get("Shelf", current[item_id_value]["shelf"]).strip().upper(),
            "title": row.get("Title", "").strip(),
            "edition": row.get("Edition", "").strip(),
            "distributor": row.get("Distributor", "").strip(),
            "barcode": row.get("Barcode", "").strip(),
            "condition": row.get("Condition", "Not Graded").strip() or "Not Graded",
            "condition_notes": row.get("Condition notes", "").strip(),
            "price_cents": _price_to_cents(row.get("Price", "")),
            "quantity": quantity,
            "tags": row.get("Tags", "").strip(),
            "product_type": row.get("Product type", "VHS Tape").strip() or "VHS Tape",
            "vendor": row.get("Vendor", "Canada VHS").strip() or "Canada VHS",
            "description": row.get("Description", "").strip(),
            "ready": _parse_bool(row.get("Ready status", "FALSE")),
            "review": _parse_bool(row.get("Review flag", _bool_text(current[item_id_value]["review"]))),
        }
        prepared.append((values, item_id_value, current[item_id_value]))

    timestamp = datetime.now().isoformat(timespec="seconds")
    with db.transaction(db_file) as connection:
        for values, item_id_value, previous in prepared:
            assignments = ", ".join(f"{field}=?" for field in values)
            connection.execute(
                f"UPDATE items SET {assignments}, updated_at=? WHERE item_id=?",
                [*values.values(), timestamp, item_id_value],
            )
            if values["shelf"] != previous["shelf"]:
                connection.execute(
                    """
                    INSERT INTO inventory_events(
                        item_id, batch_id, occurred_at, event_type, from_location,
                        to_location, source, notes
                    ) VALUES(?, ?, ?, 'LOCATION_CHANGED', ?, ?, 'CSV_IMPORT', '')
                    """,
                    (
                        item_id_value,
                        previous["batch_id"],
                        timestamp,
                        previous["shelf"],
                        values["shelf"],
                    ),
                )
            if int(values["quantity"]) != int(previous["quantity"]):
                connection.execute(
                    """
                    INSERT INTO inventory_events(
                        item_id, batch_id, occurred_at, event_type, to_location,
                        quantity_delta, source, notes
                    ) VALUES(?, ?, ?, 'QUANTITY_ADJUSTED', ?, ?, 'CSV_IMPORT', '')
                    """,
                    (
                        item_id_value,
                        previous["batch_id"],
                        timestamp,
                        values["shelf"],
                        int(values["quantity"]) - int(previous["quantity"]),
                    ),
                )
    validate_items(db_file, identifiers)
    return len(prepared)


def validation_errors(item: dict[str, Any], photo_paths: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if not item["title"].strip():
        errors.append("Title is required")
    if len(item["title"]) > 255:
        errors.append("Title must be 255 characters or fewer")
    if item["price_cents"] is None or int(item["price_cents"]) <= 0:
        errors.append("Price must be greater than zero")
    if int(item["quantity"]) < 0:
        errors.append("Quantity cannot be negative")
    if item["condition"] not in CONDITIONS:
        errors.append(f"Condition must be one of: {', '.join(CONDITIONS)}")
    if item["pool_mode"] not in POOL_MODES:
        errors.append("Pool mode must be POOLED or UNIQUE")
    if not LOCATION_RE.fullmatch(f"CVHS1:LOC:{item['shelf']}"):
        errors.append("Shelf must be Q1 or A1 through J10")
    barcode = item["barcode"].strip()
    if barcode and (not barcode.isdigit() or len(barcode) not in {8, 12, 13, 14}):
        errors.append("Barcode must be 8, 12, 13, or 14 digits")
    if item["sku"] != item["item_id"]:
        errors.append("SKU must remain equal to immutable Item ID")
    if not photo_paths:
        errors.append("At least one product image is required")
    elif int(photo_paths[0]["photo_order"] or 0) != 1:
        errors.append("Front image F is missing")
    for photo in photo_paths:
        path = Path(photo["processed_path"] or "")
        if not path.is_file():
            errors.append(f"Missing processed image: {photo['proposed_name']}")
    return errors


def validate_items(db_file: Path, identifiers: list[str] | None = None) -> dict[str, list[str]]:
    selected = db.list_items(db_file)
    if identifiers is not None:
        wanted = set(identifiers)
        selected = [item for item in selected if item["item_id"] in wanted]
    prepared: list[tuple[dict[str, Any], list[str], str]] = []
    for item in selected:
        photos = db.get_item_photos(db_file, item["item_id"])
        errors = validation_errors(item, photos)
        if item["ready"]:
            status = "READY" if not errors else "BLOCKED"
        else:
            status = "INCOMPLETE"
        prepared.append((item, errors, status))

    results: dict[str, list[str]] = {}
    with db.transaction(db_file) as connection:
        for item, errors, status in prepared:
            connection.execute(
                "UPDATE items SET validation_status=?, validation_errors=?, updated_at=? WHERE item_id=?",
                (
                    status, json.dumps(errors), datetime.now().isoformat(timespec="seconds"),
                    item["item_id"],
                ),
            )
            results[item["item_id"]] = errors
    return results


def export_audit_csv(db_file: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with db.connect(db_file) as connection, destination.open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        rows = connection.execute(
            """
            SELECT e.*, i.sku, i.title FROM inventory_events e
            JOIN items i ON i.item_id=e.item_id
            ORDER BY e.occurred_at, e.inventory_event_id
            """
        ).fetchall()
        fields = list(rows[0].keys()) if rows else ["inventory_event_id"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)
    return destination
