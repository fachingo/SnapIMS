# SnapIMS project status

Version: **0.5.0 reconstruction release**

Classification: **functional beta candidate**

## Verified in this build

- Deterministic NEXT-only parser and QR vocabulary.
- Original preservation, safe JPEG generation, immutable Item IDs, and duplicate imports.
- Unified workstation with saved-value precedence.
- Completed-item correction, cancellation, validation, and restart durability.
- Durable recognition states and physical queue position.
- Configured/recent import folders and non-durable Preview identity.
- One-click approval with inline Price and Discount.
- Safe partial CSV import; Release year and Discount export.
- Shopify simulation and hardened resumable stage design.
- 17/20 one-click browser approvals; 1.20 average clicks per tape.
- 17 automated tests passing locally.

## Environment limitation

The execution environment blocks direct Chromium access to loopback servers. Browser verification used real Chromium rendering and visible controls, with form submissions transported to the FastAPI application through an in-process ASGI harness. This verifies rendered UI, controls, application responses, and durable state, but not the environment's blocked TCP loopback path.

## Required before 1.0.0

- Real 20-tape Pixel pilot.
- Live AI tested with real tape images.
- One live Shopify draft created and reconciled.
- CSV reconciled against the physical batch.
- Final native deployment browser walkthrough.
- Operator Guide followed by a first-time operator.
- No remaining production blockers.
