from __future__ import annotations

from typing import Any

import pytest

from snapims import db
from snapims.demo import create_demo_batch
from snapims.processor import process_batch
from snapims.recognition import repository
from snapims.recognition.base import BaseRecognizer, RecognitionResult
from snapims.recognition.providers import MockRecognizer
from snapims.recognition.service import list_results, run_batch_recognition, run_recognition


class _FailOnItemRecognizer(BaseRecognizer):
    name = "fail-on-item"

    def __init__(self, fail_item_ids: set[str]) -> None:
        self._fail_item_ids = fail_item_ids
        self._mock = MockRecognizer()

    def recognize(self, item: dict[str, Any], images: list) -> RecognitionResult:
        if item["item_id"] in self._fail_item_ids:
            raise RuntimeError(f"Recognition failed for {item['item_id']}")
        return self._mock.recognize(item, images)


class _CountingRecognizer(BaseRecognizer):
    name = "counting"
    attempts = 0

    def recognize(self, item: dict[str, Any], images: list) -> RecognitionResult:
        _CountingRecognizer.attempts += 1
        if _CountingRecognizer.attempts == 2:
            raise RuntimeError("Simulated failure on second item")
        return MockRecognizer().recognize(item, images)


@pytest.fixture
def imported_batch(tmp_path, data_paths):
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    return result.batch_id, data_paths


def _add_third_item(batch_id: str, paths) -> str:
    item_id = f"{batch_id}-B2-003"
    with db.transaction(paths.db_file) as connection:
        imported_at = connection.execute(
            "SELECT imported_at FROM batches WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO items(
                item_id, sku, batch_id, sequence, shelf, created_at, updated_at
            ) VALUES(?, ?, ?, 3, 'B2', ?, ?)
            """,
            (item_id, item_id, batch_id, imported_at, imported_at),
        )
        connection.execute("INSERT INTO shopify_sync(item_id) VALUES(?)", (item_id,))
        connection.execute(
            "UPDATE batches SET item_count = item_count + 1 WHERE batch_id = ?",
            (batch_id,),
        )
    return item_id


def test_batch_recognition_processes_entire_batch(imported_batch) -> None:
    batch_id, paths = imported_batch
    items = db.list_items(paths.db_file, batch_id_value=batch_id)

    summary = run_batch_recognition(paths.db_file, batch_id, MockRecognizer())

    assert summary.total == len(items) == 2
    assert summary.completed == 2
    assert summary.recognized == 2
    assert summary.review_required == 2
    assert summary.skipped == 0
    assert summary.failed == 0
    for item in items:
        assert len(list_results(paths.db_file, item["item_id"])) == 1
        unchanged = db.get_item(paths.db_file, item["item_id"])
        assert unchanged["title"] == ""


def test_three_batch_items_persist_through_shared_repository(imported_batch) -> None:
    batch_id, paths = imported_batch
    _add_third_item(batch_id, paths)
    items = db.list_items(paths.db_file, batch_id_value=batch_id)

    summary = run_batch_recognition(paths.db_file, batch_id, MockRecognizer())

    assert summary.recognized == 3
    assert summary.failed == 0
    stored = [
        repository.list_results_for_item(paths.db_file, item["item_id"])[0]
        for item in items
    ]
    assert {result.item_id for result in stored} == {item["item_id"] for item in items}
    assert {result.batch_id for result in stored} == {batch_id}
    assert {result.provider for result in stored} == {"mock"}
    assert {result.model_name for result in stored} == {"deterministic-mock"}
    assert all(result.recognition_result_id > 0 for result in stored)
    assert all(result.created_at for result in stored)
    assert all(result.suggested_title for result in stored)
    assert all(result.confidence == 0.91 for result in stored)
    assert all(result.requires_review for result in stored)
    assert all(result.uncertainty_reasons for result in stored)
    assert all(result.raw_response_reference.startswith("mock:") for result in stored)


def test_batch_recognition_skips_existing_results(imported_batch) -> None:
    batch_id, paths = imported_batch
    items = db.list_items(paths.db_file, batch_id_value=batch_id)
    run_recognition(paths.db_file, items[0]["item_id"], MockRecognizer())

    summary = run_batch_recognition(
        paths.db_file,
        batch_id,
        MockRecognizer(),
        skip_existing=True,
    )

    assert summary.recognized == 1
    assert summary.skipped == 1
    assert len(list_results(paths.db_file, items[0]["item_id"])) == 1
    assert len(list_results(paths.db_file, items[1]["item_id"])) == 1


def test_batch_recognition_only_missing_title_mode(imported_batch) -> None:
    batch_id, paths = imported_batch
    items = db.list_items(paths.db_file, batch_id_value=batch_id)
    db.update_item(paths.db_file, items[0]["item_id"], {"title": "Already titled"})

    summary = run_batch_recognition(
        paths.db_file,
        batch_id,
        MockRecognizer(),
        only_missing_title=True,
        skip_existing=False,
    )

    assert summary.recognized == 1
    assert summary.skipped == 1
    assert len(list_results(paths.db_file, items[0]["item_id"])) == 0
    assert len(list_results(paths.db_file, items[1]["item_id"])) == 1


def test_batch_recognition_force_reprocess(imported_batch) -> None:
    batch_id, paths = imported_batch
    items = db.list_items(paths.db_file, batch_id_value=batch_id)
    run_recognition(paths.db_file, items[0]["item_id"], MockRecognizer())

    summary = run_batch_recognition(
        paths.db_file,
        batch_id,
        MockRecognizer(),
        skip_existing=True,
        force_reprocess=True,
    )

    assert summary.recognized == 2
    assert summary.skipped == 0
    assert len(list_results(paths.db_file, items[0]["item_id"])) == 2


def test_batch_recognition_continues_after_individual_failure(imported_batch) -> None:
    batch_id, paths = imported_batch
    items = db.list_items(paths.db_file, batch_id_value=batch_id)

    summary = run_batch_recognition(
        paths.db_file,
        batch_id,
        _FailOnItemRecognizer({items[0]["item_id"]}),
    )

    assert summary.recognized == 1
    assert summary.failed == 1
    assert summary.failures[0].item_id == items[0]["item_id"]
    assert len(list_results(paths.db_file, items[1]["item_id"])) == 1


def test_batch_recognition_saves_each_item_before_later_failure(imported_batch) -> None:
    batch_id, paths = imported_batch
    items = db.list_items(paths.db_file, batch_id_value=batch_id)
    _CountingRecognizer.attempts = 0

    summary = run_batch_recognition(paths.db_file, batch_id, _CountingRecognizer())

    assert summary.recognized == 1
    assert summary.failed == 1
    assert len(list_results(paths.db_file, items[0]["item_id"])) == 1
    failed_results = repository.list_results_for_item(paths.db_file, items[1]["item_id"])
    assert len(failed_results) == 1
    assert failed_results[0].result_status == repository.RESULT_FAILED


def test_batch_recognition_counts_persistence_failure_as_failed(
    imported_batch, monkeypatch
) -> None:
    batch_id, paths = imported_batch
    items = db.list_items(paths.db_file, batch_id_value=batch_id)
    real_save = repository.save_result

    def fail_first_save(db_file, item_id_value, result, *, model_name, created_at):
        if item_id_value == items[0]["item_id"]:
            raise RuntimeError("Simulated persistence failure")
        return real_save(
            db_file,
            item_id_value,
            result,
            model_name=model_name,
            created_at=created_at,
        )

    monkeypatch.setattr(repository, "save_result", fail_first_save)

    summary = run_batch_recognition(paths.db_file, batch_id, MockRecognizer())

    assert summary.recognized == 1
    assert summary.failed == 1
    assert "persistence failure" in summary.failures[0].message
    failed_results = repository.list_results_for_item(paths.db_file, items[0]["item_id"])
    assert len(failed_results) == 1
    assert failed_results[0].result_status == repository.RESULT_FAILED
    assert len(repository.list_results_for_item(paths.db_file, items[1]["item_id"])) == 1


def test_batch_recognition_does_not_auto_accept_suggestions(imported_batch) -> None:
    batch_id, paths = imported_batch
    items = db.list_items(paths.db_file, batch_id_value=batch_id)

    run_batch_recognition(paths.db_file, batch_id, MockRecognizer())

    for item in items:
        stored = db.get_item(paths.db_file, item["item_id"])
        assert stored["title"] == ""
        assert stored["recognition_provider"] == ""
