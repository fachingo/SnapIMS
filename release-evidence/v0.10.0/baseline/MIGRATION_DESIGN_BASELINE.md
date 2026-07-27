# v0.10.0 Migration Design Baseline

This is the pre-schema-change contract required by the integrated roadmap. Exact migration numbers and DDL will be finalized phase by phase after predecessor gates pass.

## Current schemas

- Inventory schema: 8
- Catalog schema: 1
- Both production databases pass integrity, foreign-key, and application structure checks.
- The external pre-work online backups and restore probes are recorded in `V010_IMPLEMENTATION_STATE.md`.

## Permanent preservation invariants

No migration may regenerate, repurpose, or detach:

- Batch ID or source fingerprint;
- Item ID, SKU, physical sequence, or image linkage;
- location/inventory/change/Review history;
- existing recognition result IDs or evidence;
- existing Movie IDs, sources, candidates, decisions, or Item links;
- existing Shopify product, variant, inventory Item, attempt, or checkpoint IDs.

External provider IDs, titles, aliases, and list positions are references, never physical identity.

## Planned inventory evolution

Expected forward-only additions include:

- authentication generation, login-failure/audit, and security metadata;
- approved Tag taxonomy, aliases, and Item-to-Tag history;
- operational events and retention metadata;
- non-secret settings metadata and provenance (never secret values);
- expanded recognition attempt tier/trigger/forced/image/prompt/schema/cost/selection fields;
- availability transitions, movements, quantities, holds, and quarantine history;
- editions and Item-to-Edition links;
- global inventory FTS/index support;
- durable Shopify listing links and outbound logical steps/idempotency/request hashes;
- order, revision, line, sync cursor, webhook delivery, reservation, pick task, fulfillment attempt, and reconciliation entities.

Constraints must enforce nonnegative quantity, exact Item mapping, one active exclusive reservation per Item, idempotent provider identities, and validated transition history. SQLite partial unique indexes and transactional compare/revision checks should be used where CHECK alone cannot enforce cross-row state.

## Planned catalog evolution

Expected forward-only additions include:

- provider registry/policy/capability records;
- Wikidata provider-source uniqueness and field-level provenance;
- bounded Wikipedia enrichment provenance/attribution;
- expanded candidate decisions/outcomes;
- inventory-bootstrap/dump/incremental job/checkpoint/source-version records;
- minimum Edition facts only where catalog authority belongs outside inventory;
- FTS/index migrations that rebuild safely and verify row parity.

Existing Movie IDs and aliases are preserved. Retry/restart must not create a second Movie for the same accepted provider entity.

## Backup and migration sequence

For every schema migration:

1. Refuse a schema newer than supported.
2. Verify source integrity, foreign keys, and the expected manifest.
3. Create an online database backup outside the live DB files.
4. Record checksum, size, source schema, target schema, and operation ID.
5. Exercise DDL/data migration against a disposable copy.
6. Run injected interruption and re-entry tests.
7. Apply in one bounded transaction where SQLite permits.
8. Record the migration row and set `user_version` last.
9. Verify integrity, foreign keys, manifest, uniqueness, indexes/FTS, and identity counts.
10. On failure, leave the original/backup untouched and provide forward-repair or restore instructions.

## Rollback policy

Production migrations are forward-only after successful commit. Rollback means restoring a validated online backup while the application is stopped or applying a separately tested forward repair; it does not mean dropping new tables ad hoc. External Shopify effects are reconciled, never "rolled back" by blindly recreating or deleting remote state.

## Interruption/restart cases

Disposable tests must cover interruption:

- before backup completion;
- after backup and before DDL;
- during data copy/index rebuild;
- after DDL but before version record;
- after version record but before post-check;
- while an application process with the previous schema is still alive.

Re-entry must either safely resume or fail with a precise repair instruction. No identity-bearing row may be duplicated or omitted.
