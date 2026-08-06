# SnapIMS v0.15.0 Shopify Setup Guide

SnapIMS uses Shopify Dev Dashboard client credentials for a single-owner store integration. Client ID and Client Secret are saved once. Generated Admin API access tokens are encrypted, reused until near expiry, and refreshed automatically.

## Required app scopes

Configure and release only the scopes used by the active workflow:

| Scope | SnapIMS operation |
| --- | --- |
| `read_locations` | Discover and verify inventory locations. |
| `read_products` | Duplicate SKU detection and reconciliation. |
| `write_products` | Create/update drafts, product status, variants, media, archive, and delete. |
| `read_inventory` | Read current inventory state. |
| `write_inventory` | Activate inventory and set quantity at the selected location. |
| `read_publications` | List available storefront/publication targets. |
| `write_publications` | Publish products to the selected publication. |

After changing scopes, release the app version and approve the updated permissions in the store.

## Connect

1. Confirm the app is released, installed, and owned by the same Shopify organization as the store.
2. Open **Settings → Shopify connection**.
3. Enter the permanent `store-name.myshopify.com` domain without protocol or path.
4. Enter the Client ID and Client Secret from Shopify Dev Dashboard.
5. Enter the current SnapIMS administrator password.
6. Select **Test and save securely**.
7. Confirm store identity, authentication mode, token validity, and every required permission.
8. Select the inventory location by name.
9. Select the publication/storefront by name.
10. Confirm **Draft-first publishing: Enabled**.

## Token behavior

- Normal client-credentials tokens are short-lived.
- SnapIMS refreshes before expiry using a five-minute safety margin.
- A Shopify authentication failure triggers one refresh and one retry.
- Permission, GraphQL user, and validation errors do not cause refresh loops.
- Concurrent requests share one refresh under process and filesystem locks.
- Changing domain, Client ID, or Client Secret invalidates the prior cache.
- Restarting SnapIMS does not require re-entering credentials.

## Test safely

```bash
snapims shopify status
snapims shopify test
snapims shopify refresh
```

`shopify test` is read-only. It retrieves identity, scopes, locations, and publications. It does not create a product.

Use **Publish → Run Shopify simulation** before any write. The first real owner test should use one tape, create a draft, inspect it, then type `SUBMIT` to publish live only when verified.

## Remove or replace credentials

- To replace credentials, enter the replacement values and test/save again.
- To remove the connection, re-authenticate as administrator and type `REMOVE`.
- Removal deletes saved Shopify credentials and cached access only. Inventory, Shopify GIDs, job history, and reconciliation history remain.
- Legacy static tokens remain a deprecated fallback only for migration.
