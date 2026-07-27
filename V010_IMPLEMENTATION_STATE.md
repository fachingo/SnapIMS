# V010_IMPLEMENTATION_STATE

## Repository

- Project: SnapIMS
- Branch: `feature/v0.10.0-final-preproduction`
- HEAD: `c9a0fd5` (verified Phase 1 orchestration/Shopify milestone)
- Upstream: none (branch not yet pushed)
- Started: 2026-07-26T18:59:00-06:00
- Last updated: 2026-07-26T20:38:00-06:00
- Current application version: source/package metadata `0.9.0`; installed editable distribution metadata `0.7.0`
- Inventory schema: 8
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

- Phase: 1 — Stabilization, Security and Truthful Orchestration
- Phase file: `docs/codex-work-orders/v0.10.0/03_PHASE_1_STABILIZATION_SECURITY.md`
- Status: IN PROGRESS
- Latest verified commit: `c9a0fd5` (`fix: make orchestration and Shopify retries truthful`)
- NEXT_PHASE: `03_PHASE_1_STABILIZATION_SECURITY.md`
- NEXT_ACTION: Repair the remaining baseline type defects, then implement the schema-backed Controlled Tags workflow and verified Firefox shortcuts.

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

## Migrations

| Migration | Database | Backup | Applied to disposable copy | Applied to production | Verification |
|---|---|---|---|---|---|
| Baseline schema 8 (existing) | inventory | Validated external online backup | Opened read-only | Already present before work | integrity OK; FK 0; manifest OK |
| Baseline schema 1 (existing) | catalog | Validated external online backup | Opened read-only | Already present before work | integrity OK; FK 0; structure OK |

No v0.10.0 migration has been authored or applied.

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
| Installed-wheel smoke | PASS | `release-evidence/v0.10.0/phase-1-security/installed-wheel-smoke.txt` | Wheel and source both report 0.9.0 |
| Phase 1 orchestration/Shopify focused tests | PASS | `release-evidence/v0.10.0/phase-1-orchestration/VERIFICATION.md` | 40 tests |
| Full regression after orchestration/Shopify milestone | PASS | `release-evidence/v0.10.0/phase-1-orchestration/VERIFICATION.md` | One expected skip |
| Build and dependency verification | PASS | `release-evidence/v0.10.0/phase-1-orchestration/VERIFICATION.md` | sdist, wheel, and pip check pass |
| Current mypy | FAIL, improved | `release-evidence/v0.10.0/phase-1-orchestration/VERIFICATION.md` | 16 remaining baseline defects; none in changed modules |

## Browser verification

| Workflow | Browser | Result | Evidence |
|---|---|---|---|
| Public SnapIMS authentication landing | read-only HTTP probe | PASS | `release-evidence/v0.10.0/baseline/ENDPOINT_VERIFICATION.md` |
| Official Guacamole hostname | DNS/HTTP probe | FAIL | `desktop.ims.canadavhs.ca` did not resolve |
| Compatibility Guacamole hostname | read-only HTTP probe | PASS | Guacamole login markers found at `remote.canadavhs.ca` |
| Native Firefox final walkthrough | Firefox | NOT RUN | Required after Phase 1 UI repair |

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
| V010-P0-001 | High | `python -m mypy snapims --ignore-missing-imports` | Improved from 19 to 16 baseline type errors | Repair before Phase 1 exit |
| V010-P0-002 | High | `python -m build --no-isolation` | RESOLVED | Installed declared setuptools/wheel; build and isolated wheel smoke pass |
| V010-P0-003 | High | Resolve `desktop.ims.canadavhs.ca` | DNS resolution fails | Treat `remote.canadavhs.ca` as compatibility evidence; owner/infrastructure decision before docs claim official hostname |
| V010-P0-004 | High | Backup root-only Guacamole secret file | RESOLVED | Owner completed copy; checksum/mode verified and external manifest updated |
| V010-P0-005 | Medium | Compare installed metadata to source | installed metadata 0.7.0; source 0.9.0 | Reinstall verified package after build repair |
| V010-P0-006 | Low | `sha256sum -c SHA256SUMS` in work-order package | All present files match; two reference PDFs and `install_into_repo.sh` are absent | Markdown references are complete and authoritative; do not claim the package has all 26 manifest files |

## Owner decisions

| Decision | Choice | Date | Consequence |
|---|---|---|---|
| Tool/command approvals | Owner approved all remaining commands | 2026-07-26 | No further tool-level confirmation is needed, but approval cannot supply the host's interactive sudo password |
| Root-only Guacamole backup | Completed | 2026-07-26 | Phase 0 restore point is complete |
| Official vs compatibility Guacamole hostname | Pending | — | Current evidence supports only `remote.canadavhs.ca` |

## Files/areas currently being edited

- `snapims/db.py`
- `snapims/catalog/`
- `snapims/inventory.py`
- `snapims/processor.py`
- `snapims/recognition/`
- `snapims/shopify/`
- `snapims/web/app.py`
- Phase 1 stabilization tests

## Resume checklist

1. Verify branch and HEAD.
2. Verify working tree.
3. Verify latest phase commit.
4. Run focused tests.
5. Read current phase acceptance criteria.
6. Continue first incomplete item.
