from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from snapims import db
from snapims.demo import create_demo_batch
from snapims.processor import process_batch
from snapims.recognition import repository
from snapims.recognition.providers import MockRecognizer
from snapims.recognition.service import accept_result, run_batch_recognition, run_recognition


def _run_review_app(data_paths, monkeypatch) -> AppTest:
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(data_paths.root))
    app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
    workspace = next(radio for radio in app.radio if radio.key == "workspace_page")
    workspace.set_value("Review").run()
    assert not app.exception
    return app


def _item_context_text(app: AppTest) -> str:
    return " ".join(str(element.value) for element in app.markdown)


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


def test_review_accept_advances_to_next_item_by_item_id(
    tmp_path: Path, monkeypatch, data_paths
) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    items = db.list_items(data_paths.db_file, batch_id_value=result.batch_id)
    run_batch_recognition(data_paths.db_file, result.batch_id, MockRecognizer())

    app = _run_review_app(data_paths, monkeypatch)
    assert items[0]["item_id"] in _item_context_text(app)

    app = next(button for button in app.button if button.label == "Accept").click().run()

    assert not app.exception
    accepted = repository.latest_result_for_item(data_paths.db_file, items[0]["item_id"])
    assert accepted is not None
    assert accepted.review_status == repository.REVIEW_ACCEPTED
    assert items[1]["item_id"] in _item_context_text(app)
    assert items[0]["item_id"] not in _item_context_text(app)


def test_review_edit_and_save_updates_item_and_advances(
    tmp_path: Path, monkeypatch, data_paths
) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    items = db.list_items(data_paths.db_file, batch_id_value=result.batch_id)
    run_batch_recognition(data_paths.db_file, result.batch_id, MockRecognizer())
    stored = repository.latest_result_for_item(data_paths.db_file, items[0]["item_id"])
    assert stored is not None

    app = _run_review_app(data_paths, monkeypatch)
    app = next(button for button in app.button if button.label == "Edit").click().run()
    assert not app.exception

    title_input = app.text_input(key=f"review_title_{stored.recognition_result_id}")
    title_input.set_value("Operator-confirmed title").run()
    app = next(
        button for button in app.button if button.label == "Save edits & next"
    ).click().run()

    assert not app.exception
    updated_item = db.get_item(data_paths.db_file, items[0]["item_id"])
    assert updated_item is not None
    assert updated_item["title"] == "Operator-confirmed title"
    assert items[1]["item_id"] in _item_context_text(app)


def test_review_later_keeps_item_reachable_in_to_review(
    tmp_path: Path, monkeypatch, data_paths
) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    items = db.list_items(data_paths.db_file, batch_id_value=result.batch_id)
    run_batch_recognition(data_paths.db_file, result.batch_id, MockRecognizer())

    app = _run_review_app(data_paths, monkeypatch)
    app = next(button for button in app.button if button.label == "Skip").click().run()

    assert not app.exception
    to_review = repository.list_review_queue(
        data_paths.db_file, result.batch_id, repository.QUEUE_TO_REVIEW
    )
    assert {entry.result.item_id for entry in to_review} == {
        items[0]["item_id"],
        items[1]["item_id"],
    }
    assert items[1]["item_id"] in _item_context_text(app)


def test_review_previous_stays_on_a_valid_item_without_exception(
    tmp_path: Path, monkeypatch, data_paths
) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    run_batch_recognition(data_paths.db_file, result.batch_id, MockRecognizer())

    app = _run_review_app(data_paths, monkeypatch)
    app = next(button for button in app.button if button.label == "← Previous").click().run()

    assert not app.exception
    assert any(title.value == "Review" for title in app.title)


def test_review_retry_recovers_failed_item_to_to_review(
    tmp_path: Path, monkeypatch, data_paths
) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    items = db.list_items(data_paths.db_file, batch_id_value=result.batch_id)
    repository.save_failure(
        data_paths.db_file,
        items[0]["item_id"],
        provider="mock",
        model_name="deterministic-mock",
        created_at="2026-07-16T20:00:00",
        error_message="Unreadable cover",
    )

    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(data_paths.root))
    app = AppTest.from_file("streamlit_app.py", default_timeout=30)
    app.session_state["recognition_provider_name"] = "mock"
    app = app.run()
    workspace = next(radio for radio in app.radio if radio.key == "workspace_page")
    workspace.set_value("Review").run()
    queue_filter = next(box for box in app.selectbox if box.key == "review_filter")
    app = queue_filter.set_value(repository.QUEUE_FAILED).run()
    assert items[0]["item_id"] in _item_context_text(app)

    app = next(button for button in app.button if button.label == "Retry").click().run()

    assert not app.exception
    latest = repository.latest_result_for_item(data_paths.db_file, items[0]["item_id"])
    assert latest is not None
    assert latest.result_status == repository.RESULT_SUCCEEDED
    failed_queue = repository.list_review_queue(
        data_paths.db_file, result.batch_id, repository.QUEUE_FAILED
    )
    assert items[0]["item_id"] not in {entry.result.item_id for entry in failed_queue}


def test_review_open_in_review_from_skipped_batch_outcome_selects_correct_item(
    tmp_path: Path, monkeypatch, data_paths
) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    items = db.list_items(data_paths.db_file, batch_id_value=result.batch_id)
    run_batch_recognition(data_paths.db_file, result.batch_id, MockRecognizer())

    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(data_paths.root))
    app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
    workspace = next(radio for radio in app.radio if radio.key == "workspace_page")
    app = workspace.set_value("Recognition").run()
    run_button = next(button for button in app.button if button.key == "batch_recognition_run")
    app = run_button.click().run()

    saved_summary = app.session_state["batch_recognition_summary"]
    outcome = next(
        outcome for outcome in saved_summary["outcomes"] if outcome["item_id"] == items[0]["item_id"]
    )
    assert outcome["status"] == "SKIPPED"
    open_key = f"open_batch_result_{outcome['item_id']}_{outcome['result_id']}"
    app = next(button for button in app.button if button.key == open_key).click().run()

    assert not app.exception
    assert any(title.value == "Review" for title in app.title)
    queue_filter = next(box for box in app.selectbox if box.key == "review_filter")
    assert queue_filter.value == repository.QUEUE_TO_REVIEW
    assert items[0]["item_id"] in _item_context_text(app)


def test_review_resume_falls_back_to_valid_item_when_preferred_left_queue(
    tmp_path: Path, monkeypatch, data_paths
) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    items = db.list_items(data_paths.db_file, batch_id_value=result.batch_id)
    first_result_id, _ = run_recognition(data_paths.db_file, items[0]["item_id"], MockRecognizer())
    run_recognition(data_paths.db_file, items[1]["item_id"], MockRecognizer())
    accept_result(data_paths.db_file, first_result_id)

    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(data_paths.root))
    app = AppTest.from_file("streamlit_app.py", default_timeout=30)
    app.session_state["review_preferred_item_id"] = items[0]["item_id"]
    app = app.run()
    workspace = next(radio for radio in app.radio if radio.key == "workspace_page")
    app = workspace.set_value("Review").run()

    assert not app.exception
    assert items[1]["item_id"] in _item_context_text(app)
    assert items[0]["item_id"] not in _item_context_text(app)


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
