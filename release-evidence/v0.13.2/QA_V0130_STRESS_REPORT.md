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
