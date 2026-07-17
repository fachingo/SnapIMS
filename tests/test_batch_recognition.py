from __future__ import annotations

from typing import Any

import pytest

from snapims import db
from snapims.demo import create_demo_batch
from snapims.processor import process_batch
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
    assert len(list_results(paths.db_file, items[1]["item_id"])) == 0


def test_batch_recognition_does_not_auto_accept_suggestions(imported_batch) -> None:
    batch_id, paths = imported_batch
    items = db.list_items(paths.db_file, batch_id_value=batch_id)

    run_batch_recognition(paths.db_file, batch_id, MockRecognizer())

    for item in items:
        stored = db.get_item(paths.db_file, item["item_id"])
        assert stored["title"] == ""
        assert stored["recognition_provider"] == ""
