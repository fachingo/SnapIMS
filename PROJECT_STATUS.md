# SnapIMS prototype status

Version: **0.3.0 working prototype**
Authoritative workflow: **Canada VHS Inventory System Version 2.0 — QR-Delimited Workflow**

## Verified checkpoint

The exact functional checkpoint entering release/documentation verification is commit `21b7a09b20fcbe0d17196e006b2d6d9ff433a355` (`Resume recognition jobs after process restart`). The Phase 9 documentation and release-safety tree was then checked on 2026-07-17 with:

```text
pytest -q: 249 passed
ruff check .: All checks passed
mypy snapims --ignore-missing-imports: Success, no issues found in 31 source files
git diff --check: passed
wheel smoke: snapims-0.3.0-py3-none-any.whl built successfully
```

These values are copied from the actual local gate run, not projected release claims.

## Complete and verified

- NEXT-only parsing, deterministic ordering, approved QR vocabulary, and quarantined unknown `CVHS1` payloads
- Hash-preserved originals, GPS-free processed copies, stable Item IDs/names, duplicate detection, and import recovery
- Atomic migration runner with pre-migration backup; current schema includes durable recognition jobs and Item-ID Review cursors
- Five operator destinations: Home, Import, Review, Publish, Settings & diagnostics
- Active-batch workflow, keyboard-first Review, automatic validation, CSV-by-Item-ID round trip, and batch Publish queues
- Deterministic mock recognition; optional live OpenAI vision; optional local Tesseract OCR; stubbed Gemini boundary
- Recognition suggestions remain non-authoritative until acceptance and never change physical REVIEW
- Shopify simulation by default, read-only SKU checking, deliberate draft-only writes, and per-item retry checkpoints
- Tracked-files source release guard plus wheel/archive smoke coverage

## Known limitations and manual verification

- A controlled physical Pixel/printed-card pilot is still required for lighting, glare, focus, QR decode rate, and operator timing.
- HEIC/HEIF support exists, but a real Pixel HEIC metadata sample still needs device-specific confirmation.
- The OpenAI adapter is implemented but was not called with a production key during this verification. Gemini remains intentionally stubbed. Local OCR requires system Tesseract plus `pytesseract`.
- Shopify writes were verified with deterministic fake transports, not a merchant store. The first real integration must use a development store and verify drafts only; publishing remains manual.
- SnapIMS remains a single-operator local workstation. Multi-user/network operation is outside this release.
- Recognition runs synchronously but commits durable per-item progress and resumes safely after restart.

## Safe release command

```bash
.venv/bin/python -m snapims.release --root . --output dist/snapims-source.tar.gz
```

Only validated Git-tracked source/fixture artifacts are eligible. Real credentials, databases, logs, caches, exports, backups, operator workspaces, and non-synthetic inventory images do not belong in Git or a release archive.
