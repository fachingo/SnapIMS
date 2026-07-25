#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
echo "Installed. Launch with: .venv/bin/snapims --data-dir ~/SnapIMS-data serve"
