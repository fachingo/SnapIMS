# SnapIMS v0.15.0 Production Readiness Report

**Decision:** CONDITIONAL OWNER-PILOT CANDIDATE — NOT v1.0.0

## Passed locally

- Complete Shopify publish UI from validation through draft creation and controlled live publication.
- Exact typed confirmations for live, direct-live, restore, archive, delete, keep-Shopify, and merge actions.
- Durable Shopify jobs, bounded retry, duplicate-active-job prevention, per-item persistence, browser-refresh safety, and restart recovery.
- Shopify Product/Variant/Inventory Item GID persistence and direct admin links.
- Publication discovery/selection and minimum-scope diagnostics.
- Product reconciliation, local-to-remote sync, Keep Shopify, merge, restore draft, archive, and delete logic with deterministic Shopify fakes.
- Local batch rename, archive, restore, duplicate, and recoverable soft delete.
- Schema-16 clean initialization and v0.14.0 linkage migration.
- 299 passed, 3 skipped, 0 failed across the complete collected test inventory.
- 52/52 Chromium browser checks passed at desktop and 390-pixel mobile widths.

## Still required before v1.0.0

- Real 20-tape Pixel pilot.
- Live OpenAI recognition with intended models and credentials.
- Live Shopify one-item draft creation, media/inventory verification, live publication, restore-to-draft/archive/delete checks, and duplicate/retry proof.
- Owner-machine restart durability during a real Shopify job.
- Native Firefox and direct Chromium walkthrough.
- Operator-guide walkthrough against the installed owner build.
- Target-hardware soak, backup/restore drill, remote-access security review, and zero unresolved Critical/High defects.

No skipped or simulated external capability is reported as a production pass.
