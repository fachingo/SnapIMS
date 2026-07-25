from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from snapims import db as inventory_db
from snapims.catalog import db as catalog_db
from snapims.catalog.normalization import normalize_title, strip_leading_article
from snapims.catalog.service import get_movie, search_local
from snapims.config import DataPaths


def _start_job(paths: DataPaths, operation: str, payload: dict[str, Any]) -> int:
    catalog_db.initialize(paths.catalog_db_file, paths=paths)
    with catalog_db.transaction(paths.catalog_db_file) as connection:
        cursor = connection.execute(
            """INSERT INTO catalog_maintenance_jobs(
                   operation,status,payload_json,created_at,updated_at
               ) VALUES(?,'RUNNING',?,?,?)""",
            (operation, json.dumps(payload, sort_keys=True), catalog_db.now(), catalog_db.now()),
        )
        return int(cursor.lastrowid)


def _finish_job(
    paths: DataPaths,
    job_id: int,
    status: str,
    *,
    result: dict[str, Any] | None = None,
    error: str = "",
) -> None:
    with catalog_db.transaction(paths.catalog_db_file) as connection:
        connection.execute(
            """UPDATE catalog_maintenance_jobs
               SET status=?,result_json=?,last_error=?,updated_at=?,finished_at=CASE WHEN ? IN ('COMPLETE','FAILED') THEN ? ELSE finished_at END
               WHERE maintenance_job_id=?""",
            (
                status,
                json.dumps(result or {}, sort_keys=True),
                error,
                catalog_db.now(),
                status,
                catalog_db.now(),
                job_id,
            ),
        )


def add_alias(
    paths: DataPaths,
    movie_id: str,
    alias: str,
    *,
    alias_type: str = "operator",
    language: str = "",
    source: str = "OPERATOR",
) -> None:
    catalog_db.initialize(paths.catalog_db_file, paths=paths)
    normalized = normalize_title(alias)
    if not normalized:
        raise ValueError("Alias is required")
    with catalog_db.transaction(paths.catalog_db_file) as connection:
        if connection.execute("SELECT 1 FROM movies WHERE movie_id=? AND active=1", (movie_id,)).fetchone() is None:
            raise KeyError(f"Unknown active Movie ID: {movie_id}")
        connection.execute(
            """INSERT OR IGNORE INTO movie_aliases(
                   movie_id,alias,normalized_alias,articleless_alias,alias_type,language,
                   source,source_page_id,created_at
               ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                movie_id,
                alias.strip(),
                normalized,
                strip_leading_article(normalized),
                alias_type,
                language,
                source,
                "",
                catalog_db.now(),
            ),
        )
        connection.execute(
            "UPDATE movies SET catalog_revision=catalog_revision+1,updated_at=? WHERE movie_id=?",
            (catalog_db.now(), movie_id),
        )
        connection.execute(
            """INSERT INTO catalog_events(occurred_at,event_type,movie_id,source,details_json)
               VALUES(?,'ALIAS_ADDED',?,'OPERATOR',?)""",
            (catalog_db.now(), movie_id, json.dumps({"alias": alias.strip()})),
        )
    catalog_db.rebuild_search_index(paths.catalog_db_file)


def _relink_inventory_movie(paths: DataPaths, old_movie_id: str, new_movie_id: str, *, method: str) -> int:
    with inventory_db.connect(paths.db_file) as connection:
        rows = connection.execute(
            "SELECT * FROM item_movie_links WHERE movie_id=? ORDER BY item_id", (old_movie_id,)
        ).fetchall()
    count = 0
    new_movie = get_movie(paths.catalog_db_file, new_movie_id)
    if new_movie is None:
        raise KeyError(new_movie_id)
    for row in rows:
        inventory_db.set_item_movie_link(
            paths.db_file,
            item_id=str(row["item_id"]),
            movie_id=new_movie_id,
            link_status="LOCAL_MATCH",
            link_method=method,
            recognition_result_id=int(row["recognition_result_id"] or 0),
            match_score=float(row["match_score"] or 1.0),
            operator_confirmed=True,
            catalog_revision=int(new_movie["catalog_revision"]),
        )
        count += 1
    return count


def merge_movies(paths: DataPaths, survivor_movie_id: str, duplicate_movie_id: str) -> dict[str, Any]:
    """Merge duplicate Movie business data and relink physical Items explicitly.

    The catalog commit occurs first. A durable maintenance job remains LINK_PENDING
    if inventory relinking fails, so the operation can be reconciled after restart.
    """

    if survivor_movie_id == duplicate_movie_id:
        raise ValueError("Survivor and duplicate Movie IDs must differ")
    catalog_db.backup_catalog(paths, "before-movie-merge")
    inventory_db.backup_database(paths, "before-movie-merge")
    payload = {"survivor_movie_id": survivor_movie_id, "duplicate_movie_id": duplicate_movie_id}
    job_id = _start_job(paths, "MERGE", payload)
    try:
        with catalog_db.transaction(paths.catalog_db_file) as connection:
            survivor = connection.execute(
                "SELECT * FROM movies WHERE movie_id=? AND active=1", (survivor_movie_id,)
            ).fetchone()
            duplicate = connection.execute(
                "SELECT * FROM movies WHERE movie_id=? AND active=1", (duplicate_movie_id,)
            ).fetchone()
            if survivor is None or duplicate is None:
                raise KeyError("Both Movies must exist and be active")
            for table, columns in (
                (
                    "movie_aliases",
                    "alias,normalized_alias,articleless_alias,alias_type,language,source,source_page_id,created_at",
                ),
                ("movie_titles", "title,normalized_title,title_type,language,region,source,created_at"),
                (
                    "movie_credits",
                    "person_name,credit_type,billing_order,source,created_at",
                ),
                ("movie_genres", "genre,source"),
                ("movie_countries", "country,source"),
                ("movie_languages", "language,source"),
            ):
                column_list = columns.split(",")
                rows = connection.execute(
                    f"SELECT {columns} FROM {table} WHERE movie_id=?", (duplicate_movie_id,)
                ).fetchall()
                placeholders = ",".join("?" for _ in range(len(column_list) + 1))
                connection.executemany(
                    f"INSERT OR IGNORE INTO {table}(movie_id,{columns}) VALUES({placeholders})",
                    [(survivor_movie_id, *tuple(row)) for row in rows],
                )
                connection.execute(f"DELETE FROM {table} WHERE movie_id=?", (duplicate_movie_id,))
            connection.execute(
                "UPDATE movie_sources SET movie_id=? WHERE movie_id=?",
                (survivor_movie_id, duplicate_movie_id),
            )
            connection.execute(
                """UPDATE movies SET active=0,data_quality_status='MERGED',updated_at=?
                   WHERE movie_id=?""",
                (catalog_db.now(), duplicate_movie_id),
            )
            connection.execute(
                """UPDATE movies SET catalog_revision=catalog_revision+1,updated_at=?
                   WHERE movie_id=?""",
                (catalog_db.now(), survivor_movie_id),
            )
            connection.execute(
                """INSERT INTO catalog_events(occurred_at,event_type,movie_id,source,details_json)
                   VALUES(?,'MOVIE_MERGED',?,'OPERATOR',?)""",
                (catalog_db.now(), survivor_movie_id, json.dumps(payload)),
            )
            connection.execute(
                """UPDATE catalog_maintenance_jobs SET status='CATALOG_COMMITTED',updated_at=?
                   WHERE maintenance_job_id=?""",
                (catalog_db.now(), job_id),
            )
        catalog_db.rebuild_search_index(paths.catalog_db_file)
        try:
            relinked = _relink_inventory_movie(
                paths, duplicate_movie_id, survivor_movie_id, method="MOVIE_MERGE"
            )
        except Exception as exc:
            _finish_job(paths, job_id, "LINK_PENDING", error=str(exc))
            raise
        result = {"maintenance_job_id": job_id, "survivor_movie_id": survivor_movie_id, "merged_movie_id": duplicate_movie_id, "relinked_items": relinked}
        _finish_job(paths, job_id, "COMPLETE", result=result)
        return result
    except Exception as exc:
        with catalog_db.connect(paths.catalog_db_file, readonly=True) as connection:
            row = connection.execute(
                "SELECT status FROM catalog_maintenance_jobs WHERE maintenance_job_id=?", (job_id,)
            ).fetchone()
        if row and str(row[0]) == "RUNNING":
            _finish_job(paths, job_id, "FAILED", error=str(exc))
        raise


def split_movie(
    paths: DataPaths,
    source_movie_id: str,
    *,
    canonical_title: str,
    release_year: int | None,
    item_ids: list[str],
    alias_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Create a distinct Movie and move only explicitly selected evidence/items."""

    if not item_ids:
        raise ValueError("At least one linked Item must be selected for a split")
    catalog_db.backup_catalog(paths, "before-movie-split")
    inventory_db.backup_database(paths, "before-movie-split")
    payload = {
        "source_movie_id": source_movie_id,
        "canonical_title": canonical_title,
        "release_year": release_year,
        "item_ids": sorted(item_ids),
        "alias_ids": sorted(alias_ids or []),
    }
    job_id = _start_job(paths, "SPLIT", payload)
    try:
        with catalog_db.transaction(paths.catalog_db_file) as connection:
            source = connection.execute(
                "SELECT * FROM movies WHERE movie_id=? AND active=1", (source_movie_id,)
            ).fetchone()
            if source is None:
                raise KeyError(source_movie_id)
            new_movie_id = catalog_db.next_movie_id(connection)
            normalized = normalize_title(canonical_title)
            connection.execute(
                """INSERT INTO movies(
                       movie_id,canonical_title,normalized_title,articleless_title,original_title,
                       primary_release_year,media_type,active,data_quality_status,catalog_revision,
                       created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    new_movie_id,
                    canonical_title.strip(),
                    normalized,
                    strip_leading_article(normalized),
                    "",
                    release_year,
                    str(source["media_type"]),
                    1,
                    "OPERATOR_CONFIRMED_SPLIT",
                    1,
                    catalog_db.now(),
                    catalog_db.now(),
                ),
            )
            connection.execute(
                """INSERT INTO movie_aliases(
                       movie_id,alias,normalized_alias,articleless_alias,alias_type,source,created_at
                   ) VALUES(?,?,?,?,?,'OPERATOR',?)""",
                (
                    new_movie_id,
                    canonical_title.strip(),
                    normalized,
                    strip_leading_article(normalized),
                    "canonical",
                    catalog_db.now(),
                ),
            )
            for alias_id in alias_ids or []:
                connection.execute(
                    "UPDATE movie_aliases SET movie_id=? WHERE alias_id=? AND movie_id=?",
                    (new_movie_id, alias_id, source_movie_id),
                )
            connection.execute(
                "UPDATE movies SET catalog_revision=catalog_revision+1,updated_at=? WHERE movie_id=?",
                (catalog_db.now(), source_movie_id),
            )
            connection.execute(
                """INSERT INTO catalog_events(occurred_at,event_type,movie_id,source,details_json)
                   VALUES(?,'MOVIE_SPLIT',?,'OPERATOR',?)""",
                (catalog_db.now(), source_movie_id, json.dumps({**payload, "new_movie_id": new_movie_id})),
            )
            connection.execute(
                "UPDATE catalog_maintenance_jobs SET status='CATALOG_COMMITTED',result_json=?,updated_at=? WHERE maintenance_job_id=?",
                (json.dumps({"new_movie_id": new_movie_id}), catalog_db.now(), job_id),
            )
        catalog_db.rebuild_search_index(paths.catalog_db_file)
        new_movie = get_movie(paths.catalog_db_file, new_movie_id)
        assert new_movie is not None
        relinked = 0
        for item_id in item_ids:
            current = inventory_db.get_item_movie_link(paths.db_file, item_id)
            if current is None or str(current.get("movie_id") or "") != source_movie_id:
                raise ValueError(f"Item is not currently linked to source Movie: {item_id}")
            inventory_db.set_item_movie_link(
                paths.db_file,
                item_id=item_id,
                movie_id=new_movie_id,
                link_status="LOCAL_MATCH",
                link_method="MOVIE_SPLIT",
                recognition_result_id=int(current.get("recognition_result_id") or 0),
                match_score=float(current.get("match_score") or 1.0),
                operator_confirmed=True,
                catalog_revision=int(new_movie["catalog_revision"]),
            )
            relinked += 1
        result = {"maintenance_job_id": job_id, "source_movie_id": source_movie_id, "new_movie_id": new_movie_id, "relinked_items": relinked}
        _finish_job(paths, job_id, "COMPLETE", result=result)
        return result
    except Exception as exc:
        with catalog_db.connect(paths.catalog_db_file, readonly=True) as connection:
            row = connection.execute(
                "SELECT status FROM catalog_maintenance_jobs WHERE maintenance_job_id=?", (job_id,)
            ).fetchone()
        if row and str(row[0]) == "CATALOG_COMMITTED":
            _finish_job(paths, job_id, "LINK_PENDING", error=str(exc))
        else:
            _finish_job(paths, job_id, "FAILED", error=str(exc))
        raise


def reconcile_maintenance_jobs(paths: DataPaths) -> int:
    catalog_db.initialize(paths.catalog_db_file, create=False)
    with catalog_db.connect(paths.catalog_db_file, readonly=True) as connection:
        rows = connection.execute(
            "SELECT * FROM catalog_maintenance_jobs WHERE status='LINK_PENDING' ORDER BY maintenance_job_id"
        ).fetchall()
    completed = 0
    for row in rows:
        payload = json.loads(str(row["payload_json"]))
        try:
            if row["operation"] == "MERGE":
                relinked = _relink_inventory_movie(
                    paths,
                    str(payload["duplicate_movie_id"]),
                    str(payload["survivor_movie_id"]),
                    method="MOVIE_MERGE_RECONCILIATION",
                )
                result = {"relinked_items": relinked, **payload}
            else:
                continue
            _finish_job(paths, int(row["maintenance_job_id"]), "COMPLETE", result=result)
            completed += 1
        except Exception as exc:
            _finish_job(paths, int(row["maintenance_job_id"]), "LINK_PENDING", error=str(exc))
    return completed


def manual_search(paths: DataPaths, title: str, year: int | None = None) -> list[dict[str, Any]]:
    return [
        {
            "movie_id": row.movie_id,
            "canonical_title": row.canonical_title,
            "release_year": row.primary_release_year,
            "score": row.match_score,
            "method": row.method,
            "reason": row.reason,
            "unique": row.unique,
        }
        for row in search_local(paths.catalog_db_file, title, year)
    ]


def import_catalog_json(paths: DataPaths, source: Path) -> dict[str, int]:
    """Import a documented SLMC JSON package without replacing either database."""

    payload = json.loads(source.read_text(encoding="utf-8"))
    manifest = payload.get("manifest") or {}
    if int(manifest.get("schema_version") or 0) != catalog_db.CATALOG_SCHEMA_VERSION:
        raise ValueError("Catalog package schema version is incompatible")
    catalog_db.backup_catalog(paths, "before-catalog-import")
    counts: dict[str, int] = {}
    tables = (
        "movies",
        "movie_aliases",
        "movie_titles",
        "movie_sources",
        "movie_credits",
        "movie_genres",
        "movie_countries",
        "movie_languages",
    )
    with catalog_db.transaction(paths.catalog_db_file) as connection:
        for table in tables:
            rows = payload.get(table) or []
            if not rows:
                counts[table] = 0
                continue
            columns = list(rows[0])
            placeholders = ",".join("?" for _ in columns)
            before = connection.total_changes
            connection.executemany(
                f"INSERT OR IGNORE INTO {table}({','.join(columns)}) VALUES({placeholders})",
                [[row.get(column) for column in columns] for row in rows],
            )
            counts[table] = connection.total_changes - before
        max_id = connection.execute(
            "SELECT COALESCE(MAX(CAST(SUBSTR(movie_id,5) AS INTEGER)),0)+1 FROM movies WHERE movie_id GLOB 'MOV-[0-9]*'"
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO catalog_sequences(name,next_value) VALUES('movie',?)
               ON CONFLICT(name) DO UPDATE SET next_value=MAX(next_value,excluded.next_value)""",
            (int(max_id),),
        )
        connection.execute(
            """INSERT INTO catalog_events(occurred_at,event_type,source,details_json)
               VALUES(?,'CATALOG_IMPORTED','ADMIN',?)""",
            (catalog_db.now(), json.dumps({"source": str(source), "counts": counts})),
        )
    catalog_db.rebuild_search_index(paths.catalog_db_file)
    return counts
