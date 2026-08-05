from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapims import db
from snapims.recognition.service import (
    accept_item,
    claim_item_recognition_lease,
    release_item_recognition_lease,
)
from snapims.web.app import app
from tests.helpers import ready_item


def test_schema_14_contains_durable_item_lease(tmp_path: Path, data_paths) -> None:
    db.initialize(data_paths.db_file, paths=data_paths)
    with db.connect(data_paths.db_file) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 15
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(recognition_item_leases)")
        }
        indexes = {
            str(row[1])
            for row in connection.execute("PRAGMA index_list(recognition_item_leases)")
        }
    assert {"item_id", "owner_kind", "owner_id", "status", "expires_at"} <= columns
    assert "idx_recognition_item_leases_status" in indexes


def test_item_lease_blocks_batch_and_request_overlap(tmp_path: Path, data_paths) -> None:
    _, item = ready_item(tmp_path, data_paths)
    item_id = str(item["item_id"])
    assert claim_item_recognition_lease(
        data_paths.db_file, item_id, owner_kind="BATCH", owner_id="batch-owner"
    )
    assert not claim_item_recognition_lease(
        data_paths.db_file, item_id, owner_kind="REQUEST", owner_id="request-owner"
    )
    release_item_recognition_lease(
        data_paths.db_file, item_id, owner_kind="BATCH", owner_id="batch-owner"
    )
    assert claim_item_recognition_lease(
        data_paths.db_file, item_id, owner_kind="REQUEST", owner_id="request-owner"
    )


def test_quick_accept_rejects_stale_revision(tmp_path: Path, data_paths) -> None:
    _, item = ready_item(tmp_path, data_paths)
    item_id = str(item["item_id"])
    stale_revision = int(item["record_revision"])
    db.update_item(
        data_paths.db_file,
        item_id,
        {"title": "New authoritative title"},
        expected_revision=stale_revision,
    )
    with pytest.raises(RuntimeError, match="changed in another session"):
        accept_item(
            data_paths.db_file,
            item_id,
            price_cents=int(item["price_cents"]),
            discount_percent=float(item["discount_percent"]),
            title_override="Stale title",
            expected_revision=stale_revision,
        )
    assert db.get_item(data_paths.db_file, item_id)["title"] == "New authoritative title"


def test_recognition_metadata_acceptance_can_preserve_commercial_fields(
    tmp_path: Path, data_paths
) -> None:
    _, item = ready_item(tmp_path, data_paths)
    item_id = str(item["item_id"])
    db.update_item(
        data_paths.db_file,
        item_id,
        {"price_cents": 2499, "discount_percent": 12.5},
    )
    current = db.get_item(data_paths.db_file, item_id)
    assert current is not None
    with db.transaction(data_paths.db_file) as connection:
        cursor = connection.execute(
            """INSERT INTO recognition_results(
                   item_id,provider,created_at,suggested_title,suggested_price_cents,
                   suggested_discount_percent,confidence,attempt_uuid,tier,trigger,
                   selected_images_json,title_evidence_json,field_evidence_json,
                   contradiction_flags_json
               ) VALUES(?,?,?,?,?,?,?,?,?,?, '[]','[]','{}','[]')""",
            (
                item_id,
                "mock",
                db.now(),
                "Replacement metadata title",
                100,
                0,
                0.99,
                "v0101-commercial-preserve",
                "baseline",
                "TEST",
            ),
        )
        result_id = int(cursor.lastrowid)
        connection.execute(
            """INSERT INTO recognition_attempt_states(
                   recognition_result_id,state,selected_at,selected_by,updated_at
               ) VALUES(?,'SELECTED',?,'test',?)""",
            (result_id, db.now(), db.now()),
        )
        connection.execute(
            """INSERT INTO item_recognition_selection(
                   item_id,recognition_result_id,selected_by,selected_at
               ) VALUES(?,?,?,?)
                   ON CONFLICT(item_id) DO UPDATE SET
                       recognition_result_id=excluded.recognition_result_id,
                       selected_by=excluded.selected_by,
                       selected_at=excluded.selected_at""",
            (item_id, result_id, "test", db.now()),
        )
    errors = accept_item(
        data_paths.db_file,
        item_id,
        price_cents=2499,
        discount_percent=12.5,
        replace_approved=True,
        expected_revision=int(current["record_revision"]),
    )
    assert errors == []
    saved = db.get_item(data_paths.db_file, item_id)
    assert saved["title"] == "Replacement metadata title"
    assert saved["price_cents"] == 2499
    assert saved["discount_percent"] == 12.5


def test_auth_disabled_state_change_still_requires_csrf(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SNAPIMS_AUTH_SECRET", "")
    monkeypatch.setenv("SNAPIMS_ADMIN_PASSWORD_HASH", "")
    with TestClient(app, base_url="http://testserver", auto_csrf=False) as client:
        client.get("/")
        response = client.post("/import/remove-recent", data={"path": "/tmp"})
        assert response.status_code == 403


def test_auth_disabled_refuses_non_local_host(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SNAPIMS_AUTH_SECRET", "")
    monkeypatch.setenv("SNAPIMS_ADMIN_PASSWORD_HASH", "")
    with TestClient(app, base_url="http://ims.canadavhs.ca") as client:
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 503
        assert response.json()["detail"].startswith("Authentication is required")


def test_recognition_totals_source_is_not_display_limit() -> None:
    source = Path("snapims/web/app.py").read_text(encoding="utf-8")
    assert '"basis": "all matching attempts' in source
    assert "SELECT COUNT(*) AS attempts" in source


def test_batch_editor_has_serialized_item_queue() -> None:
    source = Path("snapims/web/static/app.js").read_text(encoding="utf-8")
    assert "const saveQueues = new Map()" in source
    assert "const prior = saveQueues.get(itemId)" in source
    assert "Saving latest change" in source


def test_tag_picker_exposes_combobox_state() -> None:
    source = Path("snapims/web/static/app.js").read_text(encoding="utf-8")
    for value in ("aria-expanded", "aria-controls", "aria-activedescendant"):
        assert value in source


def test_no_accidental_terminal_help_file() -> None:
    assert not Path('ion bump"').exists()


def test_release_version_is_current() -> None:
    import snapims

    assert snapims.__version__ == "0.13.2"
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.9.' not in pyproject
