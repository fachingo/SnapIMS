# SnapIMS Local Movie Catalog Architecture

**Package:** SLMC-0.1.0  
**Host application:** SnapIMS 0.6.0  
**Source baseline:** `feature/v0.6.0-operator-workstation` at `5c316ca0e6c881c2df7ea2913d7f242a523fdc78`

## Purpose

SLMC adds a permanent, local, reusable Movie authority without turning Review into a metadata-entry workflow. The first-pass vision provider still recognizes the physical tape. SLMC then searches local business data, calls English Wikipedia only on a genuine miss, preserves candidates and provenance, and links the physical Item to an immutable local Movie ID.

This is not an API cache. `movie_catalog.sqlite3` is durable Canada VHS business data and must be backed up.

## Two-database authority boundary

| Database | Authority |
|---|---|
| `inventory.sqlite3` | Batch, Item, photographs, sequence, shelf, condition, Price, Discount, quantity, operator values, recognition history, Review state, CSV state, Shopify state, inventory events, current Item-to-Movie link and link-event audit |
| `movie_catalog.sqlite3` | Movie identity, canonical and alternate titles, release year, film facts, aliases, sources, revisions, retrieval provenance, candidates, decisions, catalog jobs, lookup attempts, bounded response cache, maintenance state, FTS/index state and catalog events |

The catalog never duplicates physical inventory rows. Inventory never stores large raw Wikipedia payloads.

## Recognition-to-catalog sequence

1. A recognition provider returns a result.
2. SnapIMS commits the original `recognition_results` row unchanged.
3. `queue_recognition_lookup()` builds a request from title, year, edition/distributor clues, confidence and `recognition_result_id`.
4. Local canonical titles, aliases, title/year evidence, prior mappings and FTS are searched inline.
5. A materially unique local result is linked immediately with no Wikipedia request.
6. A miss creates one restart-safe catalog job and runs bounded external discovery in a background worker.
7. Candidates, attempts and errors are persisted.
8. A materially unique result is normalized into one permanent Movie, then linked to the Item.
9. Ambiguity remains explicit and is resolved by an operator candidate selection or title correction.
10. Review renders operator value → local Movie canonical title → AI suggestion → manual untitled state.

## Cross-database consistency

SQLite cannot enforce a foreign key between the two files. SLMC therefore uses durable reconciliation rather than claiming atomicity across databases:

1. Locate or commit the Movie in the catalog transaction.
2. Record a catalog event and revision.
3. Commit the one-current-link row and link-event audit in inventory.
4. If inventory linking fails, retain the shared Movie and mark the job `LINK_PENDING`.
5. Reconcile idempotently after restart.
6. Never delete a Movie because one Item link failed.

## Failure isolation

Catalog initialization, structural verification, write failure, corruption or unavailability cannot roll back committed recognition or physical inventory. Review falls back to the original AI suggestion and shows Catalog unavailable. Approve & Next remains available unless the title itself is missing or materially ambiguous. CSV and Shopify simulation omit catalog facts rather than inventing them.

## Concurrency controls

- One catalog job per `recognition_result_id`.
- Unique provider/page source identity.
- Duplicate check repeated inside the catalog write transaction.
- Unique Movie/normalized-title/year/media identity guard.
- Unique alias constraints.
- One current inventory link per Item.
- Audited relink history.
- Leased job state and orphan recovery.
- Shared Movie retained when link retry is required.

## Provider boundary

Review, CSV and Shopify depend on normalized Movie domain objects, not MediaWiki field names. The current provider implementation uses official English Wikipedia/MediaWiki endpoints only. It does not use Wikidata, SPARQL, DBpedia, TMDb, IMDb scraping or full dumps.

## Operator contract

The routine path is unchanged:

1. Look at the photograph.
2. Confirm the title.
3. Optionally change Price.
4. Optionally change Discount.
5. Click **Approve & Next** or press Enter once.

Catalog status is compact evidence. Full candidate/source detail belongs in exception and administration views.
