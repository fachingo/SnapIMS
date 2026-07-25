# SnapIMS 0.6.1 Test Results

## Automated tests

- Collected: 136 tests across 13 test modules.
- Full-suite result: **PASS**, exit status 0.
- Full-suite log: `release-evidence/v0.6.1/tests/full-pytest.log`.
- Every module also passed independently; counts are recorded in `release-evidence/v0.6.1/tests/per-file-results.txt`.
- New stabilization coverage includes test-provider quarantine, Shopify provenance guards, BLOCKED provider semantics, atomic CSV/bulk/external-review failure injection, audited restore, fail-closed schema verification, legacy constraint repair, import-journal restart recovery, exact money, and browser-visible confidence.

## Static and packaging gates

- `python -m compileall -q snapims tests scripts/native_browser_audit_v061.py scripts/generate_operator_guide_v061.py`: **PASS**.
- `node --check snapims/web/static/app.js`: **PASS**.
- `git diff --check`: **PASS**.
- `python -m pip wheel . --no-deps --no-build-isolation -w dist`: **PASS**.
- Wheel import/CLI smoke: **PASS** (`snapims`, FastAPI application, and CLI all report 0.6.1; schema constant is 7).
- Local Ruff/mypy installation was unavailable because the isolated package index returned no package/503 responses. The GitHub quality workflow remains configured to run Ruff, mypy, pytest, compileall, build, pip check, and an installed-wheel smoke test in a clean Python 3.12 environment.
- The shared host's `pip check` reports an unrelated pre-existing `moviepy` versus `Pillow` conflict. SnapIMS does not depend on moviepy; clean CI remains the authoritative dependency check.

## Database gates

- SQLite `integrity_check`: `ok` on the browser audit workspace before evidence cleanup.
- SQLite `foreign_key_check`: zero violations.
- Schema manifest: passed at schema version 7.
- Interrupted import, CSV, bulk edit, external review, and checkpoint restore tests passed.

## Browser gate

Status: **PASS**. See `NATIVE_BROWSER_VERIFICATION.md`, `release-evidence/v0.6.1/browser/results.json`, screenshots, logs, and trace.
