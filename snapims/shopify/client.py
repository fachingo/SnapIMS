from __future__ import annotations

import json
import mimetypes
import secrets
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from snapims import __version__
from snapims.config import ShopifyConfig
from snapims.shopify.auth import ShopifyTokenManager, ShopifyCredentialError, ShopifyTokenError
from snapims.money import final_price_cents, format_price_cents


class ShopifyAPIError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        authentication: bool = False,
        rejected_token: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.authentication = authentication
        self.rejected_token = rejected_token


class ShopifyTransport(Protocol):
    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]: ...
    def upload(self, url: str, parameters: list[dict[str, str]], file_path: Path) -> None: ...


class HTTPShopifyTransport:
    def __init__(
        self,
        config: ShopifyConfig,
        timeout: int = 60,
        *,
        token_manager: ShopifyTokenManager | None = None,
    ) -> None:
        self.config = config
        self.timeout = timeout
        self.endpoint = f"https://{config.store_domain}/admin/api/{config.api_version}/graphql.json"
        self.token_manager = token_manager
        if self.token_manager is None and config.auth_mode == "client_credentials":
            self.token_manager = ShopifyTokenManager(
                credentials=(config.store_domain, config.client_id, config.client_secret, config.access_token)
            )

    def _access_token(self, *, force_refresh: bool = False) -> str:
        if self.token_manager is not None:
            try:
                return self.token_manager.get_access_token(force_refresh=force_refresh)
            except (ShopifyCredentialError, ShopifyTokenError) as exc:
                raise ShopifyAPIError(str(exc), authentication=True) from exc
        if not self.config.access_token:
            raise ShopifyAPIError("Shopify authentication is not configured.", authentication=True)
        return self.config.access_token

    def _graphql_once(self, query: str, variables: dict[str, Any], *, force_refresh: bool = False) -> dict[str, Any]:
        access_token = self._access_token(force_refresh=force_refresh)
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps({"query": query, "variables": variables}).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": access_token,
                "User-Agent": f"SnapIMS/{__version__}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode())
                if not isinstance(payload, dict):
                    raise ShopifyAPIError("Shopify returned a non-object response")
                return payload
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise ShopifyAPIError(
                    "Shopify authentication expired or was rejected.",
                    status_code=401,
                    authentication=True,
                    rejected_token=access_token,
                ) from exc
            if exc.code == 403:
                raise ShopifyAPIError(
                    "Shopify denied this operation. Check the app's Admin API scopes.",
                    status_code=403,
                ) from exc
            if exc.code == 429:
                raise ShopifyAPIError("Shopify rate limit reached; retry later.", status_code=429) from exc
            raise ShopifyAPIError(f"Shopify returned HTTP {exc.code}", status_code=exc.code) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ShopifyAPIError("Shopify connection failed or returned an invalid response.") from exc

    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._graphql_once(query, variables)
        except ShopifyAPIError as exc:
            if not exc.authentication or self.token_manager is None:
                raise
            # One bounded refresh-and-retry for authentication failure only.
            self.token_manager.get_access_token(
                force_refresh=True, rejected_token=exc.rejected_token
            )
            return self._graphql_once(query, variables)

    def upload(self, url: str, parameters: list[dict[str, str]], file_path: Path) -> None:
        boundary = f"----snapims-{secrets.token_hex(12)}"
        body = bytearray()
        for parameter in parameters:
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(f'Content-Disposition: form-data; name="{parameter["name"]}"\r\n\r\n'.encode())
            body.extend(parameter["value"].encode())
            body.extend(b"\r\n")
        mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'.encode())
        body.extend(f"Content-Type: {mime}\r\n\r\n".encode())
        body.extend(file_path.read_bytes())
        body.extend(f"\r\n--{boundary}--\r\n".encode())
        request = urllib.request.Request(url, data=bytes(body), method="POST", headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if response.status not in {200, 201, 204}:
                    raise ShopifyAPIError(f"Staged upload returned HTTP {response.status}")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            raise ShopifyAPIError(f"Staged upload failed for {file_path.name}") from exc


class ShopifyClient:
    def __init__(self, config: ShopifyConfig, transport: ShopifyTransport | None = None) -> None:
        self.config = config
        self.transport = transport or HTTPShopifyTransport(config)

    def _call(self, query: str, variables: dict[str, Any], field: str) -> dict[str, Any]:
        payload = self.transport.graphql(query, variables)
        if payload.get("errors"):
            raise ShopifyAPIError("; ".join(error.get("message", "GraphQL error") for error in payload["errors"]))
        data = payload.get("data", {}).get(field)
        if data is None:
            raise ShopifyAPIError(f"Shopify response did not contain {field}")
        if not isinstance(data, dict):
            raise ShopifyAPIError(f"Shopify response field {field} was not an object")
        user_errors = data.get("userErrors") or []
        if user_errors:
            raise ShopifyAPIError("; ".join(error.get("message", "Shopify user error") for error in user_errors))
        return data

    def find_variant_by_sku(self, sku: str) -> dict[str, Any] | None:
        payload = self.transport.graphql(
            """query VariantBySku($query:String!){productVariants(first:2,query:$query){nodes{id sku inventoryItem{id} product{id title status}}}}""",
            {"query": f"sku:{sku}"},
        )
        nodes = payload.get("data", {}).get("productVariants", {}).get("nodes", [])
        if len(nodes) > 1:
            raise ShopifyAPIError(
                f"Shopify returned multiple variants for exact SKU {sku}; manual reconciliation required"
            )
        return nodes[0] if nodes else None

    def create_draft_product(self, item: dict[str, Any]) -> dict[str, str]:
        data = self._call(
            """mutation CreateDraft($product:ProductCreateInput!){productCreate(product:$product){product{id variants(first:1){nodes{id inventoryItem{id}}}} userErrors{field message}}}""",
            {"product": {"title": item["title"], "descriptionHtml": item["description"], "vendor": item["vendor"], "productType": item["product_type"], "tags": [tag.strip() for tag in item["tags"].split(",") if tag.strip()], "status": "DRAFT"}},
            "productCreate",
        )
        product = data["product"]
        variant = product["variants"]["nodes"][0]
        return {"product_id": product["id"], "variant_id": variant["id"], "inventory_item_id": variant["inventoryItem"]["id"]}

    def configure_variant(self, item: dict[str, Any], product_id: str, variant_id: str, *, allow_incomplete: bool = False) -> None:
        variant: dict[str, Any] = {
            "id": variant_id,
            "taxable": True,
            "inventoryItem": {
                "sku": item["sku"],
                "tracked": True,
                "requiresShipping": True,
                "measurement": {
                    "weight": {
                        "value": 250,
                        "unit": "GRAMS",
                    }
                },
            },
        }
        if item.get("price_cents") is not None:
            final_price = final_price_cents(int(item["price_cents"]), item.get("discount_percent") or 0)
            variant["price"] = format_price_cents(final_price)
        elif not allow_incomplete:
            raise ValueError("Price is required unless the operator explicitly attempts an incomplete Shopify draft.")
        if item["barcode"]:
            variant["barcode"] = item["barcode"]
        self._call(
            """mutation ConfigureVariant($productId:ID!,$variants:[ProductVariantsBulkInput!]!){productVariantsBulkUpdate(productId:$productId,variants:$variants){productVariants{id} userErrors{field message}}}""",
            {"productId": product_id, "variants": [variant]},
            "productVariantsBulkUpdate",
        )

    def activate_inventory(
        self, inventory_item_id: str, quantity: int, idempotency_key: str
    ) -> None:
        self._call(
            """mutation ActivateInventory($inventoryItemId:ID!,$locationId:ID!,$available:Int!,$idempotencyKey:String!){inventoryActivate(inventoryItemId:$inventoryItemId,locationId:$locationId,available:$available) @idempotent(key:$idempotencyKey){inventoryLevel{id} userErrors{field message}}}""",
            {
                "inventoryItemId": inventory_item_id,
                "locationId": self.config.location_id,
                "available": quantity,
                "idempotencyKey": idempotency_key,
            },
            "inventoryActivate",
        )


    def set_inventory_quantity(
        self,
        inventory_item_id: str,
        quantity: int,
        current_quantity: int,
        idempotency_key: str,
    ) -> None:
        self._call(
            """mutation SetInventory($input:InventorySetQuantitiesInput!,$idempotencyKey:String!){inventorySetQuantities(input:$input) @idempotent(key:$idempotencyKey){inventoryAdjustmentGroup{createdAt} userErrors{field message code}}}""",
            {
                "input": {
                    "name": "available",
                    "reason": "correction",
                    "referenceDocumentUri": f"snapims://inventory/{inventory_item_id}",
                    "quantities": [
                        {
                            "inventoryItemId": inventory_item_id,
                            "locationId": self.config.location_id,
                            "quantity": quantity,
                            "changeFromQuantity": current_quantity,
                        }
                    ],
                },
                "idempotencyKey": idempotency_key,
            },
            "inventorySetQuantities",
        )


    def inventory_quantity(self, inventory_item_id: str) -> int | None:
        payload = self.transport.graphql(
            """query InventoryQuantity($id:ID!){inventoryItem(id:$id){inventoryLevels(first:50){nodes{location{id} quantities(names:[\"available\"]){name quantity}}}}}""",
            {"id": inventory_item_id},
        )
        nodes = payload.get("data", {}).get("inventoryItem", {}).get("inventoryLevels", {}).get("nodes", [])
        for node in nodes:
            if node.get("location", {}).get("id") != self.config.location_id:
                continue
            for quantity in node.get("quantities", []):
                if quantity.get("name") == "available":
                    return int(quantity.get("quantity", 0))
        return None

    def stage_images(self, image_paths: list[Path]) -> list[dict[str, Any]]:
        inputs = [{"filename": path.name, "mimeType": mimetypes.guess_type(path.name)[0] or "image/jpeg", "httpMethod": "POST", "resource": "PRODUCT_IMAGE"} for path in image_paths]
        data = self._call(
            """mutation StageImages($input:[StagedUploadInput!]!){stagedUploadsCreate(input:$input){stagedTargets{url resourceUrl parameters{name value}} userErrors{field message}}}""",
            {"input": inputs},
            "stagedUploadsCreate",
        )
        targets = data["stagedTargets"] or []
        if len(targets) != len(image_paths):
            raise ShopifyAPIError("Shopify returned the wrong number of staged upload targets")
        return targets

    def upload_staged_images(self, image_paths: list[Path], targets: list[dict[str, Any]]) -> list[str]:
        for path, target in zip(image_paths, targets, strict=True):
            self.transport.upload(target["url"], target["parameters"], path)
        return [target["resourceUrl"] for target in targets]

    def attach_media(
        self, product_id: str, resource_urls: list[str], media_identifiers: list[str]
    ) -> None:
        if len(resource_urls) != len(media_identifiers):
            raise ShopifyAPIError("Shopify media identity count did not match staged uploads")
        media = [
            {"originalSource": url, "alt": identifier, "mediaContentType": "IMAGE"}
            for url, identifier in zip(resource_urls, media_identifiers, strict=True)
        ]
        self._call(
            """mutation AttachMedia($product:ProductUpdateInput!,$media:[CreateMediaInput!]){productUpdate(product:$product,media:$media){product{id} userErrors{field message}}}""",
            {"product": {"id": product_id}, "media": media},
            "productUpdate",
        )

    def media_records(self, product_id: str) -> list[dict[str, str]]:
        payload = self.transport.graphql(
            """query MediaStatus($id:ID!){product(id:$id){media(first:100){nodes{id alt preview{status}}}}}""",
            {"id": product_id},
        )
        nodes = payload.get("data", {}).get("product", {}).get("media", {}).get("nodes", [])
        return [
            {
                "id": str(node.get("id") or ""),
                "alt": str(node.get("alt") or ""),
                "status": str(node.get("preview", {}).get("status", "UNKNOWN")),
            }
            for node in nodes
        ]

    def media_status(self, product_id: str) -> list[str]:
        return [record["status"] for record in self.media_records(product_id)]

    def product_snapshot(self, product_id: str) -> dict[str, Any] | None:
        payload = self.transport.graphql(
            """query SnapIMSProduct($id:ID!){product(id:$id){id title handle status updatedAt vendor productType tags descriptionHtml variants(first:1){nodes{id price barcode sku inventoryItem{id}}}}}""",
            {"id": product_id},
        )
        product = payload.get("data", {}).get("product")
        return dict(product) if isinstance(product, dict) else None

    def update_product(self, item: dict[str, Any], product_id: str) -> None:
        self._call(
            """mutation UpdateProduct($product:ProductUpdateInput!){productUpdate(product:$product){product{id status updatedAt} userErrors{field message}}}""",
            {
                "product": {
                    "id": product_id,
                    "title": item["title"],
                    "descriptionHtml": item["description"],
                    "vendor": item["vendor"],
                    "productType": item["product_type"],
                    "tags": [tag.strip() for tag in item["tags"].split(",") if tag.strip()],
                }
            },
            "productUpdate",
        )

    def set_product_status(self, product_id: str, status: str) -> dict[str, str]:
        normalized = status.strip().upper()
        if normalized not in {"DRAFT", "ACTIVE", "ARCHIVED"}:
            raise ShopifyAPIError(f"Unsupported Shopify product status: {status}")
        data = self._call(
            """mutation SetProductStatus($product:ProductUpdateInput!){productUpdate(product:$product){product{id status updatedAt} userErrors{field message}}}""",
            {"product": {"id": product_id, "status": normalized}},
            "productUpdate",
        )
        product = data.get("product") or {}
        return {
            "product_id": str(product.get("id") or product_id),
            "status": str(product.get("status") or normalized),
            "updated_at": str(product.get("updatedAt") or ""),
        }

    def list_publications(self) -> list[dict[str, Any]]:
        payload = self.transport.graphql(
            """query SnapIMSPublications{publications(first:50){nodes{id name autoPublish supportsFuturePublishing catalog{title}}}}""",
            {},
        )
        nodes = payload.get("data", {}).get("publications", {}).get("nodes", [])
        return [dict(node) for node in nodes if isinstance(node, dict)]

    def publish_to_publication(self, product_id: str, publication_id: str) -> None:
        if not publication_id.startswith("gid://shopify/Publication/"):
            raise ShopifyAPIError("A verified Shopify publication is required before publishing live.")
        self._call(
            """mutation PublishProduct($id:ID!,$input:[PublicationInput!]!){publishablePublish(id:$id,input:$input){publishable{availablePublicationsCount{count}} userErrors{field message}}}""",
            {"id": product_id, "input": [{"publicationId": publication_id}]},
            "publishablePublish",
        )

    def unpublish_from_publication(self, product_id: str, publication_id: str) -> None:
        if not publication_id.startswith("gid://shopify/Publication/"):
            return
        self._call(
            """mutation UnpublishProduct($id:ID!,$input:[PublicationInput!]!){publishableUnpublish(id:$id,input:$input){publishable{availablePublicationsCount{count}} userErrors{field message}}}""",
            {"id": product_id, "input": [{"publicationId": publication_id}]},
            "publishableUnpublish",
        )

    def delete_product(self, product_id: str) -> None:
        self._call(
            """mutation DeleteProduct($input:ProductDeleteInput!){productDelete(input:$input){deletedProductId userErrors{field message}}}""",
            {"input": {"id": product_id}},
            "productDelete",
        )
