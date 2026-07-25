# SnapIMS 0.5.1 Test Results

## Final local execution

| Gate | Exact result |
|---|---|
| `pytest -q` | **110 passed**; elapsed 00:29.26; max RSS 295,116 KB |
| `python -m compileall -q snapims` | Passed |
| Native Chromium -> uvicorn audit | Passed; 31 screenshots; genuine process interruption passed |
| Wheel build | Passed with `pip wheel . --no-deps --no-build-isolation` |
| Wheel | `snapims-0.5.1-py3-none-any.whl`; SHA-256 `ae8ed356553b1b09f593f9b7ec89100ca7577fb8011d846c8f9d906f83543654` |
| Installed-wheel smoke | Version 0.5.1; FastAPI app 0.5.1; Review template and CSS package resources present; CLI `--version` returned 0.5.1 |
| SQLite post-audit | integrity `ok`; zero foreign-key violations |

## Regression scope

110 tests are collected across 11 modules:

- CSV and partial-update safety: 16
- migration/database: 8
- processor/original preservation: 3
- QR/protocol/interpreter: 33
- recognition jobs/precedence/recovery: 11
- Review workflow: 20
- Shopify simulation/checkpoint/retry/media boundaries: 16
- web routes/startup: 3

This is meaningful reconstructed coverage, not a claim that the lost 285-test suite was reproduced byte-for-byte.

## Tooling that could not execute in this container

- `ruff check .`: Ruff was absent and the restricted package index returned no available Ruff distribution.
- `mypy snapims --ignore-missing-imports`: MyPy was absent and the restricted package index returned no available MyPy distribution.
- `python -m build`: the `build` frontend was absent. The same setuptools PEP 517 wheel was built successfully with pip using `--no-build-isolation`.
- `pip check`: the shared base environment reports a pre-existing unrelated conflict: MoviePy requires Pillow `<12.0`, while the container supplies Pillow 12.2.0. SnapIMS itself built, installed, imported, and passed the CLI/resource smoke.

No unavailable command is described as passed. `.github/workflows/quality.yml` runs pytest, Ruff, MyPy, compileall, `python -m build`, `pip check`, and installed-wheel smoke after an authorized push.
