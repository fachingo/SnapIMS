from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from snapims import db
from snapims.config import ShopifyConfig
from snapims.demo import create_demo_batch
from snapims.inventory import validate_items
from snapims.processor import process_batch
from snapims.shopify.client import ShopifyClient
from snapims.shopify.service import ShopifyService


class FakeShopifyTransport:
    def __init__(self, *, duplicate_sku: bool = False) -> None:
        self.duplicate_sku = duplicate_sku
        self.operations: list[str] = []
        self.uploads: list[Path] = []

    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        if "VariantBySku" in query:
            self.operations.append("sku_check")
            nodes = []
            if self.duplicate_sku:
                nodes = [
                    {
                        "id": "gid://shopify/ProductVariant/99",
                        "sku": variables["query"].removeprefix("sku:"),
                        "inventoryItem": {"id": "gid://shopify/InventoryItem/99"},
                        "product": {
                            "id": "gid://shopify/Product/99",
                            "title": "Existing tape",
                            "status": "ACTIVE",
                        },
                    }
                ]
            return {"data": {"productVariants": {"nodes": nodes}}}
        if "CreateDraft" in query:
            self.operations.append("create_product")
            return {
                "data": {
                    "productCreate": {
                        "product": {
                            "id": "gid://shopify/Product/1",
                            "handle": "demo-tape",
                            "variants": {
                                "nodes": [
                                    {
                                        "id": "gid://shopify/ProductVariant/2",
                                        "inventoryItem": {
                                            "id": "gid://shopify/InventoryItem/3"
                                        },
                                    }
                                ]
                            },
                        },
                        "userErrors": [],
                    }
                }
            }
        if "ConfigureVariant" in query:
            self.operations.append("configure_variant")
            return {
                "data": {
                    "productVariantsBulkUpdate": {
                        "productVariants": [],
                        "userErrors": [],
                    }
                }
            }
        if "ActivateInventory" in query:
            self.operations.append("activate_inventory")
            return {
                "data": {
                    "inventoryActivate": {
                        "inventoryLevel": {"id": "gid://shopify/InventoryLevel/4"},
                        "userErrors": [],
                    }
                }
            }
        if "StageImages" in query:
            self.operations.append("stage_images")
            targets = [
                {
                    "url": f"https://uploads.example/{index}",
                    "resourceUrl": f"https://cdn.example/{index}.jpg",
                    "parameters": [],
                }
                for index, _ in enumerate(variables["input"], start=1)
            ]
            return {
                "data": {
                    "stagedUploadsCreate": {
                        "stagedTargets": targets,
                        "userErrors": [],
                    }
                }
            }
        if "AttachMedia" in query:
            self.operations.append("attach_media")
            return {
                "data": {
                    "productUpdate": {
                        "product": {"id": "gid://shopify/Product/1"},
                        "userErrors": [],
                    }
                }
            }
        raise AssertionError(f"Unexpected Shopify operation: {query}")

    def upload(
        self, url: str, parameters: list[dict[str, str]], file_path: Path
    ) -> None:
        assert url.startswith("https://uploads.example/")
        assert parameters == []
        assert file_path.is_file()
        self.uploads.append(file_path)


def _ready_item(tmp_path, data_paths) -> str:
    source = create_demo_batch(tmp_path / "camera")
    result = process_batch(source, paths=data_paths)
    item = db.list_items(data_paths.db_file, batch_id_value=result.batch_id)[0]
    db.update_item(
        data_paths.db_file,
        item["item_id"],
        {
            "title": "Synthetic VHS Test Tape",
            "price_cents": 1299,
            "condition": "Very Good",
            "ready": 1,
        },
    )
    validate_items(data_paths.db_file, [item["item_id"]])
    return str(item["item_id"])


def _config() -> ShopifyConfig:
    return ShopifyConfig(
        store_domain="canada-vhs.myshopify.com",
        access_token="shpat_test_only",
        location_id="gid://shopify/Location/123",
        api_version="2026-07",
    )


def test_shopify_simulation_runs_without_credentials(tmp_path, data_paths) -> None:
    item_id = _ready_item(tmp_path, data_paths)
    service = ShopifyService(
        data_paths.db_file,
        ShopifyConfig(store_domain="", access_token="", location_id=""),
    )
    report = service.dry_run(item_id)
    assert report.ready is True
    assert report.action == "SIMULATE_CREATE_DRAFT"
    assert report.image_count == 2
    assert report.warnings


def test_shopify_remote_dry_run_blocks_duplicate_sku(tmp_path, data_paths) -> None:
    item_id = _ready_item(tmp_path, data_paths)
    transport = FakeShopifyTransport(duplicate_sku=True)
    service = ShopifyService(
        data_paths.db_file,
        _config(),
        ShopifyClient(_config(), transport=transport),
    )
    report = service.dry_run(item_id, remote_check=True)
    assert report.ready is False
    assert report.action == "BLOCK"
    assert any("SKU already exists" in error for error in report.errors)


def test_shopify_live_boundary_requires_deliberate_confirmation(tmp_path, data_paths) -> None:
    item_id = _ready_item(tmp_path, data_paths)
    with pytest.raises(PermissionError, match="deliberate confirmation"):
        ShopifyService(data_paths.db_file, _config()).upload_draft(item_id)


def test_shopify_mock_upload_checkpoints_and_finishes_as_draft(tmp_path, data_paths) -> None:
    item_id = _ready_item(tmp_path, data_paths)
    transport = FakeShopifyTransport()
    service = ShopifyService(
        data_paths.db_file,
        _config(),
        ShopifyClient(_config(), transport=transport),
    )
    result = service.upload_draft(item_id, confirmed=True)
    assert result["status"] == "UPLOADED_AS_DRAFT"
    assert result["image_count"] == 2
    assert len(transport.uploads) == 2
    assert transport.operations == [
        "sku_check",
        "create_product",
        "configure_variant",
        "activate_inventory",
        "stage_images",
        "attach_media",
    ]
    item = db.get_item(data_paths.db_file, item_id)
    assert item is not None
    assert item["upload_status"] == "UPLOADED"
    assert item["shopify_product_id"] == "gid://shopify/Product/1"
    with db.connect(data_paths.db_file) as connection:
        attempt = connection.execute(
            "SELECT status, step FROM upload_attempts WHERE item_id=?", (item_id,)
        ).fetchone()
        assert tuple(attempt) == ("SUCCESS", "attach_media")
