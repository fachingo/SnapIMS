# SnapIMS 0.7.0 Local Movie Catalog Integration Report

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
