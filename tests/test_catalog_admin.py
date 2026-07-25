from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from snapims import db
from snapims.catalog import db as catalog_db
from snapims.catalog.admin import add_alias, import_catalog_json, merge_movies, split_movie
from snapims.catalog.models import MovieCandidate
from snapims.catalog.service import create_or_update_movie, get_catalog_status, queue_recognition_lookup, search_local
from snapims.demo import create_demo_batch
from snapims.processor import process_batch
from snapims.recognition.base import BaseRecognizer, RecognitionResult
from snapims.recognition.service import run_recognition


class Recognizer(BaseRecognizer):
    name = "admin-fixture"

    def __init__(self, title: str, year: int) -> None:
        self.title = title
        self.year = year

    def recognize(self, item, images):
        return RecognitionResult(
            suggested_title=self.title,
            edition="VHS",
            distributor="Studio",
            year=self.year,
            barcode_candidates=(),
            suggested_price_cents=999,
            suggested_discount_percent=0,
            confidence=0.95,
            provider_name=self.name,
            raw_response_reference="admin",
            requires_review=False,
        )


def movie(title: str, year: int, page_id: str) -> MovieCandidate:
    return MovieCandidate(
        provider="wikipedia",
        source_page_id=page_id,
        source_page_title=title,
        source_url=f"https://en.wikipedia.org/?curid={page_id}",
        canonical_title=title,
        release_year=year,
        media_type="film",
        runtime_minutes=100,
        directors=("Director",),
        countries=("Canada",),
        languages=("English",),
        genres=("Drama",),
        summary="A film.",
        source_revision_id=f"r-{page_id}",
        retrieved_at=catalog_db.now(),
        raw_response_hash=f"h-{page_id}",
        attribution="English Wikipedia",
        parser_version=catalog_db.CATALOG_PARSER_VERSION,
        score=0.99,
        evidence=("exact",),
    )


def linked_item(tmp_path: Path, data_paths, title: str, year: int):
    result = process_batch(create_demo_batch(tmp_path / f"camera-{title}-{year}", item_count=1), paths=data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    result_id, _ = run_recognition(data_paths.db_file, item["item_id"], Recognizer(title, year))
    queue_recognition_lookup(data_paths, result_id, start_worker=False)
    return item


def test_add_alias_and_rebuild_search_index(data_paths) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    movie_id, _ = create_or_update_movie(data_paths.catalog_db_file, movie("Gremlins", 1984, "1001"))
    add_alias(data_paths, movie_id, "Gremlins: Special Edition")
    match = search_local(data_paths.catalog_db_file, "Gremlins: Special Edition")
    assert match[0].movie_id == movie_id
    assert match[0].unique


def test_merge_movies_relinks_items_and_is_audited(tmp_path: Path, data_paths) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    survivor, _ = create_or_update_movie(data_paths.catalog_db_file, movie("Gremlins", 1984, "1001"))
    duplicate, _ = create_or_update_movie(data_paths.catalog_db_file, movie("Gremlins Special", 1984, "1002"))
    item = linked_item(tmp_path, data_paths, "Gremlins Special", 1984)
    assert get_catalog_status(data_paths, item["item_id"]).movie_id == duplicate
    result = merge_movies(data_paths, survivor, duplicate)
    assert result["relinked_items"] == 1
    assert get_catalog_status(data_paths, item["item_id"]).movie_id == survivor
    with catalog_db.connect(data_paths.catalog_db_file, readonly=True) as connection:
        merged = connection.execute("SELECT active,data_quality_status FROM movies WHERE movie_id=?", (duplicate,)).fetchone()
        job = connection.execute("SELECT status FROM catalog_maintenance_jobs WHERE maintenance_job_id=?", (result["maintenance_job_id"],)).fetchone()
        event = connection.execute("SELECT COUNT(*) FROM catalog_events WHERE event_type='MOVIE_MERGED'").fetchone()[0]
    assert tuple(merged) == (0, "MERGED")
    assert job[0] == "COMPLETE"
    assert event == 1
    assert list(data_paths.backups.glob("*before-movie-merge*.sqlite3"))


def test_split_movie_relinks_only_selected_item(tmp_path: Path, data_paths) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    source, _ = create_or_update_movie(data_paths.catalog_db_file, movie("Crash", 1996, "1202"))
    result = process_batch(create_demo_batch(tmp_path / "camera-split", item_count=2), paths=data_paths)
    first, second = db.list_items(data_paths.db_file, batch_id=result.batch_id)
    for item in (first, second):
        result_id, _ = run_recognition(data_paths.db_file, item["item_id"], Recognizer("Crash", 1996))
        queue_recognition_lookup(data_paths, result_id, start_worker=False)
    assert get_catalog_status(data_paths, first["item_id"]).movie_id == source
    assert get_catalog_status(data_paths, second["item_id"]).movie_id == source
    result = split_movie(
        data_paths,
        source,
        canonical_title="Crash",
        release_year=1978,
        item_ids=[first["item_id"]],
    )
    assert result["relinked_items"] == 1
    assert get_catalog_status(data_paths, first["item_id"]).movie_id == result["new_movie_id"]
    assert get_catalog_status(data_paths, second["item_id"]).movie_id == source
    with catalog_db.connect(data_paths.catalog_db_file, readonly=True) as connection:
        assert connection.execute("SELECT status FROM catalog_maintenance_jobs WHERE maintenance_job_id=?", (result["maintenance_job_id"],)).fetchone()[0] == "COMPLETE"


def test_export_import_round_trip(data_paths, tmp_path: Path) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    original, _ = create_or_update_movie(data_paths.catalog_db_file, movie("Gremlins", 1984, "1001"))
    export = tmp_path / "catalog.json"
    catalog_db.export_catalog_json(data_paths.catalog_db_file, export)

    other_root = tmp_path / "other"
    from snapims.config import DataPaths

    other = DataPaths.from_root(other_root).ensure()
    db.initialize(other.db_file, paths=other)
    catalog_db.initialize(other.catalog_db_file, paths=other)
    counts = import_catalog_json(other, export)
    assert counts["movies"] == 1
    assert search_local(other.catalog_db_file, "Gremlins", 1984)[0].movie_id == original
    with catalog_db.connect(other.catalog_db_file, readonly=True) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_catalog_backup_restores_exact_business_data(data_paths, tmp_path: Path) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    create_or_update_movie(data_paths.catalog_db_file, movie("Gremlins", 1984, "1001"))
    backup = catalog_db.backup_catalog(data_paths, "restore-test")
    assert backup is not None
    create_or_update_movie(data_paths.catalog_db_file, movie("The Thing", 1982, "1102"))
    assert catalog_db.catalog_summary(data_paths.catalog_db_file)["movies"] == 2

    data_paths.catalog_db_file.unlink()
    target = sqlite3.connect(data_paths.catalog_db_file)
    source = sqlite3.connect(backup)
    source.backup(target)
    source.close()
    target.close()
    assert catalog_db.catalog_summary(data_paths.catalog_db_file)["movies"] == 1


def test_import_rejects_incompatible_schema(data_paths, tmp_path: Path) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    source = tmp_path / "bad.json"
    source.write_text(json.dumps({"manifest": {"schema_version": 999}}), encoding="utf-8")
    try:
        import_catalog_json(data_paths, source)
    except ValueError as exc:
        assert "incompatible" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("incompatible import was accepted")
