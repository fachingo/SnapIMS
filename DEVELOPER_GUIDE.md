# SnapIMS 0.8.1 Developer Guide

Use the existing architecture. Do not redesign import, review, publish, AI recognition, database schema, or Shopify workflows for infrastructure work.

Development setup:

```bash
cd /path/to/SnapIMS
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
scripts/install_launcher.sh
```

Run the app in the foreground:

```bash
snapims serve
```

Run managed local services:

```bash
snapims up
snapims restart
snapims status
snapims down
```

Configuration is centralized in `snapims.config.SnapIMSConfig`. `.env` is loaded from the project root resolved by `SNAPIMS_PROJECT_PATH` or by the installed launcher. Tests set `SNAPIMS_SKIP_DOTENV=1` to avoid consuming real operator credentials.

Quality gate:

```bash
python -m pytest -q
python -m ruff check .
python -m compileall -q snapims tests
```
