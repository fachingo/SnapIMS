# SnapIMS v0.15.0 Deployment Guide

SnapIMS is local-first. Keep release source separate from `~/SnapIMS-data`.

The installer manages the release virtual environment, `~/.local/bin/snapims`, user service, database backup, and schema-16 migration.

Before remote exposure:

- enable SnapIMS authentication;
- verify administrator password and session revocation;
- verify secret directory `0700` and secret files `0600`;
- confirm CSRF and allowed hosts;
- verify Cloudflare/Guacamole/xrdp independently;
- run `snapims status`, `snapims doctor`, and direct browser checks.

Remote owner infrastructure was not verified in the sandbox.
