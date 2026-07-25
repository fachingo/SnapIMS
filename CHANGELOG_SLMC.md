# SLMC Changelog

## SLMC-0.1.0

Initial standalone integration package for SnapIMS 0.6.0.

### Added

- independent permanent `movie_catalog.sqlite3` and catalog schema 1;
- immutable local Movie IDs;
- indexed local title/alias/year search and FTS5 fallback;
- official English Wikipedia bounded discovery client;
- source revision, retrieval, parser, response-hash and attribution provenance;
- idempotent restart-safe catalog jobs, candidates, decisions and attempts;
- inventory schema 7 with one-current-link and append-only link events;
- post-recognition local-first lookup;
- compact Review catalog states and ambiguity resolution;
- operator-title correction and stale-link handling;
- structured CSV and Shopify simulation Movie fields;
- diagnostics, backup, integrity, search-index, retry, import/export, alias, merge and split tools;
- synthetic scale benchmarks and browser evidence;
- deterministic fixtures and optional skipped live Wikipedia test;
- integration documentation, migration references and archive safety scanner.

### Preserved

Import, Publish navigation, QR grouping, Item IDs, Batch IDs, physical photos, operator Price/Discount, recognition history and draft-only Shopify policy.

### Release classification

SLMC remains package version 0.1.0. After blending, this capability is a **minor SnapIMS release**. No exact host version is assigned here. SnapIMS 1.0.0 remains prohibited until all production acceptance gates pass.
