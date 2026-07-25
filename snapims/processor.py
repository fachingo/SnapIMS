from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

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
from snapims.models import BatchRecord, ImportResult, ItemRecord, PhotoRecord, ProcessedPhoto
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


def _photo_payload(photo: PhotoRecord) -> dict[str, Any]:
    return {
        "path": str(photo.path),
        "original_name": photo.original_name,
        "captured_at": photo.captured_at.isoformat(),
        "timestamp_source": photo.timestamp_source,
        "stream_index": photo.stream_index,
        "sha256": photo.sha256,
        "qr_payload": photo.qr_payload,
    }


def _journal_manifest(batch: BatchRecord, artifacts: list[ProcessedPhoto]) -> dict[str, Any]:
    photos = {photo.stream_index: _photo_payload(photo) for photo in batch.source_photos}
    return {
        "batch": {
            "batch_id": batch.batch_id,
            "source_folder": str(batch.source_folder),
            "created_at": batch.created_at.isoformat(),
            "source_fingerprint": batch.source_fingerprint,
            "started": batch.started,
            "ended": batch.ended,
            "warnings": batch.warnings,
            "photos": photos,
            "items": [
                {
                    "sequence": item.sequence,
                    "shelf": item.shelf,
                    "rare": item.rare,
                    "review": item.review,
                    "photo_streams": [photo.stream_index for photo in item.photos],
                }
                for item in batch.items
            ],
            "command_streams": [photo.stream_index for photo in batch.commands],
        },
        "artifacts": [
            {
                "item_id": artifact.item_id,
                "stream_index": artifact.source.stream_index,
                "kind": artifact.kind,
                "proposed_name": artifact.proposed_name,
                "original_copy_path": str(artifact.original_copy_path),
                "processed_path": str(artifact.processed_path) if artifact.processed_path else None,
                "thumbnail_path": str(artifact.thumbnail_path) if artifact.thumbnail_path else None,
                "recognition_path": str(artifact.recognition_path) if artifact.recognition_path else None,
                "photo_order": artifact.photo_order,
            }
            for artifact in artifacts
        ],
    }


def _from_journal_manifest(payload: dict[str, Any]) -> tuple[BatchRecord, list[ProcessedPhoto]]:
    batch_payload = payload["batch"]
    photos = {
        int(index): PhotoRecord(
            path=Path(photo["path"]),
            original_name=str(photo["original_name"]),
            captured_at=datetime.fromisoformat(str(photo["captured_at"])),
            timestamp_source=str(photo["timestamp_source"]),
            stream_index=int(photo["stream_index"]),
            sha256=str(photo.get("sha256") or ""),
            qr_payload=photo.get("qr_payload"),
        )
        for index, photo in batch_payload["photos"].items()
    }
    items = [
        ItemRecord(
            sequence=int(item["sequence"]),
            shelf=str(item["shelf"]),
            rare=bool(item["rare"]),
            review=bool(item["review"]),
            photos=[photos[int(index)] for index in item["photo_streams"]],
        )
        for item in batch_payload["items"]
    ]
    batch = BatchRecord(
        batch_id=str(batch_payload["batch_id"]),
        source_folder=Path(batch_payload["source_folder"]),
        created_at=datetime.fromisoformat(str(batch_payload["created_at"])),
        source_fingerprint=str(batch_payload["source_fingerprint"]),
        started=bool(batch_payload["started"]),
        ended=bool(batch_payload["ended"]),
        items=items,
        commands=[photos[int(index)] for index in batch_payload["command_streams"]],
        source_photos=[photos[index] for index in sorted(photos)],
        warnings=list(batch_payload.get("warnings") or []),
    )
    artifacts = [
        ProcessedPhoto(
            artifact.get("item_id"),
            photos[int(artifact["stream_index"])],
            str(artifact["kind"]),
            str(artifact["proposed_name"]),
            Path(artifact["original_copy_path"]),
            Path(artifact["processed_path"]) if artifact.get("processed_path") else None,
            Path(artifact["thumbnail_path"]) if artifact.get("thumbnail_path") else None,
            Path(artifact["recognition_path"]) if artifact.get("recognition_path") else None,
            int(artifact["photo_order"]) if artifact.get("photo_order") is not None else None,
        )
        for artifact in payload["artifacts"]
    ]
    return batch, artifacts


def _write_import_journal(
    db_file: Path,
    *,
    import_id: str,
    batch: BatchRecord,
    staging_originals: Path,
    staging_processed: Path,
    final_originals: Path,
    final_processed: Path,
    artifacts: list[ProcessedPhoto],
) -> None:
    timestamp = db.now()
    manifest = json.dumps(_journal_manifest(batch, artifacts), separators=(",", ":"))
    with db.transaction(db_file) as connection:
        connection.execute(
            """INSERT INTO import_journal(
                   import_id,source_fingerprint,batch_id,status,source_folder,staging_originals,
                   staging_processed,final_originals,final_processed,manifest_json,created_at,updated_at
               ) VALUES(?,?,?,'STAGED',?,?,?,?,?,?,?,?)
               ON CONFLICT(source_fingerprint) DO UPDATE SET
                   batch_id=excluded.batch_id,status='STAGED',source_folder=excluded.source_folder,
                   staging_originals=excluded.staging_originals,
                   staging_processed=excluded.staging_processed,
                   final_originals=excluded.final_originals,final_processed=excluded.final_processed,
                   manifest_json=excluded.manifest_json,updated_at=excluded.updated_at,error=''""",
            (
                import_id,
                batch.source_fingerprint,
                batch.batch_id,
                str(batch.source_folder),
                str(staging_originals),
                str(staging_processed),
                str(final_originals),
                str(final_processed),
                manifest,
                timestamp,
                timestamp,
            ),
        )


def _update_import_journal(db_file: Path, import_id: str, status: str, error: str = "") -> None:
    with db.transaction(db_file) as connection:
        connection.execute(
            "UPDATE import_journal SET status=?,updated_at=?,completed_at=CASE WHEN ?='COMPLETE' THEN ? ELSE completed_at END,error=? WHERE import_id=?",
            (status, db.now(), status, db.now(), error, import_id),
        )


def reconcile_import_journals(paths: DataPaths) -> dict[str, int]:
    """Repair or quarantine cross-filesystem imports left incomplete by a process interruption."""
    db.initialize(paths.db_file, paths=paths)
    result = {"completed": 0, "resumable": 0, "quarantined": 0, "failed": 0, "orphaned": 0}
    with db.connect(paths.db_file) as connection:
        rows = connection.execute(
            "SELECT * FROM import_journal WHERE status!='COMPLETE' ORDER BY created_at"
        ).fetchall()
    for raw in rows:
        journal = dict(raw)
        import_id = str(journal["import_id"])
        staging_originals = Path(journal["staging_originals"])
        staging_processed = Path(journal["staging_processed"])
        final_originals = Path(journal["final_originals"])
        final_processed = Path(journal["final_processed"])
        staging_any = staging_originals.exists() or staging_processed.exists()
        final_both = final_originals.is_dir() and final_processed.is_dir()
        final_any = final_originals.exists() or final_processed.exists()
        batch_exists = db.get_batch(paths.db_file, str(journal["batch_id"])) is not None
        try:
            if final_both and batch_exists:
                _update_import_journal(paths.db_file, import_id, "COMPLETE")
                result["completed"] += 1
            elif final_both and not batch_exists and not staging_any:
                batch, artifacts = _from_journal_manifest(json.loads(journal["manifest_json"]))
                _insert_batch(paths.db_file, batch, artifacts)
                export_inventory_csv(
                    paths.db_file,
                    batch.batch_id,
                    final_processed / "inventory_work.csv",
                )
                _update_import_journal(paths.db_file, import_id, "COMPLETE")
                result["completed"] += 1
            elif staging_originals.is_dir() and staging_processed.is_dir() and not final_any:
                _update_import_journal(paths.db_file, import_id, "STAGED")
                result["resumable"] += 1
            elif staging_any and final_any:
                _update_import_journal(
                    paths.db_file,
                    import_id,
                    "QUARANTINED",
                    "Both staging and final paths exist; automatic recovery was refused.",
                )
                result["quarantined"] += 1
            elif final_any and not final_both:
                _update_import_journal(
                    paths.db_file,
                    import_id,
                    "QUARANTINED",
                    "Only part of the final media tree exists; operator recovery is required.",
                )
                result["quarantined"] += 1
            else:
                _update_import_journal(
                    paths.db_file,
                    import_id,
                    "FAILED",
                    "Neither staging nor final media exists.",
                )
                result["failed"] += 1
        except Exception as exc:
            _update_import_journal(paths.db_file, import_id, "QUARANTINED", str(exc))
            result["quarantined"] += 1

    with db.connect(paths.db_file) as connection:
        known_batches = {str(row[0]) for row in connection.execute("SELECT batch_id FROM batches")}
        journal_batches = {str(row[0]) for row in connection.execute("SELECT batch_id FROM import_journal")}
    for folder in paths.processed.iterdir():
        if not folder.is_dir() or folder.name.startswith(".staging-"):
            continue
        if folder.name in known_batches or folder.name in journal_batches:
            continue
        originals = paths.originals / folder.name
        timestamp = db.now()
        with db.transaction(paths.db_file) as connection:
            connection.execute(
                """INSERT OR IGNORE INTO import_journal(
                       import_id,source_fingerprint,batch_id,status,source_folder,staging_originals,
                       staging_processed,final_originals,final_processed,manifest_json,
                       created_at,updated_at,error
                   ) VALUES(?,?,?,?,?,?,?,?,?,'{}',?,?,?)""",
                (
                    f"orphan-{folder.name}",
                    f"orphan-{folder.name}",
                    folder.name,
                    "QUARANTINED",
                    "",
                    "",
                    "",
                    str(originals),
                    str(folder),
                    timestamp,
                    timestamp,
                    "Final media exists without a batch or import journal.",
                ),
            )
        result["orphaned"] += 1
    return result


def _insert_batch(
    db_file: Path,
    batch: BatchRecord,
    artifacts: list[ProcessedPhoto],
    *,
    batch_status: str = "IMPORTED",
) -> None:
    timestamp = db.now()
    with db.transaction(db_file) as connection:
        connection.execute(
            """INSERT INTO batches(batch_id,source_fingerprint,source_folder,created_at,imported_at,started,ended,status,item_count,product_photo_count,command_count,warning_count,warnings_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (batch.batch_id, batch.source_fingerprint, str(batch.source_folder), batch.created_at.isoformat(), timestamp, int(batch.started), int(batch.ended), batch_status, len(batch.items), batch.photo_count, len(batch.commands), len(batch.warnings), json.dumps(batch.warnings)),
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
            "VALUES(?, '','READY',?,?,?)",
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
    interrupt_at: str | None = None,
) -> ImportResult:
    paths = (paths or DataPaths.from_root()).ensure()
    db.initialize(paths.db_file, paths=paths)
    reconcile_import_journals(paths)
    db.backup_database(paths, "before-import")
    batch = parse_batch(source_folder, batch_name=batch_name, decoder=decoder, recursive=recursive)
    existing = db.find_batch_by_fingerprint(paths.db_file, batch.source_fingerprint)
    if existing:
        batch_id = str(existing["batch_id"])
        return ImportResult(
            batch_id,
            int(existing["item_count"]),
            int(existing["product_photo_count"]),
            int(existing["command_count"]),
            paths.processed / batch_id,
            paths.processed / batch_id / "inventory_work.csv",
            tuple(json.loads(existing["warnings_json"])),
            True,
        )

    with db.connect(paths.db_file) as connection:
        journal_row = connection.execute(
            "SELECT * FROM import_journal WHERE source_fingerprint=?",
            (batch.source_fingerprint,),
        ).fetchone()
    if journal_row:
        batch.batch_id = str(journal_row["batch_id"])
    else:
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
    completed_before = 0
    if progress_path.exists():
        completed_before = int(json.loads(progress_path.read_text(encoding="utf-8")).get("completed_artifacts", 0))

    for completed, artifact in enumerate(artifacts, start=1):
        original_destination = staging_originals / artifact.original_copy_path.relative_to(
            paths.originals / batch.batch_id
        )
        processed_destination = (
            staging_processed / artifact.processed_path.relative_to(paths.processed / batch.batch_id)
            if artifact.processed_path
            else None
        )
        preview_destination = (
            staging_processed / artifact.thumbnail_path.relative_to(paths.processed / batch.batch_id)
            if artifact.thumbnail_path
            else None
        )
        recognition_destination = (
            staging_processed / artifact.recognition_path.relative_to(paths.processed / batch.batch_id)
            if artifact.recognition_path
            else None
        )
        if completed > completed_before or not original_destination.is_file():
            copy_original(artifact.source.path, original_destination, artifact.source.sha256)
        if processed_destination and not processed_destination.is_file():
            create_safe_jpeg(artifact.source.path, processed_destination)
        if preview_destination and not preview_destination.is_file():
            create_preview(artifact.source.path, preview_destination)
        if recognition_destination and not recognition_destination.is_file():
            create_recognition_derivative(artifact.source.path, recognition_destination)
        temporary = progress_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "batch_id": batch.batch_id,
                    "completed_artifacts": completed,
                    "total_artifacts": len(artifacts),
                }
            ),
            encoding="utf-8",
        )
        os.replace(temporary, progress_path)
        if interrupt_after is not None and completed >= interrupt_after:
            raise ImportInterrupted(f"Simulated interruption after {completed} artifacts")

    write_manifests(staging_processed, batch, artifacts)
    progress_path.unlink(missing_ok=True)
    final_originals = paths.originals / batch.batch_id
    final_processed = paths.processed / batch.batch_id
    if final_originals.exists() or final_processed.exists():
        raise FileExistsError(f"Refusing to overwrite existing batch output: {batch.batch_id}")

    final_artifacts = [
        ProcessedPhoto(
            artifact.item_id,
            artifact.source,
            artifact.kind,
            artifact.proposed_name,
            final_originals
            / artifact.original_copy_path.relative_to(paths.originals / batch.batch_id),
            final_processed
            / artifact.processed_path.relative_to(paths.processed / batch.batch_id)
            if artifact.processed_path
            else None,
            final_processed
            / artifact.thumbnail_path.relative_to(paths.processed / batch.batch_id)
            if artifact.thumbnail_path
            else None,
            final_processed
            / artifact.recognition_path.relative_to(paths.processed / batch.batch_id)
            if artifact.recognition_path
            else None,
            artifact.photo_order,
        )
        for artifact in artifacts
    ]
    import_id = str(journal_row["import_id"]) if journal_row else uuid4().hex
    _write_import_journal(
        paths.db_file,
        import_id=import_id,
        batch=batch,
        staging_originals=staging_originals,
        staging_processed=staging_processed,
        final_originals=final_originals,
        final_processed=final_processed,
        artifacts=final_artifacts,
    )
    if interrupt_at == "after_journal":
        raise ImportInterrupted("Simulated interruption after import journal commit")

    try:
        os.replace(staging_originals, final_originals)
        _update_import_journal(paths.db_file, import_id, "ORIGINALS_FINALIZED")
        if interrupt_at == "after_originals_rename":
            raise ImportInterrupted("Simulated interruption after originals finalization")
        os.replace(staging_processed, final_processed)
        _update_import_journal(paths.db_file, import_id, "MEDIA_FINALIZED")
        if interrupt_at == "after_media_rename":
            raise ImportInterrupted("Simulated interruption after media finalization")
        _insert_batch(paths.db_file, batch, final_artifacts)
        _update_import_journal(paths.db_file, import_id, "DATABASE_COMMITTED")
        if interrupt_at == "after_database_commit":
            raise ImportInterrupted("Simulated interruption after database commit")
        work_csv = export_inventory_csv(
            paths.db_file,
            batch.batch_id,
            final_processed / "inventory_work.csv",
        )
        _update_import_journal(paths.db_file, import_id, "COMPLETE")
    except Exception as exc:
        with db.connect(paths.db_file) as connection:
            status_row = connection.execute(
                "SELECT status FROM import_journal WHERE import_id=?", (import_id,)
            ).fetchone()
        current_status = str(status_row[0]) if status_row else "FAILED"
        if current_status != "COMPLETE":
            _update_import_journal(paths.db_file, import_id, current_status, str(exc))
        raise

    db.remember_folder(paths.db_file, source_folder)
    return ImportResult(
        batch.batch_id,
        len(batch.items),
        batch.photo_count,
        len(batch.commands),
        final_processed,
        work_csv,
        tuple(batch.warnings),
    )
