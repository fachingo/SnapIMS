# SnapIMS v0.15.0 Operator Guide

## 1. Start and verify

```bash
export PATH="$HOME/.local/bin:$PATH"
snapims up
snapims status
```

Confirm **Version 0.15.0**, **Inventory schema 16 / 16**, the intended Project path, and `~/SnapIMS-data`. Open `http://127.0.0.1:8767/`.

## 2. Import

1. Create one folder inside `~/SnapIMS-data/batches`.
2. Put product photographs inside in capture order.
3. Photograph `NEXT ITEM` between tapes. Leading, consecutive, and trailing NEXT cards are handled with warnings rather than empty products.
4. Open **Import**, select the folder, and enter any free-text location or leave it unassigned.
5. Select **Preview batch**. Refreshing does not lose the scan job.
6. Correct grouping with the focused photo interpretation controls.
7. Select **Commit Import** only after the Item count matches the physical tapes.

## 3. Recognition, Review, and Batch Editor

- Failed or blocked provider results are not treated as successful recognition.
- Review title, price, tags, condition, quantity, Rare, Physical Review, and evidence.
- Batch Editor uses bounded pages and supports Fill Down for Title, Price, Tags, Discount, Description, Location, Review, and Rare.
- Tags Fill Down replaces the destination set; **Append Tags** is separate.
- Rows hidden by search/filter are deselected before bulk actions.

## 4. Shopify connection

1. In Shopify Dev Dashboard, release and install the SnapIMS app with the required scopes.
2. Open **Settings → Shopify connection**.
3. Enter the permanent `.myshopify.com` domain, Client ID, Client Secret, and current SnapIMS administrator password.
4. Select **Test and save securely**.
5. Confirm the store identity, scopes, token state, and available locations.
6. Select the inventory location by name.
7. Select the storefront publication by name.
8. Keep **Draft-first publishing** enabled.

SnapIMS generates, encrypts, caches, and refreshes the short-lived access token. The operator does not paste a generated access token during normal setup.

## 5. Complete Publish workflow

### Stage 1 — Validate

The batch must show **PASSED** with zero publish blockers. Use Review or Batch Editor to correct blockers.

### Stage 2 — Simulate

Select **Run Shopify simulation**. Simulation is read-only and reports ready/blocked items, duplicate SKU checks, missing data, media, location, and configuration issues. It does not create or modify Shopify objects.

### Stage 3 — Create drafts

Select **Create Shopify Drafts**. SnapIMS:

- creates each draft;
- configures SKU, price, barcode, and inventory;
- attaches media;
- stores Product, Variant, and Inventory Item GIDs;
- displays durable progress, rate, elapsed time, ETA, per-item status, retries, and failures.

After completion, SnapIMS opens the Shopify draft-products page in another tab. Use **Open Created Drafts** to open it again.

### Stage 4 — Review drafts

Review in Shopify is optional but recommended. SnapIMS remains open. The product-management table includes direct Shopify links and copyable Product GIDs.

### Stage 5 — Publish live

Type `SUBMIT` exactly and select **Publish Drafts Live**. SnapIMS activates each product and publishes it to the selected publication. Items already completed are skipped on retry or resume.

### Fast track

Open **Fast track: publish directly**, type `SUBMIT LIVE`, and submit. This bypasses the review pause but still creates missing drafts before making them live.

## 6. Product management

Use Checked products or Entire batch with these actions:

- **Check Shopify status** — read-only reconciliation.
- **Keep SnapIMS — overwrite Shopify** — sync local working values to the linked product.
- **Keep Shopify — overwrite local working values** — accept supported remote values locally.
- **Merge non-conflicting values** — import non-conflicting remote values and leave unresolved differences visible.
- **Publish live** — requires `SUBMIT`.
- **Restore to draft** — requires `RESTORE`.
- **Archive on Shopify** — requires `ARCHIVE`.
- **Delete permanently from Shopify** — requires `DELETE`; irreversible.

Search, status filter, Select all visible, and Invert visible apply to the current page. Use the entire-batch scope for all Items.

## 7. Batch management

- Rename batch.
- Archive local batch with `ARCHIVE BATCH`.
- Restore archived or soft-deleted batch.
- Duplicate local batch with `DUPLICATE BATCH`; Shopify identities are cleared in the copy.
- Remove local batch with `DELETE BATCH`; this is a recoverable soft delete.
- Permanently deleting linked Shopify products is a separate Product Management action.

## 8. Recovery

- Refresh or restart during a Shopify job: reopen Publish; the durable job resumes.
- Failed items: select **Retry failed or interrupted Items**.
- Wrong release path: run `snapims status` and reinstall from the intended extracted release.
- Database issue: stop SnapIMS and restore only from a copied pre-schema-16 backup.
- Do not delete the database, token cache, source photographs, or batch folders as a troubleshooting shortcut.

## 9. Shutdown

```bash
snapims down
```

Stop SnapIMS before offline backups.
