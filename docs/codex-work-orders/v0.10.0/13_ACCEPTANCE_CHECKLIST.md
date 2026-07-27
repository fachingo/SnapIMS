# SnapIMS v0.10.0 Acceptance Checklist

## Phase 0

- [ ] Current branch/commit recorded.
- [ ] Dirty work preserved.
- [ ] Inventory and catalog backups validated.
- [ ] Media/config manifest created.
- [ ] Baseline tests captured.
- [ ] Architecture contradictions registered.

## Stabilization

- [ ] CSRF protects all state changes.
- [ ] Login throttle/audit works.
- [ ] Session revocation works.
- [ ] Security headers verified.
- [ ] Degraded schema produces failed health.
- [ ] Doctor exits nonzero on required failure.
- [ ] Tunnel public-route failure is detected.
- [ ] Shopify idempotency key passed and persisted.
- [ ] Duplicate SKU ambiguity rejected.
- [ ] Update check/apply safe.
- [ ] Shell path handling safe.
- [ ] Alt+P works in Firefox.
- [ ] Alt+1–9 works in Firefox.
- [ ] Approved Tags workflow exists and is documented.
- [ ] Cold boot remains one-command.

## Observability

- [ ] `snapims log` alias works.
- [ ] CLI filters compose.
- [ ] Live Activity exists.
- [ ] Operation IDs correlate jobs.
- [ ] Redaction adversarial tests pass.
- [ ] Support bundle contains no secrets.
- [ ] Rotation/retention bounded.

## Settings

- [ ] Secret store permissions correct.
- [ ] Atomic save/backup/rollback works.
- [ ] Re-authentication required.
- [ ] OpenAI configuration works.
- [ ] Image-capable model probe works.
- [ ] Shopify wizard and location discovery work.
- [ ] Scope/capability failures are exact.
- [ ] Movie provider/Wikimedia settings work.
- [ ] Restart retains settings.
- [ ] No secret is returned or logged.

## Recognition

- [ ] Successful Item can be rerun.
- [ ] Attempt history immutable.
- [ ] Compare models without changing approved values.
- [ ] `UNKNOWN` supported.
- [ ] Baseline/escalation/frontier routing works.
- [ ] Approved Tag IDs only.
- [ ] Duplicate Batch rerun scopes work.
- [ ] Test copy is quarantined.
- [ ] Benchmark report works with labelled truth.
- [ ] Restart recovery works.

## Inventory

- [ ] Global title search.
- [ ] Item ID search.
- [ ] SKU search.
- [ ] Barcode search.
- [ ] Location search.
- [ ] Shopify ID search.
- [ ] Duplicate copies remain separate rows.
- [ ] Item detail includes history.
- [ ] Move requires reason.
- [ ] Stale edit rejected.
- [ ] Missing/quarantine state enforced.
- [ ] Results bounded/paginated.
- [ ] Scale evidence truthful.

## Movie database

- [ ] Provider-neutral interface.
- [ ] Wikidata candidate search.
- [ ] Wikimedia User-Agent/rate handling.
- [ ] Bounded Wikipedia enrichment.
- [ ] Local-first reuse.
- [ ] Ambiguity preserved.
- [ ] Unsupported media distinct.
- [ ] Inventory-driven bootstrap.
- [ ] Title-list bootstrap.
- [ ] Optional dump downloader guarded.
- [ ] Resume/checksum/storage gates.
- [ ] Streaming importer.
- [ ] Incremental support where practical.
- [ ] Every external field has provenance.
- [ ] Second copy causes no unnecessary request.

## Shopify and picking

- [ ] Draft simulation.
- [ ] Deliberate draft UI.
- [ ] One live draft remains owner-gated.
- [ ] Order polling idempotent.
- [ ] Optional webhooks HMAC/dedupe.
- [ ] Polling reconciles missed webhooks.
- [ ] Exact listing link maps to Item.
- [ ] Exclusive reservation.
- [ ] Cancellation release.
- [ ] Pick Queue shows exact shelf.
- [ ] Missing exception.
- [ ] Packed state.
- [ ] Fulfillment confirmation.
- [ ] Duplicate fulfillment protected.
- [ ] Restart persistence.

## Verification and release

- [ ] Full pytest.
- [ ] Ruff.
- [ ] Type check.
- [ ] Compileall.
- [ ] JS syntax.
- [ ] Build.
- [ ] Installed smoke.
- [ ] Pip check.
- [ ] DB integrity.
- [ ] Catalog integrity.
- [ ] Secret/archive scan.
- [ ] Native Firefox walkthrough.
- [ ] Cold boot.
- [ ] Operator Guide synchronized.
- [ ] Screenshots replaced.
- [ ] Guide walkthrough repeated.
- [ ] Every active document says 0.10.0.
- [ ] Branch pushed.
- [ ] 1.0 gate remains separate.
