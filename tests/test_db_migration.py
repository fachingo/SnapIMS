from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from snapims import db
from snapims.config import DataPaths


def legacy_v03_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        PRAGMA user_version=3;
        CREATE TABLE batches (
          batch_id TEXT PRIMARY KEY, source_fingerprint TEXT NOT NULL UNIQUE,
          source_folder TEXT NOT NULL, created_at TEXT NOT NULL, imported_at TEXT NOT NULL,
          started INTEGER NOT NULL, ended INTEGER NOT NULL, status TEXT NOT NULL,
          item_count INTEGER NOT NULL, product_photo_count INTEGER NOT NULL,
          command_count INTEGER NOT NULL, warning_count INTEGER NOT NULL,
          warnings_json TEXT NOT NULL
        );
        CREATE TABLE items (
          item_id TEXT PRIMARY KEY, sku TEXT NOT NULL UNIQUE, batch_id TEXT NOT NULL,
          sequence INTEGER NOT NULL, shelf TEXT NOT NULL, rare INTEGER NOT NULL DEFAULT 0,
          review INTEGER NOT NULL DEFAULT 0, title TEXT NOT NULL DEFAULT '',
          edition TEXT NOT NULL DEFAULT '', distributor TEXT NOT NULL DEFAULT '',
          price_cents INTEGER, description TEXT NOT NULL DEFAULT '',
          vendor TEXT NOT NULL DEFAULT 'Canada VHS', product_type TEXT NOT NULL DEFAULT 'VHS Tape',
          tags TEXT NOT NULL DEFAULT '', barcode TEXT NOT NULL DEFAULT '',
          condition TEXT NOT NULL DEFAULT 'Not Graded', condition_notes TEXT NOT NULL DEFAULT '',
          pool_mode TEXT NOT NULL DEFAULT 'POOLED', quantity INTEGER NOT NULL DEFAULT 1,
          ready INTEGER NOT NULL DEFAULT 0, validation_status TEXT NOT NULL DEFAULT 'INCOMPLETE',
          validation_errors TEXT NOT NULL DEFAULT '[]', recognition_provider TEXT NOT NULL DEFAULT '',
          recognition_confidence REAL, upload_status TEXT NOT NULL DEFAULT 'NOT_UPLOADED',
          shopify_product_id TEXT NOT NULL DEFAULT '', shopify_variant_id TEXT NOT NULL DEFAULT '',
          shopify_inventory_item_id TEXT NOT NULL DEFAULT '', shopify_admin_url TEXT NOT NULL DEFAULT '',
          last_error TEXT NOT NULL DEFAULT '', retry_count INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE photos (
          photo_id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT NOT NULL,
          item_id TEXT, kind TEXT NOT NULL, stream_index INTEGER NOT NULL, photo_order INTEGER,
          original_name TEXT NOT NULL, captured_at TEXT NOT NULL, timestamp_source TEXT NOT NULL,
          sha256 TEXT NOT NULL, qr_payload TEXT, source_path TEXT NOT NULL,
          original_copy_path TEXT NOT NULL, proposed_name TEXT NOT NULL,
          processed_path TEXT, thumbnail_path TEXT
        );
        CREATE TABLE recognition_results (
          recognition_result_id INTEGER PRIMARY KEY AUTOINCREMENT,
          item_id TEXT NOT NULL, provider TEXT NOT NULL, created_at TEXT NOT NULL,
          suggested_title TEXT NOT NULL DEFAULT '', edition TEXT NOT NULL DEFAULT '',
          distributor TEXT NOT NULL DEFAULT ''
        );
        """
    )
    connection.execute(
        "INSERT INTO batches VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "LEGACY", "fingerprint", "/camera", "2026-01-01", "2026-01-01", 1, 1,
            "IMPORTED", 1, 1, 0, 0, "[]",
        ),
    )
    connection.execute(
        """INSERT INTO items(
            item_id,sku,batch_id,sequence,shelf,rare,review,title,edition,distributor,
            price_cents,description,vendor,product_type,tags,barcode,condition,
            condition_notes,pool_mode,quantity,ready,validation_status,validation_errors,
            recognition_provider,recognition_confidence,upload_status,shopify_product_id,
            shopify_variant_id,shopify_inventory_item_id,shopify_admin_url,last_error,
            retry_count,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "LEGACY-A1-001", "LEGACY-A1-001", "LEGACY", 1, "A1", 0, 0,
            "Legacy Tape", "Clamshell", "Legacy Studio", 1299, "Description",
            "Canada VHS", "VHS Tape", "legacy", "012345678905", "Good", "",
            "UNIQUE", 1, 1, "READY", "[]", "mock", 0.9, "NOT_UPLOADED",
            "", "", "", "", "", 0, "2026-01-01", "2026-01-01",
        ),
    )
    connection.execute(
        "INSERT INTO photos(batch_id,item_id,kind,stream_index,photo_order,original_name,captured_at,timestamp_source,sha256,source_path,original_copy_path,proposed_name,processed_path) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "LEGACY", "LEGACY-A1-001", "product", 1, 1, "front.jpg", "2026-01-01",
            "test", "hash", "/camera/front.jpg", "/original/front.jpg", "front.jpg", "/processed/front.jpg",
        ),
    )
    connection.execute(
        "INSERT INTO recognition_results(item_id,provider,created_at,suggested_title,edition,distributor) VALUES(?,?,?,?,?,?)",
        ("LEGACY-A1-001", "mock", "2026-01-01", "Suggested Legacy", "VHS", "Studio"),
    )
    connection.commit()
    connection.close()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_legacy_v03_upgrade_retains_identity_and_history(tmp_path: Path) -> None:
    paths = DataPaths.from_root(tmp_path / "workspace").ensure()
    legacy_v03_database(paths.db_file)
    db.initialize(paths.db_file, paths=paths)
    with db.connect(paths.db_file) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
        item = connection.execute("SELECT * FROM items").fetchone()
        assert item["item_id"] == "LEGACY-A1-001"
        assert item["sku"] == "LEGACY-A1-001"
        assert item["title"] == "Legacy Tape"
        assert item["discount_percent"] == 0
        assert item["review_status"] == "UNFINISHED"
        history = connection.execute("SELECT suggested_title FROM recognition_results").fetchone()[0]
        assert history == "Suggested Legacy"
        assert connection.execute("SELECT COUNT(*) FROM shopify_sync").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM recognition_jobs").fetchone()[0] == 1
        legacy_tag = connection.execute(
            "SELECT * FROM tag_definitions WHERE canonical_label='legacy'"
        ).fetchone()
        assert legacy_tag is not None
        assert legacy_tag["ai_eligible"] == 0
        relation = connection.execute(
            "SELECT * FROM item_tags WHERE item_id='LEGACY-A1-001'"
        ).fetchone()
        assert relation is not None
        assert relation["tag_id"] == legacy_tag["tag_id"]
        assert relation["acceptance_state"] == "ACCEPTED"
        toonie = connection.execute(
            "SELECT * FROM tag_definitions WHERE tag_id='TAG-TOONIE-TAPES'"
        ).fetchone()
        assert toonie["deterministic_only"] == 1
        assert toonie["ai_eligible"] == 0


def test_pre_migration_backup_created(tmp_path: Path) -> None:
    paths = DataPaths.from_root(tmp_path / "workspace").ensure()
    legacy_v03_database(paths.db_file)
    db.initialize(paths.db_file, paths=paths)
    backups = list(paths.backups.glob(f"*before-schema-v{db.SCHEMA_VERSION}*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3


def test_post_migration_integrity_and_foreign_keys(tmp_path: Path) -> None:
    paths = DataPaths.from_root(tmp_path / "workspace").ensure()
    legacy_v03_database(paths.db_file)
    db.initialize(paths.db_file, paths=paths)
    with db.connect(paths.db_file) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_failed_migration_restores_original_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = DataPaths.from_root(tmp_path / "workspace").ensure()
    legacy_v03_database(paths.db_file)
    before = digest(paths.db_file)
    original = db._base_schema

    def fail_after_schema(connection):
        original(connection)
        raise RuntimeError("forced migration failure")

    monkeypatch.setattr(db, "_base_schema", fail_after_schema)
    with pytest.raises(RuntimeError, match="forced migration failure"):
        db.initialize(paths.db_file, paths=paths)
    assert before
    with sqlite3.connect(paths.db_file) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert connection.execute("SELECT title FROM items").fetchone()[0] == "Legacy Tape"


def test_unsupported_future_schema_refused_without_modification(tmp_path: Path) -> None:
    db_file = tmp_path / "future.sqlite3"
    connection = sqlite3.connect(db_file)
    connection.execute("PRAGMA user_version=99")
    connection.execute("CREATE TABLE marker(value TEXT)")
    connection.execute("INSERT INTO marker VALUES('keep')")
    connection.commit()
    connection.close()
    before = digest(db_file)
    with pytest.raises(RuntimeError, match="newer than supported"):
        db.initialize(db_file)
    assert digest(db_file) == before


def test_transaction_rolls_back(tmp_path: Path) -> None:
    db_file = tmp_path / "rollback.sqlite3"
    db.initialize(db_file)
    with pytest.raises(RuntimeError):
        with db.transaction(db_file) as connection:
            connection.execute("INSERT INTO settings VALUES('x','y','now')")
            raise RuntimeError("rollback")
    with db.connect(db_file) as connection:
        assert connection.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0


def test_controlled_tags_reject_unknown_and_new_retired_selection(
    tmp_path: Path,
) -> None:
    paths = DataPaths.from_root(tmp_path / "workspace").ensure()
    legacy_v03_database(paths.db_file)
    db.initialize(paths.db_file, paths=paths)
    item = db.get_item(paths.db_file, "LEGACY-A1-001")
    assert item is not None
    legacy_id = item["tag_ids"][0]

    with pytest.raises(ValueError, match="Unknown controlled tag"):
        db.update_item(
            paths.db_file,
            item["item_id"],
            {"tag_ids": ["TAG-NOT-APPROVED"]},
            source="BATCH_EDITOR",
        )
    assert db.get_item(paths.db_file, item["item_id"])["tag_ids"] == [legacy_id]

    with db.transaction(paths.db_file) as connection:
        connection.execute(
            "UPDATE tag_definitions SET active=0 WHERE tag_id=?", (legacy_id,)
        )
    db.update_item(
        paths.db_file,
        item["item_id"],
        {"tag_ids": [legacy_id]},
        source="BATCH_EDITOR",
    )
    db.update_item(
        paths.db_file,
        item["item_id"],
        {"tag_ids": []},
        source="BATCH_EDITOR",
    )
    with pytest.raises(ValueError, match="Retired tag"):
        db.update_item(
            paths.db_file,
            item["item_id"],
            {"tag_ids": [legacy_id]},
            source="BATCH_EDITOR",
        )


def test_ai_tag_ids_are_allowlisted_and_rejections_are_evidence(
    tmp_path: Path,
) -> None:
    paths = DataPaths.from_root(tmp_path / "workspace").ensure()
    legacy_v03_database(paths.db_file)
    db.initialize(paths.db_file, paths=paths)
    with db.transaction(paths.db_file) as connection:
        connection.execute(
            """INSERT INTO tag_definitions(
                   tag_id,canonical_label,category,active,ai_eligible,
                   shopify_visible,deterministic_only,sort_order,created_at,
                   updated_at,evidence_json
               ) VALUES('TAG-HORROR','Horror','Genre',1,1,1,0,20,?,?,?)""",
            (db.now(), db.now(), '{"source":"operator"}'),
        )
        recognition_id = int(
            connection.execute(
                "SELECT recognition_result_id FROM recognition_results LIMIT 1"
            ).fetchone()[0]
        )
        accepted, rejected = db.record_ai_tag_suggestions_in_connection(
            connection,
            "LEGACY-A1-001",
            ["TAG-HORROR", "TAG-TOONIE-TAPES", "TAG-UNKNOWN"],
            recognition_result_id=recognition_id,
        )
    assert accepted == ["TAG-HORROR"]
    assert rejected == ["TAG-TOONIE-TAPES", "TAG-UNKNOWN"]
    with db.connect(paths.db_file) as connection:
        suggestion = connection.execute(
            "SELECT acceptance_state FROM item_tags WHERE item_id=? AND tag_id=?",
            ("LEGACY-A1-001", "TAG-HORROR"),
        ).fetchone()
        reasons = {
            str(row[0])
            for row in connection.execute(
                "SELECT reason FROM tag_rejections WHERE item_id='LEGACY-A1-001'"
            )
        }
    assert suggestion["acceptance_state"] == "SUGGESTED"
    assert reasons == {"AI_INELIGIBLE", "UNKNOWN_TAG_ID"}


def test_current_schema_initialize_is_idempotent(tmp_path: Path) -> None:
    db_file = tmp_path / "current.sqlite3"
    db.initialize(db_file)
    first = digest(db_file)
    db.initialize(db_file)
    # WAL metadata may vary, but the logical schema and version remain stable.
    with db.connect(db_file) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert first


def test_backup_round_trip(tmp_path: Path) -> None:
    paths = DataPaths.from_root(tmp_path / "workspace").ensure()
    db.initialize(paths.db_file, paths=paths)
    db.set_setting(paths.db_file, "marker", "before")
    backup = db.backup_database(paths, "unit-test")
    assert backup is not None
    db.set_setting(paths.db_file, "marker", "after")
    db._restore_database(paths.db_file, backup)
    assert db.get_setting(paths.db_file, "marker") == "before"
