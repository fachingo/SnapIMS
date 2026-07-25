from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from snapims.config import DataPaths

CATALOG_SCHEMA_VERSION = 1
CATALOG_PARSER_VERSION = "slmc-wikipedia-1"


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def connect(db_file: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        connection = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True, timeout=30)
    else:
        db_file.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(db_file, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    if not readonly:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
    return connection


@contextmanager
def transaction(db_file: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(db_file)
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def backup_catalog(paths: DataPaths, reason: str) -> Path | None:
    source_file = paths.catalog_db_file
    if not source_file.exists():
        return None
    paths.backups.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() else "-" for ch in reason).strip("-")
    destination = paths.backups / (
        f"movie-catalog-{datetime.now():%Y%m%d-%H%M%S-%f}-{safe or 'backup'}.sqlite3"
    )
    source = connect(source_file, readonly=True)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return destination


def _restore_database(db_file: Path, backup: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        Path(f"{db_file}{suffix}").unlink(missing_ok=True)
    db_file.unlink(missing_ok=True)
    shutil.copy2(backup, db_file)


def _base_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS catalog_schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL,
            description TEXT NOT NULL,
            schema_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS catalog_sequences (
            name TEXT PRIMARY KEY,
            next_value INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS movies (
            movie_id TEXT PRIMARY KEY,
            canonical_title TEXT NOT NULL,
            normalized_title TEXT NOT NULL,
            articleless_title TEXT NOT NULL,
            original_title TEXT NOT NULL DEFAULT '',
            primary_release_year INTEGER,
            release_date TEXT,
            media_type TEXT NOT NULL DEFAULT 'film',
            runtime_minutes INTEGER,
            concise_summary TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            data_quality_status TEXT NOT NULL DEFAULT 'PROVISIONAL',
            catalog_revision INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK(primary_release_year IS NULL OR primary_release_year BETWEEN 1870 AND 2200),
            CHECK(runtime_minutes IS NULL OR runtime_minutes BETWEEN 1 AND 10000)
        );
        CREATE TABLE IF NOT EXISTS movie_aliases (
            alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
            movie_id TEXT NOT NULL REFERENCES movies(movie_id) ON DELETE RESTRICT,
            alias TEXT NOT NULL,
            normalized_alias TEXT NOT NULL,
            articleless_alias TEXT NOT NULL,
            alias_type TEXT NOT NULL DEFAULT 'alternate',
            language TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            source_page_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE(movie_id, normalized_alias, alias_type, language)
        );
        CREATE TABLE IF NOT EXISTS movie_titles (
            title_id INTEGER PRIMARY KEY AUTOINCREMENT,
            movie_id TEXT NOT NULL REFERENCES movies(movie_id) ON DELETE RESTRICT,
            title TEXT NOT NULL,
            normalized_title TEXT NOT NULL,
            title_type TEXT NOT NULL,
            language TEXT NOT NULL DEFAULT '',
            region TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE(movie_id, normalized_title, title_type, language, region)
        );
        CREATE TABLE IF NOT EXISTS movie_sources (
            movie_source_id INTEGER PRIMARY KEY AUTOINCREMENT,
            movie_id TEXT NOT NULL REFERENCES movies(movie_id) ON DELETE RESTRICT,
            provider_name TEXT NOT NULL,
            source_page_title TEXT NOT NULL,
            source_page_id TEXT NOT NULL,
            source_url TEXT NOT NULL,
            source_revision_id TEXT NOT NULL DEFAULT '',
            retrieved_at TEXT NOT NULL,
            parser_version TEXT NOT NULL,
            raw_response_hash TEXT NOT NULL,
            attribution_data TEXT NOT NULL DEFAULT '',
            refresh_eligible INTEGER NOT NULL DEFAULT 1,
            field_provenance_json TEXT NOT NULL DEFAULT '{}',
            active INTEGER NOT NULL DEFAULT 1,
            UNIQUE(provider_name, source_page_id)
        );
        CREATE TABLE IF NOT EXISTS movie_credits (
            credit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            movie_id TEXT NOT NULL REFERENCES movies(movie_id) ON DELETE RESTRICT,
            person_name TEXT NOT NULL,
            credit_type TEXT NOT NULL,
            billing_order INTEGER,
            source TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE(movie_id, person_name, credit_type)
        );
        CREATE TABLE IF NOT EXISTS movie_genres (
            movie_id TEXT NOT NULL REFERENCES movies(movie_id) ON DELETE RESTRICT,
            genre TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(movie_id, genre)
        );
        CREATE TABLE IF NOT EXISTS movie_countries (
            movie_id TEXT NOT NULL REFERENCES movies(movie_id) ON DELETE RESTRICT,
            country TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(movie_id, country)
        );
        CREATE TABLE IF NOT EXISTS movie_languages (
            movie_id TEXT NOT NULL REFERENCES movies(movie_id) ON DELETE RESTRICT,
            language TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(movie_id, language)
        );
        CREATE TABLE IF NOT EXISTS movie_candidates (
            candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL REFERENCES catalog_lookup_jobs(job_id) ON DELETE RESTRICT,
            provider_name TEXT NOT NULL,
            source_page_id TEXT NOT NULL,
            source_page_title TEXT NOT NULL,
            source_url TEXT NOT NULL DEFAULT '',
            canonical_title TEXT NOT NULL DEFAULT '',
            release_year INTEGER,
            media_type TEXT NOT NULL DEFAULT '',
            score REAL NOT NULL DEFAULT 0,
            evidence_json TEXT NOT NULL DEFAULT '[]',
            rejected_reason TEXT NOT NULL DEFAULT '',
            candidate_payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            UNIQUE(job_id, provider_name, source_page_id)
        );
        CREATE TABLE IF NOT EXISTS movie_match_decisions (
            decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL REFERENCES catalog_lookup_jobs(job_id) ON DELETE RESTRICT,
            item_id TEXT NOT NULL,
            recognition_result_id INTEGER NOT NULL,
            selected_movie_id TEXT REFERENCES movies(movie_id) ON DELETE RESTRICT,
            selected_candidate_id INTEGER REFERENCES movie_candidates(candidate_id) ON DELETE RESTRICT,
            decision_type TEXT NOT NULL,
            decision_reason TEXT NOT NULL,
            match_score REAL,
            operator_confirmed INTEGER NOT NULL DEFAULT 0,
            decided_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS catalog_lookup_jobs (
            job_id INTEGER PRIMARY KEY AUTOINCREMENT,
            recognition_result_id INTEGER NOT NULL UNIQUE,
            item_id TEXT NOT NULL,
            proposed_title TEXT NOT NULL,
            normalized_title TEXT NOT NULL,
            proposed_year INTEGER,
            request_json TEXT NOT NULL,
            status TEXT NOT NULL,
            selected_movie_id TEXT REFERENCES movies(movie_id) ON DELETE RESTRICT,
            link_state TEXT NOT NULL DEFAULT 'NOT_LINKED',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            candidate_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            next_retry_at TEXT,
            lease_owner TEXT NOT NULL DEFAULT '',
            lease_expires_at TEXT
        );
        CREATE TABLE IF NOT EXISTS catalog_lookup_attempts (
            attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL REFERENCES catalog_lookup_jobs(job_id) ON DELETE RESTRICT,
            phase TEXT NOT NULL,
            provider_name TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            request_hash TEXT NOT NULL DEFAULT '',
            response_hash TEXT NOT NULL DEFAULT '',
            http_status INTEGER,
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS wikipedia_response_cache (
            cache_key TEXT PRIMARY KEY,
            request_url TEXT NOT NULL,
            response_json TEXT NOT NULL,
            response_hash TEXT NOT NULL,
            http_status INTEGER NOT NULL,
            retrieved_at TEXT NOT NULL,
            expires_at TEXT,
            etag TEXT NOT NULL DEFAULT '',
            last_modified TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS catalog_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS catalog_maintenance_jobs (
            maintenance_job_id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            result_json TEXT NOT NULL DEFAULT '{}',
            last_error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            finished_at TEXT
        );
        CREATE TABLE IF NOT EXISTS catalog_events (
            catalog_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            occurred_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            movie_id TEXT REFERENCES movies(movie_id) ON DELETE RESTRICT,
            item_id TEXT NOT NULL DEFAULT '',
            recognition_result_id INTEGER,
            catalog_revision INTEGER,
            source TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_movies_normalized ON movies(normalized_title, primary_release_year);
        CREATE INDEX IF NOT EXISTS idx_movies_articleless ON movies(articleless_title, primary_release_year);
        CREATE INDEX IF NOT EXISTS idx_alias_normalized ON movie_aliases(normalized_alias);
        CREATE INDEX IF NOT EXISTS idx_alias_articleless ON movie_aliases(articleless_alias);
        CREATE INDEX IF NOT EXISTS idx_sources_movie ON movie_sources(movie_id, active);
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON catalog_lookup_jobs(status, updated_at);
        CREATE INDEX IF NOT EXISTS idx_jobs_item ON catalog_lookup_jobs(item_id, recognition_result_id DESC);
        CREATE INDEX IF NOT EXISTS idx_candidates_job_score ON movie_candidates(job_id, score DESC);
        CREATE INDEX IF NOT EXISTS idx_events_movie ON catalog_events(movie_id, occurred_at DESC);
        CREATE INDEX IF NOT EXISTS idx_maintenance_status ON catalog_maintenance_jobs(status, updated_at);
        """
    )
    connection.execute(
        "INSERT OR IGNORE INTO catalog_sequences(name,next_value) VALUES('movie',1)"
    )
    try:
        connection.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS movie_search USING fts5(
                   movie_id UNINDEXED,
                   title,
                   aliases,
                   tokenize='unicode61 remove_diacritics 2'
               )"""
        )
        connection.execute(
            "INSERT OR IGNORE INTO catalog_settings(key,value,updated_at) VALUES('fts_available','1',?)",
            (now(),),
        )
    except sqlite3.OperationalError:
        connection.execute(
            "INSERT OR REPLACE INTO catalog_settings(key,value,updated_at) VALUES('fts_available','0',?)",
            (now(),),
        )


def expected_manifest() -> dict[str, tuple[str, ...]]:
    return {
        "movies": (
            "movie_id",
            "canonical_title",
            "normalized_title",
            "articleless_title",
            "primary_release_year",
            "catalog_revision",
        ),
        "movie_aliases": ("movie_id", "alias", "normalized_alias", "articleless_alias"),
        "movie_sources": ("movie_id", "provider_name", "source_page_id", "source_url"),
        "catalog_lookup_jobs": ("recognition_result_id", "item_id", "status", "link_state"),
        "movie_candidates": ("job_id", "source_page_id", "score", "candidate_payload_json"),
        "catalog_events": ("event_type", "movie_id", "details_json"),
        "catalog_maintenance_jobs": ("operation", "status", "payload_json", "result_json"),
    }


def schema_hash(connection: sqlite3.Connection) -> str:
    rows = connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
    ).fetchall()
    payload = "\n".join("|".join(str(value or "") for value in row) for row in rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_structure(connection: sqlite3.Connection) -> list[str]:
    errors: list[str] = []
    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")
    }
    for table, required_columns in expected_manifest().items():
        if table not in tables:
            errors.append(f"Missing required catalog table: {table}")
            continue
        columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
        for column in required_columns:
            if column not in columns:
                errors.append(f"Missing required catalog column: {table}.{column}")
    return errors


def initialize(db_file: Path, *, paths: DataPaths | None = None, create: bool = True) -> None:
    db_file.parent.mkdir(parents=True, exist_ok=True)
    exists = db_file.exists() and db_file.stat().st_size > 0
    if not exists and not create:
        raise FileNotFoundError(f"Catalog database does not exist: {db_file}")
    current = 0
    if exists:
        probe = connect(db_file, readonly=True)
        try:
            current = int(probe.execute("PRAGMA user_version").fetchone()[0])
            integrity = str(probe.execute("PRAGMA integrity_check").fetchone()[0])
        finally:
            probe.close()
        if integrity != "ok":
            raise RuntimeError(
                f"Catalog database integrity failure: {integrity}. The file was left untouched."
            )
        if current > CATALOG_SCHEMA_VERSION:
            raise RuntimeError(
                f"Catalog schema {current} is newer than supported schema {CATALOG_SCHEMA_VERSION}."
            )
        if current == CATALOG_SCHEMA_VERSION:
            readonly = connect(db_file, readonly=True)
            try:
                errors = verify_structure(readonly)
                foreign = readonly.execute("PRAGMA foreign_key_check").fetchall()
            finally:
                readonly.close()
            if errors or foreign:
                raise RuntimeError(
                    "Catalog schema is structurally incompatible: "
                    + "; ".join([*errors, f"foreign-key violations={len(foreign)}"])
                )
            return

    backup: Path | None = None
    if exists and paths is not None:
        backup = backup_catalog(paths, f"before-catalog-schema-v{CATALOG_SCHEMA_VERSION}")
    try:
        with transaction(db_file) as connection:
            _base_schema(connection)
            errors = verify_structure(connection)
            if errors:
                raise RuntimeError("; ".join(errors))
            digest = schema_hash(connection)
            connection.execute(
                """INSERT OR REPLACE INTO catalog_schema_migrations(
                       version,applied_at,description,schema_hash
                   ) VALUES(?,?,?,?)""",
                (
                    CATALOG_SCHEMA_VERSION,
                    now(),
                    "SLMC permanent local movie catalog foundation",
                    digest,
                ),
            )
            defaults = {
                "local_exact_threshold": "0.90",
                "local_fuzzy_threshold": "0.78",
                "automatic_wikipedia_threshold": "0.92",
                "candidate_margin": "0.08",
                "wikipedia_enabled": "1",
                "wikipedia_max_candidates": "5",
                "wikipedia_min_interval_seconds": "1.0",
                "wikipedia_timeout_seconds": "10",
                "wikipedia_max_retries": "2",
                "media_type": "film",
            }
            for key, value in defaults.items():
                connection.execute(
                    "INSERT OR IGNORE INTO catalog_settings(key,value,updated_at) VALUES(?,?,?)",
                    (key, value, now()),
                )
            connection.execute(f"PRAGMA user_version = {CATALOG_SCHEMA_VERSION}")
        check = connect(db_file, readonly=True)
        try:
            integrity = str(check.execute("PRAGMA integrity_check").fetchone()[0])
            foreign = check.execute("PRAGMA foreign_key_check").fetchall()
        finally:
            check.close()
        if integrity != "ok" or foreign:
            raise RuntimeError(
                f"Catalog migration verification failed: integrity={integrity}; foreign={len(foreign)}"
            )
    except Exception:
        if backup is not None and backup.exists():
            _restore_database(db_file, backup)
        elif not exists:
            for suffix in ("", "-wal", "-shm", "-journal"):
                Path(f"{db_file}{suffix}").unlink(missing_ok=True)
        raise


def get_setting(db_file: Path, key: str, default: str = "") -> str:
    initialize(db_file)
    with connect(db_file, readonly=True) as connection:
        row = connection.execute("SELECT value FROM catalog_settings WHERE key=?", (key,)).fetchone()
    return str(row[0]) if row else default


def set_setting(db_file: Path, key: str, value: str) -> None:
    initialize(db_file)
    with transaction(db_file) as connection:
        connection.execute(
            """INSERT INTO catalog_settings(key,value,updated_at) VALUES(?,?,?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
            (key, value, now()),
        )


def next_movie_id(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT next_value FROM catalog_sequences WHERE name='movie'"
    ).fetchone()
    value = int(row[0]) if row else 1
    connection.execute(
        """INSERT INTO catalog_sequences(name,next_value) VALUES('movie',?)
           ON CONFLICT(name) DO UPDATE SET next_value=excluded.next_value""",
        (value + 1,),
    )
    return f"MOV-{value:08d}"


def rebuild_search_index(db_file: Path) -> int:
    initialize(db_file)
    with transaction(db_file) as connection:
        available = connection.execute(
            "SELECT value FROM catalog_settings WHERE key='fts_available'"
        ).fetchone()
        if not available or str(available[0]) != "1":
            return 0
        connection.execute("DELETE FROM movie_search")
        rows = connection.execute(
            """SELECT m.movie_id,m.canonical_title,
                      COALESCE(GROUP_CONCAT(a.alias,' | '),'')
               FROM movies m
               LEFT JOIN movie_aliases a ON a.movie_id=m.movie_id
               WHERE m.active=1
               GROUP BY m.movie_id"""
        ).fetchall()
        connection.executemany(
            "INSERT INTO movie_search(movie_id,title,aliases) VALUES(?,?,?)",
            rows,
        )
    return len(rows)


def catalog_summary(db_file: Path) -> dict[str, Any]:
    initialize(db_file, create=False)
    with connect(db_file, readonly=True) as connection:
        counts = {
            "movies": int(connection.execute("SELECT COUNT(*) FROM movies WHERE active=1").fetchone()[0]),
            "aliases": int(connection.execute("SELECT COUNT(*) FROM movie_aliases").fetchone()[0]),
            "wikipedia_calls": int(connection.execute(
                "SELECT COUNT(*) FROM catalog_lookup_attempts WHERE provider_name='wikipedia'"
            ).fetchone()[0]),
            "new_movie_records": int(connection.execute(
                "SELECT COUNT(*) FROM catalog_events WHERE event_type='MOVIE_CREATED'"
            ).fetchone()[0]),
            "ambiguous_matches": int(connection.execute(
                "SELECT COUNT(*) FROM catalog_lookup_jobs WHERE status='AMBIGUOUS'"
            ).fetchone()[0]),
            "failed_jobs": int(connection.execute(
                "SELECT COUNT(*) FROM catalog_lookup_jobs WHERE status='FAILED'"
            ).fetchone()[0]),
            "local_hits": int(connection.execute(
                "SELECT COUNT(*) FROM movie_match_decisions WHERE decision_type='AUTO_LOCAL'"
            ).fetchone()[0]),
            "wikipedia_misses": int(connection.execute(
                "SELECT COUNT(*) FROM catalog_lookup_jobs WHERE attempt_count>0"
            ).fetchone()[0]),
        }
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        schema = int(connection.execute("PRAGMA user_version").fetchone()[0])
        fts = get_setting(db_file, "fts_available", "0")
        last_external = connection.execute(
            """SELECT finished_at FROM catalog_lookup_attempts
               WHERE provider_name='wikipedia' AND status='SUCCESS'
               ORDER BY attempt_id DESC LIMIT 1"""
        ).fetchone()
        latest_external = connection.execute(
            """SELECT status,error_code,error_message,finished_at FROM catalog_lookup_attempts
               WHERE provider_name='wikipedia' ORDER BY attempt_id DESC LIMIT 1"""
        ).fetchone()
        suspected_duplicates = int(connection.execute(
            """SELECT COUNT(*) FROM (
                   SELECT normalized_title,primary_release_year,media_type
                   FROM movies WHERE active=1
                   GROUP BY normalized_title,primary_release_year,media_type
                   HAVING COUNT(*) > 1
               )"""
        ).fetchone()[0])
        pending_maintenance = int(connection.execute(
            "SELECT COUNT(*) FROM catalog_maintenance_jobs WHERE status NOT IN ('COMPLETE','FAILED')"
        ).fetchone()[0])
        fts_rows = 0
        if fts == "1":
            try:
                fts_rows = int(connection.execute("SELECT COUNT(*) FROM movie_search").fetchone()[0])
            except sqlite3.OperationalError:
                fts_rows = -1
    backup_dir = db_file.parent.parent / "backups"
    backups = sorted(backup_dir.glob("movie-catalog-*.sqlite3"), key=lambda path: path.stat().st_mtime)
    rate_limit_state = "CLEAR"
    if latest_external and str(latest_external[1] or "") == "RATE_LIMIT":
        rate_limit_state = "RATE_LIMITED"
    elif latest_external and str(latest_external[0] or "") == "FAILED":
        rate_limit_state = "LAST_LOOKUP_FAILED"
    return {
        **counts,
        "integrity": integrity,
        "foreign_key_violations": foreign,
        "schema_version": schema,
        "fts_available": fts == "1",
        "fts_index_rows": fts_rows,
        "fts_index_healthy": (fts != "1") or fts_rows == counts["movies"],
        "suspected_duplicate_movies": suspected_duplicates,
        "pending_maintenance_jobs": pending_maintenance,
        "rate_limit_state": rate_limit_state,
        "database_size_bytes": db_file.stat().st_size if db_file.exists() else 0,
        "last_backup": str(backups[-1]) if backups else "",
        "last_successful_external_lookup": str(last_external[0]) if last_external else "",
    }


def export_catalog_json(db_file: Path, destination: Path) -> Path:
    initialize(db_file, create=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_file, readonly=True) as connection:
        payload: dict[str, Any] = {
            "manifest": {
                "schema_version": CATALOG_SCHEMA_VERSION,
                "exported_at": now(),
                "schema_hash": schema_hash(connection),
            }
        }
        for table in (
            "movies",
            "movie_aliases",
            "movie_titles",
            "movie_sources",
            "movie_credits",
            "movie_genres",
            "movie_countries",
            "movie_languages",
        ):
            payload[table] = [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]
    destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return destination
