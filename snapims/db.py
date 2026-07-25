from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from snapims.config import DataPaths

SCHEMA_VERSION = 6


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
            review_source TEXT NOT NULL DEFAULT '',
            working_source TEXT NOT NULL DEFAULT 'IMPORT',
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
            preview_path TEXT,
            recognition_path TEXT,
            original_bytes INTEGER NOT NULL DEFAULT 0,
            preview_bytes INTEGER NOT NULL DEFAULT 0,
            recognition_bytes INTEGER NOT NULL DEFAULT 0,
            ai_eligible INTEGER NOT NULL DEFAULT 1,
            image_role TEXT NOT NULL DEFAULT 'unknown',
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
            pricing_source TEXT NOT NULL DEFAULT 'AI_ESTIMATE_NO_LIVE_MARKET_DATA',
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
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
            started_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            finished_at TEXT,
            model_name TEXT NOT NULL DEFAULT '',
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            error_at TEXT,
            last_success_at TEXT
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
        CREATE TABLE IF NOT EXISTS item_change_log (
            change_id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT NOT NULL REFERENCES items(item_id) ON DELETE RESTRICT,
            batch_id TEXT NOT NULL REFERENCES batches(batch_id) ON DELETE RESTRICT,
            field_name TEXT NOT NULL,
            old_value_json TEXT NOT NULL,
            new_value_json TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            source TEXT NOT NULL,
            revision INTEGER NOT NULL,
            notes TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS batch_checkpoints (
            checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL REFERENCES batches(batch_id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL,
            reason TEXT NOT NULL,
            source TEXT NOT NULL,
            item_count INTEGER NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS csv_staging (
            token TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL REFERENCES batches(batch_id) ON DELETE RESTRICT,
            filename TEXT NOT NULL,
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            diff_json TEXT NOT NULL,
            blocking_errors_json TEXT NOT NULL DEFAULT '[]'
        );
        CREATE INDEX IF NOT EXISTS idx_items_batch ON items(batch_id, sequence);
        CREATE INDEX IF NOT EXISTS idx_items_review ON items(batch_id, review_status, sequence);
        CREATE INDEX IF NOT EXISTS idx_photos_item ON photos(item_id, photo_order);
        CREATE INDEX IF NOT EXISTS idx_recognition_item ON recognition_results(item_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_inventory_item ON inventory_events(item_id, occurred_at);
        CREATE INDEX IF NOT EXISTS idx_item_change_log_item ON item_change_log(item_id, occurred_at DESC);
        CREATE INDEX IF NOT EXISTS idx_checkpoints_batch ON batch_checkpoints(batch_id, created_at DESC);
        """
    )


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


LEGACY_ITEM_ADDITIONS = [
    "release_year INTEGER",
    "edition TEXT NOT NULL DEFAULT ''",
    "distributor TEXT NOT NULL DEFAULT ''",
    "price_cents INTEGER",
    "discount_percent REAL NOT NULL DEFAULT 0",
    "description TEXT NOT NULL DEFAULT ''",
    "vendor TEXT NOT NULL DEFAULT 'Canada VHS'",
    "product_type TEXT NOT NULL DEFAULT 'VHS Tape'",
    "tags TEXT NOT NULL DEFAULT ''",
    "barcode TEXT NOT NULL DEFAULT ''",
    "condition TEXT NOT NULL DEFAULT 'Not Graded'",
    "condition_notes TEXT NOT NULL DEFAULT ''",
    "pool_mode TEXT NOT NULL DEFAULT 'POOLED'",
    "quantity INTEGER NOT NULL DEFAULT 1",
    "ready INTEGER NOT NULL DEFAULT 0",
    "validation_status TEXT NOT NULL DEFAULT 'INCOMPLETE'",
    "validation_errors TEXT NOT NULL DEFAULT '[]'",
    "review_status TEXT NOT NULL DEFAULT 'UNFINISHED'",
    "postponed_at TEXT",
    "recognition_provider TEXT NOT NULL DEFAULT ''",
    "recognition_confidence REAL",
    "recognition_status TEXT NOT NULL DEFAULT 'PENDING'",
    "recognition_error TEXT NOT NULL DEFAULT ''",
    "upload_status TEXT NOT NULL DEFAULT 'NOT_UPLOADED'",
    "shopify_product_id TEXT NOT NULL DEFAULT ''",
    "shopify_variant_id TEXT NOT NULL DEFAULT ''",
    "shopify_inventory_item_id TEXT NOT NULL DEFAULT ''",
    "shopify_admin_url TEXT NOT NULL DEFAULT ''",
    "last_error TEXT NOT NULL DEFAULT ''",
    "retry_count INTEGER NOT NULL DEFAULT 0",
    "record_revision INTEGER NOT NULL DEFAULT 0",
    "review_source TEXT NOT NULL DEFAULT ''",
    "working_source TEXT NOT NULL DEFAULT 'IMPORT'",
    "created_at TEXT NOT NULL DEFAULT ''",
    "updated_at TEXT NOT NULL DEFAULT ''",
]


def _upgrade_legacy(connection: sqlite3.Connection) -> None:
    tables = _table_names(connection)
    if "items" in tables:
        for definition in LEGACY_ITEM_ADDITIONS:
            _add_column(connection, "items", definition)
    if "photos" in tables:
        for definition in (
            "preview_path TEXT",
            "recognition_path TEXT",
            "original_bytes INTEGER NOT NULL DEFAULT 0",
            "preview_bytes INTEGER NOT NULL DEFAULT 0",
            "recognition_bytes INTEGER NOT NULL DEFAULT 0",
            "ai_eligible INTEGER NOT NULL DEFAULT 1",
            "image_role TEXT NOT NULL DEFAULT 'unknown'",
        ):
            _add_column(connection, "photos", definition)
    if "recognition_jobs" in tables:
        for definition in (
            "provider TEXT NOT NULL DEFAULT 'mock'",
            "status TEXT NOT NULL DEFAULT 'READY'",
            "total INTEGER NOT NULL DEFAULT 0",
            "completed INTEGER NOT NULL DEFAULT 0",
            "recognized INTEGER NOT NULL DEFAULT 0",
            "failed INTEGER NOT NULL DEFAULT 0",
            "current_item_id TEXT NOT NULL DEFAULT ''",
            "started_at TEXT",
            "updated_at TEXT NOT NULL DEFAULT ''",
            "finished_at TEXT",
            "model_name TEXT NOT NULL DEFAULT ''",
            "error_code TEXT NOT NULL DEFAULT ''",
            "error_message TEXT NOT NULL DEFAULT ''",
            "error_at TEXT",
            "last_success_at TEXT",
        ):
            _add_column(connection, "recognition_jobs", definition)
    if "recognition_results" in tables:
        for definition in (
            "pricing_source TEXT NOT NULL DEFAULT 'AI_ESTIMATE_NO_LIVE_MARKET_DATA'",
            "input_tokens INTEGER NOT NULL DEFAULT 0",
            "output_tokens INTEGER NOT NULL DEFAULT 0",
            "release_year INTEGER",
            "barcode_candidates_json TEXT NOT NULL DEFAULT '[]'",
            "suggested_price_cents INTEGER",
            "suggested_discount_percent REAL NOT NULL DEFAULT 0",
            "confidence REAL NOT NULL DEFAULT 0",
            "uncertainty_reasons_json TEXT NOT NULL DEFAULT '[]'",
            "raw_response_reference TEXT NOT NULL DEFAULT ''",
            "requires_review INTEGER NOT NULL DEFAULT 1",
            "accepted_at TEXT",
        ):
            _add_column(connection, "recognition_results", definition)
    if "shopify_sync" in tables:
        for definition in (
            "variant_id TEXT NOT NULL DEFAULT ''",
            "inventory_item_id TEXT NOT NULL DEFAULT ''",
            "admin_url TEXT NOT NULL DEFAULT ''",
            "media_count INTEGER NOT NULL DEFAULT 0",
            "last_synced_at TEXT",
            "last_error TEXT NOT NULL DEFAULT ''",
            "retry_count INTEGER NOT NULL DEFAULT 0",
            "idempotency_key TEXT NOT NULL DEFAULT ''",
            "last_completed_step TEXT NOT NULL DEFAULT ''",
        ):
            _add_column(connection, "shopify_sync", definition)


def _restore_database(db_file: Path, backup: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        Path(f"{db_file}{suffix}").unlink(missing_ok=True)
    db_file.unlink(missing_ok=True)
    shutil.copy2(backup, db_file)


def initialize(db_file: Path, *, paths: DataPaths | None = None) -> None:
    db_file.parent.mkdir(parents=True, exist_ok=True)
    current = 0
    existing = db_file.exists() and db_file.stat().st_size > 0
    if existing:
        # Probe with a plain read-only connection so refusing a future schema does not
        # switch journal mode or otherwise mutate the database file.
        probe = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
        try:
            current = int(probe.execute("PRAGMA user_version").fetchone()[0])
        finally:
            probe.close()
        if current > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema {current} is newer than supported schema {SCHEMA_VERSION}; "
                "startup was refused without modifying the database."
            )
        if current == SCHEMA_VERSION:
            with connect(db_file) as connection:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
            if integrity != "ok" or foreign:
                raise RuntimeError(
                    f"Database integrity failure: integrity={integrity}, "
                    f"foreign_keys={len(foreign)}"
                )
            return

    backup: Path | None = None
    if existing and paths is not None:
        backup = backup_database(paths, f"before-schema-v{SCHEMA_VERSION}")
    try:
        with transaction(db_file) as connection:
            # Add columns needed by index creation before CREATE INDEX runs on a legacy table.
            _upgrade_legacy(connection)
            _base_schema(connection)
            _upgrade_legacy(connection)
            timestamp = now()
            connection.execute(
                "UPDATE items SET created_at=CASE WHEN created_at='' THEN ? ELSE created_at END, "
                "updated_at=CASE WHEN updated_at='' THEN ? ELSE updated_at END",
                (timestamp, timestamp),
            )
            connection.execute(
                "INSERT OR IGNORE INTO shopify_sync(item_id) SELECT item_id FROM items"
            )
            connection.execute(
                "UPDATE recognition_jobs SET started_at=COALESCE(NULLIF(started_at,''),?), "
                "updated_at=COALESCE(NULLIF(updated_at,''),?)",
                (timestamp, timestamp),
            )
            connection.execute(
                "INSERT OR IGNORE INTO recognition_jobs(batch_id,provider,status,total,started_at,updated_at) "
                "SELECT batch_id,'mock','READY',COUNT(*),?,? FROM items GROUP BY batch_id",
                (timestamp, timestamp),
            )
            connection.execute(
                "INSERT OR REPLACE INTO schema_migrations(version, applied_at, description) "
                "VALUES(?, ?, ?)",
                (SCHEMA_VERSION, timestamp, "SnapIMS v0.6.0 operator workstation schema"),
            )
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        with connect(db_file) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
        if integrity != "ok" or foreign:
            raise RuntimeError(
                f"Migration integrity failure: integrity={integrity}, "
                f"foreign_keys={len(foreign)}"
            )
    except Exception:
        if backup is not None and backup.exists():
            _restore_database(db_file, backup)
        raise


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
               MIN(CASE WHEN p.photo_order=1 THEN p.photo_id END) AS front_photo_id,
               MIN(CASE WHEN p.photo_order=1 THEN COALESCE(p.preview_path,p.thumbnail_path) END) AS front_thumbnail,
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
                   MIN(CASE WHEN p.photo_order=1 THEN p.photo_id END) AS front_photo_id,
                   MIN(CASE WHEN p.photo_order=1 THEN COALESCE(p.preview_path,p.thumbnail_path) END) AS front_thumbnail,
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
    "review_source", "working_source",
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
        new_revision = int(previous["record_revision"]) + 1
        for field_name, new_value in updates.items():
            if field_name == "updated_at":
                continue
            old_value = previous[field_name]
            if old_value == new_value:
                continue
            connection.execute(
                """INSERT INTO item_change_log(
                       item_id,batch_id,field_name,old_value_json,new_value_json,
                       occurred_at,source,revision,notes
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    item_id,
                    previous["batch_id"],
                    field_name,
                    json.dumps(old_value),
                    json.dumps(new_value),
                    updates["updated_at"],
                    source,
                    new_revision,
                    reason.strip(),
                ),
            )
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
        row = connection.execute(
            """
            SELECT rowid AS _recognition_rowid, *
            FROM recognition_jobs
            WHERE batch_id=?
            ORDER BY rowid DESC
            LIMIT 1
            """,
            (batch_id,),
        ).fetchone()
    return dict(row) if row else None


def upsert_recognition_job(db_file: Path, batch_id: str, **values: Any) -> None:
    current = get_recognition_job(db_file, batch_id)
    timestamp = now()
    allowed = {
        "provider", "status", "total", "completed", "recognized", "failed",
        "current_item_id", "started_at", "updated_at", "finished_at", "model_name",
        "error_code", "error_message", "error_at", "last_success_at",
    }
    incoming = {key: value for key, value in values.items() if key in allowed}
    if incoming.get("started_at") is None:
        incoming.pop("started_at", None)
    incoming["updated_at"] = timestamp

    if current is not None:
        assignments = ",".join(f"{column}=?" for column in incoming)
        with transaction(db_file) as connection:
            connection.execute(
                f"UPDATE recognition_jobs SET {assignments} WHERE rowid=?",
                [*incoming.values(), current["_recognition_rowid"]],
            )
        return

    fields: dict[str, Any] = {
        "batch_id": batch_id,
        "provider": values.get("provider") or "mock",
        "status": values.get("status") or "READY",
        "started_at": values.get("started_at") or timestamp,
        "updated_at": timestamp,
    }
    for key, value in incoming.items():
        if key in {"started_at", "updated_at"} and value is None:
            continue
        fields[key] = value
    columns = list(fields)
    placeholders = ",".join("?" for _ in columns)
    with transaction(db_file) as connection:
        connection.execute(
            f"INSERT INTO recognition_jobs({','.join(columns)}) VALUES({placeholders})",
            [fields[column] for column in columns],
        )


def mark_interrupted_jobs_paused(db_file: Path) -> int:
    initialize(db_file)
    with transaction(db_file) as connection:
        cursor = connection.execute(
            "UPDATE recognition_jobs SET status='PAUSED',updated_at=? WHERE status IN ('RUNNING','IDENTIFYING')", (now(),)
        )
    return cursor.rowcount


def database_summary(db_file: Path) -> dict[str, int]:
    initialize(db_file)
    tables = ["batches", "items", "photos", "recognition_results", "inventory_events"]
    with connect(db_file) as connection:
        return {table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}


def item_history(db_file: Path, item_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
    initialize(db_file)
    with connect(db_file) as connection:
        rows = connection.execute(
            "SELECT * FROM item_change_log WHERE item_id=? ORDER BY change_id DESC LIMIT ?",
            (item_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def create_batch_checkpoint(
    db_file: Path,
    batch_id: str,
    *,
    reason: str,
    source: str,
) -> int:
    initialize(db_file)
    items = list_items(db_file, batch_id=batch_id)
    if not items:
        raise KeyError(f"Unknown or empty batch: {batch_id}")
    fields = [
        "item_id", "shelf", "rare", "review", "title", "release_year", "edition",
        "distributor", "price_cents", "discount_percent", "description", "vendor",
        "product_type", "tags", "barcode", "condition", "condition_notes",
        "pool_mode", "quantity", "ready", "validation_status", "validation_errors",
        "review_status", "postponed_at", "review_source", "working_source",
    ]
    payload = [{field: item.get(field) for field in fields} for item in items]
    with transaction(db_file) as connection:
        cursor = connection.execute(
            """INSERT INTO batch_checkpoints(batch_id,created_at,reason,source,item_count,payload_json)
               VALUES(?,?,?,?,?,?)""",
            (batch_id, now(), reason, source, len(payload), json.dumps(payload)),
        )
    return int(cursor.lastrowid)


def list_batch_checkpoints(db_file: Path, batch_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    initialize(db_file)
    with connect(db_file) as connection:
        rows = connection.execute(
            "SELECT checkpoint_id,batch_id,created_at,reason,source,item_count "
            "FROM batch_checkpoints WHERE batch_id=? ORDER BY checkpoint_id DESC LIMIT ?",
            (batch_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def restore_batch_checkpoint(db_file: Path, checkpoint_id: int) -> int:
    initialize(db_file)
    with connect(db_file) as connection:
        row = connection.execute(
            "SELECT * FROM batch_checkpoints WHERE checkpoint_id=?", (checkpoint_id,)
        ).fetchone()
    if row is None:
        raise KeyError(f"Unknown checkpoint: {checkpoint_id}")
    payload = json.loads(row["payload_json"])
    batch_id = str(row["batch_id"])
    create_batch_checkpoint(
        db_file, batch_id, reason=f"Before restoring checkpoint {checkpoint_id}", source="ROLLBACK",
    )
    restored = 0
    timestamp = now()
    with transaction(db_file) as connection:
        for snapshot in payload:
            item_id = snapshot.pop("item_id")
            current = connection.execute("SELECT * FROM items WHERE item_id=?", (item_id,)).fetchone()
            if current is None:
                continue
            assignments = ",".join(f"{field}=?" for field in snapshot)
            connection.execute(
                f"UPDATE items SET {assignments},updated_at=?,record_revision=record_revision+1 WHERE item_id=?",
                [*snapshot.values(), timestamp, item_id],
            )
            restored += 1
    return restored


def save_csv_staging(
    db_file: Path,
    *,
    token: str,
    batch_id: str,
    filename: str,
    payload: list[dict[str, Any]],
    diff: dict[str, Any],
    blocking_errors: list[str],
) -> None:
    initialize(db_file)
    with transaction(db_file) as connection:
        connection.execute(
            """INSERT INTO csv_staging(token,batch_id,filename,created_at,payload_json,diff_json,blocking_errors_json)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(token) DO UPDATE SET payload_json=excluded.payload_json,
               diff_json=excluded.diff_json,blocking_errors_json=excluded.blocking_errors_json""",
            (
                token, batch_id, filename, now(), json.dumps(payload), json.dumps(diff),
                json.dumps(blocking_errors),
            ),
        )


def get_csv_staging(db_file: Path, token: str) -> dict[str, Any] | None:
    initialize(db_file)
    with connect(db_file) as connection:
        row = connection.execute("SELECT * FROM csv_staging WHERE token=?", (token,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["payload"] = json.loads(result.pop("payload_json"))
    result["diff"] = json.loads(result.pop("diff_json"))
    result["blocking_errors"] = json.loads(result.pop("blocking_errors_json"))
    return result


def delete_csv_staging(db_file: Path, token: str) -> None:
    initialize(db_file)
    with transaction(db_file) as connection:
        connection.execute("DELETE FROM csv_staging WHERE token=?", (token,))


def batch_health(db_file: Path, batch_id: str, *, low_confidence: float = 0.70) -> dict[str, int]:
    items = list_items(db_file, batch_id=batch_id)
    return {
        "total": len(items),
        "approved": sum(1 for item in items if item["review_status"] == "DONE"),
        "unfinished": sum(1 for item in items if item["review_status"] == "UNFINISHED"),
        "failed": sum(1 for item in items if item["recognition_status"] == "FAILED"),
        "flagged": sum(1 for item in items if item["review"]),
        "rare": sum(1 for item in items if item["rare"]),
        "low_confidence": sum(
            1 for item in items
            if item["recognition_confidence"] is not None
            and float(item["recognition_confidence"]) < low_confidence
        ),
        "missing_required": sum(
            1 for item in items if not str(item["title"] or "").strip() or item["price_cents"] is None
        ),
        "publish_blockers": sum(1 for item in items if item["validation_status"] != "READY"),
        "changed_since_recognition": sum(
            1 for item in items if str(item.get("working_source") or "IMPORT") not in {"IMPORT", "AI_ACCEPTED"}
        ),
        "readiness_percent": int(round(
            100 * sum(1 for item in items if item["validation_status"] == "READY") / max(1, len(items))
        )),
    }


def confidence_buckets(db_file: Path, batch_id: str) -> dict[str, int]:
    items = list_items(db_file, batch_id=batch_id)
    values = [
        float(item["recognition_confidence"])
        for item in items
        if item["recognition_confidence"] is not None
    ]
    return {
        "98_100": sum(1 for value in values if value >= 0.98),
        "95_98": sum(1 for value in values if 0.95 <= value < 0.98),
        "90_95": sum(1 for value in values if 0.90 <= value < 0.95),
        "below_90": sum(1 for value in values if value < 0.90),
        "unknown": len(items) - len(values),
    }


def batch_metrics(db_file: Path, batch_id: str) -> dict[str, Any]:
    initialize(db_file)
    with connect(db_file) as connection:
        approval_rows = connection.execute(
            """SELECT occurred_at FROM item_change_log
               WHERE batch_id=? AND field_name='review_status' AND new_value_json='"DONE"'
               ORDER BY change_id""",
            (batch_id,),
        ).fetchall()
        change_count = int(connection.execute(
            "SELECT COUNT(*) FROM item_change_log WHERE batch_id=?", (batch_id,)
        ).fetchone()[0])
        token_row = connection.execute(
            """SELECT COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0)
               FROM recognition_results
               WHERE item_id IN (SELECT item_id FROM items WHERE batch_id=?)""",
            (batch_id,),
        ).fetchone()
        media = connection.execute(
            """SELECT COALESCE(SUM(original_bytes),0),COALESCE(SUM(preview_bytes),0),
                      COALESCE(SUM(recognition_bytes),0),
                      COALESCE(SUM(CASE WHEN ai_eligible=0 THEN 1 ELSE 0 END),0)
               FROM photos WHERE batch_id=?""",
            (batch_id,),
        ).fetchone()
    approvals = len(approval_rows)
    elapsed_minutes = 0.0
    if approvals >= 2:
        try:
            first = datetime.fromisoformat(str(approval_rows[0][0]))
            last = datetime.fromisoformat(str(approval_rows[-1][0]))
            elapsed_minutes = max((last - first).total_seconds() / 60, 1 / 60)
        except ValueError:
            elapsed_minutes = 0.0
    approvals_per_minute = round(approvals / elapsed_minutes, 2) if elapsed_minutes else 0.0
    original_bytes = int(media[0])
    preview_bytes = int(media[1])
    recognition_bytes = int(media[2])
    bandwidth_saved = max(0, original_bytes - recognition_bytes)
    reduction = round(100 * bandwidth_saved / original_bytes, 1) if original_bytes else 0.0
    return {
        "approval_events": approvals,
        "approvals_per_minute": approvals_per_minute,
        "total_changes": change_count,
        "images_skipped": int(media[3]),
        "original_bytes": original_bytes,
        "preview_bytes": preview_bytes,
        "recognition_bytes": recognition_bytes,
        "bandwidth_saved": bandwidth_saved,
        "payload_reduction_percent": reduction,
        "input_tokens": int(token_row[0]),
        "output_tokens": int(token_row[1]),
        "estimated_api_cost": "Not calculated",
    }


def media_totals(db_file: Path) -> dict[str, int]:
    initialize(db_file)
    with connect(db_file) as connection:
        row = connection.execute(
            """SELECT COALESCE(SUM(original_bytes),0),COALESCE(SUM(preview_bytes),0),
                      COALESCE(SUM(recognition_bytes),0),
                      COALESCE(SUM(CASE WHEN ai_eligible=0 THEN 1 ELSE 0 END),0)
               FROM photos"""
        ).fetchone()
    return {
        "original_bytes": int(row[0]),
        "preview_bytes": int(row[1]),
        "recognition_bytes": int(row[2]),
        "images_skipped": int(row[3]),
    }


def list_editor_items(db_file: Path, batch_id: str) -> list[dict[str, Any]]:
    items = list_items(db_file, batch_id=batch_id)
    result: list[dict[str, Any]] = []
    for item in items:
        suggestion = latest_recognition(db_file, item["item_id"])
        row = dict(item)
        row["suggested_title"] = suggestion["suggested_title"] if suggestion else ""
        row["suggested_price_cents"] = suggestion["suggested_price_cents"] if suggestion else None
        row["uncertainty_reasons"] = (
            json.loads(suggestion["uncertainty_reasons_json"]) if suggestion else []
        )
        row["recognition_model"] = ""
        row["pricing_source"] = suggestion.get("pricing_source", "") if suggestion else ""
        row["input_tokens"] = suggestion.get("input_tokens", 0) if suggestion else 0
        row["output_tokens"] = suggestion.get("output_tokens", 0) if suggestion else 0
        result.append(row)
    return result
