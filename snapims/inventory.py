from __future__ import annotations

import csv
import json
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from snapims import db
from snapims.config import DataPaths
from snapims.catalog.service import catalog_output_for_item
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
    "Local Movie ID", "Canonical Movie title", "Original Movie title",
    "Film release year", "Runtime minutes", "Director", "Country", "Language",
    "Genre", "Catalog match status", "Source page URL", "Provenance status",
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
        paths = DataPaths.from_root(db_file.parent.parent).ensure()
        for item in rows:
            image_folder = str(Path(item["front_image"]).parent) if item.get("front_image") else ""
            try:
                movie = catalog_output_for_item(paths, item["item_id"])
            except Exception:
                movie = {
                    "movie_id": "", "canonical_title": "", "original_title": "",
                    "release_year": None, "runtime_minutes": None, "directors": [],
                    "countries": [], "languages": [], "genres": [],
                    "catalog_match_status": "CATALOG_UNAVAILABLE",
                    "source_page_url": "", "provenance_status": "UNAVAILABLE",
                }
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
                "Local Movie ID": movie["movie_id"],
                "Canonical Movie title": movie["canonical_title"],
                "Original Movie title": movie["original_title"],
                "Film release year": movie["release_year"] or "",
                "Runtime minutes": movie["runtime_minutes"] or "",
                "Director": "; ".join(movie["directors"]),
                "Country": "; ".join(movie["countries"]),
                "Language": "; ".join(movie["languages"]),
                "Genre": "; ".join(movie["genres"]),
                "Catalog match status": movie["catalog_match_status"],
                "Source page URL": movie["source_page_url"],
                "Provenance status": movie["provenance_status"],
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


def preview_inventory_csv(
    db_file: Path,
    batch_id: str,
    csv_text: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """Parse a SnapIMS CSV without mutating the working batch."""
    import io

    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    fields = reader.fieldnames or []
    blocking: list[str] = []
    for required in ("Item ID",):
        if required not in fields:
            blocking.append(f"Missing required CSV column: {required}")
    if blocking:
        return [], {"total_rows": 0, "matched": 0, "changed": 0}, blocking

    rows = list(reader)
    identifiers = [str(row.get("Item ID") or "").strip() for row in rows]
    if any(not identifier for identifier in identifiers):
        blocking.append("Every CSV row must contain an Item ID.")
    duplicate_ids = sorted({identifier for identifier in identifiers if identifiers.count(identifier) > 1})
    if duplicate_ids:
        blocking.append(f"Duplicate Item ID in CSV: {duplicate_ids[0]}")

    batch_items = {item["item_id"]: item for item in db.list_items(db_file, batch_id=batch_id)}
    all_items = {item["item_id"]: item for item in db.list_items(db_file)}
    staged: list[dict[str, Any]] = []
    field_counts: dict[str, int] = {}
    unmatched = 0
    changed_items = 0
    unchanged_items = 0

    editable_columns = [column for column in fields if column in COLUMN_MAP]
    if not editable_columns:
        blocking.append("CSV contains no editable SnapIMS columns")

    for row_number, row in enumerate(rows, start=2):
        item_id = str(row.get("Item ID") or "").strip()
        item = batch_items.get(item_id)
        row_errors: list[str] = []
        if not item:
            unmatched += 1
            if item_id in all_items:
                row_errors.append(f"Item belongs to another batch: {item_id}")
            else:
                row_errors.append(f"Unknown Item ID: {item_id}")
            staged.append(
                {
                    "row_number": row_number,
                    "item_id": item_id,
                    "title": str(row.get("Title") or ""),
                    "updates": {},
                    "changes": [],
                    "errors": row_errors,
                }
            )
            continue

        csv_batch = str(row.get("Batch ID") or "").strip()
        if csv_batch and csv_batch != batch_id:
            row_errors.append(f"Batch ID {csv_batch} does not match {batch_id}")

        csv_sku = str(row.get("SKU") or "").strip()
        if csv_sku and csv_sku != item_id:
            row_errors.append("SKU must remain equal to immutable Item ID")

        updates: dict[str, Any] = {}
        changes: list[dict[str, Any]] = []
        for column in editable_columns:
            raw = str(row.get(column) or "")
            try:
                value = COLUMN_MAP[column][1](raw)
            except (ValueError, TypeError, CSVImportError):
                row_errors.append(f"Invalid {column}: {raw!r}")
                continue
            field_name = COLUMN_MAP[column][0]
            updates[field_name] = value
            if item.get(field_name) != value:
                changes.append(
                    {
                        "column": column,
                        "field": field_name,
                        "old": item.get(field_name),
                        "new": value,
                    }
                )
                field_counts[column] = field_counts.get(column, 0) + 1

        candidate = {**item, **updates}
        candidate_errors = validation_errors(candidate, db.get_item_photos(db_file, item_id))
        # Empty titles and invalid prices are blocking for external review and publishing.
        row_errors.extend(error for error in candidate_errors if error not in row_errors)
        if changes:
            changed_items += 1
        else:
            unchanged_items += 1
        staged.append(
            {
                "row_number": row_number,
                "item_id": item_id,
                "title": item.get("title") or str(row.get("Title") or ""),
                "thumbnail": item.get("front_thumbnail") or "",
                "updates": updates,
                "changes": changes,
                "errors": row_errors,
            }
        )

    blocking.extend(
        error
        for staged_row in staged
        for error in staged_row["errors"]
        if error not in blocking
    )
    missing = sorted(set(batch_items) - set(identifiers))
    summary = {
        "total_rows": len(rows),
        "matched": len(rows) - unmatched,
        "unmatched": unmatched,
        "items_added": unmatched,
        "items_missing": len(missing),
        "missing_item_ids": missing,
        "changed": changed_items,
        "unchanged": unchanged_items,
        "field_counts": field_counts,
        "blocking_errors": len(blocking),
        "total_edits": sum(len(row["changes"]) for row in staged),
    }
    return staged, summary, blocking


def apply_staged_csv(
    db_file: Path,
    token: str,
    *,
    paths: DataPaths | None = None,
) -> tuple[str, int, int]:
    stage = db.get_csv_staging(db_file, token)
    if stage is None:
        raise CSVImportError("CSV preview expired or no longer exists")
    if stage["blocking_errors"]:
        raise CSVImportError("Resolve blocking CSV errors before applying changes")
    batch_id = str(stage["batch_id"])
    if paths:
        db.backup_database(paths, "before-csv-apply")
    checkpoint_id = db.create_batch_checkpoint(
        db_file,
        batch_id,
        reason=f"Before CSV upload {stage['filename']}",
        source="CSV_UPLOAD",
    )
    changed = 0
    identifiers: list[str] = []
    for row in stage["payload"]:
        if row["errors"] or not row["updates"]:
            continue
        item_id = row["item_id"]
        identifiers.append(item_id)
        updates = dict(row["updates"])
        updates["working_source"] = "CSV_UPLOAD"
        db.update_item(
            db_file,
            item_id,
            updates,
            source="CSV_UPLOAD",
            reason=f"CSV upload: {stage['filename']}",
        )
        if row["changes"]:
            changed += 1
    validate_items(db_file, identifiers)
    db.delete_csv_staging(db_file, token)
    return batch_id, changed, checkpoint_id


def mark_batch_externally_reviewed(db_file: Path, batch_id: str) -> tuple[int, list[str]]:
    items = db.list_items(db_file, batch_id=batch_id)
    blockers: list[str] = []
    valid_ids: list[str] = []
    for item in items:
        errors = validation_errors(item, db.get_item_photos(db_file, item["item_id"]))
        if errors:
            blockers.extend(f"{item['item_id']}: {error}" for error in errors)
        else:
            valid_ids.append(item["item_id"])
    if blockers:
        return 0, blockers
    db.create_batch_checkpoint(
        db_file,
        batch_id,
        reason="Before external CSV review confirmation",
        source="CSV_EXTERNAL_REVIEW",
    )
    for item_id in valid_ids:
        db.update_item(
            db_file,
            item_id,
            {
                "ready": 1,
                "review_status": "DONE",
                "validation_status": "READY",
                "validation_errors": "[]",
                "review_source": "CSV_EXTERNAL_REVIEW",
                "working_source": "CSV_UPLOAD",
            },
            source="CSV_EXTERNAL_REVIEW",
        )
    db.upsert_recognition_job(db_file, batch_id, status="REVIEW_COMPLETE")
    return len(valid_ids), []
