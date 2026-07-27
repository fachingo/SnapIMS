# Phase 3 Production Acceptance

Date: 2026-07-27  
Branch: `feature/v0.10.0-final-preproduction`

## Migration

- Before: inventory schema 10, integrity `ok`, zero foreign-key
  violations, 4 batches, 32 items.
- Automatic backup:
  `/home/isaiah/SnapIMS-data/backups/inventory-20260727-130108-376761-before-schema-v11.sqlite3`
- After: inventory schema 11, integrity `ok`, zero foreign-key
  violations, manifest pass, 4 batches, 32 items.
- Added empty production tables for configuration revisions and tested
  provider-model capabilities. No production credential or setting was
  changed by the migration.

## Runtime

- Normal `snapims restart`: PASS.
- Full `snapims down` then `snapims up` cold boot: PASS.
- Application health: PASS.
- Cloudflare tunnel: RUNNING.
- Guacamole, guacd, Tomcat, xrdp, and SSH checks: PASS.
- Authentication: PASS.
- OpenAI configuration presence: PASS.
- Local `/health`: HTTP 200.
- Unauthenticated `/settings`: redirected to `/login`; final response has
  `Cache-Control: no-store`.

## Safety

- The existing project `.env` remains authoritative through the documented
  legacy-precedence tier and was not edited.
- No live OpenAI connection test or Shopify write was attempted.
- Production secret-store creation is deferred until the owner explicitly
  saves or migrates a credential in Settings.
- Production inventory identity and counts are unchanged.
