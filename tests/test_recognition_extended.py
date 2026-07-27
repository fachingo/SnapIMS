from __future__ import annotations

from pathlib import Path

import pytest

from snapims import db
from snapims.demo import create_demo_batch
from snapims.processor import process_batch
from snapims.observability import query_events
from snapims.recognition.base import BaseRecognizer, RecognitionResult
from snapims.recognition.service import (
    accept_item,
    retry_failed_item,
    run_recognition,
    start_batch_recognition,
)
from tests.helpers import recognized_batch, wait_for_job


class FixedRecognizer(BaseRecognizer):
    name = "fixed"

    def __init__(self, *, title: str = "AI Title", fail: bool = False) -> None:
        self.title = title
        self.fail = fail

    def recognize(self, item, images):
        if self.fail:
            raise RuntimeError("fixed failure")
        return RecognitionResult(
            suggested_title=self.title,
            edition="AI Edition",
            distributor="AI Studio",
            year=1994,
            barcode_candidates=("012345678905",),
            suggested_price_cents=1499,
            suggested_discount_percent=5,
            confidence=0.88,
            provider_name=self.name,
            raw_response_reference="fixed:1",
            requires_review=True,
        )


def test_suggestion_persists_without_mutating_item(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera", item_count=1), paths=data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    result_id, suggestion = run_recognition(data_paths.db_file, item["item_id"], FixedRecognizer())
    assert result_id > 0
    assert suggestion.suggested_title == "AI Title"
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert saved["title"] == ""
    assert saved["review_status"] == "UNFINISHED"
    assert db.latest_recognition(data_paths.db_file, item["item_id"])["suggested_title"] == "AI Title"


def test_acceptance_precedence_explicit_existing_ai_default(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera", item_count=1), paths=data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    run_recognition(data_paths.db_file, item["item_id"], FixedRecognizer())
    db.update_item(
        data_paths.db_file,
        item["item_id"],
        {"title": "Manual", "edition": "Manual Edition", "price_cents": 1200},
    )
    assert accept_item(data_paths.db_file, item["item_id"], price_cents=1800, discount_percent=10) == []
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert saved["title"] == "Manual"
    assert saved["edition"] == "Manual Edition"
    assert saved["distributor"] == "AI Studio"
    assert saved["release_year"] == 1994
    assert saved["price_cents"] == 1800
    assert saved["discount_percent"] == 10


def test_ordinary_reprocessing_does_not_overwrite_manual_record(tmp_path: Path, data_paths) -> None:
    result = recognized_batch(tmp_path, data_paths, item_count=1)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    db.update_item(data_paths.db_file, item["item_id"], {"title": "Manual title", "price_cents": 2200})
    run_recognition(data_paths.db_file, item["item_id"], FixedRecognizer(title="Different AI title"))
    assert accept_item(data_paths.db_file, item["item_id"], price_cents=None, discount_percent=0) == []
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert saved["title"] == "Manual title"
    assert saved["price_cents"] == 2200


def test_background_job_persists_progress_and_completes(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera", item_count=5), paths=data_paths)
    assert start_batch_recognition(data_paths.db_file, result.batch_id, "mock", delay=0.01)
    job = wait_for_job(data_paths.db_file, result.batch_id)
    assert job["status"] == "COMPLETE"
    assert job["completed"] == 5
    assert job["recognized"] == 5
    assert job["failed"] == 0
    events = query_events(
        data_paths.db_file,
        source="recognition",
        batch_id=result.batch_id,
        last=100,
    )
    event_types = [event["event_type"] for event in events]
    assert "recognition.queued" in event_types
    assert "recognition.batch_started" in event_types
    assert event_types.count("recognition.started") == 5
    assert event_types.count("recognition.completed") == 5
    assert "recognition.batch_completed" in event_types
    operation_ids = {
        event["operation_id"]
        for event in events
        if event["event_type"].startswith("recognition.")
    }
    assert operation_ids == {f"recognition:{result.batch_id}"}


def test_duplicate_start_is_rejected_while_worker_active(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera", item_count=20), paths=data_paths)
    assert start_batch_recognition(data_paths.db_file, result.batch_id, "mock", delay=0.05)
    assert not start_batch_recognition(data_paths.db_file, result.batch_id, "mock", delay=0.05)
    wait_for_job(data_paths.db_file, result.batch_id)


def test_resume_skips_existing_results_without_duplicates(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera", item_count=3), paths=data_paths)
    items = db.list_items(data_paths.db_file, batch_id=result.batch_id)
    run_recognition(data_paths.db_file, items[0]["item_id"], FixedRecognizer())
    db.upsert_recognition_job(
        data_paths.db_file,
        result.batch_id,
        provider="mock",
        status="PAUSED",
        total=3,
        completed=1,
        recognized=1,
        failed=0,
    )
    assert start_batch_recognition(data_paths.db_file, result.batch_id, "mock")
    wait_for_job(data_paths.db_file, result.batch_id)
    with db.connect(data_paths.db_file) as connection:
        counts = connection.execute(
            "SELECT item_id,COUNT(*) FROM recognition_results GROUP BY item_id ORDER BY item_id"
        ).fetchall()
    assert [row[1] for row in counts] == [1, 1, 1]


def test_failure_state_and_retry_recovery(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera", item_count=1), paths=data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    with pytest.raises(RuntimeError, match="fixed failure"):
        run_recognition(data_paths.db_file, item["item_id"], FixedRecognizer(fail=True))
    db.update_item(
        data_paths.db_file,
        item["item_id"],
        {"recognition_status": "FAILED", "recognition_error": "fixed failure"},
        source="RECOGNITION",
    )
    retry_failed_item(data_paths.db_file, item["item_id"], "mock")
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert saved["recognition_status"] == "COMPLETE"
    assert saved["recognition_error"] == ""
    assert db.latest_recognition(data_paths.db_file, item["item_id"])["provider"] == "mock"


def test_recognition_history_append_only(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera", item_count=1), paths=data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    run_recognition(data_paths.db_file, item["item_id"], FixedRecognizer(title="First"))
    run_recognition(data_paths.db_file, item["item_id"], FixedRecognizer(title="Second"))
    history = db.recognition_history(data_paths.db_file, item["item_id"])
    assert [row["suggested_title"] for row in history] == ["Second", "First"]


def test_acceptance_marks_only_latest_result_accepted(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera", item_count=1), paths=data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    run_recognition(data_paths.db_file, item["item_id"], FixedRecognizer(title="First"))
    run_recognition(data_paths.db_file, item["item_id"], FixedRecognizer(title="Second"))
    assert accept_item(data_paths.db_file, item["item_id"], price_cents=999, discount_percent=0) == []
    history = db.recognition_history(data_paths.db_file, item["item_id"])
    assert history[0]["accepted_at"]
    assert history[1]["accepted_at"] is None


def test_acceptance_uses_barcode_candidate(tmp_path: Path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera", item_count=1), paths=data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    run_recognition(data_paths.db_file, item["item_id"], FixedRecognizer())
    assert accept_item(data_paths.db_file, item["item_id"], price_cents=1000, discount_percent=0) == []
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert saved["barcode"] == "012345678905"


def test_review_complete_job_state_after_final_acceptance(tmp_path: Path, data_paths) -> None:
    result = recognized_batch(tmp_path, data_paths, item_count=1)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    assert accept_item(data_paths.db_file, item["item_id"], price_cents=999, discount_percent=0) == []
    assert db.get_recognition_job(data_paths.db_file, result.batch_id)["status"] == "REVIEW_COMPLETE"
