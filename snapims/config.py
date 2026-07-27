from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


def default_project_path() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_dotenv(project: Path) -> None:
    if os.getenv("SNAPIMS_SKIP_DOTENV"):
        return
    env_file = project / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_file, override=False)


@dataclass(frozen=True, slots=True)
class DataPaths:
    root: Path
    incoming: Path
    originals: Path
    processed: Path
    database: Path
    exports: Path
    backups: Path
    logs: Path
    db_file: Path
    catalog_db_file: Path

    @classmethod
    def from_root(cls, root: str | Path | None = None) -> DataPaths:
        configured = root or os.getenv("SNAPIMS_DATA_DIR") or "~/SnapIMS-data"
        base = Path(configured).expanduser().resolve()
        return cls(
            root=base,
            incoming=base / "incoming",
            originals=base / "originals",
            processed=base / "processed",
            database=base / "database",
            exports=base / "exports",
            backups=base / "backups",
            logs=base / "logs",
            db_file=base / "database" / "inventory.sqlite3",
            catalog_db_file=base / "database" / "movie_catalog.sqlite3",
        )

    def ensure(self) -> DataPaths:
        for folder in (
            self.root,
            self.incoming,
            self.originals,
            self.processed,
            self.database,
            self.exports,
            self.backups,
            self.logs,
        ):
            folder.mkdir(parents=True, exist_ok=True)
        return self


@dataclass(frozen=True, slots=True)
class SnapIMSConfig:
    """Central operator configuration, sourced from environment variables."""

    project_path: Path
    host: str
    port: int
    data: DataPaths
    pid_dir: Path
    app_log: Path
    tunnel_log: Path
    cloudflared_bin: str
    tunnel_config: Path
    tunnel_name: str
    guacamole_url: str
    guacamole_public_url: str
    guacd_host: str
    guacd_port: int
    guacd_service: str
    tomcat_service: str
    xrdp_service: str
    guacamole_config_dir: Path
    manage_guacamole_services: bool
    auth_secret: str
    admin_username: str
    admin_password_hash: str
    openai_api_key: str
    public_url: str
    allowed_hosts: tuple[str, ...]
    session_generation: str

    @classmethod
    def load(cls) -> "SnapIMSConfig":
        initial_project = Path(
            os.getenv("SNAPIMS_PROJECT_PATH") or default_project_path()
        ).expanduser().resolve()
        _load_dotenv(initial_project)
        configured_project = os.getenv("SNAPIMS_PROJECT_PATH", "").strip()
        project = (
            Path(configured_project).expanduser().resolve()
            if configured_project
            else initial_project
        )
        if project != initial_project:
            _load_dotenv(project)
        data = DataPaths.from_root()
        data.ensure()
        logs = data.logs
        public_url = os.getenv("SNAPIMS_PUBLIC_URL", "https://ims.canadavhs.ca").rstrip("/")
        configured_hosts = {
            value.strip().casefold()
            for value in os.getenv(
                "SNAPIMS_ALLOWED_HOSTS",
                "127.0.0.1,localhost,testserver,ims.canadavhs.ca",
            ).split(",")
            if value.strip()
        }
        if hostname := urlparse(public_url).hostname:
            configured_hosts.add(hostname.casefold())
        return cls(
            project_path=project,
            host=os.getenv("SNAPIMS_HOST", "127.0.0.1"),
            port=int(os.getenv("SNAPIMS_PORT", "8767")),
            data=data,
            pid_dir=logs / "pids",
            app_log=logs / "snapims.log",
            tunnel_log=logs / "cloudflared.log",
            cloudflared_bin=os.getenv("SNAPIMS_CLOUDFLARED_BIN", "cloudflared"),
            tunnel_config=Path(
                os.getenv("CLOUDFLARE_TUNNEL_CONFIG", "~/.cloudflared/config.yml")
            ).expanduser(),
            tunnel_name=os.getenv("CLOUDFLARE_TUNNEL_NAME", ""),
            guacamole_url=os.getenv(
                "SNAPIMS_GUACAMOLE_URL", "http://127.0.0.1:8080/guacamole"
            ).rstrip("/"),
            guacamole_public_url=os.getenv("SNAPIMS_GUACAMOLE_PUBLIC_URL", "").rstrip("/"),
            guacd_host=os.getenv("SNAPIMS_GUACD_HOST", "127.0.0.1"),
            guacd_port=int(os.getenv("SNAPIMS_GUACD_PORT", "4822")),
            guacd_service=os.getenv("SNAPIMS_GUACD_SERVICE", "guacd"),
            tomcat_service=os.getenv("SNAPIMS_TOMCAT_SERVICE", "snapims-guacamole-tomcat"),
            xrdp_service=os.getenv("SNAPIMS_XRDP_SERVICE", "xrdp"),
            guacamole_config_dir=Path(
                os.getenv("SNAPIMS_GUACAMOLE_CONFIG_DIR", "/etc/guacamole")
            ).expanduser(),
            manage_guacamole_services=os.getenv(
                "SNAPIMS_MANAGE_GUACAMOLE_SERVICES", "true"
            )
            .strip()
            .casefold()
            not in {"false", "0", "no"},
            auth_secret=os.getenv("SNAPIMS_AUTH_SECRET", ""),
            admin_username=os.getenv("SNAPIMS_ADMIN_USERNAME", "admin"),
            admin_password_hash=os.getenv("SNAPIMS_ADMIN_PASSWORD_HASH", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            public_url=public_url,
            allowed_hosts=tuple(sorted(configured_hosts)),
            session_generation=os.getenv(
                "SNAPIMS_SESSION_GENERATION", "1"
            ).strip()
            or "1",
        )

    def ensure(self) -> "SnapIMSConfig":
        self.data.ensure()
        self.pid_dir.mkdir(parents=True, exist_ok=True)
        return self


@dataclass(frozen=True, slots=True)
class ShopifyConfig:
    store_domain: str
    access_token: str
    location_id: str
    api_version: str = "2026-07"
    draft_only: bool = True

    @classmethod
    def from_env(cls) -> ShopifyConfig:
        return cls(
            store_domain=os.getenv("SHOPIFY_STORE_DOMAIN", "").strip(),
            access_token=os.getenv("SHOPIFY_ADMIN_ACCESS_TOKEN", "").strip(),
            location_id=os.getenv("SHOPIFY_LOCATION_ID", "").strip(),
            api_version=os.getenv("SHOPIFY_API_VERSION", "2026-07").strip(),
            draft_only=os.getenv("SHOPIFY_DRAFT_ONLY", "true").strip().casefold()
            not in {"false", "0", "no"},
        )

    def problems(self) -> list[str]:
        problems: list[str] = []
        if not self.store_domain or not self.store_domain.endswith(".myshopify.com"):
            problems.append("SHOPIFY_STORE_DOMAIN must end in .myshopify.com")
        if not self.access_token:
            problems.append("SHOPIFY_ADMIN_ACCESS_TOKEN is not configured")
        if not self.location_id.startswith("gid://shopify/Location/"):
            problems.append("SHOPIFY_LOCATION_ID is not a Shopify Location GID")
        if not re.fullmatch(r"\d{4}-\d{2}", self.api_version):
            problems.append("SHOPIFY_API_VERSION must look like 2026-07")
        if not self.draft_only:
            problems.append("SnapIMS permits Shopify draft-only mode only at this stage")
        return problems
