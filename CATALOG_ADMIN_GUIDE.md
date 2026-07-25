# Catalog Administration Guide

Run commands from the repository root with `PYTHONPATH=.`.

```bash
python scripts/catalog_admin.py --data-root /path/to/data verify
python scripts/catalog_admin.py --data-root /path/to/data backup --reason manual
python scripts/catalog_admin.py --data-root /path/to/data rebuild-index
python scripts/catalog_admin.py --data-root /path/to/data reconcile
python scripts/catalog_admin.py --data-root /path/to/data search "The Thing" --year 1982
python scripts/catalog_admin.py --data-root /path/to/data show MOV-00000001
python scripts/catalog_admin.py --data-root /path/to/data add-alias MOV-00000001 "Alternate title"
python scripts/catalog_admin.py --data-root /path/to/data update MOV-00000001 --canonical-title "Corrected title" --runtime 106
python scripts/catalog_admin.py --data-root /path/to/data refresh MOV-00000001
python scripts/catalog_admin.py --data-root /path/to/data export catalog.json
python scripts/catalog_admin.py --data-root /path/to/data import catalog.json
```

## Merge

Merge is deliberate, backup-protected, transactional and audited. Review both Movies and every linked physical Item first. Same title is never sufficient evidence. The surviving Movie ID remains; inventory links are reconciled and link events preserve history.

## Split

Split creates a new immutable Movie and requires explicit selection of fields/aliases and linked Items. It is backup-protected and audited. Verify all links after completion or `LINK_PENDING` recovery.

## Candidate resolution

Ambiguous candidates appear in Review for the affected Item. Select only the film shown in the photograph. The selection records an operator decision and does not change other Items automatically.

## Destructive controls

No maintenance action should expose silent delete/cascade behaviour. Preserve backups, current links and catalog events. Deactivation is preferred over destructive removal of sourced records.
