# Catalog Backup and Restore

## Required backup points

Back up both databases before catalog migration, inventory-link migration, Movie merge, Movie split, bulk import, catalog restore or server move.

## Application backup

```bash
PYTHONPATH=. python scripts/catalog_admin.py --data-root /path/to/data backup
```

The implementation uses SQLite's online backup API and writes a timestamped catalog backup under `<data-root>/backups/`.

## Verify before use

```bash
PYTHONPATH=. python scripts/catalog_admin.py --data-root /path/to/data verify
```

Require integrity `ok`, zero catalog FK violations, schema 1 and the expected structural manifest.

## Restore procedure

1. Stop SnapIMS and all catalog workers.
2. Preserve the damaged/current file and any `-wal`/`-shm` sidecars.
3. Verify the chosen backup in a separate temporary path.
4. Back up the current inventory database as well.
5. Replace `movie_catalog.sqlite3` only after explicit operator confirmation.
6. Start SnapIMS and run verify/reconcile.
7. Confirm linked Items resolve and Review/CSV/Shopify simulation show the intended Movie IDs.

Never create a new empty catalog over a recoverable damaged file.

## Moving between servers

Stop writers, create a verified online backup, copy the backup and source manifest, place it at `<new-data-root>/database/movie_catalog.sqlite3`, preserve ownership/permissions, run verify and reconcile, then resume workers. The catalog is independent of source-code checkout and must be carried across SnapIMS upgrades.
