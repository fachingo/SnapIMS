from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snapims import db
from snapims.config import DataPaths, ShopifyConfig
from snapims.inventory import validation_errors
from snapims.shopify.client import ShopifyClient


@dataclass(frozen=True, slots=True)
class ShopifyDryRun:
    item_id: str
    ready: bool
    action: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    image_count: int


class ShopifyService:
    def __init__(
        self,
        db_file: Path,
        config: ShopifyConfig,
        client: ShopifyClient | None = None,
    ) -> None:
        self.db_file = db_file
        self.config = config
        self.client = client or ShopifyClient(config)

    def dry_run(self, item_id_value: str, *, remote_check: bool = False) -> ShopifyDryRun:
        item = db.get_item(self.db_file, item_id_value)
        if item is None:
            return ShopifyDryRun(item_id_value, False, "BLOCK", ("Unknown Item ID",), (), 0)
        photos = db.get_item_photos(self.db_file, item_id_value)
        config_problems = self.config.problems()
        errors = list(config_problems) if remote_check else []
        errors.extend(validation_errors(item, photos))
        warnings: list[str] = (
            [f"Simulation only: {problem}" for problem in config_problems]
            if not remote_check else []
        )
        action = "CREATE_DRAFT" if not config_problems else "SIMULATE_CREATE_DRAFT"
        if item["upload_status"] == "UPLOADED":
            action = "SKIP_ALREADY_UPLOADED"
        if not item["ready"]:
            errors.append("Item is not marked READY")
        if remote_check and not self.config.problems():
            existing = self.client.find_variant_by_sku(item["sku"])
            if existing and not item["shopify_product_id"]:
                errors.append(f"SKU already exists in Shopify on {existing['product']['title']}")
        return ShopifyDryRun(
            item_id=item_id_value,
            ready=not errors and action in {"CREATE_DRAFT", "SIMULATE_CREATE_DRAFT"},
            action=action if not errors else "BLOCK",
            errors=tuple(dict.fromkeys(errors)),
            warnings=tuple(warnings),
            image_count=len(photos),
        )

    def upload_draft(self, item_id_value: str, *, confirmed: bool = False) -> dict[str, Any]:
        if not confirmed:
            raise PermissionError("Live Shopify writes require deliberate confirmation.")
        report = self.dry_run(item_id_value, remote_check=True)
        if not report.ready:
            raise ValueError("Shopify dry-run blocked upload: " + "; ".join(report.errors))
        paths = DataPaths.from_root(self.db_file.parent.parent).ensure()
        db.backup_database(paths, "before-shopify-upload")
        item = db.get_item(self.db_file, item_id_value)
        assert item is not None
        photos = db.get_item_photos(self.db_file, item_id_value)
        image_paths = [Path(photo["processed_path"]) for photo in photos]
        attempt = db.start_upload_attempt(self.db_file, item_id_value)
        step = "start"
        try:
            product_id = item["shopify_product_id"]
            variant_id = item["shopify_variant_id"]
            inventory_item_id = item["shopify_inventory_item_id"]
            if not product_id:
                step = "create_product"
                db.set_upload_step(self.db_file, attempt, step)
                created = self.client.create_draft_product(item)
                product_id = created["product_id"]
                variant_id = created["variant_id"]
                inventory_item_id = created["inventory_item_id"]
                db.save_shopify_checkpoint(
                    self.db_file, item_id_value, "PRODUCT_CREATED",
                    product_id=product_id, variant_id=variant_id,
                    inventory_item_id=inventory_item_id,
                )

            step = "configure_variant"
            db.set_upload_step(self.db_file, attempt, step)
            self.client.configure_variant(item, product_id, variant_id)
            db.save_shopify_checkpoint(self.db_file, item_id_value, "VARIANT_CONFIGURED")

            step = "activate_inventory"
            db.set_upload_step(self.db_file, attempt, step)
            key = str(uuid.uuid5(uuid.NAMESPACE_URL, f"snapims:{item_id_value}:inventory"))
            self.client.activate_inventory(inventory_item_id, int(item["quantity"]), key)
            db.save_shopify_checkpoint(
                self.db_file, item_id_value, "INVENTORY_SET", idempotency_key=key
            )

            step = "stage_images"
            db.set_upload_step(self.db_file, attempt, step)
            targets = self.client.stage_images(image_paths)
            resource_urls = self.client.upload_staged_images(image_paths, targets)

            step = "attach_media"
            db.set_upload_step(self.db_file, attempt, step)
            self.client.attach_media(product_id, resource_urls, item["title"])
            db.save_shopify_checkpoint(self.db_file, item_id_value, "MEDIA_ATTACHED")

            numeric_product_id = product_id.rsplit("/", 1)[-1]
            admin_url = f"https://{self.config.store_domain}/admin/products/{numeric_product_id}"
            result = {
                "product_id": product_id, "variant_id": variant_id,
                "inventory_item_id": inventory_item_id, "admin_url": admin_url,
                "image_count": len(image_paths), "status": "UPLOADED_AS_DRAFT",
            }
            db.finish_upload_success(
                self.db_file, attempt, item_id_value, product_id=product_id,
                variant_id=variant_id, inventory_item_id=inventory_item_id,
                admin_url=admin_url, response=result,
            )
            return result
        except Exception as exc:
            db.finish_upload_failure(self.db_file, attempt, item_id_value, step, str(exc))
            raise
