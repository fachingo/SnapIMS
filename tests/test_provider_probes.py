from __future__ import annotations

from typing import Any

from snapims.config import ShopifyConfig
from snapims.provider_probes import (
    ONE_PIXEL_PNG,
    OpenAIConnectionProbe,
    ShopifyConnectionProbe,
)


class FakeJSONTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request(self, method, url, *, headers, payload=None, timeout=30):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "payload": payload,
                "timeout": timeout,
            }
        )
        if url.endswith("/models"):
            return {
                "data": [
                    {"id": "gpt-vision-test"},
                    {"id": "gpt-text-test"},
                    {"id": "../invalid"},
                ]
            }
        return {"id": "resp-test", "status": "completed"}


def test_openai_discovery_and_bounded_image_schema_probe() -> None:
    transport = FakeJSONTransport()
    probe = OpenAIConnectionProbe(
        "sk-unsaved-browser-only",
        transport=transport,
        timeout=9,
    )
    assert probe.discover_models() == ["gpt-text-test", "gpt-vision-test"]
    result = probe.probe_image_and_schema("gpt-vision-test")

    assert result.compatible
    request = transport.calls[-1]
    assert request["url"].endswith("/responses")
    assert request["timeout"] == 9
    content = request["payload"]["input"][0]["content"]
    assert content[1]["image_url"] == ONE_PIXEL_PNG
    assert content[1]["detail"] == "low"
    assert request["payload"]["max_output_tokens"] == 32
    output_format = request["payload"]["text"]["format"]
    assert output_format["type"] == "json_schema"
    assert output_format["strict"] is True
    assert "sk-unsaved-browser-only" not in str(request["payload"])


class FakeShopifyTransport:
    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        assert "currentAppInstallation" in query
        assert "locations(first: 50" in query
        assert variables == {}
        return {
            "data": {
                "shop": {
                    "id": "gid://shopify/Shop/1",
                    "name": "Canada VHS",
                    "myshopifyDomain": "canada-vhs.myshopify.com",
                },
                "currentAppInstallation": {
                    "accessScopes": [
                        {"handle": "read_locations"},
                        {"handle": "write_products"},
                    ]
                },
                "locations": {
                    "nodes": [
                        {
                            "id": "gid://shopify/Location/2",
                            "name": "Warehouse",
                            "isActive": True,
                            "fulfillsOnlineOrders": True,
                        }
                    ]
                },
            }
        }

    def upload(self, url, parameters, file_path) -> None:
        raise AssertionError("Read-only connection probe must not upload.")


def test_shopify_probe_reports_identity_locations_and_exact_missing_scope() -> None:
    config = ShopifyConfig(
        store_domain="canada-vhs.myshopify.com",
        access_token="shpat-unsaved",
        location_id="",
        api_version="2026-07",
        draft_only=True,
    )
    result = ShopifyConnectionProbe(
        config,
        transport=FakeShopifyTransport(),
    ).run()

    assert result.shop["name"] == "Canada VHS"
    assert result.locations[0]["name"] == "Warehouse"
    assert result.granted_scopes == ("read_locations", "write_products")
    assert result.missing_by_capability["draft product and media creation"] == ()
    assert result.missing_by_capability["inventory activation"] == (
        "write_inventory",
    )
    assert result.missing_scopes == (
        "read_inventory",
        "read_products",
        "read_publications",
        "write_inventory",
        "write_publications",
    )
