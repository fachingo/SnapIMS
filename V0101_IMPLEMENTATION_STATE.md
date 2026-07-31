# V0101_IMPLEMENTATION_STATE

## Repository baseline

- Repository: `fachingo/SnapIMS`
- Accepted v0.9.0 baseline: `bda7093d8ca9b776b2e881ce38a09f10b222f56f`
- Audited v0.10.0 branch: `feature/v0.10.0-final-preproduction`
- Audited v0.10.0 HEAD: `89a60b5c359803e33ba9e442ca2d27883305b2a9`
- Starting application version: `0.10.0`
- Target application version: `0.10.1`
- Starting inventory code schema: `12`
- Target inventory code schema: `13`
- Catalog schema: unchanged
- Release classification: patch

## Artifact-workspace boundary

This remediation was reconstructed in an offline artifact workspace from connected
repository source and the v0.10.0 QA audit. The artifact workspace did not contain
the live production database, complete installed environment, or host browsers.
Host-level test and migration fields below must be filled by
`scripts/verify_v0101.py` and the targeted browser walkthrough.

## Preservation

The patch transformer:

- refuses a Git HEAD other than the audited commit unless explicitly overridden;
- verifies audited Git blob identities for high-risk changed files;
- creates `.snapims-v0101-backup/<timestamp>/` before replacing or deleting files;
- never reads, copies, deletes, or rebuilds inventory/media data;
- relies on the existing database migration backup and rollback path for schema 13.

## Audit disposition

| ID | Classification | Action in v0.10.1 | Status before host verification |
|---|---|---|---|
| QA-001 | B — release-state defect | Correct active history and bump only to 0.10.1 | Implemented in package |
| QA-002 | B — documentation defect | Replace obsolete active guide with patch-level current guide | Implemented; screenshots pending host browser |
| QA-003 | B — documentation defect | Rewrite release notes to actual v0.10/v0.10.1 scope | Implemented |
| QA-004 | B — evidence drift | Create this v0.10.1 state file and verification outputs | Implemented; final SHA pending |
| QA-005 | A — v0.10 schema/release mismatch | Schema 13 migration with existing backup/integrity/FK/restore guarantees | Implemented; production migration pending owner host |
| QA-006 | D — final browser acceptance gate | Run targeted changed-workflow matrix only; full v1.0 matrix deferred | Targeted script supplied |
| QA-007 | D — v1.0 acceptance gate | No patch implementation | Deferred to v1.0 |
| QA-008 | E — future minor Publish workflow | Keep simulation-only UI; no live Draft button | Deferred |
| QA-009 | A — direct recognition regression | Preserve valid baseline when escalation/later route fails | Implemented |
| QA-010 | A — direct review regression | Quick Approve revision contract and stale conflict | Implemented |
| QA-011 | A — direct recognition regression | Preserve operator Price/Discount on metadata acceptance | Implemented |
| QA-012 | A — direct Batch Editor regression | Serialize saves per Item; latest acknowledged value wins | Implemented |
| QA-013 | A — direct recognition regression | Database-backed Item recognition lease shared by both paths | Implemented |
| QA-014 | A — v0.10 security regression | Always enforce Origin/CSRF; auth-disabled is local-only | Implemented |
| QA-015 | C — pre-existing/conditional | No new Import contract in this patch | Deferred with explicit record |
| QA-016 | C — pre-existing/conditional | No broad Import scan redesign | Deferred |
| QA-017 | C/E — mixed performance architecture | No new background Import workflow; provider offload requires separate bounded follow-up | Deferred |
| QA-018 | E/D — future scale architecture/gate | No pagination/virtualization redesign | Deferred |
| QA-019 | C — pre-existing performance issue | No broad Review query rewrite | Deferred |
| QA-020 | A — direct Phase-4 inconsistency | Retry uses durable queued router | Implemented |
| QA-021 | A — v0.10 reporting defect | Independent aggregate SQL and explicit benchmark attempt basis | Implemented |
| QA-022 | A — v0.10 polling defect | Visibility-aware polling and exponential backoff | Implemented |
| QA-023 | A — workflow regression | Advance to next unfinished physical sequence | Implemented |
| QA-024 | A — v0.10 UI defect | Typed error route for repaired retry paths and error alert support | Implemented; remaining routes audited by verifier |
| QA-025 | A/C — v0.10 route disclosure plus legacy debt | Safe summaries for changed v0.10 routes; broad legacy cleanup deferred | Partially implemented by bounded scope |
| QA-026 | A — v0.10 accessibility defect | Focus-visible and combobox/listbox state | Implemented |
| QA-027 | A/C — v0.10 narrow-surface regression | Add scroll affordance and sticky identity column; no redesign | Implemented bounded fix |
| QA-028 | A — v0.10 Shopify retry defect | Per-photo stable identity reconciliation | Implemented |
| QA-029 | A — test gap | Add focused service, schema, security, source, and Shopify tests | Implemented; execution pending host |
| QA-030 | B — repository hygiene defect | Delete stray file and add hygiene verification | Implemented |

## Required host verification

- [ ] Apply transformer to audited source tree.
- [ ] Record local Git status and generated backup location.
- [ ] Run focused v0.10.1 tests.
- [ ] Run full pytest.
- [ ] Run Ruff, mypy, compileall, JS syntax, build, wheel smoke, and pip check.
- [ ] Verify schema 12 → 13 on a disposable production backup.
- [ ] Verify integrity, foreign keys, manifest, and preserved row counts.
- [ ] Restart and verify paused recognition lease recovery.
- [ ] Complete targeted Chromium, Firefox, and Edge checks where installed.
- [ ] Update screenshots in active guide if UI screenshots are retained.
- [ ] Record final branch and SHA.

## Current conclusion

`v0.10.1 PATCH BLOCKED` until the package is applied to the complete repository and
the included host verification completes. The block is verification availability,
not a requirement to complete the deferred v1.0 gates.
