# SnapIMS synthetic demonstration

The demo generator creates ten JPEGs with EXIF capture timestamps and real QR codes. The sequence is:

1. `CVHS1:BATCH:START`
2. `CVHS1:LOC:B2`
3. item 1 front
4. item 1 back
5. `CVHS1:ITEM:NEXT`
6. `CVHS1:FLAG:RARE`
7. `CVHS1:FLAG:REVIEW`
8. item 2 front
9. item 2 open-case view
10. `CVHS1:BATCH:END`

This demonstrates a two-photo ordinary item and a two-photo rare/review item. It deliberately does not use timestamp gaps as boundaries.

## Generate the camera roll

From the repository root after installation:

```bash
rm -rf demo-data
.venv/bin/snapims demo demo-data/camera-roll
```

`demo-data/` is ignored by Git. The `rm -rf demo-data` line is optional and should only be used for this generated demo directory.

## Run through the interface

1. Launch with `./scripts/run_snapims.sh`.
2. Open **Import batch**.
3. Paste the absolute `demo-data/camera-roll` path.
4. Optionally enter `DEMO` as the batch name.
5. Choose **Dry-run parser preview**. Confirm 2 items, 4 product images, 6 commands, and no grouping based on time gaps.
6. Choose **Preserve and import batch**.
7. Open **Command events** and inspect the six audited command images.
8. Open **Item grid** and confirm two B2 item cards.
9. Open **Item editor**, add a title and price, set a valid condition, mark the item READY, and save.
10. Open **Validation** and confirm the edited item is READY.
11. Open **Recognition**, select `mock`, generate a suggestion, and observe that the item remains unchanged until **Accept selected fields** is used.
12. Open **Shopify dry-run**. With no credentials, confirm `SIMULATE_CREATE_DRAFT`; no network write is made.

## Expected identifiers and files

The Batch ID uses the system date/time at import, optionally followed by `-DEMO`. Item identities are immutable:

```text
<batch-id>-B2-001
<batch-id>-B2-002
```

Processed images are:

```text
<batch-id>-B2-001-F.jpg
<batch-id>-B2-001-02.jpg
<batch-id>-B2-002-F.jpg
<batch-id>-B2-002-02.jpg
```

The title never appears in authoritative filenames.

## Command-line verification

```bash
.venv/bin/snapims --data-dir demo-data/workspace preview demo-data/camera-roll
.venv/bin/snapims --data-dir demo-data/workspace import demo-data/camera-roll --batch-name DEMO
.venv/bin/snapims --data-dir demo-data/workspace integrity
```

Expected integrity output:

```text
integrity_check=ok
foreign_key_violations=0
```

Inspect the database without changing it:

```bash
sqlite3 demo-data/workspace/database/inventory.sqlite3 \
  "SELECT batch_id,item_count,product_photo_count,command_count FROM batches;"
sqlite3 demo-data/workspace/database/inventory.sqlite3 \
  "SELECT item_id,shelf,sequence,rare,review FROM items ORDER BY sequence;"
```

## CSV round-trip

The import creates `processed/<batch-id>/inventory_work.csv`. Edit Title, Price, Condition, and Ready status, then use **CSV workflow** to upload it. Reordering rows is safe. Changing Item ID to an unknown value blocks the entire import transaction.

## Re-run behavior

Import the same camera directory again. The SHA-256 source fingerprint resolves to the prior batch, no second database batch is created, and `duplicate=true` is reported by the CLI. If processing is interrupted before database commit, the next run resumes the fingerprint-specific staging workspace.
