from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from snapims import db
from snapims.inventory import validation_errors
from snapims.money import (
    add_price_cents,
    parse_discount_percent,
    parse_price_cents,
    round_price_cents,
    subtract_percent_cents,
)
from snapims.recognition.service import _accept_values, accept_item_in_connection


@dataclass(frozen=True, slots=True)
class BulkResult:
    requested: int
    validated: int
    changed: int
    unchanged: int
    failed: int
    errors: tuple[str, ...]
    checkpoint_id: int
    request_id: str

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["errors"] = list(self.errors)
        return result


def _updates_for(action: str, item: dict[str, Any], value: Any) -> dict[str, Any]:
    if action == "set_price":
        cents = parse_price_cents(value, allow_blank=False)
        assert cents is not None
        return {"price_cents": cents}
    if action == "add_price":
        return {"price_cents": add_price_cents(item.get("price_cents"), value)}
    if action == "subtract_percent":
        return {"price_cents": subtract_percent_cents(item.get("price_cents"), value)}
    if action == "round_price":
        return {"price_cents": round_price_cents(item.get("price_cents"), value or "0.50")}
    if action == "set_discount":
        return {"discount_percent": parse_discount_percent(value)}
    if action == "set_title":
        return {"title": str(value or "").strip()}
    if action == "set_description":
        return {"description": str(value or "")}
    if action == "set_location":
        return {"shelf": str(value or "").strip().upper()}
    if action == "flag_review":
        return {"review": 1}
    if action == "clear_review":
        return {"review": 0}
    if action == "mark_rare":
        return {"rare": 1}
    if action == "clear_rare":
        return {"rare": 0}
    if action == "append_tags":
        incoming = [part.strip() for part in str(value or "").split(",") if part.strip()]
        existing = [part.strip() for part in str(item.get("tags") or "").split(",") if part.strip()]
        for part in incoming:
            if part not in existing:
                existing.append(part)
        return {"tags": ", ".join(existing)}
    if action == "prefix_description":
        return {"description": str(value or "") + str(item.get("description") or "")}
    if action == "replace_description":
        old, separator, new = str(value or "").partition("=>")
        if not separator or not old:
            raise ValueError("Use find=>replace for description replacement")
        return {"description": str(item.get("description") or "").replace(old, new)}
    if action == "approve":
        return {}
    raise ValueError("Unknown bulk action")


def apply_bulk_operation(
    db_file: Path,
    batch_id: str,
    *,
    item_ids: list[str],
    action: str,
    value: Any = None,
    reason: str = "Bulk edit",
    request_id: str,
    fail_after: int | None = None,
) -> BulkResult:
    if not item_ids:
        raise ValueError("Select at least one item")
    if len(item_ids) != len(set(item_ids)):
        raise ValueError("The bulk selection contains duplicate Item IDs")
    all_items = {item["item_id"]: item for item in db.list_items(db_file, batch_id=batch_id)}
    unknown = [item_id for item_id in item_ids if item_id not in all_items]
    if unknown:
        raise ValueError(f"Item is not in this batch: {unknown[0]}")

    with db.connect(db_file) as connection:
        previous_request = connection.execute(
            "SELECT status,result_json FROM operation_requests WHERE request_id=?",
            (request_id,),
        ).fetchone()
    if previous_request and str(previous_request[0]) == "SUCCESS":
        payload = json.loads(previous_request[1])
        return BulkResult(
            requested=int(payload["requested"]),
            validated=int(payload["validated"]),
            changed=int(payload["changed"]),
            unchanged=int(payload["unchanged"]),
            failed=int(payload["failed"]),
            errors=tuple(payload.get("errors") or []),
            checkpoint_id=int(payload["checkpoint_id"]),
            request_id=request_id,
        )

    prepared: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]] = []
    errors: list[str] = []
    unchanged = 0
    for item_id in item_ids:
        item = all_items[item_id]
        suggestion = db.latest_recognition(db_file, item_id)
        try:
            if action == "approve":
                values = _accept_values(
                    item,
                    suggestion,
                    price_cents=item.get("price_cents"),
                    discount_percent=parse_discount_percent(item.get("discount_percent") or 0),
                    review_source="BATCH_EDITOR_REVIEW",
                )
                candidate = {**item, **values}
                candidate_errors = validation_errors(
                    candidate, db.get_item_photos(db_file, item_id)
                )
                if candidate_errors:
                    errors.extend(f"{item_id}: {error}" for error in candidate_errors)
                    continue
                prepared.append((item, {}, suggestion))
            else:
                updates = _updates_for(action, item, value)
                updates["working_source"] = "BULK_EDIT"
                candidate = {**item, **updates}
                candidate_errors = validation_errors(
                    candidate, db.get_item_photos(db_file, item_id)
                )
                # Bulk edits may leave an item incomplete, but they may not introduce structurally invalid values.
                structural = [
                    error for error in candidate_errors
                    if not error.startswith("Title is required")
                    and not error.startswith("Price must be greater than zero")
                ]
                if structural:
                    errors.extend(f"{item_id}: {error}" for error in structural)
                    continue
                if all(item.get(field) == new_value for field, new_value in updates.items()):
                    unchanged += 1
                prepared.append((item, updates, suggestion))
        except Exception as exc:
            errors.append(f"{item_id}: {exc}")
    if errors:
        raise ValueError("Bulk validation failed; zero items changed. " + " | ".join(errors))

    try:
        with db.transaction(db_file) as connection:
            timestamp = db.now()
            connection.execute(
                """INSERT INTO operation_requests(
                       request_id,operation_type,batch_id,status,result_json,error_message,
                       created_at,updated_at,completed_at
                   ) VALUES(?,?,?,'RUNNING','{}','',?,?,NULL)
                   ON CONFLICT(request_id) DO UPDATE SET
                       status='RUNNING',error_message='',updated_at=excluded.updated_at,completed_at=NULL""",
                (request_id, f"BULK_{action.upper()}", batch_id, timestamp, timestamp),
            )
            checkpoint_id = db.create_batch_checkpoint_in_connection(
                connection,
                batch_id,
                reason=f"Before bulk action {action}",
                source="BULK_EDIT",
            )
            changed = 0
            for item, updates, suggestion in prepared:
                if action == "approve":
                    accept_item_in_connection(
                        connection,
                        db_file,
                        item,
                        suggestion,
                        price_cents=item.get("price_cents"),
                        discount_percent=parse_discount_percent(item.get("discount_percent") or 0),
                        review_source="BATCH_EDITOR_REVIEW",
                    )
                    changed += 1
                elif any(item.get(field) != new_value for field, new_value in updates.items()):
                    db.update_item_in_connection(
                        connection,
                        item["item_id"],
                        updates,
                        source="BULK_EDIT",
                        reason=reason or "Batch Editor bulk change",
                    )
                    changed += 1
                if fail_after is not None and changed >= fail_after:
                    raise RuntimeError(f"Injected bulk failure after {changed} item(s)")
            result = BulkResult(
                requested=len(item_ids),
                validated=len(prepared),
                changed=changed,
                unchanged=len(item_ids) - changed,
                failed=0,
                errors=(),
                checkpoint_id=checkpoint_id,
                request_id=request_id,
            )
            completed_at = db.now()
            connection.execute(
                "UPDATE operation_requests SET status='SUCCESS',result_json=?,updated_at=?,completed_at=? "
                "WHERE request_id=?",
                (json.dumps(result.as_dict()), completed_at, completed_at, request_id),
            )
        return result
    except Exception as exc:
        timestamp = db.now()
        with db.transaction(db_file) as connection:
            connection.execute(
                """INSERT INTO operation_requests(
                       request_id,operation_type,batch_id,status,result_json,error_message,
                       created_at,updated_at,completed_at
                   ) VALUES(?,?,?,'FAILED','{}',?,?,?,?)
                   ON CONFLICT(request_id) DO UPDATE SET
                       status='FAILED',error_message=excluded.error_message,
                       updated_at=excluded.updated_at,completed_at=excluded.completed_at""",
                (request_id, f"BULK_{action.upper()}", batch_id, str(exc), timestamp, timestamp, timestamp),
            )
        raise
