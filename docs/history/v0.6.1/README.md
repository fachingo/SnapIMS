# SnapIMS 0.6.1

SnapIMS is a photo-first, exception-driven inventory workstation for Canada VHS. It converts QR-delimited camera rolls into durable local inventory, human review, CSV workflows and controlled Shopify draft preparation.

## Routine workflow

1. Photograph START, location, tape photos, NEXT between tapes, and END.
2. Preview counts and warnings.
3. Preserve and import one durable batch.
4. Identify with a configured live provider or continue manually.
5. Confirm title, optionally change Price/Discount, and use Approve & Next.
6. Resolve exceptions in Batch Editor or through a staged CSV difference preview.
7. Simulate Shopify drafts before any deliberate live draft test.

## What changed in 0.6.1

- Test/mock recognition is quarantined from production mode.
- CSV, bulk edit and external review are atomic.
- Interrupted import finalization is journaled and recoverable.
- Checkpoint restore is audited.
- Schema 7 verifies real SQLite structure.
- Money uses exact cents/Decimal rules.
- AI suggestions, saved values, reviewed values and Shopify state are separate.
- BLOCKED provider recovery and manual review are explicit.
- Metrics and Diagnostics are based on measured facts.
- Browser verification covers the 20-item operator path and restart durability.

## Install

```bash
git clone https://github.com/fachingo/SnapIMS.git
cd SnapIMS
git switch fix/v0.6.1-mega-stabilization
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Run

```bash
snapims --data-dir ~/SnapIMS-data serve
```

SnapIMS binds to `127.0.0.1:8767` by default. It does not auto-run at boot unless you deliberately create and enable a service.

## Quality gate

```bash
ruff check .
mypy snapims
pytest -q
python -m compileall -q snapims tests
python -m build
pip check
git diff --check
```

## Safety boundaries

- Keep production data and `.env` outside Git.
- Original images are never overwritten.
- Item ID and Batch ID are immutable.
- CSV updates by Item ID only.
- Live Shopify mode creates drafts only and requires deliberate confirmation.
- SnapIMS remains single-operator and localhost-first.
- Mock/test providers require `SNAPIMS_ENABLE_TEST_PROVIDERS=true` and are not production truth.

## 1.0 gate

Do not label SnapIMS 1.0.0 until the real 20-tape Pixel pilot, live AI, one live Shopify draft, physical CSV verification, restart durability, independent Operator Guide walkthrough, browser verification and blocker review all pass.
