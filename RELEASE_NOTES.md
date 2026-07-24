# Release notes

## 0.5.0 - Reconstruction and application boundary

This minor release reconstructs the lost 0.4 workflow from accepted browser reports and advances the architecture.

### Added

- FastAPI browser application with Home, Import, Review, Publish, Settings, and Diagnostics.
- One-click **✓ Approve & Next** review flow.
- Inline Price and Discount quick edits.
- Durable recognition jobs and review cursors.
- Completed-item exception editor and optimistic record revision.
- Configured and recent import folders.
- Non-durable Preview identity and one durable imported Batch ID.
- Release year and discount in CSV.
- Shopify payload preview and resumable stage checkpoints.
- GitHub Actions quality workflow.

### Fixed

- Partial CSV files no longer blank columns that are absent.
- Ordinary AI acceptance no longer overwrites existing manual values.
- Interrupted recognition returns as Paused.
- Failed recognition has one clear recovery route.
- Physical batch position no longer resets with a filtered queue.

### Compatibility

- Existing 0.3 SQLite databases are upgraded to schema version 5 with a pre-migration backup.
- QR vocabulary, NEXT-only item boundaries, immutable Item IDs, and source-photo preservation are unchanged.

### Not 1.0

Live Pixel, AI, and Shopify acceptance criteria remain outstanding.
