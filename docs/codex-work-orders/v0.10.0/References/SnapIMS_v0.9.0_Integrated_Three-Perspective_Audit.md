---
title: "SnapIMS v0.10.0 Integrated Three-Perspective Audit"
subtitle: "Source audit, operator audit, owner-perspective audit, and pre-1.0 defect register"
author: "Prepared for Canada VHS"
date: "July 26, 2026"
lang: en-CA
mainfont: "DejaVu Sans"
monofont: "DejaVu Sans Mono"
fontsize: 10pt
geometry: margin=0.72in
colorlinks: true
toc: true
toc-depth: 3
---

# Executive verdict

SnapIMS has crossed an important boundary: the core idea is no longer hypothetical. The live Linux Mint workstation can now cold boot, start the complete stack through `snapims up`, expose authenticated SnapIMS and Guacamole endpoints through Cloudflare Tunnel, and report every current infrastructure check as PASS. The repository also contains unusually strong foundations for a pre-1.0 single-operator application: immutable physical Item identity, duplicate-import prevention, transactional bulk and CSV operations, optimistic record revisions, restart-aware recognition and catalog jobs, local catalog provenance, Shopify draft-only safeguards, and detailed diagnostics.

The product is nevertheless **not ready for 1.0.0**. The largest remaining risks are no longer infrastructure. They are operational completeness and truthfulness:

- no global inventory search or item retrieval workspace;
- no Shopify order ingestion, reservation, pick ticket, or fulfillment workflow;
- no operator-controlled re-recognition of a successfully recognized item;
- no staged baseline/escalation/frontier recognition router;
- Settings cannot configure API credentials, recognition models, Shopify, or metadata providers;
- runtime logging is too narrow to explain what the system is doing;
- the active branch still contains documentation and UI claims that contradict the actual implementation;
- the Shopify inventory idempotency key is stored locally but is not passed to the live mutation;
- current authentication lacks CSRF protection and login abuse controls;
- current health and tunnel checks can report PASS or RUNNING without proving the public service is healthy;
- the current Batch Editor remains a full-DOM, client-filtered design and does not prove large-scale readiness.

The recommended conclusion is:

> Accept the v0.10.0 infrastructure milestone as a successful, cold-boot-verified foundation. Do not label the product 1.0.0. Perform one bounded stabilization pass, then implement a final pre-1.0 minor release, proposed as v0.10.0, containing observability, operator configuration, recognition controls, inventory search, rights-respecting catalog completion, and Shopify order picking.

# 1. Audit scope and evidence standard

## 1.1 Repository target

- Repository: `fachingo/SnapIMS`
- Audited branch: `feature/v0.9-infrastructure`
- Audited commit: `bda7093d8ca9b776b2e881ce38a09f10b222f56f`
- Application version: `0.10.0`
- Audit date: July 26, 2026

## 1.2 Methods used

This audit combines four evidence streams:

1. **Direct source inspection** through the GitHub connector at the audited commit.
2. **Owner live-host evidence** from the Linux Mint production candidate, including cold boot, `snapims up`, `snapims status`, `snapims doctor`, external Cloudflare access, Guacamole desktop, and browser SSH.
3. **Existing planning and verification documents**, including the v0.10.0 Production Candidate Update, the v0.8.0 Status Update, and the Master Scope of Work and Implementation Plan.
4. **Three deliberately different review perspectives**:
   - technical/AI systems auditor;
   - first-time inventory operator;
   - owner-perspective audit modelled on Isaiah's actual priorities and work style.

## 1.3 Important execution limitation

A complete repository clone and isolated runtime execution were attempted, but the document-generation environment could not resolve or download the GitHub archive. The available GitHub connector supports direct file and commit inspection but does not expose a complete repository archive or filesystem checkout. Therefore:

- source-code findings in this report are independently inspected;
- cold-boot and browser findings are based on the owner's real host evidence;
- the assistant did **not** independently execute the full pytest suite or launch an isolated full SnapIMS runtime in this environment;
- claims that require a clean clone, production database, live OpenAI, live Shopify, or physical tapes remain explicitly unverified.

This limitation is material and is preserved rather than hidden.

## 1.4 Evidence classifications

| Classification | Meaning |
|---|---|
| Source-confirmed | Directly visible in the audited GitHub branch. |
| Live-host verified | Demonstrated by the owner on the actual Linux Mint host. |
| Document-claimed | Claimed by an existing report but not re-proven in this audit. |
| Pending | Requires a future controlled test or implementation. |

# 2. Current baseline

## 2.1 Live-host verified strengths

The following were demonstrated on the actual host after a cold boot:

- global `snapims` command works from the home directory;
- `snapims up` starts SnapIMS, Cloudflare Tunnel, Guacamole, `guacd`, Tomcat, and XRDP;
- `snapims status` reports the entire stack as RUNNING or PASS;
- `snapims doctor` reports all configured infrastructure checks as PASS;
- SnapIMS authentication is enabled and works through the public hostname;
- Guacamole authentication works;
- the Linux desktop works in the browser;
- the browser SSH terminal works;
- remote access works from a phone outside the local network;
- no router port forwarding is required.

This completes most of the former v0.10.0 infrastructure acceptance scope.

## 2.2 Source-confirmed product strengths

### Durable physical identity and change history

The source separates physical Item identity from recognition output and records changes with revisions, source, reason, and location events. Shelf changes require a reason. Optimistic revisions reject stale writes. This is a strong ERP-like foundation.

### Duplicate import protection

Import preview checks a source fingerprint. Re-importing an existing batch opens the existing durable batch instead of creating duplicate inventory. The owner independently observed this behaviour and correctly identified it as strong failure control.

### Recognition and catalog provenance

Recognition attempts are stored as separate rows with provider, model, confidence, token counts, image counts, uncertainty, source kind, and raw response reference. The catalog is a separate SQLite database with local matching, aliases, source records, retrieval timestamps, revision IDs, parser version, and attribution fields.

### Transaction and recovery design

CSV changes are staged before apply. Bulk operations use request IDs and checkpoints. Import journals, catalog jobs, recognition jobs, and Shopify sync checkpoints provide a meaningful recovery base.

### Draft-only Shopify boundary

The outbound Shopify service blocks unconfirmed writes, enforces draft-only configuration, checks SKU collisions, creates a local database backup before upload, and checkpoints product, variant, inventory, and media stages.

# 3. Perspective A - Technical and AI systems audit

## 3.1 Overall assessment

The system is modular and recoverable enough to continue development without a rewrite. The major issue is contract drift: several documents claim capabilities that the current source either does not implement or implements differently. Before adding a large schema expansion, the application needs a truth-reconciliation pass so tests, UI text, documentation, and code describe the same product.

## 3.2 AI recognition findings

The active live recognizer is OpenAI. Gemini appears in the provider registry but is intentionally disabled. The model is selected through `SNAPIMS_OPENAI_MODEL`; there is no in-app model selector. The recognition schema supports title, edition, distributor, year, barcodes, price, discount, confidence, uncertainty, and review requirement. It does not include the approved Tag IDs claimed in older v0.8.0 documents.

The batch worker treats any item with an existing recognition result as complete and skips it. Retry scopes only reprocess FAILED, BLOCKED, or SKIPPED items. A successful item therefore cannot be manually re-run through the current Review UI. Recognition history is stored, which makes a correct force-rerun feature straightforward, but the operator workflow is missing.

There is no measured staged router in the active source. One model is selected from the environment and applied. Confidence is stored, but it is not presently used to route a baseline result into an escalation or frontier model.

## 3.3 Catalog findings

The local catalog is substantial and should be preserved. It supports exact/alias/FTS matching, candidate scoring, durable Movie creation, provenance, aliases, director/genre/country/language data, and separate catalog events.

The external discovery path remains coupled directly to the Wikipedia client. The provider-neutral candidate-resolution boundary described in the v0.10.0 plan is not yet complete. The roadmap should add that boundary before another provider is selected so SnapIMS can use an approved API without copying its entire database or making provider IDs into local identity.

## 3.4 Shopify findings

The outbound draft workflow has good local checkpoints, but there are two serious gaps:

1. The deterministic inventory idempotency key is generated and saved **after** the `inventoryActivate` call; the client mutation does not pass it to Shopify. This contradicts the v0.8.0 claim that inventory activation idempotency was complete.
2. The inspected Publish UI exposes simulation and CSV tools but does not expose a route or deliberate button for the existing `upload_draft()` service. The live draft workflow is therefore not operator-complete in the inspected branch.

There is no inbound orders client, webhook/polling job, order table, reservation table, pick queue, or fulfillment state machine.

## 3.5 Security findings

The application login cookie is HTTP-only, secure behind forwarded HTTPS, SameSite Lax, and time-limited. These are good controls.

However, authenticated state-changing routes use cookie authentication without CSRF tokens or explicit Origin validation. There is also no login throttling, failed-login audit trail, lockout/backoff, session revocation list, or administrator password-change workflow in the application. Because the public application and Guacamole share the same registrable domain, same-site attacks from another compromised subdomain should be considered.

Secrets are loaded from `.env`. The current Settings page cannot safely write, mask, test, rotate, or audit those credentials.

## 3.6 Observability and health findings

`snapims logs` follows only the application log. It has no singular alias, no filters, no JSON/structured mode, no recognition correlation ID, no Shopify step filter, no catalog filter, no tunnel/system logs, and no redaction test. The in-app Diagnostics page shows durable records but not a live operational event stream.

A safe observability design must expose **events, evidence, decisions, requests, retries, and outcomes**, not hidden chain-of-thought. The correct feature is an operational trace, not raw private model reasoning.

The local `/health` endpoint returns HTTP 200 even when the schema status is `degraded`; the service manager treats any HTTP 200 as healthy. Cloudflare status is primarily PID/config based, not a public-route probe. Guacamole health accepts broad HTML conditions. These can produce false-positive PASS states.

## 3.7 Deployment and update findings

The new orchestration worked on the actual host, which is the strongest infrastructure evidence. However, `snapims update` performs `git pull` directly, then restarts services without first checking the current branch, dirty working tree, migration backup, upstream relationship, or rollback point. This is unsafe for a production workstation.

# 4. Perspective B - First-time operator audit

## 4.1 What feels strong

- The application presents a clear batch-centred workflow.
- Duplicate source detection protects the operator from accidental double import.
- Review keeps the routine path focused on Title, Price, Discount, and Approve & Next.
- Recognition confidence and catalog state are visible.
- CSV changes are staged and previewed.
- Batch Editor gives visible save state, undo/redo, checkpoints, and failure messages.
- Diagnostics provides real database and job state instead of generic green lights.

## 4.2 What blocks routine operation

### There is no "find this tape" workflow

The only search is inside the current Batch Editor page and operates on rows already rendered in that batch. Once inventory spans many batches, an operator cannot search the whole inventory by title, Item ID, SKU, barcode, Shopify ID, or shelf and immediately open the physical Item.

### There is no order-picking workspace

After a sale, SnapIMS cannot show a queue of ordered physical Items and their locations. There is no Reserved, Picked, Packed, Fulfilled, Cancelled, Missing, or Substitution Required workflow.

### Recognition controls disappear after success

A successful result cannot be re-run from Review. The operator cannot compare models, force escalation, or correct a suspicious high-confidence result while preserving prior attempts.

### Settings is not an operator settings page

The current page only configures the incoming folder and displays provider availability. It does not configure OpenAI, models, confidence thresholds, Shopify, metadata provider, public URLs, or connection tests.

### Duplicate handling is safe but too rigid

The default is correct: open the existing batch. The operator still needs deliberate alternatives for test work: re-run unfinished, re-run all, or create a quarantined comparison copy.

### Runtime activity is hidden

When recognition, catalog lookup, image upload, or a background job takes time, the operator does not have a single live view showing what is active, what was sent, which model/provider was used, why a retry occurred, and what failed.

## 4.3 Operator-facing contradictions

The current source and active documents disagree:

- the UI still advertises Ctrl+Shift+P/Ctrl+K for the command palette, not the claimed Alt+P;
- Batch Editor still advertises and implements Ctrl+1-9, despite real Firefox conflicts and older claims that Alt+1-9 replaced them;
- prior status documents claim a first-class Tags field, but the inspected quick Review and Batch Editor do not show that contract;
- Production Readiness and Test Results still identify v0.7.0 as current while the application is v0.10.0.

For a first-time operator, this is a trust problem even when the underlying code is stable.

# 5. Perspective C - Owner/Isaiah audit

This perspective applies the owner's demonstrated priorities: speed, directness, remote control, strong failure containment, minimal repeated work, and the ability to make the system do more than a conventional inventory application.

## 5.1 What the owner would value

- One command now starts the complete stack from anywhere.
- The system prevents duplicate imports without silently creating new inventory.
- The browser desktop and SSH terminal make the workstation remotely controllable.
- Recognition evidence and stored history make model experimentation possible.
- Local catalog reuse can make the second copy cheaper and faster than the first.
- Immutable Items and location history are the correct base for an actual warehouse workflow.

## 5.2 What would immediately become irritating

- not being able to search all tapes and pull one by bin location;
- needing `.env` and terminal edits to set models, keys, Shopify, or providers;
- being prevented from re-running AI because the program decided an item was already complete;
- not seeing a live stream of what recognition/catalog/Shopify is doing;
- not being able to compare a cheap model and stronger model on the same tape;
- having a Shopify sale without a pick ticket inside SnapIMS;
- documentation claiming a button or shortcut that the browser does not actually support;
- adding powerful systems but still needing to remember hidden setup rules.

## 5.3 Owner-direction conclusion

The next release should not be a decorative feature pass. It should make SnapIMS behave like an inventory operating system:

- configure itself inside the application;
- explain current work in logs;
- permit deliberate expert overrides;
- find any physical Item instantly;
- turn Shopify orders into exact physical pick work;
- use local catalog facts first and external APIs only when needed;
- route AI cost based on measured confidence and value.

# 6. Consolidated findings register

Severity meanings:

- **Critical**: can create security exposure, wrong external state, or physical/digital inventory divergence.
- **High**: blocks a required pre-1.0 workflow or makes the operator unable to recover safely.
- **Medium**: material usability, truthfulness, maintainability, or scale risk.
- **Low**: polish or optimization that does not block the controlled pilot.

| ID | Severity | Finding | Evidence | Required disposition |
|---|---|---|---|---|
| AUD-SEC-01 | Critical | State-changing cookie-authenticated routes have no CSRF token/origin gate. | Source-confirmed | Add CSRF protection and tests before broad public use. |
| AUD-SHP-01 | Critical | Shopify inventory idempotency key is persisted but not passed to `inventoryActivate`. | Source-confirmed | Fix mutation contract and prove retry against current API. |
| AUD-SHP-02 | Critical | No inbound order/reservation/pick workflow exists. | Source-confirmed | Implement Shopify order sync and physical Item pick queue before 1.0. |
| AUD-DOC-01 | High | Active documents and UI contracts contain obsolete versions and contradictory claims. | Source-confirmed | Synchronize all active docs and screenshots after final UI. |
| AUD-INV-01 | High | No global inventory search or Item detail retrieval workspace. | Source-confirmed/user finding | Add indexed search across all batches and exact location display. |
| AUD-REC-01 | High | Successfully recognized Items cannot be deliberately re-recognized. | Source-confirmed/user finding | Add force retry, model override, escalation, and preserved history. |
| AUD-REC-02 | High | No measured staged recognition router exists. | Source-confirmed/plan pending | Implement baseline/escalation/frontier routing from benchmark evidence. |
| AUD-CFG-01 | High | Settings cannot configure API keys, models, Shopify, or metadata providers. | Source-confirmed/user finding | Add secure admin settings and connection tests. |
| AUD-OBS-01 | High | Logs do not show full operational activity and cannot be filtered. | Source-confirmed/user finding | Add structured event logging, CLI filters, and in-app Live Logs. |
| AUD-IMP-01 | High | Duplicate protection has no deliberate reprocess/test-copy override. | Source-confirmed/user finding | Add explicit safe override scopes and quarantine test copies. |
| AUD-SHP-03 | High | Existing live draft service is not visibly connected to a deliberate Publish UI action. | Source-confirmed | Add one confirmed draft route/button and evidence package. |
| AUD-AUTH-01 | High | No login throttling, audit, session revocation, or in-app password rotation. | Source-confirmed | Harden application authentication. |
| AUD-HEALTH-01 | High | HTTP 200 can report health PASS even when schema is degraded. | Source-confirmed | Treat degraded schema as failed/degraded health and nonzero doctor result. |
| AUD-CF-01 | High | Tunnel status is process/PID based rather than public-route verified. | Source-confirmed | Add connector and endpoint probes with exact failure reason. |
| AUD-TEST-01 | High | No current v0.10.0 test report or PR-triggered CI run is associated with audited commit. | Source-confirmed | Produce current automated, Firefox, and live-host evidence. |
| AUD-CAT-01 | High | Provider-neutral candidate API boundary is incomplete. | Source-confirmed/plan pending | Add approved replaceable candidate provider interface. |
| AUD-CAT-02 | High | Rights/caching policy is designed but not fully proven in production. | Plan pending | Enforce field-level provenance, rate limits, cache policy, attribution. |
| AUD-STATE-01 | High | Approved Tags and shortcut claims do not match inspected UI/source. | Source-confirmed | Reconcile regression or remove obsolete claims. |
| AUD-SCALE-01 | High | Batch Editor renders all rows and filters/sorts client-side. | Source-confirmed | Add server-side bounded paging/virtualization before large-scale claims. |
| AUD-CMD-01 | Medium | `snapims update` pulls directly without dirty-tree, branch, backup, or rollback checks. | Source-confirmed | Make update guarded, previewable, and rollback-capable. |
| AUD-CMD-02 | Medium | `snapims shell` interpolates an unquoted project path into shell text. | Source-confirmed | Use safe argv/environment handling. |
| AUD-OBS-02 | Medium | `snapims logs` only tails one file; no `log` alias. | Source-confirmed | Add alias and scoped sources (`app`, `recognition`, `catalog`, `shopify`, `tunnel`, `system`). |
| AUD-REC-03 | Medium | Disabled Gemini is offered in provider lists. | Source-confirmed | Hide unavailable providers or label/disable them clearly. |
| AUD-REC-04 | Medium | Recognition history exists but Review does not present a usable attempt comparison. | Source-confirmed | Add attempt table with model, time, cost, confidence, reason, outcome. |
| AUD-PICK-01 | Medium | No explicit inventory states for reservation/picking exceptions. | Source-confirmed | Add reservation and fulfillment state machine with audit events. |
| AUD-SEC-02 | Medium | Secrets remain environment/file managed with no in-app masked lifecycle. | Source-confirmed | Add root-readable/local secret store abstraction and admin-only updates. |
| AUD-CAT-03 | Medium | Catalog is Movie-centric; unsupported media classification remains incomplete. | Source-confirmed/plan pending | Preserve Movies-first but classify unsupported media truthfully. |
| AUD-UX-01 | Medium | Batch search is only current-page/current-batch client search. | Source-confirmed | Separate global Inventory Search from Batch Editor filtering. |
| AUD-UX-02 | Medium | Public hostnames and older docs have used both `remote` and `desktop.ims`. | Live-host/document drift | Standardize final hostname and remove obsolete instructions. |
| AUD-BACKUP-01 | Medium | Operational update and migration backup policy is not enforced by CLI. | Source-confirmed | Require preflight backup for migrations/live external writes. |
| AUD-LOG-01 | Medium | Logging policy lacks formal redaction/correlation acceptance tests. | Source-confirmed | Add secret redaction, request IDs, bounded retention, export bundle. |
| AUD-PERF-01 | Medium | No current measured recognition cost/latency benchmark in CAD. | Plan pending | Run representative VHS benchmark before routing thresholds. |
| AUD-REL-01 | Medium | The old rule that v0.10.0 is the final feature release is no longer truthful. | New production blockers | Supersede it with one final v0.10.0 feature release. |

# 7. Detailed required outcomes

## 7.1 Operational logs, not hidden reasoning

Add:

```text
snapims log
snapims logs
snapims logs --follow
snapims logs --source recognition
snapims logs --source catalog
snapims logs --source shopify
snapims logs --errors
snapims logs --since 30m
snapims logs --item ITEM-ID
snapims logs --batch BATCH-ID
```

The in-app Diagnostics workspace should include Live Activity with filters and export. Each event should include timestamp, severity, component, operation ID, Batch/Item ID, provider/model, retry number, elapsed time, token/cost fields when applicable, outcome, and safe error detail.

Never log passwords, API keys, cookies, authorization headers, full raw model prompts containing secrets, or hidden chain-of-thought.

## 7.2 Recognition override contract

For a completed item, add:

- Run recognition again;
- Run with selected supported model;
- Escalate to configured stronger model;
- Re-run using selected images;
- clear current suggestion without deleting history;
- compare attempts;
- retain the operator-approved value unless the operator explicitly accepts a new result.

A forced attempt must create a new immutable recognition result and event. It must not rewrite prior evidence.

## 7.3 Duplicate batch override contract

The default remains "open existing batch." Add deliberate choices:

- open existing;
- re-run unfinished Items;
- re-run all recognition attempts while retaining Item IDs;
- create quarantined comparison copy;
- cancel.

A comparison copy must be visibly non-saleable and blocked from Shopify until deliberately promoted or merged.

## 7.4 Inventory search contract

The new Inventory workspace must search all Items by:

- title/alias/year;
- Item ID, SKU, barcode;
- Shopify product/variant/inventory ID;
- location/shelf;
- batch;
- status and flags;
- Movie/Edition link;
- available/reserved/sold/missing/quarantined state.

Results must show thumbnail, title, Item ID, location, availability, Shopify state, price, and last movement. Selecting a result opens a physical Item detail page with photos, history, catalog, Shopify link, and controlled actions.

## 7.5 Shopify order/pick contract

SnapIMS must import orders idempotently, map each Shopify line to the immutable physical Item, reserve it, and create a pick task. The operator sees title, image, Item ID, exact shelf/bin, order, customer-safe summary, and exception status.

Required states:

```text
NEW -> RESERVED -> PICKED -> PACKED -> FULFILLED
                 -> MISSING / HOLD / CANCELLED
```

Cancellation releases reservations. Re-importing an order never duplicates pick tasks. A missing tape creates an exception without silently substituting another copy.

# 8. Verification gaps that remain before 1.0.0

- real 20-tape Pixel pilot;
- live AI recognition benchmark with correction rate, latency, and CAD cost;
- first real candidate-provider + Wikipedia enrichment and local reuse;
- one deliberate live Shopify draft inspected in Shopify Admin;
- physical CSV reconciliation;
- live order import and pick workflow against controlled test order;
- current Firefox/Linux browser audit with console/network/server logs;
- clean restart and interrupted-job recovery test after final schema;
- complete first-time-operator guide walkthrough;
- current v0.10.x automated quality report;
- no critical/high production blocker for the supported scale.

# 9. Immediate action recommendation

Do not begin the new database/order schema immediately. First perform a short v0.10.0 stabilization and evidence pass:

1. Back up the production candidate database, media, `.env`, and Cloudflare/Guacamole configuration.
2. Reconcile shortcut, Tags, version, and documentation contradictions.
3. Fix Shopify mutation idempotency and add a failing regression test.
4. Add CSRF protection and login abuse tests.
5. Correct health/tunnel truth semantics.
6. Guard `snapims update` and shell path handling.
7. Produce a current v0.10.0 test/browser report.
8. Freeze a migration baseline and only then begin the v0.10.0 schema work.

# 10. Source register

## Repository sources inspected

- `snapims/web/app.py`
- `snapims/web/templates/base.html`
- `snapims/web/templates/home.html`
- `snapims/web/templates/import.html`
- `snapims/web/templates/review.html`
- `snapims/web/templates/batch_editor.html`
- `snapims/web/templates/publish.html`
- `snapims/web/templates/settings.html`
- `snapims/web/static/app.js`
- `snapims/cli.py`
- `snapims/config.py`
- `snapims/manager.py`
- `snapims/db.py`
- `snapims/recognition/providers.py`
- `snapims/recognition/service.py`
- `snapims/catalog/service.py`
- `snapims/shopify/client.py`
- `snapims/shopify/service.py`
- `pyproject.toml`
- `RELEASE_NOTES.md`
- `PRODUCTION_READINESS.md`
- `TEST_RESULTS.md`

## Planning sources used

- `SnapIMS_Feature_Enhancement_Work_Order_v0.10.0_Production_Candidate_Update.md`
- `SnapIMS_Feature_Enhancement_Work_Order_v0.8.0_Status.md`
- `SnapIMS_Master_Scope_of_Work_and_Implementation_Plan(1).docx`
- owner field-test findings from July 26, 2026

# 11. Audit conclusion

SnapIMS is in a stronger state than a typical solo pre-1.0 project. The infrastructure milestone is real, the physical identity model is sound, and multiple recovery controls are already better than many internal business applications.

The correct next move is not to restart or redesign the project. It is to make the product operationally complete and truthful. Search, picking, recognition control, settings, logs, provider boundaries, and final Shopify/CSV/live-AI evidence are the remaining bridge between a powerful inventory workstation and a production release.
