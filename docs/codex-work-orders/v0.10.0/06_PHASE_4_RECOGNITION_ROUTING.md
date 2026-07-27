# Phase 4 — Recognition Control, Overrides and Staged Routing

## Objective

Use the cheapest model that is demonstrably reliable for routine tapes while preserving expert override, complete attempt history and manual authority.

## Attempt contract

Extend or replace the existing recognition result model without deleting history.

Each immutable attempt records:

- attempt ID;
- Item ID;
- provider;
- model;
- tier: baseline, escalation, frontier, manual;
- trigger;
- forced-by operator/system;
- prompt version;
- schema version;
- image profile;
- image IDs/hashes/count/bytes;
- response reference;
- exact title proposal or `UNKNOWN`;
- year/edition/distributor/barcode evidence;
- approved Tag ID suggestions;
- confidence;
- uncertainty;
- contradiction flags;
- input/output tokens;
- configured CAD cost;
- latency;
- accepted/rejected/superseded state;
- accepted timestamp and actor;
- relationship to prior attempt.

Never delete prior attempts.

## Recognition workspace

Add top-level:

```text
Recognition
```

Show:

- current jobs;
- queue;
- model ladder;
- attempts by Batch and Item;
- failed/blocked/unsupported;
- low-confidence;
- contradiction filters;
- estimated/actual usage and CAD cost;
- run unfinished;
- run selected;
- force rerun;
- escalate selected;
- pause/resume where safe;
- benchmark mode;
- comparison report.

## Review controls

For every Item, including already successful/approved Items:

- Run Recognition Again;
- choose provider;
- choose tested image-capable model;
- choose tier;
- choose image profile/subset;
- escalate;
- compare attempts;
- select attempt as current suggestion;
- accept selected attempt into working fields;
- clear current suggestion without deleting history.

Rules:

- later attempt does not overwrite approved working values automatically;
- accepting a new attempt is explicit;
- physical Item ID remains unchanged;
- successful results may be rerun;
- repeated click is idempotent and does not start duplicate active attempts.

## Router

### Stage 0 — deterministic preparation

- use recognition derivatives, not originals unless explicitly chosen;
- deduplicate by hash;
- front first;
- bounded additional spine/back/support;
- record selected images;
- preserve all originals.

### Stage 1 — baseline

- lowest-cost tested model;
- strict JSON schema;
- exact title evidence;
- allowed to return `UNKNOWN`;
- approved Tag IDs only;
- no slogans/taglines as titles.

### Stage 2 — escalation

Trigger when:

- title missing;
- `UNKNOWN`;
- confidence below measured threshold;
- schema invalid;
- front/spine/back contradiction;
- catalog contradiction;
- same-title/year ambiguity;
- unsupported media uncertainty;
- operator request.

Use more/better images only when useful.

### Stage 3 — frontier exception

Use only for measured hard cases. Keep cost visible and bounded.

### Stage 4 — operator

Manual resolution is authoritative.

## Duplicate import overrides

Default remains:

```text
Open existing durable Batch; do not duplicate inventory.
```

When fingerprint matches, offer:

1. Open Existing Batch;
2. Re-run Unfinished;
3. Re-run All;
4. Create Isolated Test Copy;
5. Cancel.

Re-run All:

- same Item IDs;
- new attempts;
- no duplicate inventory;
- preserves approved values until explicit replacement.

Test Copy:

- separate Batch ID;
- test provenance;
- cannot publish;
- cannot reserve;
- visibly quarantined;
- links to source fingerprint/original Batch;
- safe for model comparison.

## Benchmark

Create a benchmark workflow with owner-labelled truth.

Dataset classes:

- clear mainstream;
- sequels/remakes;
- damaged/low contrast;
- slogan-heavy;
- music/concert;
- TV/anime;
- unusual edition;
- unsupported media.

Measure:

- exact-title accuracy;
- false confidence;
- operator correction;
- escalation rate;
- manual rate;
- latency;
- token use;
- image bytes;
- CAD cost;
- catalog agreement;
- operator time.

Do not claim quality from unlabelled synthetic outputs.

## Cost model

Store configured model price table with effective date/version. Estimated cost must state that it is calculated from configured prices, not provider billing truth.

## Failure/restart

Test:

- process stops during attempt;
- network timeout;
- 429 with Retry-After;
- invalid response;
- model unavailable;
- provider key rejected;
- app restart;
- duplicate force-click;
- accepting older attempt after newer attempt;
- stale browser.

## Acceptance

- successful Item can be rerun;
- two models can be compared without changing approved value;
- no history loss;
- `UNKNOWN` works;
- obvious tapes usually stay baseline;
- difficult tapes route upward or manual;
- cost and latency are visible;
- duplicate test copy is quarantined;
- restart recovers state.
