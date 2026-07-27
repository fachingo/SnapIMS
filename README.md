# SnapIMS 0.9.0

SnapIMS is a photo-first, exception-driven inventory workstation for Canada VHS. Version 0.9.0 added the remote-workstation infrastructure: Apache Guacamole, guacd, a SnapIMS-owned Tomcat service, RDP desktop access, SSH terminal access, Cloudflare hostname setup, and CLI diagnostics.

The active v0.10.0 pre-release branch includes a verified stabilization layer over that accepted foundation. It adds browser CSRF/origin protection, session and login hardening, truthful component health, guarded CLI updates, Shopify retry idempotency, schema-backed Controlled Tags, and Firefox-verified keyboard shortcuts. It is not yet the v0.10.0 release.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
scripts/install_launcher.sh
sudo scripts/install_guacamole.sh
scripts/configure_cloudflare_guacamole.sh
```

`install_launcher.sh` must run as the operator user. It installs `snapims` into `~/.local/bin`, avoids duplicate PATH entries, and validates `snapims --help` and `snapims version`.

`install_guacamole.sh` installs packaged `guacd`, RDP/SSH/VNC protocol modules, `xrdp`, Java, and a dedicated Tomcat 9 under `/opt/snapims/tomcat9`. It deploys `guacamole.war`, writes `/etc/guacamole`, creates an authenticated `snapims-admin` account, and validates the local Guacamole login page before reporting success.

## Operate

```bash
snapims up
snapims status
snapims doctor
snapims restart
snapims down
snapims update --check
```

`snapims up` starts only services configured as SnapIMS-managed. `status` distinguishes a running cloudflared process from a registered connector and shows service ownership. `doctor` exits nonzero for required failures while keeping optional checks as warnings. Use `snapims update --check` before the explicitly guarded `snapims update --apply`.

Default local URLs:

- SnapIMS: `http://127.0.0.1:8767`
- Guacamole: `http://127.0.0.1:8080/guacamole/`
- Remote desktop: the configured Guacamole public URL printed by `snapims up`

The owner-designated official remote desktop URL is:

- `https://remote.canadavhs.ca/guacamole/`

`desktop.ims.canadavhs.ca` remains an unresolved infrastructure backlog name.
Do not present it as working unless it is deliberately configured,
DNS-resolved, and browser-verified.

## Keyboard and Tags

- `Alt+P` opens the command palette.
- `Alt+1` through `Alt+9` activate the corresponding visible Batch Editor quick
  action when focus is not in a typing control.
- Tags are approved immutable IDs, not free-form text. Review places Tags
  between Price and Discount; Batch Editor provides pills and autocomplete.
- Arrow keys navigate tag suggestions, Enter or comma accepts, Backspace removes
  the last pill, and Escape closes suggestions first.
- Retired tags remain visible on historical items but cannot be newly selected.
- AI can suggest only active, AI-eligible Tag IDs. It cannot create taxonomy or
  assign deterministic-only tags such as `Toonie Tapes`.

## Authentication

SnapIMS auth is configured in `.env`:

```bash
SNAPIMS_AUTH_SECRET=<from snapims auth generate-secret>
SNAPIMS_ADMIN_USERNAME=admin
SNAPIMS_ADMIN_PASSWORD_HASH=<from snapims auth hash-password>
```

Guacamole credentials are separate. The installer stores the generated Guacamole admin credential in `/etc/guacamole/snapims-admin.env`; retrieve it with `sudo cat /etc/guacamole/snapims-admin.env`.

## Release Status

Version 0.9.0 is a **minor** infrastructure release. Production 1.0.0 still requires final live OpenAI, Shopify, physical CSV reconciliation, and operator acceptance gates.
