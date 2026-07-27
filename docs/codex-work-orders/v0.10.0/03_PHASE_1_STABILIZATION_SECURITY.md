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
