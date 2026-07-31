# SNAPIMS v0.10.1 Audit Remediation Report

## Release decision

Target classification: **patch**  
Version transition: **0.10.0 → 0.10.1**  
Current artifact conclusion: **v0.10.1 PATCH BLOCKED pending host verification**

## Starting state

- Repository: `fachingo/SnapIMS`
- Accepted v0.9.0 baseline: `bda7093d8ca9b776b2e881ce38a09f10b222f56f`
- Audited v0.10.0 HEAD: `89a60b5c359803e33ba9e442ca2d27883305b2a9`
- Starting code schema: 12
- Target code schema: 13
- Catalog schema: unchanged

## Implemented patch corrections

1. Added durable database-backed Item recognition leases shared by batch and
   per-item requests.
2. Preserved valid baseline attempts when escalation fails and added a truthful
   partial-route warning.
3. Converted Retry This Item to the durable Phase-4 queue.
4. Added `record_revision` to Quick Approve and rejected stale browser writes.
5. Preserved operator-approved Price and Discount when recognition metadata is
   accepted.
6. Serialized Batch Editor saves per Item and retained dirty state until the newest
   value is acknowledged.
7. Retained Host, Origin, and CSRF enforcement when login is disabled and refused
   non-local unauthenticated operation.
8. Separated Recognition display pagination from aggregate totals and defined
   benchmark evaluation as accepted-first/current-selected-second.
9. Added visibility-aware polling and exponential backoff.
10. Corrected focus indication and Tag combobox/listbox semantics.
11. Reconciled Shopify media by stable `snapims:<item>:photo:<photo_id>` identity.
12. Advanced Review to the next unfinished physical sequence rather than the first
    unresolved Item.
13. Corrected active release notes, guide, implementation state, and version history.
14. Removed the accidental `ion bump"` file and added hygiene checks.

## Schema transition

Schema 13 adds:

- `recognition_item_leases`
- `idx_recognition_item_leases_status`

The existing initialization path provides the required pre-migration backup,
transactional migration, integrity check, foreign-key check, schema-manifest check,
and automatic restore after a failed migration. Production migration must still be
run on the SnapIMS host and reconciled against pre-migration row counts.

## Deferred by classification

### v1.0 acceptance, not v0.10.1 completion

- real 20-tape Pixel pilot;
- final live OpenAI quality/cost acceptance;
- live Shopify Draft acceptance;
- physical CSV reconciliation;
- final v1.0 restart/browser/operator-guide gates.

### Future minor release

- operator-facing live Shopify Draft action;
- large-batch pagination/virtualization architecture;
- new background Import workflow;
- broader mobile/narrow navigation redesign.

### Pre-existing or not proven to be a v0.10 regression

- cryptographically bound Import preview/commit contract;
- full elimination of repeated Import scanning;
- broad Review query consolidation;
- comprehensive legacy raw-error cleanup outside changed v0.10 routes.

## Verification performed in artifact workspace

- [x] Patch transformer compiled with Python.
- [x] Payload test and verification scripts compiled with Python.
- [x] Package manifest and SHA-256 checks generated.
- [x] No production database or media was accessed.
- [ ] Full repository patch application — requires complete source checkout.
- [ ] Full pytest/static/build gate — requires complete source checkout.
- [ ] Database migration on production-data copy — requires host database backup.
- [ ] Browser matrix — requires running SnapIMS and installed browsers.

## No-regression statement

The patch does not intentionally remove any v0.10 capability. It does not restore
v0.9 source, remove recognition history, change Item IDs, add a live Publish action,
or claim v1.0 readiness.

## Final host fields

- Final branch: `PENDING`
- Final SHA: `PENDING`
- Backup paths/checksums: `PENDING`
- Focused tests: `PENDING`
- Full tests/static/build: `PENDING`
- Targeted browser matrix: `PENDING`
- Production schema migration: `PENDING`

Final classification remains **v0.10.1 PATCH BLOCKED** until those fields are
replaced with passing evidence.
