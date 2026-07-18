from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snapims import db
from snapims.inventory import validate_items
from snapims.shopify.service import ShopifyDryRun, ShopifyService


@dataclass(frozen=True, slots=True)
class PublishQueueEntry:
    item_id: str
    title: str
    sequence: int
    state: str
    reasons: tuple[str, ...]
    admin_url: str
    retry_count: int


@dataclass(frozen=True, slots=True)
class PublishBatchResult:
    item_id: str
    outcome: str
    message: str = ""
    result: dict[str, Any] | None = None


def build_publish_queue(db_file: Path, batch_id: str) -> list[PublishQueueEntry]:
    """Validate and classify every item in one batch for operator publishing."""
    items = db.list_items(db_file, batch_id_value=batch_id)
    validate_items(db_file, [str(item["item_id"]) for item in items])
    refreshed = db.list_items(db_file, batch_id_value=batch_id)
    entries: list[PublishQueueEntry] = []
    for item in refreshed:
        try:
            validation_reasons = tuple(
                str(reason) for reason in json.loads(item["validation_errors"] or "[]")
            )
        except (json.JSONDecodeError, TypeError):
            validation_reasons = (
                (str(item["validation_errors"]),) if item["validation_errors"] else ()
            )
        upload_status = str(item["upload_status"])
        if upload_status == "UPLOADED":
            state = "Drafted"
            reasons: tuple[str, ...] = ()
        elif validation_reasons or not bool(item["ready"]):
            state = "Blocked"
            reasons = validation_reasons
            if not item["ready"]:
                reasons = (*reasons, "Mark the item ready after correcting its listing")
        elif upload_status == "FAILED":
            state = "Failed"
            reasons = (str(item["last_error"] or "The previous draft attempt failed"),)
        else:
            state = "Ready"
            reasons = ()
        entries.append(
            PublishQueueEntry(
                item_id=str(item["item_id"]),
                title=str(item["title"] or "Untitled tape"),
                sequence=int(item["sequence"]),
                state=state,
                reasons=tuple(dict.fromkeys(reasons)),
                admin_url=str(item["shopify_admin_url"] or ""),
                retry_count=int(item["retry_count"]),
            )
        )
    return entries


def simulate_selected(
    service: ShopifyService, item_ids: Iterable[str], *, remote_check: bool = False
) -> list[ShopifyDryRun]:
    """Evaluate selected items; local simulation makes no network calls."""
    return [service.dry_run(item_id, remote_check=remote_check) for item_id in item_ids]


def create_selected_drafts(
    service: ShopifyService,
    item_ids: Iterable[str],
    *,
    confirmed: bool = False,
) -> list[PublishBatchResult]:
    """Create drafts independently so one item failure cannot stop the batch."""
    if not confirmed:
        raise PermissionError("Live Shopify writes require deliberate selected-set confirmation.")
    outcomes: list[PublishBatchResult] = []
    for item_id in dict.fromkeys(item_ids):
        item = db.get_item(service.db_file, item_id)
        if item is not None and item["upload_status"] == "UPLOADED":
            outcomes.append(PublishBatchResult(item_id, "SKIPPED_DRAFTED"))
            continue
        try:
            result = service.upload_draft(item_id, confirmed=True)
        except Exception as exc:
            outcomes.append(PublishBatchResult(item_id, "FAILED", str(exc)))
        else:
            outcomes.append(PublishBatchResult(item_id, "DRAFTED", result=result))
    return outcomes
