# Catalog Database Schema

**Database:** `<data-root>/database/movie_catalog.sqlite3`  
**Declared catalog schema:** 1  
**Migration ledger:** `catalog_schema_migrations`  
**Reference migration:** `snapims/catalog/migrations/0001_initial.sql`

## Durable tables

| Table | Role |
|---|---|
| `catalog_schema_migrations` | Declared version, application time, description and expected schema hash |
| `catalog_sequences` | Stable local ID allocation; Movie IDs are `MOV-########` |
| `movies` | One underlying film/work with canonical title, normalized keys, year, runtime, summary, quality state and revision |
| `movie_aliases` | Alternate/original/redirect/recognition titles with normalized and articleless keys |
| `movie_titles` | Region/language/title-type foundation |
| `movie_sources` | Provider page identity, URL, revision, retrieval, parser, response hash, attribution and field provenance |
| `movie_credits` | Director and future normalized credit rows |
| `movie_genres` | Broad genre facts |
| `movie_countries` | Country facts |
| `movie_languages` | Language facts |
| `catalog_lookup_jobs` | One idempotent restart-safe job per recognition result |
| `catalog_lookup_attempts` | Local/external phases, HTTP/error evidence and retry history |
| `movie_candidates` | Every credible bounded candidate and rejection reason |
| `movie_match_decisions` | Automatic or operator decision, reason, score and selected identity |
| `wikipedia_response_cache` | Bounded request responses; cache data is not the Movie authority |
| `catalog_settings` | Thresholds, rate limits, FTS capability and parser settings |
| `catalog_events` | Durable catalog audit events and revisions |
| `catalog_maintenance_jobs` | Restart-safe merge, split, import and maintenance operations |

## Search indexes

Routine recognition does not scan the full catalog. Indexed paths include normalized title/year, articleless title/year, normalized aliases, articleless aliases, source identity, job state, candidate ranking and event history. When FTS5 is available, `movie_search` provides Unicode-aware bounded candidate retrieval. If FTS5 is unavailable, exact indexed search continues and diagnostics reports fallback search mode.

## Structural verification

Startup does not trust a version integer alone. It verifies:

- migration ledger and schema hash;
- required tables and columns;
- required indexes and uniqueness constraints;
- `PRAGMA integrity_check`;
- `PRAGMA foreign_key_check`;
- FTS availability state.

A structurally incompatible catalog fails closed for catalog writes without replacing the file.

## Identity and uniqueness

- `movie_id` is immutable and independent of title and provider.
- A provider page has one active `movie_sources` identity.
- Same-title/different-year Movies remain distinct.
- Same-title/same-year but different media types remain distinct.
- A title alone is not globally unique.
- Aliases are unique within Movie/type/language constraints.

## Scale evidence

Synthetic measurements were captured for 10,000 and 100,000 Movies with 50,000 and 500,000 aliases. See `PERFORMANCE_REPORT.md` and `docs/slmc/evidence/performance/`.
