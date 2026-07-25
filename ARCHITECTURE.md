# SnapIMS 0.6.0 + SLMC-0.1.0 Architecture

## System boundaries

- `snapims/protocol.py`, `pipeline.py`, `processor.py`: deterministic QR/photo import.
- `snapims/db.py`: authoritative physical inventory, schema 7, backups, checkpoints, history, cursors, recognition jobs and audited Item-to-Movie links.
- `snapims/recognition/`: provider adapters and durable recognition orchestration.
- `snapims/catalog/`: independent permanent Movie database, local search, bounded Wikipedia discovery, candidates, jobs, reconciliation and administration.
- `snapims/inventory.py`: validation, CSV export/import staging, diff application and external review.
- `snapims/shopify/`: structured simulation/draft integration and idempotency boundaries.
- `snapims/web/`: FastAPI routes, Jinja templates, compact catalog states and diagnostics.

`inventory.sqlite3` is authoritative for physical inventory. `movie_catalog.sqlite3` is authoritative for reusable Movie identity and provenance. The databases use durable reconciliation rather than pretending to have a cross-file atomic foreign key.

## Recognition and catalog flow

The first-pass vision result is committed unchanged. SLMC immediately searches local canonical titles, aliases, title/year evidence and FTS. A materially unique local hit links without Wikipedia. A genuine miss queues one restart-safe bounded English Wikipedia lookup in the background. Review remains usable and the fast Price/Discount → Approve & Next/Enter contract is unchanged.

## Media pipeline

Each product photo has preserved original, browser preview and recognition derivative representations. QR cards and ineligible images are excluded from provider payloads without deletion.

## Concurrency and recovery

SQLite uses WAL, busy timeouts, transactions, item revisions, unique job/source constraints, one current link per Item, append-only link events, leased catalog jobs and restart reconciliation. Failed Item linking retains the shared Movie and moves to `LINK_PENDING`.

See `ARCHITECTURE_LOCAL_MOVIE_CATALOG.md` for the full SLMC design.
