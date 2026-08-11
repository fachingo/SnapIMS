# SnapIMS v0.16.0 — Current Application Specification

## Purpose
SnapIMS is a photo-first inventory workstation for physical media. v0.16.0 is an operator-first minor release ported onto the mature v0.15 architecture, not a simplified replacement application.

## Architecture principle
Four layers remain distinct:
1. normal operator workflow;
2. exception workflow;
3. configuration;
4. administration/diagnostics.

Normal pages emphasize the immediate job while preserving advanced capability through progressive disclosure.

## Core workflow and features

### Home / Dashboard
- global workload and readiness information;
- navigation to all operational stages;
- visible Item Search;
- Ctrl+K command/search palette;
- contextual help entry point.

### Import
Existing mature v0.15 folder workflow is preserved, including durable jobs, NEXT ITEM parsing, previews, photo correction, split/merge, pagination, cache/hash metrics, restart durability, source preservation, and optional batch location.

### Recognition
Existing provider/model/tier/image-profile architecture is preserved, including immutable attempts, request durability, retry/recovery, metrics, model routing/escalation, contradictions, owner-labelled benchmark mode, and catalog hooks. v0.16 removes all recognition pricing and restricts automatic tags to the approved taxonomy (max three).

### Recognition Review
- title/tag-only normal workstation;
- title autofocus;
- Enter = Approve & Next;
- Reject and Skip always continue;
- no price/barcode/etc. normal fields;
- explicit-only Edit Details;
- bulk confidence approval;
- existing catalog ambiguity, recognition rerun/history, photo tabs, revision safety, and provenance retained outside the primary path.

### Batch Editor / Bulk Editor
Existing mature batch workstation remains authoritative for high-volume changes. v0.16 adds local database pricing suggestion/provenance and row-level eBay sold links without removing bulk tools.

### eBay Pricing
Existing pricing queue/cache/evidence/worker architecture remains. UI label is explicit and advanced collector settings are secondary. Manual sold-link workflow is always supported.

### Search / title intelligence
- bounded partial discovery;
- exact/canonical aggregation;
- linked catalog movie identity where available;
- no sequel substring merging;
- local inventory, batches, locations, current prices, pricing state, current Shopify sync, recognition and metadata;
- no fabricated historical Shopify sales.

### Commit to Inventory
Advisory, auditable and idempotent working→authoritative inventory boundary. Incomplete records can be intentionally committed.

### Publish / Shopify
Existing mature v0.15 publish job/service/client architecture is preserved, including simulation, drafts, media, inventory, live publication, direct path, retry/resume, reconciliation and product management. Explicit incomplete draft attempts bypass only local completeness checks and never bypass external Shopify/configuration requirements.

### Settings
Existing settings preserved. Major sections progressively disclosed. Setting inputs receive contextual help keys.

### Diagnostics / Data Sources
Existing Diagnostics remains. Data Sources adds logical-source availability/count/freshness visibility without secrets.

## Operator authority
Operator decisions outrank AI/database suggestions. Automatic logic must never silently overwrite deliberate operator title/tag/price decisions.

## Pricing source contract
- UNPRICED: no price.
- DATABASE: strong prior local identity/edition evidence autofilled a null price.
- MANUAL: deliberate operator/current value.
- EBAY: market evidence accepted through pricing subsystem.
- FIXED: deliberate fixed/batch price.
Legacy AI/recognition-sourced prices are excluded from database-first evidence.

## Tag contract
Automatic tags are lowercase, centralized, vocabulary-bound and limited to three. Years/rarity/marketing adjectives are not automatic tags. Existing operator tag history remains intact.

## Persistence / durability
The port deliberately reuses existing inventory tables, recognition history, catalog database, pricing subsystem, Shopify synchronization/jobs, event logs and revision controls. It does not create a replacement core database.

## External integrations
- OpenAI/image recognition: real provider when configured; test providers remain test-only.
- Wikipedia/catalog: real upstream nonblocking catalog system.
- eBay: manual sold/completed links first-class; browser collector optional.
- Shopify: real upstream durable draft/live/sync system.

## Keyboard behavior
- Recognition Review title autofocus.
- Enter approves/advances from normal Review unless an intentional child control (for example tag autocomplete) is consuming Enter.
- Ctrl+K opens global palette.
- Ctrl+Shift+F opens Item Search.
- F1 opens contextual help for the focused control.
- Existing Batch Editor keyboard shortcuts remain.
