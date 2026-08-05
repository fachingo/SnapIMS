from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from snapims import __version__
from snapims.config import ShopifyConfig
from snapims.shopify.client import ShopifyAPIError, ShopifyClient, ShopifyTransport

OPENAI_API_ROOT = "https://api.openai.com/v1"
ONE_PIXEL_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
    "AScY42YAAAAASUVORK5CYII="
)
MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ProviderProbeError(RuntimeError):
    pass


class JSONTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any] | None = None,
        timeout: float = 30,
    ) -> dict[str, Any]: ...


class HTTPJSONTransport:
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any] | None = None,
        timeout: float = 30,
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=(
                json.dumps(payload, separators=(",", ":")).encode("utf-8")
                if payload is not None
                else None
            ),
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                raw = response.read(2_000_000)
        except urllib.error.HTTPError as exc:
            raise ProviderProbeError(f"Provider returned HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ProviderProbeError("Provider connection failed.") from exc
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderProbeError("Provider returned malformed JSON.") from exc
        if not isinstance(result, dict):
            raise ProviderProbeError("Provider returned an unexpected response.")
        return result


@dataclass(frozen=True, slots=True)
class ModelProbeResult:
    model_id: str
    supports_images: bool
    supports_strict_schema: bool
    status: str
    safe_summary: str

    @property
    def compatible(self) -> bool:
        return (
            self.status == "PASS"
            and self.supports_images
            and self.supports_strict_schema
        )


class OpenAIConnectionProbe:
    def __init__(
        self,
        api_key: str,
        *,
        transport: JSONTransport | None = None,
        timeout: float = 30,
    ) -> None:
        self.api_key = api_key.strip()
        self.transport = transport or HTTPJSONTransport()
        self.timeout = max(1, min(float(timeout), 120))

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderProbeError("OpenAI API key is required.")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": f"SnapIMS/{__version__}",
        }

    def discover_models(self) -> list[str]:
        response = self.transport.request(
            "GET",
            f"{OPENAI_API_ROOT}/models",
            headers=self._headers(),
            timeout=self.timeout,
        )
        data = response.get("data")
        if not isinstance(data, list):
            raise ProviderProbeError("OpenAI model list was missing.")
        identifiers = {
            str(item.get("id"))
            for item in data
            if isinstance(item, dict)
            and MODEL_ID_PATTERN.fullmatch(str(item.get("id") or ""))
        }
        return sorted(identifiers)[:1000]

    def probe_image_and_schema(self, model_id: str) -> ModelProbeResult:
        model = model_id.strip()
        if not MODEL_ID_PATTERN.fullmatch(model):
            raise ProviderProbeError("Model ID has an invalid format.")
        payload = {
            "model": model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Return the image width as strict JSON.",
                        },
                        {
                            "type": "input_image",
                            "image_url": ONE_PIXEL_PNG,
                            "detail": "low",
                        },
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "snapims_capability_probe",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {"width": {"type": "integer"}},
                        "required": ["width"],
                        "additionalProperties": False,
                    },
                }
            },
            "max_output_tokens": 32,
        }
        try:
            response = self.transport.request(
                "POST",
                f"{OPENAI_API_ROOT}/responses",
                headers=self._headers(),
                payload=payload,
                timeout=self.timeout,
            )
        except ProviderProbeError as exc:
            return ModelProbeResult(
                model,
                False,
                False,
                "FAIL",
                str(exc),
            )
        if response.get("error"):
            return ModelProbeResult(
                model,
                False,
                False,
                "FAIL",
                "OpenAI rejected the bounded capability probe.",
            )
        status = str(response.get("status") or "completed")
        if status != "completed":
            return ModelProbeResult(
                model,
                False,
                False,
                "FAIL",
                "OpenAI did not complete the bounded capability probe.",
            )
        return ModelProbeResult(
            model,
            True,
            True,
            "PASS",
            "Image input and strict structured output are compatible.",
        )


SHOPIFY_CONNECTION_QUERY = """
query SnapIMSConnectionProbe {
  shop { id name myshopifyDomain }
  currentAppInstallation { accessScopes { handle } }
  locations(first: 50, includeInactive: true) {
    nodes { id name isActive fulfillsOnlineOrders }
  }
}
""".strip()

SHOPIFY_CAPABILITIES: dict[str, frozenset[str]] = {
    "shop identity": frozenset({"read_markets_home"}),
    "location discovery": frozenset({"read_locations"}),
    "draft product creation": frozenset({"write_products"}),
    "inventory reconciliation": frozenset({"read_inventory"}),
    "inventory activation": frozenset({"write_inventory"}),
}


@dataclass(frozen=True, slots=True)
class ShopifyProbeResult:
    shop: dict[str, str]
    granted_scopes: tuple[str, ...]
    missing_by_capability: dict[str, tuple[str, ...]]
    locations: tuple[dict[str, Any], ...]

    @property
    def missing_scopes(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    scope
                    for missing in self.missing_by_capability.values()
                    for scope in missing
                }
            )
        )


class ShopifyConnectionProbe:
    def __init__(
        self,
        config: ShopifyConfig,
        *,
        transport: ShopifyTransport | None = None,
    ) -> None:
        self.config = config
        self.client = ShopifyClient(config, transport=transport)

    def run(self) -> ShopifyProbeResult:
        if not self.config.store_domain.endswith(".myshopify.com"):
            raise ProviderProbeError("A valid .myshopify.com domain is required.")
        if not self.config.access_token:
            raise ProviderProbeError("Shopify Admin API token is required.")
        try:
            payload = self.client.transport.graphql(SHOPIFY_CONNECTION_QUERY, {})
        except ShopifyAPIError as exc:
            raise ProviderProbeError(str(exc)) from exc
        errors = payload.get("errors") or []
        if errors:
            raise ProviderProbeError(
                "; ".join(
                    str(error.get("message") or "Shopify GraphQL error")
                    for error in errors
                    if isinstance(error, dict)
                )
                or "Shopify GraphQL error."
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ProviderProbeError("Shopify response did not contain data.")
        shop = data.get("shop")
        installation = data.get("currentAppInstallation")
        locations = data.get("locations")
        if not isinstance(shop, dict) or not isinstance(installation, dict):
            raise ProviderProbeError("Shopify identity or access scopes were missing.")
        scopes = tuple(
            sorted(
                {
                    str(scope.get("handle"))
                    for scope in installation.get("accessScopes") or []
                    if isinstance(scope, dict) and scope.get("handle")
                }
            )
        )
        granted = set(scopes)
        missing = {
            capability: tuple(sorted(required - granted))
            for capability, required in SHOPIFY_CAPABILITIES.items()
        }
        nodes: list[Any] = []
        if isinstance(locations, dict):
            raw_nodes = locations.get("nodes")
            if isinstance(raw_nodes, list):
                nodes = raw_nodes
        safe_locations = tuple(
            {
                "id": str(node.get("id") or ""),
                "name": str(node.get("name") or ""),
                "is_active": bool(node.get("isActive")),
                "fulfills_online_orders": bool(node.get("fulfillsOnlineOrders")),
            }
            for node in nodes[:50]
            if isinstance(node, dict)
            and str(node.get("id") or "").startswith("gid://shopify/Location/")
        )
        return ShopifyProbeResult(
            shop={
                "id": str(shop.get("id") or ""),
                "name": str(shop.get("name") or ""),
                "myshopify_domain": str(shop.get("myshopifyDomain") or ""),
            },
            granted_scopes=scopes,
            missing_by_capability=missing,
            locations=safe_locations,
        )
