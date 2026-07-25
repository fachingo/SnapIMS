# SnapIMS 0.6.1 Architecture

## Runtime

FastAPI/Jinja browser workstation, local SQLite and filesystem media storage. The CLI binds to localhost by default. SnapIMS is single-operator and does not auto-publish Shopify products.

## Durable authority

- SQLite: batches, immutable items, photos, recognition history, working values, audits, Shopify linkage, operation requests, checkpoints and import journals.
- CSV: staged editing surface keyed only by immutable Item ID.
- Original media: never overwritten.
- Shopify: external draft/sales channel; local rollback does not pretend remote state was reverted.

## Transaction boundaries

- CSV apply: one validation pass, one checkpoint, one SQLite transaction, field audit and stage completion together.
- Bulk edit: full selection validation, idempotent request ID, one checkpoint and one transaction.
- External review: all items validate before any completion state changes.
- Checkpoint restore: protected safety checkpoint plus audited field changes in one transaction.

## Cross-resource import recovery

Import writes a durable journal before final filesystem moves. Startup reconciliation completes, resumes, fails or quarantines incomplete operations without inventing new identities.

## Value-state model

`SUGGESTED` -> provider output not accepted.
`SAVED` -> durable working value.
`REVIEWED` -> human or approved external workflow accepted the record.
`DRAFTED/PUBLISHED` -> remote Shopify state, separate from local working state.

## Security boundary

Test providers require `SNAPIMS_ENABLE_TEST_PROVIDERS=true`. Production mode rejects them server-side. Application authentication and multi-user security remain deferred.
