from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from snapims.auth import generate_secret, hash_password
from snapims.provider_probes import ModelProbeResult
from snapims.settings import ConfigurationService
from snapims.shopify.auth import ShopifyTokenError
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
        "SHOPIFY_CLIENT_ID",
        "SHOPIFY_CLIENT_SECRET",
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
    assert stored_key not in service.secret_file.read_text(encoding="utf-8")
    assert service.value("OPENAI_API_KEY") == stored_key


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
    unsaved_secret = "shpss_unsaved_never_render"

    class FakeShopifyProbe:
        def __init__(self, config, token_manager=None) -> None:
            assert config.client_id == "client_example_123"
            assert config.client_secret == unsaved_secret
            assert token_manager is not None

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
                    "draft product and media creation": (),
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
                authentication_mode="client_credentials",
                token_state="valid",
                token_expires_at="2026-08-05T18:00:00-06:00",
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
                "SHOPIFY_CLIENT_ID": "client_example_123",
                "SHOPIFY_CLIENT_SECRET": unsaved_secret,
                "SHOPIFY_API_VERSION": "2026-07",
            },
        )

    assert response.status_code == 200
    assert "Canada VHS" in response.text
    assert "write_inventory" in response.text
    assert "Warehouse" in response.text
    assert unsaved_secret not in response.text
    assert service.value("SHOPIFY_CLIENT_SECRET") == ""


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


def test_shopify_settings_use_client_credentials_and_no_manual_token_field(
    data_paths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_stored_auth(monkeypatch)
    with TestClient(app) as client:
        login(client)
        response = client.get("/settings")
    assert response.status_code == 200
    assert "Client ID" in response.text
    assert "Client Secret" in response.text
    assert "you do not paste an Admin API access token" in response.text
    assert "Unsaved Admin API token" not in response.text
    assert "Admin API token to save" not in response.text


def test_shopify_test_and_save_persists_credentials_without_rendering_secret(
    data_paths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = configure_stored_auth(monkeypatch)
    client_secret = "shpss_save_me_securely_123"

    class FakeManager:
        def __init__(self, *_args, **_kwargs) -> None:
            self.mode = "client_credentials"
            self.cache_file = data_paths.secrets / "fake-shopify-token-cache.enc"

        def clear(self) -> None:
            return None

        def get_access_token(self, **_kwargs) -> str:
            return "temporary-access-token"

        def status(self):
            return SimpleNamespace(
                mode="client_credentials",
                state="valid",
                expires_at="2026-08-05T18:00:00-06:00",
                granted_scopes=("read_locations",),
                last_refresh_at="2026-08-04T18:00:00-06:00",
                last_refresh_result="PASS",
            )

    class FakeProbe:
        def __init__(self, config, token_manager=None) -> None:
            assert config.client_secret == client_secret
            assert token_manager is not None

        def run(self):
            return SimpleNamespace(
                shop={
                    "id": "gid://shopify/Shop/1",
                    "name": "Canada VHS",
                    "myshopify_domain": "canada-vhs.myshopify.com",
                },
                granted_scopes=(
                    "read_inventory",
                    "read_locations",
                    "read_products",
                    "write_inventory",
                    "write_products",
                ),
                missing_scopes=(),
                missing_by_capability={"location discovery": ()},
                locations=(
                    {
                        "id": "gid://shopify/Location/2",
                        "name": "Warehouse",
                        "is_active": True,
                        "fulfills_online_orders": True,
                    },
                ),
                authentication_mode="client_credentials",
                token_state="valid",
                token_expires_at="2026-08-05T18:00:00-06:00",
            )

    monkeypatch.setattr("snapims.web.app.ShopifyTokenManager", FakeManager)
    monkeypatch.setattr("snapims.web.app.ShopifyConnectionProbe", FakeProbe)
    with TestClient(app) as client:
        login(client)
        page = client.get("/settings")
        response = client.post(
            "/settings/shopify/test",
            data={
                "csrf_token": csrf(page.text),
                "SHOPIFY_STORE_DOMAIN": "canada-vhs.myshopify.com",
                "SHOPIFY_CLIENT_ID": "client_example_123",
                "SHOPIFY_CLIENT_SECRET": client_secret,
                "SHOPIFY_API_VERSION": "2026-07",
                "current_password": PASSWORD,
                "save_after_test": "true",
            },
        )
    assert response.status_code == 200
    assert "Canada VHS" in response.text
    assert client_secret not in response.text
    assert client_secret not in service.secret_file.read_text(encoding="utf-8")
    assert service.value("SHOPIFY_CLIENT_SECRET") == client_secret
    assert service.value("SHOPIFY_CLIENT_ID") == "client_example_123"
    assert service.value("SHOPIFY_STORE_DOMAIN") == "canada-vhs.myshopify.com"



def test_shopify_test_and_save_rolls_back_when_persistent_refresh_fails(
    data_paths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = configure_stored_auth(monkeypatch)
    service.save_nonsecret(
        "shopify",
        {
            "SHOPIFY_STORE_DOMAIN": "old-store.myshopify.com",
            "SHOPIFY_CLIENT_ID": "old_client_123",
            "SHOPIFY_LOCATION_ID": "gid://shopify/Location/99",
            "SHOPIFY_API_VERSION": "2026-07",
            "SHOPIFY_DRAFT_ONLY": "true",
        },
    )
    service.save_secrets("shopify", {"SHOPIFY_CLIENT_SECRET": "shpss_old_secure_123"})

    class FakeManager:
        def __init__(self, *_args, **kwargs) -> None:
            self.cache_enabled = kwargs.get("cache_enabled", True)
            self.cache_file = data_paths.secrets / "fake-shopify-token-cache.enc"

        def clear(self) -> None:
            self.cache_file.unlink(missing_ok=True)

        def get_access_token(self, **_kwargs) -> str:
            if self.cache_enabled:
                raise ShopifyTokenError("simulated persistent refresh failure")
            return "temporary-test-token"

        def status(self):
            return SimpleNamespace(
                mode="client_credentials",
                state="not_requested",
                expires_at="",
                granted_scopes=(),
                last_refresh_at="",
                last_refresh_result="FAILED",
            )

    class FakeProbe:
        def __init__(self, config, token_manager=None) -> None:
            assert config.store_domain == "new-store.myshopify.com"
            assert token_manager is not None

        def run(self):
            return SimpleNamespace(
                shop={
                    "id": "gid://shopify/Shop/2",
                    "name": "New Store",
                    "myshopify_domain": "new-store.myshopify.com",
                },
                granted_scopes=(
                    "read_inventory",
                    "read_locations",
                    "read_products",
                    "write_inventory",
                    "write_products",
                ),
                missing_scopes=(),
                missing_by_capability={"location discovery": ()},
                locations=(),
                authentication_mode="client_credentials",
                token_state="valid",
                token_expires_at="2026-08-05T18:00:00-06:00",
            )

    monkeypatch.setattr("snapims.web.app.ShopifyTokenManager", FakeManager)
    monkeypatch.setattr("snapims.web.app.ShopifyConnectionProbe", FakeProbe)
    with TestClient(app) as client:
        login(client)
        page = client.get("/settings")
        response = client.post(
            "/settings/shopify/test",
            data={
                "csrf_token": csrf(page.text),
                "SHOPIFY_STORE_DOMAIN": "new-store.myshopify.com",
                "SHOPIFY_CLIENT_ID": "new_client_123",
                "SHOPIFY_CLIENT_SECRET": "shpss_new_secure_123",
                "SHOPIFY_API_VERSION": "2026-07",
                "current_password": PASSWORD,
                "save_after_test": "true",
            },
        )

    assert response.status_code == 200
    assert "simulated persistent refresh failure" in response.text
    assert service.value("SHOPIFY_STORE_DOMAIN") == "old-store.myshopify.com"
    assert service.value("SHOPIFY_CLIENT_ID") == "old_client_123"
    assert service.value("SHOPIFY_CLIENT_SECRET") == "shpss_old_secure_123"
    assert service.value("SHOPIFY_LOCATION_ID") == "gid://shopify/Location/99"


def test_shopify_location_selection_and_safe_connection_removal(
    data_paths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = configure_stored_auth(monkeypatch)
    service.save_nonsecret(
        "shopify",
        {
            "SHOPIFY_STORE_DOMAIN": "canada-vhs.myshopify.com",
            "SHOPIFY_CLIENT_ID": "client_example_123",
            "SHOPIFY_API_VERSION": "2026-07",
            "SHOPIFY_DRAFT_ONLY": "true",
        },
    )
    service.save_secrets(
        "shopify", {"SHOPIFY_CLIENT_SECRET": "shpss_remove_secure_123"}
    )

    class FakeManager:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def clear(self) -> None:
            return None

        def status(self):
            return SimpleNamespace(
                mode="client_credentials",
                state="valid",
                expires_at="",
                granted_scopes=(),
                last_refresh_at="",
                last_refresh_result="PASS",
            )

    class FakeProbe:
        def __init__(self, config, token_manager=None) -> None:
            assert config.store_domain == "canada-vhs.myshopify.com"
            assert token_manager is not None

        def run(self):
            return SimpleNamespace(
                shop={
                    "id": "gid://shopify/Shop/1",
                    "name": "Canada VHS",
                    "myshopify_domain": "canada-vhs.myshopify.com",
                },
                granted_scopes=(
                    "read_inventory",
                    "read_locations",
                    "read_products",
                    "write_inventory",
                    "write_products",
                ),
                missing_scopes=(),
                missing_by_capability={"location discovery": ()},
                locations=(
                    {
                        "id": "gid://shopify/Location/2",
                        "name": "Warehouse",
                        "is_active": True,
                        "fulfills_online_orders": True,
                    },
                ),
                authentication_mode="client_credentials",
                token_state="valid",
                token_expires_at="2026-08-05T18:00:00-06:00",
            )

    monkeypatch.setattr("snapims.web.app.ShopifyTokenManager", FakeManager)
    monkeypatch.setattr("snapims.web.app.ShopifyConnectionProbe", FakeProbe)
    with TestClient(app) as client:
        login(client)
        page = client.get("/settings")
        selected = client.post(
            "/settings/shopify/location",
            data={
                "csrf_token": csrf(page.text),
                "SHOPIFY_LOCATION_ID": "gid://shopify/Location/2",
            },
        )
        assert selected.status_code == 200
        assert service.value("SHOPIFY_LOCATION_ID") == "gid://shopify/Location/2"

        page = client.get("/settings")
        removed = client.post(
            "/settings/shopify/remove",
            data={
                "csrf_token": csrf(page.text),
                "current_password": PASSWORD,
                "confirmation": "REMOVE",
            },
        )
    assert removed.status_code == 200
    assert service.value("SHOPIFY_CLIENT_SECRET") == ""
    assert service.value("SHOPIFY_CLIENT_ID") == ""
    assert service.value("SHOPIFY_STORE_DOMAIN") == ""


def test_shopify_publication_selection_is_verified_and_persisted(
    data_paths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = configure_stored_auth(monkeypatch)
    service.save_nonsecret(
        "shopify",
        {
            "SHOPIFY_STORE_DOMAIN": "canada-vhs.myshopify.com",
            "SHOPIFY_CLIENT_ID": "client_example_123",
            "SHOPIFY_API_VERSION": "2026-07",
            "SHOPIFY_DRAFT_ONLY": "true",
            "SHOPIFY_LOCATION_ID": "gid://shopify/Location/2",
        },
    )
    service.save_secrets(
        "shopify", {"SHOPIFY_CLIENT_SECRET": "shpss_publication_secure_123"}
    )

    class FakeManager:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def status(self):
            return SimpleNamespace(
                mode="client_credentials",
                state="valid",
                expires_at="2026-08-05T20:00:00-06:00",
                granted_scopes=("read_publications", "write_publications"),
                last_refresh_at="",
                last_refresh_result="PASS",
            )

    class FakeProbe:
        def __init__(self, config, token_manager=None) -> None:
            assert config.store_domain == "canada-vhs.myshopify.com"

        def run(self):
            return SimpleNamespace(
                shop={
                    "id": "gid://shopify/Shop/1",
                    "name": "Canada VHS",
                    "myshopify_domain": "canada-vhs.myshopify.com",
                },
                granted_scopes=("read_publications", "write_publications"),
                missing_scopes=(),
                missing_by_capability={"live storefront publishing": ()},
                locations=(),
                publications=(
                    {
                        "id": "gid://shopify/Publication/9",
                        "name": "Online Store",
                        "auto_publish": False,
                        "supports_future_publishing": True,
                        "catalog_title": "Online Store",
                    },
                ),
                authentication_mode="client_credentials",
                token_state="valid",
                token_expires_at="2026-08-05T20:00:00-06:00",
            )

    monkeypatch.setattr("snapims.web.app.ShopifyTokenManager", FakeManager)
    monkeypatch.setattr("snapims.web.app.ShopifyConnectionProbe", FakeProbe)
    with TestClient(app) as client:
        login(client)
        page = client.get("/settings")
        response = client.post(
            "/settings/shopify/publication",
            data={
                "csrf_token": csrf(page.text),
                "SHOPIFY_PUBLICATION_ID": "gid://shopify/Publication/9",
            },
        )
    assert response.status_code == 200
    assert service.value("SHOPIFY_PUBLICATION_ID") == "gid://shopify/Publication/9"
