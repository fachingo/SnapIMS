# SnapIMS database - schema version 5

SQLite is the durable system of record. The database defaults to `~/SnapIMS-data/database/inventory.sqlite3`.

## Important tables

- `batches`: durable batch identity and source fingerprint.
- `items`: current authoritative inventory record and immutable Item ID/SKU.
- `photos`: product, command, and excluded images.
- `recognition_results`: append-only AI suggestions and acceptance timestamp.
- `recognition_jobs`: durable running, paused, complete, failed, and review-complete state.
- `review_cursors`: persistent selected item per batch and queue.
- `inventory_events`: intake, location changes, and quantity adjustments.
- `shopify_sync`: resumable external IDs and last completed stage.
- `upload_attempts`: Shopify attempt history.
- `settings`: incoming folder and bounded recent-folder history.

## Migration safety

Before an existing database is upgraded, SnapIMS creates an online SQLite backup. Migration runs in an explicit transaction and is followed by `PRAGMA integrity_check` and `PRAGMA foreign_key_check`.

## Identity

- Batch: `YYYYMMDD-HHMMSS[-NAME]`
- Item and SKU: `<BATCH-ID>-<SHELF>-<SEQUENCE>`
- Images: `<ITEM-ID>-F.jpg`, `<ITEM-ID>-02.jpg`, and so on

Titles never determine identity or filenames.

## CSV safety

CSV lookup uses only Item ID. Missing columns preserve existing values. A partial CSV cannot silently blank unrelated fields. Unknown or duplicate Item IDs reject the import before writes begin.
