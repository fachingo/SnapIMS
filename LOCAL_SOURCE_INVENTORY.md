# SnapIMS v0.13.2 Local Source Inventory

## Release inputs found in the local sandbox

- `SnapIMS-v0.13.0-full-source.zip` — latest complete executable source archive found; used as the implementation base.
- `SnapIMS-v0.12.3-full-source(1).zip` — older baseline/upgrade source; used for benchmark and migration comparison.
- `SnapIMS_v0.13.0_Stress_QA_Bug_Report_2026-08-03.md` — authoritative prior findings.
- `SnapIMS_v0.13.0_Stress_QA_Issue_Register_2026-08-03.csv` — issue-by-issue comparison sheet.
- `SnapIMS_v0.13.0_Stress_QA_Evidence_2026-08-03.zip` — prior browser, concurrency, descriptor, and source evidence.
- `SnapIMS_v0.13.1_Full_Remediation_Prompt_With_QA_Report.md` — remediation requirements supplied in the current task.

No complete SnapIMS v0.13.1 source archive was present locally. v0.13.2 was therefore built from the latest complete source actually available, v0.13.0, while incorporating and superseding the v0.13.1 remediation requirements.

## Local implementation tree examined

The complete extracted application was searched and tested, including:

- Python application modules and migrations
- FastAPI routes, Jinja templates, CSS, and JavaScript
- Import, Recognition, Review, Batch Editor, CSV, Publish, Settings, Diagnostics, authentication, observability, and infrastructure tests
- installer, CLI, process manager, user service, deployment examples, and recovery scripts
- deterministic Import, catalog, and v0.12.3-upgrade fixtures
- editable and rendered operator documentation

The per-file release inventory is recorded in `PACKAGE_FILE_MANIFEST.sha256` and `MANIFEST_SHA256.json`.
