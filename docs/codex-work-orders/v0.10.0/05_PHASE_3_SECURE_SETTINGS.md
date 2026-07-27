# Phase 3 — Secure Settings and Connection Wizards

## Objective

Make first-time and routine configuration possible inside SnapIMS without manual `.env` editing.

## Configuration architecture

Create an explicit configuration service with provenance.

Recommended precedence:

1. explicit process environment override;
2. permissions-restricted SnapIMS secret store;
3. persisted non-secret settings;
4. legacy project `.env`;
5. application default.

The UI must show where an effective non-secret value came from.

Do not silently overwrite externally managed environment settings.

## Secret store

Use an external path such as:

```text
~/SnapIMS-data/secrets/
```

Requirements:

- directory owner-only;
- files mode 0600;
- atomic temp-file + fsync + rename;
- timestamped backup before replacement;
- no secret returned after save;
- masked read model;
- administrator re-authentication;
- audit event names field only;
- redaction integration;
- session rotation for auth changes;
- safe migration from `.env`;
- rollback.

Do not delete legacy secret values automatically. Offer a validated migration and then tell the operator exactly what remains.

## Settings navigation

Create sections:

- General;
- Recognition;
- Shopify;
- Movie Data;
- Infrastructure;
- Security;
- Backup and Retention.

### Recognition

Fields:

- OpenAI key;
- provider;
- baseline model;
- escalation model;
- optional frontier model;
- confidence threshold;
- contradiction rules;
- maximum attempts;
- timeout;
- retry limit;
- image count/profile;
- prompt version;
- configured token price table and version;
- test connection;
- test image-capability/schema.

Model discovery:

- query official provider model list;
- do not assume every model accepts images;
- maintain capability registry;
- run a bounded image + strict-schema probe;
- allow manual model ID with test;
- save only tested-compatible models for recognition roles.

### Shopify wizard

Steps:

1. store domain;
2. Admin API token;
3. shop identity test;
4. configured API version;
5. capability/scope probe;
6. display exact missing permissions;
7. discover locations;
8. choose intended location;
9. enforce draft-only;
10. save securely;
11. simulation;
12. explicit link to live-draft acceptance—not automatic execution.

Verify current official API behaviour. Do not rely only on a hardcoded scope list.

### Movie Data

Fields:

- candidate provider;
- provider credential if needed;
- approved field profile;
- language/region;
- cache policy;
- refresh policy;
- Wikipedia/Wikimedia User-Agent including contact;
- request concurrency;
- rate limit;
- timeout/retries;
- candidate test;
- provenance preview;
- catalog bootstrap status;
- dump location and storage policy.

Wikimedia requests must use a meaningful User-Agent, serial/bounded concurrency, Retry-After handling and exponential backoff.

### Infrastructure

Mostly read-only:

- project path;
- data root;
- inventory DB;
- catalog DB;
- backup path;
- log path;
- local/public URLs;
- tunnel name/config;
- Guacamole URL;
- managed-service ownership;
- current service health;
- external endpoint status.

Do not expose credential file contents.

### Security

Support:

- change admin username/password;
- rotate signing secret;
- revoke all sessions;
- view safe login audit;
- Cloudflare Access status note;
- backup before credential replacement.

## Unsaved connection tests

Allow connection tests using unsaved values in memory. The browser must not receive the secret back in the response. Discard the test secret unless the operator explicitly saves.

## Validation and rollback

Every save:

- validates format;
- tests where selected;
- creates backup;
- writes atomically;
- reloads effective configuration;
- verifies result;
- records redacted event;
- offers rollback.

## Acceptance

A first-time operator can configure:

- OpenAI;
- models;
- Shopify;
- location;
- movie provider;
- Wikimedia identification;
- relevant thresholds;

entirely in the application, restart SnapIMS and retain effective settings securely.

No secret appears in:

- page source;
- URL;
- logs;
- diagnostics;
- support bundle;
- Git;
- error response.
