# Phase 8 — Scale, Recovery and Production-Candidate Acceptance

## Objective

Verify that the combined v0.10.0 system is stable at its claimed scale and prepare the separate physical/live 1.0 acceptance program.

## Performance work

### Batch Editor

Measure:

- query;
- server render/API;
- response size;
- DOM nodes;
- first interactive time;
- search/filter/sort;
- cell save;
- thumbnail loading;
- bulk operation.

Fixtures:

- 20 Items;
- 500 Items;
- 5,000 Items.

Do not claim 5,000-row support unless target hardware/browser passes bounded rendering without freeze.

### Import

Profile:

- file enumeration;
- EXIF;
- hashing;
- image decode;
- downsample;
- QR detect/decode;
- copying;
- derivative generation;
- DB insertion.

Fixtures:

- realistic 20-tape;
- synthetic 500;
- synthetic 5,000/10,000-photo only for architecture evidence.

Optimize by measurement. Preserve exact QR semantics.

### Inventory Search

Measure duplicate-title, broad query and exact ID lookup.

### Catalog

Measure local hit vs external miss.

### Orders/Pick

Measure sync and queue rendering using fixtures with many order lines.

## Recovery matrix

Inject interruption during:

- migration;
- import;
- recognition;
- catalog fetch;
- dump download;
- dump import;
- CSV apply;
- bulk operation;
- Settings write;
- Shopify draft stages;
- order sync page;
- reservation;
- pick transition;
- fulfillment.

After restart verify:

- no duplicate identity;
- exact state;
- resumable operation;
- visible event;
- no partial hidden outcome.

## Browser matrix

Use native Firefox on production host. Also use automated Chromium/Firefox where supported.

Sizes:

- desktop target viewport;
- smaller laptop;
- mobile for supported pages only.

Monitor:

- console;
- page errors;
- failed network;
- HTTP errors;
- focus;
- double submit;
- stale state.

Walkthrough:

1. login/logout/backoff;
2. CSRF rejection;
3. Import;
4. duplicate options;
5. recognition baseline;
6. rerun success;
7. compare/escalate;
8. approved Tags;
9. Approve & Next;
10. Batch Editor;
11. Inventory Search;
12. Item detail/move;
13. catalog local hit/ambiguity;
14. Settings;
15. Live Activity;
16. CSV;
17. Publish simulation;
18. fake draft failure/retry;
19. order sync;
20. reservation;
21. Pick Queue;
22. cancellation;
23. restart;
24. public endpoint;
25. Guacamole remains operational.

## Security verification

- CSRF;
- login throttle;
- session rotation;
- secret redaction;
- file permissions;
- public origin;
- headers;
- webhook HMAC;
- support bundle;
- no accidental public database/media directory;
- no secret in release archive.

## Cold boot

On target host:

```bash
sudo reboot
```

After reconnecting, run only:

```bash
snapims up
snapims status
snapims doctor
```

Verify local/public application and Guacamole.

## 1.0 production gates remain pending until performed

Do not label 1.0 until:

- real 20-tape Pixel pilot;
- live AI measured;
- CSV physically reconciled;
- restart durability against that real batch;
- exactly one authorized Shopify draft inspected;
- first-time operator guide walkthrough;
- final browser verification;
- no known production blocker for claimed scale.

Create a detailed acceptance checklist and evidence folders so the owner can perform these without further architecture changes.

## Exit gate

- quality gate green or failures explicitly blocked;
- bounded scale claims supported by evidence;
- interruption matrix passes;
- cold boot passes;
- all owner-gated live actions are listed;
- no hidden production blocker;
- feature freeze begins after this phase.
