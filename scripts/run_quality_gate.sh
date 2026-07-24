#!/usr/bin/env bash
set -euo pipefail
pytest -q
ruff check .
mypy snapims --ignore-missing-imports
python -m compileall -q snapims
python -m build
python -m pip check
