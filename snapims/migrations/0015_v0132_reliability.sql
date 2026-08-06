-- SnapIMS inventory schema 15: v0.13.2 reliability and concurrency guards.
-- Runtime upgrades are orchestrated transactionally by snapims.db.initialize.
-- Legacy duplicate active Import jobs are marked SUPERSEDED before the index is created.

CREATE UNIQUE INDEX IF NOT EXISTS idx_import_jobs_active_folder
    ON import_jobs(folder_path)
    WHERE status IN (
        'QUEUED','RUNNING','READY','NEEDS_ATTENTION','COMMIT_QUEUED','COMMITTING'
    );
