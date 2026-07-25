# SLMC Baseline Report

- Source archive: `SnapIMS-v0.6.0-complete-repo(2).zip`
- Confirmed branch: `feature/v0.6.0-operator-workstation`
- Confirmed commit: `5c316ca0e6c881c2df7ea2913d7f242a523fdc78`
- Confirmed application version: `0.6.0`
- Confirmed inventory schema version: `6`
- Architecture: FastAPI/Jinja with SQLite inventory database.
- Inventory database path: `<data-root>/database/inventory.sqlite3`.
- Recognition result commit point: `snapims/recognition/service.py::run_recognition`, which inserts `recognition_results` and marks the Item recognition complete in one inventory transaction.
- Review rendering path: `snapims/web/app.py::review_page` -> `snapims/web/templates/review.html`.
- Database backup mechanism: `snapims/db.py::backup_database`, using the SQLite backup API into `<data-root>/backups`.
- Existing recognition tables: `recognition_results` and `recognition_jobs`.

## Baseline quality gate

- `pytest`: 123 passed in 32.76 seconds.
- `Ruff`: not installed in the supplied execution environment at baseline.
- `mypy`: baseline invocation did not complete before the execution timeout and produced no result.
- `git diff --check`: not reached in the combined timed baseline command; the starting tree was clean.

The source archive itself was not modified. Implementation proceeds in a copied working tree on `feature/slmc-local-movie-catalog`.
