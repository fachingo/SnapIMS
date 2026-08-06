# SnapIMS v0.15.0 Issue Traceability

| ID | Severity | Finding | Final status | Implementation / evidence |
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

| QA-0150-001 | High | Modern Dev Dashboard apps did not expose the static token required by Settings | Fixed | Added Client ID/Client Secret configuration and automatic client-credentials token exchange. |
| QA-0150-002 | High | Short-lived Shopify tokens required daily manual replacement | Fixed | Added encrypted restart-safe cache, proactive refresh, and one bounded 401 refresh/retry. |
| QA-0150-003 | High | Shopify secrets and generated tokens needed stronger at-rest handling | Fixed | Added Fernet-encrypted secret and token stores with owner-only key/file permissions and plaintext migration. |
| QA-0150-004 | Medium | Duplicate token fields and raw Location GID entry made Settings confusing | Fixed | Replaced the forms with one guided workflow and named location selection. |
| QA-0150-005 | Medium | Missing scopes and authentication failures were not clearly distinguished | Fixed | Added one authoritative minimum-scope declaration and actionable probe/status diagnostics. |
| QA-0150-006 | Medium | Concurrent requests could create a token-refresh storm | Fixed | Added thread and filesystem locks plus cache re-check after lock acquisition. |
| QA-0150-007 | Medium | Credential replacement/removal could leave stale cached access | Fixed | Credential fingerprint invalidation and authenticated removal clear generated tokens without deleting inventory or linkage history. |
| QA-0150-008 | Low | Existing static tokens required a safe transition path | Fixed | Preserved deprecated legacy fallback until the operator verifies and removes it. |

## Source comparison

The supplied remediation sheet was used as the required baseline. Every QA-0130 issue was reproduced or directly traced to source/evidence, fixed, and covered by automated or browser verification. Additional findings were recorded separately rather than silently folded into the original issue IDs.

## v0.15.0 publish-workflow findings

| ID | Severity | Finding | Final status | Implementation / evidence |
| --- | --- | --- | --- | --- |
| QA-0150-009 | Critical | Publish ended at simulation and never called `ShopifyService.upload_draft()` | Fixed | Durable Create Drafts POST workflow, job runner, progress page, Shopify GID persistence, and browser evidence. |
| QA-0150-010 | High | No safe batch live-publish action | Fixed | Draft-first live publication to the selected Shopify publication; exact `SUBMIT` confirmation. |
| QA-0150-011 | High | No deliberate direct-live override | Fixed | Direct-live path requires exact `SUBMIT LIVE`; draft-first remains the default. |
| QA-0150-012 | High | Refresh/restart could duplicate Shopify work | Fixed | Schema-16 durable jobs and item stages, completed-row skipping, SKU/GID reconciliation, and bounded retry. |
| QA-0150-013 | High | Shopify product lifecycle could not be managed from SnapIMS | Fixed | Selected/batch sync, reconcile, archive, restore draft, irreversible delete, Keep Shopify, and merge actions. |
| QA-0150-014 | Medium | Live publication destination was not selectable | Fixed | Publication discovery and named selection with `read_publications`/`write_publications` validation. |
| QA-0150-015 | Medium | No durable progress or actionable item result display | Fixed | Progress, elapsed time, ETA, retry/failure details, Shopify links, and GID copy controls. |
| QA-0150-016 | Medium | Batch lifecycle controls were incomplete | Fixed | Rename, duplicate, archive, restore, export/CSV, history, and guarded batch management controls. |
| QA-0150-017 | Medium | CLI and browser could resolve different Shopify configuration contexts | Fixed | Aligned project/data resolution and added `snapims shopify status/test/refresh/jobs`. |
