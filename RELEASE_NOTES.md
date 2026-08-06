# SnapIMS v0.15.0 Release Notes

**Release date:** August 4, 2026  
**Release type:** Minor release (`0.14.0 → 0.15.0`)  
**Status:** Owner-pilot candidate; not v1.0.0

## Complete Shopify publish workflow

- Added five explicit stages: Validate, Simulate, Create Drafts, Review Drafts, Publish Live.
- Wired the existing `ShopifyService.upload_draft()` implementation into a real POST workflow.
- Added durable background Shopify jobs with per-item status, progress, rate, elapsed time, ETA, bounded retries, and restart recovery.
- Automatically opens Shopify Draft Products in another browser tab after successful draft creation.
- Added exact `SUBMIT` confirmation for live publication.
- Added direct-live override requiring exact `SUBMIT LIVE`; draft-first remains the default.
- Added publication discovery and publication selection in Settings.
- Added Product ACTIVE/DRAFT/ARCHIVED lifecycle control and `publishablePublish` support.

## Product and batch management

- Added checked-product and entire-batch operations.
- Added read-only reconciliation, local-to-Shopify sync, Keep Shopify, and non-conflicting merge.
- Added restore-to-draft, archive, and irreversible permanent deletion with typed confirmations.
- Added local batch rename, archive, restore, duplicate, and recoverable soft delete.
- Batch duplication clears Shopify identities so a copied local batch cannot silently reuse remote product linkage.
- Added persistent conflict details and product/sync state display.

## CLI and diagnostics

- Added `snapims help`.
- Added `snapims shopify status`, `test`, `refresh`, and `jobs`.
- Fixed CLI/runtime data-directory alignment so web and CLI read the same secret store and database.
- Added Shopify store, token, location, publication, product-state, and durable-job diagnostics without exposing secrets.

## Database

- Inventory schema increased from 15 to 16.
- Added durable Shopify job and job-item tables.
- Extended Shopify synchronization state with product status, conflict JSON, lifecycle timestamps, and last action.
- Existing v0.14.0 linkage IDs, inventory, recognition, prices, tags, images, and history are preserved during forward migration.

## Safety

- Simulation is read-only and remains mandatory in the default workflow.
- Completed job items are not repeated on resume.
- Duplicate active jobs for the same batch/action are rejected.
- Live publishing requires a selected publication and exact typed confirmation.
- Product deletion is labeled irreversible and requires `DELETE`.

## Verification

- 302 tests collected: 299 passed and 3 skipped in bounded groups; 0 failed.
- 52/52 Chromium browser checks passed.
- No console errors, page errors, unexpected failed requests, or HTTP 500 responses were recorded.
- Live owner-store writes were not performed in the sandbox; deterministic Shopify fakes covered the complete job and lifecycle logic.
