# Phase 1 Orchestration and Shopify Verification

Verified 2026-07-26 on `feature/v0.10.0-final-preproduction`.

## Scope

- Machine-readable required-component health with HTTP 503 on inventory database
  integrity, foreign-key, or schema failure.
- Process identity verification for managed PID files.
- Cloudflare process-versus-connector status and explicit service ownership.
- Guacamole-specific marker verification.
- Required-versus-optional `snapims doctor` checks and nonzero failure status.
- Explicit, inspectable `snapims update --check` and guarded
  `snapims update --apply`.
- Argv-safe interactive shell startup.
- Stable, pre-persisted Shopify inventory activation idempotency keys and
  ambiguous exact-SKU rejection.

## Results

| Check | Result |
|---|---|
| `python -m pytest -q tests/test_infrastructure.py tests/test_shopify.py` | PASS — 40 tests |
| `python -m pytest -q` | PASS — one expected skip |
| focused Ruff | PASS |
| `python -m compileall -q snapims tests` | PASS |
| `node --check snapims/web/static/app.js` | PASS |
| `python -m build --no-isolation` | PASS — sdist and wheel |
| `python -m pip check` | PASS |
| `git diff --check` | PASS |
| `python -m mypy snapims` | 16 pre-existing errors; no errors in changed modules |
| isolated `snapims update --check` | PASS; branch, upstream, dirty state, versions, schemas, migration/backup need, and restart impact printed |

No live Shopify writes were performed. Shopify behavior was verified with the
fake/capture transports and injected uncertain-timeout reconciliation tests.
