# Phase 5 Browser Verification - Import operator workflow

Version: **0.5.1**  
Browser-tested code commit: `411b51d9f72c8da1fd7f71eb5a42ae53fdfba026`  
Browser: local Chromium over real HTTP; viewport 1440 x 1000.

## Result

- Non-durable Preview identity: **Passed**.
- Exactly one durable Batch ID after import: **Passed**.
- Configured/recent folder workflow: **Passed**.
- Missing-folder fail-closed recovery: **Passed**.

## Browser sequence

1. Opened a fresh workspace and Import page.
2. Expanded Advanced, entered the camera-roll directory, and saved it as the incoming folder.
3. Selected **Preview batch** and observed `PREVIEW - NOT IMPORTED YET`, 20 items, 40 product photos, 24 commands, and zero warnings.
4. Selected **Preserve and import batch** and observed one durable ID: `20260724-191217-V051-PILOT`.
5. Selected **Continue to Review** and opened that same batch.
6. Repeated the workflow with two additional fixtures and observed recent-folder reuse.
7. Selected a nonexistent directory through Advanced and observed the fail-closed `Folder not available` state with Preview disabled.

Evidence: `operator-audit-assets/v0.5.1-browser/screenshots/01-first-run-import.png`, `operator-audit-assets/v0.5.1-browser/screenshots/02-preview-not-imported.png`, `operator-audit-assets/v0.5.1-browser/screenshots/02-imported-durable-id.png`, `operator-audit-assets/v0.5.1-browser/screenshots/16-preview-not-imported.png`, `operator-audit-assets/v0.5.1-browser/screenshots/16-imported-durable-id.png`, `operator-audit-assets/v0.5.1-browser/screenshots/19-missing-folder-recovery.png`.
