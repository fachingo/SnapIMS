# SnapIMS v0.13.2 Performance Report

**Measured:** August 4, 2026  
**Environment:** Linux, Python 3.13.5, 5 logical CPUs. The 2012 Mac mini was not available.

## Import

| Scenario | v0.13.2 result |
| --- | --- |
| 20-item / 42-photo Preview request | 79.845 ms |
| 20-item / 42-photo cold scan | 479 ms |
| 20-item warm scan | 18 ms; 0 decodes; 0 QR scans |
| Location-only request | 15.393 ms |
| 20-item Commit | 1517.286 ms |
| 100-item / 202-photo cold scan | 2388 ms |
| 100-item warm scan | 40 ms; 0 decodes; 0 QR scans |
| Observed memory proxy | 168.77 MB |

The same-environment v0.12.3 parser baseline was 1517.626 ms. The measured cold-preview improvement was **68.44%**. Absolute latency is comfortably below the release targets, but the original 80% relative-improvement gate was not reproduced with this baseline methodology and remains a target-hardware acceptance item before v1.0.

## Batch Editor

The original v0.13.0 audit measured 22,664,709 bytes and 11.593 seconds DOMContentLoaded for 5,000 items. v0.13.2 returned **430,721 bytes**, rendered **100 rows**, and completed the relayed Chromium render in **0.414 seconds**.

## Resource stability

| Metric | Full one-process suite |
| --- | --- |
| Baseline descriptors | 3 |
| Peak descriptors | 166 |
| Final descriptors | 7 |
| Peak SQLite-related descriptors | 12 |
| Final SQLite-related descriptors | 0 |

The peak includes active temporary databases during the suite. After teardown, the process returned to seven descriptors and zero SQLite handles.
