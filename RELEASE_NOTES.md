# SnapIMS 0.9.0 Release Notes

Release type: **minor**.

0.9.0 completes the missing Apache Guacamole remote-workstation infrastructure without changing import, review, publish, AI recognition, catalog, database schema, or Shopify workflows.

## Remote Workstation

- Added `scripts/install_guacamole.sh`, an idempotent Linux installer for guacd, Guacamole protocol modules, xrdp, Java, Tomcat 9, `guacamole.war`, `/etc/guacamole`, and systemd services.
- Added authenticated Guacamole administrator setup with generated credentials stored in `/etc/guacamole/snapims-admin.env`.
- Added Guacamole connections for Linux Mint desktop over RDP and SSH terminal access, with clipboard support and file transfer where supported.
- Added `scripts/configure_cloudflare_guacamole.sh` to preserve
  `ims.canadavhs.ca` and add a separate Guacamole hostname. The current
  owner-designated hostname is `remote.canadavhs.ca`; the originally proposed
  `desktop.ims.canadavhs.ca` remains unresolved backlog.

## Service Manager

- `snapims up`, `down`, `restart`, `status`, and `doctor` now include Guacamole.
- Uninstalled hosts report Guacamole as unavailable with the missing component instead of silently omitting it.
- Diagnostics cover guacd, Tomcat, xrdp, Guacamole HTTP, guacd port 4822, RDP backend, and SSH backend.

## Boundary

This is not production 1.0.0. Live OpenAI quality/cost validation, one live Shopify draft, physical CSV reconciliation, and final operator acceptance remain required before 1.0.0.
