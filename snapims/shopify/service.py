from __future__ import annotations

import time
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
    payload: dict[str, Any]


class ShopifyService:
    def __init__(self, db_file: Path, config: ShopifyConfig, client: ShopifyClient | None = None) -> None:
        self.db_file = db_file
        self.config = config
        self.client = client or ShopifyClient(config)

    def dry_run(self, item_id: str, *, remote_check: bool = False) -> ShopifyDryRun:
        item = db.get_item(self.db_file, item_id)
        if item is None:
            return ShopifyDryRun(item_id, False, "BLOCK", ("Unknown Item ID",), (), 0, {})
        photos = db.get_item_photos(self.db_file, item_id)
        config_problems = self.config.problems()
        errors = list(config_problems) if remote_check else []
        errors.extend(validation_errors(item, photos))
        if not item["ready"] or item["review_status"] != "DONE":
            errors.append("Item is not completed and READY")
        if item["upload_status"] == "UPLOADED":
            action = "SKIP_ALREADY_UPLOADED"
        else:
            action = "CREATE_DRAFT" if not config_problems else "SIMULATE_CREATE_DRAFT"
        if remote_check and not config_problems:
            existing = self.client.find_variant_by_sku(item["sku"])
            if existing and not item["shopify_product_id"]:
                errors.append(f"SKU already exists in Shopify on {existing['product']['title']}")
        final_price = int(round(int(item["price_cents"] or 0) * (1 - float(item["discount_percent"] or 0) / 100)))
        payload = {
            "item_id": item["item_id"], "sku": item["sku"], "title": item["title"],
            "price_cents": item["price_cents"], "discount_percent": item["discount_percent"],
            "final_price_cents": final_price, "quantity": item["quantity"], "barcode": item["barcode"],
            "vendor": item["vendor"], "product_type": item["product_type"], "tags": item["tags"],
            "image_count": len(photos), "status": "DRAFT",
        }
        warnings = tuple(f"Simulation only: {problem}" for problem in config_problems) if not remote_check else ()
        return ShopifyDryRun(item_id, not errors and action in {"CREATE_DRAFT", "SIMULATE_CREATE_DRAFT"}, action if not errors else "BLOCK", tuple(dict.fromkeys(errors)), warnings, len(photos), payload)

    def upload_draft(self, item_id: str, *, confirmed: bool = False, media_timeout: float = 30) -> dict[str, Any]:
        if not confirmed:
            raise PermissionError("Live Shopify writes require deliberate confirmation.")
        report = self.dry_run(item_id, remote_check=True)
        if not report.ready:
            raise ValueError("Shopify dry-run blocked upload: " + "; ".join(report.errors))
        paths = DataPaths.from_root(self.db_file.parent.parent).ensure()
        db.backup_database(paths, "before-shopify-upload")
        item = db.get_item(self.db_file, item_id)
        assert item is not None
        photos = db.get_item_photos(self.db_file, item_id)
        image_paths = [Path(photo["processed_path"]) for photo in photos]
        with db.connect(self.db_file) as connection:
            sync = connection.execute("SELECT * FROM shopify_sync WHERE item_id=?", (item_id,)).fetchone()
        checkpoint = dict(sync) if sync else {}
        attempt: int
        with db.transaction(self.db_file) as connection:
            cursor = connection.execute("INSERT INTO upload_attempts(item_id,started_at,status) VALUES(?,?,'RUNNING')", (item_id, db.now()))
            attempt = int(cursor.lastrowid)
        step = checkpoint.get("last_completed_step") or ""
        try:
            product_id = item["shopify_product_id"]
            variant_id = item["shopify_variant_id"]
            inventory_item_id = item["shopify_inventory_item_id"]
            if not product_id:
                created = self.client.create_draft_product(item)
                product_id, variant_id, inventory_item_id = created["product_id"], created["variant_id"], created["inventory_item_id"]
                step = "create_product"
                self._checkpoint(item_id, step, product_id=product_id, variant_id=variant_id, inventory_item_id=inventory_item_id)
            if step in {"", "create_product"}:
                self.client.configure_variant(item, product_id, variant_id)
                step = "configure_variant"
                self._checkpoint(item_id, step)
            if step == "configure_variant":
                self.client.activate_inventory(inventory_item_id, int(item["quantity"]))
                step = "activate_inventory"
                self._checkpoint(item_id, step, idempotency_key=str(uuid.uuid5(uuid.NAMESPACE_URL, f"snapims:{item_id}:inventory")))
            if step == "activate_inventory":
                targets = self.client.stage_images(image_paths)
                urls = self.client.upload_staged_images(image_paths, targets)
                self.client.attach_media(product_id, urls, item["title"])
                step = "attach_media"
                self._checkpoint(item_id, step)
            deadline = time.monotonic() + media_timeout
            while time.monotonic() < deadline:
                statuses = self.client.media_status(product_id)
                if len(statuses) >= len(image_paths) and all(status == "READY" for status in statuses):
                    break
                if any(status in {"FAILED", "ERROR"} for status in statuses):
                    raise RuntimeError(f"Shopify media processing failed: {statuses}")
                time.sleep(0.5)
            else:
                raise TimeoutError("Shopify media did not reach READY before timeout")
            admin_url = f"https://{self.config.store_domain}/admin/products/{product_id.rsplit('/',1)[-1]}"
            result = {"product_id": product_id, "variant_id": variant_id, "inventory_item_id": inventory_item_id, "admin_url": admin_url, "image_count": len(image_paths), "status": "UPLOADED_AS_DRAFT"}
            with db.transaction(self.db_file) as connection:
                connection.execute("UPDATE upload_attempts SET finished_at=?,status='SUCCESS',step=?,response_json=? WHERE attempt_id=?", (db.now(), step, __import__('json').dumps(result), attempt))
                connection.execute("UPDATE items SET upload_status='UPLOADED',shopify_product_id=?,shopify_variant_id=?,shopify_inventory_item_id=?,shopify_admin_url=?,last_error='',updated_at=? WHERE item_id=?", (product_id, variant_id, inventory_item_id, admin_url, db.now(), item_id))
                connection.execute("UPDATE shopify_sync SET status='UPLOADED',product_id=?,variant_id=?,inventory_item_id=?,admin_url=?,media_count=?,last_synced_at=?,last_error='',last_completed_step='complete' WHERE item_id=?", (product_id, variant_id, inventory_item_id, admin_url, len(image_paths), db.now(), item_id))
            return result
        except Exception as exc:
            with db.transaction(self.db_file) as connection:
                connection.execute("UPDATE upload_attempts SET finished_at=?,status='FAILED',step=?,error=? WHERE attempt_id=?", (db.now(), step, str(exc), attempt))
                connection.execute("UPDATE items SET upload_status='FAILED',last_error=?,retry_count=retry_count+1,updated_at=? WHERE item_id=?", (str(exc), db.now(), item_id))
                connection.execute("UPDATE shopify_sync SET status='FAILED',last_error=?,retry_count=retry_count+1 WHERE item_id=?", (str(exc), item_id))
            raise

    def _checkpoint(self, item_id: str, step: str, *, product_id: str = "", variant_id: str = "", inventory_item_id: str = "", idempotency_key: str = "") -> None:
        with db.transaction(self.db_file) as connection:
            connection.execute(
                """UPDATE items SET upload_status=?,shopify_product_id=CASE WHEN ?='' THEN shopify_product_id ELSE ? END,shopify_variant_id=CASE WHEN ?='' THEN shopify_variant_id ELSE ? END,shopify_inventory_item_id=CASE WHEN ?='' THEN shopify_inventory_item_id ELSE ? END,updated_at=? WHERE item_id=?""",
                (step.upper(), product_id, product_id, variant_id, variant_id, inventory_item_id, inventory_item_id, db.now(), item_id),
            )
            connection.execute(
                """UPDATE shopify_sync SET status=?,product_id=CASE WHEN ?='' THEN product_id ELSE ? END,variant_id=CASE WHEN ?='' THEN variant_id ELSE ? END,inventory_item_id=CASE WHEN ?='' THEN inventory_item_id ELSE ? END,idempotency_key=CASE WHEN ?='' THEN idempotency_key ELSE ? END,last_completed_step=? WHERE item_id=?""",
                (step.upper(), product_id, product_id, variant_id, variant_id, inventory_item_id, inventory_item_id, idempotency_key, idempotency_key, step, item_id),
            )
