from __future__ import annotations

import csv
import json
import sqlite3
import threading
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapims import db
from snapims.catalog import db as catalog_db
from snapims.catalog.models import MovieCandidate
from snapims.catalog.normalization import normalize_title, title_variants
from snapims.catalog.service import (
    create_or_update_movie,
    get_catalog_status,
    process_catalog_job_sync,
    queue_operator_title_correction,
    queue_recognition_lookup,
    recover_catalog_jobs,
    search_local,
    select_candidate,
)
from snapims.catalog.wikipedia import (
    FixtureTransport,
    WikipediaClient,
    WikipediaMalformedResponse,
    WikipediaRateLimit,
)
from snapims.config import ShopifyConfig
from snapims.demo import create_demo_batch
from snapims.inventory import export_inventory_csv
from snapims.processor import process_batch
from snapims.recognition.base import BaseRecognizer, RecognitionResult
from snapims.recognition.service import accept_item, run_recognition
from snapims.shopify.service import ShopifyService
from snapims.web.app import app


class FilmRecognizer(BaseRecognizer):
    name = "catalog-fixture"

    def __init__(self, title: str, year: int | None) -> None:
        self.title = title
        self.year = year

    def recognize(self, item, images):
        return RecognitionResult(
            suggested_title=self.title,
            edition="VHS",
            distributor="Fixture Studio",
            year=self.year,
            barcode_candidates=(),
            suggested_price_cents=1299,
            suggested_discount_percent=0,
            confidence=0.95,
            provider_name=self.name,
            raw_response_reference="fixture:1",
            requires_review=False,
        )


def candidate(
    title: str,
    year: int | None,
    *,
    page_id: str,
    media_type: str = "film",
    aliases: tuple[str, ...] = (),
) -> MovieCandidate:
    return MovieCandidate(
        provider="wikipedia",
        source_page_id=page_id,
        source_page_title=title,
        source_url=f"https://en.wikipedia.org/?curid={page_id}",
        canonical_title=title,
        original_title="",
        release_year=year,
        media_type=media_type,
        runtime_minutes=106,
        countries=("United States",),
        languages=("English",),
        directors=("Fixture Director",),
        genres=("Horror",),
        summary=f"{title} is a film.",
        aliases=aliases,
        source_revision_id=f"r-{page_id}",
        retrieved_at=catalog_db.now(),
        raw_response_hash=f"hash-{page_id}",
        attribution="English Wikipedia",
        parser_version=catalog_db.CATALOG_PARSER_VERSION,
        score=0.99,
        evidence=("exact normalized title", "release year agrees", "page is classified as a film"),
    )


def recognized_item(tmp_path: Path, data_paths, title: str, year: int | None):
    result = process_batch(create_demo_batch(tmp_path / f"camera-{title}-{year}", item_count=1), paths=data_paths)
    item = db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]
    result_id, _ = run_recognition(data_paths.db_file, item["item_id"], FilmRecognizer(title, year))
    return result, item, result_id


def test_catalog_schema_is_independent_and_repeatable(data_paths) -> None:
    db.initialize(data_paths.db_file, paths=data_paths)
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    assert data_paths.catalog_db_file != data_paths.db_file
    with catalog_db.connect(data_paths.catalog_db_file, readonly=True) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert catalog_db.verify_structure(connection) == []


def test_normalization_is_conservative() -> None:
    assert normalize_title("The Thing — 1982") == "the thing 1982"
    assert "rocky 2" in title_variants("Rocky II")
    assert normalize_title("It") != normalize_title("It: Chapter Two")


def test_exact_title_year_and_alias_local_matches(data_paths) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    gremlins, _ = create_or_update_movie(
        data_paths.catalog_db_file,
        candidate("Gremlins", 1984, page_id="1001", aliases=("Gremlins: The Movie",)),
    )
    exact = search_local(data_paths.catalog_db_file, "Gremlins", 1984)
    alias = search_local(data_paths.catalog_db_file, "Gremlins: The Movie", 1984)
    assert exact[0].movie_id == gremlins and exact[0].unique
    assert alias[0].movie_id == gremlins and alias[0].unique


def test_same_title_different_years_remain_separate(data_paths) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    older, _ = create_or_update_movie(data_paths.catalog_db_file, candidate("The Thing", 1951, page_id="1101"))
    newer, _ = create_or_update_movie(data_paths.catalog_db_file, candidate("The Thing", 1982, page_id="1102"))
    assert older != newer
    assert search_local(data_paths.catalog_db_file, "The Thing", 1951)[0].movie_id == older
    assert search_local(data_paths.catalog_db_file, "The Thing", 1982)[0].movie_id == newer
    ambiguous = search_local(data_paths.catalog_db_file, "The Thing")
    assert not ambiguous[0].unique


@pytest.mark.parametrize(
    ("title", "years"),
    [("The Fly", (1958, 1986)), ("Crash", (1978, 1996)), ("Halloween", (1978, 2007))],
)
def test_remake_collisions_are_separate(data_paths, title: str, years: tuple[int, int]) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    ids = [create_or_update_movie(data_paths.catalog_db_file, candidate(title, year, page_id=f"{title}-{year}"))[0] for year in years]
    assert len(set(ids)) == 2
    assert search_local(data_paths.catalog_db_file, title, years[0])[0].movie_id == ids[0]
    assert search_local(data_paths.catalog_db_file, title, years[1])[0].movie_id == ids[1]


def test_film_and_television_collision_is_not_silently_unique(data_paths) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    create_or_update_movie(data_paths.catalog_db_file, candidate("It", 1990, page_id="it-tv", media_type="television"))
    create_or_update_movie(data_paths.catalog_db_file, candidate("It", 2017, page_id="it-film"))
    matches = search_local(data_paths.catalog_db_file, "It")
    assert len(matches) == 2
    assert not matches[0].unique


def test_wikipedia_fixture_parses_film_metadata(data_paths) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    client = WikipediaClient(
        data_paths.catalog_db_file,
        transport=FixtureTransport(Path("tests/fixtures/wikipedia")),
        min_interval=0,
        max_retries=0,
    )
    movies = client.search_candidates("Gremlins", 1984)
    assert len(movies) == 1
    movie = movies[0]
    assert movie.canonical_title == "Gremlins"
    assert movie.release_year == 1984
    assert movie.directors == ("Joe Dante",)
    assert movie.runtime_minutes == 106
    assert movie.score >= 0.92
    assert movie.source_revision_id == "123456"


def test_wikipedia_nonfilm_contamination_is_rejected(data_paths) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    client = WikipediaClient(
        data_paths.catalog_db_file,
        transport=FixtureTransport(Path("tests/fixtures/wikipedia")),
        min_interval=0,
        max_retries=0,
    )
    movies = client.search_candidates("Crash", 1996)
    assert any(movie.media_type == "non-film" and movie.rejected_reason for movie in movies)
    assert movies[0].canonical_title == "Crash"
    assert movies[0].release_year == 1996


def test_timeout_rate_limit_and_malformed_response(data_paths) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)

    def rate_limited(params):
        return 429, {}, {}

    client = WikipediaClient(data_paths.catalog_db_file, transport=rate_limited, min_interval=0, max_retries=0)
    with pytest.raises(WikipediaRateLimit):
        client.search("Gremlins", 1984)

    def malformed(params):
        if params.get("list") == "search":
            return 200, {"query": {"search": [{"pageid": 1, "title": "Gremlins"}]}}, {}
        return 200, {"query": {"pages": []}}, {}

    client = WikipediaClient(data_paths.catalog_db_file, transport=malformed, min_interval=0, max_retries=0)
    with pytest.raises(WikipediaMalformedResponse):
        client.search_candidates("Gremlins", 1984)


def test_first_gremlins_creates_one_movie_second_copy_is_local_hit(tmp_path: Path, data_paths) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    _, first_item, first_result_id = recognized_item(tmp_path, data_paths, "Gremlins", 1984)
    first_job = queue_recognition_lookup(data_paths, first_result_id, start_worker=False)
    assert first_job is not None
    transport = FixtureTransport(Path("tests/fixtures/wikipedia"))
    calls: Counter[str] = Counter()

    def counting(params):
        calls[params.get("list") or params.get("action", "query")] += 1
        return transport(params)

    process_catalog_job_sync(
        data_paths,
        first_job,
        client=WikipediaClient(data_paths.catalog_db_file, transport=counting, min_interval=0, max_retries=0),
    )
    first_status = get_catalog_status(data_paths, first_item["item_id"])
    assert first_status.status == "NEW_WIKIPEDIA_RECORD"
    assert first_status.movie_id.startswith("MOV-")
    with catalog_db.connect(data_paths.catalog_db_file, readonly=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM movies").fetchone()[0] == 1

    _, second_item, second_result_id = recognized_item(tmp_path, data_paths, "Gremlins", 1984)
    second_job = queue_recognition_lookup(data_paths, second_result_id, start_worker=False)
    second_status = get_catalog_status(data_paths, second_item["item_id"])
    assert second_status.status == "LOCAL_MATCH"
    assert second_status.movie_id == first_status.movie_id
    assert calls == Counter({"search": 1, "query": 1, "parse": 1})
    with catalog_db.connect(data_paths.catalog_db_file, readonly=True) as connection:
        row = connection.execute("SELECT status,attempt_count FROM catalog_lookup_jobs WHERE job_id=?", (second_job,)).fetchone()
    assert row[0] == "LOCAL_MATCHED" and row[1] == 0


def test_concurrent_duplicate_ingest_creates_one_movie(data_paths) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    ids: list[str] = []
    errors: list[Exception] = []

    def worker() -> None:
        try:
            ids.append(create_or_update_movie(data_paths.catalog_db_file, candidate("Gremlins", 1984, page_id="1001"))[0])
        except Exception as exc:  # pragma: no cover - diagnostic
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len(set(ids)) == 1
    with catalog_db.connect(data_paths.catalog_db_file, readonly=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM movies").fetchone()[0] == 1


def test_ambiguous_candidates_persist_and_operator_can_select(tmp_path: Path, data_paths) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    _, item, result_id = recognized_item(tmp_path, data_paths, "Crash", None)
    job_id = queue_recognition_lookup(data_paths, result_id, start_worker=False)
    assert job_id is not None
    process_catalog_job_sync(
        data_paths,
        job_id,
        client=WikipediaClient(
            data_paths.catalog_db_file,
            transport=FixtureTransport(Path("tests/fixtures/wikipedia")),
            min_interval=0,
            max_retries=0,
        ),
    )
    status = get_catalog_status(data_paths, item["item_id"])
    assert status.status == "AMBIGUOUS"
    assert status.candidate_count >= 2
    with catalog_db.connect(data_paths.catalog_db_file, readonly=True) as connection:
        selected = connection.execute(
            "SELECT candidate_id FROM movie_candidates WHERE job_id=? AND release_year=1996", (job_id,)
        ).fetchone()[0]
    movie_id = select_candidate(data_paths, job_id, int(selected))
    assert get_catalog_status(data_paths, item["item_id"]).movie_id == movie_id
    assert db.get_item_movie_link(data_paths.db_file, item["item_id"])["operator_confirmed"] == 1


def test_restart_recovers_running_job_without_duplicate(data_paths) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    with catalog_db.transaction(data_paths.catalog_db_file) as connection:
        connection.execute(
            """INSERT INTO catalog_lookup_jobs(recognition_result_id,item_id,proposed_title,normalized_title,request_json,status,created_at,updated_at)
               VALUES(999,'ITEM-X','Gremlins','gremlins',?,'SEARCHING_WIKIPEDIA',?,?)""",
            (json.dumps({"item_id": "ITEM-X", "recognition_result_id": 999, "proposed_title": "Gremlins"}), catalog_db.now(), catalog_db.now()),
        )
    assert recover_catalog_jobs(data_paths, start_workers=False) == 1
    with catalog_db.connect(data_paths.catalog_db_file, readonly=True) as connection:
        row = connection.execute("SELECT status,COUNT(*) OVER() FROM catalog_lookup_jobs WHERE recognition_result_id=999").fetchone()
    assert row[0] == "PAUSED" and row[1] == 1


def test_operator_title_correction_marks_old_link_stale_and_relinks(tmp_path: Path, data_paths) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    old_id, _ = create_or_update_movie(data_paths.catalog_db_file, candidate("The Thing", 1951, page_id="1101"))
    new_id, _ = create_or_update_movie(data_paths.catalog_db_file, candidate("The Thing", 1982, page_id="1102"))
    _, item, result_id = recognized_item(tmp_path, data_paths, "The Thing", 1951)
    queue_recognition_lookup(data_paths, result_id, start_worker=False)
    assert get_catalog_status(data_paths, item["item_id"]).movie_id == old_id
    queue_operator_title_correction(data_paths, item["item_id"], "The Thing", 1982)
    assert get_catalog_status(data_paths, item["item_id"]).movie_id == new_id
    history = db.item_movie_link_history(data_paths.db_file, item["item_id"])
    assert any(row["event_type"] == "STALE" for row in history)


def test_catalog_unavailable_does_not_break_review_or_approval(tmp_path: Path, data_paths) -> None:
    _, item, _ = recognized_item(tmp_path, data_paths, "Unknown Fixture", 1999)
    data_paths.catalog_db_file.write_bytes(b"not a sqlite database")
    status = get_catalog_status(data_paths, item["item_id"])
    assert not status.available
    assert accept_item(data_paths.db_file, item["item_id"], price_cents=999, discount_percent=0) == []
    assert db.get_item(data_paths.db_file, item["item_id"])["review_status"] == "DONE"


def test_catalog_corruption_is_left_untouched(data_paths) -> None:
    data_paths.catalog_db_file.parent.mkdir(parents=True, exist_ok=True)
    data_paths.catalog_db_file.write_bytes(b"damaged catalog")
    before = data_paths.catalog_db_file.read_bytes()
    with pytest.raises((RuntimeError, sqlite3.DatabaseError)):
        catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    assert data_paths.catalog_db_file.read_bytes() == before


def test_csv_and_shopify_include_movie_and_item_identity(tmp_path: Path, data_paths) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    movie_id, _ = create_or_update_movie(data_paths.catalog_db_file, candidate("Gremlins", 1984, page_id="1001"))
    result, item, result_id = recognized_item(tmp_path, data_paths, "Gremlins", 1984)
    queue_recognition_lookup(data_paths, result_id, start_worker=False)
    assert accept_item(data_paths.db_file, item["item_id"], price_cents=1299, discount_percent=10) == []
    destination = tmp_path / "inventory.csv"
    export_inventory_csv(data_paths.db_file, result.batch_id, destination)
    row = next(csv.DictReader(destination.open(encoding="utf-8-sig")))
    assert row["Item ID"] == item["item_id"]
    assert row["Local Movie ID"] == movie_id
    assert row["Canonical Movie title"] == "Gremlins"
    assert row["Price"] == "12.99"
    assert row["Discount percent"] == "10"

    report = ShopifyService(data_paths.db_file, ShopifyConfig("", "", "")).dry_run(item["item_id"])
    assert report.payload["item_id"] == item["item_id"]
    assert report.payload["local_movie_id"] == movie_id
    assert report.payload["movie"]["directors"] == ["Fixture Director"]
    assert report.payload["status"] == "DRAFT"


def test_review_renders_compact_catalog_status(tmp_path: Path, data_paths, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    create_or_update_movie(data_paths.catalog_db_file, candidate("Gremlins", 1984, page_id="1001"))
    result, item, result_id = recognized_item(tmp_path, data_paths, "Gremlins", 1984)
    queue_recognition_lookup(data_paths, result_id, start_worker=False)
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(data_paths.root))
    with TestClient(app) as client:
        response = client.get(f"/review?batch_id={result.batch_id}&item_id={item['item_id']}")
    assert response.status_code == 200
    assert "Catalog match: LOCAL MATCH" in response.text
    assert "Gremlins" in response.text
    assert "Approve &amp; Next" in response.text or "Approve & Next" in response.text


def test_catalog_output_has_provenance(data_paths) -> None:
    catalog_db.initialize(data_paths.catalog_db_file, paths=data_paths)
    movie_id, _ = create_or_update_movie(data_paths.catalog_db_file, candidate("Gremlins", 1984, page_id="1001"))
    assert movie_id.startswith("MOV-")
    summary = catalog_db.catalog_summary(data_paths.catalog_db_file)
    assert summary["movies"] == 1
    assert summary["new_movie_records"] == 1
    export = data_paths.root / "exports" / "catalog.json"
    catalog_db.export_catalog_json(data_paths.catalog_db_file, export)
    payload = json.loads(export.read_text())
    assert payload["manifest"]["schema_version"] == 1
    assert payload["movie_sources"][0]["source_page_id"] == "1001"
