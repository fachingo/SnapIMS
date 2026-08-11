# Applying the SnapIMS v0.16.0 Rescue Port

## Do not use the failed donor as the base
Start with a real checkout of `fachingo/SnapIMS` at the authoritative v0.15.0/current pre-v0.16 main source.

## 1. Make a working copy
Do not point the first application attempt at production data. Use a source branch/copy and a copied test data directory.

## 2. Verify only

```bash
python /path/to/rescue-kit/scripts/apply_v0160_rescue_port.py /path/to/real/SnapIMS --dry-run
```

The script must report the mature Import/Recognition/Batch Editor/Publish/Shopify source anchors and test tree. It intentionally refuses the simplified failed donor build.

## 3. Apply

```bash
python /path/to/rescue-kit/scripts/apply_v0160_rescue_port.py /path/to/real/SnapIMS
```

The installer creates a timestamped `.snapims-v0160-backup/` copy of every mature file it edits before changing it.

## 4. Inspect the diff

```bash
git status
git diff --stat
git diff
```

No whole mature subsystem should be replaced. Import, Recognition, Batch Editor and Publish should still clearly contain their pre-v0.16 functionality.

## 5. Run tests

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
```

Do not weaken existing tests. Any pre-existing non-superseded failure caused by the port is a regression.

## 6. Run locally

Use a copied/nonproduction `SNAPIMS_DATA_DIR`, start SnapIMS normally, then complete the Browser Verification report.

## 7. External APIs
If production credentials are unavailable, use existing test/provider seams and controlled Shopify service doubles. Label simulated evidence as simulated. Do not claim live verification.

## 8. Finalize release evidence
Only after browser QA:
- capture new full-resolution screenshots;
- update the final Operator Guide with those screenshots;
- walk the guide against the browser;
- update production readiness;
- ensure active operator documentation references v0.16.0 consistently.
