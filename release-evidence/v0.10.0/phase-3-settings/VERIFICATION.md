# Phase 3 Secure Settings Verification

Date: 2026-07-27  
Branch: `feature/v0.10.0-final-preproduction`  
Application milestone: `594283c`

## Implemented contract

- Explicit effective-value precedence: process environment, owner-only secret
  store, persisted non-secret setting, legacy `.env`, application default.
- Provenance and external-management state for every displayed non-secret
  setting.
- Schema 11 configuration revision history and OpenAI model-capability
  registry.
- Owner-only `secrets/` directory, mode-0600 secret and backup files,
  timestamped pre-replacement backups, atomic fsync-and-rename writes,
  masked read models, insecure-permission refusal, migration without legacy
  deletion, and rollback.
- Administrator re-authentication for secret saves, migration, rollback,
  credential changes, and session revocation.
- General, Recognition, Shopify, Movie Data, Infrastructure, Security, and
  Backup/Retention settings sections.
- Bounded OpenAI model discovery and image plus strict-schema compatibility
  probe; only compatible tested models can be assigned recognition roles.
- Read-only Shopify identity, current access-scope, capability-gap, and
  location discovery wizard; no mutation is issued from Settings.
- Wikimedia identification, bounded concurrency, minimum request spacing,
  `Retry-After`, exponential retry, timeout, cache, and candidate-provenance
  controls.
- Safe infrastructure status, login audit, credential rotation, and
  immediate session-generation revocation.
- Submitted test secrets are used in memory and never returned in HTML,
  redirects, diagnostic events, or support bundles.

## Current official API contracts checked

- OpenAI model list:
  `https://platform.openai.com/docs/api-reference/models/object`
- OpenAI Responses image inputs and strict `text.format` JSON schema:
  `https://platform.openai.com/docs/api-reference/responses`
- Shopify `currentAppInstallation`:
  `https://shopify.dev/docs/api/admin-graphql/latest/queries/currentAppInstallation`
- Shopify `shop`:
  `https://shopify.dev/docs/api/admin-graphql/latest/queries/shop`
- Shopify `locations`:
  `https://shopify.dev/docs/api/admin-graphql/latest/queries/locations`

The exact `SnapIMSConnectionProbe` GraphQL document was validated against the
current Shopify Admin schema before implementation. The runtime additionally
compares the granted handles returned by
`currentAppInstallation.accessScopes` with each SnapIMS capability instead of
assuming that a hard-coded token type is sufficient.

## Automated gates

| Gate | Result |
|---|---|
| Full `pytest` suite | PASS; one intentional skip |
| `ruff check .` | PASS |
| `mypy snapims` | PASS; 40 source modules |
| `compileall snapims` | PASS |
| Isolated sdist and wheel build | PASS |
| `git diff --check` | PASS |
| Schema 3 → 11 migration/restore tests | PASS |
| Secret precedence/provenance/atomicity/permissions/rollback tests | PASS |
| Provider request-shape and capability-gap tests | PASS |
| Authenticated settings HTTP and no-secret-echo tests | PASS |

The isolated build initially failed under the restricted sandbox because its
fresh environment could not resolve PyPI. It passed unchanged when rerun
through the approved network path.

## Native Firefox

Evidence: `release-evidence/v0.10.0/phase-3-firefox/`

- Real uvicorn server and Playwright Firefox.
- Stored-authentication login.
- All seven settings sections and provenance.
- Externally managed setting protection.
- Secure OpenAI-key save without echo.
- Wikimedia fixture candidate test and provenance preview.
- Support-bundle redaction.
- Restart retention from the secret store.
- Session revocation.
- Directory mode 0700 and secret file mode 0600.
- Ten checks passed; zero console errors; zero page errors.

No live OpenAI request, Shopify mutation, or full catalog dump was attempted.
