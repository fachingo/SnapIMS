# SnapIMS 0.6.0 Test Results

## Automated tests

Result: **123 passed**.

Coverage includes protocol parsing, imports, migrations, recognition, Review, Batch Editor, CSV diff/apply/rollback, Shopify idempotency, web routes, and restart behavior.

The full suite reached `123 passed in 37.19s` in the container. The hosting harness occasionally retained the completed Python process after pytest printed its final result; individual test modules and grouped release tests exited normally.

## Additional checks

- `python -m compileall -q snapims scripts/native_browser_audit_v060.py`: passed.
- `node --check snapims/web/static/app.js`: passed.
- Native Chromium audit: passed.
- SQLite migration/integrity tests: passed.

Ruff is declared in the development dependencies and remains part of `scripts/run_quality_gate.sh`. The artifact environment used for this reconstruction did not contain a Ruff executable and had no package-network access; run the repository quality gate in the installed project environment before merge.
