# SnapIMS 0.6.0 Production Readiness

Verdict: **not production 1.0; ready for controlled real-pilot testing**.

## Closed blockers in 0.6.0

- Empty folder submission no longer exposes raw FastAPI 422 JSON.
- `recognition_jobs.started_at` is defaulted safely and cannot be overwritten by `None`.
- Recognition failure now shows the cause and recovery actions.
- AI-title approval follows displayed-value precedence.
- Legacy recognition-job schema remains compatible.
- Browser and AI payloads use persistent derivatives rather than original phone files.
- CSV replacement is staged, diffed, validated, confirmed, and checkpointed.
- Bulk edits create rollback checkpoints and record change history.

## Remaining 1.0 acceptance work

1. Run a real 20-tape Pixel batch.
2. Run live AI with a real API key and inspect token use/results.
3. Review and correct the batch using both Review and Batch Editor.
4. Reconcile downloaded CSV against physical tapes.
5. Create one live Shopify draft and verify product, variant, inventory, media, SKU, and price.
6. Restart during/after recognition and confirm durability.
7. Follow the Operator Guide step by step with the final UI.
8. Resolve every pilot blocker before labelling 1.0.0.
