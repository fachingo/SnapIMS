# SnapIMS v0.10.0 Architecture Reconciliation

## Evidence basis

This report reconciles the live repository at commit `bda7093d8ca9b776b2e881ce38a09f10b222f56f`, the production schema and service probes, the integrated v0.9.0 audit, and the v0.10.0 roadmap. No implementation claim below is based only on an older report.

Status meanings:

- **Verified** — source plus a relevant baseline test/live read-only check.
- **Implemented, unverified** — present in source but not exercised at the required final acceptance level.
- **Partial** — useful foundation exists but the v0.10.0 contract is incomplete.
- **Contradicted** — current source or browser-facing text disproves the old claim.
- **Absent** — no implementation found.
- **Deferred** — explicitly outside the v0.10.0 minimum.

## Foundation and physical identity

| Capability | Status | Current reality |
|---|---|---|
| Immutable Batch/Item identity | Verified | Primary keys, unique source fingerprint/SKU/sequence, restrictive foreign keys, and history tables exist. Production has 4 Batches and 32 Items. |
| Image-to-Item relationship | Verified | `photos.item_id` and media paths/hashes are durable; production integrity/FK checks pass. |
| Duplicate import prevention | Implemented, unverified | Source fingerprint opens existing durable Batch; no v0.10.0 Firefox rerun yet. |
| Import interruption recovery | Implemented, unverified | `import_journal` and reconciliation exist. |
| Review and Approve & Next | Implemented, unverified | Compact workflow exists; final Tags insertion and browser proof remain. |
| Optimistic revision/history | Verified | `record_revision`, change log, checkpoints, and stale-write handling exist and baseline pytest passes. |
| CSV stage/apply/cancel/rollback | Implemented, unverified | Staging, diff, checkpoint, apply, cancel, and reports exist. |

## Stabilization and security

| Capability | Status | Current reality |
|---|---|---|
| CSRF protection | Absent | Cookie-authenticated POST/JSON routes have no token or common Origin/Host gate. |
| Login throttling/backoff | Absent | Password verification exists; bounded failure tracking does not. |
| Auth audit/session revocation | Absent | Timed signed cookie exists without generation/version or revocation state. |
| Security headers | Absent | No common CSP/nosniff/referrer/permissions/frame/no-store middleware. |
| Health truth | Contradicted | `/health` returns a dict/HTTP 200; manager treats any 200 as healthy. |
| Doctor nonzero failure | Contradicted | Checks are printed but `doctor` does not aggregate failures into a nonzero exit. |
| Tunnel connector/public truth | Partial | PID/config checks exist; no public marker/connector evidence in status. |
| Guacamole marker health | Contradicted | Fallback accepts generic HTML when URL contains `/guacamole`. |
| Managed process ownership | Partial | PID files scope common paths, but PID identity/command is not verified before signal. |
| Safe CLI update | Absent | Current `update` performs direct `git pull` and restart. |
| Safe CLI shell | Contradicted | Project path is interpolated into a shell command string. |

## Shortcut and Tags truth

| Capability | Status | Current reality |
|---|---|---|
| `Alt+P` command palette | Contradicted | UI advertises `Ctrl+Shift+P` and `Ctrl+K`. |
| `Alt+1`–`Alt+9` quick actions | Contradicted | UI advertises `Ctrl+1`–`Ctrl+9`. |
| First-class controlled Tags | Absent | Items have a free-form `tags` string and bulk append action; no immutable taxonomy or many-to-many approved Tag IDs. |
| Tags between Price and Discount | Absent | Quick Review does not implement the controlled pill/autocomplete contract. |
| AI approved Tag IDs only | Absent | Recognition schema has no approved Tag-ID output. |

## Observability

| Capability | Status | Current reality |
|---|---|---|
| Durable operational events | Partial | Inventory/catalog/job/history tables exist, but no unified event model/correlation contract. |
| Shared redaction service | Absent | No common recursive redactor for logs, exceptions, bundles, and CLI. |
| `snapims log` alias | Absent | Only plural `logs` exists. |
| Filtered/JSON/export/follow CLI | Contradicted | Current command is an unconditional `tail -f` of one app log. |
| Diagnostics Live Activity | Absent | Diagnostics shows snapshots, not bounded durable activity with filters. |
| Support bundle | Absent | No safe bundled diagnostic export. |
| Bounded log rotation/retention | Absent | Plain append logs are configured without rotation policy. |

## Secure Settings

| Capability | Status | Current reality |
|---|---|---|
| Configuration precedence/provenance | Partial | Environment plus `.env` and defaults exist; no persisted/secret-store provenance service. |
| Owner-only atomic secret store | Absent | Secrets are read from `.env`; no atomic backup/rollback lifecycle. |
| Recognition settings wizard | Absent | Key/model/threshold/profile tests are not editable in application. |
| Shopify wizard/capability/location | Absent | Environment config class exists; no UI wizard or scope/capability probe. |
| Movie/Wikimedia settings | Partial | Catalog settings table has thresholds/rate values; no complete operator UI or configured contact identity contract. |
| Infrastructure settings | Partial | Diagnostics and config expose some safe status, not the required organized read-only section. |
| Security settings/session rotation | Absent | No in-app username/password/signing-secret/session workflow. |

## Recognition control and routing

| Capability | Status | Current reality |
|---|---|---|
| Immutable recognition history | Partial | Attempts are separate rows and not deleted, but tier/trigger/forced/image/prompt/schema/cost/acceptance state fields are incomplete. |
| Successful Item force rerun | Contradicted | Worker skips complete recognition; item retry only supports failed recovery. |
| Attempt comparison/selection | Absent | Latest evidence can be shown, but no full compare/select/supersede workflow. |
| Baseline/escalation/frontier router | Absent | One configured model/provider runs without measured staged routing. |
| `UNKNOWN` contract | Partial | Empty/missing-title behavior exists, but no explicit durable routed result contract. |
| Duplicate rerun/test-copy options | Absent | Existing Batch is opened; re-run all and quarantined copy do not exist. |
| Labelled benchmark/cost model | Absent | Token/image fields exist; no configured CAD price version or truth-labelled benchmark. |

## Global inventory and scale

| Capability | Status | Current reality |
|---|---|---|
| Top-level Inventory workspace | Absent | Navigation is Batch-centred. |
| Global server-side search | Absent | Batch Editor is batch-scoped and renders the full Batch. |
| Physical availability state machine | Absent | Quantity/working state fields exist without reservation/pick transition constraints. |
| Item detail/history/actions | Absent | Review/media/catalog fragments exist; no global physical Item detail workspace. |
| Bounded Batch Editor | Contradicted | All Batch rows are rendered and filtered/sorted client-side. |
| 500/5,000 evidence | Absent | Only historical controlled small fixtures are documented. |

## Movie catalog

| Capability | Status | Current reality |
|---|---|---|
| Permanent local Movie IDs | Verified | Separate catalog DB, sequence IDs, aliases, sources, jobs, decisions, events, FTS, and integrity checks exist. |
| Local-first matching | Implemented, unverified | Exact/alias/FTS and scoring services exist; production currently has zero Movies. |
| Provider-neutral interface | Absent | Catalog service is directly coupled to the Wikipedia client. |
| Wikidata candidate source | Absent | Current external discovery is English Wikipedia, not Wikidata structured data. |
| Bounded Wikipedia enrichment | Partial | Official Action API, caching, retries, parsing, provenance, and bounded candidates exist; rights/User-Agent policy needs repair. |
| Distinct catalog outcomes | Partial | Jobs distinguish several states but not the complete v0.10.0 contract. |
| Minimum Edition model | Absent | Item edition text exists; no durable Edition identity/source relationship. |
| Inventory bootstrap CLI | Absent | Existing catalog admin commands do not implement the required bootstrap flow. |
| Guarded full dump/download/import | Absent | No Wikidata dump tooling. |

## Shopify, orders, and picking

| Capability | Status | Current reality |
|---|---|---|
| Draft simulation | Implemented, unverified | Simulation/service/tests exist. |
| Deliberate draft UI | Absent | Publish does not expose `upload_draft()` as an owner-confirmed action. |
| Stable outbound checkpoints | Partial | Upload attempts and per-Item sync checkpoints exist. |
| `inventoryActivate` idempotency | Contradicted | Key is persisted after activation and not passed through the mutation. |
| Duplicate SKU ambiguity rejection | Partial | Collision checks exist but current client behavior must be regression-tested against multiple matches. |
| Order polling/revisions | Absent | No order entities or sync command/UI. |
| Webhook HMAC/deduplication | Absent | No webhook receiver. |
| Exact listing link | Partial | IDs live on Item/shopify sync; no separate constrained listing-link entity for order allocation. |
| Exclusive reservations | Absent | No reservation table/state/uniqueness. |
| Pick Queue and state machine | Absent | No Orders/Pick navigation or workflows. |
| Fulfillment confirmation/idempotency | Absent | No fulfillment attempts or `fulfillmentCreate` flow. |

## Release, browser, and documentation

| Capability | Status | Current reality |
|---|---|---|
| Active version consistency | Contradicted | Source is 0.9.0, installed metadata 0.7.0, and active test/readiness documents still claim 0.7.0. |
| Current Firefox shortcut proof | Absent | Historical evidence contradicts active shortcut claims; new native run required. |
| Current Operator Guide/UI parity | Contradicted | Guide cannot cover absent v0.10.0 workflows and existing shortcut/hostname truth differs. |
| Official Guacamole public hostname | Contradicted by live DNS | `desktop.ims.canadavhs.ca` failed resolution; compatibility `remote` hostname passed. |
| Release archive/evidence | Partial | Historical tooling/evidence exists; no v0.10.0 sanitized archive yet. |
| 1.0 acceptance | Intentionally deferred | Physical tape, live AI, live Shopify draft/order, CSV reconciliation, cold boot, and final guide/browser gates remain owner-live acceptance. |

## Architecture conclusion

The v0.9.0 branch is a sound recoverable foundation, not an implementation of the v0.10.0 work order. Permanent physical identity, transactional editing, local catalog foundations, and draft checkpoints should be extended in place. The stabilization/security phase is a real prerequisite: new settings, external jobs, inventory transitions, and order actions must not be added before CSRF, auth/session, health truth, process ownership, update safety, and outbound idempotency are corrected.
