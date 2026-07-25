# SnapIMS 0.7.0

SnapIMS is a photo-first, exception-driven inventory workstation for Canada VHS. Version 0.7.0 adds the local-first Movie Catalog, true spreadsheet-style Batch Editor keyboard operation, one-Enter manual-title Review, resilient CSV round trips, and migration/folder-picker repairs while preserving the v0.6.1 integrity foundation.

## Routine workflow

1. Photograph START, location, tape photos, NEXT between tapes, and END.
2. Preview counts and warnings; then preserve one durable batch.
3. Identify with a configured live provider or continue manually.
4. Review the photograph. Title is focused only when empty; otherwise Price is selected. Press Enter once to approve and open the next unfinished tape.
5. Use Batch Editor for keyboard-driven corrections, atomic bulk actions, checkpoints, and CSV staging.
6. Let the background catalog search the local database first and bounded English Wikipedia only on a genuine local miss.
7. Simulate Shopify drafts before any deliberate live draft test.

## 0.7.0 highlights

- **Local Movie Catalog:** separate rebuildable `movie_catalog.sqlite3`, local-first matching, bounded Wikipedia retrieval, source provenance, ambiguity resolution, restart-safe jobs, CSV/Shopify enrichment, diagnostics, backup and restore.
- **Review:** inline Title/Price/Discount quick fields; Title receives focus only when required; one Enter submits the valid record exactly once.
- **Batch Editor:** arrow-key grid navigation, Enter-to-save-and-move, Shift range selection, Ctrl/Cmd+A visible-row selection, Ctrl/Cmd+1–9 quick actions, persistent action order, and concise action descriptions.
- **CSV:** unchanged SnapIMS exports round-trip successfully; BOM, CRLF/LF, comma/semicolon/tab delimiters, harmless header variation, and `item_id` aliases are handled without weakening immutable-ID safety.
- **Import:** missing Tkinter becomes a clear manual-path fallback; `python3-tk` is an optional Linux dependency for the native folder picker.
- **Migration:** schema 8 automatically removes the obsolete `recognition_job_items` table before rebuilding recognition jobs, preventing the v0.6.1 foreign-key mismatch on existing databases.

## Install and run

```bash
cd ~/Projects/SnapIMS-v0.7.0
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
snapims --data-dir ~/SnapIMS-data serve
```

Open `http://127.0.0.1:8767`.

For the native Linux folder picker:

```bash
sudo apt install python3-tk
```

SnapIMS binds to localhost by default. Do not expose the application directly with router port forwarding.

## Release status

Version 0.7.0 is a **minor feature release**, not production 1.0.0. The real 20-tape Pixel pilot, live AI test, one live Shopify draft, physical CSV reconciliation, restart durability on the production machine, final Operator Guide walkthrough, browser verification, and blocker review remain mandatory before 1.0.0.
