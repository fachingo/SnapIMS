# SnapIMS 0.5.1 Architecture

## Core rule

The camera roll is an ordered event stream. Time gaps never define item boundaries. `CVHS1:ITEM:NEXT` is the sole normal boundary.

## Layers

- `snapims/protocol.py`, `sorter.py`, `interpreter.py`, `pipeline.py`: deterministic capture/event interpretation.
- `snapims/processor.py`: preserved originals, sanitized product copies, staging, fingerprinting, and transactional import.
- `snapims/db.py`: SQLite schema v5, migrations, events, settings, cursors, recognition jobs, and publish checkpoints.
- `snapims/recognition/`: provider-neutral suggestion interface, durable jobs, acceptance, failure, and retry.
- `snapims/inventory.py`: validation and immutable-ID CSV round-trip.
- `snapims/shopify/`: draft-only payload, transport boundary, checkpointed publication, media verification, and reconciliation.
- `snapims/web/`: FastAPI/Jinja browser client. UI actions call application services; SQLite remains authoritative.

## Durability

Each recognized item is committed independently. A process killed during recognition leaves the job RUNNING in SQLite; startup converts orphaned RUNNING jobs to PAUSED. Continue reconstructs completed boundaries from recognition history and does not duplicate results.

## Future clients

A mobile capture client can emit the same START, LOCATION, NEXT, FLAG, PHOTO, and END event vocabulary. A server/multi-operator edition requires authentication and concurrency policy beyond 0.5.1.
