# SnapIMS

SnapIMS is a locally runnable, photo-first inventory intake system for Canada VHS. It reads a camera roll as a chronological command stream, preserves every source file, groups product photographs only at `CVHS1:ITEM:NEXT` boundaries, and creates an auditable SQLite/CSV inventory workspace.

This repository is a working prototype based on **Canada VHS Inventory System Version 2.0 — QR-Delimited Workflow**. Timestamp-gap grouping is not implemented and must not be reintroduced. Capture time is used only to restore deterministic camera order.

## What works

- EXIF/subsecond ordering with deterministic filename and filesystem fallbacks
- Strict recognition of the existing `CVHS1` QR vocabulary, including all A1–J10 shelves and Q1
- NEXT-only state machine with duplicate, out-of-order, mid-item, CONT, and unknown-code safeguards
- SHA-256 original preservation, GPS-free processed JPEGs, collision-safe names, resume markers, and duplicate batch detection
- Required manifests, warnings, command audit copies, work CSV, and SQLite records
- CSV export/re-import strictly by immutable Item ID
- Five-page Streamlit workflow: **Home, Import, Review, Publish, Settings & diagnostics**
- Durable active-batch context, recognition progress/resume, and keyboard-first Review cursor
- Deterministic mock recognition, live optional OpenAI vision, optional local Tesseract OCR, and a configured-but-stubbed Gemini boundary
- Shopify draft-product boundary with SKU checks, staged media, inventory activation, checkpoints, dry-run default, and deliberate live confirmation
- Synthetic QR-delimited demo generation and automated end-to-end tests

## Linux Mint installation

SnapIMS supports Python 3.10 or newer. From the extracted project directory:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
chmod +x scripts/install_linux_mint.sh scripts/run_snapims.sh
./scripts/install_linux_mint.sh
```

The installer creates an isolated `.venv`, initializes `~/SnapIMS-data`, and adds **SnapIMS** to the Linux Mint application menu. Routine use after installation does not require a terminal.

If `python3 --version` is older than 3.10, install a supported Python release and run:

```bash
PYTHON_BIN=python3.11 ./scripts/install_linux_mint.sh
```

## Launch

Open **SnapIMS** from the Linux Mint application menu, or run the exact launch command:

```bash
./scripts/run_snapims.sh
```

Streamlit opens the local interface in the default browser. It does not expose the application to the public internet by default.

## First end-to-end test

Generate a realistic synthetic camera roll:

```bash
.venv/bin/snapims demo demo-data/camera-roll
```

Then launch SnapIMS, open **Import**, enter the absolute path to `demo-data/camera-roll`, choose **Dry-run parser preview**, and then **Preserve and import batch**. Continue through **Review** and **Publish**; see [DEMO.md](DEMO.md) for the complete five-page walkthrough.

The equivalent command-line smoke path is:

```bash
.venv/bin/snapims --data-dir demo-data/workspace preview demo-data/camera-roll
.venv/bin/snapims --data-dir demo-data/workspace import demo-data/camera-roll --batch-name DEMO
.venv/bin/snapims --data-dir demo-data/workspace integrity
```

## Data directory

The default root is `~/SnapIMS-data`; override it in `.env` or the Streamlit sidebar.

```text
data-root/
├── incoming/
├── originals/<batch-id>/
├── processed/<batch-id>/images/
├── processed/<batch-id>/commands/
├── processed/<batch-id>/thumbnails/
├── processed/<batch-id>/batch_manifest.json
├── processed/<batch-id>/image_manifest.csv
├── processed/<batch-id>/commands.csv
├── processed/<batch-id>/inventory_work.csv
├── processed/<batch-id>/warnings.txt
├── database/inventory.sqlite3
├── exports/
├── backups/
└── logs/snapims.log
```

Every source image—including deliberately excluded pre-START/post-END images—is retained byte-for-byte under `originals`. Command images are copied to the command audit directory and never become product images.

## Configuration and secrets

Copy `.env.example` to `.env` only when configuration is needed:

```bash
cp .env.example .env
```

Do not commit `.env`. AI keys and the Shopify token are read only from environment variables. SnapIMS runs without them. Shopify defaults to simulation and draft-only mode; a live draft requires valid credentials plus the exact in-app confirmation.

## Developer verification

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/mypy snapims --ignore-missing-imports
```

## Safe source release

Build a source archive only from Git-tracked artifacts:

```bash
.venv/bin/python -m snapims.release --root . --output dist/snapims-source.tar.gz
```

The command validates every member before creating the archive. It refuses environment files, credential-like content, databases, logs, caches, exports, backups, runtime inventory folders, and images outside the tracked synthetic `demo-data/camera-roll/` fixture set.

## Documentation

- [DEMO.md](DEMO.md) — synthetic batch and operator walkthrough
- [ARCHITECTURE.md](ARCHITECTURE.md) — component and safety design
- [DATABASE.md](DATABASE.md) — schema, migrations, events, backup, and integrity
- [PROJECT_STATUS.md](PROJECT_STATUS.md) — verified scope and honest limitations

The authoritative source documents and QR-card PDF are retained under `docs/reference/` for traceability.
