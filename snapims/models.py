from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(slots=True)
class PhotoRecord:
    path: Path
    original_name: str
    captured_at: datetime
    timestamp_source: str
    stream_index: int
    sha256: str = ""
    qr_payload: str | None = None


@dataclass(slots=True)
class ItemRecord:
    sequence: int
    shelf: str
    rare: bool = False
    review: bool = False
    photos: list[PhotoRecord] = field(default_factory=list)


@dataclass(slots=True)
class BatchRecord:
    batch_id: str
    source_folder: Path
    created_at: datetime
    source_fingerprint: str = ""
    started: bool = False
    ended: bool = False
    items: list[ItemRecord] = field(default_factory=list)
    commands: list[PhotoRecord] = field(default_factory=list)
    source_photos: list[PhotoRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def photo_count(self) -> int:
        return sum(len(item.photos) for item in self.items)


@dataclass(frozen=True, slots=True)
class ProcessedPhoto:
    item_id: str | None
    source: PhotoRecord
    kind: str
    proposed_name: str
    original_copy_path: Path
    processed_path: Path | None = None
    thumbnail_path: Path | None = None
    photo_order: int | None = None


@dataclass(frozen=True, slots=True)
class ImportResult:
    batch_id: str
    item_count: int
    product_photo_count: int
    command_count: int
    output_folder: Path
    work_csv: Path
    warnings: tuple[str, ...]
    duplicate: bool = False
