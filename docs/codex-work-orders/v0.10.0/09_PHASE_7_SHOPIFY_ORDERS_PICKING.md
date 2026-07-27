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
