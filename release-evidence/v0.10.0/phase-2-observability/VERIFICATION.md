# Phase 2 Observability Verification

Date: 2026-07-26 (America/Edmonton)

## Automated gates

- Full `python -m pytest -q`: PASS with one expected skip.
- `python -m ruff check .`: PASS.
- `python -m mypy snapims`: PASS across 38 source modules.
- `python -m build --no-isolation`: PASS; sdist and wheel built.
- `python -m compileall -q snapims`: PASS.
- `node --check snapims/web/static/app.js`: PASS.
- `git diff --check`: PASS.

## Contract coverage

- Schema 10 durable append-safe `operational_events` store and required indexes.
- Retention policy distinguishes debug, standard, business, and security records.
- Shared redaction covers nested data, headers, URLs, query strings, environment
  assignments, multiline exceptions, curl text, known secret values, email, and phone data.
- Application and consolidated JSONL files rotate at bounded sizes and use mode 0600.
- `snapims log` and `snapims logs` share structured filters, JSON, follow, and export.
- Recognition acceptance test traces queue, batch start, each item attempt/result, and batch result
  under one correlation ID.
- Catalog acceptance tests preserve local miss/candidate/ambiguity/link/failure facts.
- Shopify fake-transport tests identify the exact failed stage and retry attempt numbers.
- Duplicate import acceptance records the existing Batch ID and no duplicate creation.
- Live Activity has active operations, queue depths, filters, correlations, elapsed time,
  retry/recovery relationships, safe details, copy, bounded polling, and support-bundle export.
- Support bundles include version, commit, schema manifest, redacted settings, bounded events,
  job states, and health; credentials, customer PII, environment values, and images are excluded.

## Native browser

Playwright Firefox against real uvicorn: PASS.

Evidence: `release-evidence/v0.10.0/phase-2-firefox/`

- eight workflow checks passed;
- zero console errors;
- zero page errors;
- polling remained bounded to 100 rows;
- support bundle contained no secret fixture;
- durable event remained visible after a server restart.
