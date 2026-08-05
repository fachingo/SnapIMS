from __future__ import annotations

import argparse
import getpass
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from snapims import __version__, db
from snapims.auth import (
    authentication_enabled,
    authentication_problem,
    generate_secret,
    hash_password,
)
from snapims.catalog import db as catalog_db
from snapims.config import SnapIMSConfig
from snapims.demo import create_demo_batch
from snapims.manager import ServiceManager
from snapims.observability import query_events, redact
from snapims.pipeline import parse_batch
from snapims.processor import process_batch


def _ensure_venv(config: SnapIMSConfig) -> None:
    venv = config.project_path / ".venv"
    venv_python = venv / "bin" / "python"
    if not venv_python.exists():
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    probe = subprocess.run(
        [
            str(venv_python),
            "-c",
            "import fastapi, uvicorn, snapims",
        ],
        cwd=config.project_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if probe.returncode == 0:
        return
    subprocess.check_call(
        [
            str(venv_python),
            "-m",
            "pip",
            "install",
            "--no-build-isolation",
            "-e",
            str(config.project_path),
        ]
    )


def _pass_fail(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _running_stopped(ok: bool) -> str:
    return "RUNNING" if ok else "STOPPED"


def _auth_state(config: SnapIMSConfig) -> tuple[str, str]:
    problem = authentication_problem(config.auth_secret, config.admin_password_hash)
    if authentication_enabled(config.auth_secret, config.admin_password_hash):
        return "PASS", "enabled"
    if problem:
        return "FAIL", problem
    return "WARN", "disabled"


def _database_ok(config: SnapIMSConfig) -> bool:
    try:
        db.initialize(config.data.db_file, paths=config.data)
        with db.connect(config.data.db_file) as connection:
            integrity = str(
                connection.execute("PRAGMA integrity_check").fetchone()[0]
            )
            foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
            manifest = db.schema_manifest_report(connection)
            return integrity == "ok" and not foreign and bool(manifest["ok"])
    except Exception:
        return False


def _print_service_urls(config: SnapIMSConfig) -> None:
    print(f"SnapIMS local URL: http://{config.host}:{config.port}")
    print(f"Guacamole local URL: {config.guacamole_url}/")
    if config.guacamole_public_url:
        print(f"Guacamole public URL: {config.guacamole_public_url}")


def _print_runtime_identity(config: SnapIMSConfig, manager: ServiceManager) -> None:
    print(f"Resolved project path: {config.project_path.resolve()}")
    print(f"Resolved Python: {manager._app_python().resolve()}")
    print(f"Data directory: {config.data.root.resolve()}")
    print(f"Application version: {__version__}")
    print(
        "Inventory schema: "
        f"{_database_schema_version(config.data.db_file, 'schema_migrations')} "
        f"(supported {db.SCHEMA_VERSION})"
    )


def _git(
    config: SnapIMSConfig, *args: str, check: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=config.project_path,
        text=True,
        capture_output=True,
        check=check,
    )


def _project_version_from_text(payload: str, fallback: str) -> str:
    try:
        parsed = tomllib.loads(payload)
        return str(parsed.get("project", {}).get("version") or fallback)
    except (tomllib.TOMLDecodeError, AttributeError):
        return fallback


def _schema_version_from_text(payload: str, variable: str) -> int | None:
    match = re.search(rf"^{re.escape(variable)}\s*=\s*(\d+)\s*$", payload, re.MULTILINE)
    return int(match.group(1)) if match else None


def _database_schema_version(db_file: Path, table: str) -> int:
    if not db_file.exists():
        return 0
    connection = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    try:
        row = connection.execute(f"SELECT MAX(version) FROM {table}").fetchone()
        return int(row[0] or 0)
    except sqlite3.Error:
        return 0
    finally:
        connection.close()


def update_report(config: SnapIMSConfig) -> dict[str, Any]:
    branch_result = _git(config, "branch", "--show-current")
    branch = branch_result.stdout.strip()
    detached = not branch
    upstream_result = _git(
        config, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"
    )
    upstream = upstream_result.stdout.strip() if upstream_result.returncode == 0 else ""
    dirty_rows = [
        row
        for row in _git(config, "status", "--porcelain").stdout.splitlines()
        if row.strip()
    ]
    ahead = behind = 0
    incoming: list[str] = []
    target_version = __version__
    target_inventory_schema: int | None = db.SCHEMA_VERSION
    target_catalog_schema: int | None = catalog_db.CATALOG_SCHEMA_VERSION
    if upstream:
        counts = _git(config, "rev-list", "--left-right", "--count", f"HEAD...{upstream}")
        if counts.returncode == 0:
            parts = counts.stdout.split()
            if len(parts) == 2:
                ahead, behind = int(parts[0]), int(parts[1])
        incoming = [
            line
            for line in _git(
                config, "log", "--oneline", "--decorate", f"HEAD..{upstream}"
            ).stdout.splitlines()
            if line.strip()
        ]
        remote_pyproject = _git(config, "show", f"{upstream}:pyproject.toml")
        if remote_pyproject.returncode == 0:
            target_version = _project_version_from_text(
                remote_pyproject.stdout, __version__
            )
        remote_inventory = _git(config, "show", f"{upstream}:snapims/db.py")
        if remote_inventory.returncode == 0:
            target_inventory_schema = _schema_version_from_text(
                remote_inventory.stdout, "SCHEMA_VERSION"
            )
        remote_catalog = _git(config, "show", f"{upstream}:snapims/catalog/db.py")
        if remote_catalog.returncode == 0:
            target_catalog_schema = _schema_version_from_text(
                remote_catalog.stdout, "CATALOG_SCHEMA_VERSION"
            )
    current_inventory_schema = _database_schema_version(
        config.data.db_file, "schema_migrations"
    )
    current_catalog_schema = _database_schema_version(
        config.data.catalog_db_file, "catalog_schema_migrations"
    )
    migration_need = (
        target_inventory_schema is None
        or target_catalog_schema is None
        or current_inventory_schema < target_inventory_schema
        or current_catalog_schema < target_catalog_schema
    )
    return {
        "branch": branch or "(detached)",
        "detached": detached,
        "upstream": upstream or "(none)",
        "dirty": bool(dirty_rows),
        "dirty_count": len(dirty_rows),
        "ahead": ahead,
        "behind": behind,
        "incoming": incoming,
        "current_version": __version__,
        "target_version": target_version,
        "current_inventory_schema": current_inventory_schema,
        "target_inventory_schema": target_inventory_schema,
        "current_catalog_schema": current_catalog_schema,
        "target_catalog_schema": target_catalog_schema,
        "migration_need": migration_need,
        "backup_need": config.data.db_file.exists()
        or config.data.catalog_db_file.exists(),
        "restart_impact": "SnapIMS app and managed tunnel restart; Guacamole remains available",
    }


def _print_update_report(report: dict[str, Any]) -> None:
    for key in (
        "branch",
        "upstream",
        "dirty",
        "dirty_count",
        "ahead",
        "behind",
        "current_version",
        "target_version",
        "current_inventory_schema",
        "target_inventory_schema",
        "current_catalog_schema",
        "target_catalog_schema",
        "migration_need",
        "backup_need",
        "restart_impact",
    ):
        print(f"{key.replace('_', ' ').title()}: {report[key]}")
    print("Incoming commits:")
    if report["incoming"]:
        for commit in report["incoming"]:
            print(f"  {commit}")
    else:
        print("  (none)")


def _parse_event_since(value: str) -> str:
    candidate = value.strip()
    relative = re.fullmatch(r"(\d+)([mhd])", candidate, flags=re.IGNORECASE)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2).casefold()
        delta = {
            "m": timedelta(minutes=amount),
            "h": timedelta(hours=amount),
            "d": timedelta(days=amount),
        }[unit]
        return (
            (datetime.now(UTC) - delta)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--since must be a relative duration such as 30m or 2h, "
            "or an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _event_lines(events: list[dict[str, Any]], *, as_json: bool) -> list[str]:
    safe_events = cast(list[dict[str, Any]], redact(events))
    if as_json:
        return [
            json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for event in safe_events
        ]
    lines: list[str] = []
    for event in safe_events:
        relationships = []
        if event.get("retry_of_event_id"):
            relationships.append(f"retry_of={event['retry_of_event_id']}")
        if event.get("recovery_of_event_id"):
            relationships.append(f"recovery_of={event['recovery_of_event_id']}")
        context = [
            f"operation={event['operation_id']}" if event.get("operation_id") else "",
            f"batch={event['batch_id']}" if event.get("batch_id") else "",
            f"item={event['item_id']}" if event.get("item_id") else "",
            f"order={event['order_id']}" if event.get("order_id") else "",
            *relationships,
        ]
        detail = " ".join(value for value in context if value)
        summary = str(event.get("safe_summary") or event.get("outcome") or "").strip()
        suffix = " ".join(value for value in (detail, summary) if value)
        lines.append(
            f"{event['occurred_at']} {event['severity']:<8} "
            f"{event['component']}/{event['event_type']} id={event['event_id']}"
            + (f" {suffix}" if suffix else "")
        )
    return lines


def _show_events(config: SnapIMSConfig, args: argparse.Namespace) -> None:
    if args.last < 1:
        raise SystemExit("--last must be at least 1")
    db.initialize(config.data.db_file, paths=config.data)
    filters = {
        "last": args.last,
        "since": args.since or "",
        "errors": bool(args.errors),
        "severity": args.severity or "",
        "source": args.source or "",
        "batch_id": args.batch or "",
        "item_id": args.item or "",
        "order_id": args.order or "",
        "operation_id": args.operation or "",
    }
    events = query_events(config.data.db_file, **filters)
    lines = _event_lines(events, as_json=bool(args.json))
    if args.export:
        destination = Path(args.export).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(("\n".join(lines) + ("\n" if lines else "")), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(destination)
        destination.chmod(0o600)
        print(f"Exported {len(lines)} redacted events to {destination}")
    else:
        for line in lines:
            print(line)
    if not args.follow:
        return
    last_event_id = max((int(event["event_id"]) for event in events), default=0)
    try:
        while True:
            following = query_events(
                config.data.db_file,
                **filters,
                after_event_id=last_event_id,
            )
            for line in _event_lines(following, as_json=bool(args.json)):
                print(line, flush=True)
            if following:
                last_event_id = max(int(event["event_id"]) for event in following)
            time.sleep(1)
    except KeyboardInterrupt:
        return


def _apply_update(
    config: SnapIMSConfig, manager: ServiceManager, *, allow_dirty: bool
) -> None:
    report = update_report(config)
    _print_update_report(report)
    if report["detached"]:
        raise SystemExit("Update refused: HEAD is detached.")
    if report["upstream"] == "(none)":
        raise SystemExit("Update refused: the current branch has no upstream.")
    if report["dirty"] and not allow_dirty:
        raise SystemExit("Update refused: working tree is dirty.")

    inventory_backup = db.backup_database(config.data, "before-cli-update")
    catalog_backup = catalog_db.backup_catalog(config.data, "before-cli-update")
    metadata = {
        "created_at": datetime.now().astimezone().isoformat(),
        "branch": report["branch"],
        "upstream": report["upstream"],
        "head": _git(config, "rev-parse", "HEAD").stdout.strip(),
        "inventory_backup": str(inventory_backup or ""),
        "catalog_backup": str(catalog_backup or ""),
    }
    restore_metadata = (
        config.data.backups / f"update-{datetime.now():%Y%m%d-%H%M%S}-restore.json"
    )
    temporary = restore_metadata.with_suffix(".tmp")
    temporary.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    temporary.replace(restore_metadata)
    try:
        subprocess.check_call(
            ["git", "pull", "--ff-only"], cwd=config.project_path
        )
        _ensure_venv(config)
        subprocess.check_call(
            [
                str(config.project_path / ".venv" / "bin" / "python"),
                "-m",
                "pip",
                "install",
                "--no-build-isolation",
                "-e",
                str(config.project_path),
            ],
            cwd=config.project_path,
        )
        db.initialize(config.data.db_file, paths=config.data)
        catalog_db.initialize(config.data.catalog_db_file, paths=config.data)
        manager.stop("tunnel")
        manager.stop("app")
        manager.start_app()
        manager.start_tunnel()
        if not manager.wait_for_health():
            raise RuntimeError("updated application did not become healthy")
    except Exception as exc:
        print(f"Update failed: {exc}")
        print(f"Restore metadata: {restore_metadata}")
        print(f"Previous commit: {metadata['head']}")
        print("Rollback requires restoring the recorded databases and previous commit deliberately.")
        raise SystemExit(5) from exc
    print(f"Update complete. Restore metadata: {restore_metadata}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="snapims")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in (
        "up",
        "down",
        "restart",
        "status",
        "doctor",
        "shell",
        "version",
    ):
        sub.add_parser(command)
    for command in ("log", "logs"):
        logs = sub.add_parser(command)
        logs.add_argument("--follow", action="store_true")
        logs.add_argument("--last", type=int, default=100)
        logs.add_argument("--since", type=_parse_event_since)
        level = logs.add_mutually_exclusive_group()
        level.add_argument("--errors", action="store_true")
        level.add_argument(
            "--severity",
            choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        )
        logs.add_argument(
            "--source",
            help=(
                "Component such as app, recognition, catalog, shopify, import, "
                "cloudflare, guacamole, system, auth, or inventory"
            ),
        )
        logs.add_argument("--batch")
        logs.add_argument("--item")
        logs.add_argument("--order")
        logs.add_argument("--operation")
        logs.add_argument("--json", action="store_true")
        logs.add_argument("--export")
    update = sub.add_parser("update")
    update_mode = update.add_mutually_exclusive_group(required=True)
    update_mode.add_argument("--check", action="store_true")
    update_mode.add_argument("--apply", action="store_true")
    update.add_argument("--allow-dirty", action="store_true")
    tunnel = sub.add_parser("tunnel")
    tunnel.add_argument("action", choices=("start", "stop", "restart", "status"))
    auth = sub.add_parser("auth")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    auth_sub.add_parser("generate-secret")
    hash_cmd = auth_sub.add_parser("hash-password")
    hash_cmd.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the new password from standard input instead of prompting.",
    )
    for command in ("serve", "run"):
        serve = sub.add_parser(command)
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
    if args.command == "version":
        print(__version__)
        return
    if args.command == "auth":
        if args.auth_command == "generate-secret":
            print(generate_secret())
            return
        if args.auth_command == "hash-password":
            if args.password_stdin:
                password = sys.stdin.readline().rstrip("\n")
            else:
                password = getpass.getpass("New SnapIMS administrator password: ")
                confirmation = getpass.getpass("Confirm password: ")
                if password != confirmation:
                    raise SystemExit("Passwords do not match.")
            if len(password) < 12:
                raise SystemExit("Administrator password must be at least 12 characters.")
            print(hash_password(password))
            return
    config = SnapIMSConfig.load().ensure()
    paths = config.data
    manager = ServiceManager(config)
    if args.command == "up":
        _print_runtime_identity(config, manager)
        _ensure_venv(config)
        auth_state, auth_detail = _auth_state(config)
        if auth_state == "FAIL":
            print(f"Authentication: FAIL ({auth_detail})")
        manager.start_app()
        tunnel = manager.start_tunnel()
        guacamole_started = manager.start_guacamole()
        healthy = manager.wait_for_health()
        guacamole = manager.guacamole_status()
        _print_service_urls(config)
        print(f"SnapIMS: {_running_stopped(bool(manager._read_pid('app')))}")
        print(f"Health check: {_pass_fail(healthy)}")
        print(
            "Cloudflare Tunnel: RUNNING"
            if tunnel
            else f"Cloudflare Tunnel: STOPPED ({manager.tunnel_problem() or 'not started'})"
        )
        print(
            "Guacamole: RUNNING"
            if guacamole_started or guacamole["available"]
            else f"Guacamole: UNAVAILABLE ({guacamole['problem'] or 'not installed'})"
        )
    elif args.command == "down":
        manager.stop_guacamole()
        manager.stop("tunnel")
        manager.stop("app")
        print("SnapIMS stopped")
    elif args.command == "restart":
        _print_runtime_identity(config, manager)
        manager.stop_guacamole()
        manager.stop("tunnel")
        manager.stop("app")
        _ensure_venv(config)
        manager.start_app()
        manager.start_tunnel()
        manager.start_guacamole()
        healthy = manager.wait_for_health()
        print("SnapIMS restarted")
        print(f"Health check: {_pass_fail(healthy)}")
        guacamole = manager.guacamole_status()
        print(
            "Guacamole: RUNNING"
            if guacamole["available"]
            else f"Guacamole: UNAVAILABLE ({guacamole['problem'] or 'not installed'})"
        )
    elif args.command == "status":
        status = manager.status()
        guacamole = cast(dict[str, object], status["guacamole"])
        auth_state, auth_detail = _auth_state(config)
        database_ok = _database_ok(config)
        print(
            f"SnapIMS .............. {_running_stopped(bool(status['app']))}\n"
            f"Health ............... {_pass_fail(bool(status['health']))}\n"
            f"Cloudflare Tunnel .... {_running_stopped(bool(status['tunnel']))}\n"
            f"Guacamole ............ {'RUNNING' if guacamole['available'] else 'UNAVAILABLE'}\n"
            f"guacd ................ {_running_stopped(bool(guacamole['guacd_service_active']))}\n"
            f"Tomcat ............... {_running_stopped(bool(guacamole['tomcat_service_active']))}\n"
            f"xrdp desktop ......... {_running_stopped(bool(guacamole['xrdp_service_active']))}\n"
            f"Authentication ....... {auth_state}\n"
            f"Database ............. {_pass_fail(database_ok)}\n"
            f"OpenAI ............... {_pass_fail(bool(config.openai_api_key))}\n"
            f"Port ................. {status['port']}\n"
            f"Version .............. {status['version']}\n"
            f"PID .................. {status['pid']}\n"
            f"Project path ......... {status['project_path']}\n"
            f"Python executable .... {status['python_executable']}\n"
            f"Data directory ....... {status['data_directory']}\n"
            f"Inventory schema ..... {_database_schema_version(config.data.db_file, 'schema_migrations')} / {db.SCHEMA_VERSION}"
        )
        if status["tunnel_problem"] and not status["tunnel"]:
            print(f"Cloudflare detail .... {status['tunnel_problem']}")
        if status["tunnel_connector_problem"]:
            print(f"Connector detail ..... {status['tunnel_connector_problem']}")
        ownership = cast(dict[str, str], status["ownership"])
        print(
            "Service ownership ..... "
            f"app={ownership['app']}, tunnel={ownership['tunnel']}, "
            f"guacd={ownership['guacd']}, tomcat={ownership['tomcat']}, "
            f"xrdp={ownership['xrdp']}"
        )
        if guacamole["problem"]:
            print(f"Guacamole detail ..... {guacamole['problem']}")
        if guacamole["warning"]:
            print(f"Guacamole warning .... {guacamole['warning']}")
        if auth_detail and auth_state != "PASS":
            print(f"Authentication detail  {auth_detail}")
    elif args.command in {"log", "logs"}:
        _show_events(config, args)
    elif args.command == "tunnel":
        if args.action == "start":
            pid = manager.start_tunnel()
            if pid:
                print(f"Tunnel started (pid {pid})")
            else:
                print(f"Tunnel not started: {manager.tunnel_problem()}")
        elif args.action == "stop":
            manager.stop("tunnel")
            print("Tunnel stopped")
        elif args.action == "restart":
            manager.stop("tunnel")
            pid = manager.start_tunnel()
            if pid:
                print(f"Tunnel started (pid {pid})")
            else:
                print(f"Tunnel not started: {manager.tunnel_problem()}")
        else:
            status = manager.status()
            if status["tunnel"]:
                print("Tunnel connected")
            elif status["tunnel_problem"]:
                print(f"Tunnel unavailable: {status['tunnel_problem']}")
            else:
                print("Tunnel stopped")
    elif args.command == "doctor":
        dependencies = all(
            importlib.util.find_spec(name)
            for name in ("fastapi", "uvicorn", "cv2", "itsdangerous", "dotenv")
        )
        port_free = manager.health() or not any(
            manager._read_pid(name) for name in ("app", "tunnel")
        )
        auth_problem = authentication_problem(config.auth_secret, config.admin_password_hash)
        project_venv = config.project_path / ".venv" / "bin" / "python"
        active_virtualenv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
        required_checks = [
            ("Python", sys.version_info >= (3, 12)),
            ("venv", project_venv.exists() or active_virtualenv),
            ("dependencies", dependencies),
            ("SQLite", _database_ok(config)),
            ("logs directory", config.data.logs.is_dir()),
            ("config", config.project_path.is_dir()),
            ("write permissions", os.access(config.data.root, os.W_OK)),
            ("port availability", port_free),
        ]
        failed_required = [name for name, ok in required_checks if not ok]
        for name, ok in required_checks:
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if authentication_enabled(config.auth_secret, config.admin_password_hash):
            print("PASS  authentication")
        elif auth_problem:
            print(f"FAIL  authentication - {auth_problem}")
            failed_required.append("authentication")
        else:
            print("WARN  authentication disabled")
        print("PASS  OpenAI API key" if config.openai_api_key else "WARN  OpenAI API key not configured")
        tunnel_config_problem = manager.tunnel_problem()
        connector_problem = manager.tunnel_connector_problem()
        if tunnel_config_problem:
            print(f"WARN  Cloudflare tunnel - {tunnel_config_problem}")
        elif connector_problem:
            print(f"FAIL  Cloudflare tunnel - {connector_problem}")
            failed_required.append("Cloudflare tunnel")
        else:
            print("PASS  Cloudflare tunnel")
        guacamole = manager.guacamole_status()
        guacamole_required = config.manage_guacamole_services
        if guacamole["web"]:
            print("PASS  Guacamole web application")
        elif guacamole_required:
            print(
                "FAIL  Guacamole web application - "
                f"{guacamole['problem'] or 'not installed'}"
            )
            failed_required.append("Guacamole web application")
        else:
            print(
                "WARN  Guacamole web application - "
                f"{guacamole['problem'] or 'not managed by SnapIMS'}"
            )
        if guacamole["warning"]:
            print(f"WARN  Guacamole config - {guacamole['warning']}")
        guacamole_checks = [
            (
                "guacd service",
                bool(guacamole["guacd_service_active"]),
                f"{guacamole['guacd_service']} is not running",
            ),
            (
                "Tomcat service",
                bool(guacamole["tomcat_service_active"]),
                f"{guacamole['tomcat_service']} is not running",
            ),
            (
                "Guacamole HTTP port",
                bool(guacamole["http_port_open"]),
                "is not listening",
            ),
            (
                "guacd port 4822",
                bool(guacamole["guacd_port_open"]),
                "is not listening",
            ),
            (
                "RDP desktop backend",
                bool(guacamole["rdp_port_open"]),
                "is not listening on 127.0.0.1:3389",
            ),
            (
                "SSH backend",
                bool(guacamole["ssh_port_open"]),
                "is not listening on 127.0.0.1:22",
            ),
        ]
        for name, ok, problem in guacamole_checks:
            level = "PASS" if ok else ("FAIL" if guacamole_required else "WARN")
            print(f"{level}  {name}" + ("" if ok else f" - {problem}"))
            if not ok and guacamole_required:
                failed_required.append(name)
        if failed_required:
            print("Doctor result: required checks failed: " + ", ".join(failed_required))
            raise SystemExit(2)
    elif args.command == "shell":
        os.chdir(config.project_path)
        venv = config.project_path / ".venv"
        os.environ["VIRTUAL_ENV"] = str(venv)
        os.environ["PATH"] = f"{venv / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"
        os.execv(
            "/bin/bash",
            [
                "bash",
                "-i",
            ],
        )
    elif args.command == "update":
        if args.check:
            _print_update_report(update_report(config))
        else:
            _apply_update(config, manager, allow_dirty=bool(args.allow_dirty))
    elif args.command in {"serve", "run"}:
        import uvicorn

        uvicorn.run("snapims.web.app:app", host=args.host, port=args.port, reload=False)
    elif args.command == "preview":
        batch = parse_batch(Path(args.source), batch_name=args.batch_name)
        print(
            f"items={len(batch.items)} product_photos={batch.photo_count} commands={len(batch.commands)} warnings={len(batch.warnings)}"
        )
    elif args.command == "import":
        result = process_batch(Path(args.source), paths=paths, batch_name=args.batch_name)
        print(
            f"batch_id={result.batch_id} items={result.item_count} duplicate={str(result.duplicate).lower()}"
        )
    elif args.command == "demo":
        create_demo_batch(Path(args.folder), item_count=args.items)
        print(Path(args.folder).resolve())
    elif args.command == "integrity":
        db.initialize(paths.db_file, paths=paths)
        with db.connect(paths.db_file) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        print(f"integrity_check={result}")


if __name__ == "__main__":
    main()
