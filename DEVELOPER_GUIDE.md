# SnapIMS v0.15.0 Developer Guide

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pytest
python -m compileall snapims tests scripts
node --check snapims/web/static/app.js
bash -n install_v0150.sh
```

## Shopify architecture

- `snapims/shopify/auth.py`: encrypted client-credentials token lifecycle.
- `snapims/shopify/client.py`: GraphQL transport and product/inventory/publication operations.
- `snapims/shopify/service.py`: Item-level draft, publish, sync, reconcile, archive, restore, and delete operations.
- `snapims/shopify/jobs.py`: durable batch/selected-item orchestration, progress, retry, resume, and idempotency.
- `snapims/web/app.py` and `publish.html`: operator workflow and management endpoints.

Use bounded database pages. Never expose secrets in HTML/logs. Never retry permission/user errors as authentication failures. Completed durable job items must remain terminal on resume.
