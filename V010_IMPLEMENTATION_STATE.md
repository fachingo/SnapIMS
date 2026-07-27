# V010_IMPLEMENTATION_STATE

## Repository

- Project: SnapIMS
- Branch: `feature/v0.10.0-final-preproduction`
- HEAD: `d2b6670` (Phase 0 preservation milestone)
- Upstream: none (branch not yet pushed)
- Started: 2026-07-26T18:59:00-06:00
- Last updated: 2026-07-26T19:18:00-06:00
- Current application version: source/package metadata `0.9.0`; installed editable distribution metadata `0.7.0`
- Inventory schema: 8
- Catalog schema: 1

## Preservation

- Backup root: `/home/isaiah/SnapIMS-backups/v0.10.0-prework-20260726-190242`
- Inventory backup: `databases/inventory.sqlite3`, SHA-256 `c7e98c31c4c4cfe78d22a8c900917588e181057e1dfa3eb70b20e0b10fa68fb0`
- Catalog backup: `databases/movie_catalog.sqlite3`, SHA-256 `a0ab5e86c76c4d4f2df84c2d72a90b255f5f28c4c4cc4677d87b5202d99cdcd0`
- Media manifest: `manifests/media-sha256.jsonl`; 1,306 files; 433,149,821 bytes; media was not duplicated
- Secret/config backup: project `.env`, prior `.env` backup, Cloudflare directory, accessible Guacamole files, and service units copied with owner-only backup permissions. `/etc/guacamole/snapims-admin.env` remains root-only and requires the owner action below.
- Git preservation: `git/repository.bundle`, worktree/index patches, status/log/remote records, and an external copy of the untracked work-order package
- Integrity result: both backups `PRAGMA integrity_check=ok`; zero foreign-key violations
- Restore probe: both backup databases copied to `restore-probe/` and opened successfully at schemas 8 and 1

## Current phase

- Phase: 0 — Baseline, Preservation and Architecture Reconciliation
- Phase file: `docs/codex-work-orders/v0.10.0/02_PHASE_0_BASELINE_AND_PRESERVATION.md`
- Status: BLOCKED
- Latest verified commit: `d2b6670` (`chore: preserve and baseline v0.10.0 work`)
- NEXT_PHASE: `02_PHASE_0_BASELINE_AND_PRESERVATION.md`
- NEXT_ACTION: Owner runs the exact sudo copy under External actions; verify its presence/mode, update this state, commit the Phase 0 exit milestone, then begin Phase 1.

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
- [ ] Back up `/etc/guacamole/snapims-admin.env` using owner-authorized sudo and verify the copied file is owner-only.
- [ ] Capture an installed-wheel smoke test after the baseline build-tool failure is repaired in Phase 1.
- [ ] Create the verified Phase 0 exit commit after the root-only config backup is complete.

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
| `python -m mypy snapims --ignore-missing-imports` | FAIL | `release-evidence/v0.10.0/baseline/mypy.txt` | 19 pre-existing errors |
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
| Copy root-only Guacamole credential into backup | Yes — sudo credential | Blanket command approval received; OS credential unavailable | BLOCKED; run `sudo cp -a /etc/guacamole/snapims-admin.env /home/isaiah/SnapIMS-backups/v0.10.0-prework-20260726-190242/config/guacamole/snapims-admin.env` then `sudo chown isaiah:isaiah /home/isaiah/SnapIMS-backups/v0.10.0-prework-20260726-190242/config/guacamole/snapims-admin.env` and `chmod 600 /home/isaiah/SnapIMS-backups/v0.10.0-prework-20260726-190242/config/guacamole/snapims-admin.env` |

## Known failures

| ID | Severity | Reproduction | Current state | Next action |
|---|---|---|---|---|
| V010-P0-001 | High | `python -m mypy snapims --ignore-missing-imports` | 19 baseline type errors | Repair in first Phase 1 bounded milestone |
| V010-P0-002 | High | `python -m build --no-isolation` | `setuptools.build_meta` unavailable | Restore build dependencies, build, then installed-wheel smoke |
| V010-P0-003 | High | Resolve `desktop.ims.canadavhs.ca` | DNS resolution fails | Treat `remote.canadavhs.ca` as compatibility evidence; owner/infrastructure decision before docs claim official hostname |
| V010-P0-004 | High | Backup root-only Guacamole secret file | `sudo -n` requires a password | Owner runs exact local command above |
| V010-P0-005 | Medium | Compare installed metadata to source | installed metadata 0.7.0; source 0.9.0 | Reinstall verified package after build repair |
| V010-P0-006 | Low | `sha256sum -c SHA256SUMS` in work-order package | All present files match; two reference PDFs and `install_into_repo.sh` are absent | Markdown references are complete and authoritative; do not claim the package has all 26 manifest files |

## Owner decisions

| Decision | Choice | Date | Consequence |
|---|---|---|---|
| Tool/command approvals | Owner approved all remaining commands | 2026-07-26 | No further tool-level confirmation is needed, but approval cannot supply the host's interactive sudo password |
| Root-only Guacamole backup | Pending local sudo credential | — | Phase 0 cannot claim a complete secret/config restore point until copied |
| Official vs compatibility Guacamole hostname | Pending | — | Current evidence supports only `remote.canadavhs.ca` |

## Files/areas currently being edited

- `V010_IMPLEMENTATION_STATE.md`
- `release-evidence/v0.10.0/baseline/`
- `docs/codex-work-orders/v0.10.0/` (preserved owner-provided work-order package)

## Resume checklist

1. Verify branch and HEAD.
2. Verify working tree.
3. Verify latest phase commit.
4. Run focused tests.
5. Read current phase acceptance criteria.
6. Continue first incomplete item.
