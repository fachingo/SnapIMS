# SnapIMS Release Notes

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
