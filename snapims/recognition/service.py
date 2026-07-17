from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from snapims import db
from snapims.recognition.base import BaseRecognizer, RecognitionResult


@dataclass(frozen=True, slots=True)
class BatchRecognitionFailure:
    item_id: str
    message: str


@dataclass(slots=True)
class BatchRecognitionProgress:
    batch_id: str
    current_item_id: str = ""
    total: int = 0
    completed: int = 0
    recognized: int = 0
    review_required: int = 0
    skipped: int = 0
    failed: int = 0
    failures: list[BatchRecognitionFailure] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class BatchRecognitionSummary:
    batch_id: str
    total: int
    completed: int
    recognized: int
    review_required: int
    skipped: int
    failed: int
    failures: tuple[BatchRecognitionFailure, ...]


def _item_has_recognition_results(db_file: Path, item_id_value: str) -> bool:
    with db.connect(db_file) as connection:
        row = connection.execute(
            "SELECT 1 FROM recognition_results WHERE item_id = ? LIMIT 1",
            (item_id_value,),
        ).fetchone()
    return row is not None


def _skip_reason(
    item: dict,
    *,
    has_existing_result: bool,
    skip_existing: bool,
    only_missing_title: bool,
    force_reprocess: bool,
) -> str | None:
    if only_missing_title and (item.get("title") or "").strip():
        return "Item already has a title"
    if not force_reprocess and skip_existing and has_existing_result:
        return "Item already has a recognition result"
    return None


def run_recognition(
    db_file: Path, item_id_value: str, recognizer: BaseRecognizer
) -> tuple[int, RecognitionResult]:
    item = db.get_item(db_file, item_id_value)
    if item is None:
        raise KeyError(f"Unknown Item ID: {item_id_value}")
    photos = db.get_item_photos(db_file, item_id_value)
    image_paths = [Path(photo["processed_path"]) for photo in photos]
    result = recognizer.recognize(item, image_paths)
    with db.transaction(db_file) as connection:
        cursor = connection.execute(
            """
            INSERT INTO recognition_results(
                item_id, provider, created_at, suggested_title, edition, distributor,
                release_year, barcode_candidates_json, confidence,
                uncertainty_reasons_json, raw_response_reference, requires_review
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id_value, result.provider_name, datetime.now().isoformat(timespec="seconds"),
                result.suggested_title, result.edition, result.distributor, result.year,
                json.dumps(result.barcode_candidates), result.confidence,
                json.dumps(result.uncertainty_reasons), result.raw_response_reference,
                int(result.requires_review),
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return a recognition result ID")
        return cursor.lastrowid, result


def list_results(db_file: Path, item_id_value: str) -> list[dict]:
    with db.connect(db_file) as connection:
        rows = connection.execute(
            "SELECT * FROM recognition_results WHERE item_id=? ORDER BY created_at DESC",
            (item_id_value,),
        ).fetchall()
    return [dict(row) for row in rows]


def accept_result(db_file: Path, result_id: int) -> None:
    with db.transaction(db_file) as connection:
        row = connection.execute(
            "SELECT * FROM recognition_results WHERE recognition_result_id=?", (result_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown recognition result: {result_id}")
        connection.execute(
            """
            UPDATE items SET title=CASE WHEN ?='' THEN title ELSE ? END,
                edition=CASE WHEN ?='' THEN edition ELSE ? END,
                distributor=CASE WHEN ?='' THEN distributor ELSE ? END,
                recognition_provider=?, recognition_confidence=?, review=1, updated_at=?
            WHERE item_id=?
            """,
            (
                row["suggested_title"], row["suggested_title"],
                row["edition"], row["edition"], row["distributor"], row["distributor"],
                row["provider"], row["confidence"], datetime.now().isoformat(timespec="seconds"),
                row["item_id"],
            ),
        )
        connection.execute(
            "UPDATE recognition_results SET accepted_at=? WHERE recognition_result_id=?",
            (datetime.now().isoformat(timespec="seconds"), result_id),
        )


def run_batch_recognition(
    db_file: Path,
    batch_id_value: str,
    recognizer: BaseRecognizer,
    *,
    skip_existing: bool = True,
    only_missing_title: bool = False,
    force_reprocess: bool = False,
    progress_callback: Callable[[BatchRecognitionProgress], None] | None = None,
) -> BatchRecognitionSummary:
    if db.get_batch(db_file, batch_id_value) is None:
        raise KeyError(f"Unknown batch: {batch_id_value}")

    items = db.list_items(db_file, batch_id_value=batch_id_value)
    progress = BatchRecognitionProgress(batch_id=batch_id_value, total=len(items))

    def publish(current_item_id: str = "") -> None:
        progress.current_item_id = current_item_id
        if progress_callback is not None:
            progress_callback(progress)

    publish()
    for item in items:
        item_id_value = item["item_id"]
        publish(item_id_value)
        skip_message = _skip_reason(
            item,
            has_existing_result=_item_has_recognition_results(db_file, item_id_value),
            skip_existing=skip_existing,
            only_missing_title=only_missing_title,
            force_reprocess=force_reprocess,
        )
        if skip_message is not None:
            progress.skipped += 1
            progress.completed += 1
            publish(item_id_value)
            continue
        try:
            _, result = run_recognition(db_file, item_id_value, recognizer)
        except Exception as exc:
            progress.failed += 1
            progress.failures.append(BatchRecognitionFailure(item_id=item_id_value, message=str(exc)))
        else:
            progress.recognized += 1
            if result.requires_review:
                progress.review_required += 1
        progress.completed += 1
        publish(item_id_value)

    return BatchRecognitionSummary(
        batch_id=batch_id_value,
        total=progress.total,
        completed=progress.completed,
        recognized=progress.recognized,
        review_required=progress.review_required,
        skipped=progress.skipped,
        failed=progress.failed,
        failures=tuple(progress.failures),
    )
