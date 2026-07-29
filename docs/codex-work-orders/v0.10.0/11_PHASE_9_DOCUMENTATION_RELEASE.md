# Phase 9 — Documentation Synchronization, Versioning and Release Package

## Objective

Make the application, Operator Guide, screenshots, release documents and version metadata describe the exact same product.

## Version classification

This package adds operator workflows, schema and external-system integration.

Classification:

```text
Minor release: 0.10.0 → 0.10.0
```

Do not use 0.9.1 for the completed combined package.

Do not use 1.0.0.

## Synchronize version everywhere

Update:

- package version;
- `snapims.__version__`;
- browser footer/header;
- README;
- Release Notes;
- Operator Guide;
- Installation Guide;
- Deployment Guide;
- Developer Guide;
- Test Results;
- Browser Verification;
- Production Readiness;
- roadmap;
- archive names;
- generated screenshot captions;
- service/about output.

Search the active repository for obsolete version references. Historical archived reports may retain their historical version only if clearly under a history/archive path and not presented as current.

## Operator Guide

Use final browser UI as source of truth.

Assume first-time operator.

Cover:

- install/start;
- login;
- Import;
- duplicate Batch options;
- Recognition;
- model routing;
- force rerun;
- compare attempts;
- approved Tags;
- Review;
- Batch Editor;
- Inventory Search;
- Item detail and location move;
- Movie/catalog status;
- Settings;
- logs/Live Activity;
- CSV;
- Shopify setup;
- draft workflow;
- Orders;
- Pick Queue;
- missing/cancelled exceptions;
- recovery;
- cold boot;
- end-of-batch checklist;
- 1.0 acceptance boundaries.

Replace every affected screenshot at full useful resolution. Do not crop away important controls.

## Documentation walkthrough

After updating the guide:

1. use a clean browser session;
2. follow it step by step;
3. verify every label/button/path;
4. verify screenshots;
5. fix discrepancy;
6. repeat affected steps.

Do not claim guide verification from source review alone.

## Release evidence

Create:

```text
release-evidence/v0.10.0/
```

Include:

- baseline;
- tests;
- browser;
- Firefox;
- security;
- migration;
- database;
- scale;
- cold-boot;
- screenshots;
- support bundle sample;
- final report;
- production readiness;
- unresolved owner gates.

Sanitize evidence.

## Release archive

Build source/release archive excluding:

- `.git`;
- `.env`;
- secrets;
- production DB;
- WAL/SHM;
- media;
- logs;
- caches;
- cloud credentials;
- Guacamole credentials;
- backups.

Scan archive contents and extracted copy.

## Git completion

Before final commit:

```bash
git status
git diff --check
git diff --stat
```

Review all files.

Commit synchronized release.

Push branch:

```bash
git push -u origin feature/v0.10.0-final-preproduction
```

Do not merge automatically.

Do not create/tag `v1.0.0`.

A `v0.10.0` tag should only be created if the owner explicitly requests tagging after reviewing the release candidate.

## Final report

Use `14_FINAL_REPORT_TEMPLATE.md`.

State separately:

- implemented and verified;
- implemented but owner-live-gated;
- not implemented;
- deferred post-1.0;
- known risks;
- exact 1.0 blockers.

## Exit gate

- all active docs use 0.10.0;
- final UI and guide match;
- screenshots current;
- archive clean;
- tests/evidence referenced;
- branch pushed;
- working tree clean;
- 1.0 remains prohibited until acceptance gates pass.
