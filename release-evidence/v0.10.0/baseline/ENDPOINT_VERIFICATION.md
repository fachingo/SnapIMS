# Baseline Endpoint Verification

Checked 2026-07-26T19:12:40-06:00 using read-only requests.

## Local SnapIMS

- URL: `http://127.0.0.1:8767/health`
- Result: HTTP 200
- Body: `{"status":"ok","version":"0.10.0","schema":{"ok":true,"problems":[],"schema_version":8}}`

## Public SnapIMS

- URL: `https://ims.canadavhs.ca`
- Result: HTTP 303 to `/login`, followed by HTTP 200
- Expected marker: `SnapIMS`
- Marker result: present

This proves that the public route reached the authenticated SnapIMS login page at the time checked. It does not authenticate or exercise state changes.

## Official Guacamole hostname

- URL: `https://desktop.ims.canadavhs.ca/guacamole/`
- Result: FAIL — DNS name did not resolve

No PASS is claimed.

## Compatibility Guacamole hostname

- URL: `https://remote.canadavhs.ca/guacamole/`
- Result: HTTP 200
- Expected markers: `guacamole` and login application assets
- Marker result: present

This compatibility hostname is the only public Guacamole endpoint verified in the baseline.
