# SnapIMS 0.9.0 Developer Guide

Use the existing architecture. Do not redesign import, review, publish, AI recognition, catalog, database schema, or Shopify workflows for infrastructure work.

## Setup

```bash
cd /path/to/SnapIMS
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
scripts/install_launcher.sh
```

System-level Guacamole work is isolated to reusable scripts:

```bash
sudo scripts/install_guacamole.sh
scripts/configure_cloudflare_guacamole.sh
```

Do not hand-edit host-specific assumptions into Python code. Use `SnapIMSConfig` environment variables for service names, ports, and URLs.

## Service Manager

```bash
snapims up
snapims status
snapims doctor
snapims restart
snapims down
```

The manager must report Guacamole as unavailable when `guacd`, `/etc/guacamole`, or `snapims-guacamole-tomcat` is missing. Tests should not require system packages to be installed.

## Quality Gate

```bash
python -m pytest -q
python -m ruff check .
python -m compileall -q snapims tests
bash -n scripts/install_guacamole.sh
bash -n scripts/configure_cloudflare_guacamole.sh
```
