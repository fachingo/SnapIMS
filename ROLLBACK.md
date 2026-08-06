# SnapIMS v0.15.0 Rollback

Stop SnapIMS and preserve the complete data directory before rollback. Inventory schema 16 is forward-only; installing older application code does not downgrade the database.

Use a copied `before-schema-v16` backup only when every change after that backup may be discarded. Verify SQLite integrity and foreign keys in a separate data directory before replacing active data.

Do not delete source photographs, batch folders, logs, credentials, Shopify job history, or the database to repair a workflow issue.
