# SnapIMS 0.8.1 Deployment Guide

SnapIMS is a single-operator local web application. It should bind to localhost and be exposed only through a trusted tunnel or reverse proxy.

## Managed CLI

```bash
snapims up
snapims status
snapims restart
snapims down
```

`snapims up` starts the app, attempts to start the configured Cloudflare tunnel, and waits for the local health check. `snapims status` reports app process state, health, tunnel state, port, and version.

## Cloudflare Tunnel

SnapIMS does not create tunnels or change DNS. Keep the existing Cloudflare credentials and config, normally:

```bash
~/.cloudflared/config.yml
```

Optional `.env` settings:

```bash
SNAPIMS_CLOUDFLARED_BIN=cloudflared
CLOUDFLARE_TUNNEL_CONFIG=~/.cloudflared/config.yml
CLOUDFLARE_TUNNEL_NAME=
```

Validate tunnel readiness:

```bash
snapims tunnel status
snapims tunnel start
```

If credentials or `cloudflared` are missing, SnapIMS reports the specific reason and keeps the local app usable.

## Optional systemd user services

Service files are in `deployment/`. They intentionally depend on the installed `~/.local/bin/snapims` launcher so they do not hard-code a clone path.

```bash
mkdir -p ~/.config/systemd/user
cp deployment/snapims.service deployment/cloudflared.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user start snapims.service
systemctl --user status snapims.service
```

Enable services only after manual validation:

```bash
systemctl --user enable snapims.service
systemctl --user enable cloudflared.service
```
