# Inventory Database Integration

**Existing authority:** `<data-root>/database/inventory.sqlite3`  
**Baseline schema:** 6  
**Integration schema:** 7  
**Reference migration:** `snapims/migrations/0007_item_movie_links.sql`

## Added structures

### `item_movie_links`

One current optional Movie link per physical Item:

- `item_id`
- `movie_id`
- `link_status`
- `link_method`
- `recognition_result_id`
- `match_score`
- `linked_at`
- `updated_at`
- `operator_confirmed`
- `catalog_revision`
- `last_error`

### `item_movie_link_events`

Append-only audit of initial link, relink, stale/unavailable state and reconciliation. It preserves the previous Movie ID, new Movie ID, event type, recognition evidence, operator confirmation, source and JSON detail.

## Migration safety

Before schema 6 is altered, SnapIMS uses its SQLite backup API to create a timestamped backup, applies the smallest additive migration, sets schema 7, then verifies integrity and foreign keys. No Item, Batch, photo, SKU, recognition, Review, price, discount or Shopify identity is renumbered or rewritten.

## Service-layer validation

The inventory database cannot enforce that a Movie exists in a separate SQLite file. The catalog service validates the Movie and catalog revision before calling `set_item_movie_link()`. Inventory also verifies that the recognition result belongs to the Item.

## Corrections

Changing an operator title:

- never changes Item ID, Batch ID or photos;
- preserves the original recognition row;
- marks the old Movie link stale when needed;
- records a link event;
- searches local Movie data first;
- calls Wikipedia only on a genuine miss;
- prevents punctuation-only duplicate creation.

## CSV and Shopify

The integration adds structured Movie fields while preserving immutable Item identity and item-specific facts. CSV remains keyed by Item ID. Shopify remains simulation/draft-only under the host release policy.
