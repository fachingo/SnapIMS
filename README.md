# SnapIMS 0.5.1

SnapIMS is a photo-first inventory ingestion system built around deterministic QR event capture, AI-assisted recognition, exception-only Review, immutable inventory identity, CSV reconciliation, and Shopify draft output.

## Routine workflow

```text
Photograph -> Preview/Import -> Identify -> Approve exceptions -> Simulate/Export
```

Correctly recognized tapes normally require one action: **Approve & Next**. Price and Discount remain inline; Edit is reserved for exceptions.

## Install

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
snapims --data-dir ~/SnapIMS-data serve
```

## Quality commands

```bash
pytest -q
ruff check .
mypy snapims --ignore-missing-imports
python -m compileall -q snapims
python -m build
pip check
```

## Verification record

- 110 collected pytest tests pass locally.
- Native Chromium-to-uvicorn audit passes.
- 20-item fast path: 1.20 clicks/tape; 85% one-click.
- Average application approval-to-next render: 0.091s.
- Real operator time remains a live-pilot measurement.

The restricted reconstruction environment could not install Ruff, MyPy, or the `build` frontend. Their exact commands remain in GitHub Actions and are not falsely marked passed.

## Documentation

- `SnapIMS_Operator_Guide.pdf` / `.docx`
- `NATIVE_BROWSER_VERIFICATION.md`
- `FINAL_OPERATOR_AUDIT.md`
- `FINAL_PRODUCTION_READINESS.md`
- `V0.5.1_DISCREPANCY_CLOSURE_REPORT.md`
- Phase 1-5 verification reports

## Version policy

0.5.1 is a patch release. 1.0.0 remains forbidden until all real production acceptance gates pass.
