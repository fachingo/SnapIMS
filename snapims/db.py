from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from snapims.config import DataPaths
from snapims.manifests import item_id
from snapims.models import BatchRecord, ProcessedPhoto
from snapims.protocol import parse_command

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS batches (
    batch_id TEXT PRIMARY KEY,
    source_fingerprint TEXT NOT NULL UNIQUE,
    source_folder TEXT NOT NULL,
    created_at TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    started INTEGER NOT NULL,
    ended INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'IMPORTED',
    item_count INTEGER NOT NULL,
    product_photo_count INTEGER NOT NULL,
    command_count INTEGER NOT NULL,
    warning_count INTEGER NOT NULL,
    warnings_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS items (
    item_id TEXT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    batch_id TEXT NOT NULL REFERENCES batches(batch_id) ON DELETE RESTRICT,
    sequence INTEGER NOT NULL,
    shelf TEXT NOT NULL,
    rare INTEGER NOT NULL DEFAULT 0,
    review INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '',
    edition TEXT NOT NULL DEFAULT '',
    distributor TEXT NOT NULL DEFAULT '',
    price_cents INTEGER,
    description TEXT NOT NULL DEFAULT '',
    vendor TEXT NOT NULL DEFAULT 'Canada VHS',
    product_type TEXT NOT NULL DEFAULT 'VHS Tape',
    tags TEXT NOT NULL DEFAULT '',
    barcode TEXT NOT NULL DEFAULT '',
    condition TEXT NOT NULL DEFAULT 'Not Graded',
    condition_notes TEXT NOT NULL DEFAULT '',
    pool_mode TEXT NOT NULL DEFAULT 'POOLED',
    quantity INTEGER NOT NULL DEFAULT 1,
    ready INTEGER NOT NULL DEFAULT 0,
    validation_status TEXT NOT NULL DEFAULT 'INCOMPLETE',
    validation_errors TEXT NOT NULL DEFAULT '[]',
    recognition_provider TEXT NOT NULL DEFAULT '',
    recognition_confidence REAL,
    upload_status TEXT NOT NULL DEFAULT 'NOT_UPLOADED',
    shopify_product_id TEXT NOT NULL DEFAULT '',
    shopify_variant_id TEXT NOT NULL DEFAULT '',
    shopify_inventory_item_id TEXT NOT NULL DEFAULT '',
    shopify_admin_url TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(batch_id, sequence)
);

CREATE TABLE IF NOT EXISTS photos (
    photo_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL REFERENCES batches(batch_id) ON DELETE RESTRICT,
    item_id TEXT REFERENCES items(item_id) ON DELETE RESTRICT,
    kind TEXT NOT NULL CHECK(kind IN ('product', 'command', 'excluded')),
    stream_index INTEGER NOT NULL,
    photo_order INTEGER,
    original_name TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    timestamp_source TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    qr_payload TEXT,
    source_path TEXT NOT NULL,
    original_copy_path TEXT NOT NULL,
    proposed_name TEXT NOT NULL,
    processed_path TEXT,
    thumbnail_path TEXT,
    UNIQUE(batch_id, stream_index)
);

CREATE TABLE IF NOT EXISTS command_events (
    command_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL REFERENCES batches(batch_id) ON DELETE RESTRICT,
    stream_index INTEGER NOT NULL,
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    command_kind TEXT NOT NULL,
    command_value TEXT,
    source_photo_id INTEGER REFERENCES photos(photo_id) ON DELETE RESTRICT,
    warning TEXT NOT NULL DEFAULT '',
    UNIQUE(batch_id, stream_index)
);

CREATE TABLE IF NOT EXISTS recognition_results (
    recognition_result_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL REFERENCES items(item_id) ON DELETE RESTRICT,
    provider TEXT NOT NULL,
    created_at TEXT NOT NULL,
    suggested_title TEXT NOT NULL DEFAULT '',
    edition TEXT NOT NULL DEFAULT '',
    distributor TEXT NOT NULL DEFAULT '',
    release_year INTEGER,
    barcode_candidates_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0,
    uncertainty_reasons_json TEXT NOT NULL DEFAULT '[]',
    raw_response_reference TEXT NOT NULL DEFAULT '',
    requires_review INTEGER NOT NULL DEFAULT 1,
    accepted_at TEXT
);

CREATE TABLE IF NOT EXISTS catalog_products (
    catalog_product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_title TEXT NOT NULL,
    edition TEXT NOT NULL DEFAULT '',
    distributor TEXT NOT NULL DEFAULT '',
    release_year INTEGER,
    barcode TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(canonical_title, edition, distributor, barcode)
);

CREATE TABLE IF NOT EXISTS inventory_events (
    inventory_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL REFERENCES items(item_id) ON DELETE RESTRICT,
    batch_id TEXT REFERENCES batches(batch_id) ON DELETE RESTRICT,
    occurred_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    from_location TEXT,
    to_location TEXT,
    quantity_delta INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS shopify_sync (
    item_id TEXT PRIMARY KEY REFERENCES items(item_id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'NOT_UPLOADED',
    product_id TEXT NOT NULL DEFAULT '',
    variant_id TEXT NOT NULL DEFAULT '',
    inventory_item_id TEXT NOT NULL DEFAULT '',
    admin_url TEXT NOT NULL DEFAULT '',
    media_count INTEGER NOT NULL DEFAULT 0,
    last_synced_at TEXT,
    last_error TEXT NOT NULL DEFAULT '',
    retry_count INTEGER NOT NULL DEFAULT 0,
    idempotency_key TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS upload_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL REFERENCES items(item_id) ON DELETE RESTRICT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    step TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    response_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_items_batch ON items(batch_id, sequence);
CREATE INDEX IF NOT EXISTS idx_items_shelf ON items(shelf, item_id);
CREATE INDEX IF NOT EXISTS idx_items_upload ON items(upload_status, ready);
CREATE INDEX IF NOT EXISTS idx_photos_item ON photos(item_id, photo_order);
CREATE INDEX IF NOT EXISTS idx_commands_batch ON command_events(batch_id, stream_index);
CREATE INDEX IF NOT EXISTS idx_recognition_item ON recognition_results(item_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_inventory_item ON inventory_events(item_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_inventory_location ON inventory_events(to_location, occurred_at);
"""
MIGRATIONS = (
    (1, "Initial event-sourced SnapIMS prototype schema", SCHEMA_SQL),
)
SCHEMA_VERSION = MIGRATIONS[-1][0]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect(db_file: Path) -> sqlite3.Connection:
    db_file.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_file, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize(db_file: Path) -> None:
    with connect(db_file) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL,
                description TEXT NOT NULL
            )
            """
        )
        applied = {
            row[0] for row in connection.execute("SELECT version FROM schema_migrations")
        }
        for version, description, sql in MIGRATIONS:
            if version in applied:
                continue
            connection.executescript(sql)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at, description) VALUES(?, ?, ?)",
                (version, _now(), description),
            )
            connection.execute(f"PRAGMA user_version = {version}")


@contextmanager
def transaction(db_file: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(db_file)
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def backup_database(paths: DataPaths, reason: str) -> Path | None:
    if not paths.db_file.exists():
        return None
    paths.backups.mkdir(parents=True, exist_ok=True)
    safe_reason = "".join(c if c.isalnum() else "-" for c in reason).strip("-") or "backup"
    destination = paths.backups / (
        f"inventory-{datetime.now():%Y%m%d-%H%M%S-%f}-{safe_reason}.sqlite3"
    )
    source = connect(paths.db_file)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return destination


def find_batch_by_fingerprint(db_file: Path, fingerprint: str) -> dict[str, Any] | None:
    initialize(db_file)
    with connect(db_file) as connection:
        row = connection.execute(
            "SELECT * FROM batches WHERE source_fingerprint = ?", (fingerprint,)
        ).fetchone()
    return dict(row) if row else None


def batch_exists(db_file: Path, batch_id: str) -> bool:
    initialize(db_file)
    with connect(db_file) as connection:
        return connection.execute(
            "SELECT 1 FROM batches WHERE batch_id = ?", (batch_id,)
        ).fetchone() is not None


def insert_batch(
    db_file: Path,
    batch: BatchRecord,
    artifacts: list[ProcessedPhoto],
) -> None:
    initialize(db_file)
    timestamp = _now()
    with transaction(db_file) as connection:
        connection.execute(
            """
            INSERT INTO batches(
                batch_id, source_fingerprint, source_folder, created_at, imported_at,
                started, ended, item_count, product_photo_count, command_count,
                warning_count, warnings_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch.batch_id, batch.source_fingerprint, str(batch.source_folder),
                batch.created_at.isoformat(), timestamp, int(batch.started), int(batch.ended),
                len(batch.items), batch.photo_count, len(batch.commands), len(batch.warnings),
                json.dumps(batch.warnings),
            ),
        )
        for item in batch.items:
            iid = item_id(batch.batch_id, item.shelf, item.sequence)
            connection.execute(
                """
                INSERT INTO items(
                    item_id, sku, batch_id, sequence, shelf, rare, review, pool_mode,
                    created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    iid, iid, batch.batch_id, item.sequence, item.shelf,
                    int(item.rare), int(item.review), "UNIQUE" if item.rare else "POOLED",
                    timestamp, timestamp,
                ),
            )
            connection.execute(
                "INSERT INTO shopify_sync(item_id) VALUES(?)", (iid,)
            )
            connection.execute(
                """
                INSERT INTO inventory_events(
                    item_id, batch_id, occurred_at, event_type, to_location,
                    quantity_delta, source, notes
                ) VALUES(?, ?, ?, 'ITEM_INTAKE', ?, 1, 'QR_BATCH', ?)
                """,
                (iid, batch.batch_id, timestamp, item.shelf, f"Imported as sequence {item.sequence}"),
            )
        photo_ids: dict[int, int] = {}
        for artifact in artifacts:
            cursor = connection.execute(
                """
                INSERT INTO photos(
                    batch_id, item_id, kind, stream_index, photo_order, original_name,
                    captured_at, timestamp_source, sha256, qr_payload, source_path,
                    original_copy_path, proposed_name, processed_path, thumbnail_path
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch.batch_id, artifact.item_id, artifact.kind,
                    artifact.source.stream_index, artifact.photo_order,
                    artifact.source.original_name, artifact.source.captured_at.isoformat(),
                    artifact.source.timestamp_source, artifact.source.sha256 or "",
                    artifact.source.qr_payload, str(artifact.source.path),
                    str(artifact.original_copy_path), artifact.proposed_name,
                    str(artifact.processed_path) if artifact.processed_path else None,
                    str(artifact.thumbnail_path) if artifact.thumbnail_path else None,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a photo row ID")
            photo_ids[artifact.source.stream_index] = cursor.lastrowid

        for command_photo in batch.commands:
            command = parse_command(command_photo.qr_payload or "")
            if command is None:
                continue
            connection.execute(
                """
                INSERT INTO command_events(
                    batch_id, stream_index, occurred_at, payload, command_kind,
                    command_value, source_photo_id
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch.batch_id, command_photo.stream_index,
                    command_photo.captured_at.isoformat(), command.payload,
                    command.kind.value, command.value, photo_ids.get(command_photo.stream_index),
                ),
            )


def list_batches(db_file: Path) -> list[dict[str, Any]]:
    initialize(db_file)
    with connect(db_file) as connection:
        rows = connection.execute("SELECT * FROM batches ORDER BY imported_at DESC").fetchall()
    return [dict(row) for row in rows]


def get_batch(db_file: Path, batch_id_value: str) -> dict[str, Any] | None:
    initialize(db_file)
    with connect(db_file) as connection:
        row = connection.execute(
            "SELECT * FROM batches WHERE batch_id = ?", (batch_id_value,)
        ).fetchone()
    return dict(row) if row else None


def list_items(
    db_file: Path, *, batch_id_value: str | None = None, status: str | None = None
) -> list[dict[str, Any]]:
    initialize(db_file)
    clauses: list[str] = []
    parameters: list[Any] = []
    if batch_id_value:
        clauses.append("i.batch_id = ?")
        parameters.append(batch_id_value)
    if status:
        if status == "READY":
            clauses.append("i.ready = 1 AND i.validation_status = 'READY'")
        elif status == "BLOCKED":
            clauses.append("i.validation_status = 'BLOCKED'")
        else:
            clauses.append("i.upload_status = ?")
            parameters.append(status)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    query = f"""
        SELECT i.*, COUNT(p.photo_id) AS image_count,
               MIN(CASE WHEN p.photo_order = 1 THEN p.thumbnail_path END) AS front_thumbnail,
               MIN(CASE WHEN p.photo_order = 1 THEN p.processed_path END) AS front_image
        FROM items i
        LEFT JOIN photos p ON p.item_id = i.item_id AND p.kind = 'product'
        {where}
        GROUP BY i.item_id
        ORDER BY i.batch_id DESC, i.sequence
    """
    with connect(db_file) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


def get_item(db_file: Path, item_id_value: str) -> dict[str, Any] | None:
    items = list_items(db_file)
    return next((row for row in items if row["item_id"] == item_id_value), None)


def get_item_photos(db_file: Path, item_id_value: str) -> list[dict[str, Any]]:
    initialize(db_file)
    with connect(db_file) as connection:
        rows = connection.execute(
            "SELECT * FROM photos WHERE item_id = ? ORDER BY photo_order", (item_id_value,)
        ).fetchall()
    return [dict(row) for row in rows]


EDITABLE_FIELDS = {
    "shelf", "title", "edition", "distributor", "price_cents", "description", "vendor", "product_type",
    "tags", "barcode", "condition", "condition_notes", "pool_mode", "quantity", "ready", "review",
}


def update_item(db_file: Path, item_id_value: str, values: dict[str, Any]) -> None:
    updates = {key: value for key, value in values.items() if key in EDITABLE_FIELDS}
    if not updates:
        return
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{key} = ?" for key in updates)
    parameters = list(updates.values()) + [item_id_value]
    with transaction(db_file) as connection:
        previous = connection.execute(
            "SELECT batch_id, shelf, quantity FROM items WHERE item_id=?", (item_id_value,)
        ).fetchone()
        if previous is None:
            raise KeyError(f"Unknown Item ID: {item_id_value}")
        cursor = connection.execute(
            f"UPDATE items SET {assignments} WHERE item_id = ?", parameters
        )
        if cursor.rowcount != 1:
            raise KeyError(f"Unknown Item ID: {item_id_value}")
        changed_at = _now()
        if "shelf" in updates and updates["shelf"] != previous["shelf"]:
            connection.execute(
                """
                INSERT INTO inventory_events(
                    item_id, batch_id, occurred_at, event_type, from_location,
                    to_location, source, notes
                ) VALUES(?, ?, ?, 'LOCATION_CHANGED', ?, ?, 'ITEM_EDITOR', '')
                """,
                (
                    item_id_value,
                    previous["batch_id"],
                    changed_at,
                    previous["shelf"],
                    updates["shelf"],
                ),
            )
        if "quantity" in updates and int(updates["quantity"]) != int(previous["quantity"]):
            connection.execute(
                """
                INSERT INTO inventory_events(
                    item_id, batch_id, occurred_at, event_type, to_location,
                    quantity_delta, source, notes
                ) VALUES(?, ?, ?, 'QUANTITY_ADJUSTED', ?, ?, 'ITEM_EDITOR', '')
                """,
                (
                    item_id_value,
                    previous["batch_id"],
                    changed_at,
                    updates.get("shelf", previous["shelf"]),
                    int(updates["quantity"]) - int(previous["quantity"]),
                ),
            )


def set_validation(
    db_file: Path, item_id_value: str, status: str, errors: list[str]
) -> None:
    with transaction(db_file) as connection:
        connection.execute(
            "UPDATE items SET validation_status=?, validation_errors=?, updated_at=? WHERE item_id=?",
            (status, json.dumps(errors), _now(), item_id_value),
        )


def start_upload_attempt(db_file: Path, item_id_value: str) -> int:
    with transaction(db_file) as connection:
        cursor = connection.execute(
            "INSERT INTO upload_attempts(item_id, started_at, status) VALUES(?, ?, 'RUNNING')",
            (item_id_value, _now()),
        )
        connection.execute(
            "UPDATE items SET last_error='', updated_at=? WHERE item_id=?",
            (_now(), item_id_value),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return an upload attempt ID")
        return cursor.lastrowid


def set_upload_step(db_file: Path, attempt_id: int, step: str) -> None:
    with transaction(db_file) as connection:
        connection.execute(
            "UPDATE upload_attempts SET step=? WHERE attempt_id=?", (step, attempt_id)
        )


def save_shopify_checkpoint(
    db_file: Path,
    item_id_value: str,
    status: str,
    *,
    product_id: str = "",
    variant_id: str = "",
    inventory_item_id: str = "",
    idempotency_key: str = "",
) -> None:
    with transaction(db_file) as connection:
        connection.execute(
            """
            UPDATE items SET upload_status=?,
                shopify_product_id=CASE WHEN ?='' THEN shopify_product_id ELSE ? END,
                shopify_variant_id=CASE WHEN ?='' THEN shopify_variant_id ELSE ? END,
                shopify_inventory_item_id=CASE WHEN ?='' THEN shopify_inventory_item_id ELSE ? END,
                updated_at=? WHERE item_id=?
            """,
            (
                status, product_id, product_id, variant_id, variant_id,
                inventory_item_id, inventory_item_id, _now(), item_id_value,
            ),
        )
        connection.execute(
            """
            UPDATE shopify_sync SET status=?,
                product_id=CASE WHEN ?='' THEN product_id ELSE ? END,
                variant_id=CASE WHEN ?='' THEN variant_id ELSE ? END,
                inventory_item_id=CASE WHEN ?='' THEN inventory_item_id ELSE ? END,
                idempotency_key=CASE WHEN ?='' THEN idempotency_key ELSE ? END
            WHERE item_id=?
            """,
            (
                status, product_id, product_id, variant_id, variant_id,
                inventory_item_id, inventory_item_id, idempotency_key, idempotency_key,
                item_id_value,
            ),
        )


def finish_upload_success(
    db_file: Path,
    attempt_id: int,
    item_id_value: str,
    *,
    product_id: str,
    variant_id: str,
    inventory_item_id: str,
    admin_url: str,
    response: dict[str, Any],
) -> None:
    with transaction(db_file) as connection:
        connection.execute(
            "UPDATE upload_attempts SET finished_at=?, status='SUCCESS', response_json=? WHERE attempt_id=?",
            (_now(), json.dumps(response), attempt_id),
        )
        connection.execute(
            """
            UPDATE items SET upload_status='UPLOADED', shopify_product_id=?,
                shopify_variant_id=?, shopify_inventory_item_id=?, shopify_admin_url=?,
                last_error='', updated_at=? WHERE item_id=?
            """,
            (product_id, variant_id, inventory_item_id, admin_url, _now(), item_id_value),
        )
        connection.execute(
            """
            UPDATE shopify_sync SET status='UPLOADED', product_id=?, variant_id=?,
                inventory_item_id=?, admin_url=?, media_count=?, last_synced_at=?, last_error=''
            WHERE item_id=?
            """,
            (
                product_id,
                variant_id,
                inventory_item_id,
                admin_url,
                int(response.get("image_count", 0)),
                _now(),
                item_id_value,
            ),
        )


def finish_upload_failure(
    db_file: Path, attempt_id: int, item_id_value: str, step: str, error: str
) -> None:
    with transaction(db_file) as connection:
        connection.execute(
            """
            UPDATE upload_attempts SET finished_at=?, status='FAILED', step=?, error=?
            WHERE attempt_id=?
            """,
            (_now(), step, error, attempt_id),
        )
        connection.execute(
            """
            UPDATE items SET upload_status='FAILED', last_error=?, retry_count=retry_count+1,
                updated_at=? WHERE item_id=?
            """,
            (error, _now(), item_id_value),
        )
        connection.execute(
            """
            UPDATE shopify_sync SET status='FAILED', last_error=?, retry_count=retry_count+1
            WHERE item_id=?
            """,
            (error, item_id_value),
        )


def database_summary(db_file: Path) -> dict[str, int]:
    initialize(db_file)
    with connect(db_file) as connection:
        return {
            "batches": connection.execute("SELECT COUNT(*) FROM batches").fetchone()[0],
            "items": connection.execute("SELECT COUNT(*) FROM items").fetchone()[0],
            "ready": connection.execute(
                "SELECT COUNT(*) FROM items WHERE ready=1 AND validation_status='READY'"
            ).fetchone()[0],
            "uploaded": connection.execute(
                "SELECT COUNT(*) FROM items WHERE upload_status='UPLOADED'"
            ).fetchone()[0],
            "blocked": connection.execute(
                "SELECT COUNT(*) FROM items WHERE validation_status='BLOCKED'"
            ).fetchone()[0],
        }
