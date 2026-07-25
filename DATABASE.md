# SnapIMS 0.6.0 Database

Current schema version: **6**.

Important durable entities:

- `batches`: immutable import identity and source fingerprint.
- `items`: authoritative working inventory records and immutable Item IDs/SKUs.
- `photos`: original, preview, recognition paths and byte accounting.
- `recognition_results`: append-only AI suggestions, confidence, uncertainty, pricing-source label, and token use.
- `recognition_jobs`: durable provider state, progress, failure details, and recovery timestamps.
- `item_change_log`: field-level audit trail.
- `batch_checkpoints`: rollback snapshots before CSV replacement and bulk edits.
- `csv_staging`: unapplied CSV previews and blocking errors.
- `review_cursors`: restart-durable Review position.

Migrations back up an existing database before schema changes. Legacy recognition-job tables that allow multiple rows per batch remain supported through SQLite `rowid` selection until a future explicit normalization migration is justified.
