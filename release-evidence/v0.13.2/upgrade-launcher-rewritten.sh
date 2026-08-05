#!/usr/bin/env bash
set -euo pipefail
export SNAPIMS_PROJECT_PATH="/tmp/snapims-v0132-upgrade-test/release"
export SNAPIMS_DATA_DIR="${SNAPIMS_DATA_DIR:-/tmp/snapims-v0132-upgrade-test/data}"
exec "/tmp/snapims-v0132-upgrade-test/release/.venv/bin/python" -m snapims.cli "$@"
