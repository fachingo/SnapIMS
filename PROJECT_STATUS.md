# SnapIMS 0.7.0 Project Status

Status: **browser-verified minor feature release; controlled real-pilot candidate; not 1.0.0**.

Current capabilities:

- QR-delimited photo import with immutable Batch and Item IDs.
- SQLite schema 8 with structural manifest verification, backups, atomic operations, audited rollback, and legacy migration repair.
- Production-safe live-provider framework with explicit blocked/manual recovery.
- One-Enter Review for AI-suggested or manually typed titles.
- Spreadsheet-style Batch Editor keyboard navigation, row selection, autosave, atomic quick actions, persistent action order, and checkpoints.
- Staged CSV diff, tolerant safe header parsing, atomic apply, and audited rollback.
- Independent local Movie Catalog with local-first search, bounded Wikipedia source lookup, provenance, ambiguity resolution, restart-safe jobs, CSV/Shopify enrichment, and admin recovery.
- Shopify simulation and controlled draft-only architecture.
- Browser-verified restart durability, diagnostics, and clean relevant console/network state.

Next required work is the real 20-tape Pixel/live-AI pilot, physical CSV reconciliation, one deliberately authorized live Shopify draft, production-machine restart verification, and final first-time-operator guide walkthrough. Scale claims remain limited: the full 5,000-row editor/import architecture is deferred.
