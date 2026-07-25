#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
DATA_DIR="${SNAPIMS_DATA_DIR:-$HOME/SnapIMS-data}"
exec python -m snapims.cli --data-dir "$DATA_DIR" serve "$@"
