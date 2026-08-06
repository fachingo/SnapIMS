-- SnapIMS schema 16: durable Shopify draft/live publish workflow.
CREATE TABLE IF NOT EXISTS shopify_publish_jobs (
    job_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES batches(batch_id) ON DELETE RESTRICT,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    selection_scope TEXT NOT NULL DEFAULT 'SELECTED',
    total INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    succeeded INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    current_item_id TEXT NOT NULL DEFAULT '',
    confirmation_text TEXT NOT NULL DEFAULT '',
    options_json TEXT NOT NULL DEFAULT '{}',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    started_at TEXT,
    updated_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS shopify_publish_job_items (
    job_id TEXT NOT NULL REFERENCES shopify_publish_jobs(job_id) ON DELETE CASCADE,
    item_id TEXT NOT NULL REFERENCES items(item_id) ON DELETE RESTRICT,
    sequence INTEGER NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'QUEUED',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NOT NULL DEFAULT '',
    result_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    PRIMARY KEY(job_id,item_id)
);
