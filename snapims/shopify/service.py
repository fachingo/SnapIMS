from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snapims import db
from snapims.catalog.service import catalog_output_for_item
from snapims.config import DataPaths, ShopifyConfig
from snapims.inventory import validation_errors
from snapims.money import final_price_cents
from snapims.observability import safe_exception, try_emit_event
from snapims.runtime import is_test_provider, test_providers_enabled
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
        self.paths = DataPaths.from_root(self.db_file.parent.parent).ensure()

    def _event(self, item_id: str, event_type: str, **fields: Any) -> int | None:
        return try_emit_event(
            self.db_file,
            component="shopify",
            event_type=event_type,
            operation_id=f"shopify:{item_id}",
            item_id=item_id,
            provider="shopify",
            paths=self.paths,
            known_secrets=tuple(value for value in (self.config.access_token, self.config.client_secret) if value),
            **fields,
        )

    def dry_run(self, item_id: str, *, remote_check: bool = False) -> ShopifyDryRun:
        item = db.get_item(self.db_file, item_id)
        if item is None:
            self._event(
                item_id,
                "shopify.simulation_blocked",
                severity="WARNING",
                status="BLOCKED",
                outcome="UNKNOWN_ITEM",
                safe_summary="Shopify simulation was blocked for an unknown Item ID.",
            )
            return ShopifyDryRun(item_id, False, "BLOCK", ("Unknown Item ID",), (), 0, {})
        photos = db.get_item_photos(self.db_file, item_id)
        config_problems = self.config.problems()
        errors = list(config_problems) if remote_check else []
        errors.extend(validation_errors(item, photos))
        if not item["ready"] or item["review_status"] != "DONE":
            errors.append("Item is not completed and READY")
        if not bool(item.get("publish_eligible", 1)) or bool(item.get("is_test_copy")):
            errors.append(
                "Isolated test-copy inventory is quarantined and can never become Shopify-ready."
            )
        test_provenance = (
            str(item.get("suggestion_source_kind") or "").upper() == "TEST"
            or is_test_provider(item.get("recognition_provider"))
            or is_test_provider(item.get("suggestion_provider"))
        )
        manually_replaced = (
            str(item.get("working_source") or "") == "INDIVIDUAL_REVIEW"
            or str(item.get("review_source") or "") == "CSV_EXTERNAL_REVIEW"
        )
        if test_provenance and not (manually_replaced or test_providers_enabled()):
            errors.append(
                "Test-sourced recognition is not eligible for Shopify draft creation. "
                "Replace it with a live-provider result or complete a documented manual review."
            )
        if item["upload_status"] == "UPLOADED":
            action = "SKIP_ALREADY_UPLOADED"
        else:
            action = "CREATE_DRAFT" if not config_problems else "SIMULATE_CREATE_DRAFT"
        if remote_check and not config_problems:
            existing = self.client.find_variant_by_sku(item["sku"])
            if existing and not item["shopify_product_id"]:
                errors.append(f"SKU already exists in Shopify on {existing['product']['title']}")
        final_price = final_price_cents(int(item["price_cents"] or 0), item["discount_percent"] or 0)
        try:
            movie = catalog_output_for_item(self.paths, item_id)
        except Exception:
            movie = {
                "movie_id": "", "canonical_title": "", "original_title": "",
                "release_year": None, "runtime_minutes": None, "directors": [],
                "countries": [], "languages": [], "genres": [],
                "catalog_match_status": "CATALOG_UNAVAILABLE",
                "source_page_url": "", "provenance_status": "UNAVAILABLE",
            }
        payload = {
            "item_id": item["item_id"], "sku": item["sku"], "title": item["title"],
            "price_cents": item["price_cents"], "discount_percent": item["discount_percent"],
            "final_price_cents": final_price, "quantity": item["quantity"], "barcode": item["barcode"],
            "vendor": item["vendor"], "product_type": item["product_type"], "tags": item["tags"],
            "image_count": len(photos), "status": "DRAFT",
            "movie": movie,
            "local_movie_id": movie["movie_id"],
            "canonical_movie_title": movie["canonical_title"],
            "film_release_year": movie["release_year"],
            "catalog_match_status": movie["catalog_match_status"],
        }
        warnings = tuple(f"Simulation only: {problem}" for problem in config_problems) if not remote_check else ()
        report = ShopifyDryRun(
            item_id,
            not errors and action in {"CREATE_DRAFT", "SIMULATE_CREATE_DRAFT"},
            action if not errors else "BLOCK",
            tuple(dict.fromkeys(errors)),
            warnings,
            len(photos),
            payload,
        )
        self._event(
            item_id,
            "shopify.simulation_completed",
            severity="INFO" if report.ready else "WARNING",
            image_count=len(photos),
            status="READY" if report.ready else "BLOCKED",
            outcome=report.action,
            detail={
                "remote_check": remote_check,
                "error_count": len(report.errors),
                "warning_count": len(report.warnings),
                "image_count": len(photos),
            },
        )
        return report

    def upload_draft(
        self,
        item_id: str,
        *,
        confirmed: bool = False,
        allow_incomplete: bool = False,
        media_timeout: float = 30,
        poll_interval: float = 0.5,
    ) -> dict[str, Any]:
        if not confirmed:
            raise PermissionError("Live Shopify writes require deliberate confirmation.")
        if self.config.problems():
            raise ValueError("Shopify configuration blocked upload: " + "; ".join(self.config.problems()))
        report = self.dry_run(item_id, remote_check=False)
        if not report.ready and not allow_incomplete:
            raise ValueError("Shopify dry-run blocked upload: " + "; ".join(report.errors))

        backup = db.backup_database(self.paths, "before-shopify-upload")
        if backup is not None:
            self._event(
                item_id,
                "shopify.backup_created",
                status="COMPLETE",
                outcome="before-shopify-upload",
                detail={"filename": backup.name},
                retention_class="BUSINESS",
            )
        item = db.get_item(self.db_file, item_id)
        assert item is not None
        photos = db.get_item_photos(self.db_file, item_id)
        image_paths = [Path(photo["processed_path"]) for photo in photos]
        media_identifiers = [
            f"snapims:{item_id}:photo:{int(photo['photo_id'])}" for photo in photos
        ]
        with db.connect(self.db_file) as connection:
            sync_row = connection.execute(
                "SELECT * FROM shopify_sync WHERE item_id=?", (item_id,)
            ).fetchone()
        checkpoint = dict(sync_row) if sync_row else {}
        step = str(checkpoint.get("last_completed_step") or "")
        order = {"": 0, "create_product": 1, "configure_variant": 2, "activate_inventory": 3, "attach_media": 4, "complete": 5}

        with db.transaction(self.db_file) as connection:
            cursor = connection.execute(
                "INSERT INTO upload_attempts(item_id,started_at,status) VALUES(?,?,'RUNNING')",
                (item_id, db.now()),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return an upload attempt ID")
            attempt = cursor.lastrowid

        upload_started = time.monotonic()
        active_stage = "reconcile"
        self._event(
            item_id,
            "shopify.upload_started",
            attempt_number=int(checkpoint.get("retry_count") or 0) + 1,
            image_count=len(image_paths),
            status="RUNNING",
            detail={"last_completed_step": step},
            retention_class="BUSINESS",
        )
        try:
            product_id = str(checkpoint.get("product_id") or item["shopify_product_id"] or "")
            variant_id = str(checkpoint.get("variant_id") or item["shopify_variant_id"] or "")
            inventory_item_id = str(
                checkpoint.get("inventory_item_id") or item["shopify_inventory_item_id"] or ""
            )

            if not product_id:
                active_stage = "find_variant_by_sku"
                existing = self.client.find_variant_by_sku(item["sku"])
                if existing:
                    product = existing.get("product") or {}
                    if str(product.get("status", "DRAFT")).upper() != "DRAFT":
                        raise ValueError(
                            f"SKU already exists on a non-draft Shopify product: {product.get('title', item['sku'])}"
                        )
                    product_id = str(product["id"])
                    variant_id = str(existing["id"])
                    inventory_item_id = str((existing.get("inventoryItem") or {})["id"])
                else:
                    active_stage = "create_draft_product"
                    created = self.client.create_draft_product(item)
                    product_id = created["product_id"]
                    variant_id = created["variant_id"]
                    inventory_item_id = created["inventory_item_id"]
                step = "create_product"
                self._checkpoint(
                    item_id,
                    step,
                    product_id=product_id,
                    variant_id=variant_id,
                    inventory_item_id=inventory_item_id,
                )

            if order.get(step, 0) < order["configure_variant"]:
                active_stage = "configure_variant"
                self.client.configure_variant(item, product_id, variant_id, allow_incomplete=allow_incomplete)
                step = "configure_variant"
                self._checkpoint(item_id, step)

            if order.get(step, 0) < order["activate_inventory"]:
                active_stage = "activate_inventory"
                # Each SnapIMS item represents one separately sellable physical tape.
                desired_quantity = 1
                idempotency_key = str(
                    checkpoint.get("idempotency_key")
                    or uuid.uuid5(
                        uuid.NAMESPACE_URL, f"snapims:{item_id}:inventory-activate"
                    )
                )
                request_payload = {
                    "inventory_item_id": inventory_item_id,
                    "location_id": self.config.location_id,
                    "quantity": desired_quantity,
                }
                request_hash = hashlib.sha256(
                    json.dumps(
                        request_payload, separators=(",", ":"), sort_keys=True
                    ).encode("utf-8")
                ).hexdigest()
                self._record_outbound_request(
                    attempt,
                    item_id,
                    step="activate_inventory",
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    request_payload=request_payload,
                )
                current_quantity = self.client.inventory_quantity(inventory_item_id)
                if current_quantity is None:
                    self.client.activate_inventory(
                        inventory_item_id, desired_quantity, idempotency_key
                    )
                elif current_quantity != desired_quantity:
                    self.client.set_inventory_quantity(
                        inventory_item_id,
                        desired_quantity,
                        current_quantity,
                        idempotency_key,
                    )
                step = "activate_inventory"
                self._checkpoint(
                    item_id,
                    step,
                    idempotency_key=idempotency_key,
                )
                self._record_outbound_outcome(
                    attempt,
                    outcome="RECONCILED"
                    if current_quantity == desired_quantity
                    else "SUCCEEDED",
                )

            if order.get(step, 0) < order["attach_media"]:
                active_stage = "media_status_reconcile"
                records = self.client.media_records(product_id)
                by_identifier = {record["alt"]: record for record in records if record["alt"]}
                missing_indexes = [
                    index
                    for index, identifier in enumerate(media_identifiers)
                    if identifier not in by_identifier
                ]
                if missing_indexes:
                    missing_paths = [image_paths[index] for index in missing_indexes]
                    missing_ids = [media_identifiers[index] for index in missing_indexes]
                    active_stage = "stage_images"
                    targets = self.client.stage_images(missing_paths)
                    active_stage = "upload_staged_images"
                    urls = self.client.upload_staged_images(missing_paths, targets)
                    active_stage = "attach_media"
                    self.client.attach_media(product_id, urls, missing_ids)
                step = "attach_media"
                self._checkpoint(item_id, step)

            active_stage = "media_processing"
            deadline = time.monotonic() + media_timeout
            while time.monotonic() < deadline:
                records = self.client.media_records(product_id)
                by_identifier = {record["alt"]: record for record in records if record["alt"]}
                intended = [by_identifier.get(identifier) for identifier in media_identifiers]
                intended_statuses = [
                    record["status"] if record is not None else "MISSING"
                    for record in intended
                ]
                if intended and all(status == "READY" for status in intended_statuses):
                    break
                if any(status in {"FAILED", "ERROR"} for status in intended_statuses):
                    raise RuntimeError(
                        f"Shopify media processing failed for intended photos: {intended_statuses}"
                    )
                time.sleep(max(0, poll_interval))
            else:
                raise TimeoutError("Shopify intended media did not reach READY before timeout")

            admin_url = (
                f"https://{self.config.store_domain}/admin/products/"
                f"{product_id.rsplit('/', 1)[-1]}"
            )
            result = {
                "product_id": product_id,
                "variant_id": variant_id,
                "inventory_item_id": inventory_item_id,
                "admin_url": admin_url,
                "image_count": len(image_paths),
                "status": "UPLOADED_AS_DRAFT",
            }
            with db.transaction(self.db_file) as connection:
                request_record = connection.execute(
                    "SELECT response_json FROM upload_attempts WHERE attempt_id=?",
                    (attempt,),
                ).fetchone()
                if request_record:
                    outbound = json.loads(str(request_record[0] or "{}"))
                    if outbound:
                        result["outbound_operation"] = outbound
                connection.execute(
                    "UPDATE upload_attempts SET finished_at=?,status='SUCCESS',step=?,response_json=? WHERE attempt_id=?",
                    (db.now(), step, json.dumps(result), attempt),
                )
                connection.execute(
                    "UPDATE items SET upload_status='UPLOADED',shopify_product_id=?,shopify_variant_id=?,shopify_inventory_item_id=?,shopify_admin_url=?,last_error='',updated_at=? WHERE item_id=?",
                    (product_id, variant_id, inventory_item_id, admin_url, db.now(), item_id),
                )
                connection.execute(
                    """UPDATE shopify_sync
                          SET status='UPLOADED',product_id=?,variant_id=?,inventory_item_id=?,
                              admin_url=?,media_count=?,last_synced_at=?,last_error='',
                              last_completed_step='complete',product_status='DRAFT',
                              sync_state='IN_SYNC',last_action='CREATE_DRAFT',
                              archived_at=NULL,deleted_at=NULL
                        WHERE item_id=?""",
                    (product_id, variant_id, inventory_item_id, admin_url, len(image_paths), db.now(), item_id),
                )
            self._event(
                item_id,
                "shopify.upload_completed",
                attempt_number=int(checkpoint.get("retry_count") or 0) + 1,
                duration_ms=int((time.monotonic() - upload_started) * 1000),
                image_count=len(image_paths),
                status="UPLOADED",
                outcome="DRAFT_CREATED",
                detail={"last_completed_step": "complete"},
                retention_class="BUSINESS",
            )
            return result
        except Exception as exc:
            safe = safe_exception(exc, known_secrets=tuple(value for value in (self.config.access_token, self.config.client_secret) if value))
            with db.transaction(self.db_file) as connection:
                connection.execute(
                    "UPDATE upload_attempts SET finished_at=?,status='FAILED',step=?,error=? WHERE attempt_id=?",
                    (db.now(), step, str(exc), attempt),
                )
                connection.execute(
                    "UPDATE items SET upload_status='FAILED',last_error=?,retry_count=retry_count+1,updated_at=? WHERE item_id=?",
                    (str(exc), db.now(), item_id),
                )
                connection.execute(
                    "UPDATE shopify_sync SET status='FAILED',last_error=?,retry_count=retry_count+1 WHERE item_id=?",
                    (str(exc), item_id),
                )
            self._event(
                item_id,
                "shopify.stage_failed",
                severity="ERROR",
                attempt_number=int(checkpoint.get("retry_count") or 0) + 1,
                duration_ms=int((time.monotonic() - upload_started) * 1000),
                image_count=len(image_paths),
                status="FAILED",
                outcome=active_stage,
                error_class=safe["error_class"],
                safe_summary=safe["safe_summary"],
                detail={"stage": active_stage, "last_completed_step": step},
                retention_class="BUSINESS",
            )
            raise

    def _linked_item(self, item_id: str) -> tuple[dict[str, Any], str]:
        item = db.get_item(self.db_file, item_id)
        if item is None:
            raise KeyError(f"Unknown Item ID: {item_id}")
        product_id = str(item.get("shopify_product_id") or "")
        if not product_id:
            raise ValueError("This Item has not been created in Shopify yet.")
        return item, product_id

    def publish_live(self, item_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        if not confirmed:
            raise PermissionError("Publishing live requires deliberate confirmation.")
        if not self.config.publication_id:
            raise ValueError(
                "Select a Shopify publication in Settings before publishing live."
            )
        item, product_id = self._linked_item(item_id)
        snapshot = self.client.product_snapshot(product_id)
        if snapshot is None:
            raise ValueError("The linked Shopify product no longer exists.")
        current = str(snapshot.get("status") or "").upper()
        status_result: dict[str, Any] = {
            "updated_at": str(snapshot.get("updatedAt") or "")
        }
        if current != "ACTIVE":
            status_result = self.client.set_product_status(product_id, "ACTIVE")
        self.client.publish_to_publication(product_id, self.config.publication_id)
        timestamp = db.now()
        with db.transaction(self.db_file) as connection:
            connection.execute(
                "UPDATE items SET upload_status='PUBLISHED',last_error='',updated_at=? WHERE item_id=?",
                (timestamp, item_id),
            )
            connection.execute(
                """UPDATE shopify_sync
                      SET status='PUBLISHED',product_status='ACTIVE',sync_state='IN_SYNC',
                          last_action='PUBLISH_LIVE',last_synced_at=?,remote_updated_at=?,
                          last_error='',deleted_at=NULL,archived_at=NULL
                    WHERE item_id=?""",
                (timestamp, str(status_result.get("updated_at") or timestamp), item_id),
            )
        self._event(
            item_id,
            "shopify.publish_completed",
            status="PUBLISHED",
            outcome="LIVE",
            retention_class="BUSINESS",
        )
        return {
            "item_id": item_id,
            "product_id": product_id,
            "status": "PUBLISHED",
            "admin_url": str(item.get("shopify_admin_url") or ""),
        }

    def restore_draft(self, item_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        if not confirmed:
            raise PermissionError("Restoring a Shopify draft requires confirmation.")
        item, product_id = self._linked_item(item_id)
        if self.config.publication_id:
            self.client.unpublish_from_publication(product_id, self.config.publication_id)
        result = self.client.set_product_status(product_id, "DRAFT")
        timestamp = db.now()
        with db.transaction(self.db_file) as connection:
            connection.execute(
                "UPDATE items SET upload_status='UPLOADED',last_error='',updated_at=? WHERE item_id=?",
                (timestamp, item_id),
            )
            connection.execute(
                """UPDATE shopify_sync
                      SET status='UPLOADED',product_status='DRAFT',sync_state='IN_SYNC',
                          last_action='RESTORE_DRAFT',last_synced_at=?,remote_updated_at=?,
                          last_error='',archived_at=NULL,deleted_at=NULL
                    WHERE item_id=?""",
                (timestamp, result.get("updated_at") or timestamp, item_id),
            )
        self._event(item_id, "shopify.draft_restored", status="DRAFT", outcome="RESTORED")
        return {"item_id": item_id, "product_id": product_id, "status": "DRAFT", "admin_url": item.get("shopify_admin_url", "")}

    def archive_product(self, item_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        if not confirmed:
            raise PermissionError("Archiving a Shopify product requires confirmation.")
        item, product_id = self._linked_item(item_id)
        if self.config.publication_id:
            self.client.unpublish_from_publication(product_id, self.config.publication_id)
        result = self.client.set_product_status(product_id, "ARCHIVED")
        timestamp = db.now()
        with db.transaction(self.db_file) as connection:
            connection.execute(
                "UPDATE items SET upload_status='ARCHIVED',last_error='',updated_at=? WHERE item_id=?",
                (timestamp, item_id),
            )
            connection.execute(
                """UPDATE shopify_sync
                      SET status='ARCHIVED',product_status='ARCHIVED',sync_state='IN_SYNC',
                          last_action='ARCHIVE',last_synced_at=?,remote_updated_at=?,
                          archived_at=?,last_error=''
                    WHERE item_id=?""",
                (timestamp, result.get("updated_at") or timestamp, timestamp, item_id),
            )
        self._event(item_id, "shopify.product_archived", status="ARCHIVED", outcome="COMPLETE")
        return {"item_id": item_id, "product_id": product_id, "status": "ARCHIVED", "admin_url": item.get("shopify_admin_url", "")}

    def delete_product(self, item_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        if not confirmed:
            raise PermissionError("Deleting a Shopify product requires confirmation.")
        item, product_id = self._linked_item(item_id)
        self.client.delete_product(product_id)
        timestamp = db.now()
        with db.transaction(self.db_file) as connection:
            connection.execute(
                "UPDATE items SET upload_status='DELETED',last_error='',updated_at=? WHERE item_id=?",
                (timestamp, item_id),
            )
            connection.execute(
                """UPDATE shopify_sync
                      SET status='DELETED',product_status='DELETED',sync_state='REMOTE_DELETED',
                          last_action='DELETE',last_synced_at=?,deleted_at=?,last_error=''
                    WHERE item_id=?""",
                (timestamp, timestamp, item_id),
            )
        self._event(item_id, "shopify.product_deleted", status="DELETED", outcome="PERMANENT")
        return {"item_id": item_id, "product_id": product_id, "status": "DELETED"}

    def sync_product(self, item_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        if not confirmed:
            raise PermissionError("Synchronizing a Shopify product requires confirmation.")
        item, product_id = self._linked_item(item_id)
        snapshot = self.client.product_snapshot(product_id)
        if snapshot is None:
            timestamp = db.now()
            with db.transaction(self.db_file) as connection:
                connection.execute(
                    "UPDATE shopify_sync SET sync_state='REMOTE_DELETED',status='DELETED',last_action='RECONCILE',last_synced_at=? WHERE item_id=?",
                    (timestamp, item_id),
                )
            return {"item_id": item_id, "product_id": product_id, "status": "REMOTE_DELETED"}
        self.client.update_product(item, product_id)
        variant_id = str(item.get("shopify_variant_id") or "")
        if not variant_id:
            raise ValueError("The linked Shopify Variant GID is missing; reconcile this Item before syncing.")
        self.client.configure_variant(item, product_id, variant_id)
        inventory_item_id = str(item.get("shopify_inventory_item_id") or "")
        desired = 1
        if inventory_item_id:
            current_quantity = self.client.inventory_quantity(inventory_item_id)
            key = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"snapims:{item_id}:inventory-sync:{desired}",
                )
            )
            if current_quantity is None:
                self.client.activate_inventory(
                    inventory_item_id,
                    desired,
                    key,
                )
            elif current_quantity != desired:
                self.client.set_inventory_quantity(
                    inventory_item_id,
                    desired,
                    current_quantity,
                    key,
                )
        timestamp = db.now()
        remote_status = str(snapshot.get("status") or "").upper()
        with db.transaction(self.db_file) as connection:
            connection.execute(
                "UPDATE items SET last_error='',updated_at=? WHERE item_id=?",
                (timestamp, item_id),
            )
            connection.execute(
                """UPDATE shopify_sync
                      SET sync_state='IN_SYNC',last_action='SYNC',last_synced_at=?,
                          remote_updated_at=?,product_status=?,last_error=''
                    WHERE item_id=?""",
                (timestamp, str(snapshot.get("updatedAt") or timestamp), remote_status, item_id),
            )
        self._event(item_id, "shopify.product_synced", status="SYNCED", outcome="IN_SYNC")
        return {"item_id": item_id, "product_id": product_id, "status": "SYNCED", "admin_url": item.get("shopify_admin_url", "")}

    @staticmethod
    def _remote_values(snapshot: dict[str, Any]) -> dict[str, Any]:
        variants = ((snapshot.get("variants") or {}).get("nodes") or [])
        variant = variants[0] if variants else {}
        price_text = str(variant.get("price") or "0")
        try:
            price_cents = int(round(float(price_text) * 100))
        except ValueError:
            price_cents = 0
        return {
            "title": str(snapshot.get("title") or ""),
            "description": str(snapshot.get("descriptionHtml") or ""),
            "vendor": str(snapshot.get("vendor") or ""),
            "product_type": str(snapshot.get("productType") or ""),
            "tags": ", ".join(str(tag) for tag in (snapshot.get("tags") or [])),
            "barcode": str(variant.get("barcode") or ""),
            "price_cents": price_cents,
            "sku": str(variant.get("sku") or ""),
            "product_status": str(snapshot.get("status") or "").upper(),
            "remote_updated_at": str(snapshot.get("updatedAt") or ""),
        }

    @staticmethod
    def _differences(item: dict[str, Any], remote: dict[str, Any]) -> dict[str, dict[str, Any]]:
        differences: dict[str, dict[str, Any]] = {}
        for field in ("title", "vendor", "product_type", "tags", "barcode", "price_cents", "sku"):
            local_value = item.get(field)
            remote_value = remote.get(field)
            if field == "tags":
                normalize = lambda value: sorted(
                    {part.strip().casefold() for part in str(value or "").split(",") if part.strip()}
                )
                equal = normalize(local_value) == normalize(remote_value)
            else:
                equal = str(local_value or "") == str(remote_value or "")
            if not equal:
                differences[field] = {"snapims": local_value, "shopify": remote_value}
        return differences

    def reconcile_product(self, item_id: str) -> dict[str, Any]:
        item, product_id = self._linked_item(item_id)
        snapshot = self.client.product_snapshot(product_id)
        timestamp = db.now()
        if snapshot is None:
            status = "REMOTE_DELETED"
            product_status = "DELETED"
            differences: dict[str, dict[str, Any]] = {
                "product": {"snapims": product_id, "shopify": None}
            }
            remote: dict[str, Any] = {}
        else:
            remote = self._remote_values(snapshot)
            product_status = remote["product_status"]
            differences = self._differences(item, remote)
            status = "CONFLICT" if differences else "IN_SYNC"
        with db.transaction(self.db_file) as connection:
            connection.execute(
                """UPDATE shopify_sync SET sync_state=?,product_status=?,last_action='RECONCILE',
                          last_synced_at=?,remote_updated_at=?,conflict_json=?,last_error=''
                    WHERE item_id=?""",
                (
                    status,
                    product_status,
                    timestamp,
                    str(remote.get("remote_updated_at") or ""),
                    json.dumps(differences, sort_keys=True, default=str),
                    item_id,
                ),
            )
        self._event(
            item_id,
            "shopify.reconciliation_completed",
            severity="WARNING" if differences else "INFO",
            status=status,
            outcome=product_status,
            detail={"difference_fields": sorted(differences)},
        )
        return {
            "item_id": item_id,
            "product_id": product_id,
            "status": status,
            "differences": differences,
            "remote": snapshot or {},
        }

    def _controlled_remote_tags(self, labels: str) -> tuple[list[str], list[str]]:
        requested = [part.strip() for part in str(labels or "").split(",") if part.strip()]
        resolved: list[str] = []
        unknown: list[str] = []
        with db.connect(self.db_file) as connection:
            for label in requested:
                row = connection.execute(
                    """SELECT td.canonical_label FROM tag_definitions td
                       LEFT JOIN tag_aliases ta ON ta.tag_id=td.tag_id
                       WHERE td.canonical_label=? COLLATE NOCASE
                          OR ta.alias=? COLLATE NOCASE
                       ORDER BY td.sort_order LIMIT 1""",
                    (label, label),
                ).fetchone()
                if row is None:
                    unknown.append(label)
                elif str(row[0]) not in resolved:
                    resolved.append(str(row[0]))
        return resolved, unknown

    def keep_shopify(self, item_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        if not confirmed:
            raise PermissionError("Keeping Shopify values requires confirmation.")
        item, product_id = self._linked_item(item_id)
        snapshot = self.client.product_snapshot(product_id)
        if snapshot is None:
            raise ValueError("The linked Shopify product no longer exists.")
        remote = self._remote_values(snapshot)
        allowed = {
            key: remote[key]
            for key in ("title", "description", "vendor", "product_type", "barcode", "price_cents")
        }
        controlled_tags, unmapped_tags = self._controlled_remote_tags(remote["tags"])
        allowed["tags"] = ", ".join(controlled_tags)
        db.update_item(self.db_file, item_id, allowed, source="SHOPIFY_KEEP_REMOTE")
        timestamp = db.now()
        conflicts = (
            {"tags": {"snapims": allowed["tags"], "shopify": remote["tags"], "unmapped": unmapped_tags}}
            if unmapped_tags else {}
        )
        state = "CONFLICT" if conflicts else "IN_SYNC"
        with db.transaction(self.db_file) as connection:
            connection.execute(
                """UPDATE shopify_sync SET sync_state=?,product_status=?,
                          last_action='KEEP_SHOPIFY',last_synced_at=?,remote_updated_at=?,
                          conflict_json=?,last_error='' WHERE item_id=?""",
                (state, remote["product_status"], timestamp, remote["remote_updated_at"],
                 json.dumps(conflicts, sort_keys=True), item_id),
            )
        self._event(
            item_id, "shopify.remote_values_kept",
            severity="WARNING" if conflicts else "INFO", status=state, outcome="SHOPIFY",
            detail={"unmapped_tags": unmapped_tags},
        )
        return {
            "item_id": item_id, "product_id": product_id, "status": state,
            "source": "SHOPIFY", "unmapped_tags": unmapped_tags,
        }

    def merge_remote(self, item_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        if not confirmed:
            raise PermissionError("Merging Shopify values requires confirmation.")
        item, product_id = self._linked_item(item_id)
        snapshot = self.client.product_snapshot(product_id)
        if snapshot is None:
            raise ValueError("The linked Shopify product no longer exists.")
        remote = self._remote_values(snapshot)
        updates: dict[str, Any] = {}
        for field in ("title", "description", "vendor", "product_type", "barcode"):
            if not str(item.get(field) or "").strip() and str(remote.get(field) or "").strip():
                updates[field] = remote[field]
        if not int(item.get("price_cents") or 0) and int(remote.get("price_cents") or 0):
            updates["price_cents"] = remote["price_cents"]
        local_tags = {part.strip() for part in str(item.get("tags") or "").split(",") if part.strip()}
        controlled_remote_tags, unmapped_tags = self._controlled_remote_tags(remote.get("tags") or "")
        remote_tags = set(controlled_remote_tags)
        merged_tags = sorted(local_tags | remote_tags, key=str.casefold)
        if merged_tags != sorted(local_tags, key=str.casefold):
            updates["tags"] = ", ".join(merged_tags)
        if updates:
            db.update_item(self.db_file, item_id, updates, source="SHOPIFY_MERGE")
        refreshed = db.get_item(self.db_file, item_id) or item
        differences = self._differences(refreshed, remote)
        if unmapped_tags:
            differences["tags"] = {
                "snapims": refreshed.get("tags") or "",
                "shopify": remote.get("tags") or "",
                "unmapped": unmapped_tags,
            }
        state = "CONFLICT" if differences else "IN_SYNC"
        timestamp = db.now()
        with db.transaction(self.db_file) as connection:
            connection.execute(
                """UPDATE shopify_sync SET sync_state=?,product_status=?,last_action='MERGE',
                          last_synced_at=?,remote_updated_at=?,conflict_json=?,last_error=''
                    WHERE item_id=?""",
                (state, remote["product_status"], timestamp, remote["remote_updated_at"],
                 json.dumps(differences, sort_keys=True, default=str), item_id),
            )
        self._event(
            item_id, "shopify.values_merged",
            severity="WARNING" if differences else "INFO",
            status=state, outcome="MERGED",
            detail={"updated_fields": sorted(updates), "remaining_conflicts": sorted(differences)},
        )
        return {
            "item_id": item_id, "product_id": product_id, "status": state,
            "updated_fields": sorted(updates), "differences": differences,
        }

    def _record_outbound_request(
        self,
        attempt: int,
        item_id: str,
        *,
        step: str,
        idempotency_key: str,
        request_hash: str,
        request_payload: dict[str, Any],
    ) -> None:
        """Persist the logical request identity before the remote mutation."""
        detail = {
            "logical_attempt_id": f"{item_id}:{step}",
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "request": request_payload,
            "outcome": "REQUESTED",
        }
        with db.transaction(self.db_file) as connection:
            connection.execute(
                "UPDATE shopify_sync SET idempotency_key=? WHERE item_id=?",
                (idempotency_key, item_id),
            )
            connection.execute(
                "UPDATE upload_attempts SET step=?,response_json=? WHERE attempt_id=?",
                (f"{step}_requested", json.dumps(detail, sort_keys=True), attempt),
            )

    def _record_outbound_outcome(self, attempt: int, *, outcome: str) -> None:
        with db.transaction(self.db_file) as connection:
            row = connection.execute(
                "SELECT response_json FROM upload_attempts WHERE attempt_id=?",
                (attempt,),
            ).fetchone()
            detail = json.loads(str(row[0] or "{}")) if row else {}
            detail["outcome"] = outcome
            connection.execute(
                "UPDATE upload_attempts SET response_json=? WHERE attempt_id=?",
                (json.dumps(detail, sort_keys=True), attempt),
            )

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
        self._event(
            item_id,
            "shopify.stage_completed",
            status=step.upper(),
            outcome="SUCCEEDED",
            detail={"stage": step},
            retention_class="BUSINESS",
        )
