# SnapIMS 0.6.0 + SLMC-0.1.0 Test Results

## Automated tests

Full suite result: **155 passed, 1 skipped in 67.58 seconds**.

The skipped test is the optional live English Wikipedia integration check. It is disabled unless `SNAPIMS_LIVE_WIKIPEDIA_TEST=1` and a descriptive User-Agent are supplied.

Deterministic catalog subset: **32 passed, 1 skipped**.

Coverage includes the inherited protocol, import, recognition, Review, Batch Editor, CSV, Shopify simulation and web tests plus independent catalog migration, local-first matching, Wikipedia fixture parsing, duplicate prevention, ambiguity, persisted jobs, cross-database link reconciliation, administration, backup/restore, merge/split, provenance, structured outputs and restart durability.

## Additional checks

- `python -m compileall -q snapims scripts tests`: **passed**.
- `node --check snapims/web/static/app.js`: **passed**.
- `git diff --check`: **passed**.
- `python -m pip wheel . --no-deps --no-build-isolation`: **passed**.
- release archive safety scan: **passed**.
- clean inventory initialization: integrity `ok`, FK violations `0`, schema `7`.
- clean catalog initialization: integrity `ok`, FK violations `0`, schema `1`, FTS healthy.
- deterministic native Chromium audit: **passed with stated limitations**.

## Unresolved environment gates

The container did not contain Ruff or mypy, and the configured package gateway failed when installation was attempted. Therefore these gates are **not claimed as passed**:

- Ruff: unavailable (`No module named ruff`).
- mypy: unavailable (`No module named mypy`).
- `python -m build`: build frontend unavailable; the pip PEP 517 wheel fallback passed.

`python -m pip check` was not green because the shared container has a pre-existing MoviePy/Pillow version conflict unrelated to SnapIMS.

See `TEST_REPORT.md` for exact evidence and limitations.
