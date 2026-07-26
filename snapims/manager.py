from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
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
            self._pid(name).unlink(missing_ok=True)
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
        return {
            "app": bool(self._read_pid("app")),
            "health": self.health(),
            "tunnel": bool(self._read_pid("tunnel")),
            "tunnel_problem": self.tunnel_problem(),
            "port": self.config.port,
            "version": __version__,
        }
