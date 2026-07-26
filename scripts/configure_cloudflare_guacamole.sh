#!/usr/bin/env bash
set -euo pipefail

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

if [[ "${EUID}" -eq 0 ]]; then
  die "Do not run this script with sudo. It updates the operator user's Cloudflare tunnel config."
fi

: "${HOME:?HOME must be set}"

CONFIG_FILE="${CLOUDFLARE_TUNNEL_CONFIG:-$HOME/.cloudflared/config.yml}"
SNAPIMS_HOSTNAME="${SNAPIMS_CLOUDFLARE_HOSTNAME:-ims.canadavhs.ca}"
GUACAMOLE_HOSTNAME="${GUACAMOLE_CLOUDFLARE_HOSTNAME:-desktop.ims.canadavhs.ca}"
SNAPIMS_SERVICE="${SNAPIMS_CLOUDFLARE_SERVICE:-http://127.0.0.1:8767}"
GUACAMOLE_SERVICE="${GUACAMOLE_CLOUDFLARE_SERVICE:-http://127.0.0.1:8080}"
TUNNEL_ID="${CLOUDFLARE_TUNNEL_ID:-}"

mkdir -p "$(dirname "$CONFIG_FILE")"

if [[ -z "$TUNNEL_ID" ]]; then
  credential_file="$(find "$HOME/.cloudflared" -maxdepth 1 -type f -name '*.json' | head -n 1 || true)"
  [[ -n "$credential_file" ]] || die "No Cloudflare tunnel credentials found in $HOME/.cloudflared"
  TUNNEL_ID="$(basename "$credential_file" .json)"
else
  credential_file="$HOME/.cloudflared/${TUNNEL_ID}.json"
fi
[[ -f "$credential_file" ]] || die "Cloudflare tunnel credentials not found: $credential_file"

if [[ ! -f "$CONFIG_FILE" ]]; then
  cat > "$CONFIG_FILE" <<EOF
tunnel: ${TUNNEL_ID}
credentials-file: ${credential_file}
ingress:
  - hostname: ${SNAPIMS_HOSTNAME}
    service: ${SNAPIMS_SERVICE}
  - hostname: ${GUACAMOLE_HOSTNAME}
    service: ${GUACAMOLE_SERVICE}
  - service: http_status:404
EOF
else
  cp "$CONFIG_FILE" "${CONFIG_FILE}.pre-guacamole"
  if ! grep -Fq "hostname: ${GUACAMOLE_HOSTNAME}" "$CONFIG_FILE"; then
    tmp_file="$(mktemp)"
    awk -v host="$GUACAMOLE_HOSTNAME" -v service="$GUACAMOLE_SERVICE" '
      $0 ~ /^[[:space:]]*-[[:space:]]*service:[[:space:]]*http_status:404[[:space:]]*$/ && inserted == 0 {
        print "  - hostname: " host
        print "    service: " service
        inserted = 1
      }
      { print }
      END {
        if (inserted == 0) {
          print "  - hostname: " host
          print "    service: " service
          print "  - service: http_status:404"
        }
      }
    ' "$CONFIG_FILE" > "$tmp_file"
    mv "$tmp_file" "$CONFIG_FILE"
  fi
  if ! grep -Fq "hostname: ${SNAPIMS_HOSTNAME}" "$CONFIG_FILE"; then
    printf 'WARNING: %s was not found in %s. Review the tunnel config before restarting cloudflared.\n' "$SNAPIMS_HOSTNAME" "$CONFIG_FILE" >&2
  fi
fi

if command -v cloudflared >/dev/null 2>&1 && [[ "${SNAPIMS_SKIP_CLOUDFLARE_DNS:-}" != "1" ]]; then
  cloudflared tunnel route dns "$TUNNEL_ID" "$GUACAMOLE_HOSTNAME"
fi

printf 'Cloudflare tunnel config: %s\n' "$CONFIG_FILE"
printf 'SnapIMS hostname preserved: %s -> %s\n' "$SNAPIMS_HOSTNAME" "$SNAPIMS_SERVICE"
printf 'Guacamole hostname added: %s -> %s\n' "$GUACAMOLE_HOSTNAME" "$GUACAMOLE_SERVICE"
