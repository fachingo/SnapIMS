from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse
import urllib.request
from pathlib import Path

from snapims import __version__
from snapims.config import SnapIMSConfig


class ServiceManager:
    def __init__(self, config: SnapIMSConfig | None = None) -> None:
        self.config = (config or SnapIMSConfig.load()).ensure()

    def _pid(self, name: str) -> Path:
        return self.config.pid_dir / f"{name}.pid"

    def _read_pid(self, name: str) -> int | None:
        try:
            pid = int(self._pid(name).read_text().strip())
            os.kill(pid, 0)
            return pid
        except (OSError, ValueError):
            try:
                self._pid(name).unlink(missing_ok=True)
            except OSError:
                pass
            return None

    def _app_python(self) -> Path:
        venv_python = self.config.project_path / ".venv" / "bin" / "python"
        return venv_python if venv_python.exists() else Path(sys.executable)

    def start_app(self) -> int:
        if pid := self._read_pid("app"):
            return pid
        if not self.config.project_path.is_dir():
            raise RuntimeError(f"SnapIMS project path does not exist: {self.config.project_path}")
        log = self.config.app_log.open("a", encoding="utf-8")
        process = subprocess.Popen(
            [
                str(self._app_python()),
                "-m",
                "uvicorn",
                "snapims.web.app:app",
                "--host",
                self.config.host,
                "--port",
                str(self.config.port),
            ],
            cwd=self.config.project_path,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self._pid("app").write_text(str(process.pid))
        return process.pid

    def tunnel_problem(self) -> str:
        if not shutil.which(self.config.cloudflared_bin):
            return f"cloudflared executable not found: {self.config.cloudflared_bin}"
        if not self.config.tunnel_config.exists():
            return f"Cloudflare tunnel config not found: {self.config.tunnel_config}"
        return ""

    def _systemctl(self, *args: str, allow_sudo: bool = False) -> subprocess.CompletedProcess[str]:
        command = ["systemctl", *args]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        if (
            result.returncode != 0
            and allow_sudo
            and os.geteuid() != 0
            and sys.stdin.isatty()
            and shutil.which("sudo")
        ):
            return subprocess.run(
                ["sudo", *command],
                text=True,
                capture_output=True,
                check=False,
            )
        return result

    def _service_active(self, service: str) -> bool:
        if not service or not shutil.which("systemctl"):
            return False
        return self._systemctl("is-active", "--quiet", service).returncode == 0

    def _service_problem(self, service: str) -> str:
        if not service:
            return "service name is not configured"
        if not shutil.which("systemctl"):
            return "systemctl executable not found"
        result = self._systemctl("status", "--no-pager", service)
        if result.returncode == 0:
            return ""
        detail = (result.stderr or result.stdout).strip().splitlines()
        return detail[0] if detail else f"{service} is not available"

    def _start_system_service(self, service: str) -> bool:
        if self._service_active(service):
            return True
        return self._systemctl("start", service, allow_sudo=True).returncode == 0

    def _stop_system_service(self, service: str) -> bool:
        if not self._service_active(service):
            return True
        return self._systemctl("stop", service, allow_sudo=True).returncode == 0

    def _tcp_open(self, host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            return False

    def _path_state(self, path: Path) -> tuple[bool, str]:
        try:
            return path.exists(), ""
        except OSError as exc:
            detail = exc.strerror or str(exc)
            return False, f"cannot access {path}: {detail}"

    def _path_exists(self, path: Path) -> bool:
        return self._path_state(path)[0]

    def _tomcat_unit_installed(self) -> bool:
        return (
            self._path_exists(Path(f"/etc/systemd/system/{self.config.tomcat_service}.service"))
            or self._path_exists(Path(f"/lib/systemd/system/{self.config.tomcat_service}.service"))
            or self._path_exists(Path(f"/usr/lib/systemd/system/{self.config.tomcat_service}.service"))
        )

    def guacamole_installed(self) -> bool:
        return bool(shutil.which("guacd") and self._tomcat_unit_installed())

    def guacamole_health(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.config.guacamole_url}/", timeout=3) as response:
                if response.status != 200:
                    return False
                body = response.read(200_000).lower()
                content_type = response.headers.get("content-type", "").lower()
                return (
                    b"guacamole" in body
                    or b"ng-app=\"index\"" in body
                    or ("text/html" in content_type and "/guacamole" in self.config.guacamole_url)
                )
        except OSError:
            return False

    def wait_for_guacamole(self, timeout: float = 30) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.guacamole_health():
                return True
            time.sleep(0.5)
        return False

    def start_guacamole(self) -> bool:
        if not self.config.manage_guacamole_services or not self.guacamole_installed():
            return False
        ok = True
        ok = self._start_system_service(self.config.guacd_service) and ok
        ok = self._start_system_service(self.config.xrdp_service) and ok
        ok = self._start_system_service(self.config.tomcat_service) and ok
        return ok and self.wait_for_guacamole()

    def stop_guacamole(self) -> bool:
        if not self.config.manage_guacamole_services or not self.guacamole_installed():
            return False
        ok = True
        ok = self._stop_system_service(self.config.tomcat_service) and ok
        ok = self._stop_system_service(self.config.guacd_service) and ok
        return ok

    def guacamole_status(self) -> dict[str, object]:
        parsed = urlparse(self.config.guacamole_url)
        http_host = parsed.hostname or "127.0.0.1"
        http_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        installed = self.guacamole_installed()
        guacd_active = self._service_active(self.config.guacd_service)
        tomcat_active = self._service_active(self.config.tomcat_service)
        xrdp_active = self._service_active(self.config.xrdp_service)
        config_path = self.config.guacamole_config_dir / "guacamole.properties"
        user_mapping_path = self.config.guacamole_config_dir / "user-mapping.xml"
        config_present, config_problem = self._path_state(config_path)
        user_mapping_present, user_mapping_problem = self._path_state(user_mapping_path)
        web = self.guacamole_health()
        problems: list[str] = []
        warnings: list[str] = []
        if not shutil.which("guacd"):
            problems.append("guacd executable not found")
        if config_problem:
            warnings.append(config_problem)
        elif not config_present:
            warnings.append(f"Guacamole config not found: {config_path}")
        if user_mapping_problem:
            warnings.append(user_mapping_problem)
        elif not user_mapping_present:
            warnings.append(f"Guacamole user mapping not found: {user_mapping_path}")
        if installed and not guacd_active:
            problems.append(self._service_problem(self.config.guacd_service))
        if installed and not tomcat_active:
            problems.append(self._service_problem(self.config.tomcat_service))
        if installed and not xrdp_active:
            problems.append(self._service_problem(self.config.xrdp_service))
        if installed and not web:
            problems.append(f"Guacamole login page unavailable at {self.config.guacamole_url}/")
        available = installed and guacd_active and tomcat_active and web
        return {
            "installed": installed,
            "available": available,
            "web": web,
            "url": self.config.guacamole_url,
            "public_url": self.config.guacamole_public_url,
            "config_accessible": not (config_problem or user_mapping_problem),
            "config_present": config_present,
            "user_mapping_present": user_mapping_present,
            "guacd_service": self.config.guacd_service,
            "guacd_service_active": guacd_active,
            "guacd_port_open": self._tcp_open(self.config.guacd_host, self.config.guacd_port),
            "tomcat_service": self.config.tomcat_service,
            "tomcat_service_active": tomcat_active,
            "http_port_open": self._tcp_open(http_host, http_port),
            "xrdp_service": self.config.xrdp_service,
            "xrdp_service_active": xrdp_active,
            "rdp_port_open": self._tcp_open("127.0.0.1", 3389),
            "ssh_port_open": self._tcp_open("127.0.0.1", 22),
            "problem": "; ".join(problem for problem in problems if problem),
            "warning": "; ".join(warning for warning in warnings if warning),
        }

    def start_tunnel(self) -> int | None:
        if self.tunnel_problem():
            return None
        if pid := self._read_pid("tunnel"):
            return pid
        log = self.config.tunnel_log.open("a", encoding="utf-8")
        command = [
            self.config.cloudflared_bin,
            "tunnel",
            "--config",
            str(self.config.tunnel_config),
            "run",
        ]
        if self.config.tunnel_name:
            command.append(self.config.tunnel_name)
        process = subprocess.Popen(
            command,
            cwd=self.config.project_path,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self._pid("tunnel").write_text(str(process.pid))
        return process.pid

    def stop(self, name: str) -> bool:
        pid = self._read_pid(name)
        if not pid:
            return False
        os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            if not self._read_pid(name):
                return True
            time.sleep(0.1)
        os.kill(pid, signal.SIGKILL)
        self._pid(name).unlink(missing_ok=True)
        return True

    def health(self) -> bool:
        try:
            with urllib.request.urlopen(
                f"http://{self.config.host}:{self.config.port}/health", timeout=2
            ) as response:
                return response.status == 200
        except OSError:
            return False

    def wait_for_health(self, timeout: float = 15) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.health():
                return True
            time.sleep(0.25)
        return False

    def status(self) -> dict[str, object]:
        guacamole = self.guacamole_status()
        return {
            "app": bool(self._read_pid("app")),
            "health": self.health(),
            "tunnel": bool(self._read_pid("tunnel")),
            "tunnel_problem": self.tunnel_problem(),
            "guacamole": guacamole,
            "port": self.config.port,
            "version": __version__,
        }
