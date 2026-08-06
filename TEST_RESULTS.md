# SnapIMS v0.15.0 Test Results

**Date:** August 4, 2026  
**Verdict:** PASS for local code, schema migration, deterministic Shopify workflow, browser UI, and static checks.

## Complete automated inventory

- **302 tests collected**
- **299 passed**
- **3 skipped**
- **0 failed**

The suite was executed in bounded groups because the environment limits long single tool executions. Every collected test file completed successfully in its final run.

## Skips

| Test | Reason |
| --- | --- |
| Live English Wikipedia integration | Requires explicit `SNAPIMS_LIVE_WIKIPEDIA_TEST=1`. |
| HEIC import fixture | Optional `pillow_heif` runtime was unavailable. |
| Launcher operator-user check | Installer intentionally refuses root; must be run as the operator user. |

## Shopify v0.15.0 coverage

- Draft/live/direct job creation and exact confirmation rules.
- Durable job rows and per-item progress.
- Restart recovery and completed-item idempotency.
- Bounded transient retry and no unbounded loop.
- Publication requirement for live publishing.
- Draft creation, Product/Variant/Inventory GID persistence, inventory, media, and reconciliation.
- Product ACTIVE/DRAFT/ARCHIVED/DELETED lifecycle.
- Keep SnapIMS, Keep Shopify, merge, and conflict persistence.
- Batch duplicate identity clearing and recoverable local deletion.
- Settings publication selection, CLI Shopify commands, and diagnostics.
- Schema-16 clean install and v0.14.0 linkage migration.

## Browser verification

- **52/52 checks passed** in Chromium.
- Desktop and 390-pixel Publish workflow rendered without body overflow.
- Validation, simulation, draft action, typed `SUBMIT`, typed `SUBMIT LIVE`, durable completed job, Shopify links, product management, and diagnostics were verified.
- Console errors: 0.
- Page errors: 0.
- Unexpected failed requests: 0.
- HTTP 500 responses: 0.

## External limitation

No live Shopify write or live OpenAI call was made in the sandbox. See `SKIPPED_EXTERNAL_TESTS.md`.
