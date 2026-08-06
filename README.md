# SnapIMS v0.15.0

SnapIMS is a local, photo-first inventory workstation for Canada VHS. Version 0.15.0 completes the Shopify publish workflow: validation, read-only simulation, durable draft creation, optional Shopify review, controlled live publication, direct-live override, product reconciliation, and batch/product lifecycle management.

## Daily workflow

1. Create one immediate child folder inside `~/SnapIMS-data/batches`.
2. Name the folder with the desired batch display name.
3. Place photographs in capture order and photograph `CVHS1:ITEM:NEXT` between tapes.
4. Open **Import**, Preview, correct grouping, and Commit.
5. Complete Recognition, Review, and Batch Editor.
6. Open **Publish** and confirm validation passes.
7. Run **Shopify simulation**. Simulation never writes to Shopify.
8. Select **Create Shopify Drafts**. Progress and returned Shopify IDs are durable.
9. Review drafts in the Shopify tab that SnapIMS opens, or select **Open Shopify Drafts**.
10. Type `SUBMIT` and select **Publish Drafts Live** when ready.

The optional fast-track path requires typing `SUBMIT LIVE` and still creates the draft state first before promoting products live.

## Install

```bash
unzip SnapIMS-v0.15.0-full-source.zip
cd SnapIMS-v0.15.0
chmod +x install_v0150.sh
./install_v0150.sh
export PATH="$HOME/.local/bin:$PATH"
snapims version
snapims up
```

## Core commands

```bash
snapims help
snapims status
snapims doctor
snapims shopify status
snapims shopify test
snapims shopify jobs
snapims logs
snapims restart
snapims down
```

## Safety and durability

- Operator data remains under `~/SnapIMS-data`; release source and data are separate.
- Source photographs are not renamed, recompressed, or deleted.
- Shopify jobs survive browser refresh and application restart.
- Completed items are skipped on resume to prevent duplicate drafts or duplicate publication.
- Draft-first is the default. Live publication requires a selected Shopify publication and an exact typed confirmation.
- Permanent Shopify deletion requires typing `DELETE` and cannot be restored.

See `OPERATOR_GUIDE.md`, `SHOPIFY_SETUP_GUIDE.md`, `TEST_RESULTS.md`, `BROWSER_VERIFICATION.md`, and `V1_PRODUCTION_ACCEPTANCE_GAPS.md`.
