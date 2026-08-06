# SnapIMS v0.15.0 Performance Report

**Measured:** August 5, 2026  
**Environment:** Linux sandbox; target 2012 Mac mini unavailable.

## Browser measurements

| Scenario | Result |
| --- | --- |
| 5,000-item Batch Editor response | 430,721 bytes, 100 rendered rows |
| Relayed Chromium 5,000-item render | 0.471 seconds |
| 390-pixel Batch Editor | Page body fits; grid scrolls internally |
| 390-pixel Publish workflow | Page body fits without horizontal body overflow |
| Publish browser verification | 52 / 52 checks |

## Import benchmark

| Scenario | Cold | Warm/cache |
| --- | ---: | ---: |
| 20 items / 42 photos | 517 ms; 42 decodes; 42 QR scans | 17 ms; 42 cache hits; 0 decodes/scans |
| 100 items / 202 photos | 2,280 ms; 202 decodes; 202 QR scans | 33 ms; 202 cache hits; 0 decodes/scans |
| 20-item Commit | 1,476 ms; 42 streamed final hashes | Not applicable |

The Preview request returned control in 39 ms for the 42-photo batch and 8 ms for the 202-photo batch because the durable scan runs separately. Observed process-memory proxy peaked at 176.83 MB in this sandbox.

## Shopify execution characteristics

- Jobs are serialized locally to avoid overlapping batch writes.
- Per-item transient retries are bounded to three attempts.
- Completed items are skipped during resume.
- Progress, rate, elapsed time, and ETA are derived from durable job state.
- Draft-first is the default. Live publication requires a selected publication and exact typed confirmation.

Real Shopify API latency/rate limits and target-hardware throughput remain owner-pilot measurements.
