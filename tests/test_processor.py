from __future__ import annotations

from pathlib import Path

from PIL import Image

from snapims import db
from snapims.demo import create_demo_batch
from snapims.pipeline import sha256_file
from snapims.processor import process_batch


def test_import_preserves_originals_and_ids(tmp_path: Path, data_paths) -> None:
    source = create_demo_batch(tmp_path / "camera")
    hashes = {path.name: sha256_file(path) for path in source.glob("*.jpg")}
    result = process_batch(source, paths=data_paths, batch_name="PILOT")
    assert result.item_count == 2
    assert result.product_photo_count == 4
    items = db.list_items(data_paths.db_file, batch_id=result.batch_id)
    assert [item["item_id"] for item in items] == [f"{result.batch_id}-B2-001", f"{result.batch_id}-B2-002"]
    originals = list((data_paths.originals / result.batch_id).glob("*.jpg"))
    assert len(originals) == len(hashes)
    for copied in originals:
        assert sha256_file(copied) == hashes[copied.name.split("-", 1)[1]]
    with Image.open(items[0]["front_image"]) as image:
        assert not image.getexif()


def test_duplicate_import_is_idempotent(tmp_path: Path, data_paths) -> None:
    source = create_demo_batch(tmp_path / "camera")
    first = process_batch(source, paths=data_paths)
    second = process_batch(source, paths=data_paths)
    assert second.duplicate
    assert second.batch_id == first.batch_id
    assert db.database_summary(data_paths.db_file)["items"] == 2


def test_successful_folder_is_remembered(tmp_path: Path, data_paths) -> None:
    source = create_demo_batch(tmp_path / "camera")
    process_batch(source, paths=data_paths)
    assert db.recent_folders(data_paths.db_file) == [str(source.resolve())]
