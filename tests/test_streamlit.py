from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from snapims import db
from snapims.demo import create_demo_batch
from snapims.processor import process_batch
from snapims.recognition.providers import MockRecognizer
from snapims.recognition.service import run_batch_recognition


def test_streamlit_dashboard_renders_without_runtime_errors(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(tmp_path / "ui-data"))
    app = AppTest.from_file("streamlit_app.py", default_timeout=20).run()
    assert not app.exception
    assert any("SnapIMS dashboard" in title.value for title in app.title)


def test_review_page_renders_persisted_queue_without_routine_diagnostics(
    tmp_path: Path, monkeypatch, data_paths
) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    run_batch_recognition(data_paths.db_file, result.batch_id, MockRecognizer())
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(data_paths.root))

    app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
    workspace = next(radio for radio in app.radio if radio.key == "workspace_page")
    assert "Review" in workspace.options
    assert "Recognition Review" not in workspace.options
    workspace.set_value("Review").run()

    assert not app.exception
    assert any(title.value == "Review" for title in app.title)
    assert not app.json
    routine_text = " ".join(
        str(element.value)
        for collection in (app.markdown, app.caption, app.text)
        for element in collection
    )
    assert str(data_paths.db_file) not in routine_text
    assert any(expander.label == "Details" for expander in app.expander)
    assert db.get_item(data_paths.db_file, db.list_items(data_paths.db_file)[0]["item_id"])


def test_advanced_settings_keeps_workspace_diagnostics_reachable(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(tmp_path / "ui-data"))
    app = AppTest.from_file("streamlit_app.py", default_timeout=20).run()
    workspace = next(radio for radio in app.radio if radio.key == "workspace_page")

    workspace.set_value("Settings & diagnostics").run()

    assert not app.exception
    assert any(title.value == "Settings & diagnostics" for title in app.title)
    labels = {expander.label for expander in app.expander}
    assert "Workspace storage" in labels
    assert "Database inspection and audit" in labels
