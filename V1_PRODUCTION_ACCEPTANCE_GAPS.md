# SnapIMS Pre-v1.0 Production Acceptance Gaps

v0.15.0 is not v1.0.0. Complete every item below before assigning 1.0.0.

1. **Real 20-tape Pixel pilot** through Import, Recognition, Review, Batch Editor, CSV, draft creation, and live publication.
2. **Live AI test** with intended models, retries, malformed output, rate limits, cost/token logging, and restart durability.
3. **Live Shopify pilot** proving one draft, media order, SKU/price/barcode, inventory location/quantity, optional review-tab workflow, `SUBMIT` live publication, restore draft, archive, delete test data, duplicate prevention, and restart recovery.
4. **CSV owner-batch verification** including export, edit, reorder, staged diff, invalid rollback, and row reconciliation.
5. **Restart durability** on target hardware during scan, Recognition, Review edits, draft upload, and live publish.
6. **Operator Guide walkthrough** step-by-step against the final installed browser UI.
7. **Native Firefox and Chromium verification** at desktop/mobile widths with console/network evidence.
8. **Backup/restore and rollback drill** using copied operator data.
9. **Eight-hour/repeated-workflow soak** covering memory, descriptors, WAL, logs, temporary files, queues, and token refresh.
10. **Deployment security review** covering auth, session revocation, CSRF, secret permissions, Cloudflare, Guacamole, xrdp, and remote boundaries.
11. **Target-machine performance validation**, including 5,000-item Batch Editor and real Pixel import.
12. **Zero unresolved Critical/High production defects** and no known production blockers.
