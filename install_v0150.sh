#!/usr/bin/env bash
set -euo pipefail

RELEASE_VERSION="0.15.0"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DATA_DIR="${SNAPIMS_DATA_DIR:-$HOME/SnapIMS-data}"
VENV_DIR="$PROJECT_DIR/.venv"
WHEEL="$PROJECT_DIR/dist/snapims-${RELEASE_VERSION}-py3-none-any.whl"

fail() {
  printf 'SnapIMS installer error: %s\n' "$*" >&2
  exit 1
}

[[ -f "$WHEEL" ]] || fail "built wheel is missing: $WHEEL"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || fail "Python executable not found: $PYTHON_BIN"

"$PYTHON_BIN" - <<'PY' || fail "Python 3.12 or newer is required"
import sys
raise SystemExit(0 if sys.version_info >= (3, 12) else 1)
PY

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  if [[ "${SNAPIMS_VENV_SYSTEM_SITE_PACKAGES:-false}" == "true" ]]; then
    "$PYTHON_BIN" -m venv --system-site-packages "$VENV_DIR"
    # Offline release verification only: inherit the controlled host's installed
    # dependency paths without copying packages into the release.
    HOST_PATHS="$($PYTHON_BIN - <<'HOSTPY'
import sys
for value in sys.path:
    if value and ("site-packages" in value or "dist-packages" in value):
        print(value)
HOSTPY
)"
    VENV_SITE="$($VENV_DIR/bin/python - <<'VENVPY'
import site
print(site.getsitepackages()[0])
VENVPY
)"
    printf '%s\n' "$HOST_PATHS" > "$VENV_SITE/snapims-offline-host-paths.pth"
  else
    "$PYTHON_BIN" -m venv "$VENV_DIR"
  fi
fi

PIP_ARGS=(install --disable-pip-version-check --force-reinstall)
if [[ "${SNAPIMS_INSTALL_NO_DEPS:-false}" == "true" ]]; then
  PIP_ARGS+=(--no-deps)
fi
"$VENV_DIR/bin/python" -m pip "${PIP_ARGS[@]}" "$WHEEL"

mkdir -p "$DATA_DIR" "$DATA_DIR/batches" "$DATA_DIR/database" "$DATA_DIR/logs"

# The wrapper pins the extracted application directory while leaving the data
# directory external. Re-running the installer after moving the release rewrites it.
cat > "$VENV_DIR/bin/snapims" <<WRAPPER
#!/usr/bin/env bash
export SNAPIMS_PROJECT_PATH="$PROJECT_DIR"
export SNAPIMS_DATA_DIR="\${SNAPIMS_DATA_DIR:-$DATA_DIR}"
exec "$VENV_DIR/bin/python" -m snapims.cli "\$@"
WRAPPER
chmod +x "$VENV_DIR/bin/snapims"

SNAPIMS_PROJECT_PATH="$PROJECT_DIR" SNAPIMS_DATA_DIR="$DATA_DIR" \
  "$VENV_DIR/bin/python" - <<'PY'
from snapims import __version__, db
from snapims.catalog import db as catalog_db
from snapims.config import DataPaths

assert __version__ == "0.15.0", __version__
paths = DataPaths.from_root().ensure()
db.initialize(paths.db_file, paths=paths)
catalog_db.initialize(paths.catalog_db_file, paths=paths)
print(f"SnapIMS {__version__}: database initialization complete")
PY

# Install a stable per-user launcher that always pins this extracted release.
if [[ "${SNAPIMS_INSTALL_LAUNCHER:-true}" != "false" ]]; then
  LAUNCHER_DIR="$HOME/.local/bin"
  LAUNCHER="$LAUNCHER_DIR/snapims"
  mkdir -p "$LAUNCHER_DIR"
  cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/usr/bin/env bash
set -euo pipefail
export SNAPIMS_PROJECT_PATH="$PROJECT_DIR"
export SNAPIMS_DATA_DIR="\${SNAPIMS_DATA_DIR:-$DATA_DIR}"
exec "$VENV_DIR/bin/python" -m snapims.cli "\$@"
LAUNCHER_EOF
  chmod +x "$LAUNCHER"

  PROFILE_FILE="$HOME/.bashrc"
  case "$(basename -- "${SHELL:-bash}")" in
    zsh) PROFILE_FILE="$HOME/.zshrc" ;;
    bash) PROFILE_FILE="$HOME/.bashrc" ;;
    *) PROFILE_FILE="$HOME/.profile" ;;
  esac
  if ! grep -Fqs '$HOME/.local/bin' "$PROFILE_FILE" 2>/dev/null; then
    printf '\n# SnapIMS launcher\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$PROFILE_FILE"
  fi

  # Replace the per-user service definition so old source paths cannot survive an upgrade.
  USER_SERVICE_DIR="$HOME/.config/systemd/user"
  mkdir -p "$USER_SERVICE_DIR"
  cat > "$USER_SERVICE_DIR/snapims.service" <<SERVICE_EOF
[Unit]
Description=SnapIMS inventory application v$RELEASE_VERSION
After=network.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
Environment=SNAPIMS_PROJECT_PATH=$PROJECT_DIR
Environment=SNAPIMS_DATA_DIR=$DATA_DIR
ExecStart=$LAUNCHER serve
Restart=on-failure

[Install]
WantedBy=default.target
SERVICE_EOF
  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload >/dev/null 2>&1 || true
  fi

  INSTALLED_VERSION="$(PATH="$LAUNCHER_DIR:$PATH" "$LAUNCHER" version)"
  [[ "$INSTALLED_VERSION" == "$RELEASE_VERSION" ]] || fail "launcher resolved version $INSTALLED_VERSION instead of $RELEASE_VERSION"
fi

printf '\nSnapIMS v%s installed.\n' "$RELEASE_VERSION"
printf 'Application directory: %s\n' "$PROJECT_DIR"
printf 'Data directory: %s\n' "$DATA_DIR"
printf 'Batch Home Directory: %s/batches\n' "$DATA_DIR"
printf 'Next commands:\n'
printf '  source "%s/bin/activate"\n' "$VENV_DIR"
printf '  snapims version\n'
printf '  export PATH="$HOME/.local/bin:$PATH"\n'
printf '  snapims version\n'
printf '  snapims up\n'
