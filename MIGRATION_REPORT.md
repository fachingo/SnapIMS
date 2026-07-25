# SnapIMS 0.7.0 Migration Report

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
