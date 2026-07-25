# SLMC Browser Verification Report

**Application:** SnapIMS 0.6.0  
**Package:** SLMC-0.1.0  
**Verified commit:** `dad21ce4d50684b9dfbe21c22cfbb6ab453fcad5`  
**Audit script:** `scripts/native_browser_audit_slmc.py`  
**Evidence:** `operator-audit-assets/slmc-0.1.0-browser/`

## Environment and monitoring

The audit launched the actual FastAPI/Jinja application through Uvicorn on loopback and Chromium at 1440×1000. Console errors, page errors, failed requests and server events were monitored before first navigation. The browser used deterministic camera images, the existing Mock recognition provider and deterministic Wikipedia fixtures.

## Verified workflow

1. Import Preview and Preserve completed through the real browser route.
2. Recognition committed both result rows.
3. `Demo VHS 001 (1991)` resolved from the permanent local catalog.
4. The first batch produced exactly one Wikipedia attempt for the genuine `Demo VHS 002` miss.
5. The miss created one durable Movie and linked the Item.
6. Pressing Enter approved item 1 exactly once and opened item 2.
7. Price and Discount values were preserved through approval.
8. Review showed the compact Local Match and New Catalog Record states.
9. A second physical batch reused both Movie records.
10. Wikipedia-attempt count remained exactly one after the second batch.
11. CSV contained immutable Item IDs and matching local Movie IDs plus structured facts.
12. Shopify simulation received the same Movie identities/facts.
13. No Shopify product ID, live draft or automatic publication was created.
14. Diagnostics displayed independent inventory/catalog integrity, schemas, counts, jobs and maintenance actions.
15. A full process restart preserved Movies, aliases, jobs and Item links.
16. Inventory integrity was `ok`, FK violations `0`, schema `7`.
17. Catalog integrity was `ok`, FK violations `0`, schema `1`.

## Request/error evidence

- page errors: **0**;
- unexpected request failures: **0**;
- expected Chromium `ERR_ABORTED` events: redirect/document replacement and CSV download only;
- console errors: two favicon 404 messages inherited from the host v0.6.0 UI; no JavaScript exception was observed.

## Screenshots

- `01-import-preview.png`
- `02-import-complete.png`
- `03-local-match-review.png`
- `04-new-wikipedia-record-and-next.png`
- `05-review-complete.png`
- `06-second-copy-local-reuse.png`
- `07-shopify-simulation.png`
- `08-catalog-diagnostics.png`
- `09-restart-durable-catalog.png`

## Limitations

This audit does not prove live AI, live Wikipedia, live Shopify draft creation, a real Pixel photo batch, production network reliability or all master-plan remediation. Those remain production acceptance gates. The audit proves the integration contract and deterministic restart/browser behaviour of this package.
