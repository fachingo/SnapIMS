# SnapIMS v0.13.2 Deployment Guide

SnapIMS is local-first. Run application code from the extracted release and keep operator data under `~/SnapIMS-data`.

The installer manages:

- `~/.local/bin/snapims`
- `~/.config/systemd/user/snapims.service`
- the release `.venv`
- schema migration and backup

Remote Cloudflare/Guacamole deployment is environment-specific and was not verified in the sandbox. Configure authentication before public exposure. Verify with `snapims status`, direct browser testing, and access-control review.
