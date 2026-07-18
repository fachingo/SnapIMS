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

The repository already tracks the ten synthetic files under `demo-data/camera-roll/` as reproducible test fixtures. To generate a separate disposable camera roll without changing those fixtures:

```bash
.venv/bin/snapims demo /tmp/snapims-demo-camera-roll
```

Generated operator workspaces, databases, exports, logs, backups, and real inventory images are ignored or rejected by the release builder; only the explicitly tracked synthetic camera-roll images belong in Git.

## Run through the interface

1. Launch with `./scripts/run_snapims.sh`.
2. Open **Import**.
3. Paste the absolute `demo-data/camera-roll` path.
4. Optionally enter `DEMO` as the batch name.
5. Choose **Dry-run parser preview**. Confirm 2 items, 4 product images, 6 commands, and no grouping based on time gaps.
6. Choose **Preserve and import batch**.
7. In **Review**, expand batch details and confirm two B2 item cards plus the human-readable command timeline.
8. Use the deterministic `mock` provider to run recognition for the active batch.
9. Review suggestions with **Accept & next**, **Edit**, or **Later**. Recognition never changes authoritative fields until acceptance and never changes the physical REVIEW flag.
10. Complete required listing fields inline, mark valid items ready, and resolve the displayed validation reasons.
11. Open **Publish** and confirm the active batch is separated into Ready, Blocked, Drafted, and Failed queues.
12. Run **Simulate selected drafts** without credentials. This performs no network call.
13. Optionally inspect raw commands, validation, tables, logs, and storage under **Settings & diagnostics**.

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

The import creates `processed/<batch-id>/inventory_work.csv`. Under **Publish → CSV tools**, download the current file, edit Title, Price, Condition, and Ready status, then import it. Reordering rows is safe. Changing Item ID to an unknown value blocks the entire import transaction.

## Re-run behavior

Import the same camera directory again. The SHA-256 source fingerprint resolves to the prior batch, no second database batch is created, and `duplicate=true` is reported by the CLI. If processing is interrupted before database commit, the next run resumes the fingerprint-specific staging workspace.
