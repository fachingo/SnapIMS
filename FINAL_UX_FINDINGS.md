# SnapIMS 0.5.0 Final UX Findings

## Outcome

The reconstructed browser workflow matches or improves the nine accepted operator findings.

| Finding | Status in 0.5.0 |
|---|---|
| Recognized cards remain Untitled | Fixed: unfinished workstation shows the latest suggestion. |
| Done items show stale AI suggestions | Fixed: saved metadata is primary; AI is collapsed history. |
| Done items cannot be corrected | Fixed: same-ID exception editor, validation, Cancel, and restart durability. |
| Edit opens outside viewport | Fixed: active workstation remains first and visible. |
| Preview/import identifiers conflict | Fixed: Preview is explicitly non-durable; import shows one ID. |
| Recognition action/status unclear | Fixed: Ready, Running, Paused, Complete, Failure, and Review complete are distinct. |
| Queue numbering resets | Fixed: physical sequence is always primary. |
| Routine import requires a path | Fixed: configured and recent folders are normal; manual path is Advanced. |
| Review requires excessive scrolling | Fixed at 1440 x 1000: photo, identity, quick edits, and primary action fit together. |

## v0.5 improvements beyond the lost build

- CSV adds Release year and Discount percent.
- Partial CSV files preserve absent fields.
- Publish simulation exposes a field-level payload preview.
- HTTP application boundary reduces UI coupling.
- Optimistic record revision detects stale edits.
- Shopify stage checkpoints are consulted during retry.

## Remaining limitations

- Real AI quality was not measured.
- Live Shopify draft creation was not performed.
- Native TCP browser navigation was blocked by the execution environment; rendered-control verification used an in-process application transport.
- Multi-operator locking and authentication remain post-1.0 work.
