# SnapIMS 0.8.1 Operator Guide

Install once from the SnapIMS repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
scripts/install_launcher.sh
```

After installation, use `snapims` from any directory:

```bash
snapims up
snapims status
snapims restart
snapims logs
snapims down
```

Tunnel controls are:

```bash
snapims tunnel start
snapims tunnel status
snapims tunnel restart
snapims tunnel stop
```

## First administrator account

1. Generate a signing secret:

   ```bash
   snapims auth generate-secret
   ```

2. Generate the password hash:

   ```bash
   snapims auth hash-password
   ```

3. Put the values in `.env`:

   ```bash
   SNAPIMS_AUTH_SECRET=<generated secret>
   SNAPIMS_ADMIN_USERNAME=admin
   SNAPIMS_ADMIN_PASSWORD_HASH=<generated hash>
   ```

4. Restart SnapIMS:

   ```bash
   snapims restart
   ```

## Password reset

Run `snapims auth hash-password`, replace `SNAPIMS_ADMIN_PASSWORD_HASH` in `.env`, then run `snapims restart`. Existing sessions expire naturally or can be ended with Log out.

Logs and PID files live below `SNAPIMS_DATA_DIR/logs`, defaulting to `~/SnapIMS-data/logs`.
