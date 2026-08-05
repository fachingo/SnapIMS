#!/usr/bin/env bash
set -euo pipefail

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    die "Run this installer with sudo: sudo scripts/install_guacamole.sh"
  fi
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found after installation: $1"
}

validate_account_name() {
  local value="$1"
  [[ "$value" =~ ^[A-Za-z0-9_.@-]+$ ]] || die "Invalid account name: $value"
}

download_with_hash() {
  local url="$1"
  local destination="$2"
  local algorithm="$3"
  local hash_url="${url}.${algorithm}"
  local hash_file="${destination}.${algorithm}"
  curl -fsSL "$url" -o "$destination"
  curl -fsSL "$hash_url" -o "$hash_file"
  local expected actual
  expected="$(awk '{print $1}' "$hash_file" | head -n 1)"
  actual="$("${algorithm}sum" "$destination" | awk '{print $1}')"
  [[ -n "$expected" && "$expected" == "$actual" ]] || die "Checksum verification failed for $url"
}

set_xrdp_global_value() {
  local key="$1"
  local value="$2"
  local file="/etc/xrdp/xrdp.ini"
  [[ -f "$file" ]] || die "xrdp.ini was not installed at $file"
  if grep -Eq "^${key}=" "$file"; then
    sed -i -E "s|^${key}=.*|${key}=${value}|" "$file"
  else
    sed -i "/^\[Globals\]/a ${key}=${value}" "$file"
  fi
}

require_root

GUACAMOLE_VERSION="${GUACAMOLE_VERSION:-1.6.0}"
TOMCAT_VERSION="${TOMCAT_VERSION:-9.0.120}"
TOMCAT_HTTP_PORT="${TOMCAT_HTTP_PORT:-8080}"
SERVICE_USER="${SNAPIMS_GUACAMOLE_SERVICE_USER:-snapims-guacamole}"
SERVICE_GROUP="${SNAPIMS_GUACAMOLE_SERVICE_GROUP:-snapims-guacamole}"
GUACD_SERVICE="${SNAPIMS_GUACD_SERVICE:-guacd}"
GUACD_SERVICE_USER="${SNAPIMS_GUACD_SERVICE_USER:-guacd}"
TOMCAT_SERVICE="${SNAPIMS_TOMCAT_SERVICE:-snapims-guacamole-tomcat}"
GUACAMOLE_HOME="${SNAPIMS_GUACAMOLE_CONFIG_DIR:-/etc/guacamole}"
GUACD_HOST="${SNAPIMS_GUACD_HOST:-127.0.0.1}"
GUACD_PORT="${SNAPIMS_GUACD_PORT:-4822}"
ADMIN_USERNAME="${GUACAMOLE_ADMIN_USERNAME:-snapims-admin}"
OPERATOR_USER="${SNAPIMS_OPERATOR_USER:-${SUDO_USER:-}}"
RDP_USERNAME="${GUACAMOLE_RDP_USERNAME:-$OPERATOR_USER}"
SSH_USERNAME="${GUACAMOLE_SSH_USERNAME:-$OPERATOR_USER}"

[[ -n "$OPERATOR_USER" ]] || die "Could not determine the operator user. Set SNAPIMS_OPERATOR_USER."
validate_account_name "$ADMIN_USERNAME"
validate_account_name "$RDP_USERNAME"
validate_account_name "$SSH_USERNAME"

OPERATOR_HOME="$(getent passwd "$OPERATOR_USER" | cut -d: -f6)"
[[ -n "$OPERATOR_HOME" && -d "$OPERATOR_HOME" ]] || die "Home directory not found for $OPERATOR_USER"

export DEBIAN_FRONTEND=noninteractive
if [[ "${SNAPIMS_SKIP_APT_UPDATE:-}" != "1" ]]; then
  apt-get update
fi
apt-get install -y \
  ca-certificates \
  curl \
  default-jre-headless \
  guacd \
  libguac-client-rdp0t64 \
  libguac-client-ssh0t64 \
  libguac-client-vnc0t64 \
  openssl \
  xorgxrdp \
  xrdp

require_command curl
require_command guacd
require_command java
require_command openssl

if ! getent group "$SERVICE_GROUP" >/dev/null; then
  groupadd --system "$SERVICE_GROUP"
fi
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --gid "$SERVICE_GROUP" --home-dir /opt/snapims/tomcat9 --shell /usr/sbin/nologin "$SERVICE_USER"
fi
if id -u "$GUACD_SERVICE_USER" >/dev/null 2>&1; then
  usermod -aG "$SERVICE_GROUP" "$GUACD_SERVICE_USER"
fi

install -d -o root -g root -m 755 /opt/snapims
install -d -o root -g root -m 755 /opt/snapims/downloads
TOMCAT_ARCHIVE="/opt/snapims/downloads/apache-tomcat-${TOMCAT_VERSION}.tar.gz"
TOMCAT_VERSION_DIR="/opt/snapims/apache-tomcat-${TOMCAT_VERSION}"
TOMCAT_HOME="/opt/snapims/tomcat9"

if [[ ! -x "$TOMCAT_VERSION_DIR/bin/catalina.sh" ]]; then
  download_with_hash \
    "https://downloads.apache.org/tomcat/tomcat-9/v${TOMCAT_VERSION}/bin/apache-tomcat-${TOMCAT_VERSION}.tar.gz" \
    "$TOMCAT_ARCHIVE" \
    "sha512"
  rm -rf "${TOMCAT_VERSION_DIR}.tmp"
  mkdir -p "${TOMCAT_VERSION_DIR}.tmp"
  tar -xzf "$TOMCAT_ARCHIVE" -C "${TOMCAT_VERSION_DIR}.tmp" --strip-components=1
  rm -rf "$TOMCAT_VERSION_DIR"
  mv "${TOMCAT_VERSION_DIR}.tmp" "$TOMCAT_VERSION_DIR"
fi
ln -sfn "$TOMCAT_VERSION_DIR" "$TOMCAT_HOME"
chmod +x "$TOMCAT_HOME"/bin/*.sh

sed -i -E "s|Connector port=\"[0-9]+\" protocol=\"HTTP/1.1\"|Connector port=\"${TOMCAT_HTTP_PORT}\" protocol=\"HTTP/1.1\"|" "$TOMCAT_HOME/conf/server.xml"

GUACAMOLE_WAR_SOURCE="/opt/snapims/downloads/guacamole-${GUACAMOLE_VERSION}.war"
download_with_hash \
  "https://downloads.apache.org/guacamole/${GUACAMOLE_VERSION}/binary/guacamole-${GUACAMOLE_VERSION}.war" \
  "$GUACAMOLE_WAR_SOURCE" \
  "sha256"
install -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 640 "$GUACAMOLE_WAR_SOURCE" "$TOMCAT_HOME/webapps/guacamole.war"

install -d -o root -g "$SERVICE_GROUP" -m 750 "$GUACAMOLE_HOME"
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 750 "$GUACAMOLE_HOME/extensions"
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 750 "$GUACAMOLE_HOME/lib"
cat > "$GUACAMOLE_HOME/guacamole.properties" <<EOF
guacd-hostname: ${GUACD_HOST}
guacd-port: ${GUACD_PORT}
api-session-timeout: 60
EOF
chown root:"$SERVICE_GROUP" "$GUACAMOLE_HOME/guacamole.properties"
chmod 640 "$GUACAMOLE_HOME/guacamole.properties"
cat > "$GUACAMOLE_HOME/guacd.conf" <<EOF
[server]
bind_host = ${GUACD_HOST}
bind_port = ${GUACD_PORT}
EOF
chown root:"$SERVICE_GROUP" "$GUACAMOLE_HOME/guacd.conf"
chmod 640 "$GUACAMOLE_HOME/guacd.conf"

ADMIN_PASSWORD="${GUACAMOLE_ADMIN_PASSWORD:-}"
GENERATED_PASSWORD="0"
if [[ -z "$ADMIN_PASSWORD" ]]; then
  ADMIN_PASSWORD="$(openssl rand -base64 24)"
  GENERATED_PASSWORD="1"
fi
ADMIN_PASSWORD_MD5="$(printf '%s' "$ADMIN_PASSWORD" | md5sum | awk '{print $1}')"

if [[ -f "$GUACAMOLE_HOME/user-mapping.xml" ]] && ! grep -q "SNAPIMS MANAGED GUACAMOLE CONFIG" "$GUACAMOLE_HOME/user-mapping.xml"; then
  cp "$GUACAMOLE_HOME/user-mapping.xml" "$GUACAMOLE_HOME/user-mapping.xml.pre-snapims"
fi
cat > "$GUACAMOLE_HOME/user-mapping.xml" <<EOF
<user-mapping>
  <!-- SNAPIMS MANAGED GUACAMOLE CONFIG -->
  <authorize username="${ADMIN_USERNAME}" password="${ADMIN_PASSWORD_MD5}" encoding="md5">
    <connection name="Linux Mint Desktop">
      <protocol>rdp</protocol>
      <param name="hostname">127.0.0.1</param>
      <param name="port">3389</param>
      <param name="username">${RDP_USERNAME}</param>
      <param name="security">any</param>
      <param name="ignore-cert">true</param>
      <param name="enable-drive">true</param>
      <param name="drive-name">SnapIMS</param>
      <param name="drive-path">/var/lib/guacamole/drives/\${GUAC_USERNAME}</param>
      <param name="create-drive-path">true</param>
      <param name="resize-method">display-update</param>
    </connection>
    <connection name="SSH Terminal">
      <protocol>ssh</protocol>
      <param name="hostname">127.0.0.1</param>
      <param name="port">22</param>
      <param name="username">${SSH_USERNAME}</param>
      <param name="enable-sftp">true</param>
      <param name="sftp-hostname">127.0.0.1</param>
      <param name="sftp-port">22</param>
      <param name="sftp-username">${SSH_USERNAME}</param>
    </connection>
  </authorize>
</user-mapping>
EOF
chown root:"$SERVICE_GROUP" "$GUACAMOLE_HOME/user-mapping.xml"
chmod 640 "$GUACAMOLE_HOME/user-mapping.xml"

install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 750 /var/lib/guacamole
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 750 /var/lib/guacamole/drives
cat > "$GUACAMOLE_HOME/snapims-admin.env" <<EOF
GUACAMOLE_ADMIN_USERNAME=${ADMIN_USERNAME}
GUACAMOLE_ADMIN_PASSWORD=${ADMIN_PASSWORD}
EOF
chown root:root "$GUACAMOLE_HOME/snapims-admin.env"
chmod 600 "$GUACAMOLE_HOME/snapims-admin.env"

cat > /etc/default/guacd <<EOF
DAEMON_ARGS=
LISTEN_ADDRESS=${GUACD_HOST}
LISTEN_PORT=${GUACD_PORT}
GUACD_ARGS="-b ${GUACD_HOST} -l ${GUACD_PORT}"
EOF

GUACD_DROPIN_DIR="/etc/systemd/system/${GUACD_SERVICE}.service.d"
install -d -o root -g root -m 755 "$GUACD_DROPIN_DIR"
cat > "${GUACD_DROPIN_DIR}/snapims-permissions.conf" <<EOF
[Service]
SupplementaryGroups=${SERVICE_GROUP}
EOF

if command -v cinnamon-session-cinnamon >/dev/null 2>&1; then
  SESSION_COMMAND="cinnamon-session-cinnamon"
elif command -v cinnamon-session >/dev/null 2>&1; then
  SESSION_COMMAND="cinnamon-session"
else
  SESSION_COMMAND="x-session-manager"
fi
if [[ ! -f "$OPERATOR_HOME/.xsession" ]]; then
  printf 'exec %s\n' "$SESSION_COMMAND" > "$OPERATOR_HOME/.xsession"
  chown "$OPERATOR_USER:$OPERATOR_USER" "$OPERATOR_HOME/.xsession"
  chmod 644 "$OPERATOR_HOME/.xsession"
fi
set_xrdp_global_value "address" "127.0.0.1"
adduser xrdp ssl-cert >/dev/null 2>&1 || true

cat > "/etc/systemd/system/${TOMCAT_SERVICE}.service" <<EOF
[Unit]
Description=SnapIMS Apache Guacamole Tomcat
After=network.target ${GUACD_SERVICE}.service
Requires=${GUACD_SERVICE}.service

[Service]
Type=forking
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
Environment=GUACAMOLE_HOME=${GUACAMOLE_HOME}
Environment=CATALINA_HOME=${TOMCAT_HOME}
Environment=CATALINA_BASE=${TOMCAT_HOME}
Environment=CATALINA_PID=${TOMCAT_HOME}/temp/tomcat.pid
ExecStart=${TOMCAT_HOME}/bin/startup.sh
ExecStop=${TOMCAT_HOME}/bin/shutdown.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

chown -R "$SERVICE_USER:$SERVICE_GROUP" "$TOMCAT_VERSION_DIR"
systemctl daemon-reload
systemctl enable --now "$GUACD_SERVICE"
systemctl enable --now xrdp
systemctl restart "$GUACD_SERVICE"
systemctl restart xrdp
systemctl enable --now "$TOMCAT_SERVICE"
systemctl restart "$TOMCAT_SERVICE"

login_ok="0"
for _ in $(seq 1 60); do
  if curl -fsSL "http://127.0.0.1:${TOMCAT_HTTP_PORT}/guacamole/" | grep -qi "Guacamole"; then
    login_ok="1"
    break
  fi
  sleep 1
done
[[ "$login_ok" == "1" ]] || die "Guacamole login page did not become available on port ${TOMCAT_HTTP_PORT}"

printf 'Guacamole installation: PASS\n'
printf 'guacd: %s\n' "$(command -v guacd)"
printf 'guacd service: %s\n' "$GUACD_SERVICE"
printf 'Tomcat service: %s\n' "$TOMCAT_SERVICE"
printf 'Guacamole URL: http://127.0.0.1:%s/guacamole/\n' "$TOMCAT_HTTP_PORT"
printf 'Guacamole admin username: %s\n' "$ADMIN_USERNAME"
if [[ "$GENERATED_PASSWORD" == "1" ]]; then
  printf 'Generated admin password stored at: %s/snapims-admin.env\n' "$GUACAMOLE_HOME"
fi
