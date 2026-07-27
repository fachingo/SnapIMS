from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from snapims.config import DataPaths

SCHEMA_VERSION = 8


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def connect(db_file: Path) -> sqlite3.Connection:
    db_file.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_file, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


@contextmanager
def transaction(
    db_file: Path, *, foreign_keys: bool = True
) -> Iterator[sqlite3.Connection]:
    connection = connect(db_file)
    if not foreign_keys:
        connection.execute("PRAGMA foreign_keys = OFF")
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
            source_kind TEXT NOT NULL DEFAULT 'LIVE',
            model_name TEXT NOT NULL DEFAULT '',
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
            input_image_count INTEGER NOT NULL DEFAULT 0,
            input_image_bytes INTEGER NOT NULL DEFAULT 0,
            requires_review INTEGER NOT NULL DEFAULT 1,
            accepted_at TEXT
        );
        CREATE TABLE IF NOT EXISTS recognition_jobs (
            batch_id TEXT PRIMARY KEY REFERENCES batches(batch_id) ON DELETE RESTRICT,
            provider TEXT NOT NULL DEFAULT '',
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
            payload_json TEXT NOT NULL,
            payload_bytes INTEGER NOT NULL DEFAULT 0,
            protected INTEGER NOT NULL DEFAULT 0,
            restored_from_checkpoint_id INTEGER REFERENCES batch_checkpoints(checkpoint_id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS csv_staging (
            token TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL REFERENCES batches(batch_id) ON DELETE RESTRICT,
            filename TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            applied_at TEXT,
            status TEXT NOT NULL DEFAULT 'STAGED',
            row_count INTEGER NOT NULL DEFAULT 0,
            upload_bytes INTEGER NOT NULL DEFAULT 0,
            protected INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL,
            diff_json TEXT NOT NULL,
            blocking_errors_json TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS item_movie_links (
            item_id TEXT PRIMARY KEY REFERENCES items(item_id) ON DELETE RESTRICT,
            movie_id TEXT,
            link_status TEXT NOT NULL,
            link_method TEXT NOT NULL DEFAULT '',
            recognition_result_id INTEGER REFERENCES recognition_results(recognition_result_id) ON DELETE RESTRICT,
            match_score REAL,
            linked_at TEXT,
            updated_at TEXT NOT NULL,
            operator_confirmed INTEGER NOT NULL DEFAULT 0,
            catalog_revision INTEGER,
            last_error TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS item_movie_link_events (
            link_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT NOT NULL REFERENCES items(item_id) ON DELETE RESTRICT,
            previous_movie_id TEXT,
            movie_id TEXT,
            event_type TEXT NOT NULL,
            link_status TEXT NOT NULL,
            link_method TEXT NOT NULL DEFAULT '',
            recognition_result_id INTEGER REFERENCES recognition_results(recognition_result_id) ON DELETE RESTRICT,
            match_score REAL,
            operator_confirmed INTEGER NOT NULL DEFAULT 0,
            catalog_revision INTEGER,
            occurred_at TEXT NOT NULL,
            source TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS import_journal (
            import_id TEXT PRIMARY KEY,
            source_fingerprint TEXT NOT NULL UNIQUE,
            batch_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            source_folder TEXT NOT NULL,
            staging_originals TEXT NOT NULL,
            staging_processed TEXT NOT NULL,
            final_originals TEXT NOT NULL,
            final_processed TEXT NOT NULL,
            manifest_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            error TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS operation_requests (
            request_id TEXT PRIMARY KEY,
            operation_type TEXT NOT NULL,
            batch_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            result_json TEXT NOT NULL DEFAULT '{}',
            error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_items_batch ON items(batch_id, sequence);
        CREATE INDEX IF NOT EXISTS idx_items_review ON items(batch_id, review_status, sequence);
        CREATE INDEX IF NOT EXISTS idx_photos_item ON photos(item_id, photo_order);
        CREATE INDEX IF NOT EXISTS idx_recognition_item ON recognition_results(item_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_inventory_item ON inventory_events(item_id, occurred_at);
        CREATE INDEX IF NOT EXISTS idx_item_change_log_item ON item_change_log(item_id, occurred_at DESC);
        CREATE INDEX IF NOT EXISTS idx_checkpoints_batch ON batch_checkpoints(batch_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_csv_staging_lifecycle ON csv_staging(status, expires_at);
        CREATE INDEX IF NOT EXISTS idx_import_journal_status ON import_journal(status, updated_at);
        CREATE INDEX IF NOT EXISTS idx_item_movie_links_movie ON item_movie_links(movie_id, link_status);
        CREATE INDEX IF NOT EXISTS idx_item_movie_link_events_item ON item_movie_link_events(item_id, occurred_at DESC);
        """
    )


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


EXPECTED_SCHEMA: dict[str, set[str]] = {
    "schema_migrations": {"version", "applied_at", "description"},
    "batches": {"batch_id", "source_fingerprint", "status", "item_count"},
    "items": {
        "item_id", "sku", "batch_id", "sequence", "shelf", "title", "price_cents",
        "discount_percent", "review_status", "recognition_status", "record_revision",
        "review_source", "working_source", "created_at", "updated_at",
    },
    "photos": {
        "photo_id", "batch_id", "item_id", "kind", "stream_index", "sha256",
        "original_copy_path", "processed_path", "preview_path", "recognition_path",
    },
    "recognition_results": {
        "recognition_result_id", "item_id", "provider", "source_kind", "model_name",
        "suggested_title", "suggested_price_cents", "confidence", "accepted_at",
        "input_image_count", "input_image_bytes",
    },
    "recognition_jobs": {
        "batch_id", "provider", "status", "total", "completed", "recognized", "failed",
        "started_at", "updated_at", "error_code", "error_message",
    },
    "item_change_log": {
        "change_id", "item_id", "batch_id", "field_name", "old_value_json",
        "new_value_json", "source", "revision",
    },
    "batch_checkpoints": {
        "checkpoint_id", "batch_id", "payload_json", "payload_bytes", "protected",
        "restored_from_checkpoint_id",
    },
    "csv_staging": {
        "token", "batch_id", "status", "created_at", "updated_at", "expires_at",
        "applied_at", "row_count", "upload_bytes", "protected", "payload_json",
    },
    "import_journal": {
        "import_id", "source_fingerprint", "batch_id", "status", "staging_originals",
        "staging_processed", "final_originals", "final_processed", "manifest_json",
    },
    "operation_requests": {
        "request_id", "operation_type", "batch_id", "status", "result_json",
        "error_message", "created_at", "updated_at", "completed_at",
    },
    "item_movie_links": {
        "item_id", "movie_id", "link_status", "link_method",
        "recognition_result_id", "match_score", "linked_at", "updated_at",
        "operator_confirmed", "catalog_revision", "last_error",
    },
    "item_movie_link_events": {
        "link_event_id", "item_id", "previous_movie_id", "movie_id", "event_type",
        "link_status", "link_method", "recognition_result_id", "match_score",
        "operator_confirmed", "catalog_revision", "occurred_at", "source", "details_json",
    },
}

EXPECTED_INDEXES = {
    "idx_items_batch",
    "idx_items_review",
    "idx_photos_item",
    "idx_recognition_item",
    "idx_item_change_log_item",
    "idx_checkpoints_batch",
    "idx_csv_staging_lifecycle",
    "idx_import_journal_status",
    "idx_item_movie_links_movie",
    "idx_item_movie_link_events_item",
}


def schema_manifest_report(connection: sqlite3.Connection) -> dict[str, Any]:
    problems: list[str] = []
    tables = _table_names(connection)
    for table, required_columns in EXPECTED_SCHEMA.items():
        if table not in tables:
            problems.append(f"Missing table: {table}")
            continue
        actual = _columns(connection, table)
        for column in sorted(required_columns - actual):
            problems.append(f"Missing column: {table}.{column}")
    indexes = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_autoindex_%'"
        )
    }
    for index in sorted(EXPECTED_INDEXES - indexes):
        problems.append(f"Missing index: {index}")
    pk_rows = connection.execute("PRAGMA table_info(recognition_jobs)").fetchall()
    batch_pk = next((int(row[5]) for row in pk_rows if str(row[1]) == "batch_id"), 0)
    if batch_pk != 1:
        problems.append("recognition_jobs.batch_id must be the primary key")
    def unique_column_sets(table: str) -> set[tuple[str, ...]]:
        result: set[tuple[str, ...]] = set()
        primary = tuple(
            str(row[1])
            for row in sorted(
                (row for row in connection.execute(f"PRAGMA table_info({table})") if int(row[5]) > 0),
                key=lambda row: int(row[5]),
            )
        )
        if primary:
            result.add(primary)
        for index in connection.execute(f"PRAGMA index_list({table})"):
            if int(index[2]) != 1:
                continue
            columns = tuple(
                str(row[2])
                for row in connection.execute(f"PRAGMA index_info({index[1]})")
            )
            if columns:
                result.add(columns)
        return result

    required_unique: dict[str, set[tuple[str, ...]]] = {
        "batches": {("batch_id",), ("source_fingerprint",)},
        "items": {("item_id",), ("sku",), ("batch_id", "sequence")},
        "photos": {("batch_id", "stream_index")},
        "recognition_jobs": {("batch_id",)},
        "csv_staging": {("token",)},
        "import_journal": {("import_id",), ("source_fingerprint",), ("batch_id",)},
        "operation_requests": {("request_id",)},
    }
    for table, expected in required_unique.items():
        if table not in tables:
            continue
        actual_unique = unique_column_sets(table)
        for columns in sorted(expected - actual_unique):
            problems.append(f"Missing unique constraint: {table}({','.join(columns)})")

    required_foreign_keys = {
        ("items", "batch_id", "batches", "batch_id"),
        ("photos", "batch_id", "batches", "batch_id"),
        ("photos", "item_id", "items", "item_id"),
        ("recognition_results", "item_id", "items", "item_id"),
        ("recognition_jobs", "batch_id", "batches", "batch_id"),
        ("csv_staging", "batch_id", "batches", "batch_id"),
    }
    actual_foreign_keys: set[tuple[str, str, str, str]] = set()
    for table in tables:
        for foreign in connection.execute(f"PRAGMA foreign_key_list({table})"):
            actual_foreign_keys.add((table, str(foreign[3]), str(foreign[2]), str(foreign[4])))
    for table, column, target_table, target_column in sorted(required_foreign_keys - actual_foreign_keys):
        problems.append(
            f"Missing foreign key: {table}.{column} -> {target_table}.{target_column}"
        )
    return {"ok": not problems, "problems": problems, "schema_version": SCHEMA_VERSION}


def verify_schema(connection: sqlite3.Connection) -> None:
    report = schema_manifest_report(connection)
    if not report["ok"]:
        raise RuntimeError(
            "Database schema manifest verification failed: " + "; ".join(report["problems"])
        )


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
            "provider TEXT NOT NULL DEFAULT ''",
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
            "input_image_count INTEGER NOT NULL DEFAULT 0",
            "input_image_bytes INTEGER NOT NULL DEFAULT 0",
            "release_year INTEGER",
            "barcode_candidates_json TEXT NOT NULL DEFAULT '[]'",
            "suggested_price_cents INTEGER",
            "suggested_discount_percent REAL NOT NULL DEFAULT 0",
            "confidence REAL NOT NULL DEFAULT 0",
            "uncertainty_reasons_json TEXT NOT NULL DEFAULT '[]'",
            "raw_response_reference TEXT NOT NULL DEFAULT ''",
            "requires_review INTEGER NOT NULL DEFAULT 1",
            "accepted_at TEXT",
            "source_kind TEXT NOT NULL DEFAULT 'LIVE'",
            "model_name TEXT NOT NULL DEFAULT ''",
        ):
            _add_column(connection, "recognition_results", definition)
    if "batch_checkpoints" in tables:
        for definition in (
            "payload_bytes INTEGER NOT NULL DEFAULT 0",
            "protected INTEGER NOT NULL DEFAULT 0",
            "restored_from_checkpoint_id INTEGER",
        ):
            _add_column(connection, "batch_checkpoints", definition)
    if "csv_staging" in tables:
        for definition in (
            "updated_at TEXT NOT NULL DEFAULT ''",
            "expires_at TEXT NOT NULL DEFAULT ''",
            "applied_at TEXT",
            "status TEXT NOT NULL DEFAULT 'STAGED'",
            "row_count INTEGER NOT NULL DEFAULT 0",
            "upload_bytes INTEGER NOT NULL DEFAULT 0",
            "protected INTEGER NOT NULL DEFAULT 0",
        ):
            _add_column(connection, "csv_staging", definition)
    if "operation_requests" in tables:
        for definition in (
            "error_message TEXT NOT NULL DEFAULT ''",
            "completed_at TEXT",
        ):
            _add_column(connection, "operation_requests", definition)
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



def _rebuild_recognition_jobs_if_needed(connection: sqlite3.Connection) -> bool:
    """Repair legacy recognition_jobs tables that allowed duplicate batch rows.

    SnapIMS 0.5-era databases used an autoincrement row id and only a non-unique
    batch index.  The v0.7.0 contract is exactly one durable job row per batch.
    The newest legacy row wins, which matches the read behaviour used before this
    migration.
    """
    if "recognition_jobs" not in _table_names(connection):
        return False
    info = connection.execute("PRAGMA table_info(recognition_jobs)").fetchall()
    batch_pk = next((int(row[5]) for row in info if str(row[1]) == "batch_id"), 0)
    unique_batch = batch_pk == 1
    if not unique_batch:
        for index in connection.execute("PRAGMA index_list(recognition_jobs)").fetchall():
            if int(index[2]) != 1:
                continue
            columns = [str(row[2]) for row in connection.execute(
                f"PRAGMA index_info({index[1]})"
            ).fetchall()]
            if columns == ["batch_id"]:
                unique_batch = True
                break
    if unique_batch:
        return False

    timestamp = now()
    connection.execute("DROP TABLE IF EXISTS recognition_jobs_v7")
    connection.execute(
        """CREATE TABLE recognition_jobs_v7 (
            batch_id TEXT PRIMARY KEY REFERENCES batches(batch_id) ON DELETE RESTRICT,
            provider TEXT NOT NULL DEFAULT '',
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
        )"""
    )
    rows = connection.execute(
        """SELECT r.* FROM recognition_jobs r
           JOIN (SELECT batch_id, MAX(rowid) AS latest_rowid
                 FROM recognition_jobs GROUP BY batch_id) latest
             ON latest.latest_rowid=r.rowid
           ORDER BY r.rowid"""
    ).fetchall()
    for row in rows:
        record = dict(row)
        connection.execute(
            """INSERT INTO recognition_jobs_v7(
                batch_id,provider,status,total,completed,recognized,failed,current_item_id,
                started_at,updated_at,finished_at,model_name,error_code,error_message,
                error_at,last_success_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record.get("batch_id"),
                record.get("provider") or "",
                "COMPLETE_WITH_FAILURES" if record.get("status") == "COMPLETE_WITH_FAILURE" else (record.get("status") or "READY"),
                int(record.get("total") or 0),
                int(record.get("completed") or 0),
                int(record.get("recognized") or 0),
                int(record.get("failed") or 0),
                record.get("current_item_id") or record.get("last_item_id") or "",
                record.get("started_at") or timestamp,
                record.get("updated_at") or record.get("completed_at") or timestamp,
                record.get("finished_at") or record.get("completed_at"),
                record.get("model_name") or "",
                record.get("error_code") or "",
                record.get("error_message") or "",
                record.get("error_at"),
                record.get("last_success_at"),
            ),
        )
    connection.execute("DROP TABLE recognition_jobs")
    connection.execute("ALTER TABLE recognition_jobs_v7 RENAME TO recognition_jobs")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_recognition_jobs_status "
        "ON recognition_jobs(status, updated_at DESC)"
    )
    return True


def _unique_sets(connection: sqlite3.Connection, table: str) -> set[tuple[str, ...]]:
    result: set[tuple[str, ...]] = set()
    primary = tuple(
        str(row[1])
        for row in sorted(
            (row for row in connection.execute(f"PRAGMA table_info({table})") if int(row[5]) > 0),
            key=lambda row: int(row[5]),
        )
    )
    if primary:
        result.add(primary)
    for index in connection.execute(f"PRAGMA index_list({table})"):
        if int(index[2]) != 1:
            continue
        columns = tuple(str(row[2]) for row in connection.execute(f"PRAGMA index_info({index[1]})"))
        if columns:
            result.add(columns)
    return result


def _foreign_keys(connection: sqlite3.Connection, table: str) -> set[tuple[str, str, str]]:
    return {
        (str(row[3]), str(row[2]), str(row[4]))
        for row in connection.execute(f"PRAGMA foreign_key_list({table})")
    }


def _copy_columns(connection: sqlite3.Connection, source: str, target: str) -> None:
    source_columns = _columns(connection, source)
    target_columns = [str(row[1]) for row in connection.execute(f"PRAGMA table_info({target})")]
    common = [column for column in target_columns if column in source_columns]
    if common:
        names = ",".join(common)
        connection.execute(f"INSERT INTO {target}({names}) SELECT {names} FROM {source}")


def _rebuild_core_tables_if_needed(connection: sqlite3.Connection) -> None:
    """Upgrade legacy tables whose constraints cannot be added with ALTER TABLE.

    The v0.3-v0.6 databases used the right durable identifiers but some early
    schemas lacked foreign keys and composite uniqueness. Rebuilding in-place
    preserves rows and identifiers while making the structural manifest true.
    Migration runs with foreign-key enforcement temporarily disabled, followed
    by an explicit foreign_key_check before startup is allowed.
    """
    tables = _table_names(connection)

    if "items" in tables:
        required_unique = {("item_id",), ("sku",), ("batch_id", "sequence")}
        required_fk = {("batch_id", "batches", "batch_id")}
        if not required_unique.issubset(_unique_sets(connection, "items")) or not required_fk.issubset(
            _foreign_keys(connection, "items")
        ):
            connection.execute("DROP TABLE IF EXISTS items_v7")
            connection.execute(
                """
                CREATE TABLE items_v7 (
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
                )
                """
            )
            _copy_columns(connection, "items", "items_v7")
            connection.execute("DROP TABLE items")
            connection.execute("ALTER TABLE items_v7 RENAME TO items")

    tables = _table_names(connection)
    if "photos" in tables:
        required_unique = {("batch_id", "stream_index")}
        required_fk = {
            ("batch_id", "batches", "batch_id"),
            ("item_id", "items", "item_id"),
        }
        if not required_unique.issubset(_unique_sets(connection, "photos")) or not required_fk.issubset(
            _foreign_keys(connection, "photos")
        ):
            connection.execute("DROP TABLE IF EXISTS photos_v7")
            connection.execute(
                """
                CREATE TABLE photos_v7 (
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
                )
                """
            )
            _copy_columns(connection, "photos", "photos_v7")
            connection.execute("DROP TABLE photos")
            connection.execute("ALTER TABLE photos_v7 RENAME TO photos")

    tables = _table_names(connection)
    if "recognition_results" in tables:
        required_fk = {("item_id", "items", "item_id")}
        if not required_fk.issubset(_foreign_keys(connection, "recognition_results")):
            connection.execute("DROP TABLE IF EXISTS recognition_results_v7")
            connection.execute(
                """
                CREATE TABLE recognition_results_v7 (
                    recognition_result_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL REFERENCES items(item_id) ON DELETE RESTRICT,
                    provider TEXT NOT NULL,
                    source_kind TEXT NOT NULL DEFAULT 'LIVE',
                    model_name TEXT NOT NULL DEFAULT '',
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
                    input_image_count INTEGER NOT NULL DEFAULT 0,
                    input_image_bytes INTEGER NOT NULL DEFAULT 0,
                    requires_review INTEGER NOT NULL DEFAULT 1,
                    accepted_at TEXT
                )
                """
            )
            _copy_columns(connection, "recognition_results", "recognition_results_v7")
            connection.execute("DROP TABLE recognition_results")
            connection.execute("ALTER TABLE recognition_results_v7 RENAME TO recognition_results")

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
                manifest = schema_manifest_report(connection)
            if integrity != "ok" or foreign or not manifest["ok"]:
                details = "; ".join(manifest["problems"])
                raise RuntimeError(
                    f"Database integrity/schema failure: integrity={integrity}, "
                    f"foreign_keys={len(foreign)}, schema={details or 'ok'}"
                )
            return

    backup: Path | None = None
    if existing and paths is not None:
        backup = backup_database(paths, f"before-schema-v{SCHEMA_VERSION}")
    try:
        with transaction(db_file, foreign_keys=False) as connection:
            # Add columns before rebuilding legacy tables whose constraints cannot be altered.
            _upgrade_legacy(connection)
            _rebuild_core_tables_if_needed(connection)
            # v0.5.x used a per-item recognition_job_items table keyed to the old
            # recognition_jobs.recognition_job_id parent. v0.6+ stores one durable
            # job per batch and no current code reads the legacy child rows. Drop it
            # before rebuilding the parent so SQLite never observes a mismatched FK.
            connection.execute("DROP TABLE IF EXISTS recognition_job_items")
            _rebuild_recognition_jobs_if_needed(connection)
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
                "SELECT batch_id,'','READY',COUNT(*),?,? FROM items GROUP BY batch_id",
                (timestamp, timestamp),
            )
            connection.execute(
                "UPDATE recognition_jobs SET status='COMPLETE_WITH_FAILURES' "
                "WHERE status='COMPLETE_WITH_FAILURE'"
            )
            connection.execute(
                "UPDATE recognition_results SET source_kind=CASE "
                "WHEN lower(provider) IN ('mock','fixture','demo','synthetic','test') THEN 'TEST' "
                "ELSE COALESCE(NULLIF(source_kind,''),'LIVE') END"
            )
            connection.execute(
                "UPDATE csv_staging SET updated_at=CASE WHEN updated_at='' THEN created_at ELSE updated_at END, "
                "expires_at=CASE WHEN expires_at='' THEN ? ELSE expires_at END",
                ((datetime.now().astimezone() + timedelta(days=7)).isoformat(timespec='microseconds'),),
            )
            for checkpoint in connection.execute(
                "SELECT checkpoint_id,payload_json FROM batch_checkpoints WHERE payload_bytes=0"
            ).fetchall():
                connection.execute(
                    "UPDATE batch_checkpoints SET payload_bytes=? WHERE checkpoint_id=?",
                    (len(str(checkpoint[1]).encode('utf-8')), int(checkpoint[0])),
                )
            connection.execute(
                "INSERT OR REPLACE INTO schema_migrations(version, applied_at, description) "
                "VALUES(?, ?, ?)",
                (SCHEMA_VERSION, timestamp, "SnapIMS v0.7.0 keyboard and local Movie catalog schema"),
            )
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        with connect(db_file) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
            manifest = schema_manifest_report(connection)
        if integrity != "ok" or foreign or not manifest["ok"]:
            raise RuntimeError(
                f"Migration integrity failure: integrity={integrity}, "
                f"foreign_keys={len(foreign)}, schema={'; '.join(manifest['problems']) or 'ok'}"
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


def _item_select_sql(where: str) -> str:
    return f"""
        SELECT i.*, COUNT(p.photo_id) AS image_count,
               MIN(CASE WHEN p.photo_order=1 THEN p.photo_id END) AS front_photo_id,
               MIN(CASE WHEN p.photo_order=1 THEN COALESCE(p.preview_path,p.thumbnail_path) END) AS front_thumbnail,
               MIN(CASE WHEN p.photo_order=1 THEN p.processed_path END) AS front_image,
               r.recognition_result_id AS latest_recognition_result_id,
               r.suggested_title,
               r.edition AS suggested_edition,
               r.distributor AS suggested_distributor,
               r.release_year AS suggested_release_year,
               r.barcode_candidates_json,
               r.suggested_price_cents,
               r.suggested_discount_percent,
               r.confidence AS suggestion_confidence,
               r.provider AS suggestion_provider,
               r.source_kind AS suggestion_source_kind,
               r.model_name AS suggestion_model_name,
               r.uncertainty_reasons_json,
               r.pricing_source,
               r.input_tokens,
               r.output_tokens,
               r.input_image_count,
               r.input_image_bytes,
               r.accepted_at AS suggestion_accepted_at
        FROM items i
        LEFT JOIN photos p ON p.item_id=i.item_id AND p.kind='product'
        LEFT JOIN recognition_results r ON r.recognition_result_id=(
            SELECT MAX(r2.recognition_result_id)
            FROM recognition_results r2
            WHERE r2.item_id=i.item_id
        )
        {where}
        GROUP BY i.item_id
    """


def _decode_item_row(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    raw_reasons = result.get("uncertainty_reasons_json")
    try:
        result["uncertainty_reasons"] = json.loads(raw_reasons) if raw_reasons else []
    except (TypeError, json.JSONDecodeError):
        result["uncertainty_reasons"] = []
    raw_barcodes = result.get("barcode_candidates_json")
    try:
        result["barcode_candidates"] = json.loads(raw_barcodes) if raw_barcodes else []
    except (TypeError, json.JSONDecodeError):
        result["barcode_candidates"] = []
    result["display_confidence"] = (
        result.get("recognition_confidence")
        if result.get("review_status") == "DONE" and result.get("recognition_confidence") is not None
        else result.get("suggestion_confidence")
    )
    if result.get("review_status") == "DONE":
        result["value_state"] = "REVIEWED"
    elif result.get("title") or result.get("price_cents") is not None:
        result["value_state"] = "SAVED"
    elif result.get("suggested_title") or result.get("suggested_price_cents") is not None:
        result["value_state"] = "SUGGESTED"
    else:
        result["value_state"] = "MANUAL"
    return result


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
    elif queue == "BLOCKED":
        clauses.append("i.recognition_status='BLOCKED'")
    elif queue == "READY":
        clauses.append("i.ready=1 AND i.validation_status='READY'")
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    query = _item_select_sql(where) + " ORDER BY i.sequence"
    with connect(db_file) as connection:
        rows = connection.execute(query, values).fetchall()
    return [_decode_item_row(row) for row in rows]


def get_item(db_file: Path, item_id: str) -> dict[str, Any] | None:
    initialize(db_file)
    with connect(db_file) as connection:
        row = connection.execute(
            _item_select_sql("WHERE i.item_id=?"),
            (item_id,),
        ).fetchone()
    return _decode_item_row(row) if row else None


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


def update_item_in_connection(
    connection: sqlite3.Connection,
    item_id: str,
    values: dict[str, Any],
    *,
    source: str = "ITEM_EDITOR",
    reason: str = "",
    expected_revision: int | None = None,
) -> dict[str, Any]:
    updates = {key: value for key, value in values.items() if key in EDITABLE_FIELDS}
    previous = connection.execute("SELECT * FROM items WHERE item_id=?", (item_id,)).fetchone()
    if previous is None:
        raise KeyError(f"Unknown Item ID: {item_id}")
    if expected_revision is not None and int(previous["record_revision"]) != expected_revision:
        raise RuntimeError("This item changed in another session. Reload before saving.")
    if not updates:
        return dict(previous)
    if "shelf" in updates and updates["shelf"] != previous["shelf"] and not reason.strip():
        raise ValueError("A reason is required when changing shelf location.")
    timestamp = now()
    updates["updated_at"] = timestamp
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
                timestamp,
                source,
                new_revision,
                reason.strip(),
            ),
        )
    if "shelf" in updates and updates["shelf"] != previous["shelf"]:
        connection.execute(
            """INSERT INTO inventory_events(
                   item_id,batch_id,occurred_at,event_type,from_location,to_location,source,notes
               ) VALUES(?,?,?,'LOCATION_CHANGED',?,?,?,?)""",
            (
                item_id,
                previous["batch_id"],
                timestamp,
                previous["shelf"],
                updates["shelf"],
                source,
                reason.strip(),
            ),
        )
    if "quantity" in updates and int(updates["quantity"]) != int(previous["quantity"]):
        connection.execute(
            """INSERT INTO inventory_events(
                   item_id,batch_id,occurred_at,event_type,to_location,quantity_delta,source,notes
               ) VALUES(?,?,?,'QUANTITY_ADJUSTED',?,?,?,?)""",
            (
                item_id,
                previous["batch_id"],
                timestamp,
                updates.get("shelf", previous["shelf"]),
                int(updates["quantity"]) - int(previous["quantity"]),
                source,
                reason.strip(),
            ),
        )
    saved = connection.execute("SELECT * FROM items WHERE item_id=?", (item_id,)).fetchone()
    assert saved is not None
    return dict(saved)


def update_item(
    db_file: Path,
    item_id: str,
    values: dict[str, Any],
    *,
    source: str = "ITEM_EDITOR",
    reason: str = "",
    expected_revision: int | None = None,
) -> None:
    with transaction(db_file) as connection:
        update_item_in_connection(
            connection,
            item_id,
            values,
            source=source,
            reason=reason,
            expected_revision=expected_revision,
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
        "provider": values.get("provider") or "",
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


CHECKPOINT_FIELDS = [
    "item_id", "shelf", "rare", "review", "title", "release_year", "edition",
    "distributor", "price_cents", "discount_percent", "description", "vendor",
    "product_type", "tags", "barcode", "condition", "condition_notes",
    "pool_mode", "quantity", "ready", "validation_status", "validation_errors",
    "review_status", "postponed_at", "review_source", "working_source",
]


def create_batch_checkpoint_in_connection(
    connection: sqlite3.Connection,
    batch_id: str,
    *,
    reason: str,
    source: str,
    protected: bool = False,
    restored_from_checkpoint_id: int | None = None,
) -> int:
    rows = connection.execute(
        "SELECT * FROM items WHERE batch_id=? ORDER BY sequence", (batch_id,)
    ).fetchall()
    if not rows:
        raise KeyError(f"Unknown or empty batch: {batch_id}")
    payload = [
        {field: row[field] for field in CHECKPOINT_FIELDS}
        for row in rows
    ]
    encoded = json.dumps(payload, separators=(",", ":"))
    cursor = connection.execute(
        """INSERT INTO batch_checkpoints(
               batch_id,created_at,reason,source,item_count,payload_json,payload_bytes,
               protected,restored_from_checkpoint_id
           ) VALUES(?,?,?,?,?,?,?,?,?)""",
        (
            batch_id,
            now(),
            reason,
            source,
            len(payload),
            encoded,
            len(encoded.encode("utf-8")),
            int(protected),
            restored_from_checkpoint_id,
        ),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("SQLite did not return a checkpoint ID")
    return cursor.lastrowid


def create_batch_checkpoint(
    db_file: Path,
    batch_id: str,
    *,
    reason: str,
    source: str,
    protected: bool = False,
) -> int:
    initialize(db_file)
    with transaction(db_file) as connection:
        return create_batch_checkpoint_in_connection(
            connection,
            batch_id,
            reason=reason,
            source=source,
            protected=protected,
        )


def list_batch_checkpoints(db_file: Path, batch_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    initialize(db_file)
    with connect(db_file) as connection:
        rows = connection.execute(
            "SELECT checkpoint_id,batch_id,created_at,reason,source,item_count,payload_bytes,"
            "protected,restored_from_checkpoint_id "
            "FROM batch_checkpoints WHERE batch_id=? ORDER BY checkpoint_id DESC LIMIT ?",
            (batch_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def restore_batch_checkpoint(db_file: Path, checkpoint_id: int) -> int:
    initialize(db_file)
    with transaction(db_file) as connection:
        row = connection.execute(
            "SELECT * FROM batch_checkpoints WHERE checkpoint_id=?", (checkpoint_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown checkpoint: {checkpoint_id}")
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Checkpoint {checkpoint_id} is corrupted") from exc
        if not isinstance(payload, list):
            raise ValueError(f"Checkpoint {checkpoint_id} payload is invalid")
        batch_id = str(row["batch_id"])
        current_ids = {
            str(item[0])
            for item in connection.execute(
                "SELECT item_id FROM items WHERE batch_id=?", (batch_id,)
            ).fetchall()
        }
        snapshot_ids = {str(snapshot.get("item_id") or "") for snapshot in payload}
        if not snapshot_ids or snapshot_ids != current_ids:
            raise ValueError(
                "Checkpoint item set does not match the current batch; restore was refused"
            )
        create_batch_checkpoint_in_connection(
            connection,
            batch_id,
            reason=f"Before restoring checkpoint {checkpoint_id}",
            source="ROLLBACK_SAFETY",
            protected=True,
            restored_from_checkpoint_id=checkpoint_id,
        )
        restored = 0
        for snapshot in payload:
            item_id = str(snapshot["item_id"])
            updates = {field: snapshot.get(field) for field in CHECKPOINT_FIELDS if field != "item_id"}
            update_item_in_connection(
                connection,
                item_id,
                updates,
                source="CHECKPOINT_RESTORE",
                reason=f"Restored checkpoint {checkpoint_id}: {row['reason']}",
            )
            restored += 1
        return restored


def prune_batch_checkpoints(
    db_file: Path,
    *,
    keep_per_batch: int = 30,
    max_age_days: int = 90,
) -> int:
    initialize(db_file)
    cutoff = (datetime.now().astimezone() - timedelta(days=max_age_days)).isoformat(
        timespec="microseconds"
    )
    removed = 0
    with transaction(db_file) as connection:
        batches = [
            str(row[0]) for row in connection.execute(
                "SELECT DISTINCT batch_id FROM batch_checkpoints"
            ).fetchall()
        ]
        for batch_id in batches:
            keep_ids = {
                int(row[0])
                for row in connection.execute(
                    "SELECT checkpoint_id FROM batch_checkpoints WHERE batch_id=? "
                    "ORDER BY checkpoint_id DESC LIMIT ?",
                    (batch_id, keep_per_batch),
                ).fetchall()
            }
            candidates = connection.execute(
                "SELECT checkpoint_id FROM batch_checkpoints "
                "WHERE batch_id=? AND protected=0 AND created_at<?",
                (batch_id, cutoff),
            ).fetchall()
            for candidate in candidates:
                checkpoint = int(candidate[0])
                if checkpoint in keep_ids:
                    continue
                connection.execute(
                    "DELETE FROM batch_checkpoints WHERE checkpoint_id=?", (checkpoint,)
                )
                removed += 1
    return removed


CSV_STAGE_TTL_DAYS = 7


def save_csv_staging(
    db_file: Path,
    *,
    token: str,
    batch_id: str,
    filename: str,
    payload: list[dict[str, Any]],
    diff: dict[str, Any],
    blocking_errors: list[str],
    upload_bytes: int = 0,
    protected: bool = False,
) -> None:
    initialize(db_file)
    created = now()
    expires = (datetime.now().astimezone() + timedelta(days=CSV_STAGE_TTL_DAYS)).isoformat(
        timespec="microseconds"
    )
    with transaction(db_file) as connection:
        connection.execute(
            """INSERT INTO csv_staging(
                   token,batch_id,filename,created_at,updated_at,expires_at,status,row_count,
                   upload_bytes,protected,payload_json,diff_json,blocking_errors_json
               ) VALUES(?,?,?,?,?,?,'STAGED',?,?,?,?,?,?)
               ON CONFLICT(token) DO UPDATE SET
                   batch_id=excluded.batch_id,
                   filename=excluded.filename,
                   updated_at=excluded.updated_at,
                   expires_at=excluded.expires_at,
                   status='STAGED',
                   row_count=excluded.row_count,
                   upload_bytes=excluded.upload_bytes,
                   protected=excluded.protected,
                   payload_json=excluded.payload_json,
                   diff_json=excluded.diff_json,
                   blocking_errors_json=excluded.blocking_errors_json""",
            (
                token,
                batch_id,
                filename,
                created,
                created,
                expires,
                len(payload),
                int(upload_bytes),
                int(protected),
                json.dumps(payload),
                json.dumps(diff),
                json.dumps(blocking_errors),
            ),
        )


def get_csv_staging(db_file: Path, token: str, *, include_inactive: bool = False) -> dict[str, Any] | None:
    initialize(db_file)
    with transaction(db_file) as connection:
        row = connection.execute("SELECT * FROM csv_staging WHERE token=?", (token,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        if result["status"] == "STAGED" and str(result["expires_at"]) < now():
            connection.execute(
                "UPDATE csv_staging SET status='EXPIRED',updated_at=? WHERE token=?",
                (now(), token),
            )
            result["status"] = "EXPIRED"
        if not include_inactive and result["status"] != "STAGED":
            return None
    result["payload"] = json.loads(result.pop("payload_json"))
    result["diff"] = json.loads(result.pop("diff_json"))
    result["blocking_errors"] = json.loads(result.pop("blocking_errors_json"))
    return result


def mark_csv_staging_applied_in_connection(
    connection: sqlite3.Connection,
    token: str,
) -> None:
    timestamp = now()
    cursor = connection.execute(
        "UPDATE csv_staging SET status='APPLIED',applied_at=?,updated_at=? "
        "WHERE token=? AND status='STAGED'",
        (timestamp, timestamp, token),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("CSV stage is no longer active")


def delete_csv_staging(db_file: Path, token: str) -> None:
    initialize(db_file)
    with transaction(db_file) as connection:
        connection.execute(
            "UPDATE csv_staging SET status='CANCELLED',updated_at=? "
            "WHERE token=? AND status='STAGED'",
            (now(), token),
        )


def cleanup_csv_staging(db_file: Path, *, purge_after_days: int = 30) -> dict[str, int]:
    initialize(db_file)
    timestamp = now()
    purge_before = (datetime.now().astimezone() - timedelta(days=purge_after_days)).isoformat(
        timespec="microseconds"
    )
    with transaction(db_file) as connection:
        expired = connection.execute(
            "UPDATE csv_staging SET status='EXPIRED',updated_at=? "
            "WHERE status='STAGED' AND expires_at<? AND protected=0",
            (timestamp, timestamp),
        ).rowcount
        purged = connection.execute(
            "DELETE FROM csv_staging WHERE protected=0 AND status IN ('EXPIRED','CANCELLED','APPLIED') "
            "AND updated_at<?",
            (purge_before,),
        ).rowcount
    return {"expired": int(expired), "purged": int(purged)}


def csv_stage_summary(db_file: Path) -> dict[str, int]:
    initialize(db_file)
    with connect(db_file) as connection:
        rows = connection.execute(
            "SELECT status,COUNT(*) FROM csv_staging GROUP BY status"
        ).fetchall()
    result = {"STAGED": 0, "APPLIED": 0, "CANCELLED": 0, "EXPIRED": 0}
    result.update({str(row[0]): int(row[1]) for row in rows})
    return result


def test_contamination_count(db_file: Path, *, batch_id: str | None = None) -> int:
    initialize(db_file)
    where = "WHERE i.batch_id=?" if batch_id else ""
    values: tuple[Any, ...] = (batch_id,) if batch_id else ()
    with connect(db_file) as connection:
        return int(connection.execute(
            f"""SELECT COUNT(DISTINCT i.item_id)
                FROM items i
                LEFT JOIN recognition_results r ON r.item_id=i.item_id
                {where}
                AND (UPPER(COALESCE(r.source_kind,''))='TEST'
                     OR LOWER(COALESCE(i.recognition_provider,'')) IN
                        ('mock','fixture','demo','synthetic','test'))"""
            if where else
            """SELECT COUNT(DISTINCT i.item_id)
                FROM items i
                LEFT JOIN recognition_results r ON r.item_id=i.item_id
                WHERE UPPER(COALESCE(r.source_kind,''))='TEST'
                   OR LOWER(COALESCE(i.recognition_provider,'')) IN
                      ('mock','fixture','demo','synthetic','test')""",
            values,
        ).fetchone()[0])


def import_journal_summary(db_file: Path) -> dict[str, int]:
    initialize(db_file)
    with connect(db_file) as connection:
        rows = connection.execute(
            "SELECT status,COUNT(*) FROM import_journal GROUP BY status"
        ).fetchall()
    return {str(row[0]): int(row[1]) for row in rows}


def checkpoint_summary(db_file: Path, *, batch_id: str | None = None) -> dict[str, int]:
    initialize(db_file)
    clause = "WHERE batch_id=?" if batch_id else ""
    values: tuple[Any, ...] = (batch_id,) if batch_id else ()
    with connect(db_file) as connection:
        row = connection.execute(
            f"SELECT COUNT(*),COALESCE(SUM(payload_bytes),0),COALESCE(SUM(protected),0) "
            f"FROM batch_checkpoints {clause}",
            values,
        ).fetchone()
    return {"count": int(row[0]), "bytes": int(row[1]), "protected": int(row[2])}


def storage_summary(db_file: Path) -> dict[str, int]:
    return {
        "database_bytes": db_file.stat().st_size if db_file.exists() else 0,
        "wal_bytes": Path(f"{db_file}-wal").stat().st_size if Path(f"{db_file}-wal").exists() else 0,
        "shm_bytes": Path(f"{db_file}-shm").stat().st_size if Path(f"{db_file}-shm").exists() else 0,
    }


def batch_health(db_file: Path, batch_id: str, *, low_confidence: float = 0.70) -> dict[str, int]:
    items = list_items(db_file, batch_id=batch_id)
    test_items = sum(
        1
        for item in items
        if str(item.get("suggestion_source_kind") or "").upper() == "TEST"
        or str(item.get("recognition_provider") or "").casefold()
        in {"mock", "fixture", "demo", "synthetic", "test"}
    )
    return {
        "total": len(items),
        "approved": sum(1 for item in items if item["review_status"] == "DONE"),
        "unfinished": sum(1 for item in items if item["review_status"] == "UNFINISHED"),
        "failed": sum(1 for item in items if item["recognition_status"] == "FAILED"),
        "blocked": sum(1 for item in items if item["recognition_status"] == "BLOCKED"),
        "flagged": sum(1 for item in items if item["review"]),
        "rare": sum(1 for item in items if item["rare"]),
        "low_confidence": sum(
            1 for item in items
            if item.get("display_confidence") is not None
            and float(item["display_confidence"]) < low_confidence
        ),
        "missing_required": sum(
            1 for item in items if not str(item["title"] or "").strip() or item["price_cents"] is None
        ),
        "test_sourced": test_items,
        "publish_blockers": sum(
            1 for item in items
            if item["validation_status"] != "READY"
            or (
                str(item.get("suggestion_source_kind") or "").upper() == "TEST"
                and str(item.get("working_source") or "") != "INDIVIDUAL_REVIEW"
            )
        ),
        "changed_since_recognition": sum(
            1 for item in items if str(item.get("working_source") or "IMPORT") not in {"IMPORT", "AI_ACCEPTED"}
        ),
        "readiness_percent": int(round(
            100 * sum(
                1 for item in items
                if item["validation_status"] == "READY"
                and not (
                    str(item.get("suggestion_source_kind") or "").upper() == "TEST"
                    and str(item.get("working_source") or "") != "INDIVIDUAL_REVIEW"
                )
            ) / max(1, len(items))
        )),
    }


def confidence_buckets(db_file: Path, batch_id: str) -> dict[str, int]:
    items = list_items(db_file, batch_id=batch_id)
    values = [
        float(item["display_confidence"])
        for item in items
        if item.get("display_confidence") is not None
    ]
    manual = sum(
        1 for item in items
        if item.get("display_confidence") is None and item.get("review_status") == "DONE"
    )
    return {
        "98_100": sum(1 for value in values if value >= 0.98),
        "95_98": sum(1 for value in values if 0.95 <= value < 0.98),
        "90_95": sum(1 for value in values if 0.90 <= value < 0.95),
        "below_90": sum(1 for value in values if value < 0.90),
        "manual": manual,
        "unknown": len(items) - len(values) - manual,
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
        recognition = connection.execute(
            """SELECT COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0),
                      COALESCE(SUM(input_image_bytes),0),COALESCE(SUM(input_image_count),0)
               FROM recognition_results
               WHERE item_id IN (SELECT item_id FROM items WHERE batch_id=?)""",
            (batch_id,),
        ).fetchone()
        media = connection.execute(
            """SELECT COUNT(*),
                      COALESCE(SUM(CASE WHEN kind='command' THEN 1 ELSE 0 END),0),
                      COALESCE(SUM(CASE WHEN kind='excluded' THEN 1 ELSE 0 END),0),
                      COALESCE(SUM(CASE WHEN ai_eligible=0 AND kind='product' THEN 1 ELSE 0 END),0),
                      COALESCE(SUM(original_bytes),0),COALESCE(SUM(preview_bytes),0),
                      COALESCE(SUM(recognition_bytes),0)
               FROM photos WHERE batch_id=?""",
            (batch_id,),
        ).fetchone()
    approvals = len(approval_rows)
    elapsed_minutes = 0.0
    if approvals >= 2:
        try:
            first = datetime.fromisoformat(str(approval_rows[0][0]))
            last = datetime.fromisoformat(str(approval_rows[-1][0]))
            elapsed_seconds = (last - first).total_seconds()
            if elapsed_seconds >= 5:
                elapsed_minutes = elapsed_seconds / 60
        except ValueError:
            elapsed_minutes = 0.0
    approvals_per_minute = round(approvals / elapsed_minutes, 2) if elapsed_minutes else 0.0
    original_bytes = int(media[4])
    provider_payload_bytes = int(recognition[2])
    bandwidth_saved = max(0, original_bytes - provider_payload_bytes) if provider_payload_bytes else 0
    reduction = round(100 * bandwidth_saved / original_bytes, 1) if original_bytes and provider_payload_bytes else 0.0
    return {
        "approval_events": approvals,
        "approvals_per_minute": approvals_per_minute,
        "throughput_window_valid": bool(elapsed_minutes),
        "total_changes": change_count,
        "total_photos": int(media[0]),
        "command_images": int(media[1]),
        "excluded_images": int(media[2]),
        "ai_ineligible_product_images": int(media[3]),
        "provider_selected_images": int(recognition[3]),
        "original_bytes": original_bytes,
        "preview_bytes": int(media[5]),
        "recognition_derivative_bytes": int(media[6]),
        "provider_payload_bytes": provider_payload_bytes,
        "bandwidth_saved": bandwidth_saved,
        "payload_reduction_percent": reduction,
        "input_tokens": int(recognition[0]),
        "output_tokens": int(recognition[1]),
        "estimated_api_cost": "Not calculated",
    }


def media_totals(db_file: Path) -> dict[str, int]:
    initialize(db_file)
    with connect(db_file) as connection:
        row = connection.execute(
            """SELECT COUNT(*),
                      COALESCE(SUM(CASE WHEN kind='command' THEN 1 ELSE 0 END),0),
                      COALESCE(SUM(CASE WHEN kind='excluded' THEN 1 ELSE 0 END),0),
                      COALESCE(SUM(CASE WHEN ai_eligible=0 AND kind='product' THEN 1 ELSE 0 END),0),
                      COALESCE(SUM(original_bytes),0),COALESCE(SUM(preview_bytes),0),
                      COALESCE(SUM(recognition_bytes),0)
               FROM photos"""
        ).fetchone()
        payload = connection.execute(
            "SELECT COALESCE(SUM(input_image_bytes),0),COALESCE(SUM(input_image_count),0) "
            "FROM recognition_results"
        ).fetchone()
    return {
        "total_photos": int(row[0]),
        "command_images": int(row[1]),
        "excluded_images": int(row[2]),
        "ai_ineligible_product_images": int(row[3]),
        "original_bytes": int(row[4]),
        "preview_bytes": int(row[5]),
        "recognition_derivative_bytes": int(row[6]),
        "provider_payload_bytes": int(payload[0]),
        "provider_selected_images": int(payload[1]),
    }


def list_editor_items(db_file: Path, batch_id: str) -> list[dict[str, Any]]:
    return list_items(db_file, batch_id=batch_id)

def get_item_movie_link(db_file: Path, item_id: str) -> dict[str, Any] | None:
    initialize(db_file)
    with connect(db_file) as connection:
        row = connection.execute(
            "SELECT * FROM item_movie_links WHERE item_id=?", (item_id,)
        ).fetchone()
    return dict(row) if row else None


def set_item_movie_link(
    db_file: Path,
    *,
    item_id: str,
    movie_id: str,
    link_status: str,
    link_method: str,
    recognition_result_id: int | None,
    match_score: float | None,
    operator_confirmed: bool,
    catalog_revision: int | None,
    source: str = "SLMC",
) -> None:
    """Set the one current cross-database link and preserve an auditable event.

    The caller must validate that movie_id exists in movie_catalog.sqlite3 before
    invoking this function. SQLite cannot enforce that relationship across files.
    """

    initialize(db_file)
    if not movie_id.startswith("MOV-"):
        raise ValueError("Movie ID must use the immutable MOV- identifier format")
    timestamp = now()
    with transaction(db_file) as connection:
        item = connection.execute("SELECT item_id FROM items WHERE item_id=?", (item_id,)).fetchone()
        if item is None:
            raise KeyError(f"Unknown Item ID: {item_id}")
        if recognition_result_id is not None:
            result = connection.execute(
                "SELECT item_id FROM recognition_results WHERE recognition_result_id=?",
                (recognition_result_id,),
            ).fetchone()
            if result is None or str(result[0]) != item_id:
                raise ValueError("Recognition result does not belong to the Item being linked")
        previous = connection.execute(
            "SELECT movie_id,link_status FROM item_movie_links WHERE item_id=?", (item_id,)
        ).fetchone()
        previous_movie_id = str(previous[0] or "") if previous else ""
        linked_at = timestamp if previous_movie_id != movie_id else None
        connection.execute(
            """INSERT INTO item_movie_links(
                   item_id,movie_id,link_status,link_method,recognition_result_id,match_score,
                   linked_at,updated_at,operator_confirmed,catalog_revision,last_error
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(item_id) DO UPDATE SET
                   movie_id=excluded.movie_id,link_status=excluded.link_status,
                   link_method=excluded.link_method,recognition_result_id=excluded.recognition_result_id,
                   match_score=excluded.match_score,
                   linked_at=CASE WHEN item_movie_links.movie_id IS NOT excluded.movie_id
                                  THEN excluded.updated_at ELSE item_movie_links.linked_at END,
                   updated_at=excluded.updated_at,operator_confirmed=excluded.operator_confirmed,
                   catalog_revision=excluded.catalog_revision,last_error=''""",
            (
                item_id,
                movie_id,
                link_status,
                link_method,
                recognition_result_id,
                match_score,
                linked_at or timestamp,
                timestamp,
                int(operator_confirmed),
                catalog_revision,
                "",
            ),
        )
        event_type = "LINKED" if not previous_movie_id else (
            "RELINKED" if previous_movie_id != movie_id else "LINK_REFRESHED"
        )
        connection.execute(
            """INSERT INTO item_movie_link_events(
                   item_id,previous_movie_id,movie_id,event_type,link_status,link_method,
                   recognition_result_id,match_score,operator_confirmed,catalog_revision,
                   occurred_at,source,details_json
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item_id,
                previous_movie_id or None,
                movie_id,
                event_type,
                link_status,
                link_method,
                recognition_result_id,
                match_score,
                int(operator_confirmed),
                catalog_revision,
                timestamp,
                source,
                json.dumps({"previous_status": str(previous[1]) if previous else ""}),
            ),
        )


def mark_item_catalog_unavailable(
    db_file: Path,
    item_id: str,
    recognition_result_id: int | None,
    error: str,
) -> None:
    initialize(db_file)
    timestamp = now()
    with transaction(db_file) as connection:
        item = connection.execute("SELECT item_id FROM items WHERE item_id=?", (item_id,)).fetchone()
        if item is None:
            raise KeyError(f"Unknown Item ID: {item_id}")
        previous = connection.execute(
            "SELECT movie_id FROM item_movie_links WHERE item_id=?", (item_id,)
        ).fetchone()
        previous_movie_id = str(previous[0] or "") if previous else ""
        connection.execute(
            """INSERT INTO item_movie_links(
                   item_id,movie_id,link_status,link_method,recognition_result_id,match_score,
                   linked_at,updated_at,operator_confirmed,catalog_revision,last_error
               ) VALUES(?,NULL,'CATALOG_UNAVAILABLE','',?,NULL,NULL,?,0,NULL,?)
               ON CONFLICT(item_id) DO UPDATE SET
                   link_status='CATALOG_UNAVAILABLE',link_method='',recognition_result_id=excluded.recognition_result_id,
                   updated_at=excluded.updated_at,last_error=excluded.last_error""",
            (item_id, recognition_result_id, timestamp, error[:2000]),
        )
        connection.execute(
            """INSERT INTO item_movie_link_events(
                   item_id,previous_movie_id,movie_id,event_type,link_status,link_method,
                   recognition_result_id,occurred_at,source,details_json
               ) VALUES(?,?,NULL,'CATALOG_UNAVAILABLE','CATALOG_UNAVAILABLE','',?,?,?,?)""",
            (
                item_id,
                previous_movie_id or None,
                recognition_result_id,
                timestamp,
                "SLMC",
                json.dumps({"error": error[:2000]}),
            ),
        )


def mark_item_movie_link_stale(db_file: Path, item_id: str, *, reason: str) -> None:
    initialize(db_file)
    timestamp = now()
    with transaction(db_file) as connection:
        row = connection.execute(
            "SELECT * FROM item_movie_links WHERE item_id=?", (item_id,)
        ).fetchone()
        if row is None:
            return
        connection.execute(
            "UPDATE item_movie_links SET link_status='STALE',updated_at=?,last_error=? WHERE item_id=?",
            (timestamp, reason, item_id),
        )
        connection.execute(
            """INSERT INTO item_movie_link_events(
                   item_id,previous_movie_id,movie_id,event_type,link_status,link_method,
                   recognition_result_id,match_score,operator_confirmed,catalog_revision,
                   occurred_at,source,details_json
               ) VALUES(?,?,?,'STALE','STALE',?,?,?,?,?,?,?,?)""",
            (
                item_id,
                row["movie_id"],
                row["movie_id"],
                row["link_method"],
                row["recognition_result_id"],
                row["match_score"],
                row["operator_confirmed"],
                row["catalog_revision"],
                timestamp,
                "OPERATOR_CORRECTION",
                json.dumps({"reason": reason}),
            ),
        )


def item_movie_link_history(db_file: Path, item_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
    initialize(db_file)
    with connect(db_file) as connection:
        rows = connection.execute(
            "SELECT * FROM item_movie_link_events WHERE item_id=? ORDER BY link_event_id DESC LIMIT ?",
            (item_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def movie_link_summary(db_file: Path) -> dict[str, int]:
    initialize(db_file)
    with connect(db_file) as connection:
        return {
            "linked_items": int(connection.execute(
                "SELECT COUNT(*) FROM item_movie_links WHERE movie_id IS NOT NULL AND link_status!='STALE'"
            ).fetchone()[0]),
            "stale_links": int(connection.execute(
                "SELECT COUNT(*) FROM item_movie_links WHERE link_status='STALE'"
            ).fetchone()[0]),
            "unlinked_recognized_items": int(connection.execute(
                """SELECT COUNT(*) FROM items i
                   WHERE i.recognition_status='COMPLETE'
                     AND NOT EXISTS(
                         SELECT 1 FROM item_movie_links l
                         WHERE l.item_id=i.item_id AND l.movie_id IS NOT NULL AND l.link_status!='STALE'
                     )"""
            ).fetchone()[0]),
        }
