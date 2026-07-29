# Reference Index

## Included source files

The `References` directory contains:

- integrated v0.10.0 audit in Markdown and PDF;
- integrated pre-1.0 v0.10.0 roadmap in Markdown and PDF.

These are planning references. The live repository and final browser UI remain source of truth.

## Current official technical references to inspect during implementation

### Shopify

- GraphQL Admin API current/latest documentation.
- `inventoryActivate` and required `@idempotent` key for API versions from 2026-04 onward.
- `inventorySetQuantities` compare-and-set and idempotency.
- `fulfillmentCreate`.
- Orders query pagination and update filtering.
- Webhook delivery, headers, HMAC and ordering caveats.

### Wikimedia/Wikidata

- Wikidata database download page.
- Wikidata JSON entity dumps and incremental dumps.
- Wikimedia API access policy.
- Wikimedia API rate limits.
- MediaWiki Action API etiquette.
- Wikibase REST/Action APIs.

Key operating rules:

- meaningful User-Agent with contact;
- bounded concurrency;
- Retry-After;
- exponential backoff;
- cache;
- use bulk dumps for bulk acquisition rather than abusing interactive APIs;
- Wikidata structured data is CC0;
- Wikipedia text has separate attribution/licence requirements.

### OpenAI

Inspect official current:

- model list;
- image input;
- Responses API structured outputs;
- usage fields;
- rate limit/error behaviour.

### Cloudflare

Inspect official current:

- locally managed tunnel config;
- Linux service;
- Access policy;
- connector status;
- origin health.

## Evidence warnings

- Older SnapIMS status documents contain claims disproved by later Firefox testing.
- Old Operator Guides are not final UI truth.
- Do not use old screenshots as acceptance evidence.
