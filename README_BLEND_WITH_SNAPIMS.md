# Blend SnapIMS Local Movie Catalog Module into SnapIMS

**Package name:** SnapIMS Local Movie Catalog Module  
**Package identifier:** SLMC  
**Package version:** SLMC-0.1.0  
**Host baseline:** SnapIMS 0.6.0  
**Source branch:** `feature/v0.6.0-operator-workstation`  
**Source commit:** `5c316ca0e6c881c2df7ea2913d7f242a523fdc78`  
**Isolated branch:** `feature/slmc-local-movie-catalog`

This repository is a standalone, mergeable integration package. It is not a completed SnapIMS release and does not rename or relabel the host application. The merged capability is a minor feature release, but its exact SnapIMS version must be chosen only after integration, automated gates, browser verification and documentation synchronization.

## 1. What SLMC is

SLMC is the permanent local Movie foundation for SnapIMS. It turns a first-pass AI title into a reusable, source-backed local Movie record. The local catalog is searched before any external request. A genuine miss can perform one bounded English Wikipedia lookup, normalize the selected film, store it permanently, and link the physical Item. Future copies reuse the same Movie without another Wikipedia request.

SLMC is not a generic API cache, not a full Wikipedia mirror, not a VHS-edition database and not a replacement recognition provider.

## 2. Why the catalog is a separate database

`inventory.sqlite3` remains the operational system of record for physical inventory. `movie_catalog.sqlite3` is a reusable Movie authority with different retention, scale, maintenance and provenance requirements. Keeping them separate prevents large provider payloads/search indexes from contaminating inventory transactions and permits independent backup, verification, movement and future provider changes.

## 3. Authority by database

### `inventory.sqlite3`

Batch and Item identity; images; physical sequence; shelf; condition; Price; Discount; quantity; operator values; recognition history; Review completion; CSV and Shopify state; inventory events; current Movie link and link-event history.

### `movie_catalog.sqlite3`

Movies; aliases; normalized title keys; original titles; release year/date; media type; runtime; countries; languages; directors; genres; concise neutral summaries; source page/revision/retrieval; candidate evidence; decisions; catalog jobs/attempts; bounded response cache; settings; FTS/index state; maintenance and catalog events.

## 4. Exact source baseline

The supplied source archive was inspected locally. No GitHub source was used. Confirmed baseline:

- application version 0.6.0;
- branch `feature/v0.6.0-operator-workstation`;
- commit `5c316ca0e6c881c2df7ea2913d7f242a523fdc78`;
- inventory schema 6;
- FastAPI/Jinja browser application;
- authoritative inventory database `inventory.sqlite3`;
- recognition tables `recognition_results` and `recognition_jobs`;
- recognition commit point `snapims/recognition/service.py::run_recognition`;
- Review route `snapims/web/app.py::review_page` and template `snapims/web/templates/review.html`;
- backups use the SQLite backup API.

See `docs/slmc/BASELINE_REPORT.md`.

## 5. Added files

<!-- FILE_LIST_START -->
Exact repository files added relative to the verified baseline:

- `ARCHITECTURE_LOCAL_MOVIE_CATALOG.md`
- `BROWSER_VERIFICATION_REPORT.md`
- `CATALOG_ADMIN_GUIDE.md`
- `CATALOG_BACKUP_AND_RESTORE.md`
- `CATALOG_DATABASE_SCHEMA.md`
- `CHANGELOG_SLMC.md`
- `CROSS_DATABASE_RECOVERY.md`
- `FILE_MANIFEST.sha256`
- `INVENTORY_DATABASE_INTEGRATION.md`
- `LICENSE_AND_ATTRIBUTION.md`
- `LOCAL_MATCHING_RULES.md`
- `MERGE_CONFLICT_MAP.md`
- `PERFORMANCE_REPORT.md`
- `README_BLEND_WITH_SNAPIMS.md`
- `TEST_REPORT.md`
- `THIRD_PARTY_NOTICES.md`
- `WIKIPEDIA_DATA_POLICY.md`
- `WIKIPEDIA_INGESTION_POLICY.md`
- `docs/slmc/BASELINE_REPORT.md`
- `docs/slmc/evidence/performance/slmc-performance-10k.json`
- `docs/slmc/evidence/performance/slmc-performance.json`
- `operator-audit-assets/slmc-0.1.0-browser/downloads/slmc-working.csv`
- `operator-audit-assets/slmc-0.1.0-browser/results.json`
- `operator-audit-assets/slmc-0.1.0-browser/screenshots/01-import-preview.png`
- `operator-audit-assets/slmc-0.1.0-browser/screenshots/02-import-complete.png`
- `operator-audit-assets/slmc-0.1.0-browser/screenshots/03-local-match-review.png`
- `operator-audit-assets/slmc-0.1.0-browser/screenshots/04-new-wikipedia-record-and-next.png`
- `operator-audit-assets/slmc-0.1.0-browser/screenshots/05-review-complete.png`
- `operator-audit-assets/slmc-0.1.0-browser/screenshots/06-second-copy-local-reuse.png`
- `operator-audit-assets/slmc-0.1.0-browser/screenshots/07-shopify-simulation.png`
- `operator-audit-assets/slmc-0.1.0-browser/screenshots/08-catalog-diagnostics.png`
- `operator-audit-assets/slmc-0.1.0-browser/screenshots/09-restart-durable-catalog.png`
- `operator-audit-assets/slmc-0.1.0-browser/server-events.txt`
- `scripts/catalog_admin.py`
- `scripts/catalog_performance.py`
- `scripts/generate_operator_guide_slmc.py`
- `scripts/native_browser_audit_slmc.py`
- `scripts/scan_release_archive.py`
- `snapims/catalog/__init__.py`
- `snapims/catalog/admin.py`
- `snapims/catalog/db.py`
- `snapims/catalog/migrations/0001_initial.sql`
- `snapims/catalog/models.py`
- `snapims/catalog/normalization.py`
- `snapims/catalog/service.py`
- `snapims/catalog/wikipedia.py`
- `snapims/migrations/0007_item_movie_links.sql`
- `tests/fixtures/wikipedia/parse-1001.json`
- `tests/fixtures/wikipedia/parse-1101.json`
- `tests/fixtures/wikipedia/parse-1102.json`
- `tests/fixtures/wikipedia/parse-1201.json`
- `tests/fixtures/wikipedia/parse-1202.json`
- `tests/fixtures/wikipedia/parse-1203.json`
- `tests/fixtures/wikipedia/parse-2002.json`
- `tests/fixtures/wikipedia/query-1001.json`
- `tests/fixtures/wikipedia/query-1101.json`
- `tests/fixtures/wikipedia/query-1102.json`
- `tests/fixtures/wikipedia/query-1201.json`
- `tests/fixtures/wikipedia/query-1202.json`
- `tests/fixtures/wikipedia/query-1203.json`
- `tests/fixtures/wikipedia/query-2002.json`
- `tests/fixtures/wikipedia/search-crash.json`
- `tests/fixtures/wikipedia/search-demo-vhs-002.json`
- `tests/fixtures/wikipedia/search-gremlins.json`
- `tests/fixtures/wikipedia/search-no-result.json`
- `tests/fixtures/wikipedia/search-the-thing.json`
- `tests/test_catalog_admin.py`
- `tests/test_catalog_live_wikipedia.py`
- `tests/test_catalog_module.py`

The delivery archive also contains a package-only `patches/` directory generated from the baseline-to-final Git range.
<!-- FILE_LIST_END -->

## 6. Changed files

<!-- CHANGED_FILE_LIST_START -->
Exact repository files changed relative to the verified baseline:

- `ARCHITECTURE.md`
- `DATABASE.md`
- `DOCUMENTATION_VERIFICATION.md`
- `NATIVE_BROWSER_VERIFICATION.md`
- `PRODUCTION_READINESS.md`
- `PROJECT_STATUS.md`
- `README.md`
- `RELEASE_NOTES.md`
- `SCREENSHOT_INDEX.md`
- `SnapIMS_Operator_Guide.docx`
- `SnapIMS_Operator_Guide.pdf`
- `TEST_RESULTS.md`
- `snapims/config.py`
- `snapims/db.py`
- `snapims/inventory.py`
- `snapims/recognition/service.py`
- `snapims/shopify/service.py`
- `snapims/web/app.py`
- `snapims/web/static/app.css`
- `snapims/web/templates/diagnostics.html`
- `snapims/web/templates/review.html`
- `tests/test_db_migration.py`
<!-- CHANGED_FILE_LIST_END -->

## 7. Inventory migration

The integration migrates inventory schema 6 to 7. It adds only `item_movie_links`, `item_movie_link_events` and their indexes. The migration creates a timestamped SQLite backup, preserves every existing identity and working value, applies the additive structures, records schema migration 7, and verifies integrity and foreign keys.

Do not apply the migration by copying a database from this package. Apply it through the target application's migration path against a verified backup.

## 8. Catalog migration

Catalog schema 1 creates the normalized Movie/source/alias/candidate/job/event structures and optional FTS5 table. It maintains its own migration ledger and expected structural manifest. It does not trust `PRAGMA user_version` alone and does not overwrite an incompatible or corrupt file.

## 9. Cross-database reconciliation

The two files do not share a cross-file foreign key or atomic transaction. SLMC commits/locates the Movie first, records a durable catalog event/revision, then commits the Item link. A failed link becomes `LINK_PENDING` and is retried idempotently. The shared Movie is never deleted because one Item link failed.

See `CROSS_DATABASE_RECOVERY.md`.

## 10. Recognition integration

After the first-pass provider result is committed, SLMC builds a lookup request from title, year, distributor/edition clues, confidence and recognition result ID. It searches local Movie data inline. Unique local hits link immediately. Only a miss queues the restart-safe external job. Catalog failure never erases recognition history.

## 11. Review integration

Review adds one restrained status strip and an ambiguity panel. The title shown for fast approval follows operator-saved → catalog canonical → AI suggestion → manual untitled precedence. Price and Discount remain inline. Approve & Next and the Enter shortcut remain one action. Full metadata is not placed on the compact card.

## 12. CSV and Shopify integration

CSV and Shopify simulation can include local Movie ID, canonical title, original title, film year, runtime, director, country, language, genre, catalog status, source URL and provenance status. They do not replace Item ID, SKU, physical title override, edition facts, Price, Discount, condition, shelf or quantity. CSV remains Item-ID keyed. Shopify remains draft/simulation-only; no automatic publication is introduced.

## 13. Expected merge conflicts

Expect conflicts in inventory schema/migrations, recognition service, Review route/template, diagnostics, CSV export, Shopify service and operator documentation. Do not resolve them by replacing newer target files with v0.6.0 copies. See `MERGE_CONFLICT_MAP.md`.

## 14. Step-by-step blend procedure

1. Preserve the target branch/ref and create a tested database/media backup.
2. Record target application version, schema, branch, commit and clean/dirty state.
3. Create an isolated integration branch.
4. Apply the patch series from `patches/` or cherry-pick the logical SLMC commits in order.
5. Add `snapims/catalog/` and `DataPaths.catalog_db_file` first.
6. Reconcile catalog schema 1 with any newer target migration conventions.
7. Rebase inventory schema 7 additions onto the target schema number; never decrement a newer schema.
8. Blend post-recognition local lookup only after the target recognition transaction commits.
9. Blend Review context/status into the final workstation UI without restoring obsolete layout.
10. Blend CSV and Shopify structured fields while preserving target output contracts.
11. Blend diagnostics/admin and recovery startup.
12. Run migration tests against a copy of the target schema/database.
13. Run the full automated gate.
14. Launch the actual application and complete browser verification from Import through Review, CSV, simulation, restart and diagnostics.
15. Regenerate the Operator Guide and every affected screenshot from the merged final UI.
16. Choose the exact minor SnapIMS version only after the merged result is accepted.

## 15. Test procedure

```bash
python -m pytest -q
python -m ruff check .
python -m mypy snapims --ignore-missing-imports
python -m compileall -q snapims
python -m build
python -m pip check
git diff --check
```

Run deterministic catalog tests directly when debugging:

```bash
python -m pytest -q tests/test_catalog_module.py tests/test_catalog_admin.py
```

The optional live English Wikipedia test is skipped unless explicitly enabled:

```bash
SNAPIMS_LIVE_WIKIPEDIA_TEST=1 \
SNAPIMS_WIKIPEDIA_USER_AGENT='SnapIMS-SLMC/0.1.0 (contact: your-address)' \
python -m pytest -q tests/test_catalog_live_wikipedia.py
```

## 16. Browser verification procedure

Run:

```bash
python scripts/native_browser_audit_slmc.py
```

The audit launches Uvicorn and Chromium, attaches console/page/request monitoring before navigation, imports a real deterministic photo stream, runs recognition, verifies local hit before Wikipedia, creates one fixture-backed new Movie, verifies second-copy reuse, tests Enter advancement, downloads CSV, checks Shopify simulation, opens Diagnostics, restarts the full process and compares persisted state.

The package audit deliberately does **not** claim live AI, live Wikipedia or live Shopify. See `BROWSER_VERIFICATION_REPORT.md`.

## 17. Backup requirements

Back up both SQLite databases before every catalog/inventory migration, bulk import, merge, split, restore or server move. Preserve originals and exports separately. Use SQLite online backup, verify the backup, and record integrity/FK results and checksums.

## 18. Rollback procedure

1. Stop SnapIMS and workers.
2. Preserve current databases and sidecars.
3. Restore the verified pre-integration inventory backup.
4. Retain `movie_catalog.sqlite3` separately unless the owner deliberately removes the capability.
5. Remove/disable the catalog post-recognition hook and routes in code.
6. Start the prior application version.
7. Verify inventory integrity/FKs, Item/Batch IDs, photos, Review state, CSV and Shopify state.

Because the inventory migration is additive, a code rollback should ignore the link tables rather than destructively dropping them unless a separately reviewed cleanup is approved.

## 19. Disable/remove procedure

To temporarily disable catalog use without losing data, stop catalog workers and configure the app not to start the post-recognition hook, or move the catalog into explicit maintenance after a verified backup. Review falls back to AI/operator values. Do not delete `movie_catalog.sqlite3`.

Permanent removal requires a reviewed migration and export of link/candidate/provenance history. It is not part of SLMC-0.1.0.

## 20. Preserve the catalog across SnapIMS upgrades

Treat `<data-root>/database/movie_catalog.sqlite3` as production data, not a generated file. Keep it outside Git and source checkouts. Before upgrade, back it up and verify schema/integrity. After installing new code, run catalog migrations and reconciliation before normal recognition.

## 21. Move the catalog between servers

Stop writers, create a verified SQLite backup, copy it with its manifest/checksum to the new data root, set correct ownership/permissions, run catalog verify and inventory reconciliation, then resume recognition. Do not copy a live WAL-mode file without a proper online backup or coordinated shutdown.

## 22. Known limitations

- No live Wikipedia request was executed in the deterministic package gate.
- No live AI recognition or live Shopify draft was executed.
- Wikipedia is film-level only and cannot infer exact VHS edition facts.
- Catalog merge/split require deliberate administrator use and backups.
- FTS5 depends on the SQLite build; exact indexed fallback remains available.
- The catalog is on-demand growth; it does not contain every film at installation.
- Application-level multi-user authentication/authorization is outside this package.
- This package does not fix every v0.6.0 production-readiness issue in the master plan.

## 23. Semantic-version recommendation

Keep this integration package at **SLMC-0.1.0**. Once blended into the then-current SnapIMS branch and reverified, classify it as a **minor** SnapIMS release because it adds a database, provider capability, persisted jobs and operator-visible metadata states. Select the next available minor version from the actual target baseline. Do not label SnapIMS 1.0.0 until the real 20-tape Pixel pilot, live AI, one live Shopify draft, physical CSV verification, restart durability, synchronized Operator Guide, complete browser verification and blocker review all pass.
