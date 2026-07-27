# SnapIMS v0.10.0 Codex Work-Order Package

## Purpose

This package converts the integrated SnapIMS audit and pre-1.0 roadmap into an executable, resumable Codex implementation program.

It is intentionally split into bounded phase files. Codex should read the files from disk instead of receiving one enormous repeated chat prompt.

## Recommended model

Use:

- Model: `gpt-5.6-sol`
- Reasoning effort: **High**
- Prevent sleep while running: enabled

Reserve Ultra for a bounded difficult review or failure investigation, not the entire implementation.

## Install this package into the repository

From a terminal:

```bash
cd ~/Projects/SnapIMS
mkdir -p docs/codex-work-orders/v0.10.0
```

Extract this ZIP so the package contents are located at:

```text
~/Projects/SnapIMS/docs/codex-work-orders/v0.10.0/
```

The package should then contain `01_MASTER_CONTROLLER.md` and all numbered phase files.

## Start Codex

```bash
cd ~/Projects/SnapIMS
source .venv/bin/activate
codex -m gpt-5.6-sol
```

Select **High** reasoning effort.

Paste this compact starter prompt:

```text
You are implementing the complete SnapIMS v0.10.0 final pre-1.0 work order.

Read and obey:
docs/codex-work-orders/v0.10.0/01_MASTER_CONTROLLER.md

Then read every numbered phase file and supporting contract referenced by the controller. Inspect the live repository before editing. Create or resume V010_IMPLEMENTATION_STATE.md. Execute the phases in dependency order, committing verified bounded milestones. Continue autonomously until an owner-approval gate, an unrecoverable external block, or the end of the work order. Do not merely summarize the files. Begin now.
```

## Resume a later Codex session

Paste:

```text
Resume the SnapIMS v0.10.0 work order.

Read:
1. docs/codex-work-orders/v0.10.0/01_MASTER_CONTROLLER.md
2. V010_IMPLEMENTATION_STATE.md
3. the phase file named as NEXT_PHASE in the state file

Verify the current branch, HEAD, working tree, tests, schemas and latest phase commit. Continue from the first incomplete acceptance criterion. Do not repeat completed work and do not discard preserved changes.
```

## Owner approval gates

Codex should stop and ask only when required for:

- sudo authentication that cannot be supplied by the environment;
- a real Shopify write;
- a full Wikidata dump download/import;
- secret entry;
- an irreversible external action;
- a destructive production-data action without a validated backup;
- a product decision explicitly marked `OWNER DECISION REQUIRED`.

Ordinary code edits, tests, migrations against disposable copies, browser automation, documentation generation and local fixture creation do not require repeated approval.

## Critical release rule

The final implemented version for this package is **0.10.0**, a minor release.

Do not label SnapIMS `1.0.0`. The physical/live production acceptance gates remain separate and mandatory.
