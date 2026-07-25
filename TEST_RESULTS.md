# SnapIMS 0.7.0 Test Results

## Automated tests

- Passed: **174**
- Skipped: **1** — bounded live English Wikipedia integration, enabled only with `SNAPIMS_LIVE_WIKIPEDIA_TEST=1`.
- Failures: **0**
- Full log: `release-evidence/v0.7.0/tests/full-pytest.txt`

Coverage includes:

- realistic schema-7 database migration with legacy `recognition_job_items`;
- repeat initialization, integrity, foreign keys, and schema manifest;
- folder-picker fallback with missing Tkinter;
- inline manual Title one-request approval;
- rapid Review and recognition/catalog job interaction;
- distinct negative catalog identities for separate manual items;
- local hit, Wikipedia miss, ambiguity, operator selection, unavailable provider, restart recovery, backup/restore, FTS and reconciliation;
- exact CSV export/upload round trip, BOM, semicolon/tab/comma, CRLF/LF and header aliases;
- atomic CSV/bulk/external-review/checkpoint operations;
- production test-provider quarantine and Shopify provenance blockers;
- Batch Editor keyboard contract and quick-action ordering.

## Static and build gates

- `python -m compileall -q snapims tests scripts`: PASS
- `node --check snapims/web/static/app.js`: PASS
- `git diff --check`: PASS
- Python wheel build with no dependency resolution: PASS
- Installed-wheel import/CLI smoke: PASS
- SQLite inventory integrity and foreign-key checks: PASS
- Movie Catalog integrity, foreign-key and FTS verification: PASS
- Release archive secret/database/cache scan: PASS

The sandbox did not provide locally installable Ruff or mypy executables. Their configured GitHub quality workflow remains part of the remote merge gate. `pip check` on the shared host reports an unrelated pre-existing MoviePy/Pillow constraint; the release wheel itself is installed and smoke-tested in an isolated system-site-packages environment.

## Browser verification

Native Chromium, 1440×1000:

- Status: PASS
- Console errors: 0
- Page errors: 0
- Relevant failed requests: 0
- Relevant HTTP errors: 0
- One `ERR_ABORTED` was the expected browser download-navigation signal for a successful CSV download.

Evidence: `release-evidence/v0.7.0/browser/`.
