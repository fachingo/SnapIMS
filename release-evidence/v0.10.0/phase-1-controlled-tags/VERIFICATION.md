# Phase 1 Controlled Tags and Shortcuts Verification

Verified 2026-07-26 on `feature/v0.10.0-final-preproduction`.

## Controlled Tags

- Inventory schema 9 defines immutable Tag IDs, canonical labels, aliases,
  categories, active/retired state, AI eligibility, Shopify visibility,
  deterministic-only state, ordering, timestamps, and evidence.
- Item relationships preserve source, assignment time, optional recognition
  result, and `SUGGESTED`/`ACCEPTED`/`REJECTED` state.
- Legacy comma-separated operator tags migrate to controlled definitions with
  deterministic IDs. The text field remains a compatibility projection.
- Unknown and newly selected retired tags are rejected transactionally.
- AI output is restricted to approved IDs; unknown, retired, AI-ineligible, and
  deterministic-only values are rejected into durable evidence.
- `TAG-TOONIE-TAPES` is explicitly AI-ineligible and deterministic-only.
- Review places Tags between Price and Discount. Batch Editor has a first-class
  Tags cell with pills and approved-ID autocomplete.

## Disposable production-data migration

A disposable copy of the live schema-8 inventory database was migrated:

| Check | Before | After |
|---|---:|---:|
| Schema | 8 | 9 |
| Batches | 4 | 4 |
| Items | 32 | 32 |
| Legacy tagged items | 0 | 0 |
| Controlled definitions | — | 1 deterministic seed |

The migration created a pre-schema-9 database backup. Post-migration
`integrity_check` was `ok`, foreign-key violations were zero, and the schema
manifest passed.

## Native Firefox

The durable audit is in `release-evidence/v0.10.0/phase-1-firefox/`.
Playwright Firefox navigated a real temporary uvicorn server; it did not use
TestClient or injected HTML.

- `Alt+P` opened the command palette.
- `Alt+1` opened the first visible quick action.
- `Alt+1` did nothing while typing in a grid input.
- approved Tag ID autocomplete opened and Enter accepted the result.
- Escape closed tag suggestions first without navigating.
- console errors: 0; page errors: 0.

The first audit detected CSP-blocked inline form handlers. Those handlers were
replaced with script event listeners before the passing audit was captured.

## Automated gates

| Check | Result |
|---|---|
| Full pytest suite | PASS — one expected skip |
| `python -m mypy snapims` | PASS — 37 source files |
| `python -m ruff check .` | PASS |
| JavaScript syntax, compileall, and diff check | PASS |
| sdist and wheel build | PASS |
