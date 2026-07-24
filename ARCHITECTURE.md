# SnapIMS 0.5.0 architecture

## Design rule

The camera roll is an ordered event stream. Time restores chronology but never determines item membership. `CVHS1:ITEM:NEXT` is the sole normal item boundary.

```text
Camera folder
  -> deterministic sorter
  -> allowlisted QR decoder
  -> NEXT-only interpreter
  -> preserved originals and safe JPEGs
  -> SQLite transaction
  -> recognition jobs
  -> exception Review
  -> CSV / Shopify adapters
```

## Separation of responsibilities

- `snapims/protocol.py`, `interpreter.py`, `pipeline.py`: capture protocol and deterministic grouping.
- `snapims/processor.py`: import staging, originals, safe images, manifests, duplicate detection.
- `snapims/db.py`: schema v5, migrations, transactions, settings, jobs, cursors, audit events.
- `snapims/recognition/`: provider interface, durable jobs, manual-value precedence, fast acceptance.
- `snapims/inventory.py`: validation and safe versioned CSV round-trip.
- `snapims/shopify/`: GraphQL transport, simulation, checkpoints, resumable draft creation.
- `snapims/web/`: browser client and HTTP application boundary.

The browser never owns durable state. SQLite remains the system of record.

## Portability

The v0.5 HTTP boundary makes these future clients feasible without changing core inventory rules:

- Android capture client producing the same event stream.
- Fully local Android edition with SQLite.
- Windows/Linux desktop shell.
- Multi-operator server edition with a stronger database and authentication.

Multi-operator conflict resolution is not implemented. `record_revision` provides an optimistic-concurrency foundation, but v0.5 remains a single-operator release.
