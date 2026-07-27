from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from snapims import db
from snapims.config import ShopifyConfig
from snapims.shopify.service import ShopifyService
from tests.helpers import ready_item


class FakeShopifyClient:
    def __init__(self, *, fail_at: str | None = None, media_sequence: list[list[str]] | None = None) -> None:
        self.fail_at = fail_at
        self.calls: Counter[str] = Counter()
        self.product_id = "gid://shopify/Product/100"
        self.variant_id = "gid://shopify/ProductVariant/200"
        self.inventory_item_id = "gid://shopify/InventoryItem/300"
        self.remote_product = False
        self.inventory: int | None = None
        self.attached = False
        self.media_sequence = list(media_sequence or [["READY"]])

    def _call(self, name: str) -> None:
        self.calls[name] += 1
        if self.fail_at == name:
            self.fail_at = None
            raise RuntimeError(f"forced {name} failure")

    def find_variant_by_sku(self, sku: str) -> dict[str, Any] | None:
        self._call("find_variant_by_sku")
        if not self.remote_product:
            return None
        return {
            "id": self.variant_id,
            "sku": sku,
            "inventoryItem": {"id": self.inventory_item_id},
            "product": {"id": self.product_id, "title": "Remote Draft", "status": "DRAFT"},
        }

    def create_draft_product(self, item: dict[str, Any]) -> dict[str, str]:
        self._call("create_draft_product")
        self.remote_product = True
        return {
            "product_id": self.product_id,
            "variant_id": self.variant_id,
            "inventory_item_id": self.inventory_item_id,
        }

    def configure_variant(self, item, product_id, variant_id) -> None:
        self._call("configure_variant")

    def inventory_quantity(self, inventory_item_id: str) -> int | None:
        self._call("inventory_quantity")
        return self.inventory

    def activate_inventory(
        self, inventory_item_id: str, quantity: int, idempotency_key: str
    ) -> None:
        self._call("activate_inventory")
        self.last_idempotency_key = idempotency_key
        self.inventory = quantity

    def stage_images(self, image_paths: list[Path]) -> list[dict[str, Any]]:
        self._call("stage_images")
        return [
            {"url": f"https://upload/{index}", "parameters": [], "resourceUrl": f"https://cdn/{index}.jpg"}
            for index, _ in enumerate(image_paths)
        ]

    def upload_staged_images(self, image_paths, targets) -> list[str]:
        self._call("upload_staged_images")
        return [target["resourceUrl"] for target in targets]

    def attach_media(self, product_id: str, resource_urls: list[str], title: str) -> None:
        self._call("attach_media")
        self.attached = True

    def media_status(self, product_id: str) -> list[str]:
        self._call("media_status")
        if not self.attached:
            return []
        if len(self.media_sequence) > 1:
            return self.media_sequence.pop(0)
        return self.media_sequence[0]


def valid_config() -> ShopifyConfig:
    return ShopifyConfig(
        store_domain="example.myshopify.com",
        access_token="token",
        location_id="gid://shopify/Location/1",
        draft_only=True,
    )


def service_for(tmp_path: Path, data_paths, *, client: FakeShopifyClient | None = None):
    _, item = ready_item(tmp_path, data_paths)
    assert item is not None
    fake = client or FakeShopifyClient(media_sequence=[["READY", "READY"]])
    return ShopifyService(data_paths.db_file, valid_config(), client=fake), fake, item


def test_simulation_without_credentials(tmp_path: Path, data_paths) -> None:
    _, item = ready_item(tmp_path, data_paths)
    service = ShopifyService(
        data_paths.db_file,
        ShopifyConfig("", "", ""),
        client=FakeShopifyClient(),
    )
    report = service.dry_run(item["item_id"])
    assert report.ready
    assert report.action == "SIMULATE_CREATE_DRAFT"
    assert report.payload["status"] == "DRAFT"


def test_live_requires_confirmation(tmp_path: Path, data_paths) -> None:
    service, _, item = service_for(tmp_path, data_paths)
    with pytest.raises(PermissionError, match="confirmation"):
        service.upload_draft(item["item_id"])


def test_live_requires_valid_configuration(tmp_path: Path, data_paths) -> None:
    _, item = ready_item(tmp_path, data_paths)
    service = ShopifyService(data_paths.db_file, ShopifyConfig("", "", ""), client=FakeShopifyClient())
    with pytest.raises(ValueError, match="configuration"):
        service.upload_draft(item["item_id"], confirmed=True)


def test_successful_upload_is_draft_and_checkpointed(tmp_path: Path, data_paths) -> None:
    service, fake, item = service_for(tmp_path, data_paths)
    result = service.upload_draft(item["item_id"], confirmed=True, poll_interval=0)
    assert result["status"] == "UPLOADED_AS_DRAFT"
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert saved["upload_status"] == "UPLOADED"
    with db.connect(data_paths.db_file) as connection:
        sync = connection.execute("SELECT * FROM shopify_sync WHERE item_id=?", (item["item_id"],)).fetchone()
    assert sync["last_completed_step"] == "complete"
    assert fake.calls["create_draft_product"] == 1
    assert fake.calls["activate_inventory"] == 1
    assert fake.calls["attach_media"] == 1
    with db.connect(data_paths.db_file) as connection:
        activation = connection.execute(
            "SELECT response_json FROM upload_attempts WHERE item_id=? ORDER BY attempt_id DESC LIMIT 1",
            (item["item_id"],),
        ).fetchone()
    assert activation is not None


@pytest.mark.parametrize(
    "stage",
    [
        "create_draft_product",
        "configure_variant",
        "activate_inventory",
        "stage_images",
        "upload_staged_images",
        "attach_media",
    ],
)
def test_retry_after_stage_failure_does_not_recreate_completed_product(tmp_path: Path, data_paths, stage: str) -> None:
    fake = FakeShopifyClient(fail_at=stage, media_sequence=[["READY", "READY"]])
    service, fake, item = service_for(tmp_path, data_paths, client=fake)
    with pytest.raises(RuntimeError, match="forced"):
        service.upload_draft(item["item_id"], confirmed=True, poll_interval=0)
    service.upload_draft(item["item_id"], confirmed=True, poll_interval=0)
    expected_create_calls = 2 if stage == "create_draft_product" else 1
    assert fake.calls["create_draft_product"] == expected_create_calls
    assert db.get_item(data_paths.db_file, item["item_id"])["upload_status"] == "UPLOADED"


def test_reconcile_product_created_before_local_checkpoint(tmp_path: Path, data_paths, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeShopifyClient(media_sequence=[["READY", "READY"]])
    service, fake, item = service_for(tmp_path, data_paths, client=fake)
    original = service._checkpoint
    tripped = False

    def fail_first_checkpoint(item_id: str, step: str, **values):
        nonlocal tripped
        if step == "create_product" and not tripped:
            tripped = True
            raise RuntimeError("local checkpoint failure")
        return original(item_id, step, **values)

    monkeypatch.setattr(service, "_checkpoint", fail_first_checkpoint)
    with pytest.raises(RuntimeError, match="local checkpoint"):
        service.upload_draft(item["item_id"], confirmed=True, poll_interval=0)
    monkeypatch.setattr(service, "_checkpoint", original)
    service.upload_draft(item["item_id"], confirmed=True, poll_interval=0)
    assert fake.calls["create_draft_product"] == 1
    assert fake.calls["find_variant_by_sku"] >= 2


def test_inventory_remote_reconciliation_avoids_double_activation(tmp_path: Path, data_paths, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeShopifyClient(media_sequence=[["READY", "READY"]])
    service, fake, item = service_for(tmp_path, data_paths, client=fake)
    original = service._checkpoint
    tripped = False

    def fail_inventory_checkpoint(item_id: str, step: str, **values):
        nonlocal tripped
        if step == "activate_inventory" and not tripped:
            tripped = True
            raise RuntimeError("inventory checkpoint failure")
        return original(item_id, step, **values)

    monkeypatch.setattr(service, "_checkpoint", fail_inventory_checkpoint)
    with pytest.raises(RuntimeError):
        service.upload_draft(item["item_id"], confirmed=True, poll_interval=0)
    monkeypatch.setattr(service, "_checkpoint", original)
    service.upload_draft(item["item_id"], confirmed=True, poll_interval=0)
    assert fake.calls["activate_inventory"] == 1


def test_inventory_key_is_persisted_before_request_and_reused(
    tmp_path: Path, data_paths
) -> None:
    class UncertainInventoryClient(FakeShopifyClient):
        uncertain = True

        def activate_inventory(
            self, inventory_item_id: str, quantity: int, idempotency_key: str
        ) -> None:
            self.calls["activate_inventory"] += 1
            self.last_idempotency_key = idempotency_key
            self.inventory = quantity
            if self.uncertain:
                self.uncertain = False
                raise TimeoutError("uncertain activation timeout")

    fake = UncertainInventoryClient(media_sequence=[["READY", "READY"]])
    service, fake, item = service_for(tmp_path, data_paths, client=fake)
    with pytest.raises(TimeoutError, match="uncertain"):
        service.upload_draft(item["item_id"], confirmed=True, poll_interval=0)
    with db.connect(data_paths.db_file) as connection:
        sync = connection.execute(
            "SELECT idempotency_key,last_completed_step FROM shopify_sync WHERE item_id=?",
            (item["item_id"],),
        ).fetchone()
        attempt = connection.execute(
            "SELECT response_json FROM upload_attempts WHERE item_id=? ORDER BY attempt_id DESC LIMIT 1",
            (item["item_id"],),
        ).fetchone()
    assert sync is not None and sync["idempotency_key"]
    persisted_key = str(sync["idempotency_key"])
    assert sync["last_completed_step"] == "configure_variant"
    assert attempt is not None
    detail = __import__("json").loads(attempt["response_json"])
    assert detail["idempotency_key"] == persisted_key
    assert detail["request_hash"]

    service.upload_draft(item["item_id"], confirmed=True, poll_interval=0)
    assert fake.calls["activate_inventory"] == 1
    assert fake.last_idempotency_key == persisted_key


def test_inventory_activate_mutation_uses_required_idempotent_directive() -> None:
    from snapims.shopify.client import ShopifyClient

    class CaptureTransport:
        query = ""
        variables: dict[str, Any] = {}

        def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
            self.query = query
            self.variables = variables
            return {
                "data": {
                    "inventoryActivate": {
                        "inventoryLevel": {"id": "gid://shopify/InventoryLevel/1"},
                        "userErrors": [],
                    }
                }
            }

        def upload(self, url, parameters, file_path) -> None:
            raise AssertionError("not used")

    transport = CaptureTransport()
    ShopifyClient(valid_config(), transport=transport).activate_inventory(
        "gid://shopify/InventoryItem/1", 1, "stable-key"
    )
    assert "@idempotent(key:$idempotencyKey)" in transport.query
    assert transport.variables["idempotencyKey"] == "stable-key"


def test_exact_sku_query_rejects_ambiguous_multiple_matches() -> None:
    from snapims.shopify.client import ShopifyAPIError, ShopifyClient

    class AmbiguousTransport:
        def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
            return {
                "data": {
                    "productVariants": {
                        "nodes": [
                            {"id": "gid://shopify/ProductVariant/1"},
                            {"id": "gid://shopify/ProductVariant/2"},
                        ]
                    }
                }
            }

        def upload(self, url, parameters, file_path) -> None:
            raise AssertionError("not used")

    with pytest.raises(ShopifyAPIError, match="multiple variants"):
        ShopifyClient(valid_config(), transport=AmbiguousTransport()).find_variant_by_sku(
            "VHS-1"
        )


def test_media_remote_reconciliation_avoids_duplicate_attach(tmp_path: Path, data_paths, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeShopifyClient(media_sequence=[["READY", "READY"]])
    service, fake, item = service_for(tmp_path, data_paths, client=fake)
    original = service._checkpoint
    tripped = False

    def fail_media_checkpoint(item_id: str, step: str, **values):
        nonlocal tripped
        if step == "attach_media" and not tripped:
            tripped = True
            raise RuntimeError("media checkpoint failure")
        return original(item_id, step, **values)

    monkeypatch.setattr(service, "_checkpoint", fail_media_checkpoint)
    with pytest.raises(RuntimeError):
        service.upload_draft(item["item_id"], confirmed=True, poll_interval=0)
    monkeypatch.setattr(service, "_checkpoint", original)
    service.upload_draft(item["item_id"], confirmed=True, poll_interval=0)
    assert fake.calls["attach_media"] == 1


def test_media_processing_failure_is_recorded(tmp_path: Path, data_paths) -> None:
    fake = FakeShopifyClient(media_sequence=[["FAILED", "READY"]])
    service, fake, item = service_for(tmp_path, data_paths, client=fake)
    with pytest.raises(RuntimeError, match="media processing failed"):
        service.upload_draft(item["item_id"], confirmed=True, poll_interval=0)
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert saved["upload_status"] == "FAILED"
    assert "media processing failed" in saved["last_error"]


def test_media_timeout_is_recoverable(tmp_path: Path, data_paths) -> None:
    fake = FakeShopifyClient(media_sequence=[["PROCESSING", "PROCESSING"]])
    service, fake, item = service_for(tmp_path, data_paths, client=fake)
    with pytest.raises(TimeoutError):
        service.upload_draft(item["item_id"], confirmed=True, media_timeout=0, poll_interval=0)
    fake.media_sequence = [["READY", "READY"]]
    result = service.upload_draft(item["item_id"], confirmed=True, poll_interval=0)
    assert result["status"] == "UPLOADED_AS_DRAFT"
    assert fake.calls["attach_media"] == 1


def test_existing_non_draft_sku_is_blocked(tmp_path: Path, data_paths) -> None:
    fake = FakeShopifyClient(media_sequence=[["READY", "READY"]])
    fake.remote_product = True

    def non_draft(sku: str):
        found = FakeShopifyClient.find_variant_by_sku(fake, sku)
        assert found is not None
        found["product"]["status"] = "ACTIVE"
        return found

    fake.find_variant_by_sku = non_draft  # type: ignore[method-assign]
    service, _, item = service_for(tmp_path, data_paths, client=fake)
    with pytest.raises(ValueError, match="non-draft"):
        service.upload_draft(item["item_id"], confirmed=True, poll_interval=0)
