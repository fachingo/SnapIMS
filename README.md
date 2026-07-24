# SnapIMS 0.5.0

SnapIMS is a photo-first, exception-driven inventory ingestion system. It turns a QR-delimited camera roll into durable inventory records, AI-assisted review, CSV output, and Shopify draft simulations.

## Operator workflow

1. Photograph `START`, a shelf card, each VHS, and `NEXT` between products.
2. Open **Import**, select the incoming folder, and preview grouping.
3. Preserve and import the batch.
4. Open **Review** and identify the batch.
5. For a correct tape, optionally adjust **Price** or **Discount**, then press **✓ Approve & Next**.
6. Use **Edit** only for exceptions. Use **Later** to leave a tape unfinished.
7. Open **Publish** to simulate drafts and download the versioned inventory CSV.

## v0.5.0 highlights

- One-click fast approval for correctly recognized tapes.
- Price and Discount remain editable in the fast path.
- Completed records reopen and save against the same immutable Item ID.
- Recognition progress is durable across application restarts.
- Physical batch position stays distinct from filtered queue position.
- Import uses configured and recent folders; manual paths are Advanced recovery.
- Preview is explicitly non-durable; import shows one durable Batch ID.
- CSV partial imports update only columns actually present.
- CSV now includes Release year and Discount percent.
- Shopify stages resume from durable checkpoints and verify media readiness.
- Browser UI is separated from domain services through a FastAPI application boundary.

## Install

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

## Run

```bash
.venv/bin/snapims serve --host 127.0.0.1 --port 8767
```

Then open `http://127.0.0.1:8767`.

## Generate a demonstration camera roll

```bash
.venv/bin/snapims demo demo-data/camera-roll --items 20
```

## Quality gates

```bash
pytest
ruff check .
mypy snapims --ignore-missing-imports
python -m compileall -q snapims
```

The repository includes GitHub Actions that runs the same gates on reconstruction and feature branches.

## Current release status

SnapIMS 0.5.0 is a functional beta candidate ready for a controlled real 20-tape Pixel pilot. It is not 1.0.0. Live AI quality, one real Shopify draft, physical QR performance, and the final production acceptance checklist remain unproven.

See:

- `SnapIMS_Operator_Guide.pdf`
- `FINAL_OPERATOR_AUDIT.md`
- `FINAL_PRODUCTION_READINESS.md`
- `RELEASE_NOTES.md`
- `RECONSTRUCTION_MANIFEST.md`
- `GITHUB_PUSH_STATUS.md`
