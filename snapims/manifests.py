from __future__ import annotations

import csv
import json
from pathlib import Path

from snapims.models import BatchRecord, ProcessedPhoto


def item_id(batch_id: str, shelf: str, sequence: int) -> str:
    return f"{batch_id}-{shelf}-{sequence:03d}"


def photo_name(batch_id: str, shelf: str, sequence: int, order: int) -> str:
    suffix = "F" if order == 1 else f"{order:02d}"
    return f"{item_id(batch_id, shelf, sequence)}-{suffix}.jpg"


def write_manifests(root: Path, batch: BatchRecord, artifacts: list[ProcessedPhoto]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "batch_id": batch.batch_id,
        "source_fingerprint": batch.source_fingerprint,
        "source_folder": str(batch.source_folder),
        "item_count": len(batch.items),
        "product_photo_count": batch.photo_count,
        "command_count": len(batch.commands),
        "warnings": batch.warnings,
    }
    (root / "batch_manifest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with (root / "image_manifest.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["item_id", "kind", "stream_index", "photo_order", "name"])
        writer.writeheader()
        for artifact in artifacts:
            writer.writerow({
                "item_id": artifact.item_id or "",
                "kind": artifact.kind,
                "stream_index": artifact.source.stream_index,
                "photo_order": artifact.photo_order or "",
                "name": artifact.proposed_name,
            })
    (root / "warnings.txt").write_text("\n".join(batch.warnings) + ("\n" if batch.warnings else ""), encoding="utf-8")
