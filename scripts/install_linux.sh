#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
scripts/install_launcher.sh
echo "Installed. Validate with: snapims doctor"
