# SnapIMS Release Notes

## 0.6.0 - Operator workstation and stabilization

### Added

- Native folder browse workflow and safe import errors.
- Recognition failure classification and recovery screen.
- Preview and recognition image derivatives.
- Keyboard-first Price -> Enter Review flow.
- Batch Editor with inline editing, filtering, confidence buckets, command palette, bulk operations, checkpoints, undo/redo, and session restoration.
- CSV upload, field-level difference preview, apply confirmation, difference report, and rollback.
- External review workflow.
- Field-level audit history, token recording, media bandwidth metrics, and stale-edit conflict detection.

### Fixed

- Legacy recognition-job schema compatibility.
- `started_at` NOT NULL failures.
- Final-item recognition-job upsert failures.
- AI suggestion/title precedence during approval.
- Silent recognition failure refresh.
- Unnecessary original-image browser/AI payload use.

## 0.5.1 - Verification hardening

Historical release candidate. Its reports and generation scripts are retained under `docs/history/v0.5.1/`.
