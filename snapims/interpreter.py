from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from snapims.models import BatchRecord, ItemRecord, PhotoRecord
from snapims.protocol import CommandKind, parse_command


class ProtocolError(RuntimeError):
    """Raised when a command stream would require SnapIMS to guess."""


def sanitize_batch_name(value: str | None) -> str | None:
    if value is None:
        return None
    sanitized = re.sub(r"[^A-Z0-9]+", "-", value.strip().upper()).strip("-")
    return sanitized or None


def make_batch_id(created_at: datetime, batch_name: str | None = None) -> str:
    base = created_at.strftime("%Y%m%d-%H%M%S")
    cleaned = sanitize_batch_name(batch_name)
    return f"{base}-{cleaned}" if cleaned else base


def interpret_stream(
    records: list[PhotoRecord],
    *,
    source_folder: Path,
    batch_name: str | None = None,
    imported_at: datetime | None = None,
    batch_id: str | None = None,
    source_fingerprint: str = "",
) -> BatchRecord:
    if not records:
        raise ProtocolError("No supported photographs were found.")
    imported_at = imported_at or datetime.now()
    batch = BatchRecord(
        batch_id=batch_id or make_batch_id(imported_at, batch_name),
        source_folder=source_folder.resolve(),
        created_at=imported_at,
        source_fingerprint=source_fingerprint,
        source_photos=list(records),
    )
    active_location: str | None = None
    deferred_location: str | None = None
    current_item: ItemRecord | None = None
    pending_rare = False
    pending_review = False

    def close_item() -> None:
        nonlocal current_item, active_location, deferred_location
        if current_item is not None:
            if not current_item.photos:
                raise ProtocolError("Cannot finalize an item with no photos.")
            batch.items.append(current_item)
            current_item = None
        if deferred_location is not None:
            active_location = deferred_location
            deferred_location = None

    for record in records:
        command = parse_command(record.qr_payload) if record.qr_payload else None
        if command is None:
            if record.qr_payload and record.qr_payload.upper().startswith("CVHS1:"):
                raise ProtocolError(f"Unknown CVHS1 command: {record.qr_payload}")
            if not batch.started:
                batch.warnings.append(f"Excluded ordinary photo before START: {record.original_name}")
                continue
            if batch.ended:
                batch.warnings.append(f"Ignored ordinary photo after END: {record.original_name}")
                continue
            if active_location is None:
                raise ProtocolError(f"Product photo appears before a shelf location: {record.original_name}")
            if current_item is None:
                current_item = ItemRecord(
                    sequence=len(batch.items) + 1,
                    shelf=active_location,
                    rare=pending_rare,
                    review=pending_review,
                )
                pending_rare = False
                pending_review = False
            current_item.photos.append(record)
            continue

        batch.commands.append(replace(record, qr_payload=command.payload))
        if command.kind == CommandKind.BATCH_START:
            if batch.started:
                batch.warnings.append(f"Duplicate START ignored: {record.original_name}")
            elif batch.ended:
                batch.warnings.append(f"START after END ignored: {record.original_name}")
            else:
                batch.started = True
            continue
        if not batch.started:
            raise ProtocolError(f"Command appears before START: {command.payload}")
        if batch.ended:
            batch.warnings.append(f"Ignored command after END: {command.payload}")
            continue
        if command.kind == CommandKind.BATCH_END:
            close_item()
            batch.ended = True
        elif command.kind == CommandKind.ITEM_NEXT:
            if current_item is None:
                batch.warnings.append(f"NEXT encountered while no item was open: {record.original_name}")
                if deferred_location is not None:
                    active_location = deferred_location
                    deferred_location = None
            else:
                close_item()
        elif command.kind == CommandKind.ITEM_CONT:
            batch.warnings.append(f"CONT compatibility no-op: {record.original_name}")
        elif command.kind == CommandKind.LOCATION:
            if current_item is not None:
                deferred_location = command.value
                batch.warnings.append(
                    f"Location {command.value} was scanned inside item {current_item.sequence}; it applies after NEXT."
                )
            else:
                active_location = command.value
        elif command.kind == CommandKind.FLAG_RARE:
            if current_item is not None:
                batch.warnings.append(f"RARE scanned inside item {current_item.sequence}; applies to next item.")
            pending_rare = True
        elif command.kind == CommandKind.FLAG_REVIEW:
            if current_item is not None:
                batch.warnings.append(f"REVIEW scanned inside item {current_item.sequence}; applies to next item.")
            pending_review = True

    if not batch.started:
        raise ProtocolError("START command was not found.")
    if not batch.ended:
        close_item()
        batch.warnings.append("END command was not found; finalized at end of folder.")
    if pending_rare or pending_review:
        batch.warnings.append("Unused item flag remained at the end of the batch.")
    if not batch.items:
        raise ProtocolError("Batch contained no product items.")
    fallback_count = sum(record.timestamp_source == "filesystem_mtime" for record in records)
    if fallback_count:
        batch.warnings.append(f"{fallback_count} photo(s) used filesystem modification time.")
    return batch
