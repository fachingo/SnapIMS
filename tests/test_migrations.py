from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from snapims import db
from snapims.recognition import repository


def _write_legacy_v1_database(db_file: Path) -> None:
    """Build a real schema-v1 database, bypassing db.initialize entirely."""
    with sqlite3.connect(db_file) as connection:
        connection.executescript(db.SCHEMA_SQL)
        connection.execute(
            """
            INSERT INTO schema_migrations(version, applied_at, description)
            VALUES(1, '2026-07-16T20:00:00', 'legacy')
            """
        )
        connection.execute(
            """
            INSERT INTO batches(
                batch_id, source_fingerprint, source_folder, created_at, imported_at,
                started, ended, item_count, product_photo_count, command_count,
                warning_count
            ) VALUES(
                'BATCH-1', 'fingerprint', '/camera', '2026-07-16T20:00:00',
                '2026-07-16T20:00:00', 1, 1, 1, 1, 2, 0
            )
            """
        )
        connection.execute(
            """
            INSERT INTO items(
                item_id, sku, batch_id, sequence, shelf, review, rare, created_at, updated_at
            ) VALUES(
                'ITEM-1', 'ITEM-1', 'BATCH-1', 1, 'A1', 1, 1,
                '2026-07-16T20:00:00', '2026-07-16T20:00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO recognition_results(
                item_id, provider, created_at, suggested_title, confidence
            ) VALUES(
                'ITEM-1', 'openai', '2026-07-16T20:01:00', 'Legacy title', 0.4
            )
            """
        )


def _backup_dir(db_file: Path) -> Path:
    return db_file.parent / "migration-backups"


def test_migrating_existing_database_creates_backup_and_preserves_data(tmp_path) -> None:
    db_file = tmp_path / "legacy.sqlite3"
    _write_legacy_v1_database(db_file)

    db.initialize(db_file)

    backups = list(_backup_dir(db_file).glob("*.sqlite3"))
    assert backups, "expected an online backup before altering an existing database"

    with db.connect(db_file) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
        assert connection.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
        applied = {
            row[0] for row in connection.execute("SELECT version FROM schema_migrations")
        }
        assert applied == {version for version, _, _ in db.MIGRATIONS}

    item = db.get_item(db_file, "ITEM-1")
    assert item is not None
    assert item["review"] == 1
    assert item["rare"] == 1

    queue = repository.list_review_queue(db_file, batch_id_value="BATCH-1")
    assert any(entry.result.item_id == "ITEM-1" for entry in queue)

    # The backup itself must be a valid, openable copy of the pre-migration state.
    backup_connection = sqlite3.connect(backups[0])
    try:
        backup_version = backup_connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0]
    finally:
        backup_connection.close()
    assert backup_version == 1


def test_migration_failure_does_not_record_false_version_and_stays_recoverable(
    tmp_path, monkeypatch
) -> None:
    db_file = tmp_path / "legacy.sqlite3"
    _write_legacy_v1_database(db_file)

    broken_migrations = (
        db.MIGRATIONS[0],
        (
            2,
            "Broken migration for fault-injection test",
            "ALTER TABLE items ADD COLUMN totally_new TEXT; THIS IS NOT VALID SQL;",
        ),
        db.MIGRATIONS[2],
    )
    monkeypatch.setattr(db, "MIGRATIONS", broken_migrations)

    with pytest.raises(sqlite3.OperationalError):
        db.initialize(db_file)

    with db.connect(db_file) as connection:
        applied = {
            row[0] for row in connection.execute("SELECT version FROM schema_migrations")
        }
        assert applied == {1}
        assert connection.execute("PRAGMA user_version").fetchone()[0] != 2
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(items)")}
        assert "totally_new" not in columns
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    backups = list(_backup_dir(db_file).glob("*.sqlite3"))
    assert backups, "a recovery backup must exist even though the migration failed"

    monkeypatch.undo()
    db.initialize(db_file)
    with db.connect(db_file) as connection:
        applied = {
            row[0] for row in connection.execute("SELECT version FROM schema_migrations")
        }
        assert applied == {version for version, _, _ in db.MIGRATIONS}
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_new_empty_database_initializes_without_a_pointless_backup(tmp_path) -> None:
    db_file = tmp_path / "fresh.sqlite3"
    assert not db_file.exists()

    db.initialize(db_file)

    assert not _backup_dir(db_file).exists()
    with db.connect(db_file) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION


def test_repeated_initialize_is_idempotent(tmp_path) -> None:
    db_file = tmp_path / "fresh.sqlite3"

    db.initialize(db_file)
    db.initialize(db_file)
    db.initialize(db_file)

    assert not _backup_dir(db_file).exists()
    with db.connect(db_file) as connection:
        rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
        versions = [row[0] for row in rows]
        assert sorted(versions) == sorted(version for version, _, _ in db.MIGRATIONS)
        assert len(versions) == len(set(versions))
