# SnapIMS 0.6.0

SnapIMS is a photo-first, exception-driven inventory workstation for converting physical-media collections into validated inventory records, CSV exports, and Shopify draft products.

The operating model is deliberately simple:

```text
Photograph + QR events
-> deterministic import
-> AI recognition
-> individual Review or Batch Editor
-> validated working batch
-> CSV / Shopify output
```

SnapIMS is not designed as a conventional data-entry application. Routine records should move through with minimal effort; operators spend their time on uncertainty and exceptions.

## What is new in 0.6.0

- Actionable recognition-failure recovery, including missing API-key guidance.
- Safe import-folder validation and a native **Browse Folder...** action for local desktop use.
- Three-tier media handling: preserved original, fast browser preview, and optimized AI derivative.
- Keyboard-first Review: Price is selected automatically and Enter executes **Approve & Next**.
- Integrated Batch Editor with inline editing, filters, confidence buckets, bulk operations, checkpoints, undo/redo, and session-view restoration.
- CSV upload with staged difference preview, validation, explicit apply, and rollback checkpoint.
- Externally reviewed batch confirmation for validated CSV/bulk workflows.
- Durable change history, optimistic-revision conflict protection, and recognition token accounting.

## Install on Linux

```bash
cd SnapIMS
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
python -m playwright install chromium
```

## Launch

```bash
cd ~/Projects/SnapIMS
source .venv/bin/activate
snapims --data-dir ~/SnapIMS-data serve
```

Open `http://127.0.0.1:8767`.

The terminal remains occupied while the server runs. A quiet terminal means SnapIMS is waiting normally. Stop it with `Ctrl+C`.

## Fast operator paths

### Individual Review

1. Confirm the photo and title.
2. Accept the displayed price by pressing Enter, or type a replacement price and press Enter.
3. The next unfinished tape opens with Price selected again.

### Batch Editor

Use the Batch Editor when many records need the same treatment or when low-confidence results should be grouped together. It supports inline edits, confidence filtering, bulk price/discount/location/tag operations, Fill Down, checkpoints, and row approval.

### CSV round trip

1. Download CSV from Publish.
2. Edit in Excel or LibreOffice.
3. Upload the edited file.
4. Inspect the field-level difference preview.
5. Apply valid changes; SnapIMS creates a rollback checkpoint first.
6. Optionally confirm the batch as externally reviewed after all validation blockers are resolved.

## Quality gates

```bash
scripts/run_quality_gate.sh
python scripts/native_browser_audit_v060.py
```

Current verification evidence is documented in `TEST_RESULTS.md` and `NATIVE_BROWSER_VERIFICATION.md`.

## Version status

SnapIMS 0.6.0 is a functional beta candidate for controlled pilot work. It is **not** 1.0.0. The real Pixel pilot, live AI run, live Shopify draft, physical CSV reconciliation, and final operator acceptance remain mandatory before production release.
