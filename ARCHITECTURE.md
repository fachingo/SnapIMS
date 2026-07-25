# SnapIMS 0.6.0 Architecture

## System boundaries

- `snapims/protocol.py`, `pipeline.py`, `processor.py`: deterministic QR/photo import.
- `snapims/db.py`: SQLite persistence, migrations, checkpoints, history, cursors, recognition jobs.
- `snapims/recognition/`: provider adapters and durable recognition orchestration.
- `snapims/inventory.py`: record validation, CSV export/import staging, diff application, external review.
- `snapims/shopify/`: Shopify adapter, idempotency, and simulation/live boundaries.
- `snapims/web/`: FastAPI routes, Jinja templates, browser interactions.

The SQLite working batch is authoritative. Review, Batch Editor, CSV apply, and recovery all update the same item records. Original and AI values remain available through recognition history, change history, and rollback checkpoints.

## Media pipeline

Each product photo has three durable representations:

1. Original: exact preserved source file.
2. Preview: 1080-pixel browser derivative.
3. Recognition: 1920-pixel AI derivative.

QR cards, duplicates, blank images, and ineligible photos are excluded from provider payloads without being deleted.

## Concurrency safety

SQLite uses WAL, busy timeouts, transactions, and item record revisions. Browser edits include the expected revision; stale writes are rejected rather than silently replacing newer values.

## Extension points

Provider adapters, Shopify publishing, CSV tooling, and UI services remain separate enough to support future Android capture clients, Docker/server deployment, ERP adapters, and additional AI providers without replacing the deterministic import core.
