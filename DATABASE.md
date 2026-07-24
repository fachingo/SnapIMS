# SnapIMS 0.5.1 Database

SQLite schema version: **5**.

## Safety properties

- immutable `item_id` and matching SKU;
- foreign keys enabled on every application connection;
- WAL mode for local durability;
- explicit write transactions;
- backup before import, CSV import, Shopify live attempt, and legacy migration;
- post-migration integrity and foreign-key checks;
- unsupported future schema refused without modification;
- partial CSV import preserves absent columns;
- optimistic `record_revision` protects concurrent/stale edits;
- publish checkpoints and attempt history support reconciliation.

## Verified migration path

The test suite creates a real legacy v0.3-format fixture, upgrades it to schema 5, and verifies retained Item IDs, SKU, items, photos, recognition history, backup creation, and integrity. Failure injection verifies restoration of the original database. Future schema versions are refused safely.

## Integrity command

```bash
snapims --data-dir /path/to/workspace integrity
```

Expected:

```text
integrity_check=ok
foreign_key_violations=0
```
