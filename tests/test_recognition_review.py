from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from snapims import db
from snapims.demo import create_demo_batch
from snapims.processor import process_batch
from snapims.recognition import reconciliation, repository
from snapims.recognition.base import BaseRecognizer, RecognitionResult
from snapims.recognition.providers import MockRecognizer
from snapims.recognition.review import (
    ACTION_ACCEPT,
    ACTION_ACCEPT_EDITED,
    ACTION_DISCARD,
    ACTION_EDIT,
    ACTION_RETRY,
    ACTION_SKIP,
    current_item_id,
    keyboard_decision,
    next_item_id,
    previous_item_id,
)
from snapims.recognition.service import (
    accept_edited_result,
    accept_result,
    correct_item_location,
    mark_result_for_review,
    reject_result,
    retry_recognition,
    review_flag_reconciliation_report,
    run_batch_recognition,
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
    assert accepted["review"] == 0
    assert untouched["title"] == ""
    assert stored.review_status == repository.REVIEW_ACCEPTED
    assert stored.accepted_at
    assert stored.accepted_fields == ("title",)
    assert stored.accepted_values == {"title": "Demo VHS 001"}


def test_physical_review_flags_survive_recognition_acceptance(review_batch) -> None:
    _, items, paths = review_batch
    manual_review_item = items[0]
    qr_review_item = items[1]
    assert qr_review_item["review"] == 1
    db.update_item(paths.db_file, manual_review_item["item_id"], {"review": 1})
    manual_result_id, _ = run_recognition(
        paths.db_file,
        manual_review_item["item_id"],
        MockRecognizer(),
    )
    qr_result_id, _ = run_recognition(
        paths.db_file,
        qr_review_item["item_id"],
        MockRecognizer(),
    )

    accept_result(paths.db_file, manual_result_id)
    accept_result(paths.db_file, qr_result_id)

    manual_accepted = db.get_item(paths.db_file, manual_review_item["item_id"])
    qr_accepted = db.get_item(paths.db_file, qr_review_item["item_id"])
    qr_stored = repository.get_result(paths.db_file, qr_result_id)
    assert manual_accepted is not None and manual_accepted["review"] == 1
    assert qr_accepted is not None and qr_accepted["review"] == 1
    assert qr_stored is not None
    assert qr_stored.review_status == repository.REVIEW_ACCEPTED
    assert qr_stored.accepted_at is not None


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
    needs_attention = repository.list_review_queue(
        paths.db_file,
        rejected.batch_id,
        repository.QUEUE_NEEDS_ATTENTION,
    )
    assert [entry.result.recognition_result_id for entry in needs_attention] == [rejected_id]

    retry_id, _ = run_recognition(paths.db_file, items[0]["item_id"], MockRecognizer())
    mark_result_for_review(paths.db_file, retry_id)
    db.initialize(paths.db_file)
    manual = repository.get_result(paths.db_file, retry_id)
    assert manual is not None and manual.review_status == repository.REVIEW_REQUIRED
    manual_item = db.get_item(paths.db_file, items[0]["item_id"])
    assert manual_item is not None and manual_item["review"] == 0


def test_batch_created_result_uses_same_acceptance_path(review_batch) -> None:
    batch_id, items, paths = review_batch
    summary = run_batch_recognition(paths.db_file, batch_id, MockRecognizer())
    result_id = summary.outcomes[0].result_id
    assert result_id is not None

    accept_result(paths.db_file, result_id)

    item = db.get_item(paths.db_file, items[0]["item_id"])
    stored = repository.get_result(paths.db_file, result_id)
    assert item is not None and item["review"] == 0
    assert stored is not None and stored.review_status == repository.REVIEW_ACCEPTED
    assert stored.accepted_at is not None


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

    assert len(
        repository.list_review_queue(paths.db_file, batch_id, repository.QUEUE_TO_REVIEW)
    ) == 2
    assert len(
        repository.list_review_queue(
            paths.db_file, batch_id, repository.QUEUE_NEEDS_ATTENTION
        )
    ) == 0
    assert len(
        repository.list_review_queue(paths.db_file, batch_id, repository.QUEUE_FAILED)
    ) == 1
    assert len(
        repository.list_review_queue(paths.db_file, batch_id, repository.QUEUE_DONE)
    ) == 0

    accept_result(paths.db_file, first_id)
    skip_result(paths.db_file, second_id)

    assert len(
        repository.list_review_queue(paths.db_file, batch_id, repository.QUEUE_DONE)
    ) == 1
    assert len(
        repository.list_review_queue(paths.db_file, batch_id, repository.QUEUE_TO_REVIEW)
    ) == 1


def test_review_queue_truth_table_reaches_every_latest_state(review_batch) -> None:
    """Every recognition-review state must map to exactly one of the four queues."""
    batch_id, items, paths = review_batch
    third = _insert_item(batch_id, 3, paths)
    fourth = _insert_item(batch_id, 4, paths)
    fifth = _insert_item(batch_id, 5, paths)
    sixth = _insert_item(batch_id, 6, paths)

    unreviewed_id, _ = run_recognition(paths.db_file, items[0]["item_id"], MockRecognizer())
    skipped_id, _ = run_recognition(paths.db_file, items[1]["item_id"], MockRecognizer())
    skip_result(paths.db_file, skipped_id)
    manual_id, _ = run_recognition(paths.db_file, third["item_id"], MockRecognizer())
    mark_result_for_review(paths.db_file, manual_id)
    rejected_id, _ = run_recognition(paths.db_file, fourth["item_id"], MockRecognizer())
    reject_result(paths.db_file, rejected_id)
    accepted_id, _ = run_recognition(paths.db_file, fifth["item_id"], MockRecognizer())
    accept_result(paths.db_file, accepted_id)
    repository.save_failure(
        paths.db_file,
        sixth["item_id"],
        provider="mock",
        model_name="deterministic-mock",
        created_at="2026-07-16T20:00:00",
        error_message="Unreadable cover",
    )
    assert unreviewed_id and manual_id and rejected_id  # keep linters quiet about reuse

    to_review = repository.list_review_queue(paths.db_file, batch_id, repository.QUEUE_TO_REVIEW)
    needs_attention = repository.list_review_queue(
        paths.db_file, batch_id, repository.QUEUE_NEEDS_ATTENTION
    )
    failed = repository.list_review_queue(paths.db_file, batch_id, repository.QUEUE_FAILED)
    done = repository.list_review_queue(paths.db_file, batch_id, repository.QUEUE_DONE)

    assert {entry.result.item_id for entry in to_review} == {
        items[0]["item_id"],
        items[1]["item_id"],
    }
    assert {entry.result.item_id for entry in needs_attention} == {
        third["item_id"],
        fourth["item_id"],
    }
    assert {entry.result.item_id for entry in failed} == {sixth["item_id"]}
    assert {entry.result.item_id for entry in done} == {fifth["item_id"]}


def test_queue_navigation_advances_and_moves_previous() -> None:
    item_ids = ["BATCH-B2-011", "BATCH-B2-012", "BATCH-B2-013"]
    assert current_item_id(item_ids, None) == "BATCH-B2-011"
    assert next_item_id(item_ids, "BATCH-B2-011") == "BATCH-B2-012"
    assert previous_item_id(item_ids, "BATCH-B2-012") == "BATCH-B2-011"
    assert previous_item_id(item_ids, "BATCH-B2-011") == "BATCH-B2-011"


def test_queue_navigation_falls_back_to_first_item_when_preferred_id_left_queue() -> None:
    item_ids = ["BATCH-B2-011", "BATCH-B2-012"]
    assert current_item_id(item_ids, "BATCH-B2-099") == "BATCH-B2-011"
    assert current_item_id([], "BATCH-B2-011") is None


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


def test_reconciliation_reports_physical_and_recognition_derived_evidence(
    review_batch,
) -> None:
    _, items, paths = review_batch
    result_id, _ = run_recognition(paths.db_file, items[0]["item_id"], MockRecognizer())
    accept_result(paths.db_file, result_id)
    accepted = repository.get_result(paths.db_file, result_id)
    assert accepted is not None and accepted.accepted_at is not None
    with db.transaction(paths.db_file) as connection:
        connection.execute(
            "UPDATE items SET review = 1, updated_at = ? WHERE item_id = ?",
            (accepted.accepted_at, items[0]["item_id"]),
        )

    report = review_flag_reconciliation_report(paths.db_file)
    rows = {row.item_id: row for row in report.rows}

    derived = rows[items[0]["item_id"]]
    physical = rows[items[1]["item_id"]]
    assert derived.classification == reconciliation.LIKELY_RECOGNITION_DERIVED
    assert derived.accepted_result_ids == (result_id,)
    assert derived.acceptance_matches_item_update is True
    assert physical.classification == reconciliation.CONFIRMED_PHYSICAL_REVIEW
    assert physical.command_review_evidence is True
    assert physical.manifest_review_evidence is True
    assert db.get_item(paths.db_file, items[0]["item_id"])["review"] == 1
    assert db.get_item(paths.db_file, items[1]["item_id"])["review"] == 1


def test_reconciliation_leaves_unaudited_manual_or_legacy_flags_ambiguous(
    review_batch,
) -> None:
    _, items, paths = review_batch
    db.update_item(paths.db_file, items[0]["item_id"], {"review": 1})

    report = review_flag_reconciliation_report(paths.db_file)
    row = next(value for value in report.rows if value.item_id == items[0]["item_id"])

    assert row.classification == reconciliation.AMBIGUOUS_REVIEW_FLAG
    assert row.command_review_evidence is False
    assert row.manifest_review_evidence is False
    assert db.get_item(paths.db_file, items[0]["item_id"])["review"] == 1


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


def _insert_items(batch_id: str, count: int, start_sequence: int, paths) -> list[dict]:
    return [
        _insert_item(batch_id, start_sequence + offset, paths) for offset in range(count)
    ]


def test_100_item_queue_completes_without_orphans_or_missing_items(review_batch) -> None:
    """Simulate a 100-item operator session across every queue outcome and
    confirm every item is reachable in exactly one queue with no losses."""
    batch_id, seed_items, paths = review_batch
    items = seed_items + _insert_items(batch_id, 98, 3, paths)
    assert len(items) == 100

    for index, item in enumerate(items):
        outcome = index % 4
        if outcome == 3:
            repository.save_failure(
                paths.db_file,
                item["item_id"],
                provider="mock",
                model_name="deterministic-mock",
                created_at="2026-07-16T20:00:00",
                error_message="Unreadable cover",
            )
            continue
        result_id, _ = run_recognition(paths.db_file, item["item_id"], MockRecognizer())
        if outcome == 0:
            accept_result(paths.db_file, result_id)
        elif outcome == 1:
            skip_result(paths.db_file, result_id)
        else:
            mark_result_for_review(paths.db_file, result_id)

    to_review = repository.list_review_queue(paths.db_file, batch_id, repository.QUEUE_TO_REVIEW)
    needs_attention = repository.list_review_queue(
        paths.db_file, batch_id, repository.QUEUE_NEEDS_ATTENTION
    )
    failed = repository.list_review_queue(paths.db_file, batch_id, repository.QUEUE_FAILED)
    done = repository.list_review_queue(paths.db_file, batch_id, repository.QUEUE_DONE)

    all_queued_ids = (
        [entry.result.item_id for entry in to_review]
        + [entry.result.item_id for entry in needs_attention]
        + [entry.result.item_id for entry in failed]
        + [entry.result.item_id for entry in done]
    )
    assert len(all_queued_ids) == len(items)
    assert len(set(all_queued_ids)) == len(items), "no item may appear in more than one queue"
    assert set(all_queued_ids) == {item["item_id"] for item in items}

    # Walking "next" across the full To review + Needs attention queues must
    # reach every item deterministically without raising or losing position.
    combined_ids = [entry.result.item_id for entry in to_review] + [
        entry.result.item_id for entry in needs_attention
    ]
    cursor = current_item_id(combined_ids, None)
    visited = set()
    for _ in range(len(combined_ids)):
        assert cursor is not None
        visited.add(cursor)
        cursor = next_item_id(combined_ids, cursor)
    assert visited == set(combined_ids)


def test_physical_review_survives_discard_and_retry(review_batch) -> None:
    _, items, paths = review_batch
    item_id = items[1]["item_id"]  # QR-review item; review flag already 1.
    assert db.get_item(paths.db_file, item_id)["review"] == 1

    result_id, _ = run_recognition(paths.db_file, item_id, MockRecognizer())
    mark_result_for_review(paths.db_file, result_id)
    after_discard = db.get_item(paths.db_file, item_id)
    assert after_discard is not None and after_discard["review"] == 1

    retry_recognition(paths.db_file, item_id, MockRecognizer())
    after_retry = db.get_item(paths.db_file, item_id)
    assert after_retry is not None and after_retry["review"] == 1


def test_correct_item_location_records_one_event_and_blocks_invalid_input(
    review_batch,
) -> None:
    _, items, paths = review_batch
    item_id = items[0]["item_id"]
    original_shelf = db.get_item(paths.db_file, item_id)["shelf"]

    with pytest.raises(ValueError):
        correct_item_location(paths.db_file, item_id, "Z9", "Bad shelf format")
    with pytest.raises(ValueError):
        correct_item_location(paths.db_file, item_id, "B7", "")
    with pytest.raises(ValueError):
        correct_item_location(paths.db_file, item_id, original_shelf, "No-op reason")

    unchanged = db.get_item(paths.db_file, item_id)
    assert unchanged["shelf"] == original_shelf
    with db.connect(paths.db_file) as connection:
        corrected_before = connection.execute(
            "SELECT * FROM inventory_events WHERE item_id = ? AND event_type = 'LOCATION_CORRECTED'",
            (item_id,),
        ).fetchall()
    assert len(corrected_before) == 0

    correct_item_location(paths.db_file, item_id, "Q1", "Moved to quarantine shelf")

    corrected = db.get_item(paths.db_file, item_id)
    assert corrected["shelf"] == "Q1"
    with db.connect(paths.db_file) as connection:
        events = connection.execute(
            "SELECT * FROM inventory_events WHERE item_id = ? AND event_type = 'LOCATION_CORRECTED'",
            (item_id,),
        ).fetchall()
    assert len(events) == 1
    assert events[0]["from_location"] == original_shelf
    assert events[0]["to_location"] == "Q1"
    assert events[0]["notes"] == "Moved to quarantine shelf"


def test_keyboard_retry_is_ignored_unless_item_has_failed() -> None:
    not_failed = keyboard_decision(
        {"id": "evt-1", "key": "f", "typing": False},
        last_event_id="",
        edit_mode=False,
        is_failed=False,
    )
    failed = keyboard_decision(
        {"id": "evt-2", "key": "f", "typing": False},
        last_event_id="evt-1",
        edit_mode=False,
        is_failed=True,
    )
    assert not_failed.action is None
    assert failed.action == ACTION_RETRY


def test_keyboard_accept_edit_later_are_ignored_once_item_has_failed() -> None:
    for key, expected_action in (("Enter", ACTION_ACCEPT), ("e", ACTION_EDIT), ("ArrowRight", ACTION_SKIP)):
        not_failed = keyboard_decision(
            {"id": f"evt-{key}-1", "key": key, "typing": False},
            last_event_id="",
            edit_mode=False,
            is_failed=False,
        )
        failed = keyboard_decision(
            {"id": f"evt-{key}-2", "key": key, "typing": False},
            last_event_id=f"evt-{key}-1",
            edit_mode=False,
            is_failed=True,
        )
        assert not_failed.action == expected_action
        assert failed.action is None


def test_discard_action_constant_maps_to_manual_review_status(review_batch) -> None:
    """The single UI-facing Discard suggestion action leaves the item
    reachable in Needs attention (REVIEW_REQUIRED), never rejected/lost."""
    _, items, paths = review_batch
    result_id, _ = run_recognition(paths.db_file, items[0]["item_id"], MockRecognizer())
    assert ACTION_DISCARD == "discard"

    mark_result_for_review(paths.db_file, result_id)

    stored = repository.get_result(paths.db_file, result_id)
    assert stored is not None and stored.review_status == repository.REVIEW_REQUIRED
    needs_attention = repository.list_review_queue(
        paths.db_file, items[0]["batch_id"], repository.QUEUE_NEEDS_ATTENTION
    )
    assert items[0]["item_id"] in {entry.result.item_id for entry in needs_attention}
