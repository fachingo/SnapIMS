# SnapIMS v0.10.0 — Complete Codex Work Order

This combined document concatenates the package. Codex should normally read the split files.


---

# FILE: 00_START_HERE.md

# SnapIMS v0.10.0 Codex Work-Order Package

## Purpose

This package converts the integrated SnapIMS audit and pre-1.0 roadmap into an executable, resumable Codex implementation program.

It is intentionally split into bounded phase files. Codex should read the files from disk instead of receiving one enormous repeated chat prompt.

## Recommended model

Use:

- Model: `gpt-5.6-sol`
- Reasoning effort: **High**
- Prevent sleep while running: enabled

Reserve Ultra for a bounded difficult review or failure investigation, not the entire implementation.

## Install this package into the repository

From a terminal:

```bash
cd ~/Projects/SnapIMS
mkdir -p docs/codex-work-orders/v0.10.0
```

Extract this ZIP so the package contents are located at:

```text
~/Projects/SnapIMS/docs/codex-work-orders/v0.10.0/
```

The package should then contain `01_MASTER_CONTROLLER.md` and all numbered phase files.

## Start Codex

```bash
cd ~/Projects/SnapIMS
source .venv/bin/activate
codex -m gpt-5.6-sol
```

Select **High** reasoning effort.

Paste this compact starter prompt:

```text
You are implementing the complete SnapIMS v0.10.0 final pre-1.0 work order.

Read and obey:
docs/codex-work-orders/v0.10.0/01_MASTER_CONTROLLER.md

Then read every numbered phase file and supporting contract referenced by the controller. Inspect the live repository before editing. Create or resume V010_IMPLEMENTATION_STATE.md. Execute the phases in dependency order, committing verified bounded milestones. Continue autonomously until an owner-approval gate, an unrecoverable external block, or the end of the work order. Do not merely summarize the files. Begin now.
```

## Resume a later Codex session

Paste:

```text
Resume the SnapIMS v0.10.0 work order.

Read:
1. docs/codex-work-orders/v0.10.0/01_MASTER_CONTROLLER.md
2. V010_IMPLEMENTATION_STATE.md
3. the phase file named as NEXT_PHASE in the state file

Verify the current branch, HEAD, working tree, tests, schemas and latest phase commit. Continue from the first incomplete acceptance criterion. Do not repeat completed work and do not discard preserved changes.
```

## Owner approval gates

Codex should stop and ask only when required for:

- sudo authentication that cannot be supplied by the environment;
- a real Shopify write;
- a full Wikidata dump download/import;
- secret entry;
- an irreversible external action;
- a destructive production-data action without a validated backup;
- a product decision explicitly marked `OWNER DECISION REQUIRED`.

Ordinary code edits, tests, migrations against disposable copies, browser automation, documentation generation and local fixture creation do not require repeated approval.

## Critical release rule

The final implemented version for this package is **0.10.0**, a minor release.

Do not label SnapIMS `1.0.0`. The physical/live production acceptance gates remain separate and mandatory.


---

# FILE: 01_MASTER_CONTROLLER.md

# Master Controller — SnapIMS v0.10.0

## Assignment

Implement the complete final pre-1.0 feature release for SnapIMS.

Repository:

```text
fachingo/SnapIMS
```

Expected local path:

```text
~/Projects/SnapIMS
```

Known accepted infrastructure baseline:

- historical audited branch: `feature/v0.9-infrastructure`;
- historical audited commit: `bda7093d8ca9b776b2e881ce38a09f10b222f56f`;
- accepted infrastructure version: `0.9.0`;
- target implementation version: `0.10.0`;
- supported host: Linux Mint;
- local SnapIMS: `http://127.0.0.1:8767`;
- public SnapIMS: `https://ims.canadavhs.ca`;
- official Guacamole: `https://desktop.ims.canadavhs.ca/guacamole/`;
- compatibility Guacamole hostname may remain `https://remote.canadavhs.ca/guacamole/`;
- normal data root: `~/SnapIMS-data`.

Do not assume the repository still matches the historical commit. Inspect current reality first.

## Authority order

When instructions conflict, use this order:

1. current production data and immutable physical identity;
2. current verified browser behaviour;
3. this work-order package;
4. integrated v0.10.0 roadmap;
5. integrated v0.9.0 audit;
6. older feature documents and historical reports.

Never preserve a false old claim merely because it is documented.

## Product contract

SnapIMS is an exception-handling inventory workstation, not a generic data-entry application.

Routine Review remains:

```text
Photograph
→ confirm or correct Title
→ optionally adjust Price
→ confirm approved Tags
→ optionally adjust Discount
→ Approve & Next
```

Routine Review must remain fast. External catalog calls, expensive recognition and background enrichment must not delay `Approve & Next` unless the operator explicitly requests the operation.

## Permanent identity rules

Never change or regenerate an existing:

- Batch ID;
- Item ID;
- image-to-Item relationship;
- physical sequence;
- location history;
- Review history;
- recognition attempt;
- Movie ID;
- Edition ID;
- Shopify product/variant/inventory link;
- order/reservation/pick history.

Titles, external IDs, list positions and provider output are not physical identity.

## Repository and Git discipline

At startup record:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git log -5 --oneline --decorate
git remote -v
```

If the tree is dirty:

1. inspect every change;
2. preserve it in a timestamped patch or deliberate preservation commit;
3. do not overwrite it;
4. record the preservation action in `V010_IMPLEMENTATION_STATE.md`.

Create or use:

```text
feature/v0.10.0-final-preproduction
```

Do not:

- reset hard;
- force-push;
- rewrite shared history;
- delete branches;
- discard untracked files;
- commit `.env`;
- commit API keys or credentials;
- commit production SQLite files;
- commit production photographs or logs;
- perform a real Shopify write without explicit owner approval.

Use bounded phase commits. Suggested sequence:

1. `chore: preserve and baseline v0.10.0 work`
2. `fix: stabilize security health and external write recovery`
3. `feat: add structured operational observability`
4. `feat: add secure application settings`
5. `feat: add recognition control and staged routing`
6. `feat: add global inventory retrieval`
7. `feat: complete local-first movie catalog acquisition`
8. `feat: add Shopify orders reservations and picking`
9. `test: complete v0.10.0 verification`
10. `docs: synchronize SnapIMS v0.10.0 release`

Commit messages may be adjusted to match actual work.

## State file

Create at repository root:

```text
V010_IMPLEMENTATION_STATE.md
```

Start from `12_IMPLEMENTATION_STATE_TEMPLATE.md`.

Update it after every significant checkpoint with:

- branch and HEAD;
- current phase;
- completed criteria;
- migrations;
- tests;
- browser evidence;
- backups;
- owner approvals;
- known failures;
- exact next action.

Do not treat the state file as a substitute for Git commits.

## Phase execution

Read and execute in order:

1. `02_PHASE_0_BASELINE_AND_PRESERVATION.md`
2. `03_PHASE_1_STABILIZATION_SECURITY.md`
3. `04_PHASE_2_OBSERVABILITY.md`
4. `05_PHASE_3_SECURE_SETTINGS.md`
5. `06_PHASE_4_RECOGNITION_ROUTING.md`
6. `07_PHASE_5_INVENTORY_SEARCH.md`
7. `08_PHASE_6_MOVIE_DATABASE.md`
8. `09_PHASE_7_SHOPIFY_ORDERS_PICKING.md`
9. `10_PHASE_8_SCALE_ACCEPTANCE.md`
10. `11_PHASE_9_DOCUMENTATION_RELEASE.md`

Each phase has its own exit gate. Do not merge later schema/workflows ahead of an unmet required predecessor.

## Test discipline

For every defect or workflow, test where applicable:

- success;
- invalid input;
- duplicate invocation;
- timeout;
- rate limit;
- network failure;
- process interruption;
- application restart;
- stale browser revision;
- partial external success;
- retry;
- rollback/reconciliation;
- secret redaction;
- native Firefox behaviour;
- documentation match.

Use disposable databases and mocked transports for destructive/failure tests.

## Standard quality gate

Use repository equivalents, but normally run:

```bash
python -m pytest -q
python -m ruff check .
python -m mypy snapims --ignore-missing-imports
python -m compileall -q snapims tests scripts
node --check snapims/web/static/app.js
python -m build --no-isolation
python -m pip check
git diff --check
```

Also verify:

- inventory `PRAGMA integrity_check`;
- inventory `PRAGMA foreign_key_check`;
- catalog integrity and foreign keys;
- schema manifest;
- FTS/index health;
- release archive secret scan;
- no database/media/cache inclusion.

A missing optional local tool may be reported, but do not falsely record PASS.

## External-source rule

Technical implementations must be verified against current official documentation at implementation time.

Primary references:

- Shopify official developer documentation;
- Wikidata and Wikimedia official documentation;
- OpenAI official documentation;
- Cloudflare official documentation.

Do not rely on an old copied API example when the current provider contract differs.

## Completion rule

The assignment is complete only when:

- every implementable phase exit gate passes;
- owner-blocked live actions are clearly isolated and documented;
- version is synchronized to 0.10.0;
- browser UI and Operator Guide match;
- release evidence exists;
- the final report uses `14_FINAL_REPORT_TEMPLATE.md`;
- no known production blocker is hidden.

The assignment may end with remaining **1.0 acceptance gates**. Those gates are not defects in the work order if they require owner-controlled physical tapes, credentials or a deliberately authorized live Shopify draft.


---

# FILE: 02_PHASE_0_BASELINE_AND_PRESERVATION.md

# Phase 0 — Baseline, Preservation and Architecture Reconciliation

## Objective

Establish a trustworthy restore point and determine exactly what the current repository implements before changing schema or workflow.

## Required inspection

Record:

- current branch, commit and upstream;
- working-tree state;
- installed package version;
- `pyproject.toml` version;
- `snapims.__version__`;
- inventory database path and schema version;
- catalog database path and schema version;
- migration files/functions;
- current service state;
- current public/local URLs;
- current authentication state;
- current OpenAI model and provider configuration without printing secrets;
- current Shopify configuration state without printing tokens;
- current documentation versions;
- ignored paths;
- latest test and browser evidence.

Inspect current implementations of:

- CLI;
- service manager;
- authentication;
- import/duplicate handling;
- Review;
- Batch Editor;
- recognition providers and jobs;
- catalog jobs;
- Settings;
- Diagnostics;
- CSV;
- Shopify outbound service;
- migrations;
- documentation generators.

## Preservation

Create a timestamped external backup root such as:

```text
~/SnapIMS-backups/v0.10.0-prework-YYYYMMDD-HHMMSS/
```

Back up when present:

- `inventory.sqlite3`;
- `movie_catalog.sqlite3`;
- originals and processed media manifest/checksum;
- exports;
- `.env` and secret files;
- Cloudflare config and credential filenames;
- Guacamole config;
- systemd unit files related to SnapIMS;
- Operator Guide and active release documents;
- current Git patch/bundle.

Do not place secret-bearing backups inside Git.

For SQLite backups:

- use the SQLite online backup API or `.backup`;
- do not copy a live WAL database unsafely;
- record SHA-256;
- record size;
- run integrity and foreign-key checks on the backup;
- open the backup using the current application schema code;
- perform a disposable restore probe.

For large media:

- record manifest and checksums;
- do not duplicate hundreds of gigabytes blindly if a verified snapshot already exists;
- state exactly what was and was not copied.

## Baseline tests

Run the full existing quality gate before edits.

Capture exact stdout/stderr and exit codes below:

```text
release-evidence/v0.10.0/baseline/
```

Required evidence:

- pytest;
- Ruff;
- type check;
- compileall;
- JS syntax;
- package build;
- installed-wheel smoke;
- pip check;
- database integrity;
- catalog integrity;
- schema manifest;
- secret scan;
- Git status;
- `snapims status`;
- `snapims doctor`;
- local `/health`;
- public SnapIMS endpoint;
- public Guacamole endpoint.

Do not enter or expose credentials during evidence capture.

## Architecture reconciliation report

Create:

```text
release-evidence/v0.10.0/baseline/ARCHITECTURE_RECONCILIATION.md
```

For every roadmap feature, mark:

- already implemented and verified;
- implemented but unverified;
- partially implemented;
- contradicted by current source;
- absent;
- obsolete;
- intentionally deferred.

Pay special attention to old claims about:

- Alt shortcuts;
- Tags;
- recognition escalation;
- Shopify idempotency;
- Settings;
- Firefox verification;
- current version;
- current production readiness.

## Branch and state

After preservation:

1. create/switch to `feature/v0.10.0-final-preproduction`;
2. create `V010_IMPLEMENTATION_STATE.md`;
3. commit only non-secret preservation metadata and baseline reports.

## Exit gate

Phase 0 passes only when:

- restore points are validated;
- unknown dirty changes are preserved;
- current schemas are known;
- current test state is recorded truthfully;
- current documentation contradictions are listed;
- no production secret/database/media is staged;
- the next phase can be resumed from the state file.


---

# FILE: 03_PHASE_1_STABILIZATION_SECURITY.md

# Phase 1 — Stabilization, Security and Truthful Orchestration

## Objective

Close critical defects in the v0.9 foundation before adding business-schema complexity.

## 1. CSRF and origin protection

Protect all state-changing browser operations:

- HTML form POSTs;
- JSON fetch POST/PUT/PATCH/DELETE;
- logout;
- Settings changes;
- recognition retries;
- CSV apply/cancel;
- checkpoint restore;
- future order/pick actions.

Requirements:

- cryptographically unpredictable token;
- session-bound or signed;
- constant-time validation where relevant;
- form hidden field and fetch header support;
- token rotation with session;
- invalid/missing token returns 403 without changing state;
- tests for cross-origin, missing, stale and wrong-session tokens;
- no token in URL or logs.

Validate expected Host/Origin for local and configured public access. Do not block legitimate Cloudflare forwarded HTTPS.

## 2. Login hardening

Implement:

- per-identity/IP bounded failed-login tracking;
- exponential or stepped backoff;
- no permanent denial from a few mistakes;
- safe audit events for success, failure, logout and session revocation;
- no attempted password storage;
- generic invalid-credential response;
- current password confirmation for security-sensitive Settings changes;
- session generation/version so password or signing-secret changes revoke existing sessions;
- secure cookie flags appropriate to HTTPS and local testing.

Add security headers:

- Content-Security-Policy;
- `X-Content-Type-Options: nosniff`;
- Referrer-Policy;
- Permissions-Policy;
- anti-framing policy compatible with intended deployment;
- no-store on login, Settings and secret responses.

## 3. Health and doctor truth

Distinguish:

- process is alive;
- database schema is healthy;
- application is locally healthy;
- background dependencies are degraded;
- tunnel connector is live;
- public hostname reaches expected application;
- service unavailable.

Required changes:

- `/health` returns non-200 for required schema/integrity failure;
- response includes stable machine-readable component states;
- service manager does not treat every HTTP 200 as healthy;
- `snapims doctor` returns nonzero when required checks fail;
- warning-only optional checks remain distinct;
- tunnel status checks process plus actual connector evidence;
- optional public endpoint checks confirm expected title/marker;
- Guacamole health confirms specific login/app markers;
- exact failure reason is printed safely.

Test:

- process alive but schema degraded;
- cloudflared PID alive but public route points to wrong/dead port;
- Guacamole returns generic HTML but not Guacamole;
- network unavailable;
- authentication redirect behaviour;
- cold boot and restart.

## 4. Managed-service boundaries

Ensure:

- `snapims up` is idempotent;
- `snapims down` stops only services/processes SnapIMS is configured to manage;
- external/manual cloudflared processes are not killed accidentally;
- PID files cannot target unrelated reused PIDs;
- process identity/command is verified before signal;
- stale PID cleanup is safe;
- xrdp may remain running if policy says SnapIMS does not own it;
- service ownership is visible in status.

## 5. Shopify outbound idempotency repair

Verify against current official Shopify GraphQL Admin API documentation.

For API 2026-07, `inventoryActivate` requires an idempotency key via `@idempotent`.

Requirements:

1. create stable logical attempt ID;
2. persist the idempotency key before the network request;
3. pass it in the GraphQL mutation;
4. reuse it on retry;
5. record request hash and response outcome;
6. never generate a second key for the same unfinished logical step;
7. reject multiple SKU matches instead of selecting first;
8. reconcile uncertain timeout outcomes before creating anything again.

Consider using `inventorySetQuantities` with compare-and-set only where SnapIMS is the intended quantity authority and the operation matches Shopify's current contract.

Injected-failure tests after:

- product create;
- variant config;
- inventory activation;
- quantity change;
- staged upload creation;
- file upload;
- media attachment;
- media processing poll;
- local final persistence.

Prove retries cannot create an unexplained duplicate draft.

## 6. Safe CLI update and shell

Implement:

```text
snapims update --check
snapims update --apply
```

`--check` reports:

- branch;
- upstream;
- dirty state;
- ahead/behind;
- incoming commits;
- current/target version;
- migration need;
- backup need;
- restart impact.

`--apply`:

- refuses dirty tree by default;
- creates restore metadata;
- backs up databases before migration;
- preserves branch;
- refuses detached or unknown destructive state;
- updates dependencies;
- runs migrations;
- restarts managed stack;
- verifies health;
- prints rollback instructions on failure.

Replace shell-string interpolation with argv-safe execution and safe `cwd`.

Define meaningful CLI exit codes and test them.

## 7. Shortcut truth and controlled Tags

Current source and historical documents must be reconciled.

Implement and verify in real Firefox:

- `Alt+P` opens command palette;
- `Alt+1` through `Alt+9` activate visible Batch Editor quick actions;
- no conflict with typing, Enter, Tab, arrows, browser navigation or IME;
- visible buttons remain;
- shortcut labels reflect actual mapping.

Restore the controlled Tags workflow if absent:

Schema:

- immutable Tag ID;
- canonical label;
- aliases;
- category;
- active/retired;
- AI eligible;
- Shopify visible;
- deterministic-only flag;
- sort order;
- created/updated evidence.

Item relationship:

- many-to-many Item ↔ approved Tag ID;
- source and timestamp;
- optional recognition attempt link;
- operator acceptance state.

UI:

- Tags between Price and Discount in compact Review;
- first-class Batch Editor Tags cell;
- autocomplete;
- keyboard arrows;
- Enter/comma accept;
- Backspace removes pill;
- Escape closes suggestions first;
- retired tags remain historical but cannot be newly selected.

AI:

- may return approved Tag IDs only;
- unknown values are rejected and logged as evidence;
- no taxonomy auto-creation;
- `Toonie Tapes` is deterministic owner/pricing logic, not creative AI classification.

## 8. Current documentation reconciliation

Update affected current v0.9 documents only after browser verification of these repairs. Do not yet call the release 0.10.0 until feature phases finish.

## Exit gate

- all critical stabilization tests pass;
- current workflows remain usable;
- cold boot still succeeds using `snapims up`;
- Firefox shortcut contract passes;
- CSRF tests pass;
- doctor/health failure truth passes;
- Shopify retry tests pass with fake transport;
- documentation no longer claims absent v0.9 behaviour;
- phase commit is created and state file updated.


---

# FILE: 04_PHASE_2_OBSERVABILITY.md

# Phase 2 — Operational Observability

## Objective

Allow an operator to see what SnapIMS is doing, why it is waiting or retrying, and what outcome occurred—without exposing private model reasoning or secrets.

## Operational event model

Create a durable, append-safe event store. Reuse a suitable existing audit table only if it can meet this contract cleanly.

Suggested fields:

- event ID;
- timestamp UTC;
- severity;
- component;
- event type;
- operation/correlation ID;
- parent/retry/recovery operation ID;
- Batch ID;
- Item ID;
- Movie ID;
- order ID;
- order line ID;
- reservation ID;
- pick task ID;
- provider;
- model;
- recognition tier;
- attempt number;
- duration milliseconds;
- image count and bytes;
- input/output tokens;
- configured CAD estimated cost;
- status/outcome;
- safe error class;
- safe summary;
- redacted structured detail JSON;
- process/session marker.

Index by time, component, severity, operation, Batch, Item and order.

Bound retention by policy. Preserve business/audit events longer than verbose debug events.

## Instrumentation

Emit events for:

- application startup/shutdown;
- migration and backup;
- login/logout/failure/revocation;
- Import preview/commit/duplicate handling;
- recognition queued/started/completed/failed/retried/escalated;
- catalog local hit/candidate request/ambiguity/failure/link;
- CSV stage/apply/cancel/rollback;
- bulk operation;
- Settings test/save/rollback;
- Shopify simulation and each outbound stage;
- order sync page and reconciliation;
- reservation transition;
- pick transition;
- fulfillment attempt;
- Cloudflare/Guacamole health and recovery;
- safe self-repair action.

Do not emit hidden chain-of-thought. Store only observable facts, configured rules, evidence and outcomes.

## Redaction service

Implement one shared redaction layer used by:

- log handlers;
- operational events;
- exception serializers;
- diagnostics export;
- support bundle;
- CLI output where technical detail is shown.

Redact:

- OpenAI keys;
- Shopify tokens;
- provider tokens;
- passwords;
- cookies;
- signed sessions;
- CSRF tokens;
- authorization headers;
- Cloudflare credentials;
- Guacamole credentials;
- secret environment values;
- credentials embedded in URLs;
- customer personal information not needed for support.

Test secrets embedded in:

- plain strings;
- nested dict/list JSON;
- headers;
- query strings;
- multiline traceback;
- exception messages;
- copied curl commands.

## CLI contract

Support both:

```text
snapims log
snapims logs
```

Options:

```text
--follow
--last N
--since 30m|2h|YYYY-MM-DDTHH:MM:SSZ
--errors
--severity LEVEL
--source app|recognition|catalog|shopify|import|cloudflare|guacamole|system|auth|inventory
--batch ID
--item ID
--order ID
--operation ID
--json
--export PATH
```

Multiple filters compose.

`--follow` should follow structured app events and optionally merge safe system/tunnel sources. It must degrade gracefully when system journals require unavailable permissions.

## In-app Live Activity

Add:

```text
Diagnostics → Live Activity
```

Features:

- active operations;
- queue depth;
- recent events;
- filters;
- correlation IDs;
- elapsed time;
- retry relationship;
- safe technical details;
- copy event;
- export support bundle;
- retry button only for explicitly safe recoverable operations;
- pagination or bounded polling/SSE;
- no unbounded DOM growth.

Support bundle includes:

- version/commit;
- schema manifest;
- redacted settings summary;
- latest relevant events;
- job states;
- health summary;
- no secrets;
- no complete customer data;
- no production image binaries unless explicitly selected.

## Logging files

Maintain rotating files:

- application;
- cloudflared;
- optionally consolidated JSONL events.

Use bounded file sizes and backup counts. Ensure log permissions do not expose secrets.

## Acceptance

- a recognition attempt can be traced from queue to result;
- a catalog miss shows query/candidates/rejection safely;
- a Shopify fake-transport failure shows exact stage and retry;
- duplicate import explains the existing Batch;
- tunnel failure shows connector vs origin distinction;
- secret fixtures do not appear in output or bundle;
- CLI filters return expected records;
- Live Activity survives restart using durable events;
- no private model reasoning is claimed or exposed.


---

# FILE: 05_PHASE_3_SECURE_SETTINGS.md

# Phase 3 — Secure Settings and Connection Wizards

## Objective

Make first-time and routine configuration possible inside SnapIMS without manual `.env` editing.

## Configuration architecture

Create an explicit configuration service with provenance.

Recommended precedence:

1. explicit process environment override;
2. permissions-restricted SnapIMS secret store;
3. persisted non-secret settings;
4. legacy project `.env`;
5. application default.

The UI must show where an effective non-secret value came from.

Do not silently overwrite externally managed environment settings.

## Secret store

Use an external path such as:

```text
~/SnapIMS-data/secrets/
```

Requirements:

- directory owner-only;
- files mode 0600;
- atomic temp-file + fsync + rename;
- timestamped backup before replacement;
- no secret returned after save;
- masked read model;
- administrator re-authentication;
- audit event names field only;
- redaction integration;
- session rotation for auth changes;
- safe migration from `.env`;
- rollback.

Do not delete legacy secret values automatically. Offer a validated migration and then tell the operator exactly what remains.

## Settings navigation

Create sections:

- General;
- Recognition;
- Shopify;
- Movie Data;
- Infrastructure;
- Security;
- Backup and Retention.

### Recognition

Fields:

- OpenAI key;
- provider;
- baseline model;
- escalation model;
- optional frontier model;
- confidence threshold;
- contradiction rules;
- maximum attempts;
- timeout;
- retry limit;
- image count/profile;
- prompt version;
- configured token price table and version;
- test connection;
- test image-capability/schema.

Model discovery:

- query official provider model list;
- do not assume every model accepts images;
- maintain capability registry;
- run a bounded image + strict-schema probe;
- allow manual model ID with test;
- save only tested-compatible models for recognition roles.

### Shopify wizard

Steps:

1. store domain;
2. Admin API token;
3. shop identity test;
4. configured API version;
5. capability/scope probe;
6. display exact missing permissions;
7. discover locations;
8. choose intended location;
9. enforce draft-only;
10. save securely;
11. simulation;
12. explicit link to live-draft acceptance—not automatic execution.

Verify current official API behaviour. Do not rely only on a hardcoded scope list.

### Movie Data

Fields:

- candidate provider;
- provider credential if needed;
- approved field profile;
- language/region;
- cache policy;
- refresh policy;
- Wikipedia/Wikimedia User-Agent including contact;
- request concurrency;
- rate limit;
- timeout/retries;
- candidate test;
- provenance preview;
- catalog bootstrap status;
- dump location and storage policy.

Wikimedia requests must use a meaningful User-Agent, serial/bounded concurrency, Retry-After handling and exponential backoff.

### Infrastructure

Mostly read-only:

- project path;
- data root;
- inventory DB;
- catalog DB;
- backup path;
- log path;
- local/public URLs;
- tunnel name/config;
- Guacamole URL;
- managed-service ownership;
- current service health;
- external endpoint status.

Do not expose credential file contents.

### Security

Support:

- change admin username/password;
- rotate signing secret;
- revoke all sessions;
- view safe login audit;
- Cloudflare Access status note;
- backup before credential replacement.

## Unsaved connection tests

Allow connection tests using unsaved values in memory. The browser must not receive the secret back in the response. Discard the test secret unless the operator explicitly saves.

## Validation and rollback

Every save:

- validates format;
- tests where selected;
- creates backup;
- writes atomically;
- reloads effective configuration;
- verifies result;
- records redacted event;
- offers rollback.

## Acceptance

A first-time operator can configure:

- OpenAI;
- models;
- Shopify;
- location;
- movie provider;
- Wikimedia identification;
- relevant thresholds;

entirely in the application, restart SnapIMS and retain effective settings securely.

No secret appears in:

- page source;
- URL;
- logs;
- diagnostics;
- support bundle;
- Git;
- error response.


---

# FILE: 06_PHASE_4_RECOGNITION_ROUTING.md

# Phase 4 — Recognition Control, Overrides and Staged Routing

## Objective

Use the cheapest model that is demonstrably reliable for routine tapes while preserving expert override, complete attempt history and manual authority.

## Attempt contract

Extend or replace the existing recognition result model without deleting history.

Each immutable attempt records:

- attempt ID;
- Item ID;
- provider;
- model;
- tier: baseline, escalation, frontier, manual;
- trigger;
- forced-by operator/system;
- prompt version;
- schema version;
- image profile;
- image IDs/hashes/count/bytes;
- response reference;
- exact title proposal or `UNKNOWN`;
- year/edition/distributor/barcode evidence;
- approved Tag ID suggestions;
- confidence;
- uncertainty;
- contradiction flags;
- input/output tokens;
- configured CAD cost;
- latency;
- accepted/rejected/superseded state;
- accepted timestamp and actor;
- relationship to prior attempt.

Never delete prior attempts.

## Recognition workspace

Add top-level:

```text
Recognition
```

Show:

- current jobs;
- queue;
- model ladder;
- attempts by Batch and Item;
- failed/blocked/unsupported;
- low-confidence;
- contradiction filters;
- estimated/actual usage and CAD cost;
- run unfinished;
- run selected;
- force rerun;
- escalate selected;
- pause/resume where safe;
- benchmark mode;
- comparison report.

## Review controls

For every Item, including already successful/approved Items:

- Run Recognition Again;
- choose provider;
- choose tested image-capable model;
- choose tier;
- choose image profile/subset;
- escalate;
- compare attempts;
- select attempt as current suggestion;
- accept selected attempt into working fields;
- clear current suggestion without deleting history.

Rules:

- later attempt does not overwrite approved working values automatically;
- accepting a new attempt is explicit;
- physical Item ID remains unchanged;
- successful results may be rerun;
- repeated click is idempotent and does not start duplicate active attempts.

## Router

### Stage 0 — deterministic preparation

- use recognition derivatives, not originals unless explicitly chosen;
- deduplicate by hash;
- front first;
- bounded additional spine/back/support;
- record selected images;
- preserve all originals.

### Stage 1 — baseline

- lowest-cost tested model;
- strict JSON schema;
- exact title evidence;
- allowed to return `UNKNOWN`;
- approved Tag IDs only;
- no slogans/taglines as titles.

### Stage 2 — escalation

Trigger when:

- title missing;
- `UNKNOWN`;
- confidence below measured threshold;
- schema invalid;
- front/spine/back contradiction;
- catalog contradiction;
- same-title/year ambiguity;
- unsupported media uncertainty;
- operator request.

Use more/better images only when useful.

### Stage 3 — frontier exception

Use only for measured hard cases. Keep cost visible and bounded.

### Stage 4 — operator

Manual resolution is authoritative.

## Duplicate import overrides

Default remains:

```text
Open existing durable Batch; do not duplicate inventory.
```

When fingerprint matches, offer:

1. Open Existing Batch;
2. Re-run Unfinished;
3. Re-run All;
4. Create Isolated Test Copy;
5. Cancel.

Re-run All:

- same Item IDs;
- new attempts;
- no duplicate inventory;
- preserves approved values until explicit replacement.

Test Copy:

- separate Batch ID;
- test provenance;
- cannot publish;
- cannot reserve;
- visibly quarantined;
- links to source fingerprint/original Batch;
- safe for model comparison.

## Benchmark

Create a benchmark workflow with owner-labelled truth.

Dataset classes:

- clear mainstream;
- sequels/remakes;
- damaged/low contrast;
- slogan-heavy;
- music/concert;
- TV/anime;
- unusual edition;
- unsupported media.

Measure:

- exact-title accuracy;
- false confidence;
- operator correction;
- escalation rate;
- manual rate;
- latency;
- token use;
- image bytes;
- CAD cost;
- catalog agreement;
- operator time.

Do not claim quality from unlabelled synthetic outputs.

## Cost model

Store configured model price table with effective date/version. Estimated cost must state that it is calculated from configured prices, not provider billing truth.

## Failure/restart

Test:

- process stops during attempt;
- network timeout;
- 429 with Retry-After;
- invalid response;
- model unavailable;
- provider key rejected;
- app restart;
- duplicate force-click;
- accepting older attempt after newer attempt;
- stale browser.

## Acceptance

- successful Item can be rerun;
- two models can be compared without changing approved value;
- no history loss;
- `UNKNOWN` works;
- obvious tapes usually stay baseline;
- difficult tapes route upward or manual;
- cost and latency are visible;
- duplicate test copy is quarantined;
- restart recovers state.


---

# FILE: 07_PHASE_5_INVENTORY_SEARCH.md

# Phase 5 — Global Inventory Search and Physical Item Retrieval

## Objective

Make every owned tape findable and retrievable regardless of original Batch.

## Navigation

Add top-level:

```text
Inventory
```

Add global command-palette search.

Do not overload Batch Editor search; Batch Editor remains batch-scoped.

## Search contract

Search across all inventory by:

- working title;
- canonical Movie title;
- aliases;
- suggested titles;
- year;
- edition;
- distributor;
- Item ID;
- SKU;
- barcode;
- shelf/location;
- Batch ID;
- Shopify product ID;
- Shopify variant ID;
- Shopify inventory item ID;
- Movie ID;
- Edition ID;
- Review/recognition/catalog state;
- physical availability;
- reservation;
- pick state;
- condition;
- price;
- approved Tags;
- rare/review flags.

Use server-side SQL. Add indexes and FTS5 where appropriate.

Requirements:

- bounded page size;
- deterministic sort;
- stable query parameters;
- pagination/keyset where practical;
- no full-inventory DOM;
- lazy thumbnails/details;
- query timing event;
- safe empty/error states;
- accessible keyboard workflow.

## Physical availability state machine

Implement explicit validated states, adapting names to existing schema:

- AVAILABLE;
- RESERVED;
- PICKED;
- PACKED;
- FULFILLED or SOLD;
- MISSING;
- QUARANTINED;
- HOLD;
- RELEASED/CANCELLED as historical transitions.

Do not use one free-form string without transition validation.

Rules:

- quantity cannot be negative;
- one exact Item cannot have multiple active exclusive reservations;
- sold/fulfilled Item cannot return to available without explicit documented reversal;
- missing/quarantined Item cannot be newly reserved;
- every transition records source, reason, operation and timestamp.

## Result row

Show:

- thumbnail;
- title/year;
- Item ID;
- SKU;
- location;
- state/reservation;
- condition;
- price;
- Shopify state;
- last movement/update.

Title search results must still resolve to one physical Item per row.

## Item detail

Include:

- all photos;
- immutable identity;
- Batch and sequence;
- location and complete movement history;
- quantity adjustments;
- condition;
- Review state/history;
- recognition attempts and selected attempt;
- Movie and Edition;
- source provenance;
- approved Tags;
- Shopify IDs/admin link;
- order/reservation/pick relationships;
- availability state;
- audit events.

Actions:

- move location with required reason;
- adjust quantity with required reason;
- mark missing;
- quarantine;
- hold/release;
- re-recognize;
- open Review;
- open source Batch;
- open Shopify Admin.

Use optimistic revision. Reject stale tabs.

## Batch Editor scale repair

The existing full-DOM editor is not a proven warehouse design.

During this phase, implement at least a bounded architecture:

- server-side filter/sort/search;
- bounded page/window;
- compact payload;
- deterministic physical sequence;
- explicit bulk selection semantics:
  - current page;
  - filtered result set;
  - explicit selected IDs;
- thumbnails lazy loaded;
- no multi-megabyte all-row HTML.

Measure 20, 500 and 5,000 row fixtures, but only claim supported scale that passes on target hardware.

## API

Add stable internal endpoints for:

- search;
- paged inventory;
- Item detail;
- movement;
- status transition;
- reservation-read information.

All state-changing endpoints require CSRF/auth/optimistic revision.

## Acceptance

- title search finds duplicate physical copies as separate rows;
- Item ID, SKU, barcode and shelf search work;
- exact location is visible;
- move requires reason and persists after restart;
- stale update is rejected;
- missing/quarantine blocks reservation;
- pagination keeps DOM bounded;
- 500 and 5,000 fixture evidence is truthful;
- no physical identity changes.


---

# FILE: 08_PHASE_6_MOVIE_DATABASE.md

# Phase 6 — Rights-Respecting Movie Database Acquisition and Catalog Completion

## Objective

Build a useful permanent local Movie database from rights-approved structured sources without copying a proprietary provider database or slowing Review.

## Data-source decision

Initial structured candidate source:

```text
Wikidata
```

Reason:

- structured data;
- CC0;
- official APIs and dumps;
- commercial reuse allowed for structured data;
- external QIDs remain references, not local identity.

Bounded enrichment source:

```text
English Wikipedia through official MediaWiki APIs
```

Do not:

- scrape IMDb;
- use DBpedia as the primary production source;
- use TMDb commercially without an approved agreement;
- mirror full Wikipedia article text;
- copy another provider's proprietary database;
- use unlicensed artwork.

## Provider-neutral contract

Define:

```text
search(title, year, region, media_type, limit) -> candidates
fetch(candidate_id, approved_fields) -> normalized facts + provenance
health() -> provider/capability state
policy() -> licence, attribution, retention, refresh and field policy
```

Provider IDs are not SnapIMS Movie IDs.

## Local-first flow

```text
AI/operator title
→ local Movie/alias FTS search
→ unique local match: reuse
→ otherwise Wikidata candidate search
→ optional bounded Wikipedia enrichment
→ ambiguity/unsupported: operator queue
→ durable local Movie
→ exact physical Item link
```

External calls run asynchronously after approval and must not delay `Approve & Next`.

## Wikidata API client

Requirements:

- official endpoint;
- meaningful User-Agent with SnapIMS version and contact URL/email configured in Settings;
- JSON;
- gzip;
- serial or max three concurrent requests;
- Retry-After handling;
- exponential backoff;
- timeout;
- cache;
- operation logging;
- bounded candidate count;
- no regex SPARQL text search;
- avoid high-cost open-ended queries.

Approved fields may include:

- label/canonical title;
- aliases;
- original title;
- release date/year;
- runtime;
- director;
- bounded cast;
- genre;
- country;
- language;
- media type evidence;
- English Wikipedia sitelink;
- provider revision/retrieval evidence.

Do not ingest unrelated claims.

## Wikipedia enrichment

After candidate selection or material uniqueness:

- use official Action/REST APIs;
- resolve redirect;
- identify disambiguation;
- retrieve page ID, revision, URL, title and bounded factual summary;
- descriptive User-Agent;
- rate/timeout/retry controls;
- store provenance;
- no complete article;
- no direct copied article prose as Shopify marketing description;
- preserve attribution metadata.

## Catalog states

Distinguish:

- LOCAL_MATCH;
- NEW_EXTERNAL_RECORD;
- AMBIGUOUS;
- SUPPORTED_FILM_NOT_FOUND;
- UNSUPPORTED_MEDIA_TYPE;
- CANDIDATES_REJECTED;
- PROVIDER_UNAVAILABLE;
- RATE_LIMITED;
- MALFORMED_RESPONSE;
- RETRY_QUEUED;
- MANUAL_MATCH_REQUIRED.

Do not collapse every case into `NOT_FOUND`.

## Minimum Edition model

Before 1.0 implement only needed VHS edition data:

- Edition ID;
- Movie ID;
- format;
- distributor;
- release year/date where known;
- barcode;
- packaging/edition text;
- language/region clues;
- source/evidence;
- physical Item relationship.

Do not delay this release on a complete collector-research workspace.

## CLI

Implement:

```text
snapims catalog status
snapims catalog init
snapims catalog bootstrap --from-inventory
snapims catalog bootstrap --title-list PATH
snapims catalog download wikidata --latest --destination PATH
snapims catalog import wikidata --source PATH --resume
snapims catalog sync-incremental
snapims catalog verify
snapims catalog backup
snapims catalog rebuild-index
```

Exact syntax may follow current parser conventions.

## Required production bootstrap

`bootstrap --from-inventory` is required and must be usable immediately.

It:

- finds distinct reviewed/current titles;
- includes year/media clues;
- checks local catalog first;
- calls external source only on genuine miss;
- preserves ambiguity;
- is restart-safe;
- is asynchronous/bounded;
- creates a report;
- never changes physical identity;
- can run against a verified production database or owner-approved copy.

Run it against a safe verified copy during implementation. Live production catalog bootstrap requires normal backup and owner awareness but is not a destructive external write.

## Optional full Wikidata dump

Implement support, but do not silently launch it.

Official source discovery must occur at runtime.

Before download:

1. inspect latest official dump metadata;
2. obtain compressed size;
3. inspect free space;
4. estimate temporary and imported size;
5. require `--yes` and/or `SNAPIMS_ALLOW_LARGE_CATALOG_DOWNLOAD=1`;
6. refuse safely if space is insufficient.

Downloader:

- HTTP Range resume;
- `.part`;
- atomic rename;
- official checksum validation where available;
- progress, speed, ETA;
- bounded retry;
- lock;
- no Git path;
- operational events.

Importer:

- stream BZ2/GZip JSON;
- do not load full dump;
- handle JSON-array framing;
- periodic transactions;
- durable checkpoint;
- restart/resume;
- extract only supported entities/fields;
- report scanned/accepted/rejected/malformed;
- avoid expensive per-entity network calls;
- store dump date/version;
- final integrity and FTS verification.

Incremental dumps:

- support official add/change dumps where practical;
- apply idempotently;
- keep source version/cursor;
- recover after interruption.

If full dump is too large:

- implement and test with bounded official sample/fixture;
- execute inventory-driven bootstrap;
- report actual remote size and local free space;
- print exact later command;
- do not claim full database import.

## Search/index

Use `movie_catalog.sqlite3`.

Preserve existing Movies and aliases. Add migrations, not recreation.

Required constraints:

- unique local Movie ID;
- provider-source uniqueness;
- title/year/media safeguards;
- aliases;
- FTS;
- source provenance;
- candidate decisions;
- no duplicate Movie from restart/retry.

## Acceptance

- clear supported film creates one durable Movie;
- second copy reuses local Movie without external request;
- same-title different-year remains distinct;
- unsupported media remains inventory but not forced into Movie;
- provider failure leaves Review operational;
- restart resumes jobs;
- correction/relink preserves history;
- every external field has provenance;
- inventory-driven database bootstrap completes;
- full-dump command is guarded and resumable;
- no proprietary or unlicensed data source is used.


---

# FILE: 09_PHASE_7_SHOPIFY_ORDERS_PICKING.md

# Phase 7 — Shopify Drafts, Orders, Reservations, Picking and Fulfillment

## Objective

Complete the loop from exact physical Item to Shopify draft, Shopify order, reservation, pick task and deliberate fulfillment.

## Outbound draft UI

Expose the existing safe service through Publish:

- simulation;
- exact payload preview;
- blockers;
- field values;
- image count;
- draft-only status;
- deliberate Item-level confirmation;
- Create Shopify Draft;
- durable stage progress;
- retry/reconcile;
- Shopify Admin link.

Do not publish storefront products automatically.

Exactly one live draft may be created only after explicit owner approval.

## Current API verification

At implementation time inspect current official Shopify GraphQL Admin documentation for configured API version.

Known 2026-07 considerations:

- `inventoryActivate` requires `@idempotent(key: ...)`;
- inventory quantity mutations may require idempotency and compare-and-set;
- `fulfillmentCreate` operates on Fulfillment Orders;
- webhooks do not guarantee ordering.

Use official current contracts, not stale examples.

## Capability probe

Settings must verify actual access to:

- products;
- inventory;
- locations;
- orders;
- merchant-managed fulfillment orders;
- webhook subscription if enabled.

Display exact missing permission/capability.

## Data model

Add durable entities:

- Shopify order;
- order revision;
- order line;
- sync cursor/request;
- listing link;
- reservation;
- pick task;
- fulfillment attempt;
- webhook delivery;
- reconciliation event.

Store only operationally required customer information.

Do not show or log unnecessary personal data.

Order data includes:

- order GID;
- order name/number;
- updated timestamp;
- cancellation state;
- financial/allocation status;
- fulfillment state;
- line GID;
- variant ID;
- inventory item ID;
- quantity;
- payload hash;
- sync state/error.

## Order polling

Implement:

```text
snapims shopify status
snapims shopify sync-orders
snapims shopify sync-orders --since TIME
```

In-app:

```text
Orders → Sync Now
```

Use GraphQL cursor pagination and updated-time reconciliation.

Requirements:

- idempotent;
- restart-safe;
- checkpointed;
- duplicate-safe;
- rate-limit aware;
- handles partial page failure;
- handles out-of-order updates;
- stores payload hash/revision;
- safe manual rerun.

Polling remains authoritative reconciliation even if webhooks are enabled.

## Optional webhooks

Support order create/update/cancel topics as acceleration.

Requirements:

- verify HMAC against raw body before parsing;
- constant-time comparison;
- record webhook ID;
- deduplicate;
- validate topic/version headers;
- acknowledge quickly;
- queue durable processing;
- do not assume ordering;
- do not treat webhook delivery as complete reconciliation;
- keep polling.

Webhook exposure is opt-in and documented.

## Exact physical mapping

Resolve:

```text
Shopify Variant/Inventory ID
→ durable Listing Link
→ exact SnapIMS Item ID
```

Never match by title.

Reject ambiguous/missing mapping and create visible exception.

Before future pooling/substitution exists:

- do not silently substitute another copy;
- one order-line unit gets one exact Item reservation.

## Reservation state

Rules:

- one active exclusive reservation per Item;
- transactional uniqueness;
- no negative availability;
- no reservation for MISSING/QUARANTINED/SOLD;
- cancellation releases unpicked reservation when policy allows;
- picked reservation is not silently released;
- every transition audited;
- duplicate sync creates no duplicate reservation.

## UI

Add top-level:

- Orders;
- Pick Queue.

Order list/detail:

- order number;
- updated/sync state;
- relevant line items;
- exact Item allocations;
- reservation;
- exception;
- fulfillment;
- safe Shopify links.

Pick Queue:

- order number;
- title;
- thumbnail;
- Item ID;
- SKU;
- exact shelf/bin;
- quantity;
- task state;
- exception;
- confirm action.

State machine:

```text
NEW → RESERVED → PICKED → PACKED → FULFILLED
```

Exception/history:

```text
HOLD
MISSING
CANCELLED
RELEASED
```

Use validated transitions.

## Pick actions

- Confirm Picked;
- Mark Missing;
- Place On Hold;
- Confirm Packed;
- Release Reservation when allowed;
- open Item;
- open Order;
- deliberate Fulfill.

Missing action must make order exception visible and block silent completion.

## Fulfillment

Use current official `fulfillmentCreate`.

Requirements:

- explicit operator confirmation;
- correct Fulfillment Order IDs;
- exact line item quantities;
- local logical attempt ID;
- duplicate/retry protection;
- durable Shopify result;
- customer notification default off unless explicitly selected;
- safe error/reconciliation path.

Do not auto-fulfill when picked.

## Failure tests

- duplicate polling;
- same order update twice;
- page interruption;
- cancellation before pick;
- cancellation after pick;
- missing Item;
- stale pick screen;
- duplicate webhook;
- wrong HMAC;
- webhook out of order;
- missed webhook recovered by polling;
- fulfillment timeout;
- uncertain fulfillment result;
- duplicate fulfillment click;
- app restart at every state.

## Acceptance

- imported order resolves exact Item;
- Pick Queue shows shelf;
- duplicate sync creates no duplicate task;
- cancellation releases eligible reservation;
- picked state survives restart;
- missing creates exception;
- no negative availability;
- stale transition rejected;
- webhook duplicate ignored;
- polling reconciles missed webhook;
- fulfillment requires confirmation;
- live write remains owner-gated.


---

# FILE: 10_PHASE_8_SCALE_ACCEPTANCE.md

# Phase 8 — Scale, Recovery and Production-Candidate Acceptance

## Objective

Verify that the combined v0.10.0 system is stable at its claimed scale and prepare the separate physical/live 1.0 acceptance program.

## Performance work

### Batch Editor

Measure:

- query;
- server render/API;
- response size;
- DOM nodes;
- first interactive time;
- search/filter/sort;
- cell save;
- thumbnail loading;
- bulk operation.

Fixtures:

- 20 Items;
- 500 Items;
- 5,000 Items.

Do not claim 5,000-row support unless target hardware/browser passes bounded rendering without freeze.

### Import

Profile:

- file enumeration;
- EXIF;
- hashing;
- image decode;
- downsample;
- QR detect/decode;
- copying;
- derivative generation;
- DB insertion.

Fixtures:

- realistic 20-tape;
- synthetic 500;
- synthetic 5,000/10,000-photo only for architecture evidence.

Optimize by measurement. Preserve exact QR semantics.

### Inventory Search

Measure duplicate-title, broad query and exact ID lookup.

### Catalog

Measure local hit vs external miss.

### Orders/Pick

Measure sync and queue rendering using fixtures with many order lines.

## Recovery matrix

Inject interruption during:

- migration;
- import;
- recognition;
- catalog fetch;
- dump download;
- dump import;
- CSV apply;
- bulk operation;
- Settings write;
- Shopify draft stages;
- order sync page;
- reservation;
- pick transition;
- fulfillment.

After restart verify:

- no duplicate identity;
- exact state;
- resumable operation;
- visible event;
- no partial hidden outcome.

## Browser matrix

Use native Firefox on production host. Also use automated Chromium/Firefox where supported.

Sizes:

- desktop target viewport;
- smaller laptop;
- mobile for supported pages only.

Monitor:

- console;
- page errors;
- failed network;
- HTTP errors;
- focus;
- double submit;
- stale state.

Walkthrough:

1. login/logout/backoff;
2. CSRF rejection;
3. Import;
4. duplicate options;
5. recognition baseline;
6. rerun success;
7. compare/escalate;
8. approved Tags;
9. Approve & Next;
10. Batch Editor;
11. Inventory Search;
12. Item detail/move;
13. catalog local hit/ambiguity;
14. Settings;
15. Live Activity;
16. CSV;
17. Publish simulation;
18. fake draft failure/retry;
19. order sync;
20. reservation;
21. Pick Queue;
22. cancellation;
23. restart;
24. public endpoint;
25. Guacamole remains operational.

## Security verification

- CSRF;
- login throttle;
- session rotation;
- secret redaction;
- file permissions;
- public origin;
- headers;
- webhook HMAC;
- support bundle;
- no accidental public database/media directory;
- no secret in release archive.

## Cold boot

On target host:

```bash
sudo reboot
```

After reconnecting, run only:

```bash
snapims up
snapims status
snapims doctor
```

Verify local/public application and Guacamole.

## 1.0 production gates remain pending until performed

Do not label 1.0 until:

- real 20-tape Pixel pilot;
- live AI measured;
- CSV physically reconciled;
- restart durability against that real batch;
- exactly one authorized Shopify draft inspected;
- first-time operator guide walkthrough;
- final browser verification;
- no known production blocker for claimed scale.

Create a detailed acceptance checklist and evidence folders so the owner can perform these without further architecture changes.

## Exit gate

- quality gate green or failures explicitly blocked;
- bounded scale claims supported by evidence;
- interruption matrix passes;
- cold boot passes;
- all owner-gated live actions are listed;
- no hidden production blocker;
- feature freeze begins after this phase.


---

# FILE: 11_PHASE_9_DOCUMENTATION_RELEASE.md

# Phase 9 — Documentation Synchronization, Versioning and Release Package

## Objective

Make the application, Operator Guide, screenshots, release documents and version metadata describe the exact same product.

## Version classification

This package adds operator workflows, schema and external-system integration.

Classification:

```text
Minor release: 0.9.0 → 0.10.0
```

Do not use 0.9.1 for the completed combined package.

Do not use 1.0.0.

## Synchronize version everywhere

Update:

- package version;
- `snapims.__version__`;
- browser footer/header;
- README;
- Release Notes;
- Operator Guide;
- Installation Guide;
- Deployment Guide;
- Developer Guide;
- Test Results;
- Browser Verification;
- Production Readiness;
- roadmap;
- archive names;
- generated screenshot captions;
- service/about output.

Search the active repository for obsolete version references. Historical archived reports may retain their historical version only if clearly under a history/archive path and not presented as current.

## Operator Guide

Use final browser UI as source of truth.

Assume first-time operator.

Cover:

- install/start;
- login;
- Import;
- duplicate Batch options;
- Recognition;
- model routing;
- force rerun;
- compare attempts;
- approved Tags;
- Review;
- Batch Editor;
- Inventory Search;
- Item detail and location move;
- Movie/catalog status;
- Settings;
- logs/Live Activity;
- CSV;
- Shopify setup;
- draft workflow;
- Orders;
- Pick Queue;
- missing/cancelled exceptions;
- recovery;
- cold boot;
- end-of-batch checklist;
- 1.0 acceptance boundaries.

Replace every affected screenshot at full useful resolution. Do not crop away important controls.

## Documentation walkthrough

After updating the guide:

1. use a clean browser session;
2. follow it step by step;
3. verify every label/button/path;
4. verify screenshots;
5. fix discrepancy;
6. repeat affected steps.

Do not claim guide verification from source review alone.

## Release evidence

Create:

```text
release-evidence/v0.10.0/
```

Include:

- baseline;
- tests;
- browser;
- Firefox;
- security;
- migration;
- database;
- scale;
- cold-boot;
- screenshots;
- support bundle sample;
- final report;
- production readiness;
- unresolved owner gates.

Sanitize evidence.

## Release archive

Build source/release archive excluding:

- `.git`;
- `.env`;
- secrets;
- production DB;
- WAL/SHM;
- media;
- logs;
- caches;
- cloud credentials;
- Guacamole credentials;
- backups.

Scan archive contents and extracted copy.

## Git completion

Before final commit:

```bash
git status
git diff --check
git diff --stat
```

Review all files.

Commit synchronized release.

Push branch:

```bash
git push -u origin feature/v0.10.0-final-preproduction
```

Do not merge automatically.

Do not create/tag `v1.0.0`.

A `v0.10.0` tag should only be created if the owner explicitly requests tagging after reviewing the release candidate.

## Final report

Use `14_FINAL_REPORT_TEMPLATE.md`.

State separately:

- implemented and verified;
- implemented but owner-live-gated;
- not implemented;
- deferred post-1.0;
- known risks;
- exact 1.0 blockers.

## Exit gate

- all active docs use 0.10.0;
- final UI and guide match;
- screenshots current;
- archive clean;
- tests/evidence referenced;
- branch pushed;
- working tree clean;
- 1.0 remains prohibited until acceptance gates pass.


---

# FILE: 12_IMPLEMENTATION_STATE_TEMPLATE.md

# V010_IMPLEMENTATION_STATE

## Repository

- Project:
- Branch:
- HEAD:
- Upstream:
- Started:
- Last updated:
- Current application version:
- Inventory schema:
- Catalog schema:

## Preservation

- Backup root:
- Inventory backup:
- Catalog backup:
- Media manifest:
- Secret/config backup:
- Git preservation:
- Integrity result:
- Restore probe:

## Current phase

- Phase:
- Phase file:
- Status: NOT STARTED | IN PROGRESS | BLOCKED | COMPLETE
- Latest verified commit:
- NEXT_PHASE:
- NEXT_ACTION:

## Completed criteria

- [ ]

## Migrations

| Migration | Database | Backup | Applied to disposable copy | Applied to production | Verification |
|---|---|---|---|---|---|

## Tests

| Command/test | Result | Evidence path | Notes |
|---|---|---|---|

## Browser verification

| Workflow | Browser | Result | Evidence |
|---|---|---|---|

## External actions

| Action | Owner approval required | Approved | Result |
|---|---|---|---|

## Known failures

| ID | Severity | Reproduction | Current state | Next action |
|---|---|---|---|---|

## Owner decisions

| Decision | Choice | Date | Consequence |
|---|---|---|---|

## Files/areas currently being edited

-

## Resume checklist

1. Verify branch and HEAD.
2. Verify working tree.
3. Verify latest phase commit.
4. Run focused tests.
5. Read current phase acceptance criteria.
6. Continue first incomplete item.


---

# FILE: 13_ACCEPTANCE_CHECKLIST.md

# SnapIMS v0.10.0 Acceptance Checklist

## Phase 0

- [ ] Current branch/commit recorded.
- [ ] Dirty work preserved.
- [ ] Inventory and catalog backups validated.
- [ ] Media/config manifest created.
- [ ] Baseline tests captured.
- [ ] Architecture contradictions registered.

## Stabilization

- [ ] CSRF protects all state changes.
- [ ] Login throttle/audit works.
- [ ] Session revocation works.
- [ ] Security headers verified.
- [ ] Degraded schema produces failed health.
- [ ] Doctor exits nonzero on required failure.
- [ ] Tunnel public-route failure is detected.
- [ ] Shopify idempotency key passed and persisted.
- [ ] Duplicate SKU ambiguity rejected.
- [ ] Update check/apply safe.
- [ ] Shell path handling safe.
- [ ] Alt+P works in Firefox.
- [ ] Alt+1–9 works in Firefox.
- [ ] Approved Tags workflow exists and is documented.
- [ ] Cold boot remains one-command.

## Observability

- [ ] `snapims log` alias works.
- [ ] CLI filters compose.
- [ ] Live Activity exists.
- [ ] Operation IDs correlate jobs.
- [ ] Redaction adversarial tests pass.
- [ ] Support bundle contains no secrets.
- [ ] Rotation/retention bounded.

## Settings

- [ ] Secret store permissions correct.
- [ ] Atomic save/backup/rollback works.
- [ ] Re-authentication required.
- [ ] OpenAI configuration works.
- [ ] Image-capable model probe works.
- [ ] Shopify wizard and location discovery work.
- [ ] Scope/capability failures are exact.
- [ ] Movie provider/Wikimedia settings work.
- [ ] Restart retains settings.
- [ ] No secret is returned or logged.

## Recognition

- [ ] Successful Item can be rerun.
- [ ] Attempt history immutable.
- [ ] Compare models without changing approved values.
- [ ] `UNKNOWN` supported.
- [ ] Baseline/escalation/frontier routing works.
- [ ] Approved Tag IDs only.
- [ ] Duplicate Batch rerun scopes work.
- [ ] Test copy is quarantined.
- [ ] Benchmark report works with labelled truth.
- [ ] Restart recovery works.

## Inventory

- [ ] Global title search.
- [ ] Item ID search.
- [ ] SKU search.
- [ ] Barcode search.
- [ ] Location search.
- [ ] Shopify ID search.
- [ ] Duplicate copies remain separate rows.
- [ ] Item detail includes history.
- [ ] Move requires reason.
- [ ] Stale edit rejected.
- [ ] Missing/quarantine state enforced.
- [ ] Results bounded/paginated.
- [ ] Scale evidence truthful.

## Movie database

- [ ] Provider-neutral interface.
- [ ] Wikidata candidate search.
- [ ] Wikimedia User-Agent/rate handling.
- [ ] Bounded Wikipedia enrichment.
- [ ] Local-first reuse.
- [ ] Ambiguity preserved.
- [ ] Unsupported media distinct.
- [ ] Inventory-driven bootstrap.
- [ ] Title-list bootstrap.
- [ ] Optional dump downloader guarded.
- [ ] Resume/checksum/storage gates.
- [ ] Streaming importer.
- [ ] Incremental support where practical.
- [ ] Every external field has provenance.
- [ ] Second copy causes no unnecessary request.

## Shopify and picking

- [ ] Draft simulation.
- [ ] Deliberate draft UI.
- [ ] One live draft remains owner-gated.
- [ ] Order polling idempotent.
- [ ] Optional webhooks HMAC/dedupe.
- [ ] Polling reconciles missed webhooks.
- [ ] Exact listing link maps to Item.
- [ ] Exclusive reservation.
- [ ] Cancellation release.
- [ ] Pick Queue shows exact shelf.
- [ ] Missing exception.
- [ ] Packed state.
- [ ] Fulfillment confirmation.
- [ ] Duplicate fulfillment protected.
- [ ] Restart persistence.

## Verification and release

- [ ] Full pytest.
- [ ] Ruff.
- [ ] Type check.
- [ ] Compileall.
- [ ] JS syntax.
- [ ] Build.
- [ ] Installed smoke.
- [ ] Pip check.
- [ ] DB integrity.
- [ ] Catalog integrity.
- [ ] Secret/archive scan.
- [ ] Native Firefox walkthrough.
- [ ] Cold boot.
- [ ] Operator Guide synchronized.
- [ ] Screenshots replaced.
- [ ] Guide walkthrough repeated.
- [ ] Every active document says 0.10.0.
- [ ] Branch pushed.
- [ ] 1.0 gate remains separate.


---

# FILE: 14_FINAL_REPORT_TEMPLATE.md

# SnapIMS v0.10.0 Implementation Report

## Executive result

- Final status:
- Release classification:
- Final version:
- Production 1.0 status:
- Starting branch/commit:
- Ending branch/commit:

## Files changed

Group by:

- application;
- database/migrations;
- tests;
- scripts/deployment;
- documentation;
- release evidence.

## Implemented features

### Stabilization/security

### Observability

### Settings

### Recognition

### Inventory

### Movie database

### Shopify/orders/picking

## Schema changes

For each migration:

- database;
- from/to version;
- tables/columns/indexes/constraints;
- data migration;
- backup;
- interruption handling;
- rollback/forward repair;
- integrity result.

## Database acquisition

- Wikidata API implementation:
- inventory bootstrap result:
- titles processed:
- Movies created/reused:
- ambiguous:
- unsupported:
- external requests:
- full dump downloader status:
- full dump size/free-space result:
- full dump imported: YES/NO
- incremental status:

## Tests

- pytest:
- Ruff:
- type:
- compileall:
- JS:
- build:
- pip:
- integrity:
- archive scan:

## Browser verification

List exact workflows and browsers.

## Live external verification

- OpenAI:
- Shopify simulation:
- Live Shopify draft:
- Order sync:
- Cloudflare:
- Guacamole:

Do not mark owner-gated actions as PASS unless actually performed.

## Cold boot

- Commands:
- status:
- doctor:
- public URLs:

## Documentation synchronization

- Operator Guide:
- screenshots:
- README:
- release notes:
- test report:
- browser report:
- production readiness:
- other documents:
- final consistency search:

## Git

- commits:
- push:
- PR:
- tag:

## Known issues and remaining 1.0 gates

Explicitly list all.

## Manual owner actions

Provide exact commands/UI steps only for actions that could not be completed.

## Final verdict

State whether 0.10.0 is:

- implementation complete;
- release candidate;
- blocked;
- ready for physical/live acceptance.

Do not call it 1.0.0.


---

# FILE: 15_RESUME_PROMPT.md

# Codex Resume Prompt

Copy this into a new Codex session:

```text
Resume the SnapIMS v0.10.0 implementation.

Repository: ~/Projects/SnapIMS

Read:
- docs/codex-work-orders/v0.10.0/01_MASTER_CONTROLLER.md
- V010_IMPLEMENTATION_STATE.md
- the phase file identified by NEXT_PHASE
- any referenced acceptance contract

Before editing, run:
git status --short
git branch --show-current
git rev-parse HEAD
git log -3 --oneline

Confirm that HEAD matches the latest verified commit in the state file or explain the discrepancy. Run the focused tests for the last completed phase. Continue from NEXT_ACTION. Preserve all existing work. Do not repeat completed migrations or external writes. Update the state file and commit the next verified bounded milestone.
```


---

# FILE: 16_OWNER_APPROVAL_GATES.md

# Owner Approval Gates

Codex must stop and request explicit owner approval for these actions.

## Live Shopify write

Includes:

- creating a real draft;
- changing live inventory;
- importing real orders if the owner has not authorized the connection;
- creating fulfillment;
- webhook subscriptions that modify live app configuration.

Before asking, Codex must present:

- exact operation;
- exact Item/order;
- dry-run result;
- expected external effect;
- rollback/reconciliation plan;
- scope/capability status.

## Full Wikidata dump

Before asking, present:

- official remote file;
- compressed size;
- checksum source;
- available disk;
- estimated temporary/import storage;
- expected runtime;
- destination;
- exact command;
- ability to resume.

Inventory-driven API bootstrap does not require a full-dump approval unless it is likely to create significant traffic/cost.

## Sudo

Ask only when required. Provide the exact command and why.

## Secret entry

Never request secrets in chat or commit them. Prompt the owner to enter them directly into terminal/UI.

## Destructive production-data action

Before asking:

- validated backup path;
- checksum;
- restore test;
- affected rows/files;
- expected result;
- dry-run;
- recovery plan.

## Irreversible external infrastructure

Includes DNS deletion, tunnel deletion, credential revocation or public route removal. Normal service restart does not require approval.

## Not approval-gated

Codex should proceed autonomously with:

- source edits;
- tests;
- disposable migrations;
- fixture generation;
- local browser tests;
- documentation;
- Git phase commits;
- non-destructive backup;
- API documentation review;
- mock Shopify transport;
- bounded public read-only metadata requests under configured policy.


---

# FILE: 17_VERSION_POLICY.md

# SnapIMS Version Policy Applied to This Work

## Semantic version result

The work adds:

- Settings workflows;
- Recognition Control Centre;
- model routing;
- Inventory Search;
- Item detail;
- movie database acquisition;
- Shopify orders;
- reservations;
- pick queue;
- observability.

This is a minor release:

```text
0.9.0 → 0.10.0
```

If stabilization is released alone before the features, it may be `0.9.1`. Once the combined feature package lands, the synchronized version is `0.10.0`.

## 1.0 prohibition

Do not use `1.0.0` until:

- real 20-tape Pixel pilot;
- live AI;
- one live Shopify draft;
- CSV physical verification;
- restart durability;
- Operator Guide complete and followed;
- browser verification;
- no known blocker.

## Synchronization

After changing version, update every active operator/release document. No active document may refer to an obsolete current version.

Historical documents may retain old versions only when clearly archived as history.


---

# FILE: 18_REFERENCE_INDEX.md

# Reference Index

## Included source files

The `References` directory contains:

- integrated v0.9.0 audit in Markdown and PDF;
- integrated pre-1.0 v0.10.0 roadmap in Markdown and PDF.

These are planning references. The live repository and final browser UI remain source of truth.

## Current official technical references to inspect during implementation

### Shopify

- GraphQL Admin API current/latest documentation.
- `inventoryActivate` and required `@idempotent` key for API versions from 2026-04 onward.
- `inventorySetQuantities` compare-and-set and idempotency.
- `fulfillmentCreate`.
- Orders query pagination and update filtering.
- Webhook delivery, headers, HMAC and ordering caveats.

### Wikimedia/Wikidata

- Wikidata database download page.
- Wikidata JSON entity dumps and incremental dumps.
- Wikimedia API access policy.
- Wikimedia API rate limits.
- MediaWiki Action API etiquette.
- Wikibase REST/Action APIs.

Key operating rules:

- meaningful User-Agent with contact;
- bounded concurrency;
- Retry-After;
- exponential backoff;
- cache;
- use bulk dumps for bulk acquisition rather than abusing interactive APIs;
- Wikidata structured data is CC0;
- Wikipedia text has separate attribution/licence requirements.

### OpenAI

Inspect official current:

- model list;
- image input;
- Responses API structured outputs;
- usage fields;
- rate limit/error behaviour.

### Cloudflare

Inspect official current:

- locally managed tunnel config;
- Linux service;
- Access policy;
- connector status;
- origin health.

## Evidence warnings

- Older SnapIMS status documents contain claims disproved by later Firefox testing.
- Old Operator Guides are not final UI truth.
- Do not use old screenshots as acceptance evidence.


---

# FILE: 19_COMBINED_EXECUTION_PROMPT.md

# Combined Execution Prompt

This file is intentionally shorter than the sum of the phase specifications. It directs Codex to read them from disk.

```text
IMPLEMENT SNAPIMS v0.10.0.

Work inside ~/Projects/SnapIMS.

Read:
docs/codex-work-orders/v0.10.0/01_MASTER_CONTROLLER.md

Then execute, in order:
02_PHASE_0_BASELINE_AND_PRESERVATION.md
03_PHASE_1_STABILIZATION_SECURITY.md
04_PHASE_2_OBSERVABILITY.md
05_PHASE_3_SECURE_SETTINGS.md
06_PHASE_4_RECOGNITION_ROUTING.md
07_PHASE_5_INVENTORY_SEARCH.md
08_PHASE_6_MOVIE_DATABASE.md
09_PHASE_7_SHOPIFY_ORDERS_PICKING.md
10_PHASE_8_SCALE_ACCEPTANCE.md
11_PHASE_9_DOCUMENTATION_RELEASE.md

Create or resume V010_IMPLEMENTATION_STATE.md. Inspect current reality before editing. Preserve data and dirty work. Use bounded commits. Run the required tests and browser gates after every phase. Continue autonomously. Stop only at the owner approval gates in 16_OWNER_APPROVAL_GATES.md or a genuine unrecoverable block. Do not perform a live Shopify write or full Wikidata dump without approval. Do not label 1.0.0. Begin now.
```
