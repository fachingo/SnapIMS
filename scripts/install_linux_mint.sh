#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3 was not found. Install python3 and python3-venv, then retry." >&2
  exit 1
fi

"$PYTHON_BIN" -m venv "$PROJECT_DIR/.venv"
"$PROJECT_DIR/.venv/bin/python" -m pip install --upgrade pip
"$PROJECT_DIR/.venv/bin/python" -m pip install -e "$PROJECT_DIR"
"$PROJECT_DIR/.venv/bin/snapims" init
chmod +x "$PROJECT_DIR/scripts/run_snapims.sh"

DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/snapims.desktop"
mkdir -p "$DESKTOP_DIR"
{
  echo "[Desktop Entry]"
  echo "Type=Application"
  echo "Name=SnapIMS"
  echo "Comment=Photo-first inventory intake for Canada VHS"
  printf 'Exec="%s/scripts/run_snapims.sh"\n' "$PROJECT_DIR"
  echo "Icon=camera-photo"
  echo "Terminal=false"
  echo "Categories=Office;Utility;"
} > "$DESKTOP_FILE"
chmod +x "$DESKTOP_FILE"

echo
echo "SnapIMS installation complete."
echo "Launch it from the Linux Mint application menu, or run:"
echo "  $PROJECT_DIR/scripts/run_snapims.sh"
