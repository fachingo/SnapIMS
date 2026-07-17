from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from snapims import db
from snapims.config import DataPaths
from snapims.images import copy_original, create_safe_jpeg
from snapims.interpreter import make_batch_id
from snapims.inventory import export_inventory_csv
from snapims.manifests import item_id, photo_name, write_manifests
from snapims.models import BatchRecord, ImportResult, ProcessedPhoto
from snapims.pipeline import QRDecoder, parse_batch
from snapims.qr import decode_snapims_qr

LOGGER = logging.getLogger("snapims.processor")


class ImportInterrupted(RuntimeError):
    """Testable interruption used to verify resume behavior."""


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created).astimezone().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(paths: DataPaths) -> None:
    paths.ensure()
    root = logging.getLogger("snapims")
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    handler = logging.FileHandler(paths.logs / "snapims.log", encoding="utf-8")
    handler.setFormatter(JsonLogFormatter())
    root.addHandler(handler)


def _existing_manifest(paths: DataPaths, fingerprint: str) -> tuple[str, dict] | None:
    if not paths.processed.exists():
        return None
    for manifest_path in sorted(paths.processed.glob("*/batch_manifest.json")):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("source_fingerprint") == fingerprint:
            return str(payload["batch_id"]), payload
    return None


def _unique_batch_id(paths: DataPaths, created_at: datetime, batch_name: str | None) -> str:
    candidate_time = created_at
    for _ in range(120):
        candidate = make_batch_id(candidate_time, batch_name)
        if not (paths.processed / candidate).exists() and not (paths.originals / candidate).exists():
            return candidate
        candidate_time += timedelta(seconds=1)
    raise FileExistsError("Could not allocate a collision-free Batch ID within two minutes.")


def _artifact_plan(batch: BatchRecord, paths: DataPaths) -> list[ProcessedPhoto]:
    original_root = paths.originals / batch.batch_id
    processed_root = paths.processed / batch.batch_id
    product_by_stream: dict[int, tuple[str, int, str]] = {}
    for item in batch.items:
        iid = item_id(batch.batch_id, item.shelf, item.sequence)
        for order, photo in enumerate(item.photos, start=1):
            product_by_stream[photo.stream_index] = (
                iid, order, photo_name(batch.batch_id, item.shelf, item.sequence, order)
            )

    command_streams = {photo.stream_index for photo in batch.commands}
    command_streams |= {photo.stream_index for photo in batch.unknown_commands}
    records = sorted(batch.source_photos, key=lambda photo: photo.stream_index)
    artifacts: list[ProcessedPhoto] = []
    for photo in records:
        original_name = f"{photo.stream_index:04d}-{photo.original_name}"
        original_copy = original_root / original_name
        product = product_by_stream.get(photo.stream_index)
        if product:
            iid, order, proposed_name = product
            artifacts.append(
                ProcessedPhoto(
                    item_id=iid,
                    source=photo,
                    kind="product",
                    proposed_name=proposed_name,
                    original_copy_path=original_copy,
                    processed_path=processed_root / "images" / proposed_name,
                    thumbnail_path=processed_root / "thumbnails" / proposed_name,
                    photo_order=order,
                )
            )
        elif photo.stream_index in command_streams:
            payload = (photo.qr_payload or "UNKNOWN").replace(":", "-")
            command_name = f"{photo.stream_index:04d}-{payload}.jpg"
            artifacts.append(
                ProcessedPhoto(
                    item_id=None,
                    source=photo,
                    kind="command",
                    proposed_name=command_name,
                    original_copy_path=original_copy,
                    processed_path=processed_root / "commands" / command_name,
                )
            )
        else:
            artifacts.append(
                ProcessedPhoto(
                    item_id=None,
                    source=photo,
                    kind="excluded",
                    proposed_name="EXCLUDED",
                    original_copy_path=original_copy,
                )
            )
    return artifacts


def _stage_path(final: Path, staging_root: Path, final_root: Path) -> Path:
    return staging_root / final.relative_to(final_root)


def _write_progress(path: Path, batch_id: str, completed: int, total: int) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {"batch_id": batch_id, "completed_artifacts": completed, "total_artifacts": total},
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


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
    configure_logging(paths)
    db.initialize(paths.db_file)
    db.backup_database(paths, "before-import")
    LOGGER.info("Import preview started source=%s", source_folder)

    batch = parse_batch(
        source_folder,
        batch_name=batch_name,
        decoder=decoder,
        recursive=recursive,
    )
    existing_db = db.find_batch_by_fingerprint(paths.db_file, batch.source_fingerprint)
    if existing_db:
        batch_id_value = existing_db["batch_id"]
        output = paths.processed / batch_id_value
        LOGGER.info("Duplicate import skipped batch=%s", batch_id_value)
        return ImportResult(
            batch_id=batch_id_value,
            item_count=int(existing_db["item_count"]),
            product_photo_count=int(existing_db["product_photo_count"]),
            command_count=int(existing_db["command_count"]),
            output_folder=output,
            work_csv=output / "inventory_work.csv",
            warnings=tuple(json.loads(existing_db["warnings_json"])),
            duplicate=True,
        )

    recovered_manifest = _existing_manifest(paths, batch.source_fingerprint)
    if recovered_manifest:
        batch.batch_id = recovered_manifest[0]
        artifacts = _artifact_plan(batch, paths)
        missing = [
            str(artifact.processed_path)
            for artifact in artifacts
            if artifact.processed_path and not artifact.processed_path.exists()
        ]
        if missing:
            raise FileNotFoundError(
                "A matching prior manifest exists but processed files are incomplete: " + missing[0]
            )
        db.insert_batch(paths.db_file, batch, artifacts)
        work_csv = export_inventory_csv(paths.db_file, batch.batch_id, paths.processed / batch.batch_id / "inventory_work.csv")
        return ImportResult(
            batch_id=batch.batch_id, item_count=len(batch.items),
            product_photo_count=batch.photo_count, command_count=len(batch.commands),
            output_folder=paths.processed / batch.batch_id, work_csv=work_csv,
            warnings=tuple(batch.warnings), duplicate=False,
        )

    suffix = batch.source_fingerprint[:16]
    staging_originals = paths.originals / f".staging-{suffix}"
    staging_processed = paths.processed / f".staging-{suffix}"
    progress_path = staging_processed / "progress.json"
    if progress_path.exists():
        try:
            batch.batch_id = str(json.loads(progress_path.read_text(encoding="utf-8"))["batch_id"])
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Invalid resume marker: {progress_path}") from exc
    else:
        batch.batch_id = _unique_batch_id(paths, batch.created_at, batch_name)
    artifacts = _artifact_plan(batch, paths)
    staging_originals.mkdir(parents=True, exist_ok=True)
    staging_processed.mkdir(parents=True, exist_ok=True)

    try:
        for completed, artifact in enumerate(artifacts, start=1):
            original_destination = _stage_path(
                artifact.original_copy_path, staging_originals, paths.originals / batch.batch_id
            )
            copy_original(artifact.source.path, original_destination, artifact.source.sha256)
            if artifact.processed_path:
                processed_destination = _stage_path(
                    artifact.processed_path, staging_processed, paths.processed / batch.batch_id
                )
                create_safe_jpeg(artifact.source.path, processed_destination)
            if artifact.thumbnail_path:
                thumbnail_destination = _stage_path(
                    artifact.thumbnail_path, staging_processed, paths.processed / batch.batch_id
                )
                create_safe_jpeg(artifact.source.path, thumbnail_destination, max_dimension=640)
            _write_progress(progress_path, batch.batch_id, completed, len(artifacts))
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
        db.insert_batch(paths.db_file, batch, artifacts)
        work_csv = export_inventory_csv(
            paths.db_file, batch.batch_id, final_processed / "inventory_work.csv"
        )
    except ImportInterrupted:
        LOGGER.warning("Import interrupted; staging retained for resume batch=%s", batch.batch_id)
        raise
    except Exception:
        LOGGER.exception("Import failed source=%s", source_folder)
        raise

    LOGGER.info("Import completed batch=%s items=%d", batch.batch_id, len(batch.items))
    return ImportResult(
        batch_id=batch.batch_id,
        item_count=len(batch.items),
        product_photo_count=batch.photo_count,
        command_count=len(batch.commands),
        output_folder=final_processed,
        work_csv=work_csv,
        warnings=tuple(batch.warnings),
    )
