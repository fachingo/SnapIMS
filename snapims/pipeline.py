from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from snapims.import_repair import (
    apply_repair_plan,
    normalize_repair_plan,
    repair_action_count,
    repaired_fingerprint,
)
from snapims.import_location import (
    location_assignment_fingerprint,
    location_assignment_warning,
    normalize_manual_location,
)
from snapims.interpreter import ProtocolError, interpret_stream
from snapims.models import BatchRecord, PhotoRecord
from snapims.qr import QRDecodeError, UNREADABLE_PHOTO_PAYLOAD, decode_snapims_qr
from snapims.sorter import load_sorted_photos

QRDecoder = Callable[[Path], str | None]


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_commands(
    records: list[PhotoRecord], *, decoder: QRDecoder = decode_snapims_qr
) -> list[PhotoRecord]:
    scanned: list[PhotoRecord] = []
    for record in records:
        digest = sha256_file(record.path)
        try:
            payload = decoder(record.path)
        except QRDecodeError:
            # Keep the physical source file but route its exact position to the
            # repair menu instead of aborting the entire folder preview.
            payload = UNREADABLE_PHOTO_PAYLOAD
        scanned.append(replace(record, qr_payload=payload, sha256=digest))
    return scanned


def scan_source_photos(
    source_folder: Path,
    *,
    decoder: QRDecoder = decode_snapims_qr,
    recursive: bool = False,
) -> list[PhotoRecord]:
    return scan_commands(load_sorted_photos(source_folder, recursive=recursive), decoder=decoder)


def source_fingerprint(records: list[PhotoRecord]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(f"{record.stream_index}\0{record.sha256}\0{record.original_name}\n".encode())
    return digest.hexdigest()


def parse_batch(
    source_folder: Path,
    *,
    batch_name: str | None = None,
    imported_at: datetime | None = None,
    batch_id: str | None = None,
    decoder: QRDecoder = decode_snapims_qr,
    recursive: bool = False,
    repair_plan: str | dict[str, object] | None = None,
    manual_location: str = "",
    override_locations: bool = False,
) -> BatchRecord:
    manual_location, override_locations = normalize_manual_location(
        manual_location,
        override_locations,
    )
    scanned = scan_source_photos(source_folder, decoder=decoder, recursive=recursive)
    normalized_plan = normalize_repair_plan(repair_plan)
    effective, physical, normalized_plan = apply_repair_plan(scanned, normalized_plan)
    fingerprint = repaired_fingerprint(source_fingerprint(scanned), normalized_plan)
    fingerprint = location_assignment_fingerprint(
        fingerprint,
        manual_location,
        override_locations,
    )
    try:
        batch = interpret_stream(
            effective,
            source_folder=source_folder,
            batch_name=batch_name,
            imported_at=imported_at,
            batch_id=batch_id,
            source_fingerprint=fingerprint,
            source_records=physical,
            manual_location=manual_location,
            override_locations=override_locations,
        )
    except ProtocolError as exc:
        exc.source_records = physical
        exc.repair_plan = normalized_plan
        raise
    action_count = repair_action_count(normalized_plan)
    if action_count:
        batch.warnings.insert(
            0,
            f"Manual import repair applied: {action_count} operator command or photo correction(s).",
        )
    assignment_warning = location_assignment_warning(
        manual_location,
        override_locations,
    )
    if assignment_warning:
        batch.warnings.insert(0, assignment_warning)
    batch.capture_source = (
        "DESKTOP_IMPORT_QR"
        if batch.commands
        else "DESKTOP_IMPORT_MANUAL"
    )
    return batch
