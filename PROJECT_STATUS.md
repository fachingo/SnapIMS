# SnapIMS prototype status

Version: **0.3.0 working prototype**
Authoritative workflow: **Canada VHS Inventory System Version 2.0 — QR-Delimited Workflow**

## Complete and verified

- NEXT-only chronological parser; timestamp-gap grouping is absent
- Complete fixed command and Q1/A1–J10 location vocabulary
- Deterministic EXIF/subsecond/fallback sort
- Duplicate START/END, pre/post batch photos, consecutive/trailing NEXT, CONT, flags, shelf deferral, and unknown-code behavior
- Hash-preserved originals, GPS-free public copies, stable naming, collisions, duplicate imports, interruption/resume, and file/database recovery path
- JSON/CSV manifests, warnings, command audit copies, SQLite event schema, work CSV, validation, and audit export
- Immutable Item ID CSV round-trip independent of row order/title
- Streamlit operator workflow across all requested pages
- Provider-neutral recognition with functioning mock recognizer and explicit suggestion acceptance
- Shopify configuration, simulation, SKU dry-run, draft boundary, staged media, inventory activation, checkpoint/error state, and mocked full upload test
- Automated database backup before import, CSV import, and Shopify writes
- Linux Mint virtual-environment installer and desktop launcher

## Verification record

The release was checked with:

```text
pytest: 154 passed
ruff: All checks passed
mypy: Success, no issues found in 22 source files
SQLite integrity: ok; 0 foreign-key violations in end-to-end demo
Streamlit: dashboard AppTest passed and HTTP health smoke test performed
```

The test suite includes synthetic camera images/QR codes and a realistic decode check using the supplied QR-card PDF. It covers the parser, sorting fallbacks, image preservation, database transaction rollback, CSV identity behavior, recognition suggestions, Shopify simulation/mock upload, and Streamlit startup.

## Known limitations

- A real Pixel photo session and every physical printed card have not been camera-tested under production lighting. The supplied QR PDF is decoded in tests and the entire vocabulary is covered synthetically.
- HEIC/HEIF support is installed through `pillow-heif`, but a real Pixel HEIC metadata sample is still needed for device-specific confirmation.
- OpenAI and Gemini classes are deliberate provider stubs. They report configuration state but do not make live recognition calls. The mock provider works end to end; local OCR works when Tesseract and `pytesseract` are installed.
- Shopify GraphQL writes are implemented and tested against a deterministic fake transport, not a merchant store. Real credentials are required for the first draft-only sandbox validation. Publishing remains manual.
- The prototype is single-operator/local. Multi-user authentication, network hosting, role permissions, and concurrent operator conflict resolution are outside this phase.
- Media processing is synchronous. A background job queue is advisable before very large batches.

## Recommended next milestone

Run one controlled 20-tape Pixel pilot using the printed cards, review warning quality and QR detection rates, then connect a Shopify development store in draft-only mode. Preserve the resulting manifests, timing, failure notes, and operator corrections as acceptance fixtures before enabling a live recognition provider.

## Suggested commit sequence

1. Core protocol, deterministic ordering, interpreter, and manifests
2. SQLite schema, event history, CSV workflow, and validation
3. Image preservation, recovery, recognition, and Shopify boundaries
4. Streamlit operator interface, demo, documentation, and verification tests

The delivered repository may consolidate these into one local release commit; no secrets, production database, or inventory photos belong in Git.
