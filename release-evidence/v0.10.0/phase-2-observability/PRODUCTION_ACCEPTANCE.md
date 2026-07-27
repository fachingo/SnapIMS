# Phase 2 Production Acceptance

Date: 2026-07-26 (America/Edmonton)

## Migration

- Application was stopped before migration.
- Inventory schema migrated from 9 to 10.
- Automatic rollback backup:
  `/home/isaiah/SnapIMS-data/backups/inventory-20260726-231208-344081-before-schema-v10.sqlite3`
- Batches retained: 4.
- Items retained: 32.
- `PRAGMA integrity_check`: `ok`.
- Foreign-key violations: 0.
- Schema manifest: PASS.
- Durable `migration.completed` event: PASS.

## Cold start and services

- `snapims up`: PASS.
- SnapIMS health: PASS.
- Cloudflare connector: RUNNING.
- Guacamole: RUNNING.
- `snapims status`: all required production components PASS/RUNNING.
- `snapims doctor`: every required check PASS.

## Production CLI

- `snapims log --source app --last 10 --json`: PASS; returned the structured
  `application.started` event with schema 10 recovery facts.
- `snapims logs --severity INFO --last 10`: PASS; returned migration, process,
  Guacamole, startup, and Cloudflare connector events.

## Recovery note

Startup correctly left two pre-existing v0.5 test-artifact import journals quarantined because
both staging and final paths exist. Automatic recovery was deliberately refused; no production
Batch or Item record was changed. This is retained as operator-visible recovery evidence rather
than silently deleting ambiguous media trees.
