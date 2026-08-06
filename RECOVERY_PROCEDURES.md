# SnapIMS v0.15.0 Recovery Procedures

## Wrong version or path

Run `snapims status`. Confirm version 0.15.0, schema 16 / 16, project path, Python executable, and data directory. Re-run `install_v0150.sh` from the intended release if needed.

## Interrupted Shopify job

Reopen **Publish**. Jobs in QUEUED/RUNNING/RETRYING states are recovered at application startup. Completed Items are not repeated. Use **Retry failed or interrupted Items** for failed rows.

## Shopify credentials or token

Run:

```bash
snapims shopify status
snapims shopify test
snapims shopify refresh
```

Credential rotation invalidates cached access. Do not manually edit encrypted secret files.

## Wrong remote state

Run **Check Shopify status** on selected Items. Resolve differences with Keep SnapIMS, Keep Shopify, or Merge. Permanent deletion cannot be recovered; prefer Restore Draft or Archive when uncertain.

## Migration problem

Stop SnapIMS. Preserve current data. Restore only from a copied pre-schema-16 backup. Do not delete the active database.

## Interrupted Import

Reopen Import. Same-folder Preview reuses the durable job; repeated Commit is idempotent.
