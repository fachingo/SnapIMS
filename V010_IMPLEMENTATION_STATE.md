# V010_IMPLEMENTATION_STATE

## Repository

- Project: SnapIMS
- Branch: `feature/v0.10.0-final-preproduction`
- HEAD: `73243f5` (verified pre-Phase-4 remote/version/hostname checkpoint)
- Upstream: `origin/feature/v0.10.0-final-preproduction`
- Started: 2026-07-26T18:59:00-06:00
- Last updated: 2026-07-27T14:19:08-06:00
- Current application version: source/package metadata, active editable
  distribution, global launcher, CLI, and running status all `0.10.0`
- Inventory schema: 12 in Phase 4 code and disposable migration; production remains 11 pending the Phase 4 production gate
- Catalog schema: 1

## Preservation

- Backup root: `/home/isaiah/SnapIMS-backups/v0.10.0-prework-20260726-190242`
- Inventory backup: `databases/inventory.sqlite3`, SHA-256 `c7e98c31c4c4cfe78d22a8c900917588e181057e1dfa3eb70b20e0b10fa68fb0`
- Catalog backup: `databases/movie_catalog.sqlite3`, SHA-256 `a0ab5e86c76c4d4f2df84c2d72a90b255f5f28c4c4cc4677d87b5202d99cdcd0`
- Media manifest: `manifests/media-sha256.jsonl`; 1,306 files; 433,149,821 bytes; media was not duplicated
- Secret/config backup: project `.env`, prior `.env` backup, Cloudflare directory, Guacamole files, and service units copied with owner-only backup permissions. The owner-copied credential backup was verified without reading or printing its value.
- Git preservation: `git/repository.bundle`, worktree/index patches, status/log/remote records, and an external copy of the untracked work-order package
- Integrity result: both backups `PRAGMA integrity_check=ok`; zero foreign-key violations
- Restore probe: both backup databases copied to `restore-probe/` and opened successfully at schemas 8 and 1

## Current phase

- Phase: 4 — Recognition Routing, Escalation, and Cost Control
- Phase file: `docs/codex-work-orders/v0.10.0/06_PHASE_4_RECOGNITION_ROUTING.md`
- Status: IMPLEMENTATION COMPLETE; NATIVE FIREFOX AND PRODUCTION ACCEPTANCE PENDING
- Latest verified commit: `73243f5` (`Reconcile pre-Phase-4 checkpoint`)
- NEXT_PHASE: `06_PHASE_4_RECOGNITION_ROUTING.md`
- NEXT_ACTION: Commit the verified implementation milestone, then run native Firefox, restart/interruption, and production schema-12 acceptance before closing Phase 4.

## Completed criteria

- [x] Read the controller, every numbered phase, state/acceptance/final-report/approval/version/reference contracts, integrated roadmap, and integrated audit.
- [x] Recorded starting branch, commit, remotes, log, dirty state, versions, configuration state, paths, schemas, migrations, services, and current endpoints without printing secrets.
- [x] Preserved the untracked work-order package externally before creating the v0.10.0 branch.
- [x] Created and switched to `feature/v0.10.0-final-preproduction`.
- [x] Created online SQLite backups and verified integrity, foreign keys, checksums, and disposable restore probes.
- [x] Created a complete originals/processed checksum manifest instead of blindly duplicating 433 MB of media.
- [x] Backed up project secrets, Cloudflare configuration, exports, active documents, service units, Git history, and all readable Guacamole configuration.
- [x] Captured baseline pytest, Ruff, mypy, compileall, JavaScript, build, pip, diff, database, service, endpoint, and secret-scan results.
- [x] Created the architecture reconciliation and migration design baseline.
- [x] Verified every present work-order file against `SHA256SUMS`; all present files match.
- [x] Confirmed `snapims-admin.env` is an installer credential-retrieval file and is not loaded by either the `guacd` or SnapIMS Tomcat systemd unit; the runtime-authoritative `user-mapping.xml`, `guacamole.properties`, `guacd.conf`, and units are backed up.
- [x] Backed up `/etc/guacamole/snapims-admin.env`; verified owner/group `isaiah:isaiah`, mode 0600, parent directories mode 0700, size 97 bytes, and SHA-256 without printing contents.
- [ ] Capture an installed-wheel smoke test after the baseline build-tool failure is repaired in Phase 1.
- [x] Created the Phase 0 preservation milestone and owner-gate checkpoint commits.
- [x] Added session-bound CSRF protection for authenticated form and JSON state changes plus anonymous login CSRF.
- [x] Added configured Host/Origin validation compatible with the local and Cloudflare-forwarded HTTPS hosts.
- [x] Added CSP, nosniff, referrer, permissions, anti-frame, and sensitive-page no-store headers.
- [x] Bound signed sessions to session generation and the current password hash so credential rotation revokes existing sessions.
- [x] Added bounded identity/IP login failure tracking with stepped backoff and generic client responses.
- [x] Added safe authentication success/failure/throttle/logout operational log facts without password values.
- [x] Restored declared build tooling, built the package, and passed an isolated no-dependency installed-wheel version smoke.
- [x] Made required database health failures machine-readable and non-200 while keeping optional catalog degradation distinct.
- [x] Made doctor exit nonzero for required failures and exposed managed-service ownership, PID identity, and tunnel connector truth.
- [x] Added explicit safe update check/apply modes, dirty/detached/upstream refusal, database restore metadata, dependency update, migration, restart, and rollback guidance.
- [x] Replaced interpolated shell execution with safe `cwd`, environment, and argv execution.
- [x] Persisted Shopify inventory activation idempotency identity and request evidence before the network call, reused it on retry, reconciled uncertain outcomes, and rejected ambiguous SKUs.
- [x] Cleared all 19 baseline mypy defects without suppressions; all 37 source modules pass.
- [x] Added schema 9 Controlled Tags with immutable IDs, aliases, governance flags, evidence, and Item relationships.
- [x] Migrated legacy operator tags deterministically while keeping the text column as a compatibility projection.
- [x] Restricted AI to approved AI-eligible Tag IDs and logged unknown/ineligible/deterministic-only rejections.
- [x] Added Review and Batch Editor Tag pills/autocomplete with retired-tag history and keyboard behavior.
- [x] Implemented `Alt+P` and visible-action `Alt+1`–`Alt+9`; verified typing and Escape behavior in native Firefox.
- [x] Removed CSP-blocked inline event handlers discovered by Firefox.
- [x] Applied schema 9 to production with an automatic pre-migration backup and preserved all 4 batches and 32 items.
- [x] Passed production restart, required doctor checks, and a full `down`/`up` cold boot.
- [x] Reconciled the current README without labeling the unfinished branch as released v0.10.0.
- [x] Added schema 10 durable operational events with complete context fields, required indexes, and bounded class-based retention.
- [x] Added the shared redaction layer for events, rotating logs, exception summaries, diagnostics, CLI output, and support bundles.
- [x] Added structured `snapims log`/`snapims logs` aliases with composable follow/last/since/error/severity/source/entity/correlation/JSON/export filters.
- [x] Instrumented startup/shutdown, migration/backup, auth, import, recognition, catalog, CSV, bulk, Settings save, Shopify stages, and infrastructure recovery.
- [x] Added Diagnostics Live Activity with active operations, queue depths, filters, elapsed/correlation/retry facts, safe details, copy, bounded polling, and support-bundle export.
- [x] Verified exact recognition, catalog ambiguity, Shopify fake-failure/retry, duplicate-import, tunnel/origin, redaction, CLI, and restart-durability acceptance paths.
- [x] Passed native Firefox Phase 2 acceptance with eight checks and zero console/page errors.
- [x] Applied schema 10 to production with automatic backup and preserved all 4 batches and 32 items.
- [x] Passed production cold start, status, doctor, structured log aliases, integrity, foreign keys, and schema manifest.
- [x] Added schema 11 configuration revisions and tested provider-model capabilities with automatic pre-migration backup and rollback evidence.
- [x] Replaced implicit dotenv mutation with explicit environment → secret store → persisted setting → legacy `.env` → default precedence.
- [x] Added owner-only, mode-checked, atomic and fsynced secret storage with timestamped backups, masked reads, safe legacy copy, and rollback.
- [x] Added General, Recognition, Shopify, Movie Data, Infrastructure, Security, and Backup/Retention settings sections with provenance and external-override protection.
- [x] Added administrator re-authentication for secret changes, legacy migration, rollback, credential rotation, and global session revocation.
- [x] Added official-model discovery and bounded OpenAI image plus strict-schema capability probing; recognition roles accept only tested-compatible model IDs.
- [x] Added the validated read-only Shopify shop identity, granted-scope/capability-gap, and location probe with draft-only enforcement and no automatic write.
- [x] Added Wikimedia identification, bounded concurrency, request spacing, Retry-After/exponential retry, timeout/cache controls, and candidate provenance preview.
- [x] Verified submitted connection-test secrets are discarded unless explicitly saved and never appear in HTML, URLs, diagnostics events, support bundles, or error responses.
- [x] Passed native Firefox Phase 3 acceptance with ten checks and zero console/page errors, including secure save, restart retention, bundle redaction, and session revocation.
- [x] Applied schema 11 to production with an automatic backup, preserved all 4 batches and 32 items, and passed restart, cold boot, status, doctor, endpoint, integrity, FK, and manifest checks.
- [x] Pushed `feature/v0.10.0-final-preproduction` without merge and verified requested commit `77c09bc` in the origin branch history under later Phase 3 closure `9b1c4b7`.
- [x] Replaced stale editable 0.7.0 metadata with editable 0.10.0 and verified package, distribution, launcher, CLI, status, doctor, focused tests, pip consistency, and cold start.
- [x] Adopted `https://remote.canadavhs.ca/guacamole/` as the official Guacamole URL in runtime defaults and operator-facing material; retained unresolved `desktop.ims` only as explicit backlog.
- [x] Recorded extensible Phase 4 capture-source values and the Phase 6 shared-catalog provenance/contribution privacy boundary.
- [x] Added schema 12 append-only recognition attempts with UUID, Item/provider/model/tier/trigger/actor, prompt/schema/image profiles, selected image IDs/hashes/capture provenance, evidence, uncertainty, contradiction, token, configured-CAD-cost, latency, prior-attempt, request, and route metadata.
- [x] Separated mutable selection/acceptance state from immutable attempt evidence and added append-only selection/acceptance/supersession/failure events.
- [x] Added durable idempotent per-Item recognition requests, restart pause/recovery, safe resume, Retry-After evidence, and duplicate-click suppression.
- [x] Added configurable baseline/escalation/frontier/manual routing with strict tested-model selection, confidence/UNKNOWN/schema/image/catalog/ambiguity/unsupported/operator triggers, bounded image profiles, hash deduplication, and no automatic working-field replacement.
- [x] Added an operator Recognition workspace with jobs, queue scopes, pause/resume, model ladder, filters, attempt comparison/selection/explicit acceptance, usage/cost/latency, and owner-labelled benchmark reporting.
- [x] Kept normal Approve & Next independent of expensive recognition; later attempts on approved Items remain suggestions until explicit replacement.
- [x] Added capture provenance for desktop QR/manual and future Android/manual/test sources without implementing an Android client.
- [x] Added duplicate actions Open Existing, Rerun Unfinished, Rerun All, Isolated Test Copy, and Cancel.
- [x] Added isolated test-copy Batch/Item identity, source linkage, TEST provenance, shared immutable media evidence, visible quarantine, and database/service enforcement that prevents sale-ready, reservation-eligible, or Shopify-ready state.

## Migrations

| Migration | Database | Backup | Applied to disposable copy | Applied to production | Verification |
|---|---|---|---|---|---|
| Baseline schema 8 (existing) | inventory | Validated external online backup | Opened read-only | Already present before work | integrity OK; FK 0; manifest OK |
| Baseline schema 1 (existing) | catalog | Validated external online backup | Opened read-only | Already present before work | integrity OK; FK 0; structure OK |
| Inventory schema 8 → 9 (Controlled Tags) | inventory | `/home/isaiah/SnapIMS-data/backups/inventory-20260726-221200-351595-before-schema-v9.sqlite3` | PASS on production-data copy; 4 batches and 32 items preserved | PASS | integrity OK; FK 0; manifest OK; 4 batches and 32 items preserved |
| Inventory schema 9 → 10 (Operational Events) | inventory | `/home/isaiah/SnapIMS-data/backups/inventory-20260726-231208-344081-before-schema-v10.sqlite3` | PASS in unit migration and Firefox workspaces | PASS | integrity OK; FK 0; manifest OK; 4 batches and 32 items preserved; migration event present |
| Inventory schema 10 → 11 (Secure Settings) | inventory | `/home/isaiah/SnapIMS-data/backups/inventory-20260727-130108-376761-before-schema-v11.sqlite3` | PASS in migration tests and Firefox workspaces | PASS | integrity OK; FK 0; manifest OK; 4 batches and 32 items preserved |
| Inventory schema 11 → 12 (Recognition Routing) | inventory | Automatic `before-schema-v12` backup verified on disposable production-data copy | PASS; `/tmp/snapims-phase4-migration-fi152R` | PENDING PHASE 4 PRODUCTION GATE | integrity OK; FK 0; manifest OK; 4 batches, 32 items, 13 prior attempts and 173 photo rows preserved |

## Tests

| Command/test | Result | Evidence path | Notes |
|---|---|---|---|
| `python -m pytest -q` | PASS | `release-evidence/v0.10.0/baseline/pytest.txt` | One expected skip; exit 0 |
| `python -m ruff check .` | PASS | `release-evidence/v0.10.0/baseline/ruff.txt` | Exit 0 |
| `python -m mypy snapims --ignore-missing-imports` | FAIL | `release-evidence/v0.10.0/baseline/mypy.txt` | 19 baseline errors |
| `python -m compileall -q snapims tests scripts` | PASS | `release-evidence/v0.10.0/baseline/compileall.txt` | Exit 0 |
| `node --check snapims/web/static/app.js` | PASS | `release-evidence/v0.10.0/baseline/node-check.txt` | Exit 0 |
| `python -m build --no-isolation` | FAIL | `release-evidence/v0.10.0/baseline/build.txt` | venv lacks setuptools/wheel; no wheel smoke possible |
| `python -m pip check` | PASS | `release-evidence/v0.10.0/baseline/pip-check.txt` | Exit 0 |
| `git diff --check` | PASS | `release-evidence/v0.10.0/baseline/git-diff-check.txt` | Exit 0 |
| inventory/catalog integrity, FK, manifest/structure, FTS | PASS | `release-evidence/v0.10.0/baseline/database-integrity.json` | Inventory schema 8; catalog schema 1 |
| high-confidence repository secret scan | PASS with scope note | `release-evidence/v0.10.0/baseline/secret-scan.txt` | 525 files scanned; four >5 MB historical binaries listed as skipped |
| work-order SHA-256 verification | PARTIAL | `release-evidence/v0.10.0/baseline/work-order-sha256.txt` | All present files match; two duplicate-reference PDFs and installer listed by the manifest are absent |
| `snapims status` | PASS under current implementation | `release-evidence/v0.10.0/baseline/snapims-status.txt` | Phase 1 must make health semantics truthful |
| `snapims doctor` | PASS under current implementation | `release-evidence/v0.10.0/baseline/snapims-doctor.txt` | Current command does not yet exit nonzero on required failures |
| Phase 1 security focused tests | PASS | `release-evidence/v0.10.0/phase-1-security/security-focused.txt` | 17 tests |
| Phase 1 focused Ruff | PASS | `release-evidence/v0.10.0/phase-1-security/ruff.txt` | Exit 0 |
| Phase 1 JavaScript syntax | PASS | `release-evidence/v0.10.0/phase-1-security/node-check.txt` | Exit 0 |
| Phase 1 mypy | FAIL at baseline count | `release-evidence/v0.10.0/phase-1-security/mypy.txt` | 19 pre-existing errors; no errors from security changes |
| Installed-wheel smoke | PASS | `release-evidence/v0.10.0/phase-1-security/installed-wheel-smoke.txt` | Wheel and source both report 0.10.0 |
| Phase 1 orchestration/Shopify focused tests | PASS | `release-evidence/v0.10.0/phase-1-orchestration/VERIFICATION.md` | 40 tests |
| Full regression after orchestration/Shopify milestone | PASS | `release-evidence/v0.10.0/phase-1-orchestration/VERIFICATION.md` | One expected skip |
| Build and dependency verification | PASS | `release-evidence/v0.10.0/phase-1-orchestration/VERIFICATION.md` | sdist, wheel, and pip check pass |
| Post-orchestration interim mypy | FAIL, improved | `release-evidence/v0.10.0/phase-1-orchestration/VERIFICATION.md` | 16 remaining baseline defects at that checkpoint |
| Phase 1 final full regression | PASS | `release-evidence/v0.10.0/phase-1-controlled-tags/VERIFICATION.md` | One expected skip |
| Phase 1 final mypy | PASS | `release-evidence/v0.10.0/phase-1-type-safety/VERIFICATION.md` | 37 source files |
| Controlled Tags migration/unit/HTTP tests | PASS | `release-evidence/v0.10.0/phase-1-controlled-tags/VERIFICATION.md` | Unknown/retired/AI rejection and compatibility paths covered |
| Production cold boot and doctor | PASS | `release-evidence/v0.10.0/phase-1-controlled-tags/PRODUCTION_ACCEPTANCE.md` | Schema 9; all required checks pass |
| Phase 2 full regression/static/build gate | PASS | `release-evidence/v0.10.0/phase-2-observability/VERIFICATION.md` | One expected skip; 38 mypy-clean modules |
| Phase 2 event/redaction/CLI/workflow acceptance | PASS | `release-evidence/v0.10.0/phase-2-observability/VERIFICATION.md` | Recognition, catalog, Shopify, duplicate import, support bundle, retention |
| Phase 2 production migration/cold boot | PASS | `release-evidence/v0.10.0/phase-2-observability/PRODUCTION_ACCEPTANCE.md` | Schema 10; 4 batches/32 items; all required checks pass |
| Phase 3 full regression/static/build gate | PASS | `release-evidence/v0.10.0/phase-3-settings/VERIFICATION.md` | One expected skip; 40 mypy-clean modules; isolated sdist/wheel pass |
| Phase 3 secure store/provenance/provider/HTTP acceptance | PASS | `release-evidence/v0.10.0/phase-3-settings/VERIFICATION.md` | Atomic permissions, rollback, tested models, unsaved-secret no-echo, session revocation |
| Phase 3 production migration/cold boot | PASS | `release-evidence/v0.10.0/phase-3-settings/PRODUCTION_ACCEPTANCE.md` | Schema 11; 4 batches/32 items; all required checks pass |
| Pre-Phase-4 remote/version/hostname checkpoint | PASS | `release-evidence/v0.10.0/pre-phase-4-checkpoint/VERIFICATION.md` | Origin verified; all active metadata 0.10.0; 34 focused tests; pip check; cold boot; official hostname reconciled |
| Phase 4 full regression | PASS | `release-evidence/v0.10.0/phase-4-recognition/VERIFICATION.md` | 233 collected; one expected skip; exit 0 |
| Phase 4 focused acceptance | PASS | `tests/test_v010_phase4_recognition.py` | Immutable evidence, idempotent rerun, older-attempt selection, UNKNOWN, cost, capture provenance, test-copy quarantine, restart pause, workspace, and duplicate choices |
| Phase 4 static/build gate | PASS | `release-evidence/v0.10.0/phase-4-recognition/VERIFICATION.md` | Ruff; mypy 40 modules; JS syntax; diff check; sdist/wheel 0.10.0; pip check |

## Browser verification

| Workflow | Browser | Result | Evidence |
|---|---|---|---|
| Public SnapIMS authentication landing | read-only HTTP probe | PASS | `release-evidence/v0.10.0/baseline/ENDPOINT_VERIFICATION.md` |
| Official Guacamole hostname | owner decision and HTTPS probe | ACCESS-PROTECTED | `remote.canadavhs.ca/guacamole/` resolves and returned HTTP 403 to an unauthenticated probe; prior baseline probe found Guacamole login markers |
| Unresolved backlog hostname | DNS probe | FAIL | `desktop.ims.canadavhs.ca` does not resolve and is not a current operator endpoint |
| Phase 1 shortcuts and Controlled Tags | Playwright Firefox against real uvicorn | PASS | `release-evidence/v0.10.0/phase-1-firefox/` |
| Phase 2 Live Activity, filters, redaction, bundle, restart durability | Playwright Firefox against real uvicorn | PASS | `release-evidence/v0.10.0/phase-2-firefox/` |
| Phase 3 secure Settings, provenance, candidate test, redaction, restart, revocation | Playwright Firefox against real uvicorn | PASS | `release-evidence/v0.10.0/phase-3-firefox/` |

## External actions

| Action | Owner approval required | Approved | Result |
|---|---|---|---|
| Read-only local/public endpoint probes | No | N/A | Completed |
| Live Shopify write | Yes | No | Not attempted |
| Full Wikidata dump | Yes | No | Not attempted |
| Copy root-only Guacamole credential into backup | Yes — sudo credential | Yes | PASS; verified at required path with mode 0600 and restricted directory traversal |

## Known failures

| ID | Severity | Reproduction | Current state | Next action |
|---|---|---|---|---|
| V010-P0-001 | High | `python -m mypy snapims --ignore-missing-imports` | RESOLVED | All 37 source files pass |
| V010-P0-002 | High | `python -m build --no-isolation` | RESOLVED | Installed declared setuptools/wheel; build and isolated wheel smoke pass |
| V010-P0-003 | High | Resolve `desktop.ims.canadavhs.ca` | CLOSED AS BACKLOG | Owner designated `remote.canadavhs.ca/guacamole/` as official; do not claim `desktop.ims` without deliberate DNS and browser acceptance |
| V010-P0-004 | High | Backup root-only Guacamole secret file | RESOLVED | Owner completed copy; checksum/mode verified and external manifest updated |
| V010-P0-005 | Medium | Compare installed metadata to source | RESOLVED | Replaced stale editable 0.7.0 finder/dist-info with editable 0.10.0; CLI, package, metadata, launcher, status, doctor, tests, pip check, and cold start pass |
| V010-P0-006 | Low | `sha256sum -c SHA256SUMS` in work-order package | All present files match; two reference PDFs and `install_into_repo.sh` are absent | Markdown references are complete and authoritative; do not claim the package has all 26 manifest files |

## Owner decisions

| Decision | Choice | Date | Consequence |
|---|---|---|---|
| Tool/command approvals | Owner approved all remaining commands | 2026-07-26 | No further tool-level confirmation is needed, but approval cannot supply the host's interactive sudo password |
| Root-only Guacamole backup | Completed | 2026-07-26 | Phase 0 restore point is complete |
| Official Guacamole hostname | `https://remote.canadavhs.ca/guacamole/` | 2026-07-27 | Operator-facing defaults and claims use `remote`; `desktop.ims` remains unresolved backlog |
| Phase 4 capture provenance | Extensible capture-source values | 2026-07-27 | Recognition/image schemas must support desktop, Android-future, manual, and test origins without implementing Android |
| Community catalog contribution | Explicit opt-in policy boundary only | 2026-07-27 | Phase 6 adds field provenance and eligibility; no central upload without a separate owner-approved server/privacy/terms work order |

## Remote verification

- Branch push completed without merge:
  `origin/feature/v0.10.0-final-preproduction`.
- Remote head verified by `git ls-remote` at
  `9b1c4b78a4ff6832f75681d7c2cb83ec747642e3`.
- Requested commit
  `77c09bc17b30e24d8fcdbec3046a772d8118fe3a` is an ancestor of that later
  Phase 3 closure commit and is therefore visible in the remote branch
  history.
- Evidence:
  `release-evidence/v0.10.0/pre-phase-4-checkpoint/VERIFICATION.md`.

## Files/areas currently being edited

- Phase 4 recognition schema, routing service, import overrides, operator workspace,
  Review controls, quarantine enforcement, and acceptance tests.
- No live OpenAI or Shopify writes were performed.

## Resume checklist

1. Verify branch and HEAD.
2. Verify working tree.
3. Verify latest phase commit.
4. Run focused tests.
5. Read current phase acceptance criteria.
6. Continue first incomplete item.
