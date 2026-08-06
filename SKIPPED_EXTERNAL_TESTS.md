# SnapIMS v0.15.0 Skipped and Simulated External Tests

| Capability | Disposition | Reason |
| --- | --- | --- |
| Live OpenAI recognition | Skipped; deterministic provider tests used | No production API key/account was supplied. |
| Live Shopify draft/live/delete lifecycle | Skipped; deterministic Shopify services/transports used | Owner Shopify credentials and store were not available in the sandbox. |
| Live Wikipedia | Skipped | Explicit opt-in integration test was not enabled. |
| Native Firefox | Skipped | Firefox runtime unavailable. |
| Direct Chromium localhost navigation | Relayed local HTTP used | Managed browser policy blocked localhost navigation. |
| 2012 Mac mini target hardware | Skipped | Hardware unavailable. |
| Cloudflare/Guacamole/xrdp | Skipped | Owner infrastructure unavailable. |
| Real HEIC camera file | Skipped | Optional HEIC runtime unavailable. |

Deterministic tests exercised draft creation, live promotion, publication, restore-to-draft, archive, permanent delete, sync, conflict handling, retry, recovery, and idempotency. These are local engineering passes, not substitutes for the real owner-store pilot.
