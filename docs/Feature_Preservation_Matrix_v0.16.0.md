# SnapIMS v0.16.0 — Feature Preservation Matrix

Status legend: **PRESERVED BY PORT DESIGN**, **INTENTIONAL CHANGE**, **NEW**, **REQUIRES INTEGRATED QA**.

| Feature / subsystem | v0.15 behavior | v0.16 port treatment | Status |
|---|---|---|---|
| Folder-first Import | durable preview/commit | untouched | PRESERVED BY PORT DESIGN |
| NEXT ITEM parsing | active normal QR boundary | untouched | PRESERVED BY PORT DESIGN |
| Import thumbnails/correction | interpret/split/merge | untouched | PRESERVED BY PORT DESIGN |
| Import restart durability | SQLite jobs/journal | untouched | PRESERVED BY PORT DESIGN |
| Recognition providers | mature provider registry | preserved | PRESERVED BY PORT DESIGN |
| Model/tier/image profiles | configurable routing | preserved | PRESERVED BY PORT DESIGN |
| Recognition attempts/history | immutable evidence | preserved | PRESERVED BY PORT DESIGN |
| Recognition benchmark | owner-labelled metrics | preserved | PRESERVED BY PORT DESIGN |
| AI pricing | recognition produced estimates / 9.99 fallback | removed | INTENTIONAL CHANGE |
| AI tags | existing tag definitions supplied | hard-limited to centralized 0–3 approved IDs | INTENTIONAL CHANGE |
| Review quick form | title + price + tags + discount + pricing mode | title + tags only; Approve/Reject/Skip | INTENTIONAL CHANGE |
| Exception Editor | full item/product editor | preserved explicit-only | PRESERVED BY PORT DESIGN |
| Review catalog candidates | ambiguity resolution | preserved | PRESERVED BY PORT DESIGN |
| Review rerun/history | advanced immutable rerun | preserved | PRESERVED BY PORT DESIGN |
| Batch Editor paging/filter/sort | mature high-volume grid | preserved | PRESERVED BY PORT DESIGN |
| Batch bulk actions | pricing/location/tags/descriptions/flags/etc. | preserved | PRESERVED BY PORT DESIGN |
| Batch keyboard/undo/redo | mature workstation shortcuts | preserved | PRESERVED BY PORT DESIGN |
| Batch checkpoints | rollback | preserved | PRESERVED BY PORT DESIGN |
| Database-first pricing | absent | strong-identity null-price prefill + provenance | NEW |
| View eBay Sold | pricing area only | added to Bulk Editor rows; existing pricing action retained | NEW |
| Pricing queue/cache/evidence | mature Pricing Workbench integration | preserved; renamed eBay Pricing | PRESERVED BY PORT DESIGN |
| Pricing collector/throttle | existing optional browser collection | preserved/collapsed settings | PRESERVED BY PORT DESIGN |
| Catalog/Wikipedia | real durable catalog architecture | preserved | PRESERVED BY PORT DESIGN |
| Unified Item Search | absent | exact/canonical title intelligence | NEW |
| Existing command palette | Alt+P | preserved + Ctrl+K grouped live results | INTENTIONAL CHANGE |
| Contextual help | limited | dedicated registry + app-wide semantic fallback; no blanket exemptions | NEW |
| Existing Settings | secure configuration/provenance | preserved, progressively disclosed | PRESERVED BY PORT DESIGN |
| Diagnostics | existing operational diagnostics | preserved + Data Sources page | NEW |
| Working→inventory boundary | implicit | explicit idempotent advisory commit | NEW |
| Shopify simulation | existing | preserved | PRESERVED BY PORT DESIGN |
| Shopify drafts/media/inventory | existing durable workflow | preserved | PRESERVED BY PORT DESIGN |
| Shopify live/direct publish | typed confirmations | preserved | PRESERVED BY PORT DESIGN |
| Shopify reconciliation/sync | bidirectional management | preserved | PRESERVED BY PORT DESIGN |
| Shopify archive/delete/restore | existing management | preserved | PRESERVED BY PORT DESIGN |
| Incomplete draft override | local simulation blocked incomplete | explicit operator attempt may bypass local completeness only | INTENTIONAL CHANGE |
| Revision/stale write protection | existing | preserved | PRESERVED BY PORT DESIGN |

## Integrated QA requirement
The port installer modifies mature files surgically and refuses the failed donor baseline. Every **PRESERVED BY PORT DESIGN** row still requires the complete upstream suite/browser walk-through on the authoritative source tree before release promotion.
