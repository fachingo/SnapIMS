from __future__ import annotations

import csv
import json
from pathlib import Path

from snapims.models import BatchRecord, ProcessedPhoto


def item_id(batch_id: str, shelf: str, sequence: int) -> str:
    return f"{batch_id}-{shelf}-{sequence:03d}"


def photo_name(batch_id: str, shelf: str, sequence: int, photo_order: int) -> str:
    role = "F" if photo_order == 1 else f"{photo_order:02d}"
    return f"{item_id(batch_id, shelf, sequence)}-{role}.jpg"


def batch_to_dict(batch: BatchRecord, artifacts: list[ProcessedPhoto]) -> dict[str, object]:
    by_item: dict[str, list[ProcessedPhoto]] = {}
    for artifact in artifacts:
        if artifact.item_id:
            by_item.setdefault(artifact.item_id, []).append(artifact)

    items: list[dict[str, object]] = []
    for item in batch.items:
        iid = item_id(batch.batch_id, item.shelf, item.sequence)
        photos = sorted(by_item.get(iid, []), key=lambda p: p.photo_order or 0)
        items.append(
            {
                "item_id": iid,
                "sku": iid,
                "sequence": item.sequence,
                "shelf": item.shelf,
                "rare": item.rare,
                "review": item.review,
                "photos": [
                    {
                        "order": photo.photo_order,
                        "original_name": photo.source.original_name,
                        "captured_at": photo.source.captured_at.isoformat(),
                        "timestamp_source": photo.source.timestamp_source,
                        "sha256": photo.source.sha256,
                        "proposed_name": photo.proposed_name,
                        "original_copy_path": str(photo.original_copy_path),
                        "processed_path": str(photo.processed_path),
                        "thumbnail_path": str(photo.thumbnail_path),
                    }
                    for photo in photos
                ],
            }
        )

    return {
        "schema_version": 1,
        "batch_id": batch.batch_id,
        "source_folder": str(batch.source_folder),
        "source_fingerprint": batch.source_fingerprint,
        "created_at": batch.created_at.isoformat(),
        "started": batch.started,
        "ended": batch.ended,
        "warnings": batch.warnings,
        "items": items,
        "commands": [
            {
                "stream_index": command.stream_index,
                "original_name": command.original_name,
                "captured_at": command.captured_at.isoformat(),
                "timestamp_source": command.timestamp_source,
                "qr_payload": command.qr_payload,
                "sha256": command.sha256,
            }
            for command in batch.commands
        ],
        "excluded_photos": [
            {
                "stream_index": artifact.source.stream_index,
                "original_name": artifact.source.original_name,
                "captured_at": artifact.source.captured_at.isoformat(),
                "timestamp_source": artifact.source.timestamp_source,
                "sha256": artifact.source.sha256,
                "original_copy_path": str(artifact.original_copy_path),
            }
            for artifact in artifacts
            if artifact.kind == "excluded"
        ],
    }


def write_manifests(output_folder: Path, batch: BatchRecord, artifacts: list[ProcessedPhoto]) -> None:
    output_folder.mkdir(parents=True, exist_ok=True)
    manifest = batch_to_dict(batch, artifacts)
    (output_folder / "batch_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    product_artifacts = [artifact for artifact in artifacts if artifact.kind == "product"]
    with (output_folder / "image_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "batch_id", "item_id", "shelf", "item_sequence", "photo_order",
            "original_name", "captured_at", "timestamp_source", "sha256",
            "proposed_name", "original_copy_path", "processed_path", "thumbnail_path",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        item_lookup = {
            item_id(batch.batch_id, item.shelf, item.sequence): item for item in batch.items
        }
        for artifact in product_artifacts:
            item = item_lookup[artifact.item_id or ""]
            writer.writerow(
                {
                    "batch_id": batch.batch_id,
                    "item_id": artifact.item_id,
                    "shelf": item.shelf,
                    "item_sequence": item.sequence,
                    "photo_order": artifact.photo_order,
                    "original_name": artifact.source.original_name,
                    "captured_at": artifact.source.captured_at.isoformat(),
                    "timestamp_source": artifact.source.timestamp_source,
                    "sha256": artifact.source.sha256,
                    "proposed_name": artifact.proposed_name,
                    "original_copy_path": artifact.original_copy_path,
                    "processed_path": artifact.processed_path,
                    "thumbnail_path": artifact.thumbnail_path,
                }
            )

    with (output_folder / "commands.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "stream_index", "original_name", "captured_at", "timestamp_source",
            "qr_payload", "sha256", "source_path", "original_copy_path",
            "command_copy_path",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        command_artifacts = {
            artifact.source.stream_index: artifact
            for artifact in artifacts
            if artifact.kind == "command"
        }
        for command in batch.commands:
            artifact = command_artifacts[command.stream_index]
            writer.writerow(
                {
                    "stream_index": command.stream_index,
                    "original_name": command.original_name,
                    "captured_at": command.captured_at.isoformat(),
                    "timestamp_source": command.timestamp_source,
                    "qr_payload": command.qr_payload,
                    "sha256": command.sha256,
                    "source_path": command.path,
                    "original_copy_path": artifact.original_copy_path,
                    "command_copy_path": artifact.processed_path,
                }
            )
    (output_folder / "warnings.txt").write_text(
        "\n".join(batch.warnings) + ("\n" if batch.warnings else ""), encoding="utf-8"
    )
