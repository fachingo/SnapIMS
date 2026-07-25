# SnapIMS 0.7.0 Databases

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
