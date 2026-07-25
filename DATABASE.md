# SnapIMS 0.6.0 + SLMC-0.1.0 Databases

This integration build uses two authoritative SQLite databases.

## Inventory database

Path: `<data-root>/database/inventory.sqlite3`
Current integration schema: **7**.

Durable entities include batches, physical Items, photos, recognition results/jobs, item change history, checkpoints, CSV staging, Review cursors, Shopify sync, one current Item-to-Movie link and append-only link events.

Schema 7 is an additive migration from schema 6. It preserves all Item IDs, Batch IDs, images, recognition history, operator values and publication state. Existing databases are backed up through the SQLite backup API before migration and checked with `integrity_check` and `foreign_key_check` afterward.

## Movie catalog database

Path: `<data-root>/database/movie_catalog.sqlite3`
Current catalog schema: **1**.

The catalog is permanent business data. It stores Movies, aliases, titles, sources, revisions, provenance, credits, genres, countries, languages, candidates, decisions, lookup jobs/attempts, bounded Wikipedia transport cache, settings, events, maintenance jobs and optional FTS5 search.

The catalog has an independent migration ledger, expected structural manifest, backup/restore path and integrity checks. It is not placed in Git and is not rebuildable-only cache data.

## Cross-database rule

SQLite cannot enforce a foreign key between the files. The service validates Movie identity before writing `item_movie_links`, records both catalog and inventory audit events, and reconciles `LINK_PENDING` operations after restart.

See `CATALOG_DATABASE_SCHEMA.md`, `INVENTORY_DATABASE_INTEGRATION.md` and `CROSS_DATABASE_RECOVERY.md`.
