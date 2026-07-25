# SLMC-0.1.0 Test Report

**Host application:** SnapIMS 0.6.0  
**Package:** SLMC-0.1.0  
**Verified implementation commit:** `dad21ce4d50684b9dfbe21c22cfbb6ab453fcad5`  
**Branch:** `feature/slmc-local-movie-catalog`

## Automated test results

| Gate | Exact result |
|---|---|
| Full pytest suite | **155 passed, 1 skipped in 67.58 seconds** |
| Deterministic catalog subset | **32 passed, 1 skipped** |
| Optional live Wikipedia test | **Skipped by default**; no live network request was claimed |
| Python compile | `python -m compileall -q snapims scripts tests` — **passed** |
| Browser JavaScript syntax | `node --check snapims/web/static/app.js` — **passed** |
| Git whitespace | `git diff --check` — **passed** |
| Wheel build fallback | `python -m pip wheel . --no-deps --no-build-isolation` — **passed**; produced `snapims-0.6.0-py3-none-any.whl` |
| Release archive safety scan | `python scripts/scan_release_archive.py SnapIMS-SLMC-0.1.0-integration-package.zip` — **passed** |

The full suite includes the inherited v0.6.0 tests and the new catalog, migration, job, matching, ambiguity, administration, CSV, Shopify-simulation, restart and browser-contract tests.

## Required deterministic SLMC cases

The test suite covers:

- exact title, title/year and alias local matches;
- zero Wikipedia calls on local hits;
- first-record creation and repeated-copy reuse;
- concurrent duplicate prevention;
- same-title/different-year and film/television collisions;
- punctuation, leading article, Roman/numeric sequel and redirect normalization;
- disambiguation, non-film contamination, timeout, rate-limit, malformed and no-result paths;
- candidate persistence and operator selection;
- operator title correction and stale-link handling;
- persisted job restart, duplicate-job prevention and pending-link reconciliation;
- catalog unavailable/corrupt failure isolation;
- independent catalog migration and inventory schema-6-to-7 integration;
- merge, split, restart reconciliation, backup, restore, export/import and provenance durability;
- CSV Movie/Item identity and Shopify structured facts;
- unchanged VHS edition, Price and Discount fields;
- one-action Approve & Next, Enter advancement and duplicate-action protection;
- FTS rebuild and representative indexed performance.

## Schema and database verification

A clean temporary data root was initialized through the production migration paths.

| Database | Integrity | Foreign-key violations | Schema |
|---|---:|---:|---:|
| `inventory.sqlite3` | `ok` | 0 | 7 |
| `movie_catalog.sqlite3` | `ok` | 0 | 1 |

Catalog structural verification also reported FTS available and healthy.

## Browser verification

The deterministic native Chromium audit passed on the actual FastAPI/Jinja application at commit `dad21ce4d50684b9dfbe21c22cfbb6ab453fcad5`.

- page errors: 0;
- unexpected request failures: 0;
- two inherited favicon 404 console entries recorded;
- local hit performed no Wikipedia attempt;
- one fixture-backed miss created one durable Movie;
- a second batch reused both Movie IDs and kept Wikipedia attempts at one;
- Enter advanced exactly once;
- CSV and Shopify simulation received the same structured Movie identities;
- full process restart preserved Movies, aliases, jobs and links.

See `BROWSER_VERIFICATION_REPORT.md` and `operator-audit-assets/slmc-0.1.0-browser/results.json`.

## Performance verification

Synthetic indexed benchmarks were run at 10,000 Movies and at 100,000 Movies / 500,000 aliases. The larger database measured 202,215,424 bytes. Median exact, title/year, alias and FTS lookups were approximately 0.86–1.03 ms in that run. One exact-title outlier reached approximately 992 ms; therefore the report does not claim a hard worst-case latency guarantee.

See `PERFORMANCE_REPORT.md` and `docs/slmc/evidence/performance/`.

## Gates that could not be executed in this container

The artifact container did not include Ruff or mypy. Installation was attempted through both pip and uv, but the configured package gateway returned no Ruff distribution / HTTP 503. Exact command results:

- `python -m ruff check .` — **not run successfully: `No module named ruff`**;
- `python -m mypy snapims --ignore-missing-imports` — **not run successfully: `No module named mypy`**;
- `python -m build` — **not run successfully: build frontend unavailable as an executable module**.

A standards-based wheel was nevertheless built successfully through pip's PEP 517 path. These missing-tool gates are explicitly unresolved and must be rerun in the developer environment before merge acceptance.

`python -m pip check` also reported an unrelated pre-existing environment conflict: MoviePy requires Pillow `<12.0`, while the shared container has Pillow `12.2.0`. SnapIMS itself built and tested successfully, but the global-environment check is not green.

## Live/production gates not claimed

- live AI recognition;
- live English Wikipedia request;
- real 20-tape Pixel pilot;
- physical CSV reconciliation;
- one live Shopify draft;
- final verification after blending into a newer SnapIMS branch.

These remain mandatory before SnapIMS 1.0.0.
