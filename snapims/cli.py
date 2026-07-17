from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from snapims import db
from snapims.config import DataPaths, ShopifyConfig
from snapims.demo import create_demo_batch
from snapims.inventory import export_inventory_csv, import_inventory_csv, validate_items
from snapims.pipeline import parse_batch
from snapims.processor import process_batch
from snapims.shopify.service import ShopifyService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SnapIMS camera-first inventory prototype")
    parser.add_argument("--data-dir", type=Path, help="Override SNAPIMS_DATA_DIR")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("init", help="Create the data folders and SQLite database")
    demo = commands.add_parser("demo", help="Generate a synthetic QR-delimited camera roll")
    demo.add_argument("destination", type=Path)
    preview = commands.add_parser("preview", help="Dry-run a photo directory")
    preview.add_argument("source", type=Path)
    preview.add_argument("--batch-name")
    preview.add_argument("--recursive", action="store_true")
    import_cmd = commands.add_parser("import", help="Preserve and import a photo directory")
    import_cmd.add_argument("source", type=Path)
    import_cmd.add_argument("--batch-name")
    import_cmd.add_argument("--recursive", action="store_true")
    validate = commands.add_parser("validate", help="Validate one batch or all items")
    validate.add_argument("--batch-id")
    export = commands.add_parser("csv-export", help="Regenerate a batch work CSV")
    export.add_argument("batch_id")
    export.add_argument("destination", type=Path, nargs="?")
    csv_import = commands.add_parser("csv-import", help="Re-import an edited work CSV")
    csv_import.add_argument("csv_path", type=Path)
    commands.add_parser("integrity", help="Run SQLite integrity and FK checks")
    shopify = commands.add_parser("shopify-dry-run", help="Simulate one Shopify draft")
    shopify.add_argument("item_id")
    shopify.add_argument("--remote-check", action="store_true")
    return parser


def _print_preview(batch) -> None:
    print(f"Batch: {batch.batch_id}")
    print(f"Items: {len(batch.items)} | Product images: {batch.photo_count} | Commands: {len(batch.commands)}")
    for item in batch.items:
        flags = ",".join(name for name, active in (("RARE", item.rare), ("REVIEW", item.review)) if active)
        print(f"  {item.sequence:03d} | {item.shelf} | {len(item.photos)} image(s) | {flags or '-'}")
    for warning in batch.warnings:
        print(f"WARNING: {warning}")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    if args.command == "demo":
        try:
            print(create_demo_batch(args.destination))
            return 0
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    paths = DataPaths.from_root(args.data_dir).ensure()
    db.initialize(paths.db_file)
    try:
        if args.command == "init":
            print(f"SnapIMS data initialized at {paths.root}")
        elif args.command == "preview":
            _print_preview(parse_batch(args.source, batch_name=args.batch_name, recursive=args.recursive))
        elif args.command == "import":
            result = process_batch(
                args.source, paths=paths, batch_name=args.batch_name, recursive=args.recursive
            )
            print(json.dumps({
                "batch_id": result.batch_id, "items": result.item_count,
                "product_photos": result.product_photo_count, "commands": result.command_count,
                "duplicate": result.duplicate, "output": str(result.output_folder),
                "work_csv": str(result.work_csv), "warnings": result.warnings,
            }, indent=2))
        elif args.command == "validate":
            identifiers = [
                item["item_id"] for item in db.list_items(paths.db_file, batch_id_value=args.batch_id)
            ]
            results = validate_items(paths.db_file, identifiers)
            print(json.dumps(results, indent=2))
        elif args.command == "csv-export":
            destination = args.destination or paths.processed / args.batch_id / "inventory_work.csv"
            print(export_inventory_csv(paths.db_file, args.batch_id, destination))
        elif args.command == "csv-import":
            print(f"Updated {import_inventory_csv(paths.db_file, args.csv_path, paths=paths)} item(s)")
        elif args.command == "integrity":
            with db.connect(paths.db_file) as connection:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
            print(f"integrity_check={integrity}")
            print(f"foreign_key_violations={len(foreign_keys)}")
            return 0 if integrity == "ok" and not foreign_keys else 1
        elif args.command == "shopify-dry-run":
            report = ShopifyService(paths.db_file, ShopifyConfig.from_env()).dry_run(
                args.item_id, remote_check=args.remote_check
            )
            print(json.dumps({
                "item_id": report.item_id, "ready": report.ready, "action": report.action,
                "errors": report.errors, "warnings": report.warnings,
                "image_count": report.image_count,
            }, indent=2))
            return 0 if report.ready else 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
