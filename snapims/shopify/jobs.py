from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable
from uuid import uuid4

from snapims import db
from snapims.config import DataPaths, ShopifyConfig
from snapims.observability import safe_exception, try_emit_event
from snapims.shopify.client import ShopifyAPIError
from snapims.shopify.service import ShopifyService

ACTIONS = frozenset(
    {
        "CREATE_DRAFTS",
        "PUBLISH_LIVE",
        "DIRECT_PUBLISH",
        "SYNC",
        "RECONCILE",
        "ARCHIVE",
        "RESTORE_DRAFT",
        "DELETE",
        "KEEP_SHOPIFY",
        "MERGE",
    }
)
CONFIRMATIONS: dict[str, str] = {
    "PUBLISH_LIVE": "SUBMIT",
    "DIRECT_PUBLISH": "SUBMIT LIVE",
    "ARCHIVE": "ARCHIVE",
    "RESTORE_DRAFT": "RESTORE",
    "DELETE": "DELETE",
    "KEEP_SHOPIFY": "KEEP SHOPIFY",
    "MERGE": "MERGE",
}
TERMINAL_JOB_STATUSES = frozenset({"COMPLETE", "COMPLETE_WITH_FAILURES", "FAILED", "CANCELLED"})
TERMINAL_ITEM_STATUSES = frozenset({"SUCCESS", "SKIPPED", "FAILED"})
_TRANSIENT_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_ACTIVE: dict[str, threading.Thread] = {}
_ACTIVE_LOCK = threading.RLock()
_EXECUTION_LOCK = threading.Lock()


class ShopifyJobError(RuntimeError):
    pass


def _event(paths: DataPaths, job_id: str, event_type: str, **fields: Any) -> None:
    try_emit_event(
        paths.db_file,
        component="shopify",
        event_type=event_type,
        operation_id=f"shopify-job:{job_id}",
        paths=paths,
        retention_class="BUSINESS",
        **fields,
    )


def _normalize_item_ids(db_file: Path, batch_id: str, item_ids: Iterable[str], scope: str) -> list[str]:
    requested = [str(value).strip() for value in item_ids if str(value).strip()]
    with db.connect(db_file) as connection:
        if scope.upper() == "ALL":
            rows = connection.execute(
                "SELECT item_id FROM items WHERE batch_id=? ORDER BY sequence,item_id",
                (batch_id,),
            ).fetchall()
            return [str(row[0]) for row in rows]
        if not requested:
            raise ShopifyJobError("Select at least one Item or choose the entire batch.")
        placeholders = ",".join("?" for _ in requested)
        rows = connection.execute(
            f"SELECT item_id FROM items WHERE batch_id=? AND item_id IN ({placeholders}) ORDER BY sequence,item_id",
            (batch_id, *requested),
        ).fetchall()
    found = [str(row[0]) for row in rows]
    if len(found) != len(set(requested)):
        raise ShopifyJobError("One or more selected Items do not belong to this batch.")
    return found


def _validate_confirmation(action: str, confirmation: str) -> None:
    required = CONFIRMATIONS.get(action)
    if required and confirmation.strip() != required:
        raise ShopifyJobError(f"Type {required} exactly to confirm this Shopify action.")


def _assert_no_active_duplicate(db_file: Path, batch_id: str, action: str) -> None:
    with db.connect(db_file) as connection:
        row = connection.execute(
            """SELECT job_id FROM shopify_publish_jobs
                 WHERE batch_id=? AND action=?
                   AND status IN ('QUEUED','RUNNING','RETRYING','PAUSED')
                 ORDER BY created_at DESC LIMIT 1""",
            (batch_id, action),
        ).fetchone()
    if row:
        raise ShopifyJobError(
            f"A {action.replace('_', ' ').lower()} job is already active for this batch ({row[0]})."
        )


def create_job(
    paths: DataPaths,
    *,
    batch_id: str,
    action: str,
    item_ids: Iterable[str] = (),
    selection_scope: str = "SELECTED",
    confirmation: str = "",
    options: dict[str, Any] | None = None,
    service_factory: Callable[[Path, ShopifyConfig], ShopifyService] | None = None,
    start: bool = True,
) -> str:
    db.initialize(paths.db_file, paths=paths)
    normalized_action = action.strip().upper()
    if normalized_action not in ACTIONS:
        raise ShopifyJobError(f"Unsupported Shopify job action: {action}")
    scope = selection_scope.strip().upper() or "SELECTED"
    if scope not in {"SELECTED", "ALL"}:
        raise ShopifyJobError("Selection scope must be SELECTED or ALL.")
    _validate_confirmation(normalized_action, confirmation)
    normalized_options = dict(options or {})
    allow_incomplete = bool(normalized_options.get("allow_incomplete"))
    selected = _normalize_item_ids(paths.db_file, batch_id, item_ids, scope)
    if not selected:
        raise ShopifyJobError("This batch has no Items to process.")
    _assert_no_active_duplicate(paths.db_file, batch_id, normalized_action)

    config = ShopifyConfig.from_env()
    service = (service_factory or ShopifyService)(paths.db_file, config)
    if normalized_action in {"CREATE_DRAFTS", "DIRECT_PUBLISH"} and not allow_incomplete:
        blocked: list[str] = []
        for item_id in selected:
            item = db.get_item(paths.db_file, item_id)
            if item and item.get("shopify_product_id"):
                continue
            report = service.dry_run(item_id, remote_check=False)
            if not report.ready:
                blocked.append(f"{item_id}: {'; '.join(report.errors) or report.action}")
        if blocked:
            preview = " | ".join(blocked[:5])
            suffix = f" (+{len(blocked)-5} more)" if len(blocked) > 5 else ""
            raise ShopifyJobError(f"Shopify simulation blocked this job: {preview}{suffix}")
    if normalized_action in {"PUBLISH_LIVE", "DIRECT_PUBLISH"} and not config.publication_id:
        raise ShopifyJobError(
            "Select the Shopify publication in Settings before publishing live."
        )

    job_id = str(uuid4())
    timestamp = db.now()
    with db.transaction(paths.db_file) as connection:
        connection.execute(
            """INSERT INTO shopify_publish_jobs(
                   job_id,batch_id,action,status,selection_scope,total,
                   confirmation_text,options_json,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                job_id,
                batch_id,
                normalized_action,
                "QUEUED",
                scope,
                len(selected),
                confirmation.strip(),
                json.dumps(normalized_options, sort_keys=True),
                timestamp,
                timestamp,
            ),
        )
        for sequence, item_id in enumerate(selected, start=1):
            connection.execute(
                """INSERT INTO shopify_publish_job_items(
                       job_id,item_id,sequence,action,status,updated_at
                   ) VALUES(?,?,?,?,?,?)""",
                (job_id, item_id, sequence, normalized_action, "QUEUED", timestamp),
            )
    _event(
        paths,
        job_id,
        "shopify.job_queued",
        batch_id=batch_id,
        status="QUEUED",
        outcome=normalized_action,
        detail={"total": len(selected), "selection_scope": scope},
    )
    if start:
        start_job(paths, job_id, service_factory=service_factory)
    return job_id


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, ShopifyAPIError):
        return exc.status_code in _TRANSIENT_STATUS_CODES
    return isinstance(exc, (TimeoutError, ConnectionError))


def _perform(service: ShopifyService, action: str, item_id: str, *, options: dict[str, Any] | None = None) -> dict[str, Any]:
    item = db.get_item(service.db_file, item_id)
    options = dict(options or {})
    if item is None:
        raise ShopifyJobError(f"Unknown Item ID: {item_id}")
    remote_id = str(item.get("shopify_product_id") or "")
    upload_status = str(item.get("upload_status") or "").upper()

    if action == "CREATE_DRAFTS":
        if remote_id and upload_status not in {"FAILED", "DELETED", "NOT_UPLOADED"}:
            return {"status": "SKIPPED", "reason": "Shopify product already linked", "product_id": remote_id}
        return service.upload_draft(item_id, confirmed=True, allow_incomplete=bool(options.get("allow_incomplete")))
    if action == "PUBLISH_LIVE":
        if upload_status == "PUBLISHED":
            return {"status": "SKIPPED", "reason": "Already published", "product_id": remote_id}
        return service.publish_live(item_id, confirmed=True)
    if action == "DIRECT_PUBLISH":
        draft = None
        if not remote_id or upload_status in {"FAILED", "DELETED", "NOT_UPLOADED"}:
            draft = service.upload_draft(item_id, confirmed=True, allow_incomplete=bool(options.get("allow_incomplete")))
        live = service.publish_live(item_id, confirmed=True)
        return {"status": "PUBLISHED", "draft": draft, "live": live, **live}
    if action == "SYNC":
        return service.sync_product(item_id, confirmed=True)
    if action == "RECONCILE":
        return service.reconcile_product(item_id)
    if action == "ARCHIVE":
        if upload_status == "ARCHIVED":
            return {"status": "SKIPPED", "reason": "Already archived", "product_id": remote_id}
        return service.archive_product(item_id, confirmed=True)
    if action == "RESTORE_DRAFT":
        if upload_status == "UPLOADED":
            return {"status": "SKIPPED", "reason": "Already a draft", "product_id": remote_id}
        return service.restore_draft(item_id, confirmed=True)
    if action == "DELETE":
        if upload_status == "DELETED":
            return {"status": "SKIPPED", "reason": "Already deleted", "product_id": remote_id}
        return service.delete_product(item_id, confirmed=True)
    if action == "KEEP_SHOPIFY":
        return service.keep_shopify(item_id, confirmed=True)
    if action == "MERGE":
        return service.merge_remote(item_id, confirmed=True)
    raise ShopifyJobError(f"Unsupported action: {action}")


def _run_job_inner(
    paths: DataPaths,
    job_id: str,
    service_factory: Callable[[Path, ShopifyConfig], ShopifyService] | None = None,
) -> None:
    with _EXECUTION_LOCK:
        with db.connect(paths.db_file) as connection:
            job = connection.execute(
                "SELECT * FROM shopify_publish_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        if job is None:
            return
        action = str(job["action"])
        try:
            job_options = json.loads(str(job["options_json"] or "{}"))
        except json.JSONDecodeError:
            job_options = {}
        timestamp = db.now()
        with db.transaction(paths.db_file) as connection:
            connection.execute(
                """UPDATE shopify_publish_jobs
                      SET status='RUNNING',started_at=COALESCE(started_at,?),
                          updated_at=?,error_message=''
                    WHERE job_id=?""",
                (timestamp, timestamp, job_id),
            )
            connection.execute(
                """UPDATE shopify_publish_job_items
                      SET status='QUEUED',updated_at=?
                    WHERE job_id=? AND status='RUNNING'""",
                (timestamp, job_id),
            )
        _event(
            paths,
            job_id,
            "shopify.job_started",
            batch_id=str(job["batch_id"]),
            status="RUNNING",
            outcome=action,
        )
        service = (service_factory or ShopifyService)(paths.db_file, ShopifyConfig.from_env())
        with db.connect(paths.db_file) as connection:
            rows = connection.execute(
                """SELECT * FROM shopify_publish_job_items
                     WHERE job_id=? AND status NOT IN ('SUCCESS','SKIPPED')
                     ORDER BY sequence""",
                (job_id,),
            ).fetchall()
        fatal_error = ""
        for row in rows:
            item_id = str(row["item_id"])
            with db.transaction(paths.db_file) as connection:
                connection.execute(
                    """UPDATE shopify_publish_job_items
                          SET status='RUNNING',started_at=COALESCE(started_at,?),
                              updated_at=?,error_message='',attempt_count=attempt_count+1
                        WHERE job_id=? AND item_id=?""",
                    (db.now(), db.now(), job_id, item_id),
                )
                connection.execute(
                    "UPDATE shopify_publish_jobs SET current_item_id=?,updated_at=? WHERE job_id=?",
                    (item_id, db.now(), job_id),
                )
            result: dict[str, Any] = {}
            error_message = ""
            item_status = "FAILED"
            for attempt in range(1, 4):
                try:
                    result = _perform(service, action, item_id, options=job_options)
                    item_status = "SKIPPED" if str(result.get("status") or "").upper() == "SKIPPED" else "SUCCESS"
                    break
                except Exception as exc:  # bounded retry is classified below
                    safe = safe_exception(
                        exc,
                        known_secrets=tuple(
                            value
                            for value in (service.config.access_token, service.config.client_secret)
                            if value
                        ),
                    )
                    error_message = safe["safe_summary"]
                    if attempt >= 3 or not _is_transient(exc):
                        break
                    with db.transaction(paths.db_file) as connection:
                        connection.execute(
                            "UPDATE shopify_publish_job_items SET status='RETRYING',updated_at=? WHERE job_id=? AND item_id=?",
                            (db.now(), job_id, item_id),
                        )
                    _event(
                        paths,
                        job_id,
                        "shopify.item_retrying",
                        batch_id=str(job["batch_id"]),
                        item_id=item_id,
                        status="RETRYING",
                        outcome=action,
                        attempt_number=attempt,
                        safe_summary=error_message,
                    )
                    time.sleep(min(2.0, 0.25 * (2 ** (attempt - 1))))
            with db.transaction(paths.db_file) as connection:
                connection.execute(
                    """UPDATE shopify_publish_job_items
                          SET status=?,error_message=?,result_json=?,updated_at=?,finished_at=?
                        WHERE job_id=? AND item_id=?""",
                    (
                        item_status,
                        error_message,
                        json.dumps(result, sort_keys=True, default=str),
                        db.now(),
                        db.now(),
                        job_id,
                        item_id,
                    ),
                )
                counts = connection.execute(
                    """SELECT COUNT(*) AS total,
                              SUM(CASE WHEN status IN ('SUCCESS','SKIPPED','FAILED') THEN 1 ELSE 0 END) AS completed,
                              SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) AS succeeded,
                              SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) AS failed,
                              SUM(CASE WHEN status='SKIPPED' THEN 1 ELSE 0 END) AS skipped
                         FROM shopify_publish_job_items WHERE job_id=?""",
                    (job_id,),
                ).fetchone()
                connection.execute(
                    """UPDATE shopify_publish_jobs
                          SET completed=?,succeeded=?,failed=?,skipped=?,updated_at=?
                        WHERE job_id=?""",
                    (
                        int(counts["completed"] or 0),
                        int(counts["succeeded"] or 0),
                        int(counts["failed"] or 0),
                        int(counts["skipped"] or 0),
                        db.now(),
                        job_id,
                    ),
                )
            _event(
                paths,
                job_id,
                "shopify.item_completed" if item_status != "FAILED" else "shopify.item_failed",
                batch_id=str(job["batch_id"]),
                item_id=item_id,
                severity="INFO" if item_status != "FAILED" else "ERROR",
                status=item_status,
                outcome=action,
                safe_summary=error_message,
            )

        with db.transaction(paths.db_file) as connection:
            counts = connection.execute(
                "SELECT completed,succeeded,failed,skipped,total FROM shopify_publish_jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
            final_status = "COMPLETE_WITH_FAILURES" if int(counts["failed"] or 0) else "COMPLETE"
            connection.execute(
                """UPDATE shopify_publish_jobs
                      SET status=?,current_item_id='',updated_at=?,finished_at=?,error_message=?
                    WHERE job_id=?""",
                (final_status, db.now(), db.now(), fatal_error, job_id),
            )
        _event(
            paths,
            job_id,
            "shopify.job_completed",
            batch_id=str(job["batch_id"]),
            status=final_status,
            outcome=action,
            detail={
                "total": int(counts["total"] or 0),
                "succeeded": int(counts["succeeded"] or 0),
                "failed": int(counts["failed"] or 0),
                "skipped": int(counts["skipped"] or 0),
            },
        )
    with _ACTIVE_LOCK:
        _ACTIVE.pop(job_id, None)



def _run_job(
    paths: DataPaths,
    job_id: str,
    service_factory: Callable[[Path, ShopifyConfig], ShopifyService] | None = None,
) -> None:
    try:
        _run_job_inner(paths, job_id, service_factory)
    except Exception as exc:
        safe = safe_exception(exc)
        try:
            with db.transaction(paths.db_file) as connection:
                row = connection.execute(
                    "SELECT batch_id,action FROM shopify_publish_jobs WHERE job_id=?",
                    (job_id,),
                ).fetchone()
                connection.execute(
                    """UPDATE shopify_publish_jobs
                          SET status='FAILED',current_item_id='',error_message=?,
                              updated_at=?,finished_at=?
                        WHERE job_id=?""",
                    (safe["safe_summary"], db.now(), db.now(), job_id),
                )
                connection.execute(
                    """UPDATE shopify_publish_job_items
                          SET status='FAILED',error_message=?,updated_at=?,finished_at=?
                        WHERE job_id=? AND status IN ('QUEUED','RUNNING','RETRYING')""",
                    (safe["safe_summary"], db.now(), db.now(), job_id),
                )
            _event(
                paths,
                job_id,
                "shopify.job_failed",
                batch_id=str(row["batch_id"] if row else ""),
                severity="ERROR",
                status="FAILED",
                outcome=str(row["action"] if row else "UNKNOWN"),
                error_class=safe["error_class"],
                safe_summary=safe["safe_summary"],
            )
        except Exception:
            # The worker must never crash the application process while reporting
            # a secondary persistence failure. The original exception remains
            # represented by the stopped worker and the durable job row when possible.
            pass
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE.pop(job_id, None)


def start_job(
    paths: DataPaths,
    job_id: str,
    *,
    service_factory: Callable[[Path, ShopifyConfig], ShopifyService] | None = None,
) -> bool:
    with _ACTIVE_LOCK:
        existing = _ACTIVE.get(job_id)
        if existing and existing.is_alive():
            return False
        thread = threading.Thread(
            target=_run_job,
            args=(paths, job_id, service_factory),
            name=f"snapims-shopify-{job_id[:8]}",
            daemon=True,
        )
        _ACTIVE[job_id] = thread
        thread.start()
        return True


def get_job(db_file: Path, job_id: str) -> dict[str, Any] | None:
    db.initialize(db_file)
    with db.connect(db_file) as connection:
        row = connection.execute(
            "SELECT * FROM shopify_publish_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        items = [
            dict(value)
            for value in connection.execute(
                """SELECT ji.*,i.title,i.sku,i.shopify_admin_url,i.shopify_product_id,i.upload_status
                     FROM shopify_publish_job_items ji
                     JOIN items i ON i.item_id=ji.item_id
                    WHERE ji.job_id=? ORDER BY ji.sequence""",
                (job_id,),
            ).fetchall()
        ]
    result = dict(row)
    for item in items:
        try:
            item["result"] = json.loads(str(item.get("result_json") or "{}"))
        except json.JSONDecodeError:
            item["result"] = {}
    result["items"] = items
    total = max(1, int(result.get("total") or 0))
    completed = int(result.get("completed") or 0)
    result["progress_percent"] = int(round(100 * completed / total))
    started = str(result.get("started_at") or "")
    elapsed = 0.0
    if started:
        try:
            from datetime import datetime

            elapsed = max(0.0, time.time() - datetime.fromisoformat(started).timestamp())
        except ValueError:
            elapsed = 0.0
    rate = completed / elapsed if elapsed > 0 and completed else 0.0
    result["elapsed_seconds"] = round(elapsed, 1)
    result["items_per_minute"] = round(rate * 60, 1) if rate else 0.0
    result["eta_seconds"] = round((int(result.get("total") or 0) - completed) / rate, 1) if rate else None
    result["terminal"] = str(result.get("status") or "") in TERMINAL_JOB_STATUSES
    return result


def list_jobs(db_file: Path, batch_id: str = "", *, limit: int = 20) -> list[dict[str, Any]]:
    db.initialize(db_file)
    with db.connect(db_file) as connection:
        if batch_id:
            rows = connection.execute(
                "SELECT * FROM shopify_publish_jobs WHERE batch_id=? ORDER BY created_at DESC LIMIT ?",
                (batch_id, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM shopify_publish_jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]


def resume_job(
    paths: DataPaths,
    job_id: str,
    *,
    service_factory: Callable[[Path, ShopifyConfig], ShopifyService] | None = None,
) -> bool:
    with db.transaction(paths.db_file) as connection:
        row = connection.execute(
            "SELECT status FROM shopify_publish_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise ShopifyJobError("Unknown Shopify job.")
        connection.execute(
            """UPDATE shopify_publish_job_items
                  SET status='QUEUED',error_message='',updated_at=?,finished_at=NULL
                WHERE job_id=? AND status='FAILED'""",
            (db.now(), job_id),
        )
        connection.execute(
            """UPDATE shopify_publish_jobs
                  SET status='QUEUED',failed=0,error_message='',updated_at=?,finished_at=NULL
                WHERE job_id=?""",
            (db.now(), job_id),
        )
    return start_job(paths, job_id, service_factory=service_factory)


def recover_jobs(
    paths: DataPaths,
    *,
    start_workers: bool = True,
    service_factory: Callable[[Path, ShopifyConfig], ShopifyService] | None = None,
) -> int:
    db.initialize(paths.db_file, paths=paths)
    with db.transaction(paths.db_file) as connection:
        rows = connection.execute(
            """SELECT job_id FROM shopify_publish_jobs
                 WHERE status IN ('RUNNING','RETRYING','QUEUED')
                 ORDER BY created_at"""
        ).fetchall()
        timestamp = db.now()
        for row in rows:
            job_id = str(row[0])
            connection.execute(
                "UPDATE shopify_publish_job_items SET status='QUEUED',updated_at=? WHERE job_id=? AND status IN ('RUNNING','RETRYING')",
                (timestamp, job_id),
            )
            connection.execute(
                "UPDATE shopify_publish_jobs SET status='QUEUED',current_item_id='',updated_at=? WHERE job_id=?",
                (timestamp, job_id),
            )
    if start_workers:
        for row in rows:
            start_job(paths, str(row[0]), service_factory=service_factory)
    return len(rows)
