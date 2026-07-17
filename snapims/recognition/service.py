from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from snapims import db
from snapims.recognition import reconciliation, repository
from snapims.recognition.base import BaseRecognizer, RecognitionResult


@dataclass(frozen=True, slots=True)
class BatchRecognitionFailure:
    item_id: str
    message: str


@dataclass(frozen=True, slots=True)
class BatchRecognitionOutcome:
    item_id: str
    status: str
    result_id: int | None = None
    suggested_title: str = ""
    confidence: float = 0.0
    message: str = ""


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
    outcomes: list[BatchRecognitionOutcome] = field(default_factory=list)


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
    outcomes: tuple[BatchRecognitionOutcome, ...]


def _item_has_recognition_results(db_file: Path, item_id_value: str) -> bool:
    return repository.has_result(db_file, item_id_value)


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
    stored = repository.save_result(
        db_file,
        item_id_value,
        result,
        model_name=recognizer.persistence_model_name(),
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    return stored.recognition_result_id, result


def list_results(db_file: Path, item_id_value: str) -> list[dict]:
    return [result.as_dict() for result in repository.list_results_for_item(db_file, item_id_value)]


def review_flag_reconciliation_report(
    db_file: Path,
) -> reconciliation.ReviewFlagReconciliationReport:
    return reconciliation.build_review_flag_reconciliation_report(db_file)


def accept_result(db_file: Path, result_id: int) -> None:
    repository.accept_result(
        db_file,
        result_id,
        accepted_at=datetime.now().isoformat(timespec="seconds"),
    )


def accept_edited_result(
    db_file: Path,
    result_id: int,
    edited_values: dict,
) -> None:
    repository.accept_result(
        db_file,
        result_id,
        edited_values=edited_values,
        accepted_at=datetime.now().isoformat(timespec="seconds"),
    )


def reject_result(db_file: Path, result_id: int) -> None:
    repository.set_review_status(
        db_file,
        result_id,
        repository.REVIEW_REJECTED,
        reviewed_at=datetime.now().isoformat(timespec="seconds"),
    )


def skip_result(db_file: Path, result_id: int) -> None:
    repository.set_review_status(
        db_file,
        result_id,
        repository.REVIEW_SKIPPED,
        reviewed_at=datetime.now().isoformat(timespec="seconds"),
    )


def mark_result_for_review(db_file: Path, result_id: int) -> None:
    repository.set_review_status(
        db_file,
        result_id,
        repository.REVIEW_REQUIRED,
        reviewed_at=datetime.now().isoformat(timespec="seconds"),
    )


def retry_recognition(
    db_file: Path,
    item_id_value: str,
    recognizer: BaseRecognizer,
) -> tuple[int, RecognitionResult]:
    try:
        return run_recognition(db_file, item_id_value, recognizer)
    except Exception as exc:
        repository.save_failure(
            db_file,
            item_id_value,
            provider=recognizer.name,
            model_name=recognizer.persistence_model_name(),
            created_at=datetime.now().isoformat(timespec="seconds"),
            error_message=str(exc),
        )
        raise


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
            existing = repository.latest_result_for_item(db_file, item_id_value)
            progress.skipped += 1
            progress.outcomes.append(
                BatchRecognitionOutcome(
                    item_id=item_id_value,
                    status="SKIPPED",
                    result_id=existing.recognition_result_id if existing else None,
                    suggested_title=existing.suggested_title if existing else "",
                    confidence=existing.confidence if existing else 0.0,
                    message=skip_message,
                )
            )
            progress.completed += 1
            publish(item_id_value)
            continue
        try:
            result_id, result = run_recognition(db_file, item_id_value, recognizer)
        except Exception as exc:
            failure_message = str(exc)
            try:
                failed_record = repository.save_failure(
                    db_file,
                    item_id_value,
                    provider=recognizer.name,
                    model_name=recognizer.persistence_model_name(),
                    created_at=datetime.now().isoformat(timespec="seconds"),
                    error_message=failure_message,
                )
                failed_result_id: int | None = failed_record.recognition_result_id
            except Exception as persistence_exc:
                failed_result_id = None
                failure_message = (
                    f"{failure_message} (failure record could not be saved: {persistence_exc})"
                )
            progress.failed += 1
            progress.failures.append(
                BatchRecognitionFailure(item_id=item_id_value, message=failure_message)
            )
            progress.outcomes.append(
                BatchRecognitionOutcome(
                    item_id=item_id_value,
                    status="FAILED",
                    result_id=failed_result_id,
                    message=failure_message,
                )
            )
        else:
            progress.recognized += 1
            progress.outcomes.append(
                BatchRecognitionOutcome(
                    item_id=item_id_value,
                    status="REVIEW_REQUIRED" if result.requires_review else "UNREVIEWED",
                    result_id=result_id,
                    suggested_title=result.suggested_title,
                    confidence=result.confidence,
                )
            )
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
        outcomes=tuple(progress.outcomes),
    )
