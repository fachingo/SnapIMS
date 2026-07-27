# SnapIMS 0.9.0 Deployment Guide

SnapIMS and Guacamole both bind to localhost. Public access must go through Cloudflare Tunnel or another trusted reverse proxy.

## Managed CLI

```bash
snapims up
snapims status
snapims restart
snapims down
snapims doctor
```

`snapims up` verifies the virtual environment and auth configuration, starts SnapIMS, attempts the configured Cloudflare tunnel, starts or verifies guacd, xrdp, and `snapims-guacamole-tomcat`, then checks the SnapIMS health endpoint and the Guacamole login page.

`snapims down` stops the SnapIMS app, Cloudflare tunnel process, Guacamole Tomcat service, and guacd. It leaves SSH and xrdp installed so the host remains administrable.

## Guacamole Services

The installer creates:

- `guacd.service`: packaged Guacamole proxy daemon;
- `xrdp.service`: local-only RDP desktop backend;
- `snapims-guacamole-tomcat.service`: dedicated Tomcat 9 service for `guacamole.war`.

Local ports:

- `4822`: guacd;
- `3389`: xrdp, bound to `127.0.0.1`;
- `8080`: Tomcat/Guacamole.

Configuration:

```bash
/etc/guacamole/guacamole.properties
/etc/guacamole/user-mapping.xml
/etc/guacamole/snapims-admin.env
```

## Cloudflare

Do not replace the existing `ims.canadavhs.ca` route. Add a second ingress:

```yaml
ingress:
  - hostname: ims.canadavhs.ca
    service: http://127.0.0.1:8767
  - hostname: remote.canadavhs.ca
    service: http://127.0.0.1:8080
  - service: http_status:404
```

Use:

```bash
scripts/configure_cloudflare_guacamole.sh
```

If DNS routing cannot be completed locally, add `remote.canadavhs.ca` in the
Cloudflare dashboard as a Public Hostname on the same tunnel, with service
`http://127.0.0.1:8080`.

`desktop.ims.canadavhs.ca` is not a current route. Keep it as backlog unless it
is deliberately configured, DNS-resolved, and browser-verified.

## Environment

Relevant `.env` settings:

```bash
SNAPIMS_GUACAMOLE_URL=http://127.0.0.1:8080/guacamole
SNAPIMS_GUACAMOLE_PUBLIC_URL=https://remote.canadavhs.ca/guacamole
SNAPIMS_GUACD_SERVICE=guacd
SNAPIMS_TOMCAT_SERVICE=snapims-guacamole-tomcat
SNAPIMS_XRDP_SERVICE=xrdp
SNAPIMS_MANAGE_GUACAMOLE_SERVICES=true
```

## Validation

```bash
which guacd
systemctl status guacd
systemctl status snapims-guacamole-tomcat
systemctl status xrdp
ss -ltn
curl -fsSL http://127.0.0.1:8080/guacamole/ >/dev/null
snapims status
snapims doctor
```
