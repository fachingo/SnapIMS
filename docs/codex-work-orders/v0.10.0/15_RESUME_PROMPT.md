# Codex Resume Prompt

Copy this into a new Codex session:

```text
Resume the SnapIMS v0.10.0 implementation.

Repository: ~/Projects/SnapIMS

Read:
- docs/codex-work-orders/v0.10.0/01_MASTER_CONTROLLER.md
- V010_IMPLEMENTATION_STATE.md
- the phase file identified by NEXT_PHASE
- any referenced acceptance contract

Before editing, run:
git status --short
git branch --show-current
git rev-parse HEAD
git log -3 --oneline

Confirm that HEAD matches the latest verified commit in the state file or explain the discrepancy. Run the focused tests for the last completed phase. Continue from NEXT_ACTION. Preserve all existing work. Do not repeat completed migrations or external writes. Update the state file and commit the next verified bounded milestone.
```
