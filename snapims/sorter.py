from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from PIL import Image

from snapims.models import PhotoRecord

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
_FILENAME_TIME = re.compile(r"(20\d{6})[_-]?(\d{6})(\d{0,6})")


def _capture_time(path: Path) -> tuple[datetime, str]:
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            for tag in (36867, 36868, 306):
                raw = exif.get(tag)
                if raw:
                    return datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S"), "exif"
    except (OSError, ValueError):
        pass
    match = _FILENAME_TIME.search(path.stem)
    if match:
        base = datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S")
        micro = (match.group(3) + "000000")[:6]
        return base.replace(microsecond=int(micro)), "filename"
    return datetime.fromtimestamp(path.stat().st_mtime), "filesystem_mtime"


def load_sorted_photos(source_folder: Path, *, recursive: bool = False) -> list[PhotoRecord]:
    if not source_folder.is_dir():
        raise FileNotFoundError(f"Folder not available: {source_folder}")
    iterator = source_folder.rglob("*") if recursive else source_folder.iterdir()
    paths = [path for path in iterator if path.is_file() and path.suffix.casefold() in SUPPORTED_EXTENSIONS]
    records: list[tuple[datetime, str, Path]] = []
    for path in paths:
        captured, source = _capture_time(path)
        records.append((captured, source, path))
    records.sort(key=lambda row: (row[0], row[2].name.casefold()))
    return [
        PhotoRecord(path=path, original_name=path.name, captured_at=captured, timestamp_source=source, stream_index=index)
        for index, (captured, source, path) in enumerate(records)
    ]
