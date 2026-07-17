from __future__ import annotations

from pathlib import Path

import pytest

from snapims import active_batch, db
from snapims.demo import create_demo_batch
from snapims.processor import process_batch
from snapims.recognition import repository
from snapims.recognition.providers import MockRecognizer
from snapims.recognition.service import accept_result, run_batch_recognition


def _distinct_batch(tmp_path: Path, name: str) -> Path:
    """Create a demo camera roll with content unique to ``name``.

    ``create_demo_batch`` produces byte-identical fixtures by default, so a
    second call would fingerprint as a duplicate of the first. Appending a
    unique suffix to one product photo, mirroring the existing
    output-collision test, gives each call a distinct ``source_fingerprint``.
    """
    source = create_demo_batch(tmp_path / name)
    product = sorted(source.glob("*.jpg"))[2]
    product.write_bytes(product.read_bytes() + f"-{name}".encode())
    return source


def test_import_sets_active_batch_and_survives_restart(tmp_path: Path, data_paths) -> None:
    batch_a = process_batch(_distinct_batch(tmp_path, "batch-a"), paths=data_paths)
    active = active_batch.get_active_batch(data_paths.db_file)
    assert active is not None
    assert active["batch_id"] == batch_a.batch_id

    batch_b = process_batch(_distinct_batch(tmp_path, "batch-b"), paths=data_paths)
    assert batch_b.batch_id != batch_a.batch_id

    # A restart has no in-memory state; re-reading from the database file is
    # an equivalent check that the active batch is durable, not session-only.
    restarted = active_batch.get_active_batch(data_paths.db_file)
    assert restarted is not None
    assert restarted["batch_id"] == batch_b.batch_id


def test_explicit_change_batch_persists_across_restart(tmp_path: Path, data_paths) -> None:
    batch_a = process_batch(_distinct_batch(tmp_path, "batch-a"), paths=data_paths)
    process_batch(_distinct_batch(tmp_path, "batch-b"), paths=data_paths)

    active_batch.set_active_batch(data_paths.db_file, batch_a.batch_id)

    restarted = active_batch.get_active_batch(data_paths.db_file)
    assert restarted is not None
    assert restarted["batch_id"] == batch_a.batch_id


def test_duplicate_import_reopens_existing_batch_as_active(tmp_path: Path, data_paths) -> None:
    source_a = _distinct_batch(tmp_path, "batch-a")
    batch_a = process_batch(source_a, paths=data_paths)
    process_batch(_distinct_batch(tmp_path, "batch-b"), paths=data_paths)

    result = process_batch(source_a, paths=data_paths)

    assert result.duplicate is True
    assert result.batch_id == batch_a.batch_id
    active = active_batch.get_active_batch(data_paths.db_file)
    assert active is not None
    assert active["batch_id"] == batch_a.batch_id


def test_stale_active_batch_setting_is_repaired(tmp_path: Path, data_paths) -> None:
    process_batch(_distinct_batch(tmp_path, "batch-a"), paths=data_paths)
    db.set_setting(data_paths.db_file, active_batch.ACTIVE_BATCH_SETTING, "NONEXISTENT-BATCH")

    repaired = active_batch.get_active_batch(data_paths.db_file)

    assert repaired is None
    assert not db.get_setting(data_paths.db_file, active_batch.ACTIVE_BATCH_SETTING)


def test_set_active_batch_rejects_unknown_batch_id(data_paths) -> None:
    with pytest.raises(KeyError):
        active_batch.set_active_batch(data_paths.db_file, "NOT-A-REAL-BATCH")


def test_no_active_batch_returns_none(data_paths) -> None:
    assert active_batch.get_active_batch(data_paths.db_file) is None


def test_active_batch_review_queue_excludes_other_batches(tmp_path: Path, data_paths) -> None:
    batch_a = process_batch(_distinct_batch(tmp_path, "batch-a"), paths=data_paths)
    items_a = db.list_items(data_paths.db_file, batch_id_value=batch_a.batch_id)
    run_batch_recognition(data_paths.db_file, batch_a.batch_id, MockRecognizer())

    batch_b = process_batch(_distinct_batch(tmp_path, "batch-b"), paths=data_paths)
    items_b = db.list_items(data_paths.db_file, batch_id_value=batch_b.batch_id)
    run_batch_recognition(data_paths.db_file, batch_b.batch_id, MockRecognizer())

    active = active_batch.get_active_batch(data_paths.db_file)
    assert active is not None
    assert active["batch_id"] == batch_b.batch_id

    queue = repository.list_review_queue(
        data_paths.db_file, active["batch_id"], repository.QUEUE_TO_REVIEW
    )
    queue_item_ids = {entry.result.item_id for entry in queue}
    assert queue_item_ids == {item["item_id"] for item in items_b}
    assert queue_item_ids.isdisjoint({item["item_id"] for item in items_a})


def test_compute_next_action_progresses_through_the_workflow(tmp_path: Path, data_paths) -> None:
    result = process_batch(_distinct_batch(tmp_path, "batch-a"), paths=data_paths)
    items = db.list_items(data_paths.db_file, batch_id_value=result.batch_id)

    action = active_batch.compute_next_action(data_paths.db_file, result.batch_id)
    assert action.target_page == "Recognition"

    run_batch_recognition(data_paths.db_file, result.batch_id, MockRecognizer())
    action = active_batch.compute_next_action(data_paths.db_file, result.batch_id)
    assert action.target_page == "Review"

    for item in items:
        latest = repository.latest_result_for_item(data_paths.db_file, item["item_id"])
        assert latest is not None
        accept_result(data_paths.db_file, latest.recognition_result_id)

    action = active_batch.compute_next_action(data_paths.db_file, result.batch_id)
    assert action.target_page == "Validation"


def test_compute_next_action_with_no_items_prompts_import(tmp_path: Path, data_paths) -> None:
    batch_id = "EMPTY-BATCH"
    db.initialize(data_paths.db_file)
    with db.transaction(data_paths.db_file) as connection:
        connection.execute(
            """
            INSERT INTO batches(
                batch_id, source_fingerprint, source_folder, created_at, imported_at,
                started, ended, item_count, product_photo_count, command_count,
                warning_count
            ) VALUES(?, 'fingerprint-empty', '/camera', '2026-07-16T20:00:00',
                '2026-07-16T20:00:00', 1, 1, 0, 0, 0, 0)
            """,
            (batch_id,),
        )

    action = active_batch.compute_next_action(data_paths.db_file, batch_id)
    assert action.target_page == "Import batch"
