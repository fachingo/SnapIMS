# SnapIMS Operator Guide — v0.16.0 Operator-First Port

> **Verification state:** This guide describes the intended integrated v0.16.0 behavior produced by the rescue port. Final screenshots must be captured from the authoritative v0.15-derived working tree after the port passes the full upstream test suite and browser walk-through. The failed donor screenshots are not accepted as release evidence.

## Normal workflow

**Import → Recognition → Recognition Review → Bulk Editor / Pricing → Commit to Inventory → Publish**

SnapIMS assists the operator. Warnings and suggestions do not replace operator authority.

## 1. Home / Dashboard

Home owns global workload information. Daily work pages should emphasize the immediate task rather than duplicate global dashboard cards.

Use the top navigation or **Ctrl+K** from anywhere to open the command/search palette. A visible **Search** link opens Item Search directly.

## 2. Import — preserved mature workflow

The v0.15 folder-first Import workflow is preserved. One immediate child folder under the configured incoming directory is one batch. The normal QR command is `CVHS1:ITEM:NEXT`.

Import continues to support:

- durable preview/commit jobs;
- image thumbnail preview;
- cached image classification and hashing;
- per-photo interpretation correction;
- **Split Item Before This Photo**;
- **Merge With Previous Item**;
- pagination for larger previews;
- refresh/restart durability;
- optional free-text batch location, including blank/None;
- original source preservation and durable final commit.

Recognition, title, barcode, and price are not Import prerequisites.

## 3. Recognition — preserved mature workflow

Recognition remains the full v0.15 recognition control center. The port preserves provider/model configuration, tiers, image profiles, durable requests, attempt history/comparison, failure/retry behavior, metrics, contradiction/low-confidence diagnostics, and owner-labelled benchmark tooling.

v0.16 changes recognition output policy:

- AI proposes a title, confidence, and **0–3 approved tags**;
- AI **never proposes a listing price**;
- returned AI tag IDs are hard-filtered against the centralized approved taxonomy;
- metadata/catalog work remains additive and nonblocking.

## 4. Recognition Review — single-purpose operator workstation

Recognition Review is for only:

- viewing the product photograph;
- checking/correcting the title;
- checking/editing approved tags;
- seeing recognition confidence;
- choosing **Approve & Next**, **Reject**, or **Skip**.

### Keyboard-first review

When a review item opens, the **Title** field receives focus.

- Title correct → press **Enter** → Approve & Next.
- Title wrong → type correction → press **Enter** → save/approve/advance.
- **Reject** marks the recognition result rejected/attention-needed and continues.
- **Skip** defers the item and continues.

Enter must never open Edit Details.

### What Recognition Review does not require

Normal Recognition Review does **not** require or edit:

- price;
- barcode;
- location/shelf;
- quantity;
- weight;
- distributor/studio;
- edition;
- pricing mode;
- Shopify-specific fields.

### Edit Details

The existing full exception editor is preserved. It is opened only through an explicit **Edit Details** action. Existing advanced product fields, catalog ambiguity resolution, recognition retry/history, and provenance remain available outside the simple normal review path.

### Bulk confidence approval

Use **Approve all at or above X% confidence** to review the eligible count and bulk-approve high-confidence recognized items. Failed, blank/UNKNOWN, explicitly rejected, and below-threshold items are excluded by default.

## 5. Approved tag vocabulary

Automatic tags come from one centralized, lowercase approved taxonomy. The taxonomy includes useful genres/subgenres, major franchises/series, selected brands, and exceptionally searchable performers.

Rules:

- maximum three automatic tags;
- zero tags is valid;
- fewer relevant tags is better than filler;
- years are not tags;
- AI cannot invent aliases such as `sci-fi` when the approved value is `science fiction`;
- operator manual tag changes remain authoritative.

The same definitions are seeded into the existing SnapIMS tag-definition system so existing tag IDs/history are preserved rather than replacing the mature tag subsystem.

## 6. Bulk Editor / Pricing — mature Batch Editor preserved

The real v0.15 Batch Editor remains the main high-volume completion workspace. Existing server paging, search/filter/sort, confidence buckets, bulk actions, keyboard movement, undo/redo, evidence, checkpoints/rollback, and Save All functionality are preserved.

v0.16 adds database-first pricing context to each visible row.

### Pricing provenance

Price badges mean:

- **DATABASE** — a strong prior SnapIMS identity/edition match supplied the initial price;
- **MANUAL** — the operator entered or changed the current price;
- **EBAY** — accepted market-evidence workflow supplied the price;
- **FIXED** — a deliberate fixed/batch pricing action supplied it;
- **UNPRICED** — no price exists.

A manual operator price is never overwritten by a later database suggestion.

Legacy recognition/AI-sourced prices are excluded from database-first pricing evidence so old placeholder `$9.99` values cannot become trusted historical pricing.

### Database-first behavior

When a visible Bulk Editor row has no price, SnapIMS checks previous local pricing first.

- Strong same movie/product identity + compatible edition fields → prefill the most recent deliberate prior price and show **DATABASE**.
- Exact title but conflicting/ambiguous edition identity → show history as **guidance only** and do not silently apply it.
- No usable history → remain **UNPRICED**.

## 7. View eBay Sold — first-class manual pricing

Each pricing row has **View eBay Sold**. It opens eBay Canada sold/completed results using the approved title plus `VHS` and sold/completed filters.

Recommended two-monitor workflow:

1. Keep Bulk Editor on monitor 1.
2. Click **View eBay Sold**.
3. Inspect comparable sold listings on monitor 2.
4. Enter/override price in SnapIMS.
5. Continue to the next row.

Automated scraping is optional; it is not a production prerequisite.

## 8. eBay Pricing — existing pricing subsystem preserved

The old **Pricing Review** label becomes **eBay Pricing**. The existing queue, immutable evidence, cache, collector, throttle, status/failure handling, refresh semantics, and manual price protection remain.

Pricing items stay prominent. Batch/filter/collection configuration is progressively disclosed rather than deleted.

## 9. Metadata / catalog

The real upstream catalog system remains authoritative. Recognition results continue to queue existing local-catalog/Wikipedia enrichment nonblockingly.

Metadata failure never traps Recognition Review. Existing metadata/catalog diagnostics and provenance remain available. Release year is structured metadata, not a Shopify tag.

## 10. Unified Item Search / title intelligence

Open **Search** or press **Ctrl+Shift+F** for direct Item Search. Search asks: **What does SnapIMS know about this title?**

Where available, the result includes:

- local copies;
- committed vs. pending counts;
- batches and locations;
- current prices and pricing history;
- current Shopify-linked product state;
- recognition/workflow state;
- local catalog metadata.

Historical Shopify order/sales counts are **not fabricated**. v0.15 does not persist Shopify order history, so the UI states that this source is unavailable unless a future synchronization feature actually stores it.

Identity safety is strict: `Alien`, `Aliens`, and `Alien 3` remain separate results. Partial search can discover all three, but title intelligence aggregates only an exact/canonical identity.

## 11. Ctrl+K command/search palette

**Ctrl+K** opens the existing command palette and extends it with grouped live results for Items, Navigation, Settings, and Help. Existing Alt+P behavior remains supported for compatibility.

## 12. Contextual Field Help

Use:

- **F1** on a focused control;
- the visible **?** control;
- optional right-click contextual help.

Important workflows have hand-authored help topics. All other interactive controls receive centralized semantic fallback help rather than being declared exempt. There is no blanket `data-help-exempt` bypass.

## 13. Settings

All mature v0.15 settings remain. v0.16 uses progressive disclosure so everyday configuration does not become a wall of controls.

Major groups include existing General, Recognition & AI, Publishing / Shopify, Metadata / Catalog, Infrastructure, Advanced Security, Backup & Retention, plus access to Data Sources diagnostics.

## 14. Data Sources

Open **Data Sources** from Settings/Diagnostics or Ctrl+K to inspect logical data-source health without exposing secrets:

- SnapIMS Inventory;
- Recognition;
- Catalog / Metadata;
- Pricing History;
- Shopify current sync state;
- eBay Pricing.

The page reports availability, counts/freshness where meaningful, and degraded/unconfigured states.

## 15. Commit to Inventory

**Commit to Inventory** is an explicit, auditable boundary between durable working state and authoritative inventory state.

Warnings are advisory. If records are incomplete, SnapIMS lists the warnings and offers:

- return to Bulk Editor; or
- **Commit Anyway**.

Commit is idempotent: repeating it does not create duplicate commit events for the same item.

## 16. Publish — mature v0.15 workflow preserved

The complete v0.15 Shopify workflow remains:

- staged validation;
- read-only simulation;
- draft creation;
- draft review;
- typed live confirmation;
- direct publish path where already supported;
- durable jobs and retry/resume;
- product/variant/inventory/media IDs;
- quantity 1 behavior;
- 250 g Shopify weight configuration;
- media staging/processing;
- reconciliation;
- local→Shopify sync;
- Shopify→local keep/merge workflows;
- restore draft;
- archive/delete;
- product-management controls.

v0.16 adds an explicit **Attempt incomplete items anyway** override to draft creation. This bypasses only SnapIMS completeness gating. It does not bypass Shopify authentication/configuration, typed confirmation for dangerous actions, or Shopify’s own API rules.

If price is missing and the override is explicit, SnapIMS omits the price rather than inventing one. If Shopify requires/rejects a field, the actual external failure is recorded.

## 17. Recovery

Preserve the data directory and automatic migration/backups. Do not delete the inventory database to clear workflow problems.

- stale two-tab revisions should be reloaded, not bypassed;
- recognition/provider failure does not erase previous valid evidence;
- pricing collection failure is not the same as zero valid sold matches;
- manual eBay pricing remains available if collector automation is blocked;
- Shopify job recovery/retry remains durable.

## End-of-batch checklist

- Import completed/recovered intentionally.
- Recognition completed or intentionally skipped/failed items understood.
- Recognition Review title/tag decisions completed to the operator’s chosen standard.
- Bulk Editor pricing/completion reviewed.
- Database-price provenance understood.
- Remaining warnings understood.
- Commit to Inventory deliberately completed when desired.
- Shopify simulation/draft/live actions attempted only when intended.
- Failures remain visible for follow-up.

## Release status

v0.16.0 is a minor release, not 1.0.0. Production 1.0 still requires the separately defined live acceptance criteria, including a real 20-tape Pixel pilot, live AI, live Shopify draft, CSV verification, restart durability, final browser verification, synchronized operator documentation, and no known production blockers.
