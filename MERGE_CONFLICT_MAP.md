# SLMC Merge Conflict Map

## High-probability conflicts

| Area | SLMC change | Integration guidance |
|---|---|---|
| `snapims/db.py` | schema 7, link tables and audited helpers | Rebase the additive migration onto the newer inventory schema; never lower or overwrite a newer schema number |
| `snapims/recognition/service.py` | post-commit catalog hook and catalog-aware approval title | Preserve the newer recognition transaction boundary; invoke SLMC only after the recognition result commits |
| `snapims/web/app.py` | lifespan recovery, Review status, catalog routes, diagnostics | Blend route/context additions into the final browser UI; do not replace unrelated Review redesigns |
| `snapims/web/templates/review.html` | compact match strip and ambiguity panel | Keep final workstation layout and one-action approval; insert only compact status and exception detail |
| `snapims/web/templates/diagnostics.html` | catalog metrics/actions | Preserve newer diagnostics wording and add the independent catalog section |
| `snapims/inventory.py` | structured Movie CSV columns | Preserve Item-ID keyed CSV and append catalog fields without renaming existing columns |
| `snapims/shopify/service.py` | structured Movie simulation block | Preserve draft-only/idempotency behaviour and do not use Wikipedia prose as product description |
| `snapims/config.py` | `catalog_db_file` path | Carry forward into the current `DataPaths` model |
| Operator Guide and reports | integration screenshots/procedures | Regenerate from the merged final UI; do not reuse stale SLMC screenshots when controls changed |

## Low-conflict additive areas

- `snapims/catalog/`
- `scripts/catalog_admin.py`
- catalog fixtures/tests
- reference migration files
- SLMC documentation and performance evidence

## Blend order

1. Preserve and test the target branch.
2. Add the catalog package and config path.
3. Adapt the independent catalog migration first.
4. Adapt inventory-link migration to the target schema.
5. Blend recognition post-commit hook.
6. Blend Review context/status without redesigning the workstation.
7. Blend CSV/Shopify structured outputs.
8. Add diagnostics/admin.
9. Run deterministic and migration tests.
10. Run the actual merged browser UI and regenerate all operator documentation.

## Prohibited conflict resolution

Do not resolve conflicts by restoring the older v0.6.0 versions of whole files over a newer branch. Do not copy a runtime database. Do not renumber Items/Batches. Do not assign the final SnapIMS version until merged code and browser verification pass.
