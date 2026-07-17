from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from snapims.config import DataPaths
from snapims.models import PhotoRecord

BASE_TIME = datetime(2026, 7, 16, 12, 0, 0)


def create_jpeg(
    path: Path,
    *,
    captured_at: datetime | None = None,
    color: str = "white",
    gps: bool = False,
) -> Path:
    image = Image.new("RGB", (120, 160), color)
    exif = Image.Exif()
    if captured_at is not None:
        exif[36867] = captured_at.strftime("%Y:%m:%d %H:%M:%S")
        exif[37521] = f"{captured_at.microsecond:06d}"
    if gps:
        exif[34853] = {1: "N", 2: ((53, 1), (32, 1), (0, 1)), 3: "W", 4: ((113, 1), (29, 1), (0, 1))}
    image.save(path, exif=exif)
    return path


def set_mtime(path: Path, value: datetime) -> None:
    epoch = value.timestamp()
    os.utime(path, (epoch, epoch))


def record(index: int, name: str, payload: str | None = None) -> PhotoRecord:
    return PhotoRecord(
        path=Path(name), captured_at=BASE_TIME + timedelta(seconds=index),
        timestamp_source="filename", original_name=name, sequence_hint=index,
        qr_payload=payload, stream_index=index + 1, sha256=f"hash-{index}",
    )


@pytest.fixture
def data_paths(tmp_path: Path) -> DataPaths:
    return DataPaths.from_root(tmp_path / "data").ensure()
