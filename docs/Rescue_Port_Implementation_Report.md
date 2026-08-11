# SnapIMS v0.16.0 Rescue Port — Implementation Report

## Objective
Recover the requested operator-first v0.16 functionality from the failed donor implementation without repeating its primary defect: replacing mature SnapIMS v0.15 subsystems with a simplified reconstructed application.

## Authoritative base identified
- repository: `fachingo/SnapIMS`
- authoritative observed commit: `5c790dce8cedc45e6495a36a0778cef46632e6cf`
- observed package/application version: `0.15.0`
- release class: minor → target `0.16.0`

The rescue installer verifies mature source anchors and refuses the simplified donor source tree.

## Port strategy
The deliverable is a surgical port transformer plus isolated new modules/assets/tests. It does **not** ship a second replacement application.

New isolated modules:
- approved tag taxonomy/seeding;
- operator Recognition Review semantics;
- conservative database-first pricing;
- exact/canonical title intelligence;
- advisory inventory-commit lifecycle;
- logical Data Sources diagnostics;
- contextual Help Registry and semantic fallback.

Additive UI assets/templates:
- Item Search;
- Data Sources;
- Commit to Inventory;
- operator-first CSS/JS.

Surgical mature-file edits:
- Recognition provider policy: remove AI price, hard-limit approved tag IDs;
- base navigation/palette/help integration;
- normal Recognition Review form/actions only;
- Batch Editor price-cell augmentation only;
- Pricing Review label/layout only;
- Settings progressive disclosure only;
- Publish explicit incomplete-attempt affordance only;
- Shopify jobs/service/client option propagation only;
- web app route/integration wiring.

## Preservation protections
The installer rejects source trees that do not contain the mature v0.15 Import, Recognition, Batch Editor, Publish, Shopify and test anchors. Before modifying mature files it creates timestamped backups. Every patch operation expects a unique known source anchor and aborts rather than guessing when the source differs.

The failed donor is explicitly rejected by automated rescue-patcher tests.

## Correctness fixes made during rescue QA
1. Initial broad Review-template transformation was found to remove advanced/catalog content. The test failed and the transformation was rewritten to replace only the normal quick-review form/actions. Exception Editor, catalog candidates and advanced recognition history remain.
2. Commit-to-Inventory initially risked nested SQLite lock/deadlock behavior. Warnings are now computed before the write transaction; commit is idempotent.
3. Title intelligence initially performed Python-wide inventory scans/N+1 movie-link lookups. It now uses bounded SQL discovery and exact/canonical identity queries; a 20,000-record fixture completes the exact-title test in roughly a fraction of a second in the sandbox.
4. Database-first pricing now excludes legacy AI/recognition-sourced prices so old placeholder `$9.99` values cannot seed trusted pricing.
5. Unknown current edition versus a specifically identified prior special edition is now guidance only, not an automatic price match.
6. Recognition Review no longer rewrites the unrelated item `working_source` field, preserving existing price/source provenance.
7. Contextual help no longer uses blanket exemption flags; unregistered controls receive centralized semantic fallback help.
8. Shopify incomplete override bypasses only internal completeness simulation. Configuration, deliberate write confirmation, media/inventory pipeline and external API rules remain.

## Local test evidence
Environment used for rescue-kit QA:
- Python 3.13.5 (satisfies project Python >=3.12 requirement)
- Node available for JavaScript syntax check

Latest isolated test run:
- **24 passed** (`tests/test_operator_first_modules.py` + `tests/test_rescue_patcher.py`)
- Python compile checks passed for installer/operator modules/target test payload
- Node syntax check passed for `operator_first.js`
- 20,000-record exact-title intelligence regression test passed; latest measured pytest call duration approximately 0.27 s in this sandbox.

These are **REAL LOCAL TESTS of the rescue implementation and transformer**, not a claim that the entire upstream application has already passed after transformation.

## Integrated verification limitation
The execution sandbox had read access to the authoritative GitHub source through the repository connector but did not expose a complete writable upstream checkout to the local container; shell source download was unavailable. Therefore the full upstream test suite and final browser screenshots could not truthfully be executed against an integrated v0.15-derived tree here.

This did not stop implementation. The deliverable is an application-ready surgical port kit that must be run against the authoritative working tree. It contains target regression tests, a post-port validator, a full preservation matrix, and the browser walk-through required before release promotion.

## Release status
**IMPLEMENTED AS RESCUE PORT KIT / NOT YET LIVE-RELEASE VERIFIED.**

Do not deploy to production data until:
1. installer `--dry-run` passes on the real checkout;
2. port is applied to a branch/copy;
3. full upstream pytest passes;
4. post-port validator passes;
5. browser walk-through and screenshots pass;
6. live API acceptance requirements are separately performed where required.
