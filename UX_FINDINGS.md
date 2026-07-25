# SnapIMS 0.7.0 UX Findings

## Closed

- Empty Title is now an inline quick field; typing it and pressing Enter performs Approve & Next once.
- Price remains automatically selected when Title is already populated.
- The exception editor is reserved for genuine validation/conflict work.
- Ctrl/Cmd+Shift+P opens the command palette; Ctrl/Cmd+K is a documented browser-safe fallback.
- Batch Editor supports spreadsheet-style arrows, Enter-to-save-and-move, Shift range selection, Space row toggle, and Ctrl/Cmd+A visible-row selection.
- Ctrl/Cmd+1–9 invokes the first nine quick actions through normal preview safety.
- Quick actions can be reordered, persist locally, and explain their effect/checkpoint/rollback behaviour.
- Same-version CSV export/import now round-trips without a false “Missing Item ID” blocker.
- Missing Tkinter becomes a manual-path fallback rather than an Import dead end.
- Movie ambiguity is shown as an exception; operator selection is explicit and auditable.

## Deferred

- Full 5,000-row virtualized editor and all-image QR performance architecture.
- Multi-user application sessions, roles, CSRF and concurrency controls.
- VHS Edition intelligence, automatic pooling, collection analytics and provider artwork.
- Automatic storefront publication.
