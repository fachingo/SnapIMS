# SnapIMS 0.8.1 Installation Guide

SnapIMS no longer requires a fixed `~/Projects/SnapIMS` clone path. Install from wherever the repository is cloned:

```bash
cd /path/to/SnapIMS
python3 -m venv .venv
.venv/bin/pip install -e .
scripts/install_launcher.sh
```

The launcher installer:

- refuses `sudo`/root installs;
- discovers the project root from `scripts/install_launcher.sh`;
- installs `~/.local/bin/snapims`;
- updates `.bashrc`, `.zshrc`, or `.profile` only when needed;
- avoids duplicate PATH entries;
- validates `snapims --help` and `snapims version` before reporting success.

If the installer says a shell restart or `source <profile>` is required, do that before running `snapims` in a new terminal.

Copy `.env.example` to `.env`, then configure authentication and any existing Cloudflare/OpenAI/Shopify settings:

```bash
cp .env.example .env
snapims auth generate-secret
snapims auth hash-password
```

Edit `.env`, then validate:

```bash
snapims doctor
snapims up
snapims status
snapims down
```
