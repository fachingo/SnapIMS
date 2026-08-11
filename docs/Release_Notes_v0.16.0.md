# SnapIMS v0.16.0 — Release Notes

Operator-first minor release port.

## Recognition Review
- title/tag-only primary workflow;
- autofocus title;
- Enter = Approve & Next;
- Reject / Skip;
- explicit-only Edit Details;
- bulk confidence approval;
- no recognition pricing.

## Tags
- centralized lowercase approved taxonomy;
- automatic tags limited to three;
- years/free-form AI synonyms prohibited.

## Pricing
- database-first price prefill for strong prior identity/edition matches;
- DATABASE/MANUAL/EBAY/FIXED/UNPRICED provenance;
- legacy AI prices excluded as database evidence;
- View eBay Sold in Bulk Editor;
- Pricing Review renamed eBay Pricing while preserving mature pricing queue/cache/collector functionality.

## Search / Help / Diagnostics
- unified Item Search/title intelligence;
- exact/canonical identity safety;
- Ctrl+K global palette;
- contextual help registry + semantic fallback;
- Data Sources diagnostics.

## Inventory lifecycle
- explicit advisory Commit to Inventory boundary;
- operator can intentionally Commit Anyway.

## Shopify
- mature v0.15 publish/media/inventory/reconciliation/product-management architecture preserved;
- explicit incomplete draft attempt can bypass internal completeness checks only;
- missing price is not replaced with invented data.

## Compatibility
The rescue installer is designed specifically for the mature upstream v0.15.0 source and refuses the failed simplified donor baseline.
