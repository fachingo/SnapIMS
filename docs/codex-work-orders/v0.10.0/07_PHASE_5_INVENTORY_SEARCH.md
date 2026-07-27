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
