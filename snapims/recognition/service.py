from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from snapims import db
from snapims.recognition.base import BaseRecognizer, RecognitionResult
from snapims.recognition.providers import recognizer_registry
from snapims.config import DataPaths

_ACTIVE: dict[str, threading.Thread] = {}
_LOCK = threading.Lock()


def classify_recognition_error(exc: Exception) -> tuple[str, str]:
    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.casefold()
    normalized = lowered.replace("_", " ").replace("-", " ")
    if "api key" in normalized and ("not configured" in normalized or "missing" in normalized):
        return "API_KEY_MISSING", "OpenAI API key is not configured. Add it in Settings or the environment."
    if "authentication" in lowered or "unauthorized" in lowered or "invalid api key" in lowered:
        return "AUTHENTICATION_FAILED", "The provider rejected the configured API key."
    if "rate limit" in lowered or "429" in lowered:
        return "RATE_LIMIT", "The provider rate limit was reached. Wait and retry failed items."
    if "quota" in lowered or "billing" in lowered or "insufficient_quota" in lowered:
        return "QUOTA", "The provider quota or billing limit was reached."
    if "timeout" in lowered or "timed out" in lowered:
        return "TIMEOUT", "The provider request timed out."
    if "network" in lowered or "connection" in lowered or "name resolution" in lowered:
        return "NETWORK", "SnapIMS could not reach the recognition provider."
    if "model" in lowered and ("not found" in lowered or "unavailable" in lowered):
        return "MODEL_UNAVAILABLE", "The configured model is unavailable."
    if "server" in lowered or "502" in lowered or "503" in lowered:
        return "PROVIDER_SERVER", "The recognition provider returned a server error."
    if isinstance(exc, (KeyError, ValueError, json.JSONDecodeError)):
        return "INVALID_RESPONSE", f"Recognition data was invalid: {message}"
    return "LOCAL_FAILURE", message


def recognition_images(db_file: Path, item_id: str, *, limit: int = 3) -> list[Path]:
    photos = db.get_item_photos(db_file, item_id)
    eligible = [photo for photo in photos if int(photo.get("ai_eligible", 1))]
    # Front first, then spine/support. The back/cassette remain available for a future adaptive retry.
    eligible.sort(key=lambda photo: (int(photo.get("photo_order") or 999), int(photo["photo_id"])))
    paths: list[Path] = []
    seen_hashes: set[str] = set()
    for photo in eligible:
        digest = str(photo.get("sha256") or "")
        if digest and digest in seen_hashes:
            continue
        if digest:
            seen_hashes.add(digest)
        candidate = Path(photo.get("recognition_path") or photo.get("processed_path") or "")
        if candidate.is_file():
            paths.append(candidate)
        if len(paths) >= limit:
            break
    return paths


def run_recognition(db_file: Path, item_id: str, recognizer: BaseRecognizer) -> tuple[int, RecognitionResult]:
    item = db.get_item(db_file, item_id)
    if item is None:
        raise KeyError(f"Unknown Item ID: {item_id}")
    images = recognition_images(db_file, item_id)
    result = recognizer.recognize(item, images)
    with db.transaction(db_file) as connection:
        cursor = connection.execute(
            """INSERT INTO recognition_results(
                   item_id,provider,created_at,suggested_title,edition,distributor,release_year,
                   barcode_candidates_json,suggested_price_cents,suggested_discount_percent,
                   confidence,uncertainty_reasons_json,raw_response_reference,pricing_source,
                   input_tokens,output_tokens,requires_review
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item_id,
                result.provider_name,
                db.now(),
                result.suggested_title,
                result.edition,
                result.distributor,
                result.year,
                json.dumps(result.barcode_candidates),
                result.suggested_price_cents,
                result.suggested_discount_percent,
                result.confidence,
                json.dumps(result.uncertainty_reasons),
                result.raw_response_reference,
                result.pricing_source,
                result.input_tokens,
                result.output_tokens,
                int(result.requires_review),
            ),
        )
        connection.execute(
            "UPDATE items SET recognition_status='COMPLETE',recognition_error='',updated_at=? WHERE item_id=?",
            (db.now(), item_id),
        )
    recognition_result_id = int(cursor.lastrowid)
    # Catalog work is additive. A catalog failure must never erase or roll back the
    # committed visual recognition result.
    try:
        from snapims.catalog.service import queue_recognition_lookup

        paths = DataPaths.from_root(db_file.parent.parent).ensure()
        queue_recognition_lookup(
            paths,
            recognition_result_id,
            start_worker=not bool(os.getenv("PYTEST_CURRENT_TEST")),
        )
    except Exception as exc:
        try:
            db.mark_item_catalog_unavailable(db_file, item_id, recognition_result_id, str(exc))
        except Exception:
            pass
    return recognition_result_id, result


def _job_counts(db_file: Path, batch_id: str) -> tuple[list[dict[str, Any]], int, int]:
    items = db.list_items(db_file, batch_id=batch_id)
    recognized = sum(1 for item in items if item["recognition_status"] == "COMPLETE")
    failed = sum(1 for item in items if item["recognition_status"] == "FAILED")
    return items, recognized, failed


def _recognition_worker(db_file: Path, batch_id: str, provider_name: str, delay: float) -> None:
    provider = recognizer_registry()[provider_name]
    items, recognized, failed = _job_counts(db_file, batch_id)
    existing_job = db.get_recognition_job(db_file, batch_id) or {}
    completed_ids: set[str] = set()
    with db.connect(db_file) as connection:
        rows = connection.execute(
            "SELECT DISTINCT item_id FROM recognition_results "
            "WHERE item_id IN (SELECT item_id FROM items WHERE batch_id=?)",
            (batch_id,),
        ).fetchall()
        completed_ids = {str(row[0]) for row in rows}
    recognized = len(completed_ids)
    db.upsert_recognition_job(
        db_file,
        batch_id,
        provider=provider_name,
        status="IDENTIFYING",
        total=len(items),
        completed=recognized + failed,
        recognized=recognized,
        failed=failed,
        started_at=existing_job.get("started_at") or db.now(),
        finished_at=None,
        error_code="",
        error_message="",
        error_at=None,
        model_name=getattr(provider, "model_name", lambda: "")(),
    )
    try:
        for item in items:
            if item["item_id"] in completed_ids or item["recognition_status"] == "FAILED":
                continue
            db.upsert_recognition_job(
                db_file,
                batch_id,
                status="IDENTIFYING",
                current_item_id=item["item_id"],
            )
            try:
                run_recognition(db_file, item["item_id"], provider)
            except Exception as exc:
                failed += 1
                code, message = classify_recognition_error(exc)
                db.update_item(
                    db_file,
                    item["item_id"],
                    {"recognition_status": "FAILED", "recognition_error": message},
                    source="RECOGNITION",
                )
                db.upsert_recognition_job(
                    db_file,
                    batch_id,
                    error_code=code,
                    error_message=message,
                    error_at=db.now(),
                )
            else:
                recognized += 1
                db.upsert_recognition_job(db_file, batch_id, last_success_at=db.now())
            completed = recognized + failed
            db.upsert_recognition_job(
                db_file,
                batch_id,
                status="IDENTIFYING",
                completed=completed,
                recognized=recognized,
                failed=failed,
                current_item_id=item["item_id"],
            )
            if delay:
                time.sleep(delay)
        if failed and not recognized:
            status = "FAILED"
        elif failed:
            status = "COMPLETE_WITH_FAILURE"
        else:
            status = "COMPLETE"
        db.upsert_recognition_job(
            db_file,
            batch_id,
            status=status,
            completed=len(items),
            recognized=recognized,
            failed=failed,
            current_item_id="",
            finished_at=db.now(),
        )
    finally:
        with _LOCK:
            _ACTIVE.pop(batch_id, None)


def start_batch_recognition(
    db_file: Path,
    batch_id: str,
    provider_name: str = "mock",
    *,
    delay: float = 0,
    retry_failed: bool = False,
) -> bool:
    providers = recognizer_registry()
    if provider_name not in providers:
        raise KeyError(f"Unknown provider: {provider_name}")
    provider = providers[provider_name]
    available, reason = provider.available()
    if not available:
        code, message = classify_recognition_error(RuntimeError(reason))
        items = db.list_items(db_file, batch_id=batch_id)
        db.upsert_recognition_job(
            db_file,
            batch_id,
            provider=provider_name,
            status="FAILED",
            total=len(items),
            completed=0,
            recognized=0,
            failed=len(items),
            error_code=code,
            error_message=message,
            error_at=db.now(),
            model_name=getattr(provider, "model_name", lambda: "")(),
            started_at=db.now(),
            finished_at=db.now(),
        )
        for item in items:
            db.update_item(
                db_file,
                item["item_id"],
                {"recognition_status": "FAILED", "recognition_error": message},
                source="RECOGNITION",
            )
        return False

    if retry_failed:
        for item in db.list_items(db_file, batch_id=batch_id, queue="FAILED"):
            db.update_item(
                db_file,
                item["item_id"],
                {"recognition_status": "PENDING", "recognition_error": ""},
                source="SYSTEM_RECOVERY",
            )

    with _LOCK:
        existing = _ACTIVE.get(batch_id)
        if existing and existing.is_alive():
            return False
        items, recognized, failed = _job_counts(db_file, batch_id)
        prior = db.get_recognition_job(db_file, batch_id) or {}
        db.upsert_recognition_job(
            db_file,
            batch_id,
            provider=provider_name,
            status="IDENTIFYING",
            total=len(items),
            completed=recognized + failed,
            recognized=recognized,
            failed=failed,
            current_item_id="",
            started_at=prior.get("started_at") or db.now(),
            finished_at=None,
            error_code="",
            error_message="",
            error_at=None,
            model_name=getattr(provider, "model_name", lambda: "")(),
        )
        thread = threading.Thread(
            target=_recognition_worker,
            args=(db_file, batch_id, provider_name, delay),
            daemon=True,
        )
        _ACTIVE[batch_id] = thread
        thread.start()
    return True


def retry_failed_item(db_file: Path, item_id: str, provider_name: str = "mock") -> None:
    provider = recognizer_registry()[provider_name]
    available, reason = provider.available()
    if not available:
        raise RuntimeError(reason)
    db.update_item(
        db_file,
        item_id,
        {"recognition_status": "PENDING", "recognition_error": ""},
        source="SYSTEM_RECOVERY",
    )
    run_recognition(db_file, item_id, provider)
    item = db.get_item(db_file, item_id)
    if item:
        batch_id = item["batch_id"]
        items, recognized, failed = _job_counts(db_file, batch_id)
        status = "COMPLETE_WITH_FAILURE" if failed else "COMPLETE"
        values: dict[str, Any] = {
            "status": status,
            "completed": recognized + failed,
            "recognized": recognized,
            "failed": failed,
        }
        if not failed:
            values.update(error_code="", error_message="", error_at=None)
        db.upsert_recognition_job(db_file, batch_id, **values)


def skip_batch_recognition(db_file: Path, batch_id: str) -> None:
    items = db.list_items(db_file, batch_id=batch_id)
    for item in items:
        if item["recognition_status"] != "COMPLETE":
            db.update_item(
                db_file,
                item["item_id"],
                {"recognition_status": "SKIPPED", "recognition_error": ""},
                source="SYSTEM_RECOVERY",
            )
    db.upsert_recognition_job(
        db_file,
        batch_id,
        status="PAUSED",
        current_item_id="",
        error_code="SKIPPED_BY_OPERATOR",
        error_message="Recognition was skipped. Items remain unfinished for manual review.",
        error_at=db.now(),
    )


def accept_item(
    db_file: Path,
    item_id: str,
    *,
    price_cents: int | None,
    discount_percent: float,
    review_source: str = "INDIVIDUAL_REVIEW",
) -> list[str]:
    item = db.get_item(db_file, item_id)
    if item is None:
        raise KeyError(f"Unknown Item ID: {item_id}")
    suggestion = db.latest_recognition(db_file, item_id)
    candidates = json.loads(suggestion["barcode_candidates_json"]) if suggestion else []
    catalog_title = ""
    catalog_status = None
    try:
        from snapims.catalog.service import get_catalog_status

        catalog_status = get_catalog_status(DataPaths.from_root(db_file.parent.parent).ensure(), item_id)
        catalog_title = catalog_status.canonical_title
    except Exception:
        catalog_status = None
    if catalog_status and catalog_status.materially_ambiguous and not str(item["title"] or "").strip():
        return ["Catalog match is ambiguous. Confirm the title in Edit details before approval."]
    values: dict[str, Any] = {
        "title": str(item["title"] or catalog_title or (suggestion["suggested_title"] if suggestion else "")).strip(),
        "release_year": item["release_year"] or (suggestion["release_year"] if suggestion else None),
        "edition": item["edition"] or (suggestion["edition"] if suggestion else ""),
        "distributor": item["distributor"] or (suggestion["distributor"] if suggestion else ""),
        "barcode": item["barcode"] or (candidates[0] if candidates else ""),
        "price_cents": (
            price_cents
            if price_cents is not None
            else (item["price_cents"] or (suggestion["suggested_price_cents"] if suggestion else None))
        ),
        "discount_percent": discount_percent,
        "recognition_provider": suggestion["provider"] if suggestion else item["recognition_provider"],
        "recognition_confidence": suggestion["confidence"] if suggestion else item["recognition_confidence"],
        "ready": 1,
        "review_status": "DONE",
        "postponed_at": None,
        "validation_status": "READY",
        "validation_errors": "[]",
        "review_source": review_source,
        "working_source": review_source,
    }
    candidate = {**item, **values}
    errors = validate_items_for_candidate(db_file, candidate)
    if errors:
        return errors
    db.update_item(db_file, item_id, values, source="AI_ACCEPTED" if review_source == "INDIVIDUAL_REVIEW" else review_source)
    if suggestion:
        with db.transaction(db_file) as connection:
            connection.execute(
                "UPDATE recognition_results SET accepted_at=? WHERE recognition_result_id=?",
                (db.now(), suggestion["recognition_result_id"]),
            )
    remaining = db.list_items(db_file, batch_id=item["batch_id"], queue="UNRESOLVED")
    if not remaining:
        db.upsert_recognition_job(db_file, item["batch_id"], status="REVIEW_COMPLETE")
    return []


def validate_items_for_candidate(db_file: Path, candidate: dict[str, Any]) -> list[str]:
    from snapims.inventory import validation_errors

    return validation_errors(candidate, db.get_item_photos(db_file, candidate["item_id"]))


def postpone_item(db_file: Path, item_id: str) -> None:
    db.update_item(
        db_file,
        item_id,
        {"review_status": "UNFINISHED", "postponed_at": db.now()},
        source="REVIEW",
    )
