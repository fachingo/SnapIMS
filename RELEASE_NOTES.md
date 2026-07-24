# SnapIMS Release Notes

## 0.5.1 - Verification hardening patch

This patch repairs the verification and delivery gaps in the 0.5.0 reconstruction candidate without introducing a new operator workflow.

### Fixed and verified

- created real local Git history and recovery artifacts;
- expanded regression coverage from 17 to 110 collected pytest tests;
- added migration backup/rollback/future-schema tests;
- added Shopify checkpoint, reconciliation, failure, media, and retry tests;
- replaced the hybrid audit with Chromium navigating a separately running uvicorn server;
- proved genuine recognition interruption by killing and restarting the process;
- regenerated Phase 1-5 browser reports;
- corrected timing terminology and audit evidence categories;
- regenerated and completely indexed 31 screenshots;
- synchronized application and documentation version references to 0.5.1.

### Historical note: 0.5.0

Version 0.5.0 reconstructed the missing fast Review, Import, recognition, CSV, and Shopify boundaries. Its audit used a hybrid TestClient transport and had only 17 tests; 0.5.1 supersedes it as the verification-hardened candidate.

### Still required before 1.0

Real Pixel pilot, live AI, one live Shopify draft, physical CSV verification, and independent guide walkthrough.
