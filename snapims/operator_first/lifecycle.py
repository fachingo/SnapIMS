from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from snapims import db


@dataclass(frozen=True, slots=True)
class ItemWarning:
    item_id: str
    title: str
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CommitPreview:
    batch_id: str
    item_count: int
    warning_count: int
    items_with_warnings: int
    warnings: tuple[ItemWarning, ...]
    already_committed: bool

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "warnings": [asdict(x) for x in self.warnings]}


def _item_warnings(db_file: Path, item: dict[str, Any]) -> tuple[str, ...]:
    notes: list[str] = []
    if not str(item.get("title") or "").strip():
        notes.append("Title is blank")
    if item.get("price_cents") is None:
        notes.append("Price is unpriced")
    if not item.get("tag_ids"):
        notes.append("No approved tags")
    if not str(item.get("location") or item.get("shelf") or "").strip():
        notes.append("Location is unassigned")
    if not str(item.get("barcode") or "").strip():
        notes.append("Barcode is blank")
    confidence = item.get("display_confidence")
    if confidence is not None and float(confidence) < 0.85:
        notes.append("Recognition confidence is low")
    try:
        link = db.get_item_movie_link(db_file, str(item["item_id"])) or {}
        if not link.get("movie_id") or str(link.get("link_status") or "") in {"STALE", "FAILED", "UNAVAILABLE"}:
            notes.append("Metadata unavailable or unresolved")
    except Exception:
        notes.append("Metadata unavailable")
    return tuple(notes)


def _batch_committed(db_file: Path, batch_id: str) -> bool:
    with db.connect(db_file) as connection:
        row = connection.execute(
            "SELECT 1 FROM inventory_events WHERE batch_id=? AND event_type='INVENTORY_COMMITTED' LIMIT 1",
            (batch_id,),
        ).fetchone()
    return row is not None


def commit_preview(db_file: Path, batch_id: str) -> CommitPreview:
    items = db.list_items(db_file, batch_id=batch_id)
    warnings: list[ItemWarning] = []
    warning_count = 0
    for item in items:
        notes = _item_warnings(db_file, item)
        if notes:
            warning_count += len(notes)
            warnings.append(ItemWarning(str(item["item_id"]), str(item.get("title") or item["item_id"]), notes))
    return CommitPreview(
        batch_id=batch_id,
        item_count=len(items),
        warning_count=warning_count,
        items_with_warnings=len(warnings),
        warnings=tuple(warnings),
        already_committed=_batch_committed(db_file, batch_id),
    )


def commit_batch(db_file: Path, batch_id: str, *, force: bool = False, actor: str = "local-operator") -> CommitPreview:
    preview = commit_preview(db_file, batch_id)
    if preview.items_with_warnings and not force:
        return preview
    timestamp = db.now()
    items = db.list_items(db_file, batch_id=batch_id)
    # Resolve warnings before opening the write transaction. Some warning checks read the
    # catalog-link tables and must never open a second SQLite connection while a write
    # transaction is held.
    warnings_by_item = {str(item["item_id"]): _item_warnings(db_file, item) for item in items}
    with db.transaction(db_file) as connection:
        # Idempotent: one commit event per item. Re-running Commit is non-destructive.
        for item in items:
            exists = connection.execute(
                "SELECT 1 FROM inventory_events WHERE item_id=? AND event_type='INVENTORY_COMMITTED' LIMIT 1",
                (item["item_id"],),
            ).fetchone()
            if exists:
                continue
            notes = warnings_by_item[str(item["item_id"])]
            connection.execute(
                """INSERT INTO inventory_events(
                       item_id,batch_id,occurred_at,event_type,from_location,to_location,
                       quantity_delta,source,notes
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    item["item_id"], batch_id, timestamp, "INVENTORY_COMMITTED",
                    item.get("location") or item.get("shelf") or "",
                    item.get("location") or item.get("shelf") or "",
                    0, actor,
                    json.dumps({"warnings": notes, "operator_override": bool(notes)}, sort_keys=True),
                ),
            )
        connection.execute("UPDATE batches SET status='INVENTORY_COMMITTED' WHERE batch_id=?", (batch_id,))
    return commit_preview(db_file, batch_id)
