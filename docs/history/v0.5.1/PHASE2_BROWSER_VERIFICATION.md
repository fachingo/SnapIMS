# Phase 2 Browser Verification - Completed-item correction

Version: **0.5.1**  
Browser-tested code commit: `411b51d9f72c8da1fd7f71eb5a42ae53fdfba026`  
Browser: local Chromium through the real uvicorn server; viewport 1440 x 1000.

## Result

**Passed.** A Done item was reopened, corrected, validated, cancelled after an invalid attempt, and reloaded after a full server restart without changing its immutable Item ID.

## Observed sequence

1. Opened item 1 in the Done queue and selected **Edit item**.
2. Changed the title and price, then selected **Save changes**.
3. Verified the same Item ID remained selected and the saved summary changed.
4. Reopened Edit, cleared Title, set Price to zero, and attempted Save.
5. Observed `Changes not saved`, `Title is required`, and `Price must be greater than zero`.
6. Selected **Cancel changes** and observed the valid saved record.
7. Stopped and restarted the actual uvicorn process, reopened the same URL, and verified the correction and Item ID survived.
8. Verified the corrected record in Publish simulation and the browser-downloaded CSV.

Evidence: `operator-audit-assets/v0.5.1-browser/screenshots/11-completed-item-corrected.png`, `operator-audit-assets/v0.5.1-browser/screenshots/12-invalid-edit-blocked.png`, `operator-audit-assets/v0.5.1-browser/screenshots/13-invalid-edit-cancelled.png`, `operator-audit-assets/v0.5.1-browser/screenshots/14-restart-durable-correction.png`, `operator-audit-assets/v0.5.1-browser/screenshots/15-publish-simulation.png`.
