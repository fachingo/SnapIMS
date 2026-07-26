from __future__ import annotations

import argparse
import getpass
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from snapims import __version__, db
from snapims.config import SnapIMSConfig
from snapims.demo import create_demo_batch
from snapims.manager import ServiceManager
from snapims.pipeline import parse_batch
from snapims.processor import process_batch
from snapims.auth import (
    authentication_enabled,
    authentication_problem,
    generate_secret,
    hash_password,
)


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
            return connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    except Exception:
        return False


def _print_service_urls(config: SnapIMSConfig) -> None:
    print(f"SnapIMS local URL: http://{config.host}:{config.port}")
    print(f"Guacamole local URL: {config.guacamole_url}/")
    if config.guacamole_public_url:
        print(f"Guacamole public URL: {config.guacamole_public_url}")


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
        "logs",
        "doctor",
        "shell",
        "update",
        "version",
    ):
        sub.add_parser(command)
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
        guacamole = status["guacamole"]
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
            f"Version .............. {status['version']}"
        )
        if status["tunnel_problem"] and not status["tunnel"]:
            print(f"Cloudflare detail .... {status['tunnel_problem']}")
        if guacamole["problem"]:
            print(f"Guacamole detail ..... {guacamole['problem']}")
        if guacamole["warning"]:
            print(f"Guacamole warning .... {guacamole['warning']}")
        if auth_detail and auth_state != "PASS":
            print(f"Authentication detail  {auth_detail}")
    elif args.command == "logs":
        subprocess.run(["tail", "-n", "100", "-f", str(config.app_log)], check=False)
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
            for name in ("fastapi", "uvicorn", "cv2", "openai", "itsdangerous", "dotenv")
        )
        port_free = manager.health() or not any(
            manager._read_pid(name) for name in ("app", "tunnel")
        )
        auth_problem = authentication_problem(config.auth_secret, config.admin_password_hash)
        required_checks = [
            ("Python", sys.version_info >= (3, 12)),
            ("venv", (config.project_path / ".venv" / "bin" / "python").exists()),
            ("dependencies", dependencies),
            ("SQLite", _database_ok(config)),
            ("logs directory", config.data.logs.is_dir()),
            ("config", config.project_path.is_dir()),
            ("write permissions", os.access(config.data.root, os.W_OK)),
            ("port availability", port_free),
        ]
        for name, ok in required_checks:
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if authentication_enabled(config.auth_secret, config.admin_password_hash):
            print("PASS  authentication")
        elif auth_problem:
            print(f"FAIL  authentication - {auth_problem}")
        else:
            print("WARN  authentication disabled")
        print("PASS  OpenAI API key" if config.openai_api_key else "WARN  OpenAI API key not configured")
        print(
            "PASS  Cloudflare tunnel"
            if not manager.tunnel_problem()
            else f"WARN  Cloudflare tunnel - {manager.tunnel_problem()}"
        )
        guacamole = manager.guacamole_status()
        print(
            "PASS  Guacamole web application"
            if guacamole["web"]
            else f"FAIL  Guacamole web application - {guacamole['problem'] or 'not installed'}"
        )
        if guacamole["warning"]:
            print(f"WARN  Guacamole config - {guacamole['warning']}")
        print(
            "PASS  guacd service"
            if guacamole["guacd_service_active"]
            else f"FAIL  guacd service - {guacamole['guacd_service']} is not running"
        )
        print(
            "PASS  Tomcat service"
            if guacamole["tomcat_service_active"]
            else f"FAIL  Tomcat service - {guacamole['tomcat_service']} is not running"
        )
        print(
            "PASS  Guacamole HTTP port"
            if guacamole["http_port_open"]
            else "FAIL  Guacamole HTTP port is not listening"
        )
        print(
            "PASS  guacd port 4822"
            if guacamole["guacd_port_open"]
            else "FAIL  guacd port 4822 is not listening"
        )
        print(
            "PASS  RDP desktop backend"
            if guacamole["rdp_port_open"]
            else "FAIL  RDP desktop backend is not listening on 127.0.0.1:3389"
        )
        print(
            "PASS  SSH backend"
            if guacamole["ssh_port_open"]
            else "FAIL  SSH backend is not listening on 127.0.0.1:22"
        )
    elif args.command == "shell":
        os.execv(
            "/bin/bash",
            [
                "bash",
                "-i",
                "-c",
                f"cd {config.project_path} && source .venv/bin/activate && exec bash",
            ],
        )
    elif args.command == "update":
        subprocess.check_call(["git", "pull"], cwd=config.project_path)
        _ensure_venv(config)
        manager.stop("tunnel")
        manager.stop("app")
        manager.start_app()
        manager.start_tunnel()
        print("SnapIMS updated and restarted")
    elif args.command == "serve":
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
        print(
            f"integrity_check={db.connect(paths.db_file).execute('PRAGMA integrity_check').fetchone()[0]}"
        )


if __name__ == "__main__":
    main()
