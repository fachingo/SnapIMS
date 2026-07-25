# Wikipedia Data Policy

## Stored information

SLMC stores only information needed to identify and reuse a Movie record:

- page title, page ID, URL and revision ID;
- retrieval time, parser version and response hash;
- canonical/original titles and aliases;
- release year/date when available;
- media type, runtime, countries, languages, directors and broad genres;
- a concise neutral summary;
- candidate evidence and decision history;
- attribution metadata.

It does not copy full articles or preload unrelated pages.

## Facts versus prose

Facts and source identifiers are stored as structured fields. A concise summary or extract may contain copyrightable expression and can carry Wikipedia/CC BY-SA attribution obligations. Operators redistributing summaries must preserve source/revision attribution and assess share-alike requirements for the actual use. This package is technical documentation, not legal advice.

## Shopify restriction

Wikipedia prose is not automatically used as Shopify sales copy. Shopify simulation receives structured Movie facts only. Operator-authored or separately generated commercial descriptions remain distinct fields with their own provenance.

## Cache versus business data

`wikipedia_response_cache` is bounded transport cache. Normalized Movies, aliases, source links, revisions, candidates, decisions and catalog events are durable business data and must be backed up even if the cache is cleared.

## Attribution reference

The provider record stores enough data to identify the English Wikipedia page, revision and retrieval time. See `LICENSE_AND_ATTRIBUTION.md` and `THIRD_PARTY_NOTICES.md`.
