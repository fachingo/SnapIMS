# SnapIMS v0.13.2 Skipped and Simulated External Tests

## Skipped because the capability was unavailable

| Capability | Disposition | Reason |
| --- | --- | --- |
| Live OpenAI recognition | Skipped; deterministic provider tests used | No production API key or account was supplied. Existing mock/provider contract, retries, persistence, and failure tests passed. |
| Live Shopify draft creation | Skipped; fake Shopify client tests used | No store URL or Admin API token was supplied. Draft, retry, reconciliation, inventory, media, and idempotency tests passed with deterministic dummies. |
| Live Wikipedia | Skipped | The bounded test is explicit opt-in and live Internet behavior was outside the release sandbox. |
| Native Firefox | Skipped | No Firefox binary/runtime was available. |
| Direct Chromium localhost navigation | Skipped by policy; relayed real HTTP used | The managed Chromium URLBlocklist rejected localhost HTTP navigation. |
| 2012 Mac mini | Skipped | Target hardware was not attached to this environment. |
| Cloudflare tunnel / Guacamole / xrdp | Skipped | Owner infrastructure and credentials were unavailable. |
| Real HEIC camera file | Skipped | The HEIC runtime was not installed in the test environment. |

No skipped test is reported as a pass. These gaps are carried into the v1.0 acceptance list.
