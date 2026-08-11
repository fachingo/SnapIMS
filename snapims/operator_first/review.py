from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from snapims import db
from snapims.operator_first.taxonomy import (
    APPROVED_SET,
    normalize_automatic_tag_ids,
    tag_id as approved_tag_id,
)


@dataclass(frozen=True, slots=True)
class BulkApprovalPreview:
    batch_id: str
    threshold: float
    eligible_item_ids: tuple[str, ...]
    excluded: dict[str, int]

    @property
    def eligible_count(self) -> int:
        return len(self.eligible_item_ids)

    def as_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "eligible_count": self.eligible_count,
        }


def _selected_or_latest(db_file: Path, item_id: str) -> dict[str, Any] | None:
    return db.selected_recognition(db_file, item_id) or db.latest_recognition(db_file, item_id)


def _approved_tag_ids_from_db(db_file: Path, submitted: list[str] | tuple[str, ...]) -> list[str]:
    """Resolve a user/AI tag submission to the closed v0.16 vocabulary.

    Existing v0.15 tag IDs may not equal the deterministic v0.16 IDs. Resolve
    through the database canonical label first, then return whichever active DB
    ID represents the approved label. This preserves existing tag assignments
    while enforcing the closed vocabulary.
    """
    definitions = db.list_tag_definitions(db_file, active_only=True)
    by_id = {str(row["tag_id"]): row for row in definitions}
    by_label = {str(row["canonical_label"]).strip().casefold(): row for row in definitions}
    labels: list[str] = []
    for raw in submitted:
        text = str(raw or "").strip()
        row = by_id.get(text)
        label = str(row["canonical_label"]).strip().casefold() if row else text.casefold()
        if label in APPROVED_SET and label not in labels:
            labels.append(label)
        if len(labels) >= 3:
            break
    resolved: list[str] = []
    for label in labels:
        row = by_label.get(label)
        resolved.append(str(row["tag_id"]) if row else approved_tag_id(label))
    return resolved


def suggestion_tag_ids(db_file: Path, suggestion: dict[str, Any] | None) -> list[str]:
    if not suggestion:
        return []
    raw = suggestion.get("suggested_tag_ids")
    if raw is None:
        payload = suggestion.get("suggested_tag_ids_json")
        try:
            raw = json.loads(str(payload or "[]"))
        except json.JSONDecodeError:
            raw = []
    return _approved_tag_ids_from_db(db_file, list(raw or []))


def operator_approve(
    db_file: Path,
    item_id: str,
    *,
    title: str,
    tag_ids: list[str] | tuple[str, ...] = (),
    expected_revision: int | None = None,
    actor: str = "local-operator",
) -> dict[str, Any]:
    """Record the operator's recognition-review decision without completeness gates.

    This intentionally does *not* touch price, barcode, quantity, location,
    weight, distributor, edition, or Shopify fields. A blank title is a valid
    operator decision and remains an advisory warning for later workflow stages.
    """
    item = db.get_item(db_file, item_id)
    if item is None:
        raise KeyError(f"Unknown Item ID: {item_id}")
    suggestion = _selected_or_latest(db_file, item_id)
    approved_tags = _approved_tag_ids_from_db(db_file, list(tag_ids))
    clean_title = str(title or "").strip()
    source = "RECOGNITION_REVIEW"

    values: dict[str, Any] = {
        "title": clean_title,
        "tag_ids": approved_tags,
        "_tag_source": "OPERATOR_REVIEW",
        "review_status": "DONE",
        "postponed_at": None,
        "review_source": source,
    }
    if suggestion:
        values["recognition_provider"] = str(suggestion.get("provider") or "")
        values["recognition_confidence"] = suggestion.get("confidence")
        # Recognition itself completed even if the operator chooses a blank title.
        values["recognition_status"] = "COMPLETE"
    # A deliberately blank title should be easy to find again, never a hard lock.
    values["review"] = 1 if not clean_title else int(item.get("review") or 0)

    with db.transaction(db_file) as connection:
        saved = db.update_item_in_connection(
            connection,
            item_id,
            values,
            source=source,
            reason="Recognition Review operator decision",
            expected_revision=expected_revision,
        )
        if suggestion and clean_title:
            rid = int(suggestion["recognition_result_id"])
            timestamp = db.now()
            # Preserve one accepted current attempt while retaining history.
            prior_rows = connection.execute(
                """SELECT states.recognition_result_id
                     FROM recognition_attempt_states states
                     JOIN recognition_results results
                       ON results.recognition_result_id=states.recognition_result_id
                    WHERE results.item_id=? AND states.state='ACCEPTED'
                      AND states.recognition_result_id<>?""",
                (item_id, rid),
            ).fetchall()
            for prior in prior_rows:
                prior_id = int(prior[0])
                connection.execute(
                    "UPDATE recognition_attempt_states SET state='SUPERSEDED',updated_at=? WHERE recognition_result_id=?",
                    (timestamp, prior_id),
                )
                connection.execute(
                    """INSERT INTO recognition_attempt_events(
                           recognition_result_id,event_type,actor,occurred_at,details_json
                       ) VALUES(?,'SUPERSEDED',?,?,?)""",
                    (prior_id, actor, timestamp, json.dumps({"superseded_by": rid}, sort_keys=True)),
                )
            connection.execute(
                """INSERT INTO recognition_attempt_states(
                       recognition_result_id,state,accepted_at,accepted_by,updated_at
                   ) VALUES(?,'ACCEPTED',?,?,?)
                   ON CONFLICT(recognition_result_id) DO UPDATE SET
                       state='ACCEPTED',accepted_at=excluded.accepted_at,
                       accepted_by=excluded.accepted_by,updated_at=excluded.updated_at""",
                (rid, timestamp, actor, timestamp),
            )
            connection.execute(
                """INSERT INTO recognition_attempt_events(
                       recognition_result_id,event_type,actor,occurred_at,details_json
                   ) VALUES(?,'ACCEPTED',?,?,?)""",
                (rid, actor, timestamp, json.dumps({"title": clean_title, "tag_count": len(approved_tags)}, sort_keys=True)),
            )
    return db.get_item(db_file, item_id) or saved


def operator_reject(
    db_file: Path,
    item_id: str,
    *,
    expected_revision: int | None = None,
    actor: str = "local-operator",
) -> dict[str, Any]:
    """Reject the current recognition attempt and flag the item without trapping the operator."""
    item = db.get_item(db_file, item_id)
    if item is None:
        raise KeyError(f"Unknown Item ID: {item_id}")
    suggestion = _selected_or_latest(db_file, item_id)
    with db.transaction(db_file) as connection:
        db.update_item_in_connection(
            connection,
            item_id,
            {
                "review_status": "UNFINISHED",
                "postponed_at": db.now(),
                "review": 1,
                "review_source": "RECOGNITION_REVIEW_REJECTED",
            },
            source="RECOGNITION_REVIEW_REJECTED",
            reason="Recognition rejected by operator",
            expected_revision=expected_revision,
        )
        if suggestion:
            rid = int(suggestion["recognition_result_id"])
            timestamp = db.now()
            connection.execute(
                """INSERT INTO recognition_attempt_states(
                       recognition_result_id,state,updated_at
                   ) VALUES(?,'REJECTED',?)
                   ON CONFLICT(recognition_result_id) DO UPDATE SET
                       state='REJECTED',updated_at=excluded.updated_at""",
                (rid, timestamp),
            )
            connection.execute(
                """INSERT INTO recognition_attempt_events(
                       recognition_result_id,event_type,actor,occurred_at,details_json
                   ) VALUES(?,'REJECTED',?,?,'{}')""",
                (rid, actor, timestamp),
            )
    return db.get_item(db_file, item_id) or item


def bulk_approval_preview(db_file: Path, batch_id: str, threshold: float) -> BulkApprovalPreview:
    threshold_value = max(0.0, min(float(threshold), 1.0))
    items = db.list_items(db_file, batch_id=batch_id)
    eligible: list[str] = []
    excluded = {"failed": 0, "blank": 0, "rejected": 0, "below_threshold": 0, "already_reviewed": 0}
    for item in items:
        if str(item.get("review_status") or "") == "DONE":
            excluded["already_reviewed"] += 1
            continue
        if str(item.get("recognition_status") or "") in {"FAILED", "BLOCKED"}:
            excluded["failed"] += 1
            continue
        suggestion = _selected_or_latest(db_file, str(item["item_id"]))
        if not suggestion:
            excluded["blank"] += 1
            continue
        if str(suggestion.get("attempt_state") or "").upper() == "REJECTED":
            excluded["rejected"] += 1
            continue
        title = str(suggestion.get("suggested_title") or "").strip()
        if not title or title.casefold() == "unknown":
            excluded["blank"] += 1
            continue
        if float(suggestion.get("confidence") or 0.0) < threshold_value:
            excluded["below_threshold"] += 1
            continue
        eligible.append(str(item["item_id"]))
    return BulkApprovalPreview(batch_id, threshold_value, tuple(eligible), excluded)


def bulk_approve(
    db_file: Path,
    batch_id: str,
    threshold: float,
    *,
    actor: str = "local-operator",
) -> BulkApprovalPreview:
    preview = bulk_approval_preview(db_file, batch_id, threshold)
    for item_id in preview.eligible_item_ids:
        item = db.get_item(db_file, item_id)
        suggestion = _selected_or_latest(db_file, item_id)
        if not item or not suggestion:
            continue
        operator_approve(
            db_file,
            item_id,
            title=str(suggestion.get("suggested_title") or ""),
            tag_ids=suggestion_tag_ids(db_file, suggestion),
            expected_revision=int(item["record_revision"]),
            actor=actor,
        )
    return preview
