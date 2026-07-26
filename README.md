# SnapIMS 0.8.1

SnapIMS is a photo-first, exception-driven inventory workstation for Canada VHS. This release is an infrastructure patch: launcher installation, CLI validation, authentication setup, service/tunnel management, diagnostics, deployment docs, and regression coverage were hardened without redesigning import, review, publish, AI recognition, database schema, or Shopify workflows.

## Install

Clone SnapIMS anywhere, then install from the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
scripts/install_launcher.sh
```

Do not run the installer with `sudo`. It installs `snapims` into the current operator’s `~/.local/bin`, updates bash/zsh PATH startup files without duplicating entries, and reports success only after `snapims --help` and `snapims version` pass.

## Operate

```bash
snapims doctor
snapims up
snapims status
snapims restart
snapims down
```

Foreground development remains:

```bash
snapims serve
```

SnapIMS binds to `127.0.0.1:8767` by default. Use Cloudflare Tunnel or another trusted reverse proxy; do not expose the app directly with router port forwarding.

## Authentication

Set these in `.env` before exposing SnapIMS beyond local-only development:

```bash
SNAPIMS_AUTH_SECRET=<from snapims auth generate-secret>
SNAPIMS_ADMIN_USERNAME=admin
SNAPIMS_ADMIN_PASSWORD_HASH=<from snapims auth hash-password>
```

Reset an administrator password by running `snapims auth hash-password`, replacing `SNAPIMS_ADMIN_PASSWORD_HASH` in `.env`, then running `snapims restart`.

## Release status

Version 0.8.1 is a **patch** release. It is not production 1.0.0. Live OpenAI quality/cost validation, one live Shopify draft, physical CSV reconciliation, the real Pixel pilot, and final operator acceptance remain required before 1.0.0.
