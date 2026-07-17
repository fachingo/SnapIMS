# SnapIMS database

SQLite is the durable system of record. CSV is the editing surface; Shopify is a downstream sales channel. The default file is `~/SnapIMS-data/database/inventory.sqlite3`.

## Schema and migrations

`snapims.db.initialize()` creates `schema_migrations`, checks applied versions, and applies ordered migration scripts. SQLite `user_version` is updated with each migration. Every connection enables foreign keys and WAL mode; write workflows use explicit transactions.

| Table | Purpose |
|---|---|
| `schema_migrations` | Applied schema version, timestamp, and description. |
| `batches` | Batch identity, source fingerprint, counts, status, and warnings. |
| `items` | Immutable Item ID/SKU plus editable catalog, validation, recognition, and Shopify summary fields. |
| `photos` | Product, command, and excluded source records, hashes, ordering, and preserved/processed paths. |
| `command_events` | Ordered executed command vocabulary with source-photo linkage. |
| `recognition_results` | Provider suggestions and explicit acceptance timestamp. |
| `catalog_products` | Future normalized reusable product catalog boundary. |
| `inventory_events` | Intake, location changes, and quantity deltas with source and time. |
| `shopify_sync` | Draft IDs, status, retry/error data, media count, and idempotency key. |
| `upload_attempts` | Per-attempt stage, outcome, error, and response audit. |
| `settings` | Application settings boundary for future UI-managed configuration. |

Indexes support batch item order, shelf lookup, upload queue, item photos, command stream, recognition history, and inventory history.

## Event history

Every imported item receives an `ITEM_INTAKE` inventory event at its QR shelf. Item-editor or CSV changes create `LOCATION_CHANGED` and `QUANTITY_ADJUSTED` events without rewriting history. The current operational state remains materialized on `items` for fast UI/CSV use, while the event table retains why and when it changed.

## Transactions

- Batch metadata, items, photos, command events, Shopify rows, and intake events are inserted in one transaction.
- CSV rows are parsed and all Item IDs are validated before a single update transaction begins. One unknown/duplicate/invalid identifier rejects the full import.
- Validation statuses for a selection are updated together.
- Shopify checkpoint, success, and failure updates each use short transactions.

## Backups

SQLite's online backup API creates a microsecond-stamped file under `backups/` before every batch import, CSV import, and live Shopify upload attempt. The backup uses a separate SQLite connection and is safe with WAL mode.

## Integrity checks

From the repository root:

```bash
.venv/bin/snapims integrity
```

This runs both `PRAGMA integrity_check` and `PRAGMA foreign_key_check`. The Streamlit **Database** page exposes integrity status and a fixed allowlist of database tables. It also exports inventory-event audit CSVs.

For an offline backup restore, stop SnapIMS, retain the damaged database for investigation, copy the chosen backup to `database/inventory.sqlite3`, and rerun the integrity command before reopening the UI.

## CSV identity rules

`inventory_work.csv` has one row per item. Import lookup uses only `Item ID`. Row order, title, and SKU text are never lookup keys. SKU remains equal to immutable Item ID; titles do not affect filenames. CSV output includes image, recognition, validation, Shopify ID/URL/error, and retry status fields for operator visibility.
