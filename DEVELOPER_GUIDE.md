# SnapIMS v0.13.2 Developer Guide

Run from a clean environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pytest
python -m compileall snapims tests scripts
node --check snapims/web/static/app.js
bash -n install_v0132.sh
```

Resource rule: use SnapIMS closing connection contexts; do not rely on SQLite connection garbage collection. Large editor/publish routes must use bounded queries and must not embed complete tables in HTML/JSON.
