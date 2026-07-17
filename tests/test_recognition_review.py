from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from snapims import db
from snapims.demo import create_demo_batch
from snapims.processor import process_batch
from snapims.recognition import repository
from snapims.recognition.base import BaseRecognizer, RecognitionResult
from snapims.recognition.providers import MockRecognizer
from snapims.recognition.review import (
    ACTION_ACCEPT,
    ACTION_ACCEPT_EDITED,
    current_result_id,
    keyboard_decision,
    next_result_id,
    previous_result_id,
)
from snapims.recognition.service import (
    accept_edited_result,
    accept_result,
    mark_result_for_review,
    reject_result,
    run_recognition,
    skip_result,
)


class _BlankRecognizer(BaseRecognizer):
    name = "blank"

    def recognize(self, item: dict[str, Any], images: list) -> RecognitionResult:
        return RecognitionResult(
            suggested_title="",
            edition="",
            distributor="",
            year=None,
            barcode_candidates=(),
            confidence=0.2,
            provider_name=self.name,
            requires_review=True,
        )


@pytest.fixture
def review_batch(tmp_path, data_paths):
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    items = db.list_items(data_paths.db_file, batch_id_value=result.batch_id)
    return result.batch_id, items, data_paths


def _insert_item(batch_id: str, sequence: int, paths) -> dict:
    item_id = f"{batch_id}-B2-{sequence:03d}"
    with db.transaction(paths.db_file) as connection:
        timestamp = connection.execute(
            "SELECT imported_at FROM batches WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO items(
                item_id, sku, batch_id, sequence, shelf, created_at, updated_at
            ) VALUES(?, ?, ?, ?, 'B2', ?, ?)
            """,
            (item_id, item_id, batch_id, sequence, timestamp, timestamp),
        )
        connection.execute("INSERT INTO shopify_sync(item_id) VALUES(?)", (item_id,))
    item = db.get_item(paths.db_file, item_id)
    assert item is not None
    return item


def test_accept_all_updates_correct_item_and_audits_fields(review_batch) -> None:
    _, items, paths = review_batch
    result_id, _ = run_recognition(paths.db_file, items[0]["item_id"], MockRecognizer())

    accept_result(paths.db_file, result_id)

    accepted = db.get_item(paths.db_file, items[0]["item_id"])
    untouched = db.get_item(paths.db_file, items[1]["item_id"])
    stored = repository.get_result(paths.db_file, result_id)
    assert accepted is not None
    assert untouched is not None
    assert stored is not None
    assert accepted["title"] == "Demo VHS 001"
    assert untouched["title"] == ""
    assert stored.review_status == repository.REVIEW_ACCEPTED
    assert stored.accepted_at
    assert stored.accepted_fields == ("title", "edition", "distributor")


def test_blank_suggestions_do_not_erase_existing_values(review_batch) -> None:
    _, items, paths = review_batch
    item_id = items[0]["item_id"]
    db.update_item(
        paths.db_file,
        item_id,
        {
            "title": "Existing title",
            "edition": "Existing edition",
            "distributor": "Existing distributor",
            "barcode": "123456789012",
        },
    )
    result_id, _ = run_recognition(paths.db_file, item_id, _BlankRecognizer())

    accept_result(paths.db_file, result_id)

    item = db.get_item(paths.db_file, item_id)
    assert item is not None
    assert item["title"] == "Existing title"
    assert item["edition"] == "Existing edition"
    assert item["distributor"] == "Existing distributor"
    assert item["barcode"] == "123456789012"


def test_edited_acceptance_saves_operator_values(review_batch) -> None:
    _, items, paths = review_batch
    result_id, _ = run_recognition(paths.db_file, items[0]["item_id"], MockRecognizer())

    accept_edited_result(
        paths.db_file,
        result_id,
        {
            "title": "Operator title",
            "edition": "Collector case",
            "distributor": "Operator studio",
            "release_year": 1999,
            "barcode": "999999999999",
        },
    )

    item = db.get_item(paths.db_file, items[0]["item_id"])
    stored = repository.get_result(paths.db_file, result_id)
    assert item is not None
    assert stored is not None
    assert item["title"] == "Operator title"
    assert item["release_year"] == 1999
    assert item["barcode"] == "999999999999"
    assert stored.accepted_values["title"] == "Operator title"
    assert stored.accepted_values["release_year"] == 1999


def test_rejected_skipped_and_manual_review_states_persist(review_batch) -> None:
    _, items, paths = review_batch
    rejected_id, _ = run_recognition(paths.db_file, items[0]["item_id"], MockRecognizer())
    skipped_id, _ = run_recognition(paths.db_file, items[1]["item_id"], MockRecognizer())

    reject_result(paths.db_file, rejected_id)
    skip_result(paths.db_file, skipped_id)
    rejected = repository.get_result(paths.db_file, rejected_id)
    skipped = repository.get_result(paths.db_file, skipped_id)
    assert rejected is not None and rejected.review_status == repository.REVIEW_REJECTED
    assert skipped is not None and skipped.review_status == repository.REVIEW_SKIPPED

    retry_id, _ = run_recognition(paths.db_file, items[0]["item_id"], MockRecognizer())
    mark_result_for_review(paths.db_file, retry_id)
    db.initialize(paths.db_file)
    manual = repository.get_result(paths.db_file, retry_id)
    assert manual is not None and manual.review_status == repository.REVIEW_REQUIRED


def test_review_queue_filters_return_latest_durable_states(review_batch) -> None:
    batch_id, items, paths = review_batch
    third = _insert_item(batch_id, 3, paths)
    first_id, _ = run_recognition(paths.db_file, items[0]["item_id"], MockRecognizer())
    second_id, _ = run_recognition(paths.db_file, items[1]["item_id"], MockRecognizer())
    repository.save_failure(
        paths.db_file,
        third["item_id"],
        provider="mock",
        model_name="deterministic-mock",
        created_at="2026-07-16T20:00:00",
        error_message="Unreadable cover",
    )

    assert len(repository.list_review_queue(paths.db_file, batch_id)) == 2
    assert len(
        repository.list_review_queue(
            paths.db_file, batch_id, repository.QUEUE_REVIEW_REQUIRED
        )
    ) == 2
    assert len(
        repository.list_review_queue(
            paths.db_file, batch_id, repository.QUEUE_HIGH_CONFIDENCE
        )
    ) == 2
    assert len(
        repository.list_review_queue(paths.db_file, batch_id, repository.QUEUE_FAILED)
    ) == 1

    accept_result(paths.db_file, first_id)
    skip_result(paths.db_file, second_id)

    assert len(repository.list_review_queue(paths.db_file, batch_id)) == 0
    assert len(
        repository.list_review_queue(paths.db_file, batch_id, repository.QUEUE_ACCEPTED)
    ) == 1
    assert len(
        repository.list_review_queue(paths.db_file, batch_id, repository.QUEUE_SKIPPED)
    ) == 1


def test_queue_navigation_advances_and_moves_previous() -> None:
    result_ids = [11, 12, 13]
    assert current_result_id(result_ids, None) == 11
    assert next_result_id(result_ids, 11) == 12
    assert previous_result_id(result_ids, 12) == 11
    assert previous_result_id(result_ids, 11) == 11


def test_keyboard_handler_does_not_double_submit() -> None:
    event = {"id": "evt-1", "key": "Enter", "typing": False}
    first = keyboard_decision(event, last_event_id="", edit_mode=False)
    second = keyboard_decision(event, last_event_id=first.event_id, edit_mode=False)
    assert first.action == ACTION_ACCEPT
    assert second.action is None


def test_keyboard_shortcuts_ignore_typing_except_ctrl_enter() -> None:
    typed_enter = keyboard_decision(
        {"id": "evt-1", "key": "Enter", "typing": True},
        last_event_id="",
        edit_mode=True,
    )
    typed_letter = keyboard_decision(
        {"id": "evt-2", "key": "r", "typing": True},
        last_event_id=typed_enter.event_id,
        edit_mode=True,
    )
    ctrl_enter = keyboard_decision(
        {"id": "evt-3", "key": "Enter", "typing": True, "ctrl": True},
        last_event_id=typed_letter.event_id,
        edit_mode=True,
    )
    assert typed_enter.action is None
    assert typed_letter.action is None
    assert ctrl_enter.action == ACTION_ACCEPT_EDITED


def test_review_schema_migrates_existing_recognition_rows(tmp_path) -> None:
    db_file = tmp_path / "legacy.sqlite3"
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
                item_id, sku, batch_id, sequence, shelf, created_at, updated_at
            ) VALUES(
                'ITEM-1', 'ITEM-1', 'BATCH-1', 1, 'A1',
                '2026-07-16T20:00:00', '2026-07-16T20:00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO recognition_results(
                item_id, provider, created_at, suggested_title, confidence,
                accepted_at
            ) VALUES(
                'ITEM-1', 'openai', '2026-07-16T20:01:00', 'Legacy title',
                0.9, '2026-07-16T20:02:00'
            )
            """
        )

    db.initialize(db_file)

    stored = repository.get_result(db_file, 1)
    assert stored is not None
    assert stored.batch_id == "BATCH-1"
    assert stored.model_name == ""
    assert stored.review_status == repository.REVIEW_ACCEPTED
    assert stored.reviewed_at == "2026-07-16T20:02:00"
    with db.connect(db_file) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
        assert "release_year" in {
            row["name"] for row in connection.execute("PRAGMA table_info(items)")
        }
