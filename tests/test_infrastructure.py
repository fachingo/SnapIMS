from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from snapims import __version__
from snapims import cli
from snapims.auth import generate_secret, hash_password
from snapims.config import SnapIMSConfig
from snapims.manager import ServiceManager
from snapims.web.app import app

ROOT = Path(__file__).resolve().parents[1]


def _csrf(response_text: str) -> str:
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', response_text)
    assert match, response_text
    return match.group(1)


def _isolated_env(data_dir: Path, *, auth: bool = False) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "SNAPIMS_PROJECT_PATH": str(ROOT),
            "SNAPIMS_DATA_DIR": str(data_dir),
            "SNAPIMS_ENABLE_TEST_PROVIDERS": "true",
            "SNAPIMS_SKIP_DOTENV": "1",
            "OPENAI_API_KEY": "",
            "CLOUDFLARE_TUNNEL_CONFIG": str(data_dir / "missing-cloudflared.yml"),
            "SNAPIMS_MANAGE_GUACAMOLE_SERVICES": "false",
        }
    )
    if not auth:
        env["SNAPIMS_AUTH_SECRET"] = ""
        env["SNAPIMS_ADMIN_PASSWORD_HASH"] = ""
    return env


def test_application_cli_config_manager_and_auth_imports() -> None:
    import snapims.auth
    import snapims.cli
    import snapims.config
    import snapims.manager
    import snapims.web.app

    assert snapims.auth.COOKIE == "snapims_session"
    assert snapims.cli.build_parser().prog == "snapims"
    assert snapims.config.default_project_path() == ROOT
    assert snapims.manager.ServiceManager
    assert snapims.web.app.app.title == "SnapIMS"


def test_configuration_loads_project_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project"
    data = tmp_path / "data"
    project.mkdir()
    (project / ".env").write_text(
        f"SNAPIMS_DATA_DIR={data}\nSNAPIMS_PORT=8877\nSNAPIMS_AUTH_SECRET=\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SNAPIMS_PROJECT_PATH", str(project))
    monkeypatch.delenv("SNAPIMS_DATA_DIR", raising=False)
    monkeypatch.delenv("SNAPIMS_PORT", raising=False)
    monkeypatch.setenv("SNAPIMS_ADMIN_PASSWORD_HASH", "")

    config = SnapIMSConfig.load()

    assert config.project_path == project
    assert config.data.root == data
    assert config.port == 8877


def test_fastapi_startup_and_health(data_paths, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SNAPIMS_AUTH_SECRET", "")
    monkeypatch.setenv("SNAPIMS_ADMIN_PASSWORD_HASH", "")
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["version"] == __version__
    assert response.json()["status"] == "ok"
    assert response.json()["components"]["inventory_database"]["state"] == "healthy"


def test_health_returns_503_when_required_schema_is_degraded(
    data_paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SNAPIMS_AUTH_SECRET", "")
    monkeypatch.setenv("SNAPIMS_ADMIN_PASSWORD_HASH", "")
    with TestClient(app) as client:
        monkeypatch.setattr(
            "snapims.web.app.db.schema_manifest_report",
            lambda _connection: {
                "ok": False,
                "problems": ["Missing table: items"],
                "schema_version": 8,
            },
        )
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["components"]["inventory_database"]["state"] == "degraded"


def test_authentication_login_logout_flow(data_paths, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SNAPIMS_AUTH_SECRET", generate_secret())
    monkeypatch.setenv("SNAPIMS_ADMIN_USERNAME", "operator")
    monkeypatch.setenv("SNAPIMS_ADMIN_PASSWORD_HASH", hash_password("correct horse battery"))

    with TestClient(app) as client:
        blocked = client.get("/", follow_redirects=False)
        assert blocked.status_code == 303
        assert blocked.headers["location"] == "/login"
        anonymous_csrf = _csrf(client.get("/login").text)

        bad_login = client.post(
            "/login",
            data={
                "username": "operator",
                "password": "wrong",
                "csrf_token": anonymous_csrf,
            },
            follow_redirects=False,
        )
        assert bad_login.status_code == 303
        assert "Invalid%20credentials" in bad_login.headers["location"]

        good_login = client.post(
            "/login",
            data={
                "username": "operator",
                "password": "correct horse battery",
                "csrf_token": anonymous_csrf,
            },
            follow_redirects=False,
        )
        assert good_login.status_code == 303
        assert good_login.headers["location"] == "/"

        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert "SnapIMS" in dashboard.text
        session_csrf = _csrf(dashboard.text)

        logout = client.post(
            "/logout",
            data={"csrf_token": session_csrf},
            follow_redirects=False,
        )
        assert logout.status_code == 303
        assert logout.headers["location"] == "/login"


def test_csrf_origin_session_binding_and_security_headers(
    data_paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SNAPIMS_AUTH_SECRET", generate_secret())
    monkeypatch.setenv("SNAPIMS_ADMIN_USERNAME", "security-operator")
    monkeypatch.setenv(
        "SNAPIMS_ADMIN_PASSWORD_HASH", hash_password("correct horse battery")
    )

    with TestClient(app) as first, TestClient(app) as second:
        login_page = first.get("/login")
        token = _csrf(login_page.text)
        assert login_page.headers["cache-control"] == "no-store"
        assert "default-src 'self'" in login_page.headers["content-security-policy"]
        assert login_page.headers["x-content-type-options"] == "nosniff"
        assert login_page.headers["x-frame-options"] == "DENY"

        missing = first.post(
            "/login",
            data={"username": "security-operator", "password": "correct horse battery"},
        )
        assert missing.status_code == 403

        wrong = first.post(
            "/login",
            data={
                "username": "security-operator",
                "password": "correct horse battery",
                "csrf_token": "wrong-token",
            },
        )
        assert wrong.status_code == 403

        cross_origin = first.post(
            "/login",
            data={
                "username": "security-operator",
                "password": "correct horse battery",
                "csrf_token": token,
            },
            headers={"origin": "https://evil.example"},
        )
        assert cross_origin.status_code == 403

        signed_in = first.post(
            "/login",
            data={
                "username": "security-operator",
                "password": "correct horse battery",
                "csrf_token": token,
            },
            follow_redirects=False,
        )
        assert signed_in.status_code == 303
        authenticated_token = _csrf(first.get("/").text)

        no_token = first.post("/settings", data={"incoming_folder": str(data_paths.incoming)})
        assert no_token.status_code == 403

        second_token = _csrf(second.get("/login").text)
        second_login = second.post(
            "/login",
            data={
                "username": "security-operator",
                "password": "correct horse battery",
                "csrf_token": second_token,
            },
            follow_redirects=False,
        )
        assert second_login.status_code == 303
        wrong_session = second.post(
            "/logout",
            data={"csrf_token": authenticated_token},
            follow_redirects=False,
        )
        assert wrong_session.status_code == 403

        monkeypatch.setenv(
            "SNAPIMS_ADMIN_PASSWORD_HASH", hash_password("rotated correct password")
        )
        revoked = first.get("/", follow_redirects=False)
        assert revoked.status_code == 303
        assert revoked.headers["location"] == "/login"


def test_login_backoff_is_bounded_and_generic(
    data_paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SNAPIMS_AUTH_SECRET", generate_secret())
    monkeypatch.setenv("SNAPIMS_ADMIN_USERNAME", "throttle-operator")
    monkeypatch.setenv(
        "SNAPIMS_ADMIN_PASSWORD_HASH", hash_password("correct horse battery")
    )
    with TestClient(app) as client:
        token = _csrf(client.get("/login").text)
        for _ in range(3):
            response = client.post(
                "/login",
                data={
                    "username": "throttle-operator",
                    "password": "wrong",
                    "csrf_token": token,
                },
                follow_redirects=False,
            )
            assert response.status_code == 303
            assert "Invalid%20credentials" in response.headers["location"]
        throttled = client.post(
            "/login",
            data={
                "username": "throttle-operator",
                "password": "wrong",
                "csrf_token": token,
            },
            follow_redirects=False,
        )
        assert throttled.status_code == 303
        assert int(throttled.headers["retry-after"]) <= 60
        assert "Invalid%20credentials" in throttled.headers["location"]


def test_partial_authentication_configuration_fails_closed(
    data_paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SNAPIMS_AUTH_SECRET", generate_secret())
    monkeypatch.setenv("SNAPIMS_ADMIN_PASSWORD_HASH", "")

    with TestClient(app) as client:
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].startswith("/login")
        login_page = client.get("/login")
    assert login_page.status_code == 200
    assert "SNAPIMS_ADMIN_PASSWORD_HASH must be set" in login_page.text


def test_cli_core_commands_run(tmp_path: Path) -> None:
    env = _isolated_env(tmp_path / "data")
    commands = [
        ["--help"],
        ["version"],
        ["doctor"],
        ["status"],
        ["update", "--check"],
        ["tunnel", "status"],
        ["auth", "generate-secret"],
    ]
    for command in commands:
        result = subprocess.run(
            [sys.executable, "-m", "snapims.cli", "--data-dir", str(tmp_path / "data"), *command],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr or result.stdout


def test_doctor_returns_nonzero_when_required_checks_fail(tmp_path: Path) -> None:
    env = _isolated_env(tmp_path / "data")
    env["SNAPIMS_MANAGE_GUACAMOLE_SERVICES"] = "true"
    env["SNAPIMS_GUACAMOLE_CONFIG_DIR"] = str(tmp_path / "missing-guacamole")
    env["PATH"] = str(tmp_path / "empty-bin")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "snapims.cli",
            "--data-dir",
            str(tmp_path / "data"),
            "doctor",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "required checks failed" in result.stdout


def test_update_requires_explicit_mode() -> None:
    parser = cli.build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["update"])
    assert exc.value.code == 2
    assert parser.parse_args(["update", "--check"]).check is True
    assert parser.parse_args(["update", "--apply"]).apply is True


def test_update_apply_refuses_dirty_tree_before_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SNAPIMS_PROJECT_PATH", str(ROOT))
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SNAPIMS_AUTH_SECRET", "")
    monkeypatch.setenv("SNAPIMS_ADMIN_PASSWORD_HASH", "")
    config = SnapIMSConfig.load()
    report = {
        "branch": "feature/test",
        "detached": False,
        "upstream": "origin/feature/test",
        "dirty": True,
        "dirty_count": 1,
        "ahead": 0,
        "behind": 1,
        "incoming": ["abc123 incoming"],
        "current_version": "0.9.0",
        "target_version": "0.10.0",
        "current_inventory_schema": 8,
        "target_inventory_schema": 9,
        "current_catalog_schema": 1,
        "target_catalog_schema": 1,
        "migration_need": True,
        "backup_need": True,
        "restart_impact": "test",
    }
    monkeypatch.setattr(cli, "update_report", lambda _config: report)
    monkeypatch.setattr(
        cli.db,
        "backup_database",
        lambda *_args, **_kwargs: pytest.fail("backup must not run"),
    )
    with pytest.raises(SystemExit, match="working tree is dirty"):
        cli._apply_update(config, ServiceManager(config), allow_dirty=False)


def test_auth_hash_password_cli_reads_stdin(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "snapims.cli",
            "auth",
            "hash-password",
            "--password-stdin",
        ],
        cwd=ROOT,
        env=_isolated_env(tmp_path / "data"),
        input="correct horse battery\n",
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("scrypt$")


def test_service_manager_status_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SNAPIMS_PROJECT_PATH", str(ROOT))
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SNAPIMS_AUTH_SECRET", "")
    monkeypatch.setenv("SNAPIMS_ADMIN_PASSWORD_HASH", "")
    monkeypatch.setenv("CLOUDFLARE_TUNNEL_CONFIG", str(tmp_path / "missing-cloudflared.yml"))
    monkeypatch.setenv("SNAPIMS_GUACAMOLE_CONFIG_DIR", str(tmp_path / "missing-guacamole"))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    config = SnapIMSConfig.load()
    manager = ServiceManager(config)
    status = manager.status()
    assert status["version"] == __version__
    assert "tunnel_problem" in status
    assert "guacamole" in status
    assert status["guacamole"]["available"] is False
    assert "guacd" in status["guacamole"]["problem"]


def test_guacamole_status_reports_inaccessible_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_guacd = fake_bin / "guacd"
    fake_guacd.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_guacd.chmod(0o755)
    config_dir = tmp_path / "guacamole"
    config_dir.mkdir()

    monkeypatch.setenv("SNAPIMS_PROJECT_PATH", str(ROOT))
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SNAPIMS_AUTH_SECRET", "")
    monkeypatch.setenv("SNAPIMS_ADMIN_PASSWORD_HASH", "")
    monkeypatch.setenv("CLOUDFLARE_TUNNEL_CONFIG", str(tmp_path / "missing-cloudflared.yml"))
    monkeypatch.setenv("SNAPIMS_GUACAMOLE_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("PATH", str(fake_bin))

    original_exists = Path.exists

    def exists_with_permission_error(path: Path) -> bool:
        if path in {config_dir / "guacamole.properties", config_dir / "user-mapping.xml"}:
            raise PermissionError("Permission denied")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", exists_with_permission_error)

    status = ServiceManager(SnapIMSConfig.load()).guacamole_status()

    assert status["available"] is False
    assert status["config_accessible"] is False
    assert "cannot access" in status["warning"]
    assert "Permission denied" in status["warning"]
    assert "Permission denied" not in status["problem"]


def test_guacamole_health_accepts_lowercase_guacamole_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Response:
        status = 200
        headers = {"content-type": "text/html"}

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return b'<html><link rel="stylesheet" href="app.guacamole.css"></html>'

    monkeypatch.setenv("SNAPIMS_PROJECT_PATH", str(ROOT))
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SNAPIMS_AUTH_SECRET", "")
    monkeypatch.setenv("SNAPIMS_ADMIN_PASSWORD_HASH", "")
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())

    assert ServiceManager(SnapIMSConfig.load()).guacamole_health() is True


def test_guacamole_health_rejects_generic_html(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Response:
        status = 200
        headers = {"content-type": "text/html"}

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return b"<html><title>Generic reverse proxy</title></html>"

    monkeypatch.setenv("SNAPIMS_PROJECT_PATH", str(ROOT))
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SNAPIMS_AUTH_SECRET", "")
    monkeypatch.setenv("SNAPIMS_ADMIN_PASSWORD_HASH", "")
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())

    assert ServiceManager(SnapIMSConfig.load()).guacamole_health() is False


def test_pid_file_cannot_target_unrelated_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SNAPIMS_PROJECT_PATH", str(ROOT))
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SNAPIMS_AUTH_SECRET", "")
    monkeypatch.setenv("SNAPIMS_ADMIN_PASSWORD_HASH", "")
    manager = ServiceManager(SnapIMSConfig.load())
    manager._pid("app").write_text(str(os.getpid()), encoding="utf-8")

    assert manager._read_pid("app") is None
    assert not manager._pid("app").exists()


def test_tunnel_process_without_connector_evidence_is_not_healthy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SNAPIMS_PROJECT_PATH", str(ROOT))
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SNAPIMS_AUTH_SECRET", "")
    monkeypatch.setenv("SNAPIMS_ADMIN_PASSWORD_HASH", "")
    manager = ServiceManager(SnapIMSConfig.load())
    manager.config.tunnel_log.parent.mkdir(parents=True, exist_ok=True)
    manager.config.tunnel_log.write_text("starting cloudflared\n", encoding="utf-8")
    monkeypatch.setattr(manager, "_read_pid", lambda name: 123 if name == "tunnel" else None)
    monkeypatch.setattr(manager, "guacamole_status", lambda: {})
    monkeypatch.setattr(manager, "health_details", lambda: {"ok": True})
    monkeypatch.setattr(manager, "health", lambda: True)

    status = manager.status()

    assert status["tunnel_process"] is True
    assert status["tunnel"] is False
    assert "no connector registration evidence" in str(
        status["tunnel_connector_problem"]
    )


def test_guacamole_installer_scripts_are_present_and_valid() -> None:
    scripts = [
        ROOT / "scripts" / "install_guacamole.sh",
        ROOT / "scripts" / "configure_cloudflare_guacamole.sh",
    ]
    for script in scripts:
        assert script.is_file()
        assert os.access(script, os.X_OK)
        result = subprocess.run(
            ["bash", "-n", str(script)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    installer = (ROOT / "scripts" / "install_guacamole.sh").read_text(encoding="utf-8")
    assert "LISTEN_ADDRESS=${GUACD_HOST}" in installer
    assert "LISTEN_PORT=${GUACD_PORT}" in installer
    assert "SupplementaryGroups=${SERVICE_GROUP}" in installer
    assert "$GUACAMOLE_HOME/guacd.conf" in installer


def test_launcher_installer_uses_script_location_and_updates_path_once(tmp_path: Path) -> None:
    if not (ROOT / ".venv" / "bin" / "python").exists():
        pytest.skip("launcher installer requires the SnapIMS project .venv")

    home = tmp_path / "home"
    home.mkdir()
    env = _isolated_env(tmp_path / "data")
    env.update({"HOME": str(home), "SHELL": "/bin/bash", "PATH": "/usr/bin:/bin"})
    env.pop("SNAPIMS_PROJECT_PATH", None)

    for _ in range(2):
        result = subprocess.run(
            ["bash", str(ROOT / "scripts" / "install_launcher.sh")],
            cwd=tmp_path,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr or result.stdout
        assert "Validation: PASS" in result.stdout

    launcher = home / ".local" / "bin" / "snapims"
    assert launcher.is_file()
    assert os.access(launcher, os.X_OK)
    assert launcher.read_text(encoding="utf-8").count(str(ROOT)) == 1
    assert (home / ".bashrc").read_text(encoding="utf-8").count("SnapIMS launcher PATH") == 1

    run_env = env | {"PATH": f"{launcher.parent}:{env['PATH']}"}
    result = subprocess.run(
        ["snapims", "version"],
        cwd=tmp_path,
        env=run_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == __version__
