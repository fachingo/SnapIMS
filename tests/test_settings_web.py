from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from snapims.auth import generate_secret, hash_password
from snapims.provider_probes import ModelProbeResult
from snapims.settings import ConfigurationService
from snapims.web.app import app

PASSWORD = "correct horse battery staple"


def csrf(response_text: str) -> str:
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', response_text)
    assert match, response_text
    return match.group(1)


def configure_stored_auth(monkeypatch: pytest.MonkeyPatch) -> ConfigurationService:
    for key in (
        "SNAPIMS_AUTH_SECRET",
        "SNAPIMS_ADMIN_PASSWORD_HASH",
        "SNAPIMS_ADMIN_USERNAME",
        "SNAPIMS_SESSION_GENERATION",
        "OPENAI_API_KEY",
        "SHOPIFY_ADMIN_ACCESS_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)
    service = ConfigurationService.load_runtime()
    service.save_secrets(
        "security",
        {
            "SNAPIMS_AUTH_SECRET": generate_secret(),
            "SNAPIMS_ADMIN_PASSWORD_HASH": hash_password(PASSWORD),
        },
    )
    service.save_nonsecret(
        "security",
        {
            "SNAPIMS_ADMIN_USERNAME": "admin",
            "SNAPIMS_SESSION_GENERATION": "1",
        },
    )
    return service


def login(client: TestClient) -> None:
    page = client.get("/login")
    response = client.post(
        "/login",
        data={
            "csrf_token": csrf(page.text),
            "username": "admin",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 200
    assert "/login" not in str(response.url)


def test_settings_page_has_all_sections_and_masked_secret(
    data_paths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = configure_stored_auth(monkeypatch)
    stored_key = "sk-stored-must-never-render"
    service.save_secrets("recognition", {"OPENAI_API_KEY": stored_key})

    with TestClient(app) as client:
        login(client)
        response = client.get("/settings")

    assert response.status_code == 200
    for heading in (
        "General",
        "Recognition",
        "Shopify",
        "Movie Data",
        "Infrastructure",
        "Security",
        "Backup and Retention",
    ):
        assert heading in response.text
    assert "secret store" in response.text
    assert "Configured — enter a replacement" in response.text
    assert stored_key not in response.text
    assert service.secret_file.read_text(encoding="utf-8").find(stored_key) >= 0


def test_authenticated_secret_save_never_echoes_secret(
    data_paths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = configure_stored_auth(monkeypatch)
    new_key = "sk-browser-save-never-echo"
    with TestClient(app) as client:
        login(client)
        page = client.get("/settings")
        response = client.post(
            "/settings/recognition/secrets",
            data={
                "csrf_token": csrf(page.text),
                "OPENAI_API_KEY": new_key,
                "current_password": PASSWORD,
            },
        )
        events = client.get("/api/diagnostics/events")

    assert response.status_code == 200
    assert new_key not in response.text
    assert new_key not in str(response.url)
    assert new_key not in events.text
    assert service.value("OPENAI_API_KEY") == new_key


def test_unsaved_openai_test_secret_is_discarded_and_not_rendered(
    data_paths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = configure_stored_auth(monkeypatch)
    unsaved_key = "sk-unsaved-probe-only"

    class FakeProbe:
        def __init__(self, api_key: str, **_kwargs) -> None:
            assert api_key == unsaved_key

        def discover_models(self):
            return ["gpt-test-vision"]

        def probe_image_and_schema(self, model_id: str):
            return ModelProbeResult(
                model_id,
                True,
                True,
                "PASS",
                "Compatible.",
            )

    monkeypatch.setattr("snapims.web.app.OpenAIConnectionProbe", FakeProbe)
    with TestClient(app) as client:
        login(client)
        page = client.get("/settings")
        response = client.post(
            "/settings/recognition/test",
            data={
                "csrf_token": csrf(page.text),
                "OPENAI_API_KEY": unsaved_key,
                "test_action": "probe",
                "model_id": "gpt-test-vision",
            },
        )

    assert response.status_code == 200
    assert "gpt-test-vision" in response.text
    assert unsaved_key not in response.text
    assert unsaved_key not in str(response.url)
    assert service.value("OPENAI_API_KEY") == ""
    assert service.compatible_models() == ["gpt-test-vision"]


def test_unsaved_shopify_probe_returns_safe_identity_scope_and_locations(
    data_paths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = configure_stored_auth(monkeypatch)
    unsaved_token = "shpat-unsaved-never-render"

    class FakeShopifyProbe:
        def __init__(self, config) -> None:
            assert config.access_token == unsaved_token

        def run(self):
            return SimpleNamespace(
                shop={
                    "id": "gid://shopify/Shop/1",
                    "name": "Canada VHS",
                    "myshopify_domain": "canada-vhs.myshopify.com",
                },
                granted_scopes=("read_locations", "write_products"),
                missing_scopes=("write_inventory",),
                missing_by_capability={
                    "draft product creation": (),
                    "inventory activation": ("write_inventory",),
                },
                locations=(
                    {
                        "id": "gid://shopify/Location/2",
                        "name": "Warehouse",
                        "is_active": True,
                        "fulfills_online_orders": True,
                    },
                ),
            )

    monkeypatch.setattr("snapims.web.app.ShopifyConnectionProbe", FakeShopifyProbe)
    with TestClient(app) as client:
        login(client)
        page = client.get("/settings")
        response = client.post(
            "/settings/shopify/test",
            data={
                "csrf_token": csrf(page.text),
                "SHOPIFY_STORE_DOMAIN": "canada-vhs.myshopify.com",
                "SHOPIFY_ADMIN_ACCESS_TOKEN": unsaved_token,
                "SHOPIFY_API_VERSION": "2026-07",
            },
        )

    assert response.status_code == 200
    assert "Canada VHS" in response.text
    assert "write_inventory" in response.text
    assert "Warehouse" in response.text
    assert unsaved_token not in response.text
    assert service.value("SHOPIFY_ADMIN_ACCESS_TOKEN") == ""


def test_revoke_all_sessions_invalidates_current_cookie(
    data_paths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_stored_auth(monkeypatch)
    with TestClient(app) as client:
        login(client)
        page = client.get("/settings")
        response = client.post(
            "/settings/security/revoke",
            data={
                "csrf_token": csrf(page.text),
                "current_password": PASSWORD,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"].startswith("/login")
        after = client.get("/settings", follow_redirects=False)

    assert after.status_code == 303
    assert after.headers["location"] == "/login"
