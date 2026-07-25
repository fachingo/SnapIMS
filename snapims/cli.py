from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from snapims import __version__, db
from snapims.config import DataPaths
from snapims.demo import create_demo_batch
from snapims.pipeline import parse_batch
from snapims.processor import process_batch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="snapims")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default=os.getenv("SNAPIMS_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.getenv("SNAPIMS_PORT", "8767")))
    preview = sub.add_parser("preview")
    preview.add_argument("source")
    preview.add_argument("--batch-name")
    import_cmd = sub.add_parser("import")
    import_cmd.add_argument("source")
    import_cmd.add_argument("--batch-name")
    demo = sub.add_parser("demo")
    demo.add_argument("folder")
    demo.add_argument("--items", type=int, default=2)
    sub.add_parser("integrity")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.data_dir:
        os.environ["SNAPIMS_DATA_DIR"] = args.data_dir
    paths = DataPaths.from_root().ensure()
    if args.command == "serve":
        uvicorn.run("snapims.web.app:app", host=args.host, port=args.port, reload=False)
    elif args.command == "preview":
        batch = parse_batch(Path(args.source), batch_name=args.batch_name)
        print(f"items={len(batch.items)} product_photos={batch.photo_count} commands={len(batch.commands)} warnings={len(batch.warnings)}")
    elif args.command == "import":
        result = process_batch(Path(args.source), paths=paths, batch_name=args.batch_name)
        print(f"batch_id={result.batch_id} items={result.item_count} duplicate={str(result.duplicate).lower()}")
    elif args.command == "demo":
        create_demo_batch(Path(args.folder), item_count=args.items)
        print(Path(args.folder).resolve())
    elif args.command == "integrity":
        db.initialize(paths.db_file, paths=paths)
        with db.connect(paths.db_file) as connection:
            print(f"integrity_check={connection.execute('PRAGMA integrity_check').fetchone()[0]}")
            print(f"foreign_key_violations={len(connection.execute('PRAGMA foreign_key_check').fetchall())}")


if __name__ == "__main__":
    main()
