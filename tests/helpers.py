from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from snapims import db
from snapims.demo import create_demo_batch
from snapims.processor import process_batch
from snapims.recognition.service import start_batch_recognition


def wait_for_job(db_file: Path, batch_id: str, *, timeout: float = 10) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = db.get_recognition_job(db_file, batch_id)
        if job and job["status"] in {"COMPLETE", "COMPLETE_WITH_FAILURE", "REVIEW_COMPLETE", "PAUSED"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"recognition did not finish for {batch_id}")


def recognized_batch(tmp_path: Path, data_paths, *, item_count: int = 2, provider: str = "mock"):
    source = create_demo_batch(tmp_path / f"camera-{item_count}-{provider}", item_count=item_count)
    result = process_batch(source, paths=data_paths)
    start_batch_recognition(data_paths.db_file, result.batch_id, provider)
    wait_for_job(data_paths.db_file, result.batch_id)
    return result


def ready_item(tmp_path: Path, data_paths):
    result = recognized_batch(tmp_path, data_paths, item_count=1)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    from snapims.recognition.service import accept_item

    errors = accept_item(
        data_paths.db_file,
        item["item_id"],
        price_cents=1299,
        discount_percent=0,
    )
    assert errors == []
    return result, db.get_item(data_paths.db_file, item["item_id"])
