# SnapIMS v0.15.0 Browser Verification

**Date:** August 4, 2026  
**Result:** PASS — 52/52 checks

## Method

The harness ran the real SnapIMS server and rendered its actual HTML, CSS, JavaScript, API responses, and durable database state in Chromium. A managed browser policy blocked direct localhost navigation, so the harness relayed local HTTP reads/fetches while preserving production templates and handlers.

## Publish workflow verified

- Stage 1 validation displays PASSED for a ready batch.
- Stage 2 simulation is explicit and read-only.
- Create Shopify Drafts is enabled only after simulation/configuration gates pass.
- Publish Drafts Live is disabled until exact `SUBMIT` is entered.
- Direct live remains disabled until exact `SUBMIT LIVE` is entered.
- Durable completed draft job shows 100% progress, per-item success, Product GIDs, and Shopify links.
- Product bulk management and permanent-delete warning are visible.
- Shopify publish page fits a 390-pixel body without horizontal page overflow.
- Shopify diagnostics show publication and durable jobs.

## Inherited workflows verified

- Home, Import, Recognition, Review, Publish, Settings, and Diagnostics load successfully.
- Shopify credential UI has Client ID/Secret, no normal manual token field, and mobile-safe layout.
- Batch Editor Fill Down supports Tags, Location, Review, and Rare.
- Hidden selections clear; keyboard navigation crosses Tags.
- 5,000-item editor returns 100 rows and 430,721 bytes; relayed render completed in 0.471 seconds.
- 100-item/202-photo Preview returned promptly, survived refresh, grouped 100 Items, scanned each image once, and displayed 20 preview Items per page.

## Evidence

- `browser-evidence/v0.15.0/browser-verification.json`
- `browser-evidence/v0.15.0/chromium-publish-workflow.png`
- `browser-evidence/v0.15.0/chromium-publish-drafts-complete.png`
- `browser-evidence/v0.15.0/chromium-mobile-publish.png`
- `browser-evidence/v0.15.0/chromium-diagnostics-shopify.png`
- `browser-evidence/v0.15.0/chromium-shopify-settings.png`
- `browser-evidence/v0.15.0/chromium-batch-editor.png`
- `browser-evidence/v0.15.0/chromium-mobile-editor.png`
- `browser-evidence/v0.15.0/chromium-import-preview.png`
- `browser-evidence/v0.15.0/server.log`

Native Firefox and live owner credentials remain external acceptance checks.
