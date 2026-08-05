from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from snapims import db
from snapims.config import DataPaths


def test_v0123_release_fixture_migrates_forward_without_data_loss(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "v0123_upgrade" / "data"
    data = tmp_path / "data"
    shutil.copytree(fixture, data)
    paths = DataPaths.from_root(data).ensure()

    before = sqlite3.connect(paths.db_file)
    try:
        assert before.execute("PRAGMA user_version").fetchone()[0] == 13
        batch_ids = [row[0] for row in before.execute("SELECT batch_id FROM batches")]
        item_ids = [row[0] for row in before.execute("SELECT item_id FROM items ORDER BY sequence")]
    finally:
        before.close()

    db.initialize(paths.db_file, paths=paths)

    with db.connect(paths.db_file) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 15
        assert [row[0] for row in connection.execute("SELECT batch_id FROM batches")] == batch_ids
        assert [
            row[0] for row in connection.execute("SELECT item_id FROM items ORDER BY sequence")
        ] == item_ids
        assert connection.execute(
            "SELECT COUNT(*) FROM items WHERE title='Preserved Legacy Title'"
        ).fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='import_jobs'"
        ).fetchone()[0] == 1

    assert list(paths.backups.glob("*before-schema-v15*.sqlite3"))
