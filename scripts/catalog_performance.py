#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import sqlite3
import statistics
import time
from pathlib import Path
from typing import Any

from snapims.catalog import db as catalog_db
from snapims.catalog.normalization import normalize_title, strip_leading_article
from snapims.catalog.service import search_local


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="SLMC synthetic catalog performance benchmark")
    command.add_argument("--workspace", type=Path, required=True)
    command.add_argument("--movies", type=int, default=100_000)
    command.add_argument("--aliases", type=int, default=500_000)
    command.add_argument("--samples", type=int, default=60)
    command.add_argument("--output", type=Path, required=True)
    return command


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * p)))
    return ordered[index]


def time_calls(function, count: int) -> dict[str, float]:
    values: list[float] = []
    for index in range(count):
        started = time.perf_counter()
        function(index)
        values.append((time.perf_counter() - started) * 1000)
    return {
        "samples": len(values),
        "median_ms": statistics.median(values),
        "p95_ms": percentile(values, 0.95),
        "max_ms": max(values),
    }


def insert_dataset(db_file: Path, movies: int, aliases: int) -> dict[str, Any]:
    started = time.perf_counter()
    timestamp = catalog_db.now()
    with catalog_db.connect(db_file) as connection:
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.execute("BEGIN IMMEDIATE")
        batch: list[tuple[Any, ...]] = []
        for index in range(1, movies + 1):
            title = f"Synthetic Movie {index:06d}"
            normalized = normalize_title(title)
            batch.append(
                (
                    f"MOV-{index:08d}",
                    title,
                    normalized,
                    strip_leading_article(normalized),
                    1900 + (index % 126),
                    "film",
                    "SYNTHETIC",
                    timestamp,
                    timestamp,
                )
            )
            if len(batch) >= 5000:
                connection.executemany(
                    """INSERT INTO movies(
                           movie_id,canonical_title,normalized_title,articleless_title,
                           primary_release_year,media_type,data_quality_status,created_at,updated_at
                       ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    batch,
                )
                batch.clear()
        if batch:
            connection.executemany(
                """INSERT INTO movies(
                       movie_id,canonical_title,normalized_title,articleless_title,
                       primary_release_year,media_type,data_quality_status,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                batch,
            )
        alias_batch: list[tuple[Any, ...]] = []
        for index in range(1, aliases + 1):
            movie_number = ((index - 1) % movies) + 1
            alias = f"Synthetic Alias {index:07d}"
            normalized = normalize_title(alias)
            alias_batch.append(
                (
                    f"MOV-{movie_number:08d}",
                    alias,
                    normalized,
                    strip_leading_article(normalized),
                    "synthetic",
                    "",
                    "PERFORMANCE_FIXTURE",
                    "",
                    timestamp,
                )
            )
            if len(alias_batch) >= 10_000:
                connection.executemany(
                    """INSERT INTO movie_aliases(
                           movie_id,alias,normalized_alias,articleless_alias,alias_type,
                           language,source,source_page_id,created_at
                       ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    alias_batch,
                )
                alias_batch.clear()
        if alias_batch:
            connection.executemany(
                """INSERT INTO movie_aliases(
                       movie_id,alias,normalized_alias,articleless_alias,alias_type,
                       language,source,source_page_id,created_at
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                alias_batch,
            )
        connection.execute(
            "UPDATE catalog_sequences SET next_value=? WHERE name='movie'", (movies + 1,)
        )
        connection.commit()
    return {"insert_seconds": time.perf_counter() - started}


def run(args: argparse.Namespace) -> dict[str, Any]:
    args.workspace.mkdir(parents=True, exist_ok=True)
    db_file = args.workspace / "movie_catalog.sqlite3"
    for suffix in ("", "-wal", "-shm"):
        Path(f"{db_file}{suffix}").unlink(missing_ok=True)
    catalog_db.initialize(db_file)
    insertion = insert_dataset(db_file, args.movies, args.aliases)

    before_fts_size = db_file.stat().st_size
    fts_started = time.perf_counter()
    indexed = catalog_db.rebuild_search_index(db_file)
    fts_seconds = time.perf_counter() - fts_started

    sample_count = max(10, args.samples)
    exact = time_calls(
        lambda index: search_local(
            db_file,
            f"Synthetic Movie {((index * 7919) % args.movies) + 1:06d}",
        ),
        sample_count,
    )
    title_year = time_calls(
        lambda index: search_local(
            db_file,
            f"Synthetic Movie {((index * 7919) % args.movies) + 1:06d}",
            1900 + ((((index * 7919) % args.movies) + 1) % 126),
        ),
        sample_count,
    )
    alias = time_calls(
        lambda index: search_local(
            db_file,
            f"Synthetic Alias {((index * 3571) % args.aliases) + 1:07d}",
        ),
        sample_count,
    )
    fts = time_calls(
        lambda index: search_local(
            db_file,
            f"Synthetic Movie {((index * 1117) % args.movies) + 1:06d} extended",
        ),
        sample_count,
    )

    insert_times: list[float] = []
    with catalog_db.connect(db_file) as connection:
        for index in range(10):
            movie_id = f"MOV-{args.movies + index + 1:08d}"
            title = f"Insertion Probe {index}"
            normalized = normalize_title(title)
            started = time.perf_counter()
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO movies(
                       movie_id,canonical_title,normalized_title,articleless_title,
                       primary_release_year,media_type,data_quality_status,created_at,updated_at
                   ) VALUES(?,?,?,?,?,'film','SYNTHETIC',?,?)""",
                (
                    movie_id,
                    title,
                    normalized,
                    strip_leading_article(normalized),
                    2000 + index,
                    catalog_db.now(),
                    catalog_db.now(),
                ),
            )
            connection.commit()
            insert_times.append((time.perf_counter() - started) * 1000)

    duplicate_prevention: dict[str, Any] = {}
    with catalog_db.connect(db_file) as connection:
        source_title = "Duplicate Prevention Probe"
        normalized = normalize_title(source_title)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """INSERT INTO movies(
                   movie_id,canonical_title,normalized_title,articleless_title,
                   primary_release_year,media_type,data_quality_status,created_at,updated_at
               ) VALUES('MOV-99999991',?,?,?,?, 'film','SYNTHETIC',?,?)""",
            (
                source_title,
                normalized,
                strip_leading_article(normalized),
                2001,
                catalog_db.now(),
                catalog_db.now(),
            ),
        )
        connection.execute(
            """INSERT INTO movie_sources(
                   movie_id,provider_name,source_page_title,source_page_id,source_url,
                   retrieved_at,parser_version,raw_response_hash
               ) VALUES('MOV-99999991','wikipedia','Probe','perf-probe','https://example.invalid',?,?,?)""",
            (catalog_db.now(), "performance", "hash"),
        )
        connection.commit()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO movie_sources(
                       movie_id,provider_name,source_page_title,source_page_id,source_url,
                       retrieved_at,parser_version,raw_response_hash
                   ) VALUES('MOV-99999991','wikipedia','Probe','perf-probe','https://example.invalid',?,?,?)""",
                (catalog_db.now(), "performance", "hash"),
            )
            connection.commit()
            duplicate_prevention = {"prevented": False, "error": ""}
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            duplicate_prevention = {"prevented": True, "error": str(exc)}

    with catalog_db.connect(db_file, readonly=True) as connection:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        movie_count = int(connection.execute("SELECT COUNT(*) FROM movies").fetchone()[0])
        alias_count = int(connection.execute("SELECT COUNT(*) FROM movie_aliases").fetchone()[0])
    result = {
        "package": "SLMC-0.1.0",
        "methodology": "single-process SQLite synthetic benchmark; bounded indexed lookups; timings use time.perf_counter",
        "hardware": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
        },
        "dataset": {
            "requested_movies": args.movies,
            "requested_aliases": args.aliases,
            "actual_movies_including_probes": movie_count,
            "actual_aliases": alias_count,
            "database_size_bytes": db_file.stat().st_size,
            "database_size_before_fts_bytes": before_fts_size,
        },
        "build": {**insertion, "fts_rebuild_seconds": fts_seconds, "fts_indexed_movies": indexed},
        "latency": {
            "exact_title": exact,
            "title_and_year": title_year,
            "exact_alias": alias,
            "fts_candidate": fts,
            "single_movie_insert": {
                "samples": len(insert_times),
                "median_ms": statistics.median(insert_times),
                "p95_ms": percentile(insert_times, 0.95),
                "max_ms": max(insert_times),
            },
        },
        "duplicate_prevention": duplicate_prevention,
        "integrity": integrity,
        "foreign_key_violations": foreign,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    args = parser().parse_args()
    result = run(args)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
