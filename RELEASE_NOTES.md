# SnapIMS Release Notes

## SLMC-0.1.0 integration package for SnapIMS 0.6.0

This is an isolated package, not a final SnapIMS semantic release.

### Added

- Permanent independent `movie_catalog.sqlite3` and catalog schema 1.
- Immutable local Movie IDs, normalized title/alias/year search and FTS fallback.
- Official English Wikipedia bounded miss lookup with descriptive User-Agent, limits, timeouts, retries, response cache and provenance.
- Restart-safe catalog jobs, candidates, decisions, ambiguity and link reconciliation.
- Inventory schema 7 with current Item-to-Movie links and append-only link events.
- Post-recognition local-first catalog lookup.
- Compact Review states without changing Approve & Next or Enter.
- Structured Movie fields in CSV and Shopify simulation.
- Catalog diagnostics, backup, verify, index rebuild, retry, search, inspect, alias, refresh, manual correction, merge, split, export and import tools.
- Deterministic tests, optional live Wikipedia test, browser audit, performance benchmark and integration documentation.

### Fixed during verification

- Final infobox fields no longer retain closing `}}` markup.
- Split maintenance jobs preserve their target Movie and reconcile `LINK_PENDING` Item links after restart.

### Preserved

Import, Publish/navigation layout, QR rules, Item/Batch IDs, photo grouping, Price, Discount, recognition history and draft-only Shopify policy.

### Version policy

The merged capability is a minor SnapIMS release. The exact version is chosen after blending and final browser verification. SnapIMS 1.0.0 remains prohibited until all production acceptance criteria pass.

## 0.6.0 - Operator workstation and stabilization

The original host release added native folder browsing, recognition recovery, image derivatives, keyboard-first Review, Batch Editor, CSV difference/apply/rollback, external review, durable history and token/media accounting.
