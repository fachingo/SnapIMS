from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from snapims import active_batch, db
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


def _distinct_camera_roll(tmp_path: Path, name: str) -> Path:
    """Create a demo camera roll with a fingerprint distinct from other rolls."""
    source = create_demo_batch(tmp_path / name)
    product = sorted(source.glob("*.jpg"))[2]
    product.write_bytes(product.read_bytes() + f"-{name}".encode())
    return source


def test_streamlit_home_renders_without_runtime_errors(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(tmp_path / "ui-data"))
    app = AppTest.from_file("streamlit_app.py", default_timeout=20).run()
    assert not app.exception
    assert any("SnapIMS home" in title.value for title in app.title)


def test_workspace_navigation_has_exactly_the_five_operator_destinations(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(tmp_path / "ui-data"))
    app = AppTest.from_file("streamlit_app.py", default_timeout=20).run()
    workspace = next(radio for radio in app.radio if radio.key == "workspace_page")
    assert list(workspace.options) == [
        "Home",
        "Import",
        "Review",
        "Publish",
        "Settings & diagnostics",
    ]


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


def test_review_overview_open_from_skipped_recognition_selects_correct_item(
    tmp_path: Path, monkeypatch, data_paths
) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    items = db.list_items(data_paths.db_file, batch_id_value=result.batch_id)
    run_batch_recognition(data_paths.db_file, result.batch_id, MockRecognizer())

    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(data_paths.root))
    app = AppTest.from_file("streamlit_app.py", default_timeout=30)
    app.session_state["recognition_provider_name"] = "mock"
    app = app.run()
    workspace = next(radio for radio in app.radio if radio.key == "workspace_page")
    app = workspace.set_value("Review").run()
    run_button = next(
        button for button in app.button if button.key == "review_overview_run_recognition"
    )
    app = run_button.click().run()

    assert not app.exception
    open_key = f"review_overview_open_{items[0]['item_id']}"
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


def test_dashboard_shows_active_batch_and_continue_action(
    tmp_path: Path, monkeypatch, data_paths
) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(data_paths.root))

    app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()

    assert not app.exception
    assert result.batch_id in _item_context_text(app)
    continue_button = next(button for button in app.button if button.key == "dashboard_continue")
    app = continue_button.click().run()

    assert not app.exception
    workspace = next(radio for radio in app.radio if radio.key == "workspace_page")
    assert workspace.value == "Review"


def test_dashboard_change_batch_is_explicit_and_does_not_auto_switch(
    tmp_path: Path, monkeypatch, data_paths
) -> None:
    batch_a = process_batch(_distinct_camera_roll(tmp_path, "camera-a"), paths=data_paths)
    batch_b = process_batch(_distinct_camera_roll(tmp_path, "camera-b"), paths=data_paths)
    active_batch.set_active_batch(data_paths.db_file, batch_a.batch_id)
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(data_paths.root))

    app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()

    assert batch_a.batch_id in _item_context_text(app)
    assert active_batch.get_active_batch(data_paths.db_file)["batch_id"] == batch_a.batch_id

    change_select = next(box for box in app.selectbox if box.key == "dashboard_change_batch")
    app = change_select.set_value(batch_b.batch_id).run()
    set_active_button = next(
        button for button in app.button if button.key == "dashboard_set_active"
    )
    app = set_active_button.click().run()

    assert not app.exception
    assert active_batch.get_active_batch(data_paths.db_file)["batch_id"] == batch_b.batch_id


def test_review_and_publish_pages_default_to_active_batch_and_exclude_others(
    tmp_path: Path, monkeypatch, data_paths
) -> None:
    batch_a = process_batch(_distinct_camera_roll(tmp_path, "camera-a"), paths=data_paths)
    items_a = db.list_items(data_paths.db_file, batch_id_value=batch_a.batch_id)
    run_batch_recognition(data_paths.db_file, batch_a.batch_id, MockRecognizer())

    batch_b = process_batch(_distinct_camera_roll(tmp_path, "camera-b"), paths=data_paths)
    items_b = db.list_items(data_paths.db_file, batch_id_value=batch_b.batch_id)
    run_batch_recognition(data_paths.db_file, batch_b.batch_id, MockRecognizer())

    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(data_paths.root))
    app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
    workspace = next(radio for radio in app.radio if radio.key == "workspace_page")

    app = workspace.set_value("Review").run()
    assert not app.exception
    review_batch = next(box for box in app.selectbox if box.key == "review_batch")
    assert review_batch.value == batch_b.batch_id
    context_text = _item_context_text(app)
    assert items_b[0]["item_id"] in context_text
    assert items_a[0]["item_id"] not in context_text
    assert items_a[1]["item_id"] not in context_text

    workspace = next(radio for radio in app.radio if radio.key == "workspace_page")
    app = workspace.set_value("Publish").run()
    assert not app.exception
    dry_run_batch = next(box for box in app.selectbox if box.key == "shopify_dry_run_batch")
    assert dry_run_batch.value == batch_b.batch_id
    dry_run_item = next(box for box in app.selectbox if box.key == "shopify_dry_run_item")
    assert set(dry_run_item.options) == {item["item_id"] for item in items_b}
    assert not set(dry_run_item.options) & {item["item_id"] for item in items_a}


def test_advanced_settings_keeps_workspace_diagnostics_reachable(
    tmp_path: Path, monkeypatch, data_paths
) -> None:
    process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(data_paths.root))
    app = AppTest.from_file("streamlit_app.py", default_timeout=20).run()
    workspace = next(radio for radio in app.radio if radio.key == "workspace_page")

    app = workspace.set_value("Settings & diagnostics").run()

    assert not app.exception
    assert any(title.value == "Settings & diagnostics" for title in app.title)
    labels = {expander.label for expander in app.expander}
    # Every former diagnostic-only capability (raw command events, the
    # database/table browser, manual validation rerun, and raw logs) must
    # remain reachable from this single consolidated destination.
    assert "Workspace storage" in labels
    assert "Database inspection and audit" in labels
    assert "Command events (raw)" in labels
    assert "Validation (raw)" in labels
    assert "Logs & warnings" in labels


def test_synthetic_operator_completes_import_review_publish_without_diagnostics(
    tmp_path: Path, monkeypatch, data_paths
) -> None:
    """A synthetic operator finishes the whole workflow using only the
    three primary destinations; Settings & diagnostics is never opened."""
    source = create_demo_batch(tmp_path / "camera")
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(data_paths.root))

    app = AppTest.from_file("streamlit_app.py", default_timeout=30)
    app.session_state["recognition_provider_name"] = "mock"
    app = app.run()
    workspace = next(radio for radio in app.radio if radio.key == "workspace_page")

    # Import.
    app = workspace.set_value("Import").run()
    photo_directory = next(
        text_input for text_input in app.text_input if text_input.label == "Photo directory"
    )
    app = photo_directory.set_value(str(source)).run()
    import_button = next(
        button for button in app.button if button.label == "Preserve and import batch"
    )
    app = import_button.click().run()
    assert not app.exception
    batch_id = active_batch.get_active_batch(data_paths.db_file)["batch_id"]

    # Review: run recognition from the overview, then accept every item.
    workspace = next(radio for radio in app.radio if radio.key == "workspace_page")
    app = workspace.set_value("Review").run()
    run_button = next(
        button for button in app.button if button.key == "review_overview_run_recognition"
    )
    app = run_button.click().run()
    assert not app.exception

    items = db.list_items(data_paths.db_file, batch_id_value=batch_id)
    for _ in items:
        accept_button = next(button for button in app.button if button.label == "Accept")
        app = accept_button.click().run()
        assert not app.exception

    # Publish: a simulated dry-run works with no credentials.
    workspace = next(radio for radio in app.radio if radio.key == "workspace_page")
    app = workspace.set_value("Publish").run()
    dry_run_button = next(
        button for button in app.button if button.label == "Run Shopify dry-run"
    )
    app = dry_run_button.click().run()

    assert not app.exception
    assert any(title.value == "Publish" for title in app.title)


def test_no_routine_page_leaks_database_path_or_numeric_result_ids(
    tmp_path: Path, monkeypatch, data_paths
) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    run_batch_recognition(data_paths.db_file, result.batch_id, MockRecognizer())
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(data_paths.root))

    app = AppTest.from_file("streamlit_app.py", default_timeout=30).run()
    workspace = next(radio for radio in app.radio if radio.key == "workspace_page")

    for page in ("Home", "Import", "Review", "Publish"):
        app = workspace.set_value(page).run()
        assert not app.exception
        routine_text = " ".join(
            str(element.value)
            for collection in (app.markdown, app.caption, app.text)
            for element in collection
        )
        assert str(data_paths.db_file) not in routine_text
        assert "recognition_results" not in routine_text
        if page != "Review":
            # Review keeps the numeric recognition-result ID inside its
            # explicit, collapsed "Details" expander (unchanged from the
            # prior Review-repair phase); every other destination must
            # never surface it at all.
            assert "Result ID:" not in routine_text
        workspace = next(radio for radio in app.radio if radio.key == "workspace_page")
