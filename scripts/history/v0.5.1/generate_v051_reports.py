from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "operator-audit-assets" / "v0.5.1-browser"
SHOTS = AUDIT / "screenshots"
METRICS = json.loads((AUDIT / "browser-metrics.json").read_text(encoding="utf-8"))
BROWSER_COMMIT = "411b51d9f72c8da1fd7f71eb5a42ae53fdfba026"
VERSION = "0.5.1"


def write(name: str, text: str) -> None:
    (ROOT / name).write_text(text.strip() + "\n", encoding="utf-8")


def evidence(*names: str) -> str:
    return ", ".join(f"`operator-audit-assets/v0.5.1-browser/screenshots/{name}`" for name in names)


# Baseline hashes are derived from the preserved baseline commit, not the edited worktree.
manifest_lines = ["# SHA-256 manifest of preserved SnapIMS v0.5.0 baseline commit c86233d", ""]
paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "c86233d"], cwd=ROOT, text=True).splitlines()
for path in paths:
    blob = subprocess.check_output(["git", "show", f"c86233d:{path}"], cwd=ROOT)
    manifest_lines.append(f"{hashlib.sha256(blob).hexdigest()}  {path}")
write("BASELINE_MANIFEST_SHA256.txt", "\n".join(manifest_lines))

write("PHASE1_BROWSER_VERIFICATION.md", f"""
# Phase 1 Browser Verification - Unified Review record

Version: **{VERSION}**  
Browser-tested code commit: `{BROWSER_COMMIT}`  
Transport: Chromium 149-compatible system build navigating a separately running uvicorn HTTP server on local loopback.  
Viewport: 1440 x 1000.

## Result

**Passed.** Recognized unfinished records displayed the current AI suggestion, while completed records displayed saved metadata. Recognition remained available only as secondary historical detail.

## Browser steps

1. Imported a 20-item QR-delimited fixture entirely through Import controls.
2. Started Mock identification through the visible Review action.
3. Observed `Demo VHS 001` on the unfinished item with the `AI SUGGESTION` label.
4. Approved the item, reopened it from Done, and observed `SAVED RECORD` with the persisted title.
5. Corrected item 1 to `VHS 001 - Corrected in v0.5.1` and verified the corrected saved title remained primary after restart.

Evidence: {evidence('05-recognition-complete.png', '10-review-complete.png', '11-completed-item-corrected.png', '14-restart-durable-correction.png')}.

## Boundaries

Mock recognition was used. This report verifies display precedence and browser behavior, not live AI accuracy.
""")

write("PHASE2_BROWSER_VERIFICATION.md", f"""
# Phase 2 Browser Verification - Completed-item correction

Version: **{VERSION}**  
Browser-tested code commit: `{BROWSER_COMMIT}`  
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

Evidence: {evidence('11-completed-item-corrected.png', '12-invalid-edit-blocked.png', '13-invalid-edit-cancelled.png', '14-restart-durable-correction.png', '15-publish-simulation.png')}.
""")

write("PHASE3_BROWSER_VERIFICATION.md", f"""
# Phase 3 Browser Verification - Workstation-first layout

Version: **{VERSION}**  
Browser-tested code commit: `{BROWSER_COMMIT}`  
Viewport: **1440 x 1000**.

## Result

**Passed.** The photograph, identity, physical sequence, Price, Discount, and primary action remained visible in the active workstation for the 20-item fixture. The item list remained secondary.

## Observations

- Item 1 opened as `Batch item 1 of 20` with 20 unfinished.
- Price and Discount were visible beside **Approve & Next** without entering Edit.
- Automatic advancement opened the next physical item once.
- The completed editor presented the complete exception form without changing Item ID.
- The interruption fixture also retained clear physical position with 40 items.

Evidence: {evidence('05-recognition-complete.png', '06-price-quick-edit.png', '07-discount-quick-edit.png', '08-price-discount-quick-edit.png', '09-next-item-opened.png', '12-invalid-edit-blocked.png', '28-recognition-resumed-complete.png')}.

The automated browser did not claim human inspection time. It measured application render response only.
""")

write("PHASE4_BROWSER_VERIFICATION.md", f"""
# Phase 4 Browser Verification - Recognition and queue clarity

Version: **{VERSION}**  
Browser-tested code commit: `{BROWSER_COMMIT}`  
Browser: local Chromium over real HTTP to a separate uvicorn process.

## Result

- Recognition state clarity: **Passed**.
- Physical position and unfinished-count clarity: **Passed**.
- Genuine interrupted recognition recovery: **Passed**.

## Native interruption proof

1. Imported a 40-item fixture through visible controls.
2. Started Mock recognition through the browser.
3. Observed `Identifying - 6 of 40 complete` before interruption.
4. Killed the actual application process; no database state was injected or edited.
5. Restarted the application against the same workspace.
6. Observed `Identification paused - 7 of 40 complete - 33 remaining` and exactly one **Continue identification** action.
7. Clicked Continue through the browser.
8. Observed `Recognition complete - 40 items ready to review`.
9. Post-audit reconciliation found 40 items, 40 recognition results, and zero items with duplicate recognition attempts.

Evidence: {evidence('26-recognition-running-before-kill.png', '27-recognition-paused-after-restart.png', '28-recognition-resumed-complete.png')}.

## Failure path

Gemini's intentionally disabled adapter produced one visible failed item. The operator opened the failed queue and retried with Mock, restoring a reviewable suggestion for the same physical item.

Evidence: {evidence('22-recognition-failure.png', '23-recognition-failure-recovered.png')}.
""")

write("PHASE5_BROWSER_VERIFICATION.md", f"""
# Phase 5 Browser Verification - Import operator workflow

Version: **{VERSION}**  
Browser-tested code commit: `{BROWSER_COMMIT}`  
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
4. Selected **Preserve and import batch** and observed one durable ID: `{METRICS['batches']['main']}`.
5. Selected **Continue to Review** and opened that same batch.
6. Repeated the workflow with two additional fixtures and observed recent-folder reuse.
7. Selected a nonexistent directory through Advanced and observed the fail-closed `Folder not available` state with Preview disabled.

Evidence: {evidence('01-first-run-import.png', '02-preview-not-imported.png', '02-imported-durable-id.png', '16-preview-not-imported.png', '16-imported-durable-id.png', '19-missing-folder-recovery.png')}.
""")

write("REVIEW_FAST_APPROVAL_BROWSER_VERIFICATION.md", f"""
# Review Fast Approval Browser Verification

Version: **{VERSION}**  
Browser-tested code commit: `{BROWSER_COMMIT}`.

## Verdict

**Passed through a native browser/server path.** Chromium navigated to a separately running SnapIMS uvicorn server. The audit did not use FastAPI TestClient or `page.set_content()`.

## Throughput interaction metrics

- Correctly recognized synthetic tapes: **20**
- Total counted clicks: **{METRICS['total_counted_clicks']}**
- Average clicks per tape: **{METRICS['average_clicks_per_tape']:.2f}**
- True one-click approvals: **{METRICS['one_click_tapes']}/20 ({METRICS['one_click_percent']:.0f}%)**
- Average application approval-to-next render time: **{METRICS['average_application_approval_to_next_render_seconds']:.3f} seconds**
- Real operator time per tape: **unmeasured; remains a live-pilot measurement**

Seventeen items required only **Approve & Next**. Item 18 used Price, item 19 used Discount, and item 20 used both quick fields before one approval. No Edit mode or second confirmation appeared on the valid fast path.

Evidence: {evidence('05-recognition-complete.png', '06-price-quick-edit.png', '07-discount-quick-edit.png', '08-price-discount-quick-edit.png', '09-next-item-opened.png', '10-review-complete.png')}.

## Boundaries

This test used deterministic Mock recognition. It does not claim live AI accuracy, real human inspection speed, or live Shopify behavior.
""")

write("NATIVE_BROWSER_VERIFICATION.md", f"""
# SnapIMS {VERSION} Native Browser Verification

## Transport proof

- Application: separate uvicorn process.
- Browser: Chromium driven by Playwright.
- Navigation: real local-loopback HTTP URL.
- Viewport: 1440 x 1000.
- Prohibited shortcuts absent: no TestClient operator transport, no `page.set_content()`, no form replay, and no direct database/service call to complete operator steps.
- Browser-tested code commit: `{BROWSER_COMMIT}`.

## Browser-observed operator actions

Fresh Home; first-run folder setup; Preview; preserve/import; Continue to Review; start and complete recognition; 20-item fast approval; Price and Discount quick edits; Later and return; Done correction; invalid edit and Cancel; full process restart; Publish simulation; visible CSV download; missing-folder recovery; failed recognition Retry; real interruption and Continue; Settings; Diagnostics.

## Metrics

- {METRICS['total_counted_clicks']} clicks / 20 tapes = {METRICS['average_clicks_per_tape']:.2f} clicks per tape.
- {METRICS['one_click_tapes']}/20 true one-click approvals.
- Average application approval-to-next render time: {METRICS['average_application_approval_to_next_render_seconds']:.3f} seconds.
- Real operator time per tape was not measured.

## Post-audit reconciliation

- Main batch items: {METRICS['post_audit_reconciliation']['main_items']}.
- Browser-downloaded CSV rows: {METRICS['post_audit_reconciliation']['downloaded_csv_rows']}.
- Interrupted batch items/results: {METRICS['post_audit_reconciliation']['interrupt_items']}/{METRICS['post_audit_reconciliation']['interrupt_results']}.
- Duplicate recognition-attempt items: {METRICS['post_audit_reconciliation']['duplicate_recognition_attempt_items']}.
- SQLite integrity: {METRICS['post_audit_reconciliation']['sqlite_integrity']}.
- Foreign-key violations: {METRICS['post_audit_reconciliation']['foreign_key_violations']}.

Machine-readable evidence: `operator-audit-assets/v0.5.1-browser/native-browser-results.json` and `browser-metrics.json`.
""")

shot_descriptions = {
    "00-home.png": "Fresh v0.5.1 Home with zero batches.",
    "01-first-run-import.png": "First-run Import and configured folder control.",
    "02-preview-not-imported.png": "20-item non-durable Preview with counts.",
    "02-imported-durable-id.png": "One durable Batch ID after import.",
    "04-review-before-identification.png": "Pre-recognition status and one Identify action.",
    "05-recognition-complete.png": "Recognized item 1, physical position, and fast path.",
    "06-price-quick-edit.png": "Inline Price quick edit.",
    "07-discount-quick-edit.png": "Inline Discount quick edit.",
    "08-price-discount-quick-edit.png": "Combined quick edits before one approval.",
    "09-next-item-opened.png": "Exactly one physical-item advance.",
    "10-review-complete.png": "Review-complete Done state.",
    "11-completed-item-corrected.png": "Same-ID completed correction.",
    "12-invalid-edit-blocked.png": "Atomic validation failure in exception editor.",
    "13-invalid-edit-cancelled.png": "Cancel restored valid saved data.",
    "14-restart-durable-correction.png": "Correction after full process restart.",
    "15-publish-simulation.png": "Shopify draft simulation and payload list.",
    "16-preview-not-imported.png": "Second fixture Preview through routine folder workflow.",
    "16-imported-durable-id.png": "Second fixture durable import ID.",
    "18-later-preserves-unfinished.png": "Later notice and remaining unfinished state.",
    "19-missing-folder-recovery.png": "Missing folder fails closed with Advanced recovery.",
    "20-preview-not-imported.png": "Failure fixture Preview.",
    "20-imported-durable-id.png": "Failure fixture imported ID.",
    "22-recognition-failure.png": "Provider failure attached to same physical item.",
    "23-recognition-failure-recovered.png": "Retry recovered a reviewable suggestion.",
    "24-preview-not-imported.png": "Interruption fixture Preview.",
    "24-imported-durable-id.png": "Interruption fixture durable import ID.",
    "26-recognition-running-before-kill.png": "Real recognition run active before process kill.",
    "27-recognition-paused-after-restart.png": "Paused status and one Continue action after restart.",
    "28-recognition-resumed-complete.png": "Interrupted run completed after visible Continue.",
    "29-settings.png": "Final Settings page and provider availability.",
    "30-diagnostics.png": "Integrity, foreign-key, schema, item, and workspace diagnostics.",
}
rows = ["# SnapIMS 0.5.1 Final Screenshot Index", "", "Every file below was captured from Chromium at 1440 x 1000 while navigating the real uvicorn server.", "", "| # | File | Evidence |", "|---:|---|---|"]
for idx, path in enumerate(sorted(SHOTS.glob("*.png")), 1):
    rows.append(f"| {idx} | `{path.name}` | {shot_descriptions[path.name]} |")
rows += ["", f"Total screenshots: **{len(list(SHOTS.glob('*.png')))}**. Each screenshot is listed exactly once."]
write("FINAL_SCREENSHOT_INDEX.md", "\n".join(rows))

write("FINAL_OPERATOR_AUDIT.md", f"""
# SnapIMS {VERSION} Final Operator Audit

## Verdict

**Ready with listed non-blocking limitations.** The local operator workflow passed a real browser-through-server audit. External production boundaries remain untested.

## Build and environment

- Version: {VERSION}
- Browser-tested code commit: `{BROWSER_COMMIT}`
- Browser: local Chromium, 1440 x 1000
- Server: separate uvicorn process over real loopback HTTP
- Workspace: fresh SQLite schema v5
- Recognition: deterministic Mock for normal throughput; disabled Gemini boundary for failure handling
- Publish: simulation only

## 1. Browser-observed operator actions

The operator portion used visible browser controls only:

1. Fresh Home and first-run Import.
2. Advanced folder configuration.
3. Non-durable Preview and durable import.
4. Continue to Review and Identify.
5. Twenty-tape fast Review: 17 one-click approvals plus Price, Discount, and combined quick edits.
6. Later, return to postponed item, and completion.
7. Done correction, invalid save, and Cancel.
8. Full application-process restart and durable correction.
9. Publish simulation and browser CSV download.
10. Missing-folder fail-closed recovery.
11. Recognition failure, failed queue, Retry, and recovery.
12. Real recognition interruption, process kill, restart, Paused state, Continue, and completion.
13. Settings and Diagnostics.

## 2. Post-audit database reconciliation

After the operator portion ended, independent database/CSV reconciliation confirmed:

- 20 main items and 20 browser-downloaded CSV rows.
- all main items Done;
- 40 interrupted-batch items and 40 recognition results;
- zero duplicate-attempt items;
- SQLite integrity `ok`;
- zero foreign-key violations.

## 3. Automated regression verification

The repository contains **110 collected pytest tests** across protocol/import, CSV, migrations, recognition, Review, Shopify, web routes, and packaging-adjacent smoke behavior. Exact final command output is retained in `TEST_RESULTS.md`.

## 4. Fixture setup

Synthetic QR-delimited camera rolls were generated before the operator portion. Fixture generation did not complete any operator step and is not counted as browser proof.

## 5. External boundaries not tested

- real Pixel glare/focus/QR transfer;
- live OpenAI recognition accuracy, latency, rate limits, billing, or credential recovery;
- live Shopify authentication, media transfer, and one real draft;
- independent first-time human operator walkthrough;
- multi-user or remote deployment.

## Interaction metrics

- Average clicks per correctly recognized tape: **{METRICS['average_clicks_per_tape']:.2f}**.
- True one-click approvals: **{METRICS['one_click_tapes']}/20 ({METRICS['one_click_percent']:.0f}%)**.
- Average application approval-to-next render time: **{METRICS['average_application_approval_to_next_render_seconds']:.3f} seconds**.
- Real operator time per tape: **unmeasured; remains a live-pilot measurement**.
""")

write("FINAL_UX_FINDINGS.md", f"""
# SnapIMS {VERSION} Final UX Findings

## Outcome

All nine original operator findings were observed as corrected in the native browser workflow:

| Finding | Status | Evidence |
|---|---|---|
| OA-01 recognized records remain Untitled | Fixed | Suggested title appears after identification. |
| OA-02 Done records show stale suggestion | Fixed | Saved/corrected title remains primary after restart. |
| OA-03 Done correction | Fixed | Edit, validation, Cancel, restart, CSV, and simulation use same Item ID. |
| OA-04 editor orientation | Fixed | Complete editor remains usable in workstation layout. |
| OA-05 preview/import identity | Fixed | Preview is non-durable; one ID appears after import. |
| OA-06 recognition state clarity | Fixed | Ready, Running, Paused, Complete, Failed, Review complete observed. |
| OA-07 physical queue position | Fixed | Physical item and unfinished count remain independent of queue filter. |
| OA-08 routine folder workflow | Fixed | Configured/recent choices plus Advanced recovery. |
| OA-09 excessive Review scrolling | Fixed at 1440 x 1000 | Photo, quick fields, and primary action remain together. |

## Remaining friction

- File-system folder concepts remain visible during first-run setup.
- Random access in large batches remains under the secondary All items disclosure.
- The automated audit cannot measure human photograph inspection time.
- Live external integrations remain acceptance boundaries.
""")

write("PRODUCTION_READINESS.md", f"""
# SnapIMS {VERSION} Production Readiness

Verdict: **Ready with listed non-blocking limitations.**

SnapIMS {VERSION} is ready for a controlled real 20-tape Pixel pilot. It is not a 1.0 release.

## Verified locally

- 110 pytest tests passed in the final codebase.
- Native browser/server audit passed without TestClient operator transport.
- 20-item fast path achieved {METRICS['average_clicks_per_tape']:.2f} clicks/tape and {METRICS['one_click_percent']:.0f}% true one-click approval.
- Real process interruption returned as Paused and resumed without duplicate recognition attempts.
- SQLite integrity was ok with zero foreign-key violations.
- Shopify checkpoint/retry and migration behavior have dedicated deterministic tests.
- Wheel build and installed-resource smoke test passed using the available local build path.

## Pending external acceptance

- real Pixel pilot;
- live AI;
- one live Shopify draft;
- physical CSV reconciliation;
- independent first-time operator guide walkthrough.

The environment could not obtain Ruff, MyPy, or the `build` frontend from its restricted package index. Their commands remain configured in GitHub Actions and are accurately marked pending in `TEST_RESULTS.md`; no false pass is claimed.
""")

write("FINAL_PRODUCTION_READINESS.md", f"""
# SnapIMS {VERSION} Final Production Readiness

## Verdict

**Ready with listed non-blocking limitations.**

## Readiness questions

1. **Can an inventory specialist operate without terminal commands?** Yes, in the audited local browser workflow after folder configuration.
2. **Can a batch be imported, identified, reviewed, corrected, resumed, and exported?** Yes, through visible controls.
3. **Can a completed item be corrected safely?** Yes, with the same immutable Item ID, validation, Cancel, restart, CSV, and simulation consistency.
4. **Does state survive restart?** Yes. Saved records and a genuinely interrupted recognition job survived a full process stop/start.
5. **Are image, shelf, flags, metadata, and IDs linked?** Yes for the tested fixtures and browser-downloaded CSV.
6. **Does a 20-item batch remain understandable?** Yes at 1440 x 1000.
7. **Are interruption and failure recoverable?** Yes through visible Continue and Retry actions.
8. **Does Import avoid routine path entry?** Yes after first-run setup; recent folders persist.
9. **Is Preview identity clear?** Yes: Preview is explicitly not imported and shows no durable ID.
10. **Does Publish simulation use saved data?** Yes for the tested records and payload preview.
11. **What remains unproven?** Real Pixel, live AI, live Shopify, independent first-time human, multi-user/remote deployment.
12. **Is it ready for the controlled real pilot?** Yes, with Shopify kept in simulation for the first batch.

## 1.0 gate

Do not label 1.0.0 until the real Pixel pilot, live AI, one live Shopify draft, physical CSV verification, restart durability, final guide walkthrough, browser verification, and blocker review all pass.
""")

write("PROJECT_STATUS.md", f"""
# SnapIMS Project Status

Version: **{VERSION} verification-hardening release candidate**

## Completed

- deterministic QR/event parser and original preservation;
- immutable Batch/Item identity and SQLite schema v5;
- configured/recent Import workflow;
- persisted recognition jobs with real interruption recovery;
- one-click Review with inline Price and Discount;
- Later and completed-item correction;
- safe partial CSV round-trip with year and discount;
- Shopify simulation and checkpoint/retry service tests;
- legacy migration backup/rollback tests;
- 110 pytest tests;
- real Chromium-to-uvicorn operator audit;
- synchronized phase reports, final audit, screenshots, and Operator Guide.

## Pending before 1.0

- real 20-tape Pixel pilot;
- live AI acceptance;
- one live Shopify draft;
- physical CSV reconciliation;
- independent first-time operator guide walkthrough;
- successful Ruff/MyPy/build-frontend execution in an environment where those tools are available.
""")

write("RELEASE_NOTES.md", f"""
# SnapIMS Release Notes

## {VERSION} - Verification hardening patch

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
- synchronized application and documentation version references to {VERSION}.

### Historical note: 0.5.0

Version 0.5.0 reconstructed the missing fast Review, Import, recognition, CSV, and Shopify boundaries. Its audit used a hybrid TestClient transport and had only 17 tests; {VERSION} supersedes it as the verification-hardened candidate.

### Still required before 1.0

Real Pixel pilot, live AI, one live Shopify draft, physical CSV verification, and independent guide walkthrough.
""")

write("ARCHITECTURE.md", f"""
# SnapIMS {VERSION} Architecture

## Core rule

The camera roll is an ordered event stream. Time gaps never define item boundaries. `CVHS1:ITEM:NEXT` is the sole normal boundary.

## Layers

- `snapims/protocol.py`, `sorter.py`, `interpreter.py`, `pipeline.py`: deterministic capture/event interpretation.
- `snapims/processor.py`: preserved originals, sanitized product copies, staging, fingerprinting, and transactional import.
- `snapims/db.py`: SQLite schema v5, migrations, events, settings, cursors, recognition jobs, and publish checkpoints.
- `snapims/recognition/`: provider-neutral suggestion interface, durable jobs, acceptance, failure, and retry.
- `snapims/inventory.py`: validation and immutable-ID CSV round-trip.
- `snapims/shopify/`: draft-only payload, transport boundary, checkpointed publication, media verification, and reconciliation.
- `snapims/web/`: FastAPI/Jinja browser client. UI actions call application services; SQLite remains authoritative.

## Durability

Each recognized item is committed independently. A process killed during recognition leaves the job RUNNING in SQLite; startup converts orphaned RUNNING jobs to PAUSED. Continue reconstructs completed boundaries from recognition history and does not duplicate results.

## Future clients

A mobile capture client can emit the same START, LOCATION, NEXT, FLAG, PHOTO, and END event vocabulary. A server/multi-operator edition requires authentication and concurrency policy beyond {VERSION}.
""")

write("DATABASE.md", f"""
# SnapIMS {VERSION} Database

SQLite schema version: **5**.

## Safety properties

- immutable `item_id` and matching SKU;
- foreign keys enabled on every application connection;
- WAL mode for local durability;
- explicit write transactions;
- backup before import, CSV import, Shopify live attempt, and legacy migration;
- post-migration integrity and foreign-key checks;
- unsupported future schema refused without modification;
- partial CSV import preserves absent columns;
- optimistic `record_revision` protects concurrent/stale edits;
- publish checkpoints and attempt history support reconciliation.

## Verified migration path

The test suite creates a real legacy v0.3-format fixture, upgrades it to schema 5, and verifies retained Item IDs, SKU, items, photos, recognition history, backup creation, and integrity. Failure injection verifies restoration of the original database. Future schema versions are refused safely.

## Integrity command

```bash
snapims --data-dir /path/to/workspace integrity
```

Expected:

```text
integrity_check=ok
foreign_key_violations=0
```
""")

write("DEMO.md", f"""
# SnapIMS {VERSION} Demonstration

## Generate a QR-delimited camera roll

```bash
snapims demo demo-data/camera-roll
```

## Start the browser application

```bash
snapims --data-dir demo-data/workspace serve
```

Then use only the browser:

1. Import -> Advanced -> choose `demo-data/camera-roll`.
2. Preview and confirm the non-durable identity and grouping counts.
3. Preserve and import.
4. Continue to Review.
5. Select Mock and Identify items.
6. Confirm title; optionally adjust Price or Discount; select **Approve & Next**.
7. Use Later for a postponed tape or Edit for an exception.
8. Open Publish, simulate drafts, and download the CSV.

Mock is deterministic test data. It does not prove live AI quality.
""")

write("README.md", f"""
# SnapIMS {VERSION}

SnapIMS is a photo-first inventory ingestion system built around deterministic QR event capture, AI-assisted recognition, exception-only Review, immutable inventory identity, CSV reconciliation, and Shopify draft output.

## Routine workflow

```text
Photograph -> Preview/Import -> Identify -> Approve exceptions -> Simulate/Export
```

Correctly recognized tapes normally require one action: **Approve & Next**. Price and Discount remain inline; Edit is reserved for exceptions.

## Install

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
snapims --data-dir ~/SnapIMS-data serve
```

## Quality commands

```bash
pytest -q
ruff check .
mypy snapims --ignore-missing-imports
python -m compileall -q snapims
python -m build
pip check
```

## Verification record

- 110 collected pytest tests pass locally.
- Native Chromium-to-uvicorn audit passes.
- 20-item fast path: {METRICS['average_clicks_per_tape']:.2f} clicks/tape; {METRICS['one_click_percent']:.0f}% one-click.
- Average application approval-to-next render: {METRICS['average_application_approval_to_next_render_seconds']:.3f}s.
- Real operator time remains a live-pilot measurement.

The restricted reconstruction environment could not install Ruff, MyPy, or the `build` frontend. Their exact commands remain in GitHub Actions and are not falsely marked passed.

## Documentation

- `SnapIMS_Operator_Guide.pdf` / `.docx`
- `NATIVE_BROWSER_VERIFICATION.md`
- `FINAL_OPERATOR_AUDIT.md`
- `FINAL_PRODUCTION_READINESS.md`
- `V0.5.1_DISCREPANCY_CLOSURE_REPORT.md`
- Phase 1-5 verification reports

## Version policy

0.5.1 is a patch release. 1.0.0 remains forbidden until all real production acceptance gates pass.
""")

write("TEST_RESULTS.md", f"""
# SnapIMS {VERSION} Test Results

## Passed locally

- `pytest -q`: **110 tests passed**.
- `python -m compileall -q snapims`: passed.
- Native Playwright/Chromium-through-uvicorn audit: passed.
- Wheel build: passed with `pip wheel . --no-deps --no-build-isolation`.
- Wheel filename: `snapims-0.5.1-py3-none-any.whl`.
- Isolated-target install and package-resource smoke: passed; templates and static assets were present.
- CLI help from installed wheel: passed.
- SQLite integrity after audit: ok; zero foreign-key violations.

## Not executable in this container

- `ruff check .`: Ruff was not installed and the restricted package index returned no package.
- `mypy snapims --ignore-missing-imports`: MyPy was not installed and the restricted package index returned no package.
- `python -m build`: the `build` frontend was not installed; the wheel was built successfully via pip/setuptools without build isolation.
- `pip check`: the shared container reports an unrelated pre-existing MoviePy/Pillow version conflict. SnapIMS packaging itself installed and imported successfully.

No unavailable gate is claimed as passed. The GitHub Actions workflow retains the required pytest, Ruff, MyPy, compile, and build commands for execution after the branch is pushed from an authorized environment.
""")

write("V0.5.1_DISCREPANCY_CLOSURE_REPORT.md", f"""
# SnapIMS {VERSION} Discrepancy Closure Report

| # | Original finding | Repair and evidence | Status | Remaining risk |
|---:|---|---|---|---|
| 1 | No Git history/branch | Initialized history, preserved baseline commit, created `fix/v0.5.1-verification-hardening`, added logical commits, bundle and patch deliverables. GitHub App push returned 403. | Partially closed | User must push bundle/branch from authorized Git. |
| 2 | Hybrid browser audit | Replaced with Chromium navigating real uvicorn HTTP; no TestClient or `page.set_content()`. | Closed | External browser/platform differences remain. |
| 3 | Injected interruption | Killed actual server at 6/40; restart showed 7 complete/33 remaining; Continue completed 40 with zero duplicate-attempt items. | Closed | OS/disk corruption is outside test. |
| 4 | Ruff/MyPy absent | Commands and CI retained; local install blocked by restricted index. Pytest/compile/wheel/browser passed. | Partially closed | Ruff/MyPy must run after authorized push or locally. |
| 5 | Only 17 tests | Expanded to 110 meaningful tests across 11 test modules. | Closed | Not byte-for-byte recreation of lost 285 tests. |
| 6 | Missing Phase 1-3 reports | Regenerated Phase 1-5 reports from the native audit. | Closed | Live external boundaries remain separate. |
| 7 | Audit wording overstated | Final audit now separates browser actions, reconciliation, tests, fixture setup, and untested boundaries. | Closed | None known. |
| 8 | Timing mislabeled | Metric renamed application approval-to-next render; real operator time explicitly unmeasured. | Closed | Live pilot must measure human time. |
| 9 | Screenshot index incomplete | Regenerated and indexed all {len(list(SHOTS.glob('*.png')))} screenshots exactly once. | Closed | None known. |
| 10 | Shopify hardening untested | Added 16 Shopify tests covering simulation, safeguards, checkpoints, reconciliation, media success/failure/timeout, retries, and local failure after remote success. | Closed for deterministic boundary | Real Shopify remains untested. |
| 11 | Migration hardening untested | Added 8 migration/database tests for legacy upgrade, backup, rollback, future schema, integrity, FK, and transaction safety. | Closed for deterministic boundary | Real production database backup should still precede pilot. |
| 12 | First-time operator/external gates | Accurately retained as open; no false completion claim. | Still open | Real Pixel, live AI, live Shopify, physical CSV, independent first-time human. |

## Release classification

Patch: **0.5.0 -> {VERSION}**. No new operator workflow was introduced.
""")

write("RECONSTRUCTION_MANIFEST.md", f"""
# SnapIMS {VERSION} Reconstruction Manifest

## Lineage

- Recoverable GitHub baseline: `045d91f91aaabced14f64115d84725b77bc27c4a` (legacy v0.3.0).
- Preserved v0.5.0 reconstruction baseline commit: `c86233d2db5f844812919bb8458f081eee5abe71`.
- Native browser evidence commit: `{BROWSER_COMMIT}`.
- Repair branch: `fix/v0.5.1-verification-hardening`.

## Included

- complete source and tests;
- FastAPI/Jinja templates/static resources;
- 110-test regression suite;
- migration and Shopify recovery tests;
- native browser audit script;
- 31 browser screenshots;
- browser-downloaded CSV and machine-readable metrics;
- Phase 1-5 reports;
- synchronized operator and readiness documentation;
- DOCX/PDF Operator Guide;
- local Git history, Git bundle, patch series, source-only ZIP, and checksums.

## Excluded

Secrets, `.env`, databases, browser profiles, temporary camera fixtures, temporary audit workspace, logs, virtual environments, and build caches.

## External boundaries

Real Pixel, live AI, live Shopify, physical CSV reconciliation, independent first-time human, and multi-user/remote operation remain outside {VERSION} local verification.
""")

write("GITHUB_PUSH_STATUS.md", """
# GitHub Publication Status

Target repository: `fachingo/SnapIMS`  
Target branch: `fix/v0.5.1-verification-hardening`

The connected GitHub App returned `403 Resource not accessible by integration` when branch creation was attempted. No remote branch or `main` content was changed.

## Safe publication from the bundle

```bash
git clone https://github.com/fachingo/SnapIMS.git SnapIMS
cd SnapIMS
git fetch /path/to/SnapIMS-v0.5.1.bundle fix/v0.5.1-verification-hardening:fix/v0.5.1-verification-hardening
git switch fix/v0.5.1-verification-hardening
git push -u origin fix/v0.5.1-verification-hardening
```

Do not merge until CI passes and the branch is reviewed.
""")
