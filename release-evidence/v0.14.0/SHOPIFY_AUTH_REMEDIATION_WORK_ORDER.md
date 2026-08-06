SnapIMS Shopify Authentication and Settings Remediation Work Order

You are acting as the senior SnapIMS developer, Shopify integration engineer, security engineer, UX engineer, QA engineer, documentation owner, and release manager.

Work directly from the latest pushed Git branch:

Repository: https://github.com/fachingo/SnapIMS
Starting branch: feature/shopify-auth-v0133

Begin by running:

git fetch --all --prune
git checkout feature/shopify-auth-v0133
git pull --ff-only origin feature/shopify-auth-v0133
git status

Confirm that the branch contains the complete SnapIMS v0.13.2 baseline before changing code.

Do not work from an old ZIP, main, an old v0.10/v0.12 branch, or a stale local source directory.

1. Objective

Replace SnapIMS's obsolete manual static-token-only Shopify setup with a secure, operator-friendly authentication workflow for a Shopify Dev Dashboard app owned by the same organization as the Canada VHS store.

The current application is hard-coded around:

SHOPIFY_ADMIN_ACCESS_TOKEN

The operator's Shopify app is:

created in the Shopify Dev Dashboard;

installed in the Canada VHS store;

configured with Admin API scopes;

supplied with a Client ID and Client Secret;

not supplied with a permanently displayed Admin API access token.

For this single-owner, single-store deployment, implement Shopify's current client credentials grant. SnapIMS must use the configured Client ID and Client Secret to request an access token from:

POST https://{shop}.myshopify.com/admin/oauth/access_token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
client_id=...
client_secret=...

The returned access token expires after approximately 24 hours. SnapIMS must cache it securely, track expiry, refresh it automatically before expiry or after an authentication failure, and retry the failed Shopify request once with the refreshed token.

Do not require the operator to manually generate, copy, or replace a temporary Admin API access token every day.

Do not implement a fake token workflow or merely relabel the existing token field.

2. Version decision

This is a new authentication capability and a redesigned operator setup workflow. Under the SnapIMS version policy, it is a minor release:

0.13.2 -> 0.14.0

Do not label this v0.13.3. Do not label it v1.0.0.

Create a working branch from the supplied branch:

git checkout -b feature/shopify-client-credentials-v0140

Update every active version marker to 0.14.0, including:

Python package metadata;

application version constants;

CLI output;

Home-page version;

installer;

service/launcher metadata;

current README;

current guides;

release notes;

browser report;

production-readiness report;

package names;

manifests and checksums.

Historical release notes may retain historical version numbers.

3. Shopify authentication architecture

Implement a dedicated Shopify credential/token service. Do not scatter token exchange logic through routes and GraphQL calls.

Persisted operator configuration

Store these values:

SHOPIFY_STORE_DOMAIN
SHOPIFY_CLIENT_ID
SHOPIFY_CLIENT_SECRET
SHOPIFY_LOCATION_ID
SHOPIFY_API_VERSION
SHOPIFY_DRAFT_ONLY

Security requirements:

SHOPIFY_CLIENT_SECRET is secret and must use SnapIMS's encrypted secret-storage path.

Never display the saved secret after storage.

Never write the secret or access token to logs, exception messages, browser HTML, query strings, screenshots, audit details, or test snapshots.

Client ID is not secret, but still treat it as configuration.

Normalize the store domain to the canonical *.myshopify.com form.

Reject protocols, paths, query strings, whitespace, and non-Shopify domains.

Keep SHOPIFY_DRAFT_ONLY=true mandatory for this release.

Runtime token cache

The short-lived access token must not be treated as long-term operator configuration.

Store a restart-safe token cache containing:

shop domain
access token (encrypted)
granted scopes
issued timestamp
expiry timestamp
last refresh timestamp
last refresh result

Rules:

Reuse a valid token until it approaches expiry.

Refresh proactively with a safety margin, such as five minutes.

If Shopify returns an authentication failure, refresh once and retry the original request once.

Never create an unbounded retry loop.

Coordinate refreshes so concurrent Shopify requests do not all request separate tokens.

Use a process lock plus durable state sufficient for this local single-process deployment.

If refresh fails, preserve the previous diagnostic information but do not expose secrets.

Restarting SnapIMS must not require the operator to re-enter credentials.

Removing or replacing credentials must invalidate the cached token.

Changing the store domain or Client ID must invalidate the cached token.

Record safe audit events such as credential saved, connection tested, token refreshed, and credential removed. Do not audit secret values.

Compatibility

Provide a forward migration path for an existing saved:

SHOPIFY_ADMIN_ACCESS_TOKEN

Requirements:

Do not delete an existing legacy token during migration.

Mark legacy static-token mode as deprecated.

Allow it temporarily as a clearly labeled fallback when no Client ID/Secret is configured.

Prefer client-credentials mode whenever Client ID and Client Secret are configured.

Add a safe operator action to remove the legacy token after successful migration.

Never confuse the Client ID, Client Secret, and Admin API access token in labels or validation.

Update runtime configuration validation so Shopify is considered configured when either:

client-credentials configuration is complete, or

legacy-token fallback is complete.

4. Redesign Shopify Settings

The current Shopify settings are confusing and expose duplicate token fields. Replace them with one guided setup section.

Required page structure

Use a clear step-by-step wizard or progressive section:

Step 1 — Store

Fields:

Shopify store domain
Admin API version

Help text must say:

Use the permanent .myshopify.com domain, without https:// or a trailing path.

Step 2 — Dev Dashboard credentials

Fields:

Client ID
Client Secret
Current SnapIMS administrator password

Help text must clearly distinguish:

Client ID: visible in Shopify Dev Dashboard → App → Settings.

Client Secret: secret value from that same page, commonly beginning with shpss_.

Access token: generated automatically by SnapIMS and not entered manually.

Buttons:

Save credentials securely
Test connection

A single Test and save action may be added only if validation failures never partially save configuration.

Step 3 — Connection result

Show:

authenticated store name;

canonical .myshopify.com domain;

shop GID;

authentication mode;

token status: valid, refreshing, expired, or failed;

token expiry time in local time;

granted scopes;

missing required scopes;

available locations;

whether each location is active;

whether each location fulfills online orders.

Never show the access token or Client Secret.

Step 4 — Inventory location

Present available locations as radio buttons or a select menu. Do not require the operator to copy a raw Shopify Location GID manually.

Store the selected GID internally. Display both location name and GID in a secondary detail line.

Step 5 — Publish safety

Show:

Draft-only publishing: Enabled

Explain that SnapIMS creates Shopify drafts and does not publish products live automatically.

Status and recovery controls

Provide:

Retest connection
Refresh access token now
Change credentials
Remove Shopify connection

Destructive removal must require:

SnapIMS administrator re-authentication;

explicit confirmation;

safe removal of saved credentials and cached tokens;

no deletion of existing SnapIMS items or Shopify linkage history.

UX requirements

Remove duplicate token-entry forms.

Remove obsolete wording such as “Unsaved Admin API token.”

Do not require raw GID entry during normal setup.

Keep advanced technical details in a collapsible section.

Provide actionable error messages:

wrong store domain;

invalid Client ID or Secret;

app not installed;

app/store ownership incompatibility;

missing scopes;

token endpoint rejected request;

Shopify unavailable;

no active inventory locations.

Errors must explain the next operator action without exposing secrets.

Preserve mobile usability at 390 px.

Preserve authentication and CSRF protections.

Secret changes require administrator re-authentication.

5. Required Shopify scopes

Inspect the actual GraphQL operations in the current source and derive the exact minimum required scopes.

At minimum, compare actual code usage against the currently configured app scopes, which may include:

read_files
write_files
read_products
write_products
read_inventory
write_inventory
read_locations
read_publications
write_publications

Do not blindly require every historical scope.

Create a single authoritative scope declaration used by:

settings diagnostics;

provider probes;

documentation;

tests.

For each required scope, document the operation that requires it.

If a scope is not used, do not require it.

Do not expand permissions merely to make the test pass.

6. Shopify transport integration

Update the Shopify GraphQL transport so every request obtains a valid access token from the new token service.

Requirements:

Use X-Shopify-Access-Token.

Preserve current GraphQL Admin API behavior.

Keep draft creation, media handling, inventory, retry, reconciliation, and idempotency behavior intact.

Do not log headers containing credentials.

Keep bounded timeouts.

Preserve existing request correlation and safe diagnostics.

Distinguish:

authentication failure;

authorization/scope failure;

Shopify user errors;

GraphQL errors;

transport timeout;

rate limiting.

Only authentication failure may trigger one token refresh and retry.

A missing permission must not trigger repeated token refreshes.

7. Database migration and data safety

Use a forward-only migration if durable token metadata requires database storage.

Preserve:

existing inventory;

Batch IDs;

Item IDs;

images;

recognition work;

prices;

tags;

locations and history;

Shopify product and variant IDs;

publish attempts;

reconciliation history;

credentials unrelated to Shopify;

logs and settings.

Back up the database before migration.

Never solve configuration problems by deleting the operator database.

Test:

clean installation;

upgrade from v0.13.2;

v0.13.2 with no Shopify configuration;

v0.13.2 with a legacy static token;

v0.13.2 with partially entered Shopify settings;

failed migration recovery.

8. Automated test requirements

Use deterministic fakes for Shopify. Do not require live credentials for the complete local suite.

Add unit tests for:

domain normalization and validation;

client-credentials request formation;

token response parsing;

expiry calculation;

refresh safety margin;

encrypted token persistence;

token cache reuse;

restart reuse;

proactive refresh;

refresh after authentication failure;

exactly one retry;

no retry for missing scopes or GraphQL user errors;

concurrent refresh deduplication;

credential replacement invalidates token;

credential removal clears token;

secret redaction;

legacy-token compatibility;

static-token-to-client-credentials migration behavior.

Add settings integration tests for:

successful setup;

incorrect administrator password;

invalid store domain;

invalid Client ID/Secret;

token endpoint failure;

app not installed/rejected credentials;

missing scopes;

location selection;

no locations;

save without leaking secrets;

retest;

manual refresh;

credential replacement;

removal confirmation;

CSRF;

unauthenticated access.

Add browser tests for:

desktop setup from blank state;

mobile setup at 390 px;

saved-secret masked state;

successful connection;

missing-scope warning;

location selection without raw GID entry;

restart durability;

legacy-token migration display;

safe credential removal;

no console errors;

no failed unexpected requests;

no secret values in DOM, logs, screenshots, or browser storage.

Run all pre-existing tests and preserve their behavior.

9. Live owner test support

The local automated suite may use dummies, but the release must include an operator-safe live verification procedure.

Add a bounded live test that:

requests a token with the saved Client ID and Secret;

retrieves shop identity;

checks granted scopes;

lists locations;

performs no write operation;

reports token expiry;

redacts all secrets.

Add a separate explicit draft-creation pilot requiring operator confirmation.

Never create a live product during a read-only connection test.

10. Documentation synchronization

Update:

README;

Installation Guide;

Deployment Guide;

Operator Guide;

Complete Operating Manual;

Day-to-Day Guide where relevant;

Shopify setup guide;

Recovery Procedures;

Browser Verification Report;

Production Readiness Report;

Release Notes;

skipped external tests;

pre-v1.0 gap list.

The Shopify guide must show the exact current flow:

Create or open the app in Shopify Dev Dashboard.

Configure and release the required scopes.

Install the app into the owned store.

Open SnapIMS Settings → Shopify.

Enter .myshopify.com domain.

Enter Client ID and Client Secret.

Re-authenticate as SnapIMS administrator.

Save and test.

Select an inventory location by name.

Confirm draft-only mode.

Run read-only verification.

Run one-item draft pilot separately.

Remove active instructions telling operators to locate or paste a permanent Admin API access token.

Render and visually inspect every updated PDF.

Follow the final guide against the final browser UI and correct every mismatch.

11. Verification and release gate

Run:

complete Python suite in one process;

compile checks;

JavaScript syntax checks;

installer shell checks;

migration tests;

clean install;

v0.13.2 upgrade;

restart durability;

settings browser tests;

desktop Chromium walkthrough;

390 px mobile walkthrough;

Firefox when available;

clean extracted release test.

Inspect:

server logs;

browser console;

page errors;

failed requests;

HTTP 4xx/5xx;

secret leakage;

stale version text;

stale token terminology.

Do not claim live Shopify success without actual credentials.

The release is blocked if:

credentials are exposed;

token refresh is not automatic;

concurrent refresh creates token storms;

restart loses the connection;

the UI still requires manual access-token entry for the normal Dev Dashboard flow;

raw Location GID entry is still required in the normal workflow;

missing scopes are misreported as bad credentials;

live connection testing performs a write;

existing publishing tests regress;

documentation does not match the UI.

12. Packaging

Produce:

SnapIMS-v0.14.0-full-source.zip
install_v0140.sh
snapims-0.14.0-py3-none-any.whl
SnapIMS-v0.14.0-full-source.zip.sha256

Include:

complete source;

migrations;

tests;

deterministic Shopify fakes;

browser scripts and evidence;

editable guides;

rendered PDFs;

performance/test reports;

issue traceability;

release notes;

production-readiness report;

per-file manifest.

Test the final archive from a clean extraction.

13. Git requirements

Do not modify the starting branch directly after creating the v0.14.0 branch.

When implementation and verification are complete:

git status
git add -A
git commit -m "v0.14.0: add Shopify Dev Dashboard client credentials authentication"
git push -u origin feature/shopify-client-credentials-v0140

Return:

branch name;

commit SHA;

full test totals;

skipped tests and exact reasons;

files changed;

migration number;

browser verification summary;

clean-install result;

v0.13.2 upgrade result;

release ZIP path;

archive SHA-256;

remaining pre-v1.0 limitations.

Do not leave uncommitted changes.

Do not merge to main.

Do not return only a plan, diff, or partial patch.

Implement, test, repair, document, package, commit, and push the complete v0.14.0 release.