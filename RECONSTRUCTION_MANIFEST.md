# SnapIMS v0.5.0 Reconstruction Manifest

## Authority

- Recoverable GitHub baseline: `fachingo/SnapIMS` `main`
- Baseline commit: `045d91f91aaabced14f64115d84725b77bc27c4a`
- Reconstructed release: **0.5.0**
- Intended review branch: `reconstruction/snapims-v0.5.0`
- Merge target: none; this package must be reviewed before any merge to `main`.

The lost GPT Work filesystem was not used. The recoverable GitHub source was reconstructed against the accepted Phase 1-5 reports, final operator audit, UX findings, production-readiness reports, and fast-approval verification supplied by the project owner.

## Included

- Complete Python package and FastAPI/Jinja browser application.
- SQLite schema version 5 and migration/backup handling.
- Deterministic QR parser and original-image preservation.
- Durable recognition jobs, restart recovery, and review cursors.
- One-click Review approval with inline Price and Discount.
- Exception editor, Later, completed-item correction, and validation.
- Configured/recent import folders and non-durable preview identity.
- CSV export/import with partial-column preservation.
- Shopify simulation and resumable checkpoint boundaries.
- Automated tests, GitHub Actions, browser audit harness, and evidence.
- Synchronized v0.5.0 Operator Guide in DOCX and PDF.

## Verification completed in the reconstruction environment

- `pytest`: 17 tests passed in three consecutive runs after the final recognition-start race repair.
- `python -m compileall -q snapims scripts tests`: passed.
- `python -m snapims.cli --version`: `0.5.0`.
- Wheel build with existing local build tools: passed using `--no-build-isolation`.
- Rendered-control Chromium audit: 20 correctly recognized tapes; 1.20 average clicks; 17/20 one-click approvals.
- DOCX: rendered to 26 pages and visually reviewed page by page.
- PDF: rendered to 26 pages and visually compared with the accepted DOCX render.

`ruff` and `mypy` are configured in `pyproject.toml` and `.github/workflows/quality.yml`, but those executables were unavailable in the reconstruction container. They must run through GitHub Actions after the branch is uploaded.

## External acceptance still required

This package is not 1.0.0. The following remain mandatory:

- Real 20-tape Pixel pilot.
- Live AI recognition on real tape images.
- One real Shopify draft and Shopify-side reconciliation.
- CSV reconciliation against the physical batch.
- Native deployed-browser walkthrough.
- First-time operator walkthrough using the final guide.
- No known production blockers.
