# SnapIMS v0.13.2 Operator Guide

## Start and verify

```bash
export PATH="$HOME/.local/bin:$PATH"
snapims up
snapims status
```

Confirm Version is `0.13.2`, Inventory schema is `15 / 15`, and Project path points to the intended release. Open `http://127.0.0.1:8767/`.

## Import a batch

1. Create one folder in `~/SnapIMS-data/batches`.
2. Use the folder name as the default batch name.
3. Put product photos inside in capture order.
4. Photograph NEXT ITEM between tapes. Do not photograph NEXT after the final tape unless necessary; a trailing NEXT is safely ignored with a warning.
5. Open **Import** and select the folder.
6. Enter any location such as `A6`, `Processing Table`, or leave blank/enter `None` for unassigned.
7. Select **Preview batch**. Progress is durable across refreshes.
8. Review interpreted Items. Use Treat as Product Photo, Treat as NEXT ITEM, Ignore Photo, Split Item Before This Photo, or Merge With Previous Item when needed.
9. Select **Commit Import**.

## Review and Batch Editor

- Use Review for title, price, tags, condition, recognition evidence, Rare, and Physical Review decisions.
- Batch Editor loads bounded pages. Search/filter applies to the current loaded result page and server-side query.
- Select destination rows, focus a source cell, and choose **Fill Down** for Title, Price, Tags, Discount, Description, Location, Review, or Rare.
- Tags Fill Down replaces the destination tag set exactly. **Append Tags** remains a separate bulk action.
- Location accepts free text or unassigned. Location changes are audited.
- When filters hide a selected row, that selection is cleared automatically.
- Arrow keys cross the Tags editor in both directions.

## Publish

Publish displays aggregate batch readiness without evaluating every Item. Shopify simulation is explicit and paged. Live publishing remains guarded by credentials and confirmation.

## Stop

```bash
snapims down
```

Stop the application before an offline database backup.
