from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


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
            problems.append("SnapIMS v0.5.1 permits Shopify draft-only mode")
        return problems
