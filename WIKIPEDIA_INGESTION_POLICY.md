# Wikipedia Ingestion Policy

## Approved endpoint scope

SLMC uses narrow requests to official English Wikipedia MediaWiki Action API endpoints. It does not use Wikidata, SPARQL, Wikidata dumps, DBpedia, TMDb, IMDb scraping, full Wikipedia dumps or indiscriminate crawling.

## Miss flow

1. Build a narrow title and optional-year query.
2. Request a bounded candidate set, normally no more than five.
3. Resolve redirects and detect disambiguation.
4. Retrieve only enough page, category, revision, extract and infobox evidence to establish film identity.
5. Reject obvious songs, albums, books, people, companies and unrelated episodes.
6. Persist all credible candidates.
7. Auto-select only when materially unique.
8. Repeat the local duplicate check inside the catalog transaction.
9. Create or update one permanent local Movie.
10. Store aliases, page identity, revision, retrieval, parser version, response hash and attribution.
11. Link the Item through durable reconciliation.

## Request controls

- descriptive User-Agent;
- one configurable minimum interval;
- bounded timeout;
- bounded retries;
- rate-limit state and retry evidence;
- idempotent job per recognition result;
- persisted response cache;
- no duplicate Wikipedia call for a completed/local job;
- Review browser never waits on the external request.

## Data boundary

Wikipedia may supply film-level facts. It is not authoritative for exact VHS distributor, VHS release year, UPC/barcode, packaging, Canadian edition, cover variant, physical condition, shelf, Price, Discount, rare status or quantity.

## Live testing

Deterministic tests use fixtures. A skipped-by-default live test is available with `SNAPIMS_LIVE_WIKIPEDIA_TEST=1`. The integration package browser audit used fixtures and does not claim a live network request.
