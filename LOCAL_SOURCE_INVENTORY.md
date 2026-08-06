# SnapIMS v0.15.0 Local Source Inventory

## Baseline

- Source baseline: complete SnapIMS v0.14.0 release snapshot.
- Baseline application: `0.14.0`, inventory schema 15.
- Target release: `0.15.0`, inventory schema 16.
- Working branch: `feature/v0.15.0-shopify-publish-workflow`.

## New and materially changed source

- `snapims/migrations/0016_shopify_publish_workflow.sql` — durable Shopify job, item-stage, and richer synchronization state.
- `snapims/shopify/jobs.py` — create drafts, publish live, direct live, sync, reconcile, archive, restore, delete, Keep Shopify, merge, recovery, progress, and bounded retry.
- `snapims/shopify/service.py` — Shopify lifecycle operations and conflict persistence.
- `snapims/shopify/client.py` — product update/status, publication, unpublication, deletion, inventory/media, and remote snapshot operations.
- `snapims/web/app.py` and `snapims/web/templates/publish.html` — complete browser publish workflow and batch/product management.
- `snapims/web/static/app.js` — typed confirmations, durable job polling, progress, selection, Shopify-tab opening, and copy controls.
- `snapims/config.py`, `snapims/settings.py`, and `snapims/provider_probes.py` — publication configuration and authoritative capability checks.
- `snapims/cli.py` — aligned runtime context and `snapims shopify status/test/refresh/jobs`.
- `tests/test_shopify_publish_v0150.py` and `tests/test_publish_web_v0150.py` — deterministic workflow and browser-route coverage.
- `scripts/browser_verify_v0150.py` — 52-check desktop/mobile browser verification.
- `docs/SnapIMS_v0.15.0_*` — final operator-facing DOCX and PDF guides.

## Test and evidence inventory

- Automated suite: 299 passed, 3 skipped, 0 failed.
- Browser verification: 52 / 52 passed; zero console/page errors, unexpected failed requests, or HTTP 500 responses.
- Evidence: `release-evidence/v0.15.0/` and `browser-evidence/v0.15.0/`.

## External limitations

Live owner-store writes, live OpenAI, native Firefox, owner remote infrastructure, target hardware, and a real HEIC file were unavailable in the sandbox and are not claimed as live passes. Deterministic Shopify transports covered mutation behavior and state transitions.
