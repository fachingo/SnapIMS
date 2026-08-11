# SnapIMS v0.16.0 — Database and Data Flow

## Source-of-truth rule
v0.16.0 reuses the real upstream v0.15 data architecture. The rescue port does not replace core SQLite databases with donor schemas.

## Logical flow

```text
Batch Folder / Photos
        |
        v
Import durable preview/jobs/cache
        |
        v
items + photos + batch records (working state)
        |
        v
Recognition requests/results/selection -----> Catalog lookup jobs
        |                                      | local catalog first
        v                                      v
Recognition Review                         catalog SQLite / Wikipedia
(title/tags operator decision)                |
        |                                      +--> item_movie_links
        v
Bulk Editor / Pricing <---- local prior item prices / pricing_item_states
        |                \--- eBay pricing evidence/cache/manual sold URL
        v
INVENTORY_COMMITTED event boundary
        |
        v
Publish / Shopify jobs
        |
        +--> Shopify product/variant/inventory/media
        +--> shopify_sync current state/reconciliation
```

## Inventory database
Existing v0.15 inventory SQLite remains authoritative for working records and event/history tables. Relevant existing datasets include:
- batches;
- items;
- photos;
- recognition_results / selection / attempt state/events / requests;
- tag_definitions / item_tags / tag rejections;
- item_movie_links and link history;
- inventory_events;
- item_change_log;
- import jobs/cache/corrections/journal;
- batch checkpoints / CSV staging;
- Shopify sync/jobs/upload attempts;
- pricing workflow/evidence tables initialized by the existing pricing subsystem;
- operational events and settings/revision data.

## Catalog database
Existing catalog SQLite remains separate and owns movie identities, aliases, genres, source/provenance, candidates and durable lookup work. Item↔movie identity lives in the inventory database via `item_movie_links`.

## Pricing
The existing pricing subsystem stores immutable sold-evidence collections/cache heads plus per-item workflow/decisions. Database-first pricing also reads deliberate historical item prices from inventory. It excludes prior rows whose working source is AI/recognition-derived.

Strong identity order:
1. linked movie identity + compatible edition metadata;
2. exact normalized title + compatible structured fields when neither side has a conflicting movie identity;
3. otherwise history is guidance only.

## Commit to Inventory
The rescue port intentionally avoids a duplicate authoritative inventory database. Commit writes an idempotent `INVENTORY_COMMITTED` inventory event per item and updates the batch lifecycle state. Working records remain durable and auditable.

## Shopify
The existing Shopify system remains authoritative for current remote linkage/sync state. v0.15 does not store complete Shopify order history; unified search therefore does not claim prior sold counts unless that data is genuinely synchronized in a later implementation.

## Search
Search uses bounded SQL discovery and exact/canonical identity aggregation. It does not load all inventory rows into browser memory and does not aggregate partial substring neighbors.
