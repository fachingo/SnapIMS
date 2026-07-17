from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

TimestampSource = Literal[
    "exif_original",
    "exif_digitized",
    "exif_datetime",
    "filename",
    "filesystem_mtime",
]


@dataclass(frozen=True, slots=True)
class PhotoRecord:
    path: Path
    captured_at: datetime
    timestamp_source: TimestampSource
    original_name: str
    sequence_hint: int | None = None
    qr_payload: str | None = None
    stream_index: int = 0
    sha256: str | None = None

    @property
    def is_command(self) -> bool:
        return self.qr_payload is not None


@dataclass(slots=True)
class ItemRecord:
    sequence: int
    shelf: str
    photos: list[PhotoRecord] = field(default_factory=list)
    rare: bool = False
    review: bool = False

    @property
    def front(self) -> PhotoRecord:
        if not self.photos:
            raise ValueError("Item has no product photographs.")
        return self.photos[0]


@dataclass(slots=True)
class BatchRecord:
    batch_id: str
    source_folder: Path
    created_at: datetime
    source_fingerprint: str = ""
    items: list[ItemRecord] = field(default_factory=list)
    commands: list[PhotoRecord] = field(default_factory=list)
    unknown_commands: list[PhotoRecord] = field(default_factory=list)
    source_photos: list[PhotoRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    started: bool = False
    ended: bool = False

    @property
    def photo_count(self) -> int:
        return sum(len(item.photos) for item in self.items)


@dataclass(frozen=True, slots=True)
class ProcessedPhoto:
    item_id: str | None
    source: PhotoRecord
    kind: Literal["product", "command", "excluded"]
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
