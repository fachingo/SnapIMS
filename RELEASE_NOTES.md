# SnapIMS 0.8.1 Release Notes

Release type: **patch**.

0.8.1 finalizes infrastructure for the current development stage without changing import, review, publish, AI recognition, database schema, or Shopify workflow architecture.

## Infrastructure hardening

- Launcher refuses sudo/root installs.
- Launcher discovers the repository root from its own location instead of assuming `~/Projects/SnapIMS`.
- Installer manages `~/.local/bin` PATH setup for bash/zsh/profile without duplicate entries.
- Installer validates launcher existence, executable bit, `snapims --help`, and `snapims version` before reporting success.
- `.env` loading now resolves from the project root used by the launcher.
- CLI diagnostics distinguish required local checks from optional external integrations.
- Tunnel commands report missing `cloudflared`/config clearly instead of reporting `pid None`.
- systemd app service now uses the installed launcher instead of a hard-coded clone path.

## Authentication

- Password hashes use scrypt with embedded parameters.
- Session cookies are signed and validated against the configured administrator username.
- Partial authentication configuration fails closed.
- Login/logout flow is covered by smoke tests.
- Added `snapims auth generate-secret` and `snapims auth hash-password`.

## Validation

- Full automated test suite passes in the development environment.
- Whole-repo Ruff check passes.
- Compile validation passes for `snapims` and `tests`.

## Boundary

0.8.1 is not production 1.0.0. Live OpenAI quality/cost validation, one live Shopify draft, physical CSV reconciliation, the real Pixel pilot, and final operator acceptance remain required before 1.0.0.
