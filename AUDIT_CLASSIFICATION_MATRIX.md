# SnapIMS 0.6.1 Audit Classification Matrix

Baseline: `feature/v0.6.0-operator-workstation` at `5c316ca`  
Stabilization branch: `fix/v0.6.1-mega-stabilization`

The pre-implementation classification terms required by the work order are retained below. "Fixed" means the defect was reproduced or structurally confirmed, repaired, and covered by automated or browser evidence. Deferred items remain unchanged and are not represented as closed.

| ID | Initial classification | Final disposition | Evidence / scope |
|---|---|---|---|
| O-01 | REPRODUCED - WILL FIX | Fixed | Mock/test providers hidden by default, rejected server-side, provenance retained, production publish blocked. |
| O-02 | REPRODUCED - WILL FIX | Fixed | Suggested and saved titles/prices are separate in queries, Review, Batch Editor, CSV, and Publish. |
| O-03 | REPRODUCED - WILL FIX | Fixed | Home dictionary-key collision fixed; browser and regression test reject Python method output. |
| O-04 | REPRODUCED - WILL FIX | Fixed | Unfinished recognized items expose latest suggestion confidence; accepted/manual states remain distinct. |
| O-05 | REPRODUCED - WILL FIX | Fixed | Missing credentials are BLOCKED, with direct manual review and minimum required fields. |
| O-06 | DEFERRED - ARCHITECTURAL OR OUTSIDE THIS PASS | Deferred | Deep per-photo import sequence inspector is a separate Import usability feature. Existing preview/count safety retained. |
| O-07 | REPRODUCED - WILL FIX | Fixed | Bulk operations and Save All return exact changed/unchanged/failed results; failed cells remain dirty. |
| O-08 | DEFERRED - ARCHITECTURAL OR OUTSIDE THIS PASS | Deferred | Full 5,000-row virtualized editor remains a scale architecture project. |
| O-09 | REPRODUCED - WILL FIX | Fixed | Throughput and image metrics use meaningful timestamps and measured categories. |
| O-10 | REPRODUCED - WILL FIX | Fixed | Unmeasured API cost is not invented; payload and bandwidth claims are based on recorded bytes. |
| O-11 | REPRODUCED - WILL FIX | Fixed | Routine screens emphasize Configure, Retry, Continue manually, and Diagnostics actions. |
| O-12 | REPRODUCED - WILL FIX | Fixed | Review editor grouped into Required, Common optional, Advanced, and provenance/recovery sections. |
| O-13 | REPRODUCED - WILL FIX | Fixed | Command palette hides context-inapplicable actions and advertises only wired commands. |
| O-14 | REPRODUCED - WILL FIX | Fixed | Bulk workflow uses one in-app confirmation model; duplicate native confirmation removed. |
| O-15 | DUPLICATE - COVERED BY ANOTHER FIX | Fixed with O-02/E-07 | Provenance badges and working-value source remain visible throughout the operator flow. |
| E-01 | REPRODUCED - WILL FIX | Fixed | Runtime test-provider gate, forged-request rejection, diagnostics contamination count, Shopify guard. |
| E-02 | REPRODUCED - WILL FIX | Fixed | CSV apply validates first, checkpoints and audits in one transaction, and rolls back fully on injection. |
| E-03 | REPRODUCED - WILL FIX | Fixed | Bulk actions validate all selected rows, use one transaction and idempotent request IDs. |
| E-04 | REPRODUCED - WILL FIX | Fixed | External review is all-or-nothing and only marks REVIEW_COMPLETE after commit. |
| E-05 | REPRODUCED - WILL FIX | Fixed | Durable import journal, same-filesystem staging/rename, startup reconciliation, orphan quarantine. |
| E-06 | REPRODUCED - WILL FIX | Fixed | Restore validates batch/item set, creates a protected safety checkpoint, and writes field audit events. |
| E-07 | REPRODUCED - WILL FIX | Fixed | SUGGESTED, SAVED, REVIEWED and DRAFTED/PUBLISHED state remain separate. |
| E-08 | REPRODUCED - WILL FIX | Fixed | Latest suggestion confidence is separate from accepted/manual confidence. |
| E-09 | DEFERRED - ARCHITECTURAL OR OUTSIDE THIS PASS | Deferred | Row virtualization and viewport rendering remain a future warehouse-scale work package. |
| E-10 | REPRODUCED - WILL FIX | Fixed | Item list query joins latest recognition and photo summary, eliminating the principal N+1 path. |
| E-11 | DEFERRED - ARCHITECTURAL OR OUTSIDE THIS PASS | Deferred | QR candidate prefilter and 10,000-photo importer redesign remain outside a patch release. |
| E-12 | REPRODUCED - WILL FIX | Fixed | Browser listeners attach before first navigation; screenshots, trace, logs and request results retained. |
| E-13 | REPRODUCED - WILL FIX | Fixed in source / CI required | Current source was cleaned and history scripts deliberately excluded. GitHub CI is the authoritative Ruff/mypy environment when local package index is unavailable. |
| E-14 | REPRODUCED - WILL FIX | Fixed | Durable recognition vocabulary standardized, including BLOCKED, SKIPPED and COMPLETE_WITH_FAILURES. |
| E-15 | REPRODUCED - WILL FIX | Fixed | Diagnostics report schema, storage, WAL, stages, checkpoints, imports, provenance and recent failures. |
| E-16 | DEFERRED - ARCHITECTURAL OR OUTSIDE THIS PASS | Deferred | Current image selection is described truthfully; genuine adaptive recognition remains future work. |
| E-17 | REPRODUCED - WILL FIX | Fixed | Schema manifest verifies tables, columns, indexes, unique constraints and foreign keys; current broken schemas fail closed. |
| E-18 | DEFERRED - ARCHITECTURAL OR OUTSIDE THIS PASS | Deferred | Authentication, roles, CSRF, batch claims and multi-user remote safety require a security release. |
| E-19 | REPRODUCED - WILL FIX | Fixed | Staging lifecycle, upload/row limits, expiry, protected checkpoints and rollback identity added. |
| E-20 | REPRODUCED - WILL FIX | Fixed | Decimal/integer-cent policy shared by Review, Batch Editor, CSV, bulk and Shopify payloads. |
| E-21 | REPRODUCED - WILL FIX | Fixed | Save All aggregates confirmed row outcomes instead of displaying unconditional success. |
| E-22 | REPRODUCED - WILL FIX | Fixed | Checkpoint and CSV-stage retention plus WAL/storage diagnostics added; no active-operation VACUUM. |
| E-23 | DEFERRED - ARCHITECTURAL OR OUTSIDE THIS PASS | Deferred | Near-duplicate classification and pooling intelligence are not patch-level repairs. |
| E-24 | NOT REPRODUCIBLE - EVIDENCE RECORDED | Deferred monitor | No image-lifetime loss reproduced. Originals and durable media linkage passed tests and restart audit. |
| E-25 | REPRODUCED - WILL FIX | Fixed | Full-batch retry and failed-only retry now have distinct candidate scopes and labels. |
| E-26 | REPRODUCED - WILL FIX | Fixed | Pre-attempt configuration errors are BLOCKED/NOT ATTEMPTED rather than false recognition failures. |
| E-27 | REPRODUCED - WILL FIX | Fixed | Browser keyboard path, command palette, favicon, CSV diff, restart and console gates verified. |
| E-28 | DEFERRED - ARCHITECTURAL OR OUTSIDE THIS PASS | Deferred | 20-item browser fixture and 500-item regression are supported; a real 5,000-item warehouse acceptance remains unproven. |
