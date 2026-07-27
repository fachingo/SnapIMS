# Phase 6 — Rights-Respecting Movie Database Acquisition and Catalog Completion

## Objective

Build a useful permanent local Movie database from rights-approved structured sources without copying a proprietary provider database or slowing Review.

## Data-source decision

Initial structured candidate source:

```text
Wikidata
```

Reason:

- structured data;
- CC0;
- official APIs and dumps;
- commercial reuse allowed for structured data;
- external QIDs remain references, not local identity.

Bounded enrichment source:

```text
English Wikipedia through official MediaWiki APIs
```

Do not:

- scrape IMDb;
- use DBpedia as the primary production source;
- use TMDb commercially without an approved agreement;
- mirror full Wikipedia article text;
- copy another provider's proprietary database;
- use unlicensed artwork.

## Provider-neutral contract

Define:

```text
search(title, year, region, media_type, limit) -> candidates
fetch(candidate_id, approved_fields) -> normalized facts + provenance
health() -> provider/capability state
policy() -> licence, attribution, retention, refresh and field policy
```

Provider IDs are not SnapIMS Movie IDs.

## Local-first flow

```text
AI/operator title
→ local Movie/alias FTS search
→ unique local match: reuse
→ otherwise Wikidata candidate search
→ optional bounded Wikipedia enrichment
→ ambiguity/unsupported: operator queue
→ durable local Movie
→ exact physical Item link
```

External calls run asynchronously after approval and must not delay `Approve & Next`.

## Wikidata API client

Requirements:

- official endpoint;
- meaningful User-Agent with SnapIMS version and contact URL/email configured in Settings;
- JSON;
- gzip;
- serial or max three concurrent requests;
- Retry-After handling;
- exponential backoff;
- timeout;
- cache;
- operation logging;
- bounded candidate count;
- no regex SPARQL text search;
- avoid high-cost open-ended queries.

Approved fields may include:

- label/canonical title;
- aliases;
- original title;
- release date/year;
- runtime;
- director;
- bounded cast;
- genre;
- country;
- language;
- media type evidence;
- English Wikipedia sitelink;
- provider revision/retrieval evidence.

Do not ingest unrelated claims.

## Wikipedia enrichment

After candidate selection or material uniqueness:

- use official Action/REST APIs;
- resolve redirect;
- identify disambiguation;
- retrieve page ID, revision, URL, title and bounded factual summary;
- descriptive User-Agent;
- rate/timeout/retry controls;
- store provenance;
- no complete article;
- no direct copied article prose as Shopify marketing description;
- preserve attribution metadata.

## Catalog states

Distinguish:

- LOCAL_MATCH;
- NEW_EXTERNAL_RECORD;
- AMBIGUOUS;
- SUPPORTED_FILM_NOT_FOUND;
- UNSUPPORTED_MEDIA_TYPE;
- CANDIDATES_REJECTED;
- PROVIDER_UNAVAILABLE;
- RATE_LIMITED;
- MALFORMED_RESPONSE;
- RETRY_QUEUED;
- MANUAL_MATCH_REQUIRED.

Do not collapse every case into `NOT_FOUND`.

## Minimum Edition model

Before 1.0 implement only needed VHS edition data:

- Edition ID;
- Movie ID;
- format;
- distributor;
- release year/date where known;
- barcode;
- packaging/edition text;
- language/region clues;
- source/evidence;
- physical Item relationship.

Do not delay this release on a complete collector-research workspace.

## CLI

Implement:

```text
snapims catalog status
snapims catalog init
snapims catalog bootstrap --from-inventory
snapims catalog bootstrap --title-list PATH
snapims catalog download wikidata --latest --destination PATH
snapims catalog import wikidata --source PATH --resume
snapims catalog sync-incremental
snapims catalog verify
snapims catalog backup
snapims catalog rebuild-index
```

Exact syntax may follow current parser conventions.

## Required production bootstrap

`bootstrap --from-inventory` is required and must be usable immediately.

It:

- finds distinct reviewed/current titles;
- includes year/media clues;
- checks local catalog first;
- calls external source only on genuine miss;
- preserves ambiguity;
- is restart-safe;
- is asynchronous/bounded;
- creates a report;
- never changes physical identity;
- can run against a verified production database or owner-approved copy.

Run it against a safe verified copy during implementation. Live production catalog bootstrap requires normal backup and owner awareness but is not a destructive external write.

## Optional full Wikidata dump

Implement support, but do not silently launch it.

Official source discovery must occur at runtime.

Before download:

1. inspect latest official dump metadata;
2. obtain compressed size;
3. inspect free space;
4. estimate temporary and imported size;
5. require `--yes` and/or `SNAPIMS_ALLOW_LARGE_CATALOG_DOWNLOAD=1`;
6. refuse safely if space is insufficient.

Downloader:

- HTTP Range resume;
- `.part`;
- atomic rename;
- official checksum validation where available;
- progress, speed, ETA;
- bounded retry;
- lock;
- no Git path;
- operational events.

Importer:

- stream BZ2/GZip JSON;
- do not load full dump;
- handle JSON-array framing;
- periodic transactions;
- durable checkpoint;
- restart/resume;
- extract only supported entities/fields;
- report scanned/accepted/rejected/malformed;
- avoid expensive per-entity network calls;
- store dump date/version;
- final integrity and FTS verification.

Incremental dumps:

- support official add/change dumps where practical;
- apply idempotently;
- keep source version/cursor;
- recover after interruption.

If full dump is too large:

- implement and test with bounded official sample/fixture;
- execute inventory-driven bootstrap;
- report actual remote size and local free space;
- print exact later command;
- do not claim full database import.

## Search/index

Use `movie_catalog.sqlite3`.

Preserve existing Movies and aliases. Add migrations, not recreation.

Required constraints:

- unique local Movie ID;
- provider-source uniqueness;
- title/year/media safeguards;
- aliases;
- FTS;
- source provenance;
- candidate decisions;
- no duplicate Movie from restart/retry.

## Acceptance

- clear supported film creates one durable Movie;
- second copy reuses local Movie without external request;
- same-title different-year remains distinct;
- unsupported media remains inventory but not forced into Movie;
- provider failure leaves Review operational;
- restart resumes jobs;
- correction/relink preserves history;
- every external field has provenance;
- inventory-driven database bootstrap completes;
- full-dump command is guarded and resumable;
- no proprietary or unlicensed data source is used.
