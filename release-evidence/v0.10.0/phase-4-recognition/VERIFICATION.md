# Phase 4 Recognition Implementation Verification

Date: 2026-07-27  
Branch: `feature/v0.10.0-final-preproduction`  
Starting commit: `73243f5`  
Application version: `0.10.0` (intentionally unchanged)

## Implemented contract

- Inventory schema 12 preserves legacy `recognition_results` history while
  making attempt payload rows append-only with SQLite update/delete guards.
- Attempt decisions and the current-suggestion pointer are stored separately;
  decision events are append-only and retain actor/time/prior-attempt evidence.
- Every attempt carries its provider/model/tier/trigger/forced actor,
  prompt/schema/image profile, selected photo IDs/hashes/capture sources,
  evidence, contradictions, token use, configured CAD estimate/version,
  latency, request link, and prior-attempt relationship.
- Durable per-Item requests use browser-supplied idempotency IDs, suppress
  duplicate clicks, pause on restart, and can resume without deleting history.
- Baseline, escalation, frontier, and manual roles use Phase 3 configuration.
  Operator-selected OpenAI models must have passed the image/strict-schema
  capability probe. Frontier use is explicit unless a later measured hard-case
  policy is owner-approved.
- Routing considers missing/`UNKNOWN` title, low confidence, invalid schema,
  image contradiction flags, linked-catalog contradiction, catalog ambiguity,
  unsupported-media uncertainty, and operator request.
- The Recognition workspace exposes jobs, scopes, model ladder, filters,
  attempt comparison/selection/explicit acceptance, pause/resume, latency,
  tokens, image profile/bytes, configured cost, and owner-labelled benchmark
  metrics. Unlabelled synthetic outputs are not reported as quality evidence.
- Duplicate import offers Open Existing, Rerun Unfinished, Rerun All,
  Isolated Test Copy, and Cancel. Test copies have separate Batch/Item IDs,
  source links, `TEST` provenance, and permanent database/service quarantine
  from ready-for-sale, reservation, and Shopify state.
- Capture provenance supports `DESKTOP_IMPORT_QR`,
  `DESKTOP_IMPORT_MANUAL`, `ANDROID_BUTTON`, `ANDROID_QR`,
  `ANDROID_OFFLINE_SYNC`, `MANUAL`, and `TEST`; no Android client was added.

## Automated verification

- `.venv/bin/python -m pytest -q`
  - PASS; 233 tests collected, one expected skip.
- `.venv/bin/python -m pytest -q tests/test_v010_phase4_recognition.py`
  - PASS; immutable evidence, successful Item rerun, duplicate click,
    explicit older-attempt acceptance, `UNKNOWN`, configured CAD estimate,
    capture provenance, test-copy quarantine, restart pause, workspace, and
    duplicate choices.
- `.venv/bin/ruff check .`
  - PASS.
- `.venv/bin/mypy snapims --ignore-missing-imports`
  - PASS; 40 source files.
- `node --check snapims/web/static/app.js`
  - PASS.
- `git diff --check`
  - PASS.
- `.venv/bin/python -m build`
  - PASS; built `snapims-0.10.0.tar.gz` and
    `snapims-0.10.0-py3-none-any.whl`.
- `.venv/bin/python -m pip check`
  - PASS.

## Disposable production-data migration

The production inventory database was copied to
`/tmp/snapims-phase4-migration-fi152R`; production was not mutated.

- schema: 11 → 12;
- automatic pre-schema-12 backup: present;
- integrity: `ok`;
- foreign-key violations: 0;
- schema manifest: PASS;
- preserved: 4 Batches, 32 Items, 13 prior recognition results, 173 Photos;
- migrated photo capture source: 173 `DESKTOP_IMPORT_QR`.

## Remaining Phase 4 gates

- Native Firefox operator acceptance.
- Real-process restart/interruption acceptance.
- Production schema-12 migration, restart, cold-start, status, doctor,
  integrity/foreign-key/manifest verification.
- Final Phase 4 evidence/state commit and push.

No live OpenAI recognition call, Shopify write, central catalog contribution,
or Android application work was performed.
