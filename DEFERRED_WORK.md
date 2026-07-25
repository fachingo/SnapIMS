# SnapIMS 0.6.1 Deferred Work

These items were intentionally not represented as fixed.

## Warehouse-scale editor and importer

- O-08 / E-09: virtualized 5,000-row Batch Editor.
- E-11: QR prefilter and high-volume image-decode pipeline.
- E-28: real 500-5,000 tape warehouse acceptance test.

Risk: current workflows are verified for the 20-item browser fixture and automated functional batches, not a real 5,000-tape operation. Recommended release: a future minor version because this changes scale architecture and operator behaviour.

## Import preview depth

- O-06: visual per-photo command-sequence inspector.

Risk: operators must continue using item, product-photo, command and warning counts before Preserve and Import. Recommended release: minor feature package after the real Pixel pilot identifies which sequence evidence is genuinely useful.

## Recognition architecture

- E-16: genuine adaptive image selection and confidence-driven follow-up.

Risk: current metrics must not call fixed selection adaptive. Recommended release: minor AI capability after live-model measurements.

## Security and multi-user operation

- E-18: application authentication, roles, CSRF, secure cookies, batch claims, concurrency control and multi-user acceptance.

Risk: Cloudflare Access is not a replacement for application-level multi-user controls. SnapIMS remains a single-operator, localhost-first workstation. Recommended release: dedicated minor security/workflow package before broad remote or concurrent use.

## Duplicate and edition intelligence

- E-23: near-duplicate image classification, edition matching and pooling.

Risk: exact-copy and pooled decisions remain operator-controlled. Recommended release: post-v1 enrichment package.

## Image-lifetime monitoring

- E-24: no loss was reproduced. Originals, processed media, links and restart persistence passed. Continue monitoring during the real Pixel pilot.
