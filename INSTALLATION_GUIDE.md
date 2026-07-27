# SnapIMS 0.9.0 Installation Guide

SnapIMS is portable across Linux hosts. Do not depend on `~/Projects/SnapIMS`; clone the repository anywhere and install from the repository root.

## Application Launcher

```bash
cd /path/to/SnapIMS
python3 -m venv .venv
.venv/bin/pip install -e .
scripts/install_launcher.sh
```

The launcher installer refuses sudo/root, discovers the project root from its own location, installs `~/.local/bin/snapims`, updates shell PATH once, and validates `snapims --help` plus `snapims version`.

## Guacamole Remote Workstation

Run the reusable system installer:

```bash
sudo scripts/install_guacamole.sh
```

It installs and configures:

- `guacd` on `127.0.0.1:4822`;
- RDP, SSH, and VNC Guacamole protocol modules;
- `xrdp` bound to `127.0.0.1:3389`;
- Apache Tomcat 9 under `/opt/snapims/tomcat9`;
- systemd service `snapims-guacamole-tomcat`;
- `/etc/guacamole/guacamole.properties`;
- `/etc/guacamole/user-mapping.xml`;
- Guacamole admin account `snapims-admin`;
- desktop and SSH terminal connections.

Generated Guacamole admin credentials are stored root-only:

```bash
sudo cat /etc/guacamole/snapims-admin.env
```

Optional installer variables include `GUACAMOLE_ADMIN_USERNAME`, `GUACAMOLE_ADMIN_PASSWORD`, `SNAPIMS_OPERATOR_USER`, `GUACAMOLE_RDP_USERNAME`, `GUACAMOLE_SSH_USERNAME`, `GUACAMOLE_VERSION`, `TOMCAT_VERSION`, and `TOMCAT_HTTP_PORT`.

## Cloudflare Hostname

After Guacamole is local, add the remote desktop hostname to the existing tunnel:

```bash
scripts/configure_cloudflare_guacamole.sh
```

Defaults:

- `ims.canadavhs.ca` -> `http://127.0.0.1:8767`
- `remote.canadavhs.ca` -> `http://127.0.0.1:8080`

The script updates `~/.cloudflared/config.yml`, preserves the SnapIMS hostname when present, and runs `cloudflared tunnel route dns` unless `SNAPIMS_SKIP_CLOUDFLARE_DNS=1`.

The official public URL is
`https://remote.canadavhs.ca/guacamole/`. The unresolved
`desktop.ims.canadavhs.ca` name is not a current operator endpoint.

## Validate

```bash
snapims up
snapims status
snapims doctor
```

Manual system checks:

```bash
which guacd
systemctl status guacd
systemctl status snapims-guacamole-tomcat
ss -ltn
curl -I http://127.0.0.1:8080/guacamole/
```
