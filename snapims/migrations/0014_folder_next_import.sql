-- SnapIMS inventory schema 14: v0.13.0 folder-based NEXT-only Import.
-- Runtime upgrades are orchestrated transactionally by snapims.db.initialize.
-- This file documents the additive schema objects and indexes shipped with the release.

ALTER TABLE batches ADD COLUMN display_name TEXT NOT NULL DEFAULT '';
ALTER TABLE batches ADD COLUMN source_folder_name TEXT NOT NULL DEFAULT '';
ALTER TABLE batches ADD COLUMN batch_location TEXT;
ALTER TABLE batches ADD COLUMN import_job_id TEXT NOT NULL DEFAULT '';
ALTER TABLE items ADD COLUMN location TEXT;

CREATE TABLE IF NOT EXISTS import_photo_cache (
    source_path TEXT PRIMARY KEY,
    cache_id TEXT NOT NULL DEFAULT '',
    folder_path TEXT NOT NULL,
    original_name TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    device INTEGER NOT NULL DEFAULT 0,
    inode INTEGER NOT NULL DEFAULT 0,
    captured_at TEXT NOT NULL,
    timestamp_source TEXT NOT NULL,
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    qr_payload TEXT,
    classification TEXT NOT NULL,
    read_error TEXT NOT NULL DEFAULT '',
    thumbnail_path TEXT NOT NULL DEFAULT '',
    sha256 TEXT NOT NULL DEFAULT '',
    scanned_at TEXT NOT NULL,
    decode_count INTEGER NOT NULL DEFAULT 0,
    qr_scan_count INTEGER NOT NULL DEFAULT 0,
    full_resolution_fallbacks INTEGER NOT NULL DEFAULT 0,
    filesystem_reads INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS import_photo_corrections (
    folder_path TEXT NOT NULL,
    source_path TEXT NOT NULL,
    action TEXT NOT NULL DEFAULT 'auto'
        CHECK(action IN ('auto','product','next','ignore')),
    split_before INTEGER NOT NULL DEFAULT 0 CHECK(split_before IN (0,1)),
    merge_previous INTEGER NOT NULL DEFAULT 0 CHECK(merge_previous IN (0,1)),
    updated_at TEXT NOT NULL,
    PRIMARY KEY(folder_path, source_path)
);

CREATE TABLE IF NOT EXISTS import_jobs (
    job_id TEXT PRIMARY KEY,
    folder_path TEXT NOT NULL,
    folder_name TEXT NOT NULL,
    batch_name TEXT NOT NULL,
    batch_location TEXT,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    processed_count INTEGER NOT NULL DEFAULT 0,
    total_count INTEGER NOT NULL DEFAULT 0,
    preview_json TEXT NOT NULL DEFAULT '{}',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    started_at TEXT,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    decode_count INTEGER NOT NULL DEFAULT 0,
    qr_scan_count INTEGER NOT NULL DEFAULT 0,
    full_hash_count INTEGER NOT NULL DEFAULT 0,
    filesystem_reads INTEGER NOT NULL DEFAULT 0,
    cache_hits INTEGER NOT NULL DEFAULT 0,
    cache_misses INTEGER NOT NULL DEFAULT 0,
    result_batch_id TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_import_photo_cache_folder
    ON import_photo_cache(folder_path, captured_at, original_name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_import_photo_cache_id
    ON import_photo_cache(cache_id) WHERE cache_id <> '';
CREATE INDEX IF NOT EXISTS idx_import_jobs_folder
    ON import_jobs(folder_path, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_import_jobs_status
    ON import_jobs(status, updated_at DESC);
