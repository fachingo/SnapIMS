# Owner Approval Gates

Codex must stop and request explicit owner approval for these actions.

## Live Shopify write

Includes:

- creating a real draft;
- changing live inventory;
- importing real orders if the owner has not authorized the connection;
- creating fulfillment;
- webhook subscriptions that modify live app configuration.

Before asking, Codex must present:

- exact operation;
- exact Item/order;
- dry-run result;
- expected external effect;
- rollback/reconciliation plan;
- scope/capability status.

## Full Wikidata dump

Before asking, present:

- official remote file;
- compressed size;
- checksum source;
- available disk;
- estimated temporary/import storage;
- expected runtime;
- destination;
- exact command;
- ability to resume.

Inventory-driven API bootstrap does not require a full-dump approval unless it is likely to create significant traffic/cost.

## Sudo

Ask only when required. Provide the exact command and why.

## Secret entry

Never request secrets in chat or commit them. Prompt the owner to enter them directly into terminal/UI.

## Destructive production-data action

Before asking:

- validated backup path;
- checksum;
- restore test;
- affected rows/files;
- expected result;
- dry-run;
- recovery plan.

## Irreversible external infrastructure

Includes DNS deletion, tunnel deletion, credential revocation or public route removal. Normal service restart does not require approval.

## Not approval-gated

Codex should proceed autonomously with:

- source edits;
- tests;
- disposable migrations;
- fixture generation;
- local browser tests;
- documentation;
- Git phase commits;
- non-destructive backup;
- API documentation review;
- mock Shopify transport;
- bounded public read-only metadata requests under configured policy.
