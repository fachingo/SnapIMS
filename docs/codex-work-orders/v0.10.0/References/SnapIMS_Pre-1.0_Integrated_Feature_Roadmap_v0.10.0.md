---
title: "SnapIMS Pre-1.0 Integrated Feature Roadmap"
subtitle: "Updated feature enhancement work order and dependency-aware path from v0.10.0 to v1.0.0"
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

# Purpose and authority

This document replaces the prior v0.10.0 Production Candidate Update as the current feature-enhancement and release-planning authority for SnapIMS.

It incorporates:

- the current v0.10.0 infrastructure implementation and live cold-boot acceptance;
- the v0.8.0 and v0.7.0 feature/enrichment requirements that remain incomplete;
- the Master Scope of Work issue mapping and dependency sequence;
- the July 26, 2026 integrated source/operator/owner audit;
- new production-blocking requirements for global inventory search, Shopify order picking, operator settings, observability, and controlled recognition overrides.

The live repository, production database, final browser UI, and verified host configuration remain the source of truth. This roadmap controls what should be implemented and in what order; it does not override real evidence.

# 1. Version and release policy

## 1.1 Current milestone

SnapIMS v0.10.0 is accepted as the **infrastructure and remote-operation milestone**, subject to final documentation synchronization and repository evidence.

Live evidence demonstrates:

- global launcher;
- single-command stack startup;
- authenticated SnapIMS;
- Cloudflare Tunnel;
- authenticated Guacamole desktop and SSH;
- cold-boot recovery;
- all current `snapims doctor` infrastructure checks passing.

## 1.2 Superseding the old final-feature rule

The prior plan called v0.10.0 the final planned feature release before 1.0.0. Live use exposed missing workflows that are production blockers, not optional enrichment:

- global inventory retrieval;
- Shopify order reservation and picking;
- secure first-time configuration inside SnapIMS;
- controlled recognition reprocessing and model routing;
- observable background work.

Therefore the old rule is superseded.

## 1.3 New release sequence

| Release | Scope | Rule |
|---|---|---|
| 0.10.0 | Infrastructure and remote operation | Accepted foundation; no new product schema. |
| 0.9.1 | Stabilization patch, if released separately | Defects, security hardening, health truth, Shopify idempotency, documentation reconciliation only. |
| 0.10.0 | Final pre-1.0 feature release | Observability, Settings, recognition control/router, inventory search, catalog completion, Shopify order/pick workflow. |
| 0.10.x | Production fixes and evidence | No new operator workflow after feature freeze. |
| 1.0.0 | First production release | Only after every acceptance gate passes. |

If 0.9.1 is not released separately, its fixes must be the first bounded commits in the 0.10.0 branch.

# 2. Product principles

| Principle | Required interpretation |
|---|---|
| Exception handling, not data entry | Routine Review remains photograph -> confirm/correct -> optional Price/Tags/Discount -> Approve & Next. |
| Physical identity is permanent | Batch, Item, images, location history, reservation, and Shopify linkage never depend on title or provider output. |
| Search must return physical truth | Every result resolves to a specific owned Item and current location, not only a Movie title. |
| Orders reserve exact Items | A Shopify line maps to one immutable physical Item before it enters picking. |
| AI recognizes; approved sources verify | AI proposes identity. Local catalog and rights-approved sources provide reusable facts. |
| Local catalog first | Known Movies are reused without unnecessary external calls. |
| Wikipedia is bounded enrichment | Use official APIs, limited fields, provenance, and attribution; do not mirror articles. |
| External provider rights are respected | Do not scrape IMDb, copy a provider database, or exceed licence/caching terms. |
| Operator override is deliberate and auditable | Expert reprocessing is allowed, but every attempt and acceptance is preserved. |
| Logs show events, not hidden thought | Expose observable operations, evidence, retries, and outcomes; never expose private chain-of-thought or secrets. |
| Settings are safe and testable | Secrets are masked, admin-only, validated, and never returned in full after save. |
| Review stays fast | Network lookup and stronger models run asynchronously unless the operator requests them. |
| Browser UI is the source of truth | All instructions and screenshots must match the final native browser UI. |
| 1.0 is earned | No production label without complete physical, API, browser, restart, and documentation evidence. |

# 3. Target product architecture

## 3.1 Core entities

1. **Movie** - canonical supported work and approved factual metadata.
2. **Edition** - a specific VHS commercial release or variant.
3. **Physical Item** - one owned tape with immutable local identity.
4. **Batch** - one durable capture/import session.
5. **Recognition Attempt** - one immutable provider/model evaluation of an Item.
6. **External Candidate Attempt** - one local/provider/Wikipedia resolution operation.
7. **Shopify Listing Link** - durable mapping from physical Item to Shopify product/variant/inventory IDs.
8. **Order** - one imported Shopify order revision.
9. **Reservation** - temporary exclusive claim on a physical Item for one order line.
10. **Pick Task** - operator work to retrieve, confirm, pack, or exception an exact Item.

## 3.2 Data authority

### `inventory.sqlite3`

Authoritative for physical Items, images, batches, locations, conditions, working/reviewed values, recognition attempts, Shopify listing links, order reservations, pick tasks, inventory events, audit events, and recovery state.

### `movie_catalog.sqlite3`

Authoritative for local Movies, aliases, approved facts, provider candidates, candidate decisions, source provenance, refresh metadata, and local search index.

### Secret store

Secrets must not be normal readable inventory rows. Use a local permissions-restricted secrets file or approved OS keyring abstraction with:

- owner-only file permissions;
- atomic writes and backups;
- masked read model;
- admin re-authentication before change;
- no plaintext value returned to the browser after save;
- redacted audit event.

# 4. Master dependency sequence

The following order is mandatory because it prevents new schema work from landing on contradictory or unsafe contracts.

## Phase 0 - Freeze, backup, and re-verify

1. Record branch, commit, version, inventory schema, catalog schema, and current host services.
2. Back up databases, originals/processed images, `.env`/secret store, Cloudflare config, Guacamole config, and current documentation.
3. Run secret scan and verify `.env`, credentials, production database, media, and logs are ignored.
4. Capture the current cold-boot PASS evidence.
5. Create a clean feature branch from the accepted v0.10.0 commit.

**Exit gate:** verified restore point and no unknown working-tree changes.

## Phase 1 - v0.9 stabilization and truth reconciliation

Complete before any new business schema:

- fix Shopify inventory idempotency mutation;
- add CSRF protection and authentication abuse controls;
- correct `/health`, `doctor`, and tunnel public-health truth;
- guard `snapims update` and shell path handling;
- reconcile shortcut/Tags/current-version contradictions;
- produce current automated and Firefox reports;
- synchronize all active v0.9 documentation.

**Exit gate:** no known critical defect in current workflows; documents describe the installed application.

## Phase 2 - Observability and secure application Settings

Implement before staged recognition and external APIs so later work is inspectable and configurable.

## Phase 3 - Recognition control and staged routing

Implement before the representative benchmark and before relying on recognition results for catalog/order automation.

## Phase 4 - Global inventory search and Item detail

Implement before Shopify order picking. It establishes the retrieval contract and indexes needed by pick resolution.

## Phase 5 - Provider-neutral candidate API and local catalog completion

Complete rights, provenance, configuration, and local-first candidate resolution.

## Phase 6 - Shopify setup, live draft, orders, reservations, and pick queue

Build on exact physical search and durable listing links.

## Phase 7 - Scale, recovery, and production acceptance

Run physical pilot, live integrations, browser audit, restart/interruption tests, documentation walkthrough, and final release decision.

# 5. Work Package 0 - Stabilization patch

## Objective

Make the current v0.9 foundation truthful and safe before migrations or new workflows.

## Required changes

### Security

- CSRF token or equivalent robust origin-bound protection for all state-changing browser routes.
- Login rate limiting/backoff and failed-login audit events.
- Session revocation/rotation when administrator password or signing secret changes.
- Security headers appropriate for the public deployment.

### Health and orchestration truth

- `/health` returns non-200 or a clearly degraded status consumed correctly when schema integrity fails.
- `snapims doctor` exits nonzero when a required check fails.
- tunnel status verifies a live connector and optionally public endpoint, not only a PID.
- Guacamole health requires the expected page/application marker without an overly broad HTML fallback.
- `snapims down` and restart remain scoped to SnapIMS-managed processes.

### Shopify correctness

- pass a stable idempotency key through the current Shopify API contract;
- reject ambiguous duplicate SKU results instead of using the first result;
- add tests for retry after interruption at every upload stage;
- ensure a second attempt cannot create an unexplained second draft.

### CLI safety

- `snapims update --check` displays branch, upstream, dirty state, commits, migration requirement, and backup requirement;
- refuse destructive update on a dirty tree unless explicitly overridden;
- create restore point before migration/restart;
- use safe argv/path handling in `snapims shell`;
- add explicit error exit codes.

### Contract reconciliation

- choose and implement one browser-safe command palette shortcut;
- choose and implement one browser-safe quick-action mapping;
- either restore the approved Tags workflow or correct every claim that it exists;
- update all current documents from stale 0.7/0.8 references to the actual version.

## Acceptance

- current pytest, Ruff, mypy/type gate, compileall, JS syntax, build, pip check, diff check, and secret scan pass;
- native Firefox workflow passes;
- no active document contradicts the UI;
- cold boot remains one-command operational;
- all critical audit findings in this package are closed.

# 6. Work Package 1 - Operational observability

## Objective

Let an operator understand every active and recent operation without reading raw database tables or guessing.

## CLI contract

Support both singular and plural:

```text
snapims log
snapims logs
snapims logs --follow
snapims logs --last 200
snapims logs --since 30m
snapims logs --errors
snapims logs --source app|recognition|catalog|shopify|import|cloudflare|guacamole|system
snapims logs --batch <id>
snapims logs --item <id>
snapims logs --operation <id>
snapims logs --json
snapims logs --export <path>
```

## In-app contract

Add **Diagnostics -> Live Activity**:

- current running operations;
- background queue depth;
- recognition/catalog/Shopify/import events;
- filters by component, severity, Batch, Item, provider/model, and time;
- expandable safe technical details;
- copy/export support;
- visible correlation/operation ID;
- retry action only where safe.

## Data contract

Every event includes:

- timestamp;
- component/event type;
- severity;
- operation ID;
- Batch/Item/order IDs where applicable;
- provider/model and attempt number where applicable;
- duration;
- token/image/cost fields when applicable;
- outcome and safe error class;
- restart/recovery relationship.

## Redaction contract

Never emit:

- API keys/tokens;
- passwords;
- cookies/session tokens;
- authorization headers;
- complete secret-bearing environment values;
- private model chain-of-thought.

## Acceptance

- recognition, catalog, import, Shopify, tunnel, and recovery scenarios produce readable correlated events;
- secret fixture scan proves redaction;
- log rotation and retention are bounded;
- a support bundle can be exported without production secrets or full customer data.

# 7. Work Package 2 - Secure Settings and connection wizards

## Objective

Configure normal operation without editing `.env` manually.

## Settings sections

### Recognition

- OpenAI API key (masked after save);
- supported provider;
- baseline model;
- escalation model;
- optional frontier model;
- confidence/contradiction thresholds;
- timeout/retry limits;
- image-selection profile;
- test connection;
- estimated price table/version;
- save and rollback.

### Shopify

- store domain;
- Admin API token;
- API version;
- location selection;
- draft-only lock;
- required scope validation;
- test connection;
- create one deliberate test draft workflow only after review.

### Movie data

- selected candidate provider;
- provider credential;
- permitted fields/cache policy profile;
- language/region;
- Wikipedia User-Agent;
- rate/timeout/retry settings;
- test lookup and provenance preview.

### Infrastructure

Mostly read-only:

- local/public URLs;
- service status;
- tunnel connector state;
- Guacamole URL;
- data paths;
- backup and log locations.

## Security requirements

- administrator session required;
- current password confirmation for secret changes;
- masked values only after save;
- atomic write and backup;
- no secret in URL, logs, diagnostics export, or browser HTML;
- connection test uses unsaved value in-memory, then discards it unless saved;
- audit event records field changed, not the value.

## Acceptance

A first-time operator can configure OpenAI, Shopify, and the approved movie provider entirely through the application, receive exact scope/error feedback, restart, and retain the settings securely.

# 8. Work Package 3 - Recognition Control Centre and staged router

## Objective

Use the cheapest reliable model for routine tapes while preserving expert override and complete evidence.

## Recognition Control Centre

Add a top-level **Recognition** workspace with:

- current queue and active job;
- configured model ladder;
- batch/item attempt history;
- confidence and contradiction filters;
- failed/blocked/unsupported queues;
- estimated and actual cost;
- Run Unfinished, Run Selected, Force Re-run, Escalate Selected;
- benchmark mode and comparison results.

## Per-item Review controls

For every Item, including successful results:

- Run again;
- choose supported provider/model;
- escalate;
- choose image subset/profile;
- clear current suggestion without deleting history;
- compare attempts;
- accept a selected attempt;
- retain operator-approved working value until explicit replacement.

## Staged routing

### Stage 0 - deterministic preparation

Deduplicate images, select bounded derivatives, preserve originals, and record image evidence.

### Stage 1 - baseline

Low-cost image-capable model returns exact title evidence or UNKNOWN.

### Stage 2 - escalation

Run when title is missing, confidence is below measured threshold, front/spine/back conflict, candidate provider contradicts, response schema fails, or operator requests it.

### Stage 3 - frontier exception

Use only for measured rare difficult cases.

### Stage 4 - operator

Manual resolution remains authoritative.

## Benchmark

Use a representative real VHS set containing:

- clear mainstream films;
- sequels/remakes;
- low-contrast/damaged covers;
- slogans/tagline-heavy covers;
- music/concert;
- TV/anime;
- unusual editions;
- unsupported media.

Measure:

- exact-title accuracy;
- false confidence;
- correction rate;
- escalation rate;
- latency;
- input/output tokens;
- CAD cost per tape and batch;
- catalog agreement;
- operator time.

## Acceptance

- obvious tapes usually finish at baseline;
- difficult tapes escalate or enter manual review;
- no successful attempt is irreversible;
- no attempt overwrites history;
- thresholds are derived from data;
- staged routing improves correction/time/cost enough to justify complexity.

# 9. Work Package 4 - Global Inventory Search and Item Retrieval

## Objective

Make every owned tape findable and physically retrievable regardless of original batch.

## Navigation

Add a top-level **Inventory** workspace and a global search command.

## Search fields

- canonical/working/suggested title and aliases;
- year, edition, distributor;
- Item ID, SKU, barcode;
- shelf/location;
- Batch ID;
- Shopify product, variant, and inventory IDs;
- Movie/Edition ID;
- status/flags;
- available, reserved, sold, missing, quarantined;
- condition, price, tags.

## Result row

Show:

- thumbnail;
- title/year;
- Item ID and SKU;
- exact location;
- availability/reservation;
- price;
- Shopify state;
- last movement/update.

## Item detail

Include:

- full photographs;
- physical identity and Batch;
- current location and movement history;
- condition and notes;
- recognition attempts;
- Movie/Edition link and source provenance;
- Shopify IDs/admin link;
- reservation/order link;
- actions: move, adjust quantity, flag missing, quarantine, inspect, re-recognize.

## Technical direction

- SQL-backed query parameters;
- FTS or appropriate indexes;
- deterministic sorting and pagination;
- bounded result payloads;
- no all-inventory DOM render;
- immutable Item ID in every action;
- optimistic record revision for edits.

## Acceptance

- operator finds a tape by title, SKU, Item ID, barcode, and location;
- result always identifies one physical Item;
- move action requires reason and appears in history;
- search remains responsive at the owner-approved inventory scale;
- restart and concurrent stale-tab tests pass.

# 10. Work Package 5 - Rights-respecting candidate API and catalog completion

## Objective

Resolve Movies reliably without copying another provider's database or slowing Review.

## Provider interface

Define a replaceable candidate provider contract:

```text
search(title, year, region, limit) -> candidates
fetch(candidate_id, approved_fields) -> normalized facts + provenance
health() -> capability/status
policy() -> permitted fields, cache/refresh, attribution
```

## Required restrictions

- no IMDb scraping;
- no wholesale provider dump;
- no commercial TMDb use without approved agreement;
- only approved fields and retention;
- external IDs are references, not local identity;
- provider failure leaves inventory and manual Review operational.

## Local-first flow

```text
AI/operator title
  -> local Movie/alias search
  -> unique match: reuse
  -> no unique match: approved candidate API
  -> bounded Wikipedia enrichment
  -> ambiguity or unsupported media: operator queue
  -> durable local Movie + provenance
```

## Wikipedia policy

- official MediaWiki APIs;
- descriptive User-Agent;
- bounded candidates/pages;
- timeout, retry, rate limit;
- redirect/disambiguation handling;
- no full article storage;
- no direct Wikipedia prose as Shopify sales copy;
- source page, revision, URL, retrieval time, parser version, and attribution retained.

## Edition boundary

Before 1.0, implement only the minimum Edition data required for exact physical identification and Shopify draft quality. Do not delay production on a complete collector-grade Edition research workspace unless the pilot proves it is a blocker.

## Acceptance

- first supported real film creates one durable Movie;
- second copy reuses it without unnecessary external request;
- ambiguity is visible and resolvable;
- unsupported media is not forced into Movie;
- provider and Wikipedia failure are recoverable;
- every external field is traceable.

# 11. Work Package 6 - Shopify setup, live draft, orders, and pick queue

## Objective

Close the full business loop from physical intake to order fulfillment.

## 11.1 Shopify setup wizard

1. Enter store domain and token.
2. Test API version and identity.
3. Verify exact required scopes.
4. Select location.
5. enforce draft-only mode.
6. Save securely.
7. Run simulation.
8. Create exactly one confirmed test draft.

## 11.2 Outbound listing completion

- expose deliberate live draft action in Publish;
- require item-level confirmation;
- display exact payload/diff before write;
- pass Shopify idempotency keys correctly;
- reject duplicate SKU ambiguity;
- preserve stage checkpoints and restart recovery;
- inspect title, price, discount, quantity, SKU, images, catalog facts, and Draft state in Admin.

## 11.3 Order ingestion

Initial production-safe approach may use scheduled polling if webhook infrastructure is not yet approved. The design must support idempotent revisions and later webhooks.

Store:

- Shopify order ID/name/revision;
- line item/variant/inventory IDs;
- quantity;
- financial/fulfillment/cancellation state needed for picking;
- last synced time and payload hash;
- error/retry state.

Do not store unnecessary customer data in logs or pick views.

## 11.4 Exact Item reservation

Resolve each order line through durable Shopify linkage to one physical Item. Create one exclusive reservation per quantity unit. Never match by title text.

If multiple compatible Items are intentionally pooled, use explicit owner-approved allocation rules. Before that feature exists, require exact Item linkage.

## 11.5 Pick Queue

Show:

- order number;
- Item title/image;
- Item ID/SKU;
- exact shelf/bin;
- quantity;
- status;
- exception reason;
- pick confirmation.

States:

```text
NEW -> RESERVED -> PICKED -> PACKED -> FULFILLED
  |       |          |         |
  +-> HOLD/MISSING/CANCELLED/RELEASED
```

## 11.6 Recovery rules

- repeated sync does not duplicate orders/tasks;
- cancellation releases unpicked reservations;
- restart resumes incomplete sync;
- missing tape creates exception;
- no silent substitution;
- fulfillment write is separately confirmed and idempotent;
- inventory quantity cannot go negative.

## Acceptance

- one controlled test order imports;
- exact physical Item and shelf are shown;
- pick confirmation persists across restart;
- cancellation releases reservation;
- duplicate sync creates no duplicate task;
- one deliberate fulfillment update succeeds only after confirmation.

# 12. Work Package 7 - Scale and performance

## Objective

Support the scale actually claimed without browser freeze or full-table rendering.

## Required before 1.0

The production claim may remain a controlled single-operator 20-200 Item workflow if that is what is measured. In that case, 5,000-row optimization is not a 1.0 blocker, but the application must not claim warehouse-scale readiness.

Inventory Search and Pick Queue must still use bounded server-side queries from the start.

## Deferred unless pilot proves necessary

- 5,000-row Batch Editor virtualization;
- 10,000-photo import optimization;
- multi-user batch claims and concurrency;
- large warehouse task assignment.

## Acceptance

Publish a truthful supported-scale statement with measured load, search, Review, import, and pick performance on the target machine.

# 13. Work Package 8 - Production acceptance gate

The product may be labelled 1.0.0 only when all are complete.

## Physical pilot

- real 20-tape Pixel capture;
- exact physical/digital count reconciliation;
- QR grouping and image roles inspected;
- locations assigned and physically verified;
- search finds all 20 Items.

## Live AI

- representative live recognition;
- measured correction rate, latency, failures, retry, model routing, and CAD cost;
- attempt evidence retained.

## Catalog

- first durable Movie;
- second-copy local reuse;
- ambiguity and unsupported-media case;
- approved candidate provider and Wikipedia policy evidence.

## CSV

- downloaded bytes re-uploaded;
- changed CSV previewed/applied;
- physical records reconciled;
- rollback proven.

## Shopify

- exactly one authorized live Draft inspected;
- idempotent retry proven;
- controlled order imported;
- exact pick ticket and reservation proven;
- no automatic storefront publication.

## Restart and recovery

- cold boot;
- interrupted recognition/catalog/import/order/Shopify scenarios;
- stale PID and partial operation recovery;
- no lost IDs, images, history, reservations, or links.

## Browser and documentation

- native Firefox full walkthrough;
- mobile access checks for supported views;
- no relevant console/page/network errors;
- Operator Guide updated after final UI;
- every screenshot, button, menu, workflow, recovery procedure, and end-of-batch checklist matches;
- independent guide walkthrough passes.

## Quality and release

- pytest, Ruff, type gate, compileall, JS checks, build, pip check, SQLite integrity/FK/schema manifest, secret scan, and diff check pass;
- all documents reference the same active version;
- no known production blocker for the claimed scale;
- final version decision recorded.

# 14. Required migration design

Before schema changes, create a written migration specification covering:

- current inventory and catalog schema versions;
- backup/restore procedure;
- new settings metadata (not secret values);
- recognition attempt tier/trigger/forced-by fields;
- global inventory search indexes;
- order, order line, reservation, and pick task tables;
- listing link uniqueness;
- status transition constraints;
- idempotency keys and request hashes;
- audit events;
- rollback and forward-only policy;
- migration interruption/restart tests.

No migration may change Batch ID, Item ID, image linkage, review history, location history, or existing Shopify IDs.

# 15. Testing matrix

For each work package, test:

- successful operation;
- invalid input;
- duplicate invocation;
- timeout/network failure;
- process interruption;
- application restart;
- stale browser revision;
- partial external success;
- retry;
- rollback/recovery;
- secret redaction;
- native Firefox UI;
- documentation match.

Specific required scenarios:

- force re-recognition after successful attempt;
- compare two models without changing approved value;
- duplicate import open/re-run/test-copy;
- global search with duplicate titles;
- location move with reason;
- order cancellation after reservation;
- duplicate order sync;
- missing Item during pick;
- Shopify retry after product create but before media complete;
- provider unavailable while Review continues;
- health schema degraded but process alive;
- Cloudflare process alive but public route broken.

# 16. Documentation synchronization

After final browser verification, update at minimum:

- SnapIMS Operator Guide;
- screenshots;
- README;
- Release Notes;
- Test Results;
- Browser Verification;
- Production Readiness;
- Deployment Guide;
- Installation Guide;
- Developer Guide;
- this roadmap;
- version references and archive names.

Remove obsolete controls, shortcuts, screenshots, hostnames, and version claims. Repeat the full guide walkthrough after edits.

# 17. Post-1.0 backlog

Unless the real pilot proves otherwise, defer:

- complete collector-grade Movie detail workspace;
- complete Edition evidence/research workspace;
- grouped duplicate Review;
- long-form generated descriptions and regeneration UI;
- compatible-copy pooling and substitution rules;
- Collection Intelligence;
- eBay/other marketplace integrations;
- licensed comparable-sales pricing intelligence;
- multi-user roles, assignments, and concurrent batch claims;
- 5,000-row/10,000-photo warehouse architecture;
- automatic storefront publication.

# 18. Final planning rule

The path is now:

1. preserve and stabilize v0.10.0;
2. implement the bounded v0.10.0 final feature scope in dependency order;
3. freeze features;
4. use 0.10.x only for fixes and evidence;
5. run the full physical/live production gate;
6. label 1.0.0 only when every requirement passes.

The new features are not uncontrolled expansion. Inventory search, picking, recognition override, settings, and observability are the minimum workflows needed for SnapIMS to operate as a real inventory management system rather than only an intake and listing tool.

# 19. Source register

- SnapIMS v0.10.0 audited branch `feature/v0.9-infrastructure` at commit `bda7093d8ca9b776b2e881ce38a09f10b222f56f`
- `SnapIMS_v0.10.0_Integrated_Three-Perspective_Audit.md`
- `SnapIMS_Feature_Enhancement_Work_Order_v0.10.0_Production_Candidate_Update.md`
- `SnapIMS_Feature_Enhancement_Work_Order_v0.8.0_Status.md`
- `SnapIMS_Master_Scope_of_Work_and_Implementation_Plan(1).docx`
- owner live field findings and cold-boot evidence, July 26, 2026
