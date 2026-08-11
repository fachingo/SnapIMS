# Rescue Port Manifest Notes

The distributable ZIP is intentionally curated. It does not contain the local lightweight harness/stub modules used to unit-test the rescue transformer. In particular it does not ship a replacement `snapims/db.py`, pricing subsystem, catalog subsystem, Shopify subsystem, Import system, Recognition system, Batch Editor or Publish implementation.

The only files copied into a target checkout by the installer are explicitly listed in `SAFE_MODULES` and `SAFE_PAYLOAD` inside `scripts/apply_v0160_rescue_port.py`.
