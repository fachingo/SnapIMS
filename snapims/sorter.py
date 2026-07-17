from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from PIL import ExifTags, Image

from snapims.models import PhotoRecord, TimestampSource

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass


SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff"
}
_CAMERA_SEQUENCE_RE = re.compile(r"(?:^|[_-])(\d{3,9})(?:[_-]|$)")


def find_photos(folder: Path, *, recursive: bool = False) -> list[Path]:
    folder = folder.expanduser().resolve()
    if not folder.exists():
        raise FileNotFoundError(f"Folder does not exist: {folder}")
    if not folder.is_dir():
        raise NotADirectoryError(f"Not a directory: {folder}")

    iterator = folder.rglob("*") if recursive else folder.iterdir()
    return sorted(
        (path for path in iterator if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS),
        key=lambda path: (path.name.casefold(), str(path).casefold()),
    )


def _parse_exif_datetime(raw: object, subsecond: object | None = None) -> datetime | None:
    value = str(raw).strip()
    if subsecond and "." not in value:
        digits = re.sub(r"\D", "", str(subsecond))
        if digits:
            value = f"{value}.{digits[:6]}"
    for fmt in (
        "%Y:%m:%d %H:%M:%S.%f", "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _read_exif_timestamp(path: Path) -> tuple[datetime, TimestampSource] | None:
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            if not exif:
                return None
            tags = {ExifTags.TAGS.get(tag_id, tag_id): value for tag_id, value in exif.items()}
            candidates = (
                ("DateTimeOriginal", "SubsecTimeOriginal", "exif_original"),
                ("DateTimeDigitized", "SubsecTimeDigitized", "exif_digitized"),
                ("DateTime", "SubsecTime", "exif_datetime"),
            )
            for tag_name, subsec_name, source in candidates:
                raw = tags.get(tag_name)
                if raw is None:
                    continue
                parsed = _parse_exif_datetime(raw, tags.get(subsec_name))
                if parsed is not None:
                    return parsed, source  # type: ignore[return-value]
    except (OSError, ValueError):
        return None
    return None


def _filename_timestamp(path: Path) -> datetime | None:
    patterns = (
        (re.compile(r"PXL_(\d{8})_(\d{6})(?:\d{3})?"), "%Y%m%d%H%M%S"),
        (re.compile(r"IMG[_-](\d{8})[_-](\d{6})"), "%Y%m%d%H%M%S"),
        (re.compile(r"(\d{8})[_-](\d{6})"), "%Y%m%d%H%M%S"),
        (re.compile(r"(\d{4}-\d{2}-\d{2})[_-](\d{2}-\d{2}-\d{2})"), "%Y-%m-%d%H-%M-%S"),
    )
    for pattern, fmt in patterns:
        match = pattern.search(path.stem)
        if match:
            try:
                return datetime.strptime("".join(match.groups()), fmt)
            except ValueError:
                pass
    return None


def _sequence_hint(path: Path) -> int | None:
    numbers = _CAMERA_SEQUENCE_RE.findall(path.stem)
    return int(numbers[-1]) if numbers else None


def read_photo_record(path: Path) -> PhotoRecord:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Photo does not exist: {path}")
    exif_result = _read_exif_timestamp(path)
    if exif_result is not None:
        captured_at, source = exif_result
    elif (filename_time := _filename_timestamp(path)) is not None:
        captured_at, source = filename_time, "filename"
    else:
        captured_at, source = datetime.fromtimestamp(path.stat().st_mtime), "filesystem_mtime"
    return PhotoRecord(
        path=path.resolve(), captured_at=captured_at, timestamp_source=source,  # type: ignore[arg-type]
        original_name=path.name, sequence_hint=_sequence_hint(path),
    )


def sort_records(records: Iterable[PhotoRecord]) -> list[PhotoRecord]:
    ordered = sorted(
        records,
        key=lambda record: (
            record.captured_at,
            record.sequence_hint if record.sequence_hint is not None else 2**63 - 1,
            record.original_name.casefold(),
            str(record.path).casefold(),
        ),
    )
    return [
        PhotoRecord(
            path=record.path, captured_at=record.captured_at,
            timestamp_source=record.timestamp_source, original_name=record.original_name,
            sequence_hint=record.sequence_hint, qr_payload=record.qr_payload,
            stream_index=index, sha256=record.sha256,
        )
        for index, record in enumerate(ordered, start=1)
    ]


def load_sorted_photos(folder: Path, *, recursive: bool = False) -> list[PhotoRecord]:
    return sort_records(read_photo_record(path) for path in find_photos(folder, recursive=recursive))
