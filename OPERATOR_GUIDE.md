# SnapIMS 0.9.0 Operator Guide

## Daily Operation

```bash
snapims up
snapims status
snapims doctor
snapims logs
snapims restart
snapims down
```

`snapims up` is the normal startup command. It starts SnapIMS, Cloudflare Tunnel when configured, guacd, xrdp, and Guacamole Tomcat.

Local URLs:

- SnapIMS: `http://127.0.0.1:8767`
- Guacamole: `http://127.0.0.1:8080/guacamole/`

Remote URL after Cloudflare setup:

- `https://desktop.ims.canadavhs.ca/guacamole/`

## Guacamole Login

Retrieve the generated Guacamole administrator credential:

```bash
sudo cat /etc/guacamole/snapims-admin.env
```

Log in as `snapims-admin`, then open one of the configured connections:

- `Linux Mint Desktop`: full desktop over local RDP, clipboard enabled, Guacamole drive file transfer enabled where supported;
- `SSH Terminal`: local SSH session with SFTP file transfer enabled where supported.

The RDP and SSH connections use the Linux operator username by default and prompt for that Linux account password when connecting.

## SnapIMS Administrator

Create the first SnapIMS administrator in `.env`:

```bash
snapims auth generate-secret
snapims auth hash-password
```

Set:

```bash
SNAPIMS_AUTH_SECRET=<generated secret>
SNAPIMS_ADMIN_USERNAME=admin
SNAPIMS_ADMIN_PASSWORD_HASH=<generated hash>
```

Restart:

```bash
snapims restart
```

Reset a SnapIMS password by generating a new hash, replacing `SNAPIMS_ADMIN_PASSWORD_HASH`, and restarting.

## Remote Desktop Troubleshooting

```bash
which guacd
systemctl status guacd
systemctl status snapims-guacamole-tomcat
systemctl status xrdp
ss -ltn
snapims status
snapims doctor
```

If `desktop.ims.canadavhs.ca` does not load, check `~/.cloudflared/config.yml` and the Cloudflare dashboard Public Hostname for `desktop.ims.canadavhs.ca -> http://127.0.0.1:8080`.
