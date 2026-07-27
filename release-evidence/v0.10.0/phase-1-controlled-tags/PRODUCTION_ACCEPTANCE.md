# Schema 9 Production Acceptance

Accepted 2026-07-26 on the production SnapIMS data root.

- Automatic pre-migration backup:
  `/home/isaiah/SnapIMS-data/backups/inventory-20260726-221200-351595-before-schema-v9.sqlite3`
- Backup size: 1,007,616 bytes.
- Inventory identity before/after: 4 batches and 32 items.
- Production schema: 9.
- Controlled definitions: 1 deterministic seed; existing tagged items: 0.
- `PRAGMA integrity_check`: `ok`.
- Foreign-key violations: 0.
- Schema manifest: PASS.
- Catalog remained healthy and optional.

After migration, `snapims restart` passed local health. The stronger cold-boot
gate then ran `snapims down` followed by `snapims up`:

- SnapIMS: RUNNING;
- required health: PASS;
- Cloudflare connector: RUNNING;
- Guacamole: RUNNING.

The post-boot `snapims doctor` passed every required check, including
authentication, database, connector, Guacamole, guacd, Tomcat, RDP, and SSH.
The local `/health` response was HTTP 200 with inventory schema 9, integrity
`ok`, zero foreign-key violations, and stable component states.
