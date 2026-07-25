# Third-Party Notices

## English Wikipedia / MediaWiki

SLMC's optional external discovery path uses the official English Wikipedia MediaWiki Action API. Requests are bounded, identified by a descriptive User-Agent, rate limited, retried within configured limits and cached. Attribution/provenance is retained per Movie source.

No Wikidata, SPARQL, DBpedia, TMDb, IMDb scraping, full Wikipedia dumps or bulk crawling are included.

## Python dependencies

The package uses the host SnapIMS dependency set, including FastAPI, Jinja, SQLite, Pillow, Playwright tooling for browser verification, and standard Python networking/JSON libraries. Consult `pyproject.toml` and installed package licences before redistribution.

## Test fixtures

Wikipedia JSON fixtures are synthetic/minimal deterministic test data designed to exercise the client and parser. They do not prove live Wikipedia availability or licensing compliance for a production catalog export.
