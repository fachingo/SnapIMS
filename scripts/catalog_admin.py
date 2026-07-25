#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from snapims.catalog import db as catalog_db
from snapims.catalog.admin import (
    add_alias,
    import_catalog_json,
    inspect_movie,
    manual_search,
    merge_movies,
    reconcile_maintenance_jobs,
    refresh_movie_source,
    split_movie,
    update_movie_fields,
)
from snapims.config import DataPaths


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="SnapIMS SLMC catalog administration")
    root.add_argument("--data-root", type=Path, help="SnapIMS data root; defaults to SNAPIMS_DATA_DIR")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("verify")
    commands.add_parser("backup")
    commands.add_parser("rebuild-index")
    commands.add_parser("reconcile")
    show = commands.add_parser("show")
    show.add_argument("movie_id")
    refresh = commands.add_parser("refresh")
    refresh.add_argument("movie_id")
    update = commands.add_parser("update")
    update.add_argument("movie_id")
    update.add_argument("--canonical-title")
    update.add_argument("--original-title")
    update.add_argument("--year", type=int)
    update.add_argument("--runtime", type=int)
    update.add_argument("--media-type")
    update.add_argument("--summary")
    search = commands.add_parser("search")
    search.add_argument("title")
    search.add_argument("--year", type=int)
    alias = commands.add_parser("add-alias")
    alias.add_argument("movie_id")
    alias.add_argument("alias")
    merge = commands.add_parser("merge")
    merge.add_argument("survivor_movie_id")
    merge.add_argument("duplicate_movie_id")
    split = commands.add_parser("split")
    split.add_argument("source_movie_id")
    split.add_argument("canonical_title")
    split.add_argument("--year", type=int)
    split.add_argument("--item-id", action="append", required=True)
    export = commands.add_parser("export")
    export.add_argument("destination", type=Path)
    imported = commands.add_parser("import")
    imported.add_argument("source", type=Path)
    return root


def main() -> int:
    args = parser().parse_args()
    paths = DataPaths.from_root(args.data_root).ensure() if args.data_root else DataPaths.from_root().ensure()
    catalog_db.initialize(paths.catalog_db_file, paths=paths)
    if args.command == "verify":
        output = catalog_db.catalog_summary(paths.catalog_db_file)
    elif args.command == "backup":
        output = {"backup": str(catalog_db.backup_catalog(paths, "manual-cli-backup"))}
    elif args.command == "rebuild-index":
        output = {"indexed_movies": catalog_db.rebuild_search_index(paths.catalog_db_file)}
    elif args.command == "reconcile":
        output = {"completed_jobs": reconcile_maintenance_jobs(paths)}
    elif args.command == "show":
        output = inspect_movie(paths, args.movie_id)
    elif args.command == "refresh":
        output = refresh_movie_source(paths, args.movie_id)
    elif args.command == "update":
        output = update_movie_fields(
            paths,
            args.movie_id,
            canonical_title=args.canonical_title,
            original_title=args.original_title,
            release_year=args.year,
            runtime_minutes=args.runtime,
            media_type=args.media_type,
            concise_summary=args.summary,
        )
    elif args.command == "search":
        output = manual_search(paths, args.title, args.year)
    elif args.command == "add-alias":
        add_alias(paths, args.movie_id, args.alias)
        output = {"movie_id": args.movie_id, "alias": args.alias}
    elif args.command == "merge":
        output = merge_movies(paths, args.survivor_movie_id, args.duplicate_movie_id)
    elif args.command == "split":
        output = split_movie(
            paths,
            args.source_movie_id,
            canonical_title=args.canonical_title,
            release_year=args.year,
            item_ids=args.item_id,
        )
    elif args.command == "export":
        output = {"export": str(catalog_db.export_catalog_json(paths.catalog_db_file, args.destination))}
    elif args.command == "import":
        output = import_catalog_json(paths, args.source)
    else:  # pragma: no cover
        raise AssertionError(args.command)
    print(json.dumps(output, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
