from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from snapims.config import DataPaths

SCHEMA_VERSION = 5


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def connect(db_file: Path) -> sqlite3.Connection:
    db_file.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_file, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


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
    safe = "".join(character if character.isalnum() else "-" for character in reason).strip("-")
    destination = paths.backups / f"inventory-{datetime.now():%Y%m%d-%H%M%S-%f}-{safe or 'backup'}.sqlite3"
    source = connect(paths.db_file)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return destination


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _add_column(connection: sqlite3.Connection, table: str, definition: str) -> None:
    name = definition.split()[0]
    if name not in _columns(connection, table):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _base_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
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
            release_year INTEGER,
            edition TEXT NOT NULL DEFAULT '',
            distributor TEXT NOT NULL DEFAULT '',
            price_cents INTEGER,
            discount_percent REAL NOT NULL DEFAULT 0,
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
            review_status TEXT NOT NULL DEFAULT 'UNFINISHED',
            postponed_at TEXT,
            recognition_provider TEXT NOT NULL DEFAULT '',
            recognition_confidence REAL,
            recognition_status TEXT NOT NULL DEFAULT 'PENDING',
            recognition_error TEXT NOT NULL DEFAULT '',
            upload_status TEXT NOT NULL DEFAULT 'NOT_UPLOADED',
            shopify_product_id TEXT NOT NULL DEFAULT '',
            shopify_variant_id TEXT NOT NULL DEFAULT '',
            shopify_inventory_item_id TEXT NOT NULL DEFAULT '',
            shopify_admin_url TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            retry_count INTEGER NOT NULL DEFAULT 0,
            record_revision INTEGER NOT NULL DEFAULT 0,
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
            suggested_price_cents INTEGER,
            suggested_discount_percent REAL NOT NULL DEFAULT 0,
            confidence REAL NOT NULL DEFAULT 0,
            uncertainty_reasons_json TEXT NOT NULL DEFAULT '[]',
            raw_response_reference TEXT NOT NULL DEFAULT '',
            requires_review INTEGER NOT NULL DEFAULT 1,
            accepted_at TEXT
        );
        CREATE TABLE IF NOT EXISTS recognition_jobs (
            batch_id TEXT PRIMARY KEY REFERENCES batches(batch_id) ON DELETE RESTRICT,
            provider TEXT NOT NULL DEFAULT 'mock',
            status TEXT NOT NULL DEFAULT 'READY',
            total INTEGER NOT NULL DEFAULT 0,
            completed INTEGER NOT NULL DEFAULT 0,
            recognized INTEGER NOT NULL DEFAULT 0,
            failed INTEGER NOT NULL DEFAULT 0,
            current_item_id TEXT NOT NULL DEFAULT '',
            started_at TEXT,
            updated_at TEXT NOT NULL,
            finished_at TEXT
        );
        CREATE TABLE IF NOT EXISTS review_cursors (
            batch_id TEXT NOT NULL REFERENCES batches(batch_id) ON DELETE RESTRICT,
            queue TEXT NOT NULL,
            item_id TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY(batch_id, queue)
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
            idempotency_key TEXT NOT NULL DEFAULT '',
            last_completed_step TEXT NOT NULL DEFAULT ''
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
        CREATE INDEX IF NOT EXISTS idx_items_review ON items(batch_id, review_status, sequence);
        CREATE INDEX IF NOT EXISTS idx_photos_item ON photos(item_id, photo_order);
        CREATE INDEX IF NOT EXISTS idx_recognition_item ON recognition_results(item_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_inventory_item ON inventory_events(item_id, occurred_at);
        """
    )


def _upgrade_legacy(connection: sqlite3.Connection) -> None:
    if "items" not in {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        return
    additions = [
        "release_year INTEGER",
        "discount_percent REAL NOT NULL DEFAULT 0",
        "review_status TEXT NOT NULL DEFAULT 'UNFINISHED'",
        "postponed_at TEXT",
        "recognition_status TEXT NOT NULL DEFAULT 'PENDING'",
        "recognition_error TEXT NOT NULL DEFAULT ''",
        "record_revision INTEGER NOT NULL DEFAULT 0",
    ]
    for definition in additions:
        _add_column(connection, "items", definition)
    if "recognition_results" in {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        _add_column(connection, "recognition_results", "suggested_price_cents INTEGER")
        _add_column(connection, "recognition_results", "suggested_discount_percent REAL NOT NULL DEFAULT 0")
    if "shopify_sync" in {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        _add_column(connection, "shopify_sync", "last_completed_step TEXT NOT NULL DEFAULT ''")


def initialize(db_file: Path, *, paths: DataPaths | None = None) -> None:
    db_file.parent.mkdir(parents=True, exist_ok=True)
    if db_file.exists() and paths is not None:
        with connect(db_file) as probe:
            current = int(probe.execute("PRAGMA user_version").fetchone()[0])
        if current < SCHEMA_VERSION:
            backup_database(paths, f"before-schema-v{SCHEMA_VERSION}")
    with transaction(db_file) as connection:
        _base_schema(connection)
        _upgrade_legacy(connection)
        connection.execute(
            "INSERT OR REPLACE INTO schema_migrations(version, applied_at, description) VALUES(?, ?, ?)",
            (SCHEMA_VERSION, now(), "SnapIMS v0.5.0 reconstruction schema"),
        )
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    with connect(db_file) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
    if integrity != "ok" or foreign:
        raise RuntimeError(f"Migration integrity failure: integrity={integrity}, foreign_keys={len(foreign)}")


def get_setting(db_file: Path, key: str, default: str = "") -> str:
    initialize(db_file)
    with connect(db_file) as connection:
        row = connection.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return str(row[0]) if row else default


def set_setting(db_file: Path, key: str, value: str) -> None:
    initialize(db_file)
    with transaction(db_file) as connection:
        connection.execute(
            "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, now()),
        )


def recent_folders(db_file: Path, *, limit: int = 5) -> list[str]:
    raw = get_setting(db_file, "recent_import_folders", "[]")
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        values = []
    return [str(value) for value in values if isinstance(value, str)][:limit]


def remember_folder(db_file: Path, folder: Path, *, limit: int = 5) -> None:
    resolved = str(folder.expanduser().resolve())
    values = [resolved, *[value for value in recent_folders(db_file, limit=limit) if value != resolved]]
    set_setting(db_file, "recent_import_folders", json.dumps(values[:limit]))


def list_batches(db_file: Path) -> list[dict[str, Any]]:
    initialize(db_file)
    with connect(db_file) as connection:
        rows = connection.execute("SELECT * FROM batches ORDER BY imported_at DESC").fetchall()
    return [dict(row) for row in rows]


def get_batch(db_file: Path, batch_id: str) -> dict[str, Any] | None:
    initialize(db_file)
    with connect(db_file) as connection:
        row = connection.execute("SELECT * FROM batches WHERE batch_id=?", (batch_id,)).fetchone()
    return dict(row) if row else None


def find_batch_by_fingerprint(db_file: Path, fingerprint: str) -> dict[str, Any] | None:
    initialize(db_file)
    with connect(db_file) as connection:
        row = connection.execute("SELECT * FROM batches WHERE source_fingerprint=?", (fingerprint,)).fetchone()
    return dict(row) if row else None


def list_items(db_file: Path, *, batch_id: str | None = None, queue: str = "ALL") -> list[dict[str, Any]]:
    initialize(db_file)
    clauses: list[str] = []
    values: list[Any] = []
    if batch_id:
        clauses.append("i.batch_id=?")
        values.append(batch_id)
    if queue == "UNRESOLVED":
        clauses.append("i.review_status='UNFINISHED'")
    elif queue == "DONE":
        clauses.append("i.review_status='DONE'")
    elif queue == "FAILED":
        clauses.append("i.recognition_status='FAILED'")
    elif queue == "READY":
        clauses.append("i.ready=1 AND i.validation_status='READY'")
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    query = f"""
        SELECT i.*, COUNT(p.photo_id) AS image_count,
               MIN(CASE WHEN p.photo_order=1 THEN p.thumbnail_path END) AS front_thumbnail,
               MIN(CASE WHEN p.photo_order=1 THEN p.processed_path END) AS front_image
        FROM items i LEFT JOIN photos p ON p.item_id=i.item_id AND p.kind='product'
        {where}
        GROUP BY i.item_id
        ORDER BY i.sequence
    """
    with connect(db_file) as connection:
        rows = connection.execute(query, values).fetchall()
    return [dict(row) for row in rows]


def get_item(db_file: Path, item_id: str) -> dict[str, Any] | None:
    initialize(db_file)
    with connect(db_file) as connection:
        row = connection.execute(
            """
            SELECT i.*, COUNT(p.photo_id) AS image_count,
                   MIN(CASE WHEN p.photo_order=1 THEN p.thumbnail_path END) AS front_thumbnail,
                   MIN(CASE WHEN p.photo_order=1 THEN p.processed_path END) AS front_image
            FROM items i LEFT JOIN photos p ON p.item_id=i.item_id AND p.kind='product'
            WHERE i.item_id=? GROUP BY i.item_id
            """,
            (item_id,),
        ).fetchone()
    return dict(row) if row else None


def get_item_photos(db_file: Path, item_id: str) -> list[dict[str, Any]]:
    initialize(db_file)
    with connect(db_file) as connection:
        rows = connection.execute("SELECT * FROM photos WHERE item_id=? ORDER BY photo_order", (item_id,)).fetchall()
    return [dict(row) for row in rows]


EDITABLE_FIELDS = {
    "shelf", "title", "release_year", "edition", "distributor", "price_cents",
    "discount_percent", "description", "vendor", "product_type", "tags", "barcode",
    "condition", "condition_notes", "pool_mode", "quantity", "ready", "review",
    "review_status", "postponed_at", "recognition_provider", "recognition_confidence",
    "recognition_status", "recognition_error", "validation_status", "validation_errors",
}


def update_item(
    db_file: Path,
    item_id: str,
    values: dict[str, Any],
    *,
    source: str = "ITEM_EDITOR",
    reason: str = "",
    expected_revision: int | None = None,
) -> None:
    updates = {key: value for key, value in values.items() if key in EDITABLE_FIELDS}
    if not updates:
        return
    with transaction(db_file) as connection:
        previous = connection.execute("SELECT * FROM items WHERE item_id=?", (item_id,)).fetchone()
        if previous is None:
            raise KeyError(f"Unknown Item ID: {item_id}")
        if expected_revision is not None and int(previous["record_revision"]) != expected_revision:
            raise RuntimeError("This item changed in another session. Reload before saving.")
        updates["updated_at"] = now()
        assignments = ", ".join(f"{key}=?" for key in updates)
        cursor = connection.execute(
            f"UPDATE items SET {assignments}, record_revision=record_revision+1 WHERE item_id=?",
            [*updates.values(), item_id],
        )
        if cursor.rowcount != 1:
            raise KeyError(f"Unknown Item ID: {item_id}")
        if "shelf" in updates and updates["shelf"] != previous["shelf"]:
            if not reason.strip():
                raise ValueError("A reason is required when changing shelf location.")
            connection.execute(
                """INSERT INTO inventory_events(item_id,batch_id,occurred_at,event_type,from_location,to_location,source,notes)
                   VALUES(?,?,?,'LOCATION_CHANGED',?,?,?,?)""",
                (item_id, previous["batch_id"], now(), previous["shelf"], updates["shelf"], source, reason.strip()),
            )
        if "quantity" in updates and int(updates["quantity"]) != int(previous["quantity"]):
            connection.execute(
                """INSERT INTO inventory_events(item_id,batch_id,occurred_at,event_type,to_location,quantity_delta,source,notes)
                   VALUES(?,?,?,'QUANTITY_ADJUSTED',?,?,?,?)""",
                (
                    item_id, previous["batch_id"], now(), updates.get("shelf", previous["shelf"]),
                    int(updates["quantity"]) - int(previous["quantity"]), source, reason.strip(),
                ),
            )


def latest_recognition(db_file: Path, item_id: str) -> dict[str, Any] | None:
    with connect(db_file) as connection:
        row = connection.execute(
            "SELECT * FROM recognition_results WHERE item_id=? ORDER BY recognition_result_id DESC LIMIT 1",
            (item_id,),
        ).fetchone()
    return dict(row) if row else None


def recognition_history(db_file: Path, item_id: str) -> list[dict[str, Any]]:
    with connect(db_file) as connection:
        rows = connection.execute(
            "SELECT * FROM recognition_results WHERE item_id=? ORDER BY recognition_result_id DESC", (item_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def get_cursor(db_file: Path, batch_id: str, queue: str) -> str:
    with connect(db_file) as connection:
        row = connection.execute(
            "SELECT item_id FROM review_cursors WHERE batch_id=? AND queue=?", (batch_id, queue)
        ).fetchone()
    return str(row[0]) if row else ""


def set_cursor(db_file: Path, batch_id: str, queue: str, item_id: str) -> None:
    with transaction(db_file) as connection:
        connection.execute(
            """INSERT INTO review_cursors(batch_id,queue,item_id,updated_at) VALUES(?,?,?,?)
               ON CONFLICT(batch_id,queue) DO UPDATE SET item_id=excluded.item_id,updated_at=excluded.updated_at""",
            (batch_id, queue, item_id, now()),
        )


def get_recognition_job(db_file: Path, batch_id: str) -> dict[str, Any] | None:
    initialize(db_file)
    with connect(db_file) as connection:
        row = connection.execute("SELECT * FROM recognition_jobs WHERE batch_id=?", (batch_id,)).fetchone()
    return dict(row) if row else None


def upsert_recognition_job(db_file: Path, batch_id: str, **values: Any) -> None:
    current = get_recognition_job(db_file, batch_id)
    fields = {**(current or {}), **values, "batch_id": batch_id, "updated_at": now()}
    allowed = {
        "batch_id", "provider", "status", "total", "completed", "recognized", "failed",
        "current_item_id", "started_at", "updated_at", "finished_at",
    }
    fields = {key: value for key, value in fields.items() if key in allowed}
    columns = list(fields)
    placeholders = ",".join("?" for _ in columns)
    updates = ",".join(f"{column}=excluded.{column}" for column in columns if column != "batch_id")
    with transaction(db_file) as connection:
        connection.execute(
            f"INSERT INTO recognition_jobs({','.join(columns)}) VALUES({placeholders}) ON CONFLICT(batch_id) DO UPDATE SET {updates}",
            [fields[column] for column in columns],
        )


def mark_interrupted_jobs_paused(db_file: Path) -> int:
    initialize(db_file)
    with transaction(db_file) as connection:
        cursor = connection.execute(
            "UPDATE recognition_jobs SET status='PAUSED',updated_at=? WHERE status='RUNNING'", (now(),)
        )
    return cursor.rowcount


def database_summary(db_file: Path) -> dict[str, int]:
    initialize(db_file)
    tables = ["batches", "items", "photos", "recognition_results", "inventory_events"]
    with connect(db_file) as connection:
        return {table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}
