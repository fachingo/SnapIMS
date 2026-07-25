# SnapIMS 0.6.1 Demo and Pilot Data

Synthetic fixtures exist only for development, automated tests, and browser verification.

## Safety rule

Production mode does not list or accept Mock, fixture, demo, or synthetic recognition providers. Explicit test mode requires:

```bash
export SNAPIMS_ENABLE_TEST_PROVIDERS=true
```

Test-sourced results retain provider provenance and cannot satisfy production publish readiness until a deliberate manual replacement or trusted live-provider result becomes authoritative.

## Pilot rule

Synthetic browser evidence verifies workflows; it does not prove live AI recognition, billing, latency, real Pixel capture quality, physical CSV reconciliation, or Shopify draft creation. Those remain mandatory 1.0 acceptance gates.
