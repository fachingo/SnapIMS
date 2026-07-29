# SnapIMS v0.10.0 Pre-work Baseline

Captured on 2026-07-26 before application source changes.

## Repository

- Starting branch: `feature/v0.9-infrastructure`
- Starting commit: `bda7093d8ca9b776b2e881ce38a09f10b222f56f`
- Implementation branch: `feature/v0.10.0-final-preproduction`
- Original dirty state: only the owner-provided, untracked `docs/codex-work-orders/` package
- Preservation: external work-order copy plus Git bundle and patch/status metadata
- Work-order integrity: every present file matches `SHA256SUMS`; the two PDF duplicates and `install_into_repo.sh` listed by the package manifest were not supplied

## Runtime and configuration

- Source/package version: 0.10.0
- Installed distribution metadata: 0.7.0
- Host/port: `127.0.0.1:8767`
- Data root: `/home/isaiah/SnapIMS-data`
- Authentication: configured
- OpenAI key: configured; value not inspected or recorded
- Configured OpenAI model: `gpt-5-nano`
- Shopify store/location: configured; Admin token absent; draft-only enabled; API version 2026-07
- Inventory: 4 Batches, 32 Items, 173 photos, 13 recognition attempts
- Catalog: zero Movies, nine lookup jobs

## Preservation

External backup:

`/home/isaiah/SnapIMS-backups/v0.10.0-prework-20260726-190242`

Both SQLite online backups pass integrity and foreign-key checks and were opened from disposable restore-probe copies. The media tree was not duplicated; a SHA-256 manifest covers 1,306 files (433,149,821 bytes). Secrets and configurations copied into the backup are owner-restricted.

One root-only file could not be read without interactive sudo:

`/etc/guacamole/snapims-admin.env`

This omission is explicit in `BACKUP_MANIFEST.json` and `V010_IMPLEMENTATION_STATE.md`.

## Quality gate

| Gate | Baseline |
|---|---|
| pytest | PASS, one expected skip |
| Ruff | PASS |
| mypy | FAIL, 19 existing errors |
| compileall | PASS |
| JavaScript syntax | PASS |
| build | FAIL, setuptools/wheel missing from venv |
| installed-wheel smoke | BLOCKED by build |
| pip check | PASS |
| git diff check | PASS |
| inventory integrity/FK/schema manifest | PASS |
| catalog integrity/FK/structure/FTS | PASS |
| high-confidence secret scan | PASS within recorded scope |

Each captured command has a sibling `.exit` file. Missing optional or broken local tooling is recorded as failure, not PASS.

## Service and endpoint truth

The current `snapims status` and `snapims doctor` report all checks as PASS, but source inspection confirms their semantics are too broad and their failure exit behavior is incomplete. These outputs are baseline facts, not proof that Phase 1 requirements already pass.

Read-only endpoint evidence:

- local `/health`: HTTP 200 with schema 8 reported OK;
- public SnapIMS: authentication redirect and SnapIMS login marker observed;
- `desktop.ims.canadavhs.ca`: DNS resolution failed;
- `remote.canadavhs.ca/guacamole/`: HTTP 200 with Guacamole login markers.

## Evidence limitations

- No credentials were entered.
- No live OpenAI call was made.
- No Shopify write was made.
- No production database migration was run.
- Native Firefox was not yet used for the v0.10.0 workflow.
- Four historical binary artifacts larger than 5 MB were listed but not content-scanned by the lightweight baseline secret scanner.
