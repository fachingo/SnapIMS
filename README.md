# SnapIMS 0.9.0

SnapIMS is a photo-first, exception-driven inventory workstation for Canada VHS. This release adds the missing remote-workstation infrastructure: Apache Guacamole, guacd, a SnapIMS-owned Tomcat service, RDP desktop access, SSH terminal access, Cloudflare hostname setup, and CLI diagnostics. Import, review, publish, AI recognition, database schema, catalog, and Shopify workflows are unchanged.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
scripts/install_launcher.sh
sudo scripts/install_guacamole.sh
scripts/configure_cloudflare_guacamole.sh
```

`install_launcher.sh` must run as the operator user. It installs `snapims` into `~/.local/bin`, avoids duplicate PATH entries, and validates `snapims --help` and `snapims version`.

`install_guacamole.sh` installs packaged `guacd`, RDP/SSH/VNC protocol modules, `xrdp`, Java, and a dedicated Tomcat 9 under `/opt/snapims/tomcat9`. It deploys `guacamole.war`, writes `/etc/guacamole`, creates an authenticated `snapims-admin` account, and validates the local Guacamole login page before reporting success.

## Operate

```bash
snapims up
snapims status
snapims doctor
snapims restart
snapims down
```

`snapims up` starts SnapIMS, Cloudflare Tunnel when configured, guacd, xrdp, and the SnapIMS Guacamole Tomcat service. If Guacamole is not installed, `status` and `doctor` report it as unavailable with the missing component.

Default local URLs:

- SnapIMS: `http://127.0.0.1:8767`
- Guacamole: `http://127.0.0.1:8080/guacamole/`
- Remote desktop hostname: `https://desktop.ims.canadavhs.ca/guacamole/`

## Authentication

SnapIMS auth is configured in `.env`:

```bash
SNAPIMS_AUTH_SECRET=<from snapims auth generate-secret>
SNAPIMS_ADMIN_USERNAME=admin
SNAPIMS_ADMIN_PASSWORD_HASH=<from snapims auth hash-password>
```

Guacamole credentials are separate. The installer stores the generated Guacamole admin credential in `/etc/guacamole/snapims-admin.env`; retrieve it with `sudo cat /etc/guacamole/snapims-admin.env`.

## Release Status

Version 0.9.0 is a **minor** infrastructure release. Production 1.0.0 still requires final live OpenAI, Shopify, physical CSV reconciliation, and operator acceptance gates.
