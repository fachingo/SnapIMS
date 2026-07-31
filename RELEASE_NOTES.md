# SnapIMS 0.10.1 Release Notes

Release type: **patch**.

Version transition: **0.10.0 → 0.10.1**.

SnapIMS 0.10.1 repairs defects introduced or materially worsened by the v0.10.0
stabilization, settings, observability, recognition-routing, and Shopify retry
work. It preserves the v0.10 operator workflows and does not add a new Publish,
Review, Import, Inventory, order, picking, or mobile workflow.

## Corrected behaviour

- A failed escalation no longer converts a valid baseline recognition attempt
  into a total item failure.
- Batch and per-item recognition use one database-backed Item lease.
- Retry This Item uses the durable Phase-4 request queue and returns immediately.
- Quick Approve rejects stale browser submissions using `record_revision`.
- Recognition-attempt acceptance preserves operator-approved price and discount.
- Batch Editor autosaves are serialized per Item; the newest acknowledged value
  wins and dirty state is retained until that value is saved.
- Host, Origin, and CSRF protections remain active when login authentication is
  disabled. Unauthenticated operation is limited to local hosts.
- Recognition totals aggregate all matching attempts rather than only the newest
  250 displayed rows. Benchmark metrics use an accepted attempt first, otherwise
  the current selected attempt.
- Recognition and Diagnostics polling back off, pause while hidden, and stop on
  authentication failures.
- v0.10 controls have corrected focus and combobox/listbox semantics.
- Shopify media retry reconciliation identifies each intended SnapIMS photo by a
  stable per-photo identity rather than remote count alone.
- The accidental repository-root terminal-help capture is removed.
- Active documentation now distinguishes the v0.9 baseline, v0.10 feature release,
  v0.10.1 patch, and deferred v1.0 acceptance gates.

## Database

The inventory schema advances from 12 to 13 to add the durable
`recognition_item_leases` table and supporting index. Existing migration safety
remains in force: automatic backup, transaction, integrity check, foreign-key
check, schema-manifest validation, and automatic restore when migration fails.

## Deliberately not included

- No live Shopify Draft button or new Publish workflow.
- No broad large-batch pagination/virtualization redesign.
- No claim that the real 20-tape pilot, live AI acceptance, live Shopify draft,
  physical CSV reconciliation, final v1.0 browser matrix, or v1.0 production gate
  has passed.

Those items require a future minor release or the v1.0 acceptance process.
