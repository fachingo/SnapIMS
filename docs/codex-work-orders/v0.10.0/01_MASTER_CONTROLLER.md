# Master Controller — SnapIMS v0.10.0

## Assignment

Implement the complete final pre-1.0 feature release for SnapIMS.

Repository:

```text
fachingo/SnapIMS
```

Expected local path:

```text
~/Projects/SnapIMS
```

Known accepted infrastructure baseline:

- historical audited branch: `feature/v0.9-infrastructure`;
- historical audited commit: `bda7093d8ca9b776b2e881ce38a09f10b222f56f`;
- accepted infrastructure version: `0.9.0`;
- target implementation version: `0.10.0`;
- supported host: Linux Mint;
- local SnapIMS: `http://127.0.0.1:8767`;
- public SnapIMS: `https://ims.canadavhs.ca`;
- official Guacamole: `https://desktop.ims.canadavhs.ca/guacamole/`;
- compatibility Guacamole hostname may remain `https://remote.canadavhs.ca/guacamole/`;
- normal data root: `~/SnapIMS-data`.

Do not assume the repository still matches the historical commit. Inspect current reality first.

## Authority order

When instructions conflict, use this order:

1. current production data and immutable physical identity;
2. current verified browser behaviour;
3. this work-order package;
4. integrated v0.10.0 roadmap;
5. integrated v0.9.0 audit;
6. older feature documents and historical reports.

Never preserve a false old claim merely because it is documented.

## Product contract

SnapIMS is an exception-handling inventory workstation, not a generic data-entry application.

Routine Review remains:

```text
Photograph
→ confirm or correct Title
→ optionally adjust Price
→ confirm approved Tags
→ optionally adjust Discount
→ Approve & Next
```

Routine Review must remain fast. External catalog calls, expensive recognition and background enrichment must not delay `Approve & Next` unless the operator explicitly requests the operation.

## Permanent identity rules

Never change or regenerate an existing:

- Batch ID;
- Item ID;
- image-to-Item relationship;
- physical sequence;
- location history;
- Review history;
- recognition attempt;
- Movie ID;
- Edition ID;
- Shopify product/variant/inventory link;
- order/reservation/pick history.

Titles, external IDs, list positions and provider output are not physical identity.

## Repository and Git discipline

At startup record:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git log -5 --oneline --decorate
git remote -v
```

If the tree is dirty:

1. inspect every change;
2. preserve it in a timestamped patch or deliberate preservation commit;
3. do not overwrite it;
4. record the preservation action in `V010_IMPLEMENTATION_STATE.md`.

Create or use:

```text
feature/v0.10.0-final-preproduction
```

Do not:

- reset hard;
- force-push;
- rewrite shared history;
- delete branches;
- discard untracked files;
- commit `.env`;
- commit API keys or credentials;
- commit production SQLite files;
- commit production photographs or logs;
- perform a real Shopify write without explicit owner approval.

Use bounded phase commits. Suggested sequence:

1. `chore: preserve and baseline v0.10.0 work`
2. `fix: stabilize security health and external write recovery`
3. `feat: add structured operational observability`
4. `feat: add secure application settings`
5. `feat: add recognition control and staged routing`
6. `feat: add global inventory retrieval`
7. `feat: complete local-first movie catalog acquisition`
8. `feat: add Shopify orders reservations and picking`
9. `test: complete v0.10.0 verification`
10. `docs: synchronize SnapIMS v0.10.0 release`

Commit messages may be adjusted to match actual work.

## State file

Create at repository root:

```text
V010_IMPLEMENTATION_STATE.md
```

Start from `12_IMPLEMENTATION_STATE_TEMPLATE.md`.

Update it after every significant checkpoint with:

- branch and HEAD;
- current phase;
- completed criteria;
- migrations;
- tests;
- browser evidence;
- backups;
- owner approvals;
- known failures;
- exact next action.

Do not treat the state file as a substitute for Git commits.

## Phase execution

Read and execute in order:

1. `02_PHASE_0_BASELINE_AND_PRESERVATION.md`
2. `03_PHASE_1_STABILIZATION_SECURITY.md`
3. `04_PHASE_2_OBSERVABILITY.md`
4. `05_PHASE_3_SECURE_SETTINGS.md`
5. `06_PHASE_4_RECOGNITION_ROUTING.md`
6. `07_PHASE_5_INVENTORY_SEARCH.md`
7. `08_PHASE_6_MOVIE_DATABASE.md`
8. `09_PHASE_7_SHOPIFY_ORDERS_PICKING.md`
9. `10_PHASE_8_SCALE_ACCEPTANCE.md`
10. `11_PHASE_9_DOCUMENTATION_RELEASE.md`

Each phase has its own exit gate. Do not merge later schema/workflows ahead of an unmet required predecessor.

## Test discipline

For every defect or workflow, test where applicable:

- success;
- invalid input;
- duplicate invocation;
- timeout;
- rate limit;
- network failure;
- process interruption;
- application restart;
- stale browser revision;
- partial external success;
- retry;
- rollback/reconciliation;
- secret redaction;
- native Firefox behaviour;
- documentation match.

Use disposable databases and mocked transports for destructive/failure tests.

## Standard quality gate

Use repository equivalents, but normally run:

```bash
python -m pytest -q
python -m ruff check .
python -m mypy snapims --ignore-missing-imports
python -m compileall -q snapims tests scripts
node --check snapims/web/static/app.js
python -m build --no-isolation
python -m pip check
git diff --check
```

Also verify:

- inventory `PRAGMA integrity_check`;
- inventory `PRAGMA foreign_key_check`;
- catalog integrity and foreign keys;
- schema manifest;
- FTS/index health;
- release archive secret scan;
- no database/media/cache inclusion.

A missing optional local tool may be reported, but do not falsely record PASS.

## External-source rule

Technical implementations must be verified against current official documentation at implementation time.

Primary references:

- Shopify official developer documentation;
- Wikidata and Wikimedia official documentation;
- OpenAI official documentation;
- Cloudflare official documentation.

Do not rely on an old copied API example when the current provider contract differs.

## Completion rule

The assignment is complete only when:

- every implementable phase exit gate passes;
- owner-blocked live actions are clearly isolated and documented;
- version is synchronized to 0.10.0;
- browser UI and Operator Guide match;
- release evidence exists;
- the final report uses `14_FINAL_REPORT_TEMPLATE.md`;
- no known production blocker is hidden.

The assignment may end with remaining **1.0 acceptance gates**. Those gates are not defects in the work order if they require owner-controlled physical tapes, credentials or a deliberately authorized live Shopify draft.
