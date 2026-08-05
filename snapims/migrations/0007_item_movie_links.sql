-- SnapIMS inventory schema 7: minimum SLMC integration structure.
-- Runtime application is implemented and verified in snapims/db.py.
CREATE TABLE IF NOT EXISTS item_movie_links (
    item_id TEXT PRIMARY KEY REFERENCES items(item_id) ON DELETE RESTRICT,
    movie_id TEXT,
    link_status TEXT NOT NULL,
    link_method TEXT NOT NULL DEFAULT '',
    recognition_result_id INTEGER REFERENCES recognition_results(recognition_result_id) ON DELETE RESTRICT,
    match_score REAL,
    linked_at TEXT,
    updated_at TEXT NOT NULL,
    operator_confirmed INTEGER NOT NULL DEFAULT 0,
    catalog_revision INTEGER,
    last_error TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS item_movie_link_events (
    link_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL REFERENCES items(item_id) ON DELETE RESTRICT,
    previous_movie_id TEXT,
    movie_id TEXT,
    event_type TEXT NOT NULL,
    link_status TEXT NOT NULL,
    link_method TEXT NOT NULL DEFAULT '',
    recognition_result_id INTEGER REFERENCES recognition_results(recognition_result_id) ON DELETE RESTRICT,
    match_score REAL,
    operator_confirmed INTEGER NOT NULL DEFAULT 0,
    catalog_revision INTEGER,
    occurred_at TEXT NOT NULL,
    source TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_item_movie_links_movie ON item_movie_links(movie_id, link_status);
CREATE INDEX IF NOT EXISTS idx_item_movie_link_events_item ON item_movie_link_events(item_id, occurred_at DESC);
