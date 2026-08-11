from __future__ import annotations

from pathlib import Path
from typing import Any

from snapims import db
from snapims.config import DataPaths, ShopifyConfig


def _table_count(connection, table: str) -> int | None:
    try:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except Exception:
        return None


def _latest(connection, table: str, column: str) -> str:
    try:
        row = connection.execute(f"SELECT MAX({column}) FROM {table}").fetchone()
        return str(row[0] or "") if row else ""
    except Exception:
        return ""


def data_source_status(db_file: Path) -> list[dict[str, Any]]:
    db.initialize(db_file)
    paths = DataPaths.from_root(db_file.parent.parent)
    with db.connect(db_file) as connection:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        inventory_count = _table_count(connection, "items") or 0
        recognition_count = _table_count(connection, "recognition_results") or 0
        shopify_count = _table_count(connection, "shopify_sync") or 0
        shopify_fresh = _latest(connection, "shopify_sync", "last_synced_at")
        pricing_count = _table_count(connection, "pricing_item_states") if "pricing_item_states" in tables else 0
        pricing_fresh = _latest(connection, "pricing_item_states", "updated_at") if "pricing_item_states" in tables else ""
    catalog_count = 0
    catalog_fresh = ""
    catalog_state = "UNAVAILABLE"
    if paths.catalog_db_file.is_file():
        try:
            from snapims.catalog import db as catalog_db
            with catalog_db.connect(paths.catalog_db_file, readonly=True) as connection:
                catalog_count = _table_count(connection, "movies") or 0
                catalog_fresh = _latest(connection, "movies", "updated_at")
            catalog_state = "AVAILABLE"
        except Exception:
            catalog_state = "FAILED"
    try:
        shopify = ShopifyConfig.from_env()
        shopify_configured = bool(getattr(shopify, "store_domain", "") and (getattr(shopify, "client_id", "") or getattr(shopify, "admin_access_token", "")))
    except Exception:
        shopify_configured = False
    try:
        from snapims.pricing.integration import pricing_diagnostics
        diagnostics = pricing_diagnostics()
        ebay_detail = "Browser collector available" if diagnostics.get("playwright_importable") else "Manual sold/completed links available; browser collector unavailable"
        ebay_state = "AVAILABLE"
    except Exception as exc:
        ebay_detail = f"Manual sold/completed links remain available; pricing diagnostics unavailable: {type(exc).__name__}"
        ebay_state = "DEGRADED"
    return [
        {"source":"SnapIMS Inventory","state":"AVAILABLE","records":inventory_count,"freshness":"local/current","detail":"Authoritative local working records"},
        {"source":"Recognition","state":"AVAILABLE","records":recognition_count,"freshness":"local/current","detail":"Durable recognition attempts and operator selections"},
        {"source":"Catalog / Metadata","state":catalog_state,"records":catalog_count,"freshness":catalog_fresh or "—","detail":"Local movie catalog with nonblocking Wikipedia enrichment"},
        {"source":"Pricing History","state":"AVAILABLE" if pricing_count is not None else "UNAVAILABLE","records":pricing_count or 0,"freshness":pricing_fresh or "—","detail":"Local pricing state/cache; database-first suggestions remain operator-overridable"},
        {"source":"Shopify","state":"CONFIGURED" if shopify_configured else "NOT CONFIGURED","records":shopify_count,"freshness":shopify_fresh or "—","detail":"Current product sync state only; historical orders are not claimed unless synchronized"},
        {"source":"eBay Pricing","state":ebay_state,"records":pricing_count or 0,"freshness":pricing_fresh or "—","detail":ebay_detail},
    ]
