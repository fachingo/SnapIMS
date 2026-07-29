# Pre-Phase-4 Checkpoint Verification

Date: 2026-07-27

## Remote branch

- Local branch: `feature/v0.10.0-final-preproduction`
- Upstream: `origin/feature/v0.10.0-final-preproduction`
- Requested verified commit:
  `77c09bc17b30e24d8fcdbec3046a772d8118fe3a`
- Remote head observed with `git ls-remote`:
  `9b1c4b78a4ff6832f75681d7c2cb83ec747642e3`
- `77c09bc` is an ancestor of the later Phase 3 closure commit `9b1c4b7`.
- Local and upstream counts after the push were `0 0`.
- No merge, force push, or history rewrite was performed.

## Installed version reconciliation

Cause:

- The active venv retained `snapims-0.7.0.dist-info`,
  `__editable__.snapims-0.7.0.pth`, and its editable finder.
- Running Python from the repository saw the newer source-root
  `snapims.egg-info` first, so `importlib.metadata` appeared to be 0.10.0 while
  `pip show` correctly exposed the stale active editable installation.

Repair:

```text
.venv/bin/python -m pip install --no-deps --editable .
```

The first isolated attempt was blocked by sandbox DNS. The identical command
was rerun through the approved network path and safely uninstalled editable
0.7.0 before installing editable 0.10.0.

Verified after repair:

- `snapims --version`: 0.10.0
- source package `snapims.__version__`: 0.10.0
- `importlib.metadata.version("snapims")` from `/tmp`: 0.10.0
- venv metadata: `snapims-0.10.0.dist-info`
- `pip show snapims`: 0.10.0, editable at this repository
- `~/.local/bin/snapims --version`: 0.10.0
- global launcher targets this repository's `.venv/bin/python`
- `snapims status`: Version 0.10.0 and all required components healthy
- `snapims doctor`: all checks pass
- focused infrastructure/settings/security tests: 34 pass
- `pip check`: no broken requirements
- full `snapims down` / `snapims up` cold start: pass
- post-cold-start status and doctor: pass

No source version was changed and no 0.10.0 version bump was made.

## Official Guacamole hostname

Owner decision:

```text
https://remote.canadavhs.ca/guacamole/
```

- `remote.canadavhs.ca` resolves and returned HTTP 403 to the unauthenticated
  automated probe, consistent with an access-controlled public endpoint.
- `desktop.ims.canadavhs.ca` still fails DNS resolution.
- Current defaults and operator-facing documentation now use `remote`.
- `desktop.ims` is retained only as an unresolved infrastructure backlog name
  and must not be presented as working without deliberate configuration, DNS,
  and browser verification.

## Forward compatibility decisions

Phase 4 recognition/image provenance must support:

- `DESKTOP_IMPORT_QR`
- `DESKTOP_IMPORT_MANUAL`
- `ANDROID_BUTTON`
- `ANDROID_QR`
- `ANDROID_OFFLINE_SYNC`
- `MANUAL`
- `TEST`

Phase 4 does not implement an Android client.

Phase 6 must add field-level catalog provenance and an explicit
contribution-eligibility policy. Shared normalized catalog facts may be
eligible; personal inventory, location, commerce, customer, credential,
original-photo, private-note, and device-identifying data are ineligible.
Automatic central upload remains prohibited without a separate owner-approved
server, privacy, and terms work order.
