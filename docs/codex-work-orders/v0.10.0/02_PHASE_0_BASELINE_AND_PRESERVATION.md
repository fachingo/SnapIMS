# Phase 0 — Baseline, Preservation and Architecture Reconciliation

## Objective

Establish a trustworthy restore point and determine exactly what the current repository implements before changing schema or workflow.

## Required inspection

Record:

- current branch, commit and upstream;
- working-tree state;
- installed package version;
- `pyproject.toml` version;
- `snapims.__version__`;
- inventory database path and schema version;
- catalog database path and schema version;
- migration files/functions;
- current service state;
- current public/local URLs;
- current authentication state;
- current OpenAI model and provider configuration without printing secrets;
- current Shopify configuration state without printing tokens;
- current documentation versions;
- ignored paths;
- latest test and browser evidence.

Inspect current implementations of:

- CLI;
- service manager;
- authentication;
- import/duplicate handling;
- Review;
- Batch Editor;
- recognition providers and jobs;
- catalog jobs;
- Settings;
- Diagnostics;
- CSV;
- Shopify outbound service;
- migrations;
- documentation generators.

## Preservation

Create a timestamped external backup root such as:

```text
~/SnapIMS-backups/v0.10.0-prework-YYYYMMDD-HHMMSS/
```

Back up when present:

- `inventory.sqlite3`;
- `movie_catalog.sqlite3`;
- originals and processed media manifest/checksum;
- exports;
- `.env` and secret files;
- Cloudflare config and credential filenames;
- Guacamole config;
- systemd unit files related to SnapIMS;
- Operator Guide and active release documents;
- current Git patch/bundle.

Do not place secret-bearing backups inside Git.

For SQLite backups:

- use the SQLite online backup API or `.backup`;
- do not copy a live WAL database unsafely;
- record SHA-256;
- record size;
- run integrity and foreign-key checks on the backup;
- open the backup using the current application schema code;
- perform a disposable restore probe.

For large media:

- record manifest and checksums;
- do not duplicate hundreds of gigabytes blindly if a verified snapshot already exists;
- state exactly what was and was not copied.

## Baseline tests

Run the full existing quality gate before edits.

Capture exact stdout/stderr and exit codes below:

```text
release-evidence/v0.10.0/baseline/
```

Required evidence:

- pytest;
- Ruff;
- type check;
- compileall;
- JS syntax;
- package build;
- installed-wheel smoke;
- pip check;
- database integrity;
- catalog integrity;
- schema manifest;
- secret scan;
- Git status;
- `snapims status`;
- `snapims doctor`;
- local `/health`;
- public SnapIMS endpoint;
- public Guacamole endpoint.

Do not enter or expose credentials during evidence capture.

## Architecture reconciliation report

Create:

```text
release-evidence/v0.10.0/baseline/ARCHITECTURE_RECONCILIATION.md
```

For every roadmap feature, mark:

- already implemented and verified;
- implemented but unverified;
- partially implemented;
- contradicted by current source;
- absent;
- obsolete;
- intentionally deferred.

Pay special attention to old claims about:

- Alt shortcuts;
- Tags;
- recognition escalation;
- Shopify idempotency;
- Settings;
- Firefox verification;
- current version;
- current production readiness.

## Branch and state

After preservation:

1. create/switch to `feature/v0.10.0-final-preproduction`;
2. create `V010_IMPLEMENTATION_STATE.md`;
3. commit only non-secret preservation metadata and baseline reports.

## Exit gate

Phase 0 passes only when:

- restore points are validated;
- unknown dirty changes are preserved;
- current schemas are known;
- current test state is recorded truthfully;
- current documentation contradictions are listed;
- no production secret/database/media is staged;
- the next phase can be resumed from the state file.
