from __future__ import annotations

from datetime import datetime
from pathlib import Path

from snapims.models import PhotoRecord
from snapims.sorter import SUPPORTED_EXTENSIONS, load_sorted_photos, read_photo_record, sort_records

from .conftest import create_jpeg, set_mtime


def test_supported_file_types_are_explicit() -> None:
    assert {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff"} <= SUPPORTED_EXTENSIONS


def test_reads_exif_with_subseconds(tmp_path) -> None:
    expected = datetime(2026, 7, 16, 12, 34, 56, 123456)
    path = create_jpeg(tmp_path / "photo.jpg", captured_at=expected)
    record = read_photo_record(path)
    assert record.captured_at == expected
    assert record.timestamp_source == "exif_original"


def test_missing_exif_uses_pixel_filename_before_mtime(tmp_path) -> None:
    path = create_jpeg(tmp_path / "PXL_20260716_141500000.jpg")
    set_mtime(path, datetime(2030, 1, 1))
    record = read_photo_record(path)
    assert record.captured_at == datetime(2026, 7, 16, 14, 15)
    assert record.timestamp_source == "filename"


def test_missing_exif_and_filename_uses_mtime(tmp_path) -> None:
    expected = datetime(2026, 7, 16, 9, 0, 0)
    path = create_jpeg(tmp_path / "unknown.jpg")
    set_mtime(path, expected)
    record = read_photo_record(path)
    assert abs((record.captured_at - expected).total_seconds()) < 1
    assert record.timestamp_source == "filesystem_mtime"


def test_identical_timestamps_use_sequence_hint_then_name() -> None:
    time = datetime(2026, 7, 16)
    records = [
        PhotoRecord(Path("PXL_002.jpg"), time, "filename", "PXL_002.jpg", 2),
        PhotoRecord(Path("PXL_001.jpg"), time, "filename", "PXL_001.jpg", 1),
        PhotoRecord(Path("A.jpg"), time, "filename", "A.jpg", None),
    ]
    ordered = sort_records(records)
    assert [record.original_name for record in ordered] == ["PXL_001.jpg", "PXL_002.jpg", "A.jpg"]
    assert [record.stream_index for record in ordered] == [1, 2, 3]


def test_load_sorted_photos_uses_capture_order(tmp_path) -> None:
    create_jpeg(tmp_path / "late.jpg", captured_at=datetime(2026, 7, 16, 12, 0, 2))
    create_jpeg(tmp_path / "early.jpg", captured_at=datetime(2026, 7, 16, 12, 0, 1))
    assert [record.original_name for record in load_sorted_photos(tmp_path)] == ["early.jpg", "late.jpg"]
