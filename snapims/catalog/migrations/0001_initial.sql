-- SLMC catalog schema 1 reference migration.
-- Runtime migration, FTS fallback, ledger hash, structural verification, backup,
-- and post-migration integrity checks are implemented in snapims/catalog/db.py.
CREATE TABLE IF NOT EXISTS catalog_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    description TEXT NOT NULL,
    schema_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS catalog_sequences (name TEXT PRIMARY KEY, next_value INTEGER NOT NULL);
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
CREATE TABLE IF NOT EXISTS catalog_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
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
-- Optional when SQLite FTS5 is available:
-- CREATE VIRTUAL TABLE movie_search USING fts5(movie_id UNINDEXED,title,aliases,tokenize='unicode61 remove_diacritics 2');
