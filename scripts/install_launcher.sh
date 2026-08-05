#!/usr/bin/env bash
set -euo pipefail

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

if [[ "${EUID}" -eq 0 ]]; then
  die "Do not run scripts/install_launcher.sh with sudo or as root. Run it as the SnapIMS operator user so the launcher installs into that user's ~/.local/bin."
fi

: "${HOME:?HOME must be set}"

resolve_script_path() {
  local source="${BASH_SOURCE[0]}"
  local directory
  while [[ -h "$source" ]]; do
    directory="$(cd -P "$(dirname -- "$source")" >/dev/null 2>&1 && pwd)"
    source="$(readlink "$source")"
    [[ "$source" != /* ]] && source="$directory/$source"
  done
  directory="$(cd -P "$(dirname -- "$source")" >/dev/null 2>&1 && pwd)"
  printf '%s/%s\n' "$directory" "$(basename -- "$source")"
}

path_contains_install_dir() {
  case ":${PATH:-}:" in
    *":$install_dir:"*) return 0 ;;
    *) return 1 ;;
  esac
}

profile_contains_install_dir() {
  [[ -f "$profile_file" ]] || return 1
  grep -Fqs '$HOME/.local/bin' "$profile_file" && return 0
  grep -Fqs "$install_dir" "$profile_file"
}

script_path="$(resolve_script_path)"
script_dir="$(dirname -- "$script_path")"
project_root="$(cd -P "$script_dir/.." >/dev/null 2>&1 && pwd)"
python_path="$project_root/.venv/bin/python"
install_dir="$HOME/.local/bin"
launcher="$install_dir/snapims"

[[ -x "$python_path" ]] || die "SnapIMS virtual environment was not found at $python_path. Create it first with: python3 -m venv .venv && .venv/bin/pip install -e ."

mkdir -p "$install_dir"

project_literal="$(printf '%q' "$project_root")"
tmp_launcher="$(mktemp "$install_dir/.snapims.XXXXXX")"
backup_launcher=""
cleanup() {
  rm -f "$tmp_launcher"
  if [[ -n "$backup_launcher" ]]; then
    rm -f "$backup_launcher"
  fi
}
trap cleanup EXIT

restore_previous_launcher() {
  if [[ -n "$backup_launcher" ]]; then
    mv "$backup_launcher" "$launcher"
    backup_launcher=""
  else
    rm -f "$launcher"
  fi
}

cat > "$tmp_launcher" <<EOF
#!/usr/bin/env bash
set -euo pipefail
SNAPIMS_INSTALLED_PROJECT=$project_literal
SNAPIMS_PYTHON="\$SNAPIMS_INSTALLED_PROJECT/.venv/bin/python"
if [[ ! -x "\$SNAPIMS_PYTHON" ]]; then
  printf 'ERROR: SnapIMS virtual environment not found at %s\n' "\$SNAPIMS_PYTHON" >&2
  printf 'Recreate it from the project root: python3 -m venv .venv && .venv/bin/pip install -e .\n' >&2
  exit 127
fi
export SNAPIMS_PROJECT_PATH="\${SNAPIMS_PROJECT_PATH:-\$SNAPIMS_INSTALLED_PROJECT}"
exec "\$SNAPIMS_PYTHON" -m snapims.cli "\$@"
EOF
chmod +x "$tmp_launcher"

if [[ -e "$launcher" ]]; then
  backup_launcher="$(mktemp "$install_dir/.snapims.backup.XXXXXX")"
  cp "$launcher" "$backup_launcher"
fi

mv "$tmp_launcher" "$launcher"

profile_file=""
case "$(basename -- "${SHELL:-}")" in
  zsh) profile_file="$HOME/.zshrc" ;;
  bash) profile_file="$HOME/.bashrc" ;;
  *) profile_file="$HOME/.profile" ;;
esac

path_message=""
if path_contains_install_dir; then
  path_message="PATH already contains $install_dir; no shell profile change was required."
elif profile_contains_install_dir; then
  path_message="PATH entry already exists in $profile_file. Restart the shell or run: source $profile_file"
else
  {
    printf '\n'
    printf '# SnapIMS launcher PATH\n'
    printf 'case ":$PATH:" in\n'
    printf '  *":$HOME/.local/bin:"*) ;;\n'
    printf '  *) export PATH="$HOME/.local/bin:$PATH" ;;\n'
    printf 'esac\n'
  } >> "$profile_file"
  path_message="Added $install_dir to $profile_file. Restart the shell or run: source $profile_file"
fi

validation_path="$PATH"
if ! path_contains_install_dir; then
  validation_path="$install_dir:$PATH"
fi

if [[ ! -f "$launcher" ]]; then
  restore_previous_launcher
  die "Launcher validation failed: $launcher was not created."
fi
if [[ ! -x "$launcher" ]]; then
  restore_previous_launcher
  die "Launcher validation failed: $launcher is not executable."
fi
if ! PATH="$validation_path" snapims --help >/dev/null; then
  restore_previous_launcher
  die "Launcher validation failed: snapims --help did not run."
fi
if ! PATH="$validation_path" snapims version >/dev/null; then
  restore_previous_launcher
  die "Launcher validation failed: snapims version did not run."
fi

printf 'Installed launcher: %s\n' "$launcher"
printf 'Project root: %s\n' "$project_root"
printf 'Validation: PASS (launcher exists, executable, snapims --help, snapims version)\n'
printf '%s\n' "$path_message"
