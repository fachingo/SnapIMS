# SnapIMS Release Notes

## 0.6.1 - Mega Stabilization Patch

Release type: **patch**. This release repairs correctness, integrity, recovery and truthfulness defects without introducing a new major operator workflow.

### Data integrity

- CSV application, bulk operations and external review are now deliberate all-or-nothing transactions.
- Failed operations leave zero partial authoritative changes and record a failed operation result.
- Durable import journals reconcile interrupted filesystem/database finalization after restart.
- Checkpoint restore is audited and creates a protected pre-restore safety checkpoint.
- Schema 7 verifies tables, columns, indexes, unique constraints and foreign keys rather than trusting `user_version` alone.
- Legacy `recognition_jobs` tables without a unique batch constraint are rebuilt safely; the most recent job per batch is retained.

### Operator truth

- Mock, fixture, demo and synthetic providers are disabled by default and rejected server-side in production mode.
- Historical test provenance remains visible and cannot silently become live-publish truth.
- AI suggestions are visually and structurally separate from saved working values.
- Latest suggestion confidence is visible on unfinished recognized items.
- Missing credentials produce BLOCKED / not-attempted states with manual-review recovery.
- Retry Batch and Retry Failed Items Only use distinct scopes.
- Home, throughput, image, bandwidth and cost metrics no longer display Python internals or unsupported estimates.

### Workflow reliability

- Review keeps the Price -> Enter -> next-tape rhythm.
- Batch Editor bulk changes use one confirmation dialog, one transaction and idempotent request IDs.
- Save All reports changed, unchanged and failed cells accurately.
- CSV upload remains staged behind a difference preview and confirmation.
- Favicon and browser-console regressions are covered.

### Verification

- 136 automated tests collected and every test file passed in the release environment.
- A native Chromium walkthrough completed a 20-item import, production provider guard, blocked-provider recovery, explicit test-mode recognition, Price -> Enter, 20-row bulk edit, CSV diff/apply, external review, Shopify simulation, process restart and Diagnostics.
- Browser monitoring was active before first navigation. No console errors, page errors, relevant failed requests or HTTP errors were recorded.

### Deliberately deferred

Full 5,000-row virtualization, warehouse-scale QR architecture, adaptive recognition, multi-user application security, metadata enrichment and duplicate intelligence remain future minor releases.

SnapIMS 1.0.0 remains forbidden until the real 20-tape Pixel pilot, live AI, one live Shopify draft, physical CSV verification, restart durability, independent guide walkthrough, browser verification and blocker review pass.
