from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from snapims.interpreter import interpret_stream
from snapims.models import BatchRecord, PhotoRecord
from snapims.qr import decode_snapims_qr
from snapims.sorter import load_sorted_photos

QRDecoder = Callable[[Path], str | None]


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_commands(records: list[PhotoRecord], *, decoder: QRDecoder = decode_snapims_qr) -> list[PhotoRecord]:
    return [replace(record, qr_payload=decoder(record.path), sha256=sha256_file(record.path)) for record in records]


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
) -> BatchRecord:
    ordered = load_sorted_photos(source_folder, recursive=recursive)
    scanned = scan_commands(ordered, decoder=decoder)
    fingerprint = source_fingerprint(scanned)
    return interpret_stream(
        scanned,
        source_folder=source_folder,
        batch_name=batch_name,
        imported_at=imported_at,
        batch_id=batch_id,
        source_fingerprint=fingerprint,
    )
