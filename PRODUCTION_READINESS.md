# SnapIMS 0.7.0 Production Readiness

Status: **controlled real-pilot candidate; not production 1.0.0**

## Verified in this release

- Existing-schema migration repair and schema 8 structural verification.
- One-Enter manual-title and Price-focused Review behaviour.
- Duplicate-submit protection and restart durability.
- Spreadsheet-style Batch Editor keyboard navigation and visible-row selection.
- Ctrl/Cmd+1–9 quick actions, preview safety, descriptions, reorder persistence, and atomic bulk operation.
- Same-version CSV export/upload/diff/apply round trip.
- Local-first Movie Catalog, bounded fixture-backed Wikipedia path, ambiguity preservation, operator selection, second-copy reuse, and catalog recovery/diagnostics.
- Production-mode Mock quarantine and blocked manual recovery.
- Shopify simulation with structured Movie data and draft-only safeguards.
- Native Chromium audit with no relevant console, page, network, or HTTP errors.

## Mandatory 1.0.0 blockers

1. Real 20-tape Pixel capture and import with zero physical/digital mismatch.
2. Live OpenAI recognition using real credentials and images, with measured latency, correction rate, failures, retries, and cost.
3. Downloaded CSV reconciled to the physical tapes and Review records.
4. Full application restart on the production Linux machine with all records/jobs/cursors preserved.
5. Exactly one deliberately authorized live Shopify draft, inspected for title, Price, Discount, quantity, SKU, images, metadata, and draft-only state.
6. First-time operator follows the final guide step by step; all UI/document discrepancies are fixed.
7. Final browser verification on the production machine and blocker review.
8. No known blocker for the claimed operating scale.

## Supported-scale statement

The verified browser fixture is 20 items. Existing evidence supports a controlled small-to-medium single-operator pilot. SnapIMS 0.7.0 does **not** claim 5,000-row workstation or 10,000-photo import readiness; bounded rendering and QR pipeline work remain deferred.

## External boundaries

- Live Wikipedia was not called during the default automated suite; bounded fixture transport verifies request/parse/persistence behaviour. The optional live test remains explicit.
- Live OpenAI and live Shopify were not exercised in the build environment.
- Cloudflare/Tailscale access does not make the application multi-user safe. Keep the application single-operator until per-user state, authorization, CSRF, and concurrency controls pass.
