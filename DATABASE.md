# SnapIMS 0.6.1 Database

Schema version: **7**

Startup verifies:

- required tables and columns;
- primary and unique constraints;
- required foreign keys;
- operational indexes;
- `PRAGMA integrity_check`;
- `PRAGMA foreign_key_check`.

A database claiming schema 7 but missing required structure fails closed. Older valid databases are backed up before migration. Legacy `recognition_jobs` tables are rebuilt so `batch_id` is the primary key, retaining the most recent job per batch.

New durability structures include:

- `schema_migrations`
- `batch_checkpoints` with size/protection/restore provenance
- `csv_staging` lifecycle and limits
- `import_journal`
- `operation_requests`
- recognition provider/model/source and measured payload fields

Run Diagnostics before restore or pilot work. Required state is integrity `ok`, zero foreign-key violations and a passing schema manifest.
