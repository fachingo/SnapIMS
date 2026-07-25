from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from snapims import db
from snapims.config import DataPaths
from snapims.images import (
    copy_original,
    create_preview,
    create_recognition_derivative,
    create_safe_jpeg,
    is_nearly_blank,
)
from snapims.interpreter import make_batch_id
from snapims.inventory import export_inventory_csv
from snapims.manifests import item_id, photo_name, write_manifests
from snapims.models import BatchRecord, ImportResult, ProcessedPhoto
from snapims.pipeline import QRDecoder, parse_batch
from snapims.protocol import parse_command
from snapims.qr import decode_snapims_qr


class ImportInterrupted(RuntimeError):
    pass


def _unique_batch_id(paths: DataPaths, created_at: datetime, batch_name: str | None) -> str:
    candidate = created_at
    for _ in range(120):
        batch_id = make_batch_id(candidate, batch_name)
        if not (paths.processed / batch_id).exists() and not (paths.originals / batch_id).exists():
            return batch_id
        candidate += timedelta(seconds=1)
    raise FileExistsError("Could not allocate a collision-free Batch ID within two minutes.")


def _artifact_plan(batch: BatchRecord, paths: DataPaths) -> list[ProcessedPhoto]:
    original_root = paths.originals / batch.batch_id
    processed_root = paths.processed / batch.batch_id
    products: dict[int, tuple[str, int, str]] = {}
    for item in batch.items:
        identifier = item_id(batch.batch_id, item.shelf, item.sequence)
        for order, photo in enumerate(item.photos, start=1):
            products[photo.stream_index] = (identifier, order, photo_name(batch.batch_id, item.shelf, item.sequence, order))
    command_streams = {photo.stream_index for photo in batch.commands}
    artifacts: list[ProcessedPhoto] = []
    for photo in sorted(batch.source_photos, key=lambda record: record.stream_index):
        original_copy = original_root / f"{photo.stream_index:04d}-{photo.original_name}"
        if photo.stream_index in products:
            identifier, order, name = products[photo.stream_index]
            artifacts.append(ProcessedPhoto(
                identifier, photo, "product", name, original_copy,
                processed_root / "images" / name,
                processed_root / "previews" / name,
                processed_root / "recognition" / name,
                order,
            ))
        elif photo.stream_index in command_streams:
            payload = (photo.qr_payload or "UNKNOWN").replace(":", "-")
            name = f"{photo.stream_index:04d}-{payload}.jpg"
            artifacts.append(ProcessedPhoto(None, photo, "command", name, original_copy, processed_root / "commands" / name))
        else:
            artifacts.append(ProcessedPhoto(None, photo, "excluded", "EXCLUDED", original_copy))
    return artifacts


def _insert_batch(db_file: Path, batch: BatchRecord, artifacts: list[ProcessedPhoto]) -> None:
    timestamp = db.now()
    with db.transaction(db_file) as connection:
        connection.execute(
            """INSERT INTO batches(batch_id,source_fingerprint,source_folder,created_at,imported_at,started,ended,status,item_count,product_photo_count,command_count,warning_count,warnings_json)
               VALUES(?,?,?,?,?,?,?,'IMPORTED',?,?,?,?,?)""",
            (batch.batch_id, batch.source_fingerprint, str(batch.source_folder), batch.created_at.isoformat(), timestamp, int(batch.started), int(batch.ended), len(batch.items), batch.photo_count, len(batch.commands), len(batch.warnings), json.dumps(batch.warnings)),
        )
        for item in batch.items:
            identifier = item_id(batch.batch_id, item.shelf, item.sequence)
            connection.execute(
                """INSERT INTO items(item_id,sku,batch_id,sequence,shelf,rare,review,pool_mode,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (identifier, identifier, batch.batch_id, item.sequence, item.shelf, int(item.rare), int(item.review), "UNIQUE" if item.rare else "POOLED", timestamp, timestamp),
            )
            connection.execute("INSERT INTO shopify_sync(item_id) VALUES(?)", (identifier,))
            connection.execute(
                """INSERT INTO inventory_events(item_id,batch_id,occurred_at,event_type,to_location,quantity_delta,source,notes)
                   VALUES(?,?,?,'ITEM_INTAKE',?,1,'QR_BATCH',?)""",
                (identifier, batch.batch_id, timestamp, item.shelf, f"Imported as sequence {item.sequence}"),
            )
        photo_ids: dict[int, int] = {}
        for artifact in artifacts:
            cursor = connection.execute(
                """INSERT INTO photos(
                       batch_id,item_id,kind,stream_index,photo_order,original_name,captured_at,
                       timestamp_source,sha256,qr_payload,source_path,original_copy_path,
                       proposed_name,processed_path,thumbnail_path,preview_path,recognition_path,
                       original_bytes,preview_bytes,recognition_bytes,ai_eligible,image_role
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    batch.batch_id, artifact.item_id, artifact.kind, artifact.source.stream_index,
                    artifact.photo_order, artifact.source.original_name,
                    artifact.source.captured_at.isoformat(), artifact.source.timestamp_source,
                    artifact.source.sha256, artifact.source.qr_payload, str(artifact.source.path),
                    str(artifact.original_copy_path), artifact.proposed_name,
                    str(artifact.processed_path) if artifact.processed_path else None,
                    str(artifact.thumbnail_path) if artifact.thumbnail_path else None,
                    str(artifact.thumbnail_path) if artifact.thumbnail_path else None,
                    str(artifact.recognition_path) if artifact.recognition_path else None,
                    artifact.original_copy_path.stat().st_size if artifact.original_copy_path.is_file() else 0,
                    artifact.thumbnail_path.stat().st_size if artifact.thumbnail_path and artifact.thumbnail_path.is_file() else 0,
                    artifact.recognition_path.stat().st_size if artifact.recognition_path and artifact.recognition_path.is_file() else 0,
                    int(artifact.kind == "product" and artifact.recognition_path is not None and not is_nearly_blank(artifact.recognition_path)),
                    ({1: "front", 2: "spine", 3: "back", 4: "cassette"}.get(artifact.photo_order or 0, "support") if artifact.kind == "product" else artifact.kind),
                ),
            )
            photo_ids[artifact.source.stream_index] = int(cursor.lastrowid)
        for command_photo in batch.commands:
            command = parse_command(command_photo.qr_payload or "")
            if command:
                connection.execute(
                    """INSERT INTO command_events(batch_id,stream_index,occurred_at,payload,command_kind,command_value,source_photo_id)
                       VALUES(?,?,?,?,?,?,?)""",
                    (batch.batch_id, command_photo.stream_index, command_photo.captured_at.isoformat(), command.payload, command.kind.value, command.value, photo_ids.get(command_photo.stream_index)),
                )
        connection.execute(
            "INSERT INTO recognition_jobs(batch_id,provider,status,total,started_at,updated_at) "
            "VALUES(?, 'mock','READY',?,?,?)",
            (batch.batch_id, len(batch.items), timestamp, timestamp),
        )


def process_batch(
    source_folder: Path,
    *,
    paths: DataPaths | None = None,
    batch_name: str | None = None,
    decoder: QRDecoder = decode_snapims_qr,
    recursive: bool = False,
    interrupt_after: int | None = None,
) -> ImportResult:
    paths = (paths or DataPaths.from_root()).ensure()
    db.initialize(paths.db_file, paths=paths)
    db.backup_database(paths, "before-import")
    batch = parse_batch(source_folder, batch_name=batch_name, decoder=decoder, recursive=recursive)
    existing = db.find_batch_by_fingerprint(paths.db_file, batch.source_fingerprint)
    if existing:
        batch_id = str(existing["batch_id"])
        return ImportResult(batch_id, int(existing["item_count"]), int(existing["product_photo_count"]), int(existing["command_count"]), paths.processed / batch_id, paths.processed / batch_id / "inventory_work.csv", tuple(json.loads(existing["warnings_json"])), True)
    batch.batch_id = _unique_batch_id(paths, batch.created_at, batch_name)
    artifacts = _artifact_plan(batch, paths)
    suffix = batch.source_fingerprint[:16]
    staging_originals = paths.originals / f".staging-{suffix}"
    staging_processed = paths.processed / f".staging-{suffix}"
    progress_path = staging_processed / "progress.json"
    if progress_path.exists():
        try:
            batch.batch_id = json.loads(progress_path.read_text(encoding="utf-8"))["batch_id"]
            artifacts = _artifact_plan(batch, paths)
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Invalid resume marker: {progress_path}") from exc
    staging_originals.mkdir(parents=True, exist_ok=True)
    staging_processed.mkdir(parents=True, exist_ok=True)
    for completed, artifact in enumerate(artifacts, start=1):
        original_destination = staging_originals / artifact.original_copy_path.relative_to(paths.originals / batch.batch_id)
        copy_original(artifact.source.path, original_destination, artifact.source.sha256)
        if artifact.processed_path:
            processed_destination = staging_processed / artifact.processed_path.relative_to(paths.processed / batch.batch_id)
            create_safe_jpeg(artifact.source.path, processed_destination)
        if artifact.thumbnail_path:
            thumb_destination = staging_processed / artifact.thumbnail_path.relative_to(paths.processed / batch.batch_id)
            create_preview(artifact.source.path, thumb_destination)
        if artifact.recognition_path:
            recognition_destination = staging_processed / artifact.recognition_path.relative_to(paths.processed / batch.batch_id)
            create_recognition_derivative(artifact.source.path, recognition_destination)
        temporary = progress_path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"batch_id": batch.batch_id, "completed_artifacts": completed, "total_artifacts": len(artifacts)}), encoding="utf-8")
        os.replace(temporary, progress_path)
        if interrupt_after is not None and completed >= interrupt_after:
            raise ImportInterrupted(f"Simulated interruption after {completed} artifacts")
    write_manifests(staging_processed, batch, artifacts)
    progress_path.unlink(missing_ok=True)
    final_originals = paths.originals / batch.batch_id
    final_processed = paths.processed / batch.batch_id
    if final_originals.exists() or final_processed.exists():
        raise FileExistsError(f"Refusing to overwrite existing batch output: {batch.batch_id}")
    os.replace(staging_originals, final_originals)
    os.replace(staging_processed, final_processed)
    # Rewrite artifact paths to final locations before database insert.
    final_artifacts: list[ProcessedPhoto] = []
    for artifact in artifacts:
        final_artifacts.append(ProcessedPhoto(
            artifact.item_id, artifact.source, artifact.kind, artifact.proposed_name,
            final_originals / artifact.original_copy_path.relative_to(paths.originals / batch.batch_id),
            final_processed / artifact.processed_path.relative_to(paths.processed / batch.batch_id) if artifact.processed_path else None,
            final_processed / artifact.thumbnail_path.relative_to(paths.processed / batch.batch_id) if artifact.thumbnail_path else None,
            final_processed / artifact.recognition_path.relative_to(paths.processed / batch.batch_id) if artifact.recognition_path else None,
            artifact.photo_order,
        ))
    _insert_batch(paths.db_file, batch, final_artifacts)
    work_csv = export_inventory_csv(paths.db_file, batch.batch_id, final_processed / "inventory_work.csv")
    db.remember_folder(paths.db_file, source_folder)
    return ImportResult(batch.batch_id, len(batch.items), batch.photo_count, len(batch.commands), final_processed, work_csv, tuple(batch.warnings))
