# SnapIMS 0.10.1 Operator Guide

This guide describes the v0.10.1 patch-level application. It is not the final
v1.0 Operator Guide acceptance document.

## Start and access

Start SnapIMS using the installed launcher or service commands already documented
for the Linux Mint host. Normal local access remains:

`http://127.0.0.1:8767`

Remote access must use the approved protected endpoint. SnapIMS refuses non-local
operation when application authentication is not configured. Host, Origin, and
CSRF checks remain active even in local authentication-disabled mode.

## Daily workflow

1. Open **Import** and select the source photo folder.
2. Preview the batch and review item/photo/command counts and warnings.
3. Preserve the import or choose the appropriate duplicate-batch action.
4. Open **Recognition** or **Review** and start identification when required.
5. In **Review**, confirm the photo and title. Adjust Price, Tags, or Discount only
   when needed.
6. Select **✓ Approve & Next**. SnapIMS opens the next unfinished physical sequence,
   wrapping only at the end.
7. Use **Edit details** only for exceptions.
8. Use **Batch Editor** for controlled batch-wide review and corrections.
9. Open **Publish** for validation, CSV round trip, external-review recording, and
   Shopify simulation.

The v0.10.1 Publish screen remains simulation-only. It does not include a live
Shopify Draft action.

## Recognition recovery

### Failed escalation after a valid baseline

SnapIMS preserves the baseline attempt and records the failed escalation as a
partial-route warning. Review the preserved attempt; do not assume the item has no
recognition result.

### Retry This Item

**Retry this item** queues a durable routed request and returns immediately. The
request can be inspected in Recognition and Diagnostics. Duplicate clicks do not
start parallel work for the same Item.

### Application restart

Interrupted recognition requests and Item leases become paused/recoverable. Resume
from Recognition. Do not delete recognition rows or reset Item IDs.

## Concurrent or stale editing

### Quick Approve conflict

When the same Item was changed in another tab or session, Quick Approve is rejected
with:

`This item changed in another session. Reload before saving.`

Reload the Item, review the current authoritative values, and approve again. No
partial stale overwrite is applied.

### Batch Editor save state

Batch Editor serializes saves per Item. A yellow/dirty field remains unsaved until
the newest value is acknowledged. A red field indicates a save conflict or error.
Do not navigate away while dirty or in-flight changes remain; the browser warning
is intentional.

## Recognition attempt acceptance

**Accept recognition metadata** applies the selected recognition identity/metadata
while preserving the current operator-approved Price and Discount. Commercial
values change only through the normal editable Price and Discount controls.

## Controlled Tags and keyboard use

- `Alt+P` opens the command palette.
- `Escape` closes the command palette or an open Tag suggestion list.
- Arrow keys move through Tag suggestions.
- Enter selects the active Tag suggestion.
- Visible focus outlines identify the active control.

## Shopify retry safety

The existing backend draft-upload service now reconciles intended photos by stable
SnapIMS photo identity. Unrelated Shopify media no longer satisfies completion.
The operator-facing Publish workflow remains simulation-only in this patch.

## Diagnostics

Use **Diagnostics** for redacted technical details and correlation information.
Operator pages show safe summaries. Raw SQL errors, secrets, internal paths, and
unredacted provider responses should not appear in browser messages.

## End-of-batch check

- No unfinished Items unless deliberately deferred.
- No failed or blocked Items without a documented recovery decision.
- Price and Discount values confirmed.
- Controlled Tags confirmed.
- Publish simulation reviewed.
- CSV changes previewed before apply.
- Any checkpoint restore verified before continuing.
- No dirty Batch Editor fields.
