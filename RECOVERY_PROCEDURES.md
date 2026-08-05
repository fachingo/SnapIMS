# SnapIMS v0.13.2 Recovery Procedures

## Wrong version or wrong source path

```bash
snapims status
```

Verify Version, Project path, Python executable, Data directory, and Inventory schema. Re-run `install_v0132.sh` from the intended extracted release to rewrite the pinned launcher and user service.

## Port already occupied

`snapims up` refuses to claim a port owned by another release or unmanaged process. Stop the old service first, then run `snapims up` again. Do not delete PID files blindly.

## Interrupted Import

Reopen Import. The active folder job is durable and appears as in progress or ready to resume. Starting the same folder again reuses the existing job. Repeated Commit is idempotent.

## Database migration problem

Stop SnapIMS. Preserve the current data directory. Use the pre-schema-v15 backup under `~/SnapIMS-data/backups`. Do not delete the database. Review logs and restore only from a copied backup.

## Failed external service

Open Diagnostics and read the provider-specific status. Keep failed live AI or Shopify actions as failed/blocked; do not treat blank results as success. Use deterministic tests only for diagnosis, never as production evidence.
