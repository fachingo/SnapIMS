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
from snapims.money import final_price_cents, format_price_cents


class ShopifyAPIError(RuntimeError):
    pass


class ShopifyTransport(Protocol):
    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]: ...
    def upload(self, url: str, parameters: list[dict[str, str]], file_path: Path) -> None: ...


class HTTPShopifyTransport:
    def __init__(self, config: ShopifyConfig, timeout: int = 60) -> None:
        self.config = config
        self.timeout = timeout
        self.endpoint = f"https://{config.store_domain}/admin/api/{config.api_version}/graphql.json"

    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps({"query": query, "variables": variables}).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": self.config.access_token,
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
            raise ShopifyAPIError(f"Shopify returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ShopifyAPIError(f"Shopify connection failed: {exc}") from exc

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
            raise ShopifyAPIError(f"Staged upload failed for {file_path.name}: {exc}") from exc


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

    def configure_variant(self, item: dict[str, Any], product_id: str, variant_id: str) -> None:
        final_price = final_price_cents(
            int(item["price_cents"]), item.get("discount_percent") or 0
        )
        variant: dict[str, Any] = {
            "id": variant_id,
            "price": format_price_cents(final_price),
            "taxable": True,
            "inventoryItem": {"sku": item["sku"], "tracked": True, "requiresShipping": True},
        }
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

    def attach_media(self, product_id: str, resource_urls: list[str], title: str) -> None:
        media = [{"originalSource": url, "alt": f"{title} - image {index}", "mediaContentType": "IMAGE"} for index, url in enumerate(resource_urls, start=1)]
        self._call(
            """mutation AttachMedia($product:ProductUpdateInput!,$media:[CreateMediaInput!]){productUpdate(product:$product,media:$media){product{id} userErrors{field message}}}""",
            {"product": {"id": product_id}, "media": media},
            "productUpdate",
        )

    def media_status(self, product_id: str) -> list[str]:
        payload = self.transport.graphql(
            """query MediaStatus($id:ID!){product(id:$id){media(first:100){nodes{preview{status}}}}}""",
            {"id": product_id},
        )
        nodes = payload.get("data", {}).get("product", {}).get("media", {}).get("nodes", [])
        return [str(node.get("preview", {}).get("status", "UNKNOWN")) for node in nodes]
