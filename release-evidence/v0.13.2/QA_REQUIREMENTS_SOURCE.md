# SnapIMS v0.13.1 Full Remediation, Stress-Test, and Release Prompt

You are the senior developer, QA engineer, performance engineer, database reliability engineer, browser automation engineer, installer engineer, documentation owner, and release manager for SnapIMS.

You are not being asked for advice, a plan, a patch snippet, or a bug summary.

You must work directly on the supplied complete SnapIMS v0.13.0 source inside your own local sandbox, implement every required correction, repeatedly run and repair the software until it passes, and return a complete tested SnapIMS v0.13.1 full-source release ZIP.

## Files supplied with this task

Treat these files as required inputs:

1. `SnapIMS-v0.13.0-full-source.zip`
2. `SnapIMS_v0.13.0_Stress_QA_Bug_Report_2026-08-03.md`
3. `SnapIMS_v0.13.0_Stress_QA_Issue_Register_2026-08-03.csv`, when supplied
4. `SnapIMS_v0.13.0_Stress_QA_Evidence_2026-08-03.zip`, when supplied
5. Any owner-machine logs supplied with the task

The attached stress QA report is authoritative. Read it in full before modifying code. Use the issue register and evidence archive to reproduce the findings rather than relying only on issue titles.

## Required output

Return one complete release archive:

```text
SnapIMS-v0.13.1-full-source.zip
```

It must contain the entire working source tree, not only changed files, a diff, or a partial patch.

Also include inside the release:

- `install_v0131.sh`
- built wheel
- forward-only database migrations
- complete tests and deterministic fixtures
- browser test scripts
- browser evidence
- performance evidence
- exact test logs
- issue traceability matrix
- updated editable documentation
- updated PDF documentation
- release notes
- production-readiness report
- per-file SHA-256 manifest
- archive SHA-256 checksum

Do not ask the operator to finish implementation, testing, documentation, or packaging.

---

# 1. VERSION AND RELEASE POLICY

This work is a patch release:

```text
0.13.0 -> 0.13.1
```

The QA findings are defects in the existing v0.13.0 workflow. Do not label the release v0.14.0 or v1.0.0.

Update every active version marker to `0.13.1`, including:

- Python package metadata
- application constants
- CLI version output
- Home-page version display
- installers
- service files
- launchers
- README
- current operator guides
- browser report
- performance report
- production-readiness report
- release notes
- manifests
- checksums
- package filenames

Historical changelog entries may retain historical version numbers. No current document may present v0.13.0 as the active release.

---

# 2. SOURCE PRECEDENCE AND TRUTHFULNESS

Use this precedence when information conflicts:

1. Actual extracted source and reproducible runtime behavior
2. QA evidence archive and raw logs
3. Stress QA bug report
4. CSV issue register
5. Existing documentation

Do not invent test results.

Do not claim testing on:

- the 2012 Mac mini
- native Firefox
- live AI
- live Shopify
- owner production data

unless those tests actually occurred.

Clearly distinguish:

- sandbox measurements
- supplied owner-machine evidence
- unavailable external or hardware tests

---

# 3. AUTHORITATIVE BASELINE FROM THE ATTACHED REPORT

The supplied report states:

- release tested: SnapIMS v0.13.0
- source archive SHA-256:
  `3db75f2da21ac40954b3a395aceb3b160d1885faab2beb34f3c5d4451a485541`
- verdict: FAIL
- tests collected: 266
- full one-process result:
  - 259 passed
  - 3 skipped
  - 2 failed
  - 2 setup errors
- principal failure:
  - `OSError: [Errno 24] Too many open files`
  - subsequent SQLite open failures
- monitored descriptor count:
  - 331 open descriptors by 54% completion
- 100-item/202-photo Preview request:
  - 0.166 seconds
- 100-item grouping:
  - exactly 100 items
- 100-item commit:
  - 3.215 seconds
- 5,000-item Batch Editor:
  - 22,664,709-byte response
  - 11.593-second DOMContentLoaded
- native Firefox:
  - not available in the original pass
- target 2012 Mac mini:
  - not tested in the original pass

Reproduce these findings where practical before fixing them. Record your own environment and measurements.

---

# 4. REQUIRED DEFECT REMEDIATION

Resolve every issue from `QA-0130-001` through `QA-0130-010`.

Do not mark an issue fixed because one narrow unit test passes. For every issue:

1. reproduce it;
2. identify its root cause;
3. implement a durable correction;
4. add regression coverage;
5. verify it in the actual running application;
6. record evidence;
7. include it in the traceability matrix.

## QA-0130-001 — Critical — SQLite and file-descriptor leak

### Reported behavior

The complete 266-test collection exhausts file descriptors. SQLite database and WAL handles from completed test workspaces remain open. The report found 26 `with db.connect(...) as connection:` call sites and noted that SQLite transaction context management does not guarantee explicit close.

### Required implementation

- Audit every database connection owner.
- Introduce one explicit connection context helper that always closes in `finally`.
- Convert all direct `db.connect(...)` usage to guaranteed closure.
- Audit:
  - operational routes
  - background jobs
  - Import jobs
  - migrations
  - tests
  - exception paths
  - iterators
  - image handles
  - temporary files
  - log handles
  - browser resources
  - executors
- Do not rely on garbage collection.
- Do not increase `ulimit` as the fix.
- Do not hide the leak by splitting the suite into multiple processes.

### Acceptance

- Run the complete 266-test collection in one clean Python process.
- No `Errno 24`.
- No SQLite-open failures.
- No temporary-directory creation failures.
- Add a repeated-workflow resource regression test.
- Record descriptor baseline, peak, and final counts.
- Descriptor count must return near baseline after completed cycles and must not grow linearly.

## QA-0130-002 — High — Duplicate same-folder Import race

### Reported behavior

Two tabs can create independent Preview jobs for the same canonical folder. Both reach READY. Concurrent Commit requests share a staging identity and one fails with a `FileNotFoundError` during rename.

### Required implementation

- Define a stable canonical folder identity.
- Enforce one active Preview/Commit job per canonical folder identity.
- Use a database-backed uniqueness or locking mechanism.
- Duplicate Preview must return or redirect to the existing job.
- Commit must be idempotent.
- Duplicate Commit must return the existing success result or a clear non-destructive conflict.
- Use unique per-job staging directories even after the idempotency guard.
- Protect against:
  - double-clicks
  - two tabs
  - stale tabs
  - refreshes
  - restart recovery
- Never create two imported batches from the same active folder race.
- Never corrupt or delete a valid successful import.

### Acceptance

- Two simultaneous browser Preview requests produce one effective job.
- Two simultaneous Commit requests cannot create duplicate batches or staging collisions.
- Restart during Preview remains recoverable.
- Restart after Preview but before Commit remains recoverable.
- Add database, HTTP, and browser concurrency tests.

## QA-0130-003 — High — Upgrade launcher starts obsolete code

### Reported behavior

The owner machine reported CLI version 0.13.0 while `snapims up` launched `/home/isaiah/Projects/SnapIMS`, whose log said `SnapIMS 0.12.3 starting`. The old code then refused schema 14.

### Required implementation

- Audit:
  - shell launchers
  - console scripts
  - PATH resolution
  - symlinks
  - system services
  - user services
  - service working directories
  - environment files
  - stored project paths
- The v0.13.1 installer must detect stale service and launcher definitions.
- Rewrite them to the installed v0.13.1 executable and source path.
- `snapims up` and `snapims status` must print:
  - resolved executable
  - source/project path
  - data directory
  - PID
  - application version
  - database schema version
- Refuse mixed code/schema startup with a clear diagnostic before serving requests.
- Do not report installation success until:
  - CLI version is 0.13.1
  - running process version is 0.13.1
  - Home shows 0.13.1
  - `/health` succeeds
  - authenticated or redirected Home behavior is correct
  - restart launches the same path again

### Acceptance

- Clean installation passes.
- Upgrade from a realistic v0.12.3 layout passes.
- Upgrade test includes a stale service pointing to an old source tree.
- Database, settings, credentials, logs, environment configuration, and images remain intact.
- The application cannot silently launch `~/Projects/SnapIMS` when another release is current.

## QA-0130-004 — High — Batch Editor renders all rows

### Reported behavior

The Batch Editor calls an unbounded item query and renders the full collection in HTML plus another full JSON copy. At 5,000 items the response is approximately 22.66 MB and Chromium requires 11.593 seconds to build the DOM.

### Required implementation

- Add bounded server-side pagination, incremental loading, or a proven virtualized-row implementation.
- Do not render all 1,000 or 5,000 rows.
- Do not embed a second full copy of the entire batch in page JSON.
- Preserve:
  - search
  - sort
  - filters
  - selection
  - Fill Down
  - bulk actions
  - undo/conflict behavior
  - stale-revision protection
  - keyboard navigation
  - refresh behavior
- Avoid full-table queries for counts.
- Add indexes and bounded queries where required.
- Keep the design usable on an older 8 GB machine.

### Acceptance

- Add real 1,000-item and 5,000-item browser tests.
- Normal editor navigation responds within one second in the test environment when idle.
- Initial response size is bounded and does not scale to tens of megabytes.
- Record:
  - HTML/JSON bytes
  - server response time
  - DOMContentLoaded
  - time to interactive
- Verify search, filters, selection, Fill Down, and bulk actions across page boundaries.

## QA-0130-005 — Medium — Fill Down does not support Tags

### Required implementation

- Support Fill Down for `tag_ids`.
- Copy the exact validated tag set from the source row to destination rows.
- This must be set/replace semantics, not append.
- Preserve controlled-tag validation and immutable approved Tag IDs.
- Support:
  - empty source tag set
  - one tag
  - multiple tags
  - destinations with existing tags
  - retired tags already attached to the source without allowing invalid new assignments
- Apply atomically.
- Add audit history.
- A failure must not partially update destinations.

### Acceptance

- Unit, integration, and browser tests prove exact source-to-destination equality.
- Existing Bulk Append Tags continues to work independently.

## QA-0130-006 — Medium — Location Fill Down maps stale `shelf`

### Required implementation

- Replace the stale `shelf` mapping with the real `location` field.
- Copy the exact source location.
- Blank and case-insensitive `None` become nullable unassigned.
- Never store the literal word `None`.
- Preserve arbitrary values such as `Processing Table`.
- Record each affected Item in:
  - location history
  - audit history
- Apply atomically.

### Acceptance

Test:

- standard location
- blank
- `None`
- arbitrary free text
- unchanged source folder names
- unchanged immutable IDs

## QA-0130-007 — Medium — Fill Down does not support Review or Rare

### Required implementation

- Support Fill Down for Review and Rare booleans.
- Copy the exact source state.
- Support both:
  - checked to unchecked
  - unchecked to checked
- Use one atomic audited bulk update.
- Preserve revision/conflict safety.

### Acceptance

Add browser and database tests for both directions on both fields.

## QA-0130-008 — Medium — Horizontal navigation cannot cross Tags

### Required implementation

- Fix ArrowLeft and ArrowRight navigation into and out of the Tags editor.
- Use the proper tag-input focus path instead of focusing a non-focusable wrapper.
- Preserve:
  - vertical navigation
  - text caret behavior
  - keyboard-only workflow

### Acceptance

- Keyboard traversal crosses every editable column in both directions.
- Verify in Chromium.
- Verify in Firefox if available.
- If Firefox is unavailable, state that honestly.

## QA-0130-009 — Medium — Hidden selected rows remain armed

Use the safer resolution:

- When search or filters change, automatically clear selections for rows no longer visible in the result set.
- Immediately update the selected-row count.
- Bulk actions must never silently target hidden rows.
- Sorting and paging must preserve or clear selection according to one explicitly documented model.
- Selection scope must be clear in the UI.

### Acceptance

- Select rows.
- Hide them using search/filter.
- Confirm hidden selections are cleared.
- Confirm selected count updates.
- Confirm bulk operations affect only explicitly visible selected rows.
- Add browser regression coverage.

## QA-0130-010 — Low — Shelf-only terminology remains

### Required implementation

Replace current operator-facing shelf-only wording with accurate location/unassigned terminology.

Search:

- templates
- JavaScript
- help text
- current guides
- screenshots
- checklists
- recovery documents
- browser reports
- readiness reports

Do not rewrite valid historical changelog text.

### Acceptance

- No active UI or current operator guide implies an A1-style shelf is mandatory.
- Arbitrary free-text locations and unassigned state are described correctly.

---

# 5. PRESERVE THE PASSED V0.13.0 BEHAVIOR

The report identifies these positive findings. They must remain passing:

- Import Preview returns control well under one second in the tested environment.
- Progress survives browser refresh.
- The 100-item/202-photo dataset groups exactly 100 items.
- Cold scan performs one image decode and one QR scan per source image.
- Preview displays 20 items per page.
- Bulk Append Tags works.
- Bulk Location accepts `None` as unassigned.
- Rapid consecutive edits preserve the latest value.
- Stale two-tab edits return HTTP 409 and preserve accepted data.
- The 390-pixel mobile layout remains within the viewport.
- The editor remains horizontally scrollable.
- Normal workflows produce no unhandled JavaScript page errors.

Add regression tests where needed.

Do not redesign Recognition, Review, Publish, Shopify, authentication, or global navigation unless a verified defect requires a narrow supporting change.

---

# 6. REQUIRED LOCAL WORKFLOW

## Phase A — Extract and baseline

1. Verify the supplied source ZIP checksum.
2. Extract into a clean working directory.
3. Confirm it is genuinely v0.13.0.
4. Read the complete QA report.
5. Read the issue register.
6. Inspect the evidence archive.
7. Build a traceability matrix with:
   - issue ID
   - reproduction
   - root cause
   - files changed
   - tests added
   - browser verification
   - final status
8. Create a clean virtual environment.
9. Install supported dependencies.
10. Run:
    - complete existing suite in one process
    - compile checks
    - JavaScript syntax checks
    - installer shell checks
    - actual server
    - browser smoke test
11. Record baseline failures and performance.
12. Reproduce all ten issues.

## Phase B — Implement

- Fix root causes, not symptoms.
- Keep changes scoped to the reported defects and required supporting reliability work.
- Use forward-only migrations.
- Never delete operator data.
- Never alter source photographs.
- Never weaken:
  - authentication
  - auditing
  - image preservation
  - conflict protection
  - database correctness
- Do not weaken assertions.
- Do not convert real failures into skips merely to pass.

## Phase C — Test and repair loop

After each logical change:

1. focused unit tests
2. focused integration tests
3. affected browser workflow
4. logs
5. console errors
6. page errors
7. failed requests
8. HTTP 4xx/5xx review
9. repair root cause

After all changes:

1. complete suite in one clean process
2. migrations
3. installer
4. restart durability
5. concurrency
6. descriptor/resource stability
7. 1,000-item Batch Editor
8. 5,000-item Batch Editor
9. desktop browser walkthrough
10. 390-pixel mobile walkthrough
11. Firefox when available
12. clean extracted package
13. realistic v0.12.3 upgrade with stale launcher/service
14. full suite again after documentation and packaging

Do not package until all required local checks pass.

---

# 7. PERFORMANCE AND RESOURCE REPORTING

Record actual measured results.

At minimum include:

- operating system
- CPU information
- available memory
- Python version
- browser versions
- startup time
- Home load
- Import load
- 20-item Preview
- 100-item/202-photo Preview
- 100-item Commit
- warm Preview
- 1,000-item editor
- 5,000-item editor
- response bytes
- DOMContentLoaded
- time to interactive
- idle CPU
- idle memory
- peak Import memory
- descriptor baseline
- descriptor peak
- descriptor final
- descriptor counts over repeated workflow cycles
- database query count where practical

Provide baseline-versus-final tables.

Do not fabricate unavailable hardware results.

---

# 8. MIGRATION AND DATA SAFETY

- Use forward-only migrations.
- Preserve all existing v0.12.3 and v0.13.0 operator data.
- Preserve:
  - Batch IDs
  - Item IDs
  - source paths
  - images
  - review work
  - recognition attempts
  - prices
  - tags
  - locations
  - location history
  - Shopify links
  - settings
  - credentials
  - logs
- Back up the database before migration.
- Test migration failure recovery.
- Never solve upgrade problems by deleting or recreating the production database.

---

# 9. DOCUMENTATION SYNCHRONIZATION

Update all affected current documentation to v0.13.1:

- README
- release notes
- Operator Guide
- Day-to-Day Guide
- Complete Operating Manual
- Browser Verification Report
- Performance Report
- Production Readiness Report
- Recovery Procedures
- End-of-Batch Checklist
- installer documentation
- service and launcher documentation

Update screenshots that changed.

Render and visually inspect every final PDF page.

Follow the final guide step-by-step against the final browser UI. Fix every discrepancy.

Search for stale active references to:

- v0.13.0
- `install_v0130.sh`
- obsolete source paths
- unsupported Fill Down limitations
- shelf-only wording
- full-table editor behavior

Historical changelog entries may remain historical.

---

# 10. FINAL RELEASE CONTENTS

Produce:

```text
SnapIMS-v0.13.1-full-source.zip
```

The archive must include:

- complete application source
- templates
- static assets
- `install_v0131.sh`
- built wheel
- database migrations
- complete tests
- deterministic fixtures
- concurrency tests
- resource-leak tests
- 1,000-item and 5,000-item tests
- editable documentation
- PDF documentation
- browser screenshots
- browser logs
- performance evidence
- traceability matrix
- exact test logs
- release notes
- production-readiness report
- per-file checksum manifest
- archive checksum

Test the final ZIP by:

1. extracting into a new empty directory;
2. creating a clean virtual environment;
3. performing a clean installation;
4. launching the application;
5. checking CLI version;
6. checking running-process version;
7. checking Home version;
8. checking schema version;
9. running the required tests;
10. restarting;
11. performing a v0.12.3 upgrade test;
12. confirming data preservation;
13. confirming stale service/launcher paths were corrected.

---

# 11. HARD RELEASE GATE

Do not return v0.13.1 unless:

- QA-0130-001 through QA-0130-010 are fixed;
- all 266 tests pass in one clean process, except only legitimate documented environment skips;
- descriptor counts remain stable;
- duplicate Preview and Commit are idempotent;
- clean installation passes;
- v0.12.3 upgrade with stale service path passes;
- CLI, running process, Home, and schema agree;
- 5,000-item editor no longer full-renders the collection;
- Fill Down works for Tags, Location, Review, and Rare;
- keyboard navigation crosses Tags;
- hidden selections cannot be bulk-edited;
- active wording uses location/unassigned terminology;
- desktop and mobile browser walkthroughs pass;
- restart durability passes;
- final ZIP extracts, installs, launches, and passes verification;
- current documentation matches the final UI.

If a nonessential external capability is unavailable, document it honestly. Do not claim an unperformed test passed.

---

# 12. FINAL RESPONSE FORMAT

Return:

1. release verdict
2. direct download link to `SnapIMS-v0.13.1-full-source.zip`
3. SHA-256
4. exact clean-install commands
5. exact upgrade commands
6. exact test totals
7. issue status table for QA-0130-001 through QA-0130-010
8. baseline-versus-final performance table
9. descriptor baseline/peak/final table
10. browser verification results
11. clean-install results
12. upgrade results
13. honest remaining limitations

Do not end with a plan.

Do not return only a report.

Do not return only a diff.

Do not return only changed files.

Implement, test, repair, browser-verify, document, package, and return the complete v0.13.1 full-source release.

---

# ATTACHED QA REPORT — AUTHORITATIVE CONTENT

The following report content was supplied with this task and must be treated as authoritative evidence:

# SnapIMS v0.13.0 Stress QA and Operator-Workflow Bug Report

**Test date:** August 3, 2026 (Mountain Time; evidence timestamps may appear as August 4 UTC)  
**Release tested:** SnapIMS v0.13.0  
**Source archive SHA-256:** `3db75f2da21ac40954b3a395aceb3b160d1885faab2beb34f3c5d4451a485541`  
**Verdict:** **FAIL — do not treat v0.13.0 as production-ready**

## 1. Executive result

The new folder-based Import workflow is substantially faster and more responsive than the older blocking workflow in the tested Linux environment. A real 100-item/202-photo QR fixture returned control to the browser in 0.166 seconds, grouped exactly 100 items, survived repeated browser refreshes during scanning, and recorded one decode and one QR scan per image.

The release still has four release-blocking defects:

1. A long-run SQLite/file-descriptor leak eventually breaks database and filesystem operations.
2. Two tabs can preview and commit the same folder concurrently, causing a staging-directory collision and a failed Import job.
3. The installed `snapims up` launcher can start an older source tree against the newly migrated schema.
4. Batch Editor renders all rows at once and becomes severely slow at 1,000–5,000 items.

The Batch Editor also contains the operator-consistency failures requested for this audit: Fill Down does not work for Tags, Location, Review, or Rare; keyboard navigation cannot cross the Tags column; and selected rows remain armed after filters hide them.

## 2. Environment and limits

| Component | Test environment |
|---|---|
| Operating system | Linux 6.12.13 x86_64, glibc 2.41 |
| Python | 3.13.5 |
| Browser | Chromium 144.0.7559.96 through Playwright |
| Data | Disposable `/tmp/snapims-stress-data` workspace |
| Target 2012 Mac mini | Not available; not tested |
| Native Firefox | Not available; not tested |
| Live AI / Shopify | Not exercised in this stress pass |

The owner-machine launcher/schema failure is included because it was reproduced in the supplied terminal log. All other findings below came from the locally extracted v0.13.0 archive in the sandbox.

## 3. Test scope

The audit exercised:

- Clean application startup and real HTTP server operation.
- Folder listing and Import page navigation.
- Real decodable SnapIMS NEXT QR images.
- 20-item/39-photo and 100-item/202-photo Import jobs.
- Browser refreshes during scanning.
- Commit and Batch Editor handoff.
- Concurrent browser tabs and stale revision protection.
- Rapid cell edits and latest-value persistence.
- Fill Down across every editable column type.
- Bulk Tags, Location, Review, and selection behavior.
- Desktop and 390-pixel mobile layouts.
- Synthetic 1,000-item and 5,000-item Batch Editor loads.
- Complete 266-test collection in one process.
- Focused test groups, Python compilation, JavaScript syntax, and installer shell syntax.

## 4. Measured results

### Import

| Scenario | Result |
|---|---:|
| 20 items / 39 photos — Preview request | 0.194 s |
| 20 items / 39 photos — stored scan duration | 425 ms |
| 20 items / 39 photos — decodes / QR scans | 39 / 39 |
| 100 items / 202 photos — Preview request | 0.166 s |
| 100 items / 202 photos — stored scan duration | 1,837 ms |
| 100 items / 202 photos — commit | 3.215 s |
| 100-item grouping | Exact: 100 items |
| Preview page size | 20 items |
| Refresh during scan | Passed |

### Batch Editor scaling

| Items | Browser DOMContentLoaded | Response size | Result |
|---:|---:|---:|---|
| 20 | 0.214 s direct HTTP | 111,316 bytes | Acceptable |
| 100 | 0.318 s browser | 512,017 bytes | Acceptable |
| 1,000 | 3.020 s browser | 4,527,628 bytes | Fails 1-second navigation target |
| 5,000 | 11.593 s browser | 22,664,709 bytes | Severe freeze/delay risk |

The server-side 5,000-row response completed in 1.218 seconds, but the browser required 11.593 seconds to build the DOM. The route calls `list_editor_items()` without a limit and the template renders every row, including a second full JSON representation for client-side state.

### Automated tests

| Check | Result |
|---|---|
| Tests collected | 266 |
| Complete single-process run | 259 passed, 3 skipped, 2 failed, 2 setup errors |
| Failure mode | `OSError: [Errno 24] Too many open files`; subsequent SQLite open failures |
| Monitored rerun peak by 54% | 331 open file descriptors |
| Dominant retained handles | Prior-test `inventory.sqlite3` and `inventory.sqlite3-wal` files |
| Focused grouped runs | Passed, with expected skips |
| `python3 -m compileall` | Pass |
| `node --check snapims/web/static/app.js` | Pass |
| `bash -n install_v0130.sh` | Pass |

## 5. Detailed issue register

### QA-0130-001 — Critical — SQLite/file-descriptor resources accumulate until operations fail

**Finding**  
The complete test collection reaches the end of the run and then fails because the process has retained too many open files. A monitored rerun already held 331 descriptors at 54% completion. The peak snapshot is dominated by SQLite database and WAL handles from test workspaces whose tests had already finished.

**Reproduction**

1. Run all 266 tests in one Python process.
2. Observe two failures and two setup errors near the end.
3. Errors include `Errno 24`, `sqlite3.OperationalError: unable to open database file`, and inability to create another pytest temporary directory.
4. Monitor `/proc/<pytest-pid>/fd`; the count grows across completed tests instead of returning to baseline.

**Code evidence**  
There are 26 `with db.connect(...) as connection:` call sites across operational modules. SQLite's connection context manager controls transactions but does not itself guarantee an explicit `close()` at the end of every usage path. The retained-handle snapshot proves that completed workflows leave SQLite descriptors alive; every owner and background job must be audited rather than patching only the final failing test.

**Impact**  
This is not merely a test problem. A long-running local server that repeatedly imports, reviews, recognizes, edits, and publishes can eventually lose the ability to open its database, source files, logs, or temporary files.

**Required fix**

- Introduce one explicit connection context helper that always closes in `finally`.
- Convert every direct `db.connect` usage to that helper or explicit `try/finally` close.
- Ensure completed Import and background jobs release database, directory, image, and log handles.
- Add a regression test that repeats representative workflows and asserts descriptor count returns near baseline.

**Release status:** **BLOCKER**

---

### QA-0130-002 — High — Duplicate same-folder Import jobs race during commit

**Finding**  
The same immediate batch folder can be previewed from two tabs at the same time. SnapIMS creates two independent jobs, both reach READY, and both are allowed to commit. They share a staging identity and collide during final rename.

**Reproduction**

1. Open Import in two browser tabs.
2. Select `QA-RACE-DUPLICATE` in both.
3. Submit Preview in both tabs nearly simultaneously.
4. Two jobs are created 63 ms apart:
   - `e15cb814d1494a918e2dc83dd9a7195d`
   - `be43f01fe61848759e1501cd3b4d95f1`
5. Commit both.
6. One job imports successfully; the other becomes FAILED with:

```text
FileNotFoundError: [Errno 2] No such file or directory:
'/tmp/snapims-stress-data/originals/.staging-31e81a87b8d0b773'
-> '/tmp/snapims-stress-data/originals/20260804-013707-QA-RACE-DUPLICATE'
```

**Impact**  
A double-click, stale tab, or two operators can create a failed Import state from an otherwise valid folder. Restart recovery and operator interpretation become ambiguous.

**Required fix**

- Enforce one active Preview/Commit job per canonical folder identity in the database.
- Return or redirect to the existing job when the same folder is already active.
- Make Commit idempotent and reject duplicate submission before staging begins.
- Use per-job staging directories even after an idempotency guard is added.

**Release status:** **BLOCKER**

---

### QA-0130-003 — High — Upgrade launcher can start old code against schema 14

**Finding**  
On the owner machine, the installed CLI reported `0.13.0`, but `snapims up` launched the old project at `/home/isaiah/Projects/SnapIMS`. Its log stated `SnapIMS 0.12.3 starting`. Because the database had already migrated to schema 14, the old server refused startup and Home returned HTTP 500.

**Impact**  
A nominally successful upgrade can make SnapIMS unavailable while presenting contradictory version information.

**Required fix**

- Detect all existing systemd/user-service and launcher definitions during installation.
- Rewrite service working directory and executable path to the installed v0.13.x release.
- Print the exact resolved executable and source path in `snapims up` and `snapims status`.
- Refuse to report a successful upgrade until `/health`, `/`, and the displayed version all match.
- Add an upgrade test beginning with an existing v0.12.3 service definition.

**Release status:** **BLOCKER**

---

### QA-0130-004 — High — Batch Editor fully renders every item

**Finding**  
The Batch Editor route loads the entire batch with `db.list_editor_items()` and passes every item to the template. A 5,000-item batch produces 22.66 MB of HTML and takes 11.593 seconds to reach DOMContentLoaded in Chromium.

**Impact**  
This directly conflicts with the v0.13.0 requirement to avoid full-table HTML rendering. It is particularly risky on the intended 2012 Mac mini with 8 GB RAM.

**Required fix**

- Add bounded server-side paging or virtualized/lazy row loading.
- Avoid embedding the same full item collection both as table markup and JSON.
- Keep search, sort, selection, Fill Down, undo, and bulk operations correct across pages.
- Add 1,000- and 5,000-item browser performance gates.

**Release status:** **BLOCKER**

---

### QA-0130-005 — Medium — Fill Down does not support Tags

**Finding**  
Focusing a Tags cell and selecting Fill Down displays:

```text
Fill Down is not supported for tag_ids.
```

The Fill Down action map contains only title, price, discount, description, and a stale shelf key. `tag_ids` is omitted even though the editor exposes Tags as a normal editable column.

**Impact**  
Operators must repeatedly edit tags or abandon the spreadsheet-style workflow for a separate Bulk Append Tags dialog. Append is not equivalent to copying the source cell because it cannot replace the destination tag set.

**Required fix**

- Add an atomic copy/set-tags bulk action using validated immutable Tag IDs.
- Preserve controlled-tag validation and auditing.
- Test empty tag sets, multiple tags, retired tags, and destination rows that already contain tags.

**Release status:** Patch required

---

### QA-0130-006 — Medium — Location Fill Down uses obsolete `shelf` field name

**Finding**  
The visible Location input uses `data-field="location"`, but the Fill Down map contains `shelf: "set_location"`. The operator receives:

```text
Fill Down is not supported for location.
```

**Impact**  
The most obvious location-propagation command is broken despite v0.13.0 making batch and item locations a central workflow.

**Required fix**

- Map `location` to `set_location`.
- Normalize blank and case-insensitive `None` to unassigned.
- Record each affected item in location history.
- Add browser and database assertions.

**Release status:** Patch required

---

### QA-0130-007 — Medium — Fill Down does not support Review or Rare

**Finding**  
Review and Rare are editable checkbox fields, but both are omitted from the Fill Down action map. Each produces an unsupported-field toast.

**Impact**  
The command appears universal but silently has a narrow undocumented capability set. Operators cannot propagate flags consistently with neighboring columns.

**Required fix**

- Add boolean copy-down operations for `review` and `rare`.
- Copy the focused source state exactly, including clearing checked values.
- Perform one atomic audited bulk update.

**Release status:** Patch required

---

### QA-0130-008 — Medium — Arrow-key navigation cannot cross Tags

**Finding**  
ArrowRight from Price leaves focus on `price_cents`; ArrowLeft from Discount leaves focus on `discount_percent`. The intermediate Tags wrapper is a non-focusable `<div>`. Vertical navigation already handles it using `focusTagInput()`, but horizontal navigation calls `.focus()` directly on the wrapper.

**Impact**  
Keyboard-oriented operators cannot traverse the complete row and receive no explanation that navigation failed.

**Required fix**

Reuse the same special tag-picker focus path in `moveHorizontal()` that is already used by `focusSameField()`.

**Release status:** Patch required

---

### QA-0130-009 — Medium — Hidden selected rows remain eligible for bulk changes

**Finding**  
A row can be selected, then hidden by search or filter. The counter remains `1 selected` while zero rows are visible, and bulk actions continue to target the hidden row.

**Impact**  
An operator can modify inventory that is no longer visible in the working set. The risk increases when changing search text after building a selection.

**Required fix**

Either clear newly hidden selections or display separate visible/hidden selected counts and require confirmation listing the hidden targets before applying a bulk action.

**Release status:** Patch required

---

### QA-0130-010 — Low — Bulk Location still describes a shelf-only model

**Finding**  
The Bulk Location explanation says:

```text
Moves selected tapes to this shelf.
```

v0.13.0 permits arbitrary free-text locations such as `Processing Table` and an unassigned state.

**Impact**  
The text contradicts the new workflow and can cause operators to believe an A1-style shelf is still required.

**Required fix**  
Replace current shelf-specific wording with location/unassigned terminology in the UI and synchronized documentation.

**Release status:** Patch required

## 6. Positive findings

The following behavior passed this audit:

- Import Preview returned browser control well under one second for both tested QR datasets.
- Progress persisted through browser refresh during the 202-photo scan.
- The 100-item dataset grouped exactly 100 items.
- Cold scan counters showed one image decode and one QR scan per source image.
- Preview displayed 20 items at a time rather than rendering all 100.
- Bulk Append Tags worked as a separate operation.
- Bulk Location accepted `None` and stored unassigned values.
- Rapid consecutive edits preserved the latest value in a clean targeted test.
- Two-tab stale item editing returned HTTP 409, explained the conflict, and preserved the first accepted value.
- The mobile page body stayed within a 390-pixel viewport and the wide editor grid remained horizontally scrollable.
- No unhandled JavaScript page errors occurred in normal workflows; the recorded HTTP 409 was the deliberate stale-revision test.

## 7. Release decision and versioning

SnapIMS v0.13.0 should **not** be marked production-ready. Correcting the findings above without changing the workflow constitutes a patch release under the project policy:

```text
0.13.0 -> 0.13.1
```

v0.13.1 acceptance should require:

1. The complete 266-test suite passes in one clean process with stable file-descriptor counts.
2. Duplicate same-folder Preview and Commit requests are idempotent.
3. Clean install and v0.12.3 upgrade both launch the same v0.13.1 code path and survive restart.
4. A 5,000-item editor no longer renders all rows at once and normal navigation remains responsive.
5. Fill Down works for Tags, Location, Review, and Rare.
6. Keyboard navigation crosses Tags in both directions.
7. Hidden-row bulk-selection behavior is made explicit and safe.
8. The fixed build is then rechecked on the actual 2012 Mac mini and native Firefox.

## 8. Evidence index

The evidence archive contains:

- Browser screenshots for Home, Import, preview, desktop/mobile Batch Editor, Tags Fill Down, hidden selection, and large batches.
- `targeted-browser-results.json` and `concurrency-browser-results.json`.
- `duplicate-folder-race.json`.
- `import-job-metrics.json`.
- Full-suite failure log and a monitored file-descriptor peak snapshot.
- Raw FD-count samples.
- Source excerpts showing Fill Down mappings, tag-picker focus handling, full-table route behavior, and stale shelf copy.
- Playwright scripts used for the stress checks.
- Server log from the disposable QA run.

