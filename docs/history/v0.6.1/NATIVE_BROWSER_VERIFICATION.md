# SnapIMS 0.6.1 Native Browser Verification

Status: **PASSED**

The release audit used native headless Chromium at 1440 x 1000. Console, page-error, request-failure and HTTP-response listeners were attached before the first navigation.

Verified:

- Home metrics contain operator values, not Python method objects.
- A 20-item camera fixture previews and imports with one durable Batch ID.
- Production mode hides Mock and a forged/test provider cannot be selected normally.
- Missing OpenAI credentials produce a BLOCKED state with manual-review and Diagnostics actions.
- Explicit test mode produces suggestions visibly labelled as unsaved.
- Price -> Enter approves exactly one item and refocuses Price.
- A 20-row bulk price operation applies through one confirmation model.
- The command palette opens with Ctrl+Shift+P and closes with Escape.
- CSV upload enters a difference preview, then applies after explicit confirmation.
- External review and Shopify simulation complete in explicit test mode.
- Saved values and the immutable batch survive a full server-process restart.
- Production-mode simulation uses confirmed working values while historical test evidence remains diagnostic.
- Diagnostics exposes schema, database/WAL storage, stages, checkpoints, import journals and provider provenance.
- Favicon returns 200.

Results:

- Console errors: 0
- Page errors: 0
- Relevant failed requests: 0
- Relevant HTTP errors: 0
- One `net::ERR_ABORTED` was recorded for the intentional browser file-download navigation and classified as expected.

Evidence: `release-evidence/v0.6.1/browser/`.
