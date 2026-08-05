# SnapIMS v0.13.2 Test Results

**Date:** August 4, 2026  
**Verdict:** PASS for local code, database, browser-harness, installer, migration, and restart verification.

## Complete suite

- **273 passed**
- **3 skipped**
- **0 failed**
- One Python process
- Duration: **107.84 seconds**

## Skips

| Test | Reason |
| --- | --- |
| Live English Wikipedia lookup | Opt-in live integration; SNAPIMS_LIVE_WIKIPEDIA_TEST was not enabled. |
| HEIC runtime fixture | `pillow_heif` was unavailable in the test runtime. |
| Launcher installer operator-user test | Installer intentionally refuses root; separate non-root-equivalent HOME/service rewrite tests were run. |

## Additional checks

- Python compilation: PASS
- JavaScript syntax: PASS
- Installer shell syntax: PASS
- Built wheel metadata: 0.13.2
- Clean install: PASS
- v0.12.3 database upgrade to schema 15: PASS
- Stale launcher/service rewrite: PASS
- Two successive server starts and health checks: PASS
- Browser checks: 33/33 PASS

## Data preservation

The upgrade fixture retained two Items and one Batch. Active launcher and service files no longer referenced the stale `/home/isaiah/Projects/SnapIMS` path.
