from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
import qrcode
from PIL import Image

from snapims import db
from snapims.demo import create_demo_batch
from snapims.pipeline import sha256_file
from snapims.processor import ImportInterrupted, process_batch
from snapims.qr import QRDecodeError

from .conftest import create_jpeg


def test_end_to_end_import_preserves_originals_names_images_and_events(tmp_path, data_paths) -> None:
    source = create_demo_batch(tmp_path / "camera")
    source_hashes = {path.name: sha256_file(path) for path in source.glob("*.jpg")}
    result = process_batch(source, paths=data_paths, batch_name="Demo Batch")

    assert result.item_count == 2
    assert result.product_photo_count == 4
    assert result.command_count == 6
    assert result.batch_id.endswith("-DEMO-BATCH")
    assert (result.output_folder / "batch_manifest.json").is_file()
    assert (result.output_folder / "image_manifest.csv").is_file()
    assert (result.output_folder / "commands.csv").is_file()
    assert (result.output_folder / "inventory_work.csv").is_file()
    assert (result.output_folder / "warnings.txt").is_file()
    images = sorted((result.output_folder / "images").glob("*.jpg"))
    assert [path.name.rsplit("-", 1)[-1] for path in images] == ["02.jpg", "F.jpg", "02.jpg", "F.jpg"]
    assert any(path.name.endswith("-B2-001-F.jpg") for path in images)
    assert any(path.name.endswith("-B2-002-02.jpg") for path in images)
    with Image.open(images[0]) as public_copy:
        assert not public_copy.getexif(), "Processed/upload copies must carry no EXIF/GPS metadata"
    originals = sorted((data_paths.originals / result.batch_id).glob("*.jpg"))
    assert len(originals) == len(source_hashes)
    for copy in originals:
        source_name = copy.name.split("-", 1)[1]
        assert sha256_file(copy) == source_hashes[source_name]
    with db.connect(data_paths.db_file) as connection:
        assert connection.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM photos WHERE kind='product'").fetchone()[0] == 4
        assert connection.execute("SELECT COUNT(*) FROM command_events").fetchone()[0] == 6
        assert connection.execute("SELECT COUNT(*) FROM inventory_events").fetchone()[0] == 2


def test_duplicate_import_is_idempotent(tmp_path, data_paths) -> None:
    source = create_demo_batch(tmp_path / "camera")
    first = process_batch(source, paths=data_paths)
    second = process_batch(source, paths=data_paths)
    assert second.duplicate is True
    assert second.batch_id == first.batch_id
    assert db.database_summary(data_paths.db_file)["items"] == 2


def test_output_collision_allocates_new_batch_without_overwrite(tmp_path, data_paths) -> None:
    first_source = create_demo_batch(tmp_path / "first")
    first = process_batch(first_source, paths=data_paths)
    marker = first.output_folder / "operator-note.txt"
    marker.write_text("preserve me", encoding="utf-8")
    second_source = create_demo_batch(tmp_path / "second")
    product = sorted(second_source.glob("*.jpg"))[2]
    product.write_bytes(product.read_bytes() + b"different-source-fingerprint")
    second = process_batch(second_source, paths=data_paths)
    assert second.batch_id != first.batch_id
    assert marker.read_text(encoding="utf-8") == "preserve me"


def test_interruption_retains_staging_and_rerun_resumes(tmp_path, data_paths) -> None:
    source = create_demo_batch(tmp_path / "camera")
    with pytest.raises(ImportInterrupted):
        process_batch(source, paths=data_paths, interrupt_after=3)
    progress = next(data_paths.processed.glob(".staging-*/progress.json"))
    original_batch_id = __import__("json").loads(progress.read_text())["batch_id"]
    result = process_batch(source, paths=data_paths)
    assert result.batch_id == original_batch_id
    assert result.item_count == 2
    assert not list(data_paths.processed.glob(".staging-*"))


def test_corrupted_image_aborts_without_database_rows(tmp_path, data_paths) -> None:
    source = create_demo_batch(tmp_path / "camera")
    (source / "PXL_20260716_120099999.jpg").write_bytes(b"corrupt")
    with pytest.raises(QRDecodeError):
        process_batch(source, paths=data_paths)
    assert db.database_summary(data_paths.db_file)["items"] == 0


def test_excluded_photos_are_still_preserved_and_audited(tmp_path, data_paths) -> None:
    source = create_demo_batch(tmp_path / "camera")
    create_jpeg(
        source / "PXL_20260716_115959000.jpg",
        captured_at=datetime(2026, 7, 16, 11, 59, 59),
        color="orange",
    )
    create_jpeg(
        source / "PXL_20260716_120011000.jpg",
        captured_at=datetime(2026, 7, 16, 12, 0, 11),
        color="blue",
    )
    source_hashes = {path.name: sha256_file(path) for path in source.glob("*.jpg")}
    result = process_batch(source, paths=data_paths)
    originals = list((data_paths.originals / result.batch_id).glob("*.jpg"))
    assert len(originals) == len(source_hashes) == 12
    with db.connect(data_paths.db_file) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM photos WHERE kind='excluded'"
        ).fetchone()[0] == 2
    manifest = json.loads(
        (result.output_folder / "batch_manifest.json").read_text(encoding="utf-8")
    )
    assert len(manifest["excluded_photos"]) == 2


def _write_qr_command_jpeg(path: Path, payload: str, captured_at: datetime) -> None:
    qr = qrcode.make(payload).convert("RGB").resize((300, 300))
    exif = Image.Exif()
    exif[36867] = captured_at.strftime("%Y:%m:%d %H:%M:%S")
    exif[37521] = f"{captured_at.microsecond:06d}"
    qr.save(path, exif=exif)


def test_unknown_cvhs1_command_is_quarantined_never_a_product_and_fully_audited(
    tmp_path, data_paths
) -> None:
    source = create_demo_batch(tmp_path / "camera")
    unknown_path = source / "PXL_20260716_120002500.jpg"
    _write_qr_command_jpeg(
        unknown_path, "CVHS1:DO:MAGIC", datetime(2026, 7, 16, 12, 0, 2, 500000)
    )
    source_hashes = {path.name: sha256_file(path) for path in source.glob("*.jpg")}

    result = process_batch(source, paths=data_paths)

    assert result.item_count == 2
    assert result.product_photo_count == 4
    assert result.command_count == 6
    assert any("Unknown CVHS1 command quarantined" in warning for warning in result.warnings)

    original_copy = next(
        (data_paths.originals / result.batch_id).glob(f"*-{unknown_path.name}")
    )
    assert sha256_file(original_copy) == source_hashes[unknown_path.name]

    manifest = json.loads(
        (result.output_folder / "batch_manifest.json").read_text(encoding="utf-8")
    )
    assert len(manifest["unknown_commands"]) == 1
    assert manifest["unknown_commands"][0]["qr_payload"] == "CVHS1:DO:MAGIC"
    quarantine_copy = Path(manifest["unknown_commands"][0]["quarantine_copy_path"])
    assert quarantine_copy.is_file()
    assert quarantine_copy.parent.name == "commands"

    with db.connect(data_paths.db_file) as connection:
        photo_row = connection.execute(
            "SELECT kind, qr_payload FROM photos WHERE original_name = ?",
            (unknown_path.name,),
        ).fetchone()
        assert photo_row["kind"] == "command"
        assert photo_row["qr_payload"] == "CVHS1:DO:MAGIC"
        event_row = connection.execute(
            "SELECT payload, warning FROM command_events WHERE command_kind = 'unknown_command'"
        ).fetchone()
        assert event_row["payload"] == "CVHS1:DO:MAGIC"
        assert event_row["warning"]
