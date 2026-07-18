"""Durable operator workflow context: which batch is active and what to do next.

This module intentionally stays thin. It reuses the existing settings,
batch, item, and recognition-repository helpers rather than introducing a
new persistence mechanism, and it never mutates parser, recognition, or
Shopify state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snapims import db
from snapims.recognition import progress as recognition_progress
from snapims.recognition import repository

ACTIVE_BATCH_SETTING = "active_batch_id"


def set_active_batch(db_file: Path, batch_id_value: str) -> None:
    """Durably mark ``batch_id_value`` as the operator's active batch.

    Callers must only invoke this after an explicit signal: a successful
    import, a duplicate-import re-open, or an operator's deliberate
    "Change batch" action. Never call this just because a newer batch
    happens to exist.
    """
    if not db.batch_exists(db_file, batch_id_value):
        raise KeyError(f"Unknown Batch ID: {batch_id_value}")
    db.set_setting(db_file, ACTIVE_BATCH_SETTING, batch_id_value)


def get_active_batch(db_file: Path) -> dict[str, Any] | None:
    """Return the durable active batch row, repairing a stale setting.

    If the stored active batch no longer exists, the stale setting is
    cleared so future reads return ``None`` instead of a dangling
    reference, and callers fall back to an explicit "no active batch"
    state rather than guessing a replacement.
    """
    stored_id = db.get_setting(db_file, ACTIVE_BATCH_SETTING)
    if not stored_id:
        return None
    batch = db.get_batch(db_file, stored_id)
    if batch is None:
        db.set_setting(db_file, ACTIVE_BATCH_SETTING, "")
        return None
    return batch


@dataclass(frozen=True, slots=True)
class NextAction:
    label: str
    detail: str
    target_page: str


def compute_next_action(db_file: Path, batch_id_value: str) -> NextAction:
    """Compute exactly one primary next action from durable state.

    Priority is: recognize anything never attempted, then recover
    failures, then clear the review queues, then fix validation blockers,
    then publish anything ready. This mirrors the existing Import ->
    Review -> Publish journey (recognition and validation are contextual
    steps inside Review) without adding a new status field. ``target_page``
    is always one of the five consolidated top-level destinations.
    """
    items = db.list_items(db_file, batch_id_value=batch_id_value)
    if not items:
        return NextAction(
            "Import photos for this batch",
            "This batch has no items yet.",
            "Import",
        )

    unattempted = [
        item
        for item in items
        if repository.latest_result_for_item(db_file, item["item_id"]) is None
    ]
    if unattempted:
        job = recognition_progress.latest_job(db_file, batch_id_value)
        if job is not None and job.status == "INTERRUPTED":
            return NextAction(
                f"Resume recognition ({job.remaining} remaining, {job.failed} failed)",
                f"{job.completed} of {job.total} item boundaries were committed safely.",
                "Review",
            )
        return NextAction(
            f"Run recognition for {len(unattempted)} item(s)",
            "These items have never had a recognition attempt.",
            "Review",
        )

    failed = repository.list_review_queue(db_file, batch_id_value, repository.QUEUE_FAILED)
    if failed:
        return NextAction(
            f"Retry {len(failed)} failed recognition(s)",
            "Recognition failed for these items; retry with a provider.",
            "Review",
        )

    to_review = repository.list_review_queue(db_file, batch_id_value, repository.QUEUE_TO_REVIEW)
    needs_attention = repository.list_review_queue(
        db_file, batch_id_value, repository.QUEUE_NEEDS_ATTENTION
    )
    if to_review or needs_attention:
        return NextAction(
            f"Review {len(to_review) + len(needs_attention)} item(s)",
            "Suggestions are waiting for an operator decision.",
            "Review",
        )

    blocked = [item for item in items if item["validation_status"] == "BLOCKED"]
    if blocked:
        return NextAction(
            f"Fix {len(blocked)} item(s) failing validation",
            "These items are missing required fields before they can be published.",
            "Review",
        )

    not_ready = [item for item in items if not item["ready"]]
    if not_ready:
        return NextAction(
            f"Mark {len(not_ready)} item(s) ready for publish",
            "Confirm price, condition, and other fields, then mark these items ready.",
            "Review",
        )

    ready_unpublished = [
        item
        for item in items
        if item["ready"]
        and item["validation_status"] == "READY"
        and item["upload_status"] != "UPLOADED"
    ]
    if ready_unpublished:
        return NextAction(
            f"Publish {len(ready_unpublished)} ready item(s)",
            "These items passed validation and are ready for a Shopify draft.",
            "Publish",
        )

    return NextAction(
        "Batch complete",
        "Every item has been reviewed, validated, and published or is not ready.",
        "Import",
    )
