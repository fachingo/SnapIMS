# SnapIMS v0.13.2 Release Notes

**Release date:** August 4, 2026  
**Release type:** Patch release (`0.13.1 → 0.13.2`)  
**Production status:** Pilot-ready; not approved as v1.0.0

## Scope

v0.13.2 remediates the v0.13.0 stress-audit findings and additional defects found while running the complete application locally. It does not introduce a new operator workflow. The folder-based NEXT ITEM Import protocol remains unchanged.

## Fixed issues

| ID | Severity | Finding | Status | Resolution |
| --- | --- | --- | --- | --- |
| QA-0130-001 | Critical | SQLite/file-descriptor leak | Fixed | Explicit closing SQLite connection classes, serialized initialization, and resource regression coverage. Full one-process suite ended with 0 SQLite descriptors. |
| QA-0130-002 | High | Duplicate same-folder Import race | Fixed | Canonical-folder active-job uniqueness, existing-job reuse, idempotent Commit, and unique per-job staging. |
| QA-0130-003 | High | Launcher could start obsolete source | Fixed | Pinned launcher and user service are rewritten by installer; status prints project, venv executable, data path, PID, version, and schema. |
| QA-0130-004 | High | Batch Editor rendered all items | Fixed | Bounded server-side paging with 20–200 rows; 5,000-item page rendered 100 rows and 430,721 bytes. |
| QA-0130-005 | Medium | Fill Down unsupported for Tags | Fixed | Atomic exact set/replace of validated Tag IDs with auditing. |
| QA-0130-006 | Medium | Location Fill Down used stale shelf key | Fixed | Location mapping, nullable None handling, arbitrary free text, and location-history events. |
| QA-0130-007 | Medium | Fill Down unsupported for Review/Rare | Fixed | Atomic exact boolean propagation in both directions. |
| QA-0130-008 | Medium | Horizontal navigation stuck at Tags | Fixed | ArrowLeft/ArrowRight use the tag input focus path. |
| QA-0130-009 | Medium | Hidden selected rows remained armed | Fixed | Selections are cleared as rows become hidden; bulk actions only read visible selected rows. |
| QA-0130-010 | Low | Shelf-only wording | Fixed | Current UI and guides use location/unassigned terminology. |
| QA-0132-011 | Medium | Individual Rare edit silently discarded | Fixed | rare added to the editable-field contract with regression coverage. |
| QA-0132-012 | High | Publish page dry-ran every item | Fixed | Publish summary uses aggregate SQL; dry-run is opt-in and bounded to the current page. |
| QA-0132-013 | Low | Doctor falsely failed in an active external venv | Fixed | Doctor accepts either the project venv or an active Python virtual environment. |
| QA-0132-014 | Low | CSRF URL resolution depended on window location | Fixed | Same-origin checks resolve against document.baseURI, preserving reverse-proxy and verification behavior. |

## Verification summary

- Complete suite: **273 passed, 3 skipped, 0 failed** in one Python process.
- File descriptors: baseline **3**, peak **166**, final **7**; final SQLite descriptors **0**.
- Browser checks: **33/33 passed** in Chromium using real SnapIMS HTML/JavaScript and relayed localhost HTTP because the sandbox browser policy blocked direct localhost navigation.
- Clean install, schema-15 migration, wheel installation, two server starts, and stale-launcher rewrite passed.

## Compatibility

Existing v0.12.3 and v0.13.0 databases are migrated forward to schema 15. Operator data, immutable IDs, image paths, history, settings, credentials, and logs are preserved. A pre-migration backup is created under the SnapIMS data backup directory.

## Known external verification gaps

See `SKIPPED_EXTERNAL_TESTS.md` and `V1_PRODUCTION_ACCEPTANCE_GAPS.md`. Live OpenAI, live Shopify, target Mac hardware, native Firefox, and owner infrastructure were not available in this sandbox.
