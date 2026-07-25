from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DOCS: dict[str, str] = {
"README.md": r'''# SnapIMS 0.7.0

SnapIMS is a photo-first, exception-driven inventory workstation for Canada VHS. Version 0.7.0 adds the local-first Movie Catalog, true spreadsheet-style Batch Editor keyboard operation, one-Enter manual-title Review, resilient CSV round trips, and migration/folder-picker repairs while preserving the v0.6.1 integrity foundation.

## Routine workflow

1. Photograph START, location, tape photos, NEXT between tapes, and END.
2. Preview counts and warnings; then preserve one durable batch.
3. Identify with a configured live provider or continue manually.
4. Review the photograph. Title is focused only when empty; otherwise Price is selected. Press Enter once to approve and open the next unfinished tape.
5. Use Batch Editor for keyboard-driven corrections, atomic bulk actions, checkpoints, and CSV staging.
6. Let the background catalog search the local database first and bounded English Wikipedia only on a genuine local miss.
7. Simulate Shopify drafts before any deliberate live draft test.

## 0.7.0 highlights

- **Local Movie Catalog:** separate rebuildable `movie_catalog.sqlite3`, local-first matching, bounded Wikipedia retrieval, source provenance, ambiguity resolution, restart-safe jobs, CSV/Shopify enrichment, diagnostics, backup and restore.
- **Review:** inline Title/Price/Discount quick fields; Title receives focus only when required; one Enter submits the valid record exactly once.
- **Batch Editor:** arrow-key grid navigation, Enter-to-save-and-move, Shift range selection, Ctrl/Cmd+A visible-row selection, Ctrl/Cmd+1–9 quick actions, persistent action order, and concise action descriptions.
- **CSV:** unchanged SnapIMS exports round-trip successfully; BOM, CRLF/LF, comma/semicolon/tab delimiters, harmless header variation, and `item_id` aliases are handled without weakening immutable-ID safety.
- **Import:** missing Tkinter becomes a clear manual-path fallback; `python3-tk` is an optional Linux dependency for the native folder picker.
- **Migration:** schema 8 automatically removes the obsolete `recognition_job_items` table before rebuilding recognition jobs, preventing the v0.6.1 foreign-key mismatch on existing databases.

## Install and run

```bash
cd ~/Projects/SnapIMS-v0.7.0
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
snapims --data-dir ~/SnapIMS-data serve
```

Open `http://127.0.0.1:8767`.

For the native Linux folder picker:

```bash
sudo apt install python3-tk
```

SnapIMS binds to localhost by default. Do not expose the application directly with router port forwarding.

## Release status

Version 0.7.0 is a **minor feature release**, not production 1.0.0. The real 20-tape Pixel pilot, live AI test, one live Shopify draft, physical CSV reconciliation, restart durability on the production machine, final Operator Guide walkthrough, browser verification, and blocker review remain mandatory before 1.0.0.
''',
"RELEASE_NOTES.md": r'''# SnapIMS Release Notes

## 0.7.0 — Keyboard Workstation and Local Movie Catalog

Release type: **minor**. This release introduces new operator-visible keyboard workflows and a local-first structured Movie Catalog while repairing defects found during the v0.6.1 operator test.

### Review throughput

- Title, Price, and Discount form the complete inline quick-edit surface.
- When Title is empty, it is focused first; typing the Title and pressing Enter performs the valid Approve & Next operation in one request.
- When Title exists, Price remains automatically focused and selected.
- The full exception editor appears only for genuine validation/conflict cases or explicit Edit Details use.
- Duplicate-submit protection prevents rapid double Enter from approving two tapes.

### Batch Editor keyboard workstation

- Arrow Up/Down moves within the same editable column.
- Arrow Left/Right moves between editable cells at text-caret boundaries.
- Enter saves and moves down; Escape cancels; F2 enters edit mode where applicable.
- Space toggles the active row; Shift+Arrow extends the visible-row selection; Ctrl/Cmd+A selects visible filtered rows.
- Ctrl/Cmd+1–9 opens the first nine quick actions through the same preview/confirmation dialog as a click.
- Quick actions can be reordered by drag or Alt+Left/Right, persist in local storage, and can be reset.
- Every bulk popup states what changes, which rows are affected, whether a checkpoint is created, and whether rollback is available.

### CSV round trip

- CSV exported by SnapIMS now passes upload header recognition unchanged.
- Supports UTF-8 BOM, LF/CRLF, comma/semicolon/tab delimiters, harmless whitespace/case differences, and unambiguous `Item ID`/`item_id` aliases.
- Invalid files name the columns actually detected.
- Immutable Item ID remains mandatory; no title or row-position fallback was added.
- Staging, diff preview, atomic apply, audit history, and checkpoint rollback remain intact.

### Import and migration repairs

- Missing `tkinter` now opens a manual-path fallback instead of an alarming dead end.
- Linux documentation identifies `python3-tk` as the optional native-picker package.
- Schema 8 permanently repairs the legacy `recognition_job_items`/`recognition_jobs` mismatch encountered by a real v0.6.1 database.
- Migration is repeatable, backed up, structurally verified, and preserves Batch IDs, Item IDs, recognition results, reviewed records, and media linkage.

### Local Movie Catalog

- Adds an independent, rebuildable `movie_catalog.sqlite3`; `inventory.sqlite3` remains the physical-inventory authority.
- Local title/alias/year search runs before external access.
- Bounded English Wikipedia lookup occurs only on a genuine miss and uses configurable User-Agent, timeout, retry, cache, and provenance rules.
- Ambiguous title/year/media matches are persisted for operator selection rather than silently merged.
- Movie links are auditable and never alter physical Item or Batch identity.
- Manual-title items use stable catalog-only negative request identities; they never pretend to be inventory recognition results.
- Background jobs do not delay Approve & Next and recover safely after restart.
- Structured Movie facts can enrich CSV and Shopify simulation/draft preparation without copying long Wikipedia prose or ingesting provider artwork.
- Diagnostics provides catalog counts, job state, cache health, FTS verification, backup, restore, retry, and reconciliation tools.

### Verification

- 174 automated tests passed; one bounded live-Wikipedia test was skipped unless explicitly enabled.
- Native Chromium browser audit passed at 1440×1000 with monitoring attached before first navigation.
- Console errors: 0; page errors: 0; relevant failed requests: 0; relevant HTTP errors: 0.
- Verified a real 20-item synthetic workflow through import, one-Enter Review, ambiguity selection, recognition recovery, Batch Editor keyboard operations, bulk update, CSV stage/apply, Shopify simulation, restart, and Diagnostics.

### Deliberately not included

- 5,000-row virtualization and the 10,000-photo QR pipeline redesign.
- Multi-user concurrency/session authorization.
- Automatic Shopify publication.
- eBay scraping, artwork ingestion, pooling, VHS-edition intelligence, and Collection Intelligence.

### Production boundary

Live OpenAI quality/cost and live Shopify draft creation were not exercised in this build environment. Version 1.0.0 remains prohibited until every production acceptance criterion passes.
''',
"PROJECT_STATUS.md": r'''# SnapIMS 0.7.0 Project Status

Status: **browser-verified minor feature release; controlled real-pilot candidate; not 1.0.0**.

Current capabilities:

- QR-delimited photo import with immutable Batch and Item IDs.
- SQLite schema 8 with structural manifest verification, backups, atomic operations, audited rollback, and legacy migration repair.
- Production-safe live-provider framework with explicit blocked/manual recovery.
- One-Enter Review for AI-suggested or manually typed titles.
- Spreadsheet-style Batch Editor keyboard navigation, row selection, autosave, atomic quick actions, persistent action order, and checkpoints.
- Staged CSV diff, tolerant safe header parsing, atomic apply, and audited rollback.
- Independent local Movie Catalog with local-first search, bounded Wikipedia source lookup, provenance, ambiguity resolution, restart-safe jobs, CSV/Shopify enrichment, and admin recovery.
- Shopify simulation and controlled draft-only architecture.
- Browser-verified restart durability, diagnostics, and clean relevant console/network state.

Next required work is the real 20-tape Pixel/live-AI pilot, physical CSV reconciliation, one deliberately authorized live Shopify draft, production-machine restart verification, and final first-time-operator guide walkthrough. Scale claims remain limited: the full 5,000-row editor/import architecture is deferred.
''',
"DATABASE.md": r'''# SnapIMS 0.7.0 Databases

## Authoritative inventory database

Path: `~/SnapIMS-data/database/inventory.sqlite3`  
Schema version: **8**

This database owns Batch and Item identity, photos, physical sequence, shelf, condition, Price, Discount, quantity, working/review state, recognition history, CSV stages, checkpoints, Shopify state, current Movie link, and link audit events.

Schema 8 adds/validates the Movie-link structures and permanently repairs legacy v0.6.1 recognition migration state. Before rebuilding `recognition_jobs`, initialization detects and safely removes the obsolete `recognition_job_items` table that referenced the former numeric job identity. Migration creates a timestamped backup and ends only when `integrity_check`, `foreign_key_check`, and the structural schema manifest pass.

## Rebuildable Movie Catalog

Path: `~/SnapIMS-data/database/movie_catalog.sqlite3`  
Catalog schema version: **1**

This independent database stores Movies, titles, aliases, release year/date, runtime, countries, languages, directors, genres, concise source-backed summaries, source page/revision/retrieval provenance, candidates, decisions, lookup jobs, response cache, events, maintenance jobs, and FTS search data.

The catalog is a search/enrichment aid, not the physical-inventory authority. It can be backed up, verified, rebuilt, or replaced without changing Item IDs, Batch IDs, photos, prices, reviews, or Shopify linkage.

## Cross-database contract

- `inventory.sqlite3.item_movie_links.movie_id` stores the current external local Movie identifier.
- Inventory link events preserve every link/relink/stale decision.
- The application validates the Movie exists before writing a link because SQLite cannot enforce a foreign key across two files.
- Recognition-result references are used only when a real positive `recognition_results` row exists.
- Manual title jobs use deterministic negative catalog-only identities and store `NULL` as the inventory recognition reference.
- Restart reconciliation detects incomplete jobs and preserves deterministic identity.

## Safety commands

```bash
snapims --data-dir ~/SnapIMS-data diagnostics
python scripts/catalog_admin.py --data-dir ~/SnapIMS-data verify
python scripts/catalog_admin.py --data-dir ~/SnapIMS-data backup
```

Never delete the operator database to resolve a migration problem. Use Diagnostics, backups, and documented recovery.
''',
"TEST_RESULTS.md": r'''# SnapIMS 0.7.0 Test Results

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
''',
"NATIVE_BROWSER_VERIFICATION.md": (ROOT / "release-evidence/v0.7.0/browser/NATIVE_BROWSER_VERIFICATION.md").read_text(encoding="utf-8"),
"PRODUCTION_READINESS.md": r'''# SnapIMS 0.7.0 Production Readiness

Status: **controlled real-pilot candidate; not production 1.0.0**

## Verified in this release

- Existing-schema migration repair and schema 8 structural verification.
- One-Enter manual-title and Price-focused Review behaviour.
- Duplicate-submit protection and restart durability.
- Spreadsheet-style Batch Editor keyboard navigation and visible-row selection.
- Ctrl/Cmd+1–9 quick actions, preview safety, descriptions, reorder persistence, and atomic bulk operation.
- Same-version CSV export/upload/diff/apply round trip.
- Local-first Movie Catalog, bounded fixture-backed Wikipedia path, ambiguity preservation, operator selection, second-copy reuse, and catalog recovery/diagnostics.
- Production-mode Mock quarantine and blocked manual recovery.
- Shopify simulation with structured Movie data and draft-only safeguards.
- Native Chromium audit with no relevant console, page, network, or HTTP errors.

## Mandatory 1.0.0 blockers

1. Real 20-tape Pixel capture and import with zero physical/digital mismatch.
2. Live OpenAI recognition using real credentials and images, with measured latency, correction rate, failures, retries, and cost.
3. Downloaded CSV reconciled to the physical tapes and Review records.
4. Full application restart on the production Linux machine with all records/jobs/cursors preserved.
5. Exactly one deliberately authorized live Shopify draft, inspected for title, Price, Discount, quantity, SKU, images, metadata, and draft-only state.
6. First-time operator follows the final guide step by step; all UI/document discrepancies are fixed.
7. Final browser verification on the production machine and blocker review.
8. No known blocker for the claimed operating scale.

## Supported-scale statement

The verified browser fixture is 20 items. Existing evidence supports a controlled small-to-medium single-operator pilot. SnapIMS 0.7.0 does **not** claim 5,000-row workstation or 10,000-photo import readiness; bounded rendering and QR pipeline work remain deferred.

## External boundaries

- Live Wikipedia was not called during the default automated suite; bounded fixture transport verifies request/parse/persistence behaviour. The optional live test remains explicit.
- Live OpenAI and live Shopify were not exercised in the build environment.
- Cloudflare/Tailscale access does not make the application multi-user safe. Keep the application single-operator until per-user state, authorization, CSRF, and concurrency controls pass.
''',
"MIGRATION_REPORT.md": r'''# SnapIMS 0.7.0 Migration Report

## Starting state

The v0.6.1 package used inventory schema 7. A real existing database exposed a migration defect: `recognition_job_items` still referenced the former numeric `recognition_jobs.recognition_job_id`, while the rebuilt parent table used `batch_id` as its durable identity. Startup failed during `PRAGMA foreign_key_check` even though the migration rollback restored the pre-attempt database.

## Repair

Schema 8 initialization now:

1. creates a timestamped SQLite backup before migration;
2. detects the obsolete `recognition_job_items` table;
3. removes it before rebuilding `recognition_jobs`;
4. retains the latest durable recognition job per Batch;
5. creates/validates current Movie-link structures;
6. records schema migration 8;
7. runs `integrity_check`, `foreign_key_check`, and the structural schema manifest before normal startup.

The obsolete child table is not used by current recognition processing. Existing Batch IDs, Item IDs, photos, reviewed values, recognition results, recognition job state, checkpoints, CSV stages, and Shopify data are preserved.

## Catalog integration

The Movie Catalog does not place the external data universe inside the authoritative inventory database. It creates a separate `movie_catalog.sqlite3` with catalog schema 1. Inventory stores only current Movie links and link-event provenance.

## Manual-title identity correction

Catalog jobs originally used `0` when an operator-approved title had no recognition result. Because catalog job IDs require uniqueness, separate manual items could collide, and operator candidate selection attempted to validate a nonexistent recognition result. Version 0.7.0 derives a stable negative catalog-only identity from immutable Item ID and writes no inventory recognition-result reference for it.

## Verification

- Realistic schema-7 fixture with obsolete child table: PASS
- Repeat initialization: PASS
- Inventory integrity: OK
- Inventory foreign-key violations: 0
- Inventory schema manifest: PASS
- Catalog integrity and foreign keys: PASS
- Item/Batch identity preservation: PASS
''',
"CATALOG_INTEGRATION_REPORT.md": r'''# SnapIMS 0.7.0 Local Movie Catalog Integration Report

## Architecture

`inventory.sqlite3` remains the Canada VHS system of record. `movie_catalog.sqlite3` is an independent, rebuildable search and enrichment database.

The integrated module provides:

- canonical Movie records and aliases;
- SQLite FTS local search;
- title/year/media evidence scoring;
- bounded English Wikipedia query/parse transport;
- source page, revision, retrieval time, attribution and response-hash provenance;
- durable lookup jobs, candidates and operator decisions;
- audited inventory links and stale/relink events;
- response-cache bounds and maintenance events;
- backup, restore, verify, FTS rebuild, retry and reconciliation tools;
- compact Review state, ambiguity exception panel, CSV columns, Shopify simulation fields and Diagnostics.

## Throughput contract

Approve & Next commits physical inventory first, enqueues one idempotent catalog job, and returns the next unfinished item without waiting for Wikipedia. Local search is always first. External lookup failure cannot undo Review approval.

## Matching policy

- Same title/different year, remake/original, film/television, and materially ambiguous candidates are never silently merged.
- Provider IDs are source references, not local physical identities.
- Correcting a Movie match does not change Item ID, Batch ID, SKU, image linkage, location history or Shopify linkage.
- Wikipedia facts do not define VHS edition/packaging facts.

## Content and licensing boundary

The catalog stores structured facts and concise source-backed summaries with provenance. It does not ingest arbitrary artwork and does not copy long Wikipedia prose into Shopify descriptions. Storefront prose remains operator-owned or separately generated from approved structured facts under owner policy.

## Verification

- Local cache hit: PASS
- Fixture-backed Wikipedia miss: PASS
- Ambiguous candidate persistence and operator selection: PASS
- Manual-title catalog identity: PASS
- Second-copy local reuse: PASS
- Wikipedia unavailable does not block Review: PASS
- Interrupted job recovery: PASS
- Backup/restore/verify/FTS: PASS
- CSV and Shopify simulation enrichment: PASS
- Browser ambiguity and selection workflow: PASS

The bounded live Wikipedia test remains opt-in and was not run by default.
''',
"UX_FINDINGS.md": r'''# SnapIMS 0.7.0 UX Findings

## Closed

- Empty Title is now an inline quick field; typing it and pressing Enter performs Approve & Next once.
- Price remains automatically selected when Title is already populated.
- The exception editor is reserved for genuine validation/conflict work.
- Ctrl/Cmd+Shift+P opens the command palette; Ctrl/Cmd+K is a documented browser-safe fallback.
- Batch Editor supports spreadsheet-style arrows, Enter-to-save-and-move, Shift range selection, Space row toggle, and Ctrl/Cmd+A visible-row selection.
- Ctrl/Cmd+1–9 invokes the first nine quick actions through normal preview safety.
- Quick actions can be reordered, persist locally, and explain their effect/checkpoint/rollback behaviour.
- Same-version CSV export/import now round-trips without a false “Missing Item ID” blocker.
- Missing Tkinter becomes a manual-path fallback rather than an Import dead end.
- Movie ambiguity is shown as an exception; operator selection is explicit and auditable.

## Deferred

- Full 5,000-row virtualized editor and all-image QR performance architecture.
- Multi-user application sessions, roles, CSRF and concurrency controls.
- VHS Edition intelligence, automatic pooling, collection analytics and provider artwork.
- Automatic storefront publication.
''',
"SCREENSHOT_INDEX.md": r'''# SnapIMS 0.7.0 Screenshot Index

Browser evidence: `release-evidence/v0.7.0/browser/screenshots/`

1. `01-home-production.png` — Home in production mode
2. `02-import-preview.png` — 20-item Preview
3. `03-import-complete.png` — durable Import result
4. `04-empty-title-one-enter.png` — inline manual Title completed with one Enter
5. `05-catalog-ambiguity-preserved.png` — ambiguous Movie candidates
6. `05b-local-movie-catalog-match.png` — operator-selected local Movie match
7. `06-recognition-blocked-manual-recovery.png` — missing provider key and manual recovery
8. `07-price-enter-advances-once.png` — Price/Enter automatic advancement
9. `08-command-palette.png` — Quick Command Palette
10. `09-batch-editor-keyboard-grid.png` — keyboard grid, selection and quick action
11. `10-batch-editor-atomic-bulk.png` — atomic bulk Price result
12. `11-csv-difference-preview.png` — staged CSV difference preview
13. `12-shopify-simulation-test-mode.png` — explicit test-mode simulation
14. `13-restart-durability-production.png` — process restart durability
15. `14-shopify-simulation-production-manual-replacement.png` — production-safe simulation
16. `15-diagnostics-catalog.png` — schema and Movie Catalog diagnostics
''',
"DOCUMENTATION_VERIFICATION.md": r'''# SnapIMS 0.7.0 Documentation Verification

The 52-page Operator Guide was regenerated after the final v0.7.0 native browser audit. It uses the final 1440×1000 screenshots for Home, Import, Review, Movie ambiguity/selection, recognition recovery, Batch Editor keyboard operation, CSV, Publish, restart and Diagnostics.

Verification procedure:

- compare every button name, shortcut, state label and recovery instruction to the final browser UI;
- render DOCX through the approved document rendering tool;
- render the resulting PDF independently;
- inspect every page for clipping, overlap, unreadable screenshots and obsolete version references;
- follow the guide sequence against the browser evidence;
- retain explicit boundaries for live AI, live Shopify, live Wikipedia and warehouse scale.

Final files:

- `SnapIMS_Operator_Guide_v0.7.0.docx`
- `SnapIMS_Operator_Guide_v0.7.0.pdf`
- unversioned convenience copies with the same content.
''',
"GITHUB_PUSH_STATUS.md": r'''# GitHub Publication Status

Target repository: `fachingo/SnapIMS`  
Target branch: `feature/v0.7.0-keyboard-catalog`

The release is packaged as a complete repository and portable Git bundle. No force-push or automatic merge is performed by the release package.

Publish from MacMint:

```bash
cd ~/Projects/SnapIMS-v0.7.0
git status
git log -1 --oneline
git push -u origin feature/v0.7.0-keyboard-catalog
git push origin v0.7.0
```

Open a pull request into the owner-approved base branch only after CI and the real-operator review of the package.
''',
"SNAPIMS_V070_INSTALL_AND_RUN.md": r'''# SnapIMS 0.7.0 — Extract, Install, Test, Run and Push

## Extract

```bash
cd ~/Projects
unzip ~/Downloads/SnapIMS-v0.7.0-complete-repo.zip
cd ~/Projects/SnapIMS-v0.7.0
```

## Optional native Linux folder picker

```bash
sudo apt update
sudo apt install -y python3-tk
```

Without Tkinter, SnapIMS automatically exposes the manual-path fallback.

## Create environment and install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

## Configure OpenAI

```bash
cp -n .env.example .env
nano .env
```

In `.env`, set the `OPENAI_API_KEY` variable to the real key. Do not commit or paste the key into logs, screenshots, documentation, or support messages.

## Run with the existing data directory

```bash
snapims --data-dir ~/SnapIMS-data serve
```

Open `http://127.0.0.1:8767`.

## Run tests

```bash
pytest -q
python -m compileall -q snapims tests scripts
node --check snapims/web/static/app.js
git diff --check
```

## Catalog administration

```bash
python scripts/catalog_admin.py --data-dir ~/SnapIMS-data verify
python scripts/catalog_admin.py --data-dir ~/SnapIMS-data backup
```

## Push

```bash
git status
git push -u origin feature/v0.7.0-keyboard-catalog
git push origin v0.7.0
```
''',
}

# Reports completed after the final commit receive commit fields during packaging.
DOCS["FINAL_IMPLEMENTATION_REPORT.md"] = r'''# SnapIMS 0.7.0 Final Implementation Report

## Release identity

- Starting release: SnapIMS 0.6.1, inventory schema 7
- Ending release: SnapIMS 0.7.0, inventory schema 8, catalog schema 1
- Branch: `feature/v0.7.0-keyboard-catalog`
- Classification: **minor feature release**
- Production 1.0.0: **not authorized**

## Delivered

1. Permanent legacy recognition migration repair.
2. Native-folder-picker manual fallback and Linux dependency documentation.
3. Cross-page command-palette shortcut repair.
4. Inline manual Title and one-Enter Review.
5. Spreadsheet-style Batch Editor keyboard navigation and selection.
6. Ctrl/Cmd+1–9 quick actions, descriptions and persistent reorder.
7. Robust immutable-ID CSV export/upload round trip.
8. Independent local-first Movie Catalog with bounded Wikipedia integration.
9. Audited inventory Movie links, candidates, operator decisions and restart-safe jobs.
10. CSV/Shopify/Review/Diagnostics catalog integration.
11. Automated and native-browser verification.
12. Synchronized Operator Guide, reports, release artifacts and version references.

## Data and migration

- Existing Batch IDs, Item IDs, photos, saved values, recognition results, review state, checkpoints and Shopify linkage are preserved.
- Schema 8 removes the obsolete child table before recognition-job rebuild and fails closed if integrity, foreign keys or manifest verification fail.
- `movie_catalog.sqlite3` remains independent and rebuildable.
- Manual catalog jobs use deterministic negative identities; no nonexistent inventory recognition FK is stored.

## Verification summary

- Automated: 174 passed, 1 optional live-Wikipedia test skipped, 0 failed.
- Browser: PASS, Chromium 1440×1000.
- Console/page/relevant request/relevant HTTP errors: 0/0/0/0.
- Compileall, JavaScript syntax, diff check, wheel build and installed-wheel smoke: PASS.
- Inventory and catalog SQLite integrity/foreign-key verification: PASS.

## Not verified live

- OpenAI recognition quality, billing, latency and real-image correction rate.
- Live Wikipedia request in the default suite.
- Live Shopify draft creation/media upload.
- 5,000-row/10,000-photo warehouse-scale architecture.
- Multi-user remote operation.

## Required next action

Run the real 20-tape Pixel pilot with live AI, reconcile CSV, restart the production process, and create exactly one authorized Shopify draft. Do not label 1.0.0 until all acceptance gates pass.
'''

for name, text in DOCS.items():
    (ROOT / name).write_text(text.rstrip() + "\n", encoding="utf-8")
print(f"Wrote {len(DOCS)} release documents")
