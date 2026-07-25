# SnapIMS 0.7.0 Architecture

SnapIMS is a localhost-bound FastAPI/Jinja workstation with two SQLite databases and filesystem-managed original/processed media.

## Inventory authority

`inventory.sqlite3` schema 8 owns physical Batch/Item identity, photos, sequence, shelf, condition, money, Review, recognition, checkpoints, CSV staging, audit events, Shopify state and current Movie links.

## Rebuildable Movie Catalog

`movie_catalog.sqlite3` catalog schema 1 owns normalized Movie facts, aliases, FTS search, candidates, decisions, source provenance, bounded Wikipedia response cache, lookup jobs and maintenance events. It is intentionally separate from physical inventory.

## Service boundaries

- Import: deterministic QR stream parsing, staging, durable journal and final media reconciliation.
- Recognition: provider abstraction, durable batch state, provenance and test-provider quarantine.
- Review: one-Enter quick transaction for Title/Price/Discount; exception editor only for genuine problems.
- Batch Editor: browser grid, optimistic revisions, autosave, atomic bulk services and checkpoints.
- CSV: immutable-ID export, tolerant safe parsing, staged diff, atomic apply and rollback.
- Catalog: local-first normalized search, bounded external source adapter, background jobs and audited links.
- Shopify: saved working values, structured Movie projection, draft-only simulation/live architecture and idempotent stage recovery.
- Diagnostics: inventory/catalog integrity, schema manifest, jobs, WAL, backups and recovery state.

The browser remains the operator source of truth. UI code calls service/database boundaries rather than directly inventing authority. Remote exposure remains single-user and deny-by-default until application authentication, per-user state, CSRF and concurrency controls pass.
