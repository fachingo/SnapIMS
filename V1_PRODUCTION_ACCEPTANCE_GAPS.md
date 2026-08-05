# SnapIMS Pre-v1.0 Production Acceptance Gaps

v0.13.2 is a patch release, not v1.0.0. The following must be completed before the project can be labeled 1.0.0.

## Required production acceptance

1. **Real 20-tape Pixel pilot** on the actual operator workstation, including NEXT placement, Preview correction, Commit, Recognition, Review, Batch Editor, CSV, and Publish handoff.
2. **Live AI test** with the intended provider and real credentials, including timeout, retry, malformed output, cost/token logging, rate-limit recovery, and restart durability.
3. **Live Shopify draft creation** with a real test product, image media, inventory activation, retry/reconciliation, and proof that the product remains draft.
4. **CSV verification** using a real owner batch: export, edit, reorder, import, validation failure, all-or-nothing rollback, and row-count reconciliation.
5. **Restart durability** on the target machine during scan, after Preview, during Recognition, during Review edits, and around Publish checkpoints.
6. **Operator Guide completion and walkthrough** by following every step against the final direct browser UI and replacing any mismatched screenshot or control name.
7. **Direct browser verification** in native Firefox and Chromium on the owner machine, desktop and mobile widths, with console/network evidence.
8. **No known production blockers** after the pilot and all live integrations.

## Additional release-blocking engineering checks

- Run an eight-hour or equivalent repeated-workflow soak and confirm descriptor, memory, WAL, log, and temporary-file stability.
- Perform the real in-place upgrade from the owner’s active installation and verify that `snapims up`, the process, Home, schema, and service all resolve to v0.13.2 or the later release.
- Complete a backup, restore, and rollback drill using copied operator data.
- Validate authentication, session revocation, CSRF, secret-file permissions, Cloudflare exposure, Guacamole access, and remote-workstation boundaries in the real deployment.
- Test real HEIC/HEIF input if it remains an advertised format.
- Confirm source-photo immutability with before/after hashes and metadata on a real Pixel folder.
- Confirm 5,000-item Batch Editor paging, search, selection, Fill Down, and bulk edits on the 8 GB target machine.
- Reconcile the performance acceptance methodology: this sandbox measured 68.44% cold-preview improvement over its v0.12.3 parser baseline, below the written 80% relative gate despite passing all absolute targets. Meet the gate on the target hardware or formally revise the acceptance criterion with documented approval.
- Verify live API quotas, permission scopes, credential rotation, failure messages, and support procedures.
- Complete a production-readiness review with zero unresolved Critical/High defects.
