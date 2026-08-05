# SnapIMS v0.13.2 Rollback

Stop SnapIMS and preserve the complete current data directory before any rollback. Schema 15 is forward-only. Application-code rollback does not downgrade the inventory database.

Use the backup created under `~/SnapIMS-data/backups` before schema-v15 migration only when every v0.13.2 change that occurred after that backup can be discarded. Restore into a copied data directory first and verify integrity before replacing active data.

Never delete original photographs, the Batch Home Directory, logs, credentials, or the database to repair an Import Preview.
