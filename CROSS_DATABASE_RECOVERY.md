# Cross-Database Recovery

## Consistency model

The two SQLite files do not share one atomic foreign-key transaction. SLMC uses a durable saga:

1. commit or locate Movie;
2. record catalog event/revision;
3. commit Item link;
4. mark `LINK_PENDING` if the inventory write fails;
5. retry idempotently on restart or administrator reconciliation.

## Startup recovery

- orphaned running catalog jobs become recoverable/paused work;
- completed Movie creation with missing Item link is reconciled;
- duplicate job creation is prevented by `recognition_result_id` uniqueness;
- missing Movie link targets are reported as stale/missing, never cascaded away;
- catalog maintenance jobs retain explicit state and error detail.

## Catalog unavailable

Do not delete or rename the suspect file. Preserve it and its WAL/SHM files, stop catalog writes, copy Diagnostics, and make a filesystem-level preservation copy. Inventory recognition, physical records, Review and Approve & Next remain operational using AI/operator titles. CSV and Shopify must not claim catalog fields.

## Inventory unavailable

Do not create fake physical Items and do not run Item-linking. Explicit catalog-only verify/export/backup operations may continue. Restore inventory from a verified backup, run integrity and foreign-key checks, then reconcile pending links.

## Link reconciliation command

```bash
PYTHONPATH=. python scripts/catalog_admin.py --data-root /path/to/data reconcile
```

## Recovery verification

After any restore or reconciliation:

- inventory integrity `ok`;
- inventory FK violations `0`;
- inventory schema `7`;
- catalog integrity `ok`;
- catalog FK violations `0`;
- catalog schema `1`;
- each current Item link resolves to one active Movie;
- no title, Price, Discount, location, photo or Item identity changed unexpectedly.
