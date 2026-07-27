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
