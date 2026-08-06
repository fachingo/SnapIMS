# SnapIMS v0.15.0 Architecture

- Local-first FastAPI browser workstation.
- SQLite inventory database, current schema 16.
- Immutable source photographs and immutable internal Batch/Item IDs.
- Durable Import, Recognition, Catalog, CSV, and Shopify jobs.
- Encrypted provider secrets and Shopify token cache.
- Shopify layers: authentication/token manager, GraphQL client, Item service, durable job orchestrator, and operator UI.
- Bounded Batch Editor/Publish pages and aggregate health queries.
- Draft-first Shopify safety with explicit publication target and typed live confirmation.
