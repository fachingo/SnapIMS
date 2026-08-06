from __future__ import annotations

import io
import json
import threading
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from snapims import db
from snapims.config import DataPaths, ShopifyConfig
from snapims.settings import ConfigurationService
from snapims.shopify.auth import (
    ShopifyCredentialError,
    ShopifyTokenManager,
    normalize_shop_domain,
)
from snapims.shopify.client import HTTPShopifyTransport, ShopifyAPIError


def service_for(tmp_path: Path) -> ConfigurationService:
    project = tmp_path / "project"
    project.mkdir()
    paths = DataPaths.from_root(tmp_path / "data").ensure()
    db.initialize(paths.db_file, paths=paths)
    service = ConfigurationService(
        project_path=project,
        paths=paths,
        process_environment={},
        legacy={},
    )
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
        "shopify", {"SHOPIFY_CLIENT_SECRET": "shpss_example_secret_123"}
    )
    return service


def test_domain_normalization_rejects_urls_and_paths() -> None:
    assert normalize_shop_domain("  Canada-VHS.myshopify.com ") == "canada-vhs.myshopify.com"
    for invalid in (
        "https://canada-vhs.myshopify.com",
        "canada-vhs.myshopify.com/admin",
        "canadavhs.ca",
        "",
    ):
        if invalid:
            with pytest.raises(ShopifyCredentialError):
                normalize_shop_domain(invalid)
        else:
            assert normalize_shop_domain(invalid) == ""


def test_client_credentials_are_exchanged_cached_encrypted_and_reused(tmp_path: Path) -> None:
    service = service_for(tmp_path)
    now = [1_000.0]
    calls: list[tuple[str, str, str]] = []

    def exchange(domain: str, client_id: str, client_secret: str):
        calls.append((domain, client_id, client_secret))
        return {
            "access_token": "token-one-secret",
            "expires_in": 3600,
            "scope": "read_locations,write_products",
        }

    manager = ShopifyTokenManager(service, exchange=exchange, clock=lambda: now[0])
    assert manager.get_access_token() == "token-one-secret"
    assert manager.get_access_token() == "token-one-secret"
    assert len(calls) == 1
    assert b"token-one-secret" not in manager.cache_file.read_bytes()
    assert b"shpss_example_secret_123" not in manager.cache_file.read_bytes()
    assert manager.cache_file.stat().st_mode & 0o777 == 0o600
    status = manager.status()
    assert status.mode == "client_credentials"
    assert status.state == "valid"
    assert status.granted_scopes == ("read_locations", "write_products")

    restarted = ShopifyTokenManager(service, exchange=exchange, clock=lambda: now[0])
    assert restarted.get_access_token() == "token-one-secret"
    assert len(calls) == 1


def test_token_refreshes_before_expiry_and_credentials_invalidate_cache(tmp_path: Path) -> None:
    service = service_for(tmp_path)
    now = [1_000.0]
    counter = [0]

    def exchange(_domain: str, _client_id: str, _client_secret: str):
        counter[0] += 1
        return {"access_token": f"token-{counter[0]}", "expires_in": 600, "scope": "read_locations"}

    manager = ShopifyTokenManager(service, exchange=exchange, clock=lambda: now[0])
    assert manager.get_access_token() == "token-1"
    now[0] = 1_301.0  # less than five minutes remain
    assert manager.get_access_token() == "token-2"
    service.save_nonsecret("shopify", {"SHOPIFY_CLIENT_ID": "client_replaced_456"})
    assert manager.get_access_token() == "token-3"
    assert counter[0] == 3


def test_concurrent_refresh_is_deduplicated(tmp_path: Path) -> None:
    service = service_for(tmp_path)
    calls = [0]
    gate = threading.Barrier(8)
    exchange_lock = threading.Lock()

    def exchange(_domain: str, _client_id: str, _client_secret: str):
        with exchange_lock:
            calls[0] += 1
        return {"access_token": "shared-token", "expires_in": 3600, "scope": "read_locations"}

    results: list[str] = []

    def worker() -> None:
        gate.wait()
        results.append(ShopifyTokenManager(service, exchange=exchange).get_access_token())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert results == ["shared-token"] * 8
    assert calls[0] == 1


def test_legacy_static_token_is_supported_as_deprecated_fallback(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    paths = DataPaths.from_root(tmp_path / "data").ensure()
    db.initialize(paths.db_file, paths=paths)
    service = ConfigurationService(project_path=project, paths=paths, process_environment={}, legacy={})
    service.save_nonsecret(
        "shopify",
        {
            "SHOPIFY_STORE_DOMAIN": "canada-vhs.myshopify.com",
            "SHOPIFY_API_VERSION": "2026-07",
            "SHOPIFY_DRAFT_ONLY": "true",
        },
    )
    service.save_secrets("shopify", {"SHOPIFY_ADMIN_ACCESS_TOKEN": "legacy-token"})
    manager = ShopifyTokenManager(service)
    assert manager.get_access_token() == "legacy-token"
    assert manager.status().mode == "legacy_static_token"
    assert manager.status().last_refresh_result == "DEPRECATED"


def test_graphql_401_refreshes_once_and_403_does_not(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeManager:
        def __init__(self) -> None:
            self.token = "old-token"
            self.refreshes = 0

        def get_access_token(self, *, force_refresh=False, rejected_token="") -> str:
            if force_refresh:
                self.refreshes += 1
                assert rejected_token == "old-token"
                self.token = "new-token"
            return self.token

    manager = FakeManager()
    config = ShopifyConfig(
        "canada-vhs.myshopify.com",
        "",
        "gid://shopify/Location/1",
        client_id="client_example_123",
        client_secret="shpss_example_secret_123",
    )
    seen_tokens: list[str] = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"data":{"shop":{"id":"gid://shopify/Shop/1"}}}'

    attempts = [401, 200]

    def urlopen(request, timeout):
        seen_tokens.append(request.headers["X-shopify-access-token"])
        result = attempts.pop(0)
        if result == 401:
            raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO())
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    transport = HTTPShopifyTransport(config, token_manager=manager)
    payload = transport.graphql("query { shop { id } }", {})
    assert payload["data"]["shop"]["id"].endswith("/1")
    assert manager.refreshes == 1
    assert seen_tokens == ["old-token", "new-token"]

    def forbidden(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, io.BytesIO())

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    with pytest.raises(ShopifyAPIError, match="scopes"):
        transport.graphql("query { shop { id } }", {})
    assert manager.refreshes == 1


def test_secret_store_is_encrypted_and_plaintext_legacy_migrates(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    paths = DataPaths.from_root(tmp_path / "data").ensure()
    db.initialize(paths.db_file, paths=paths)
    service = ConfigurationService(project_path=project, paths=paths, process_environment={}, legacy={})
    service._ensure_secret_permissions()
    service.legacy_secret_file.write_text(
        json.dumps({"SHOPIFY_CLIENT_SECRET": "shpss_legacy_plaintext"}), encoding="utf-8"
    )
    service.legacy_secret_file.chmod(0o600)
    assert service.value("SHOPIFY_CLIENT_SECRET") == "shpss_legacy_plaintext"
    service.save_secrets("shopify", {"SHOPIFY_CLIENT_SECRET": "shpss_replaced_secure"})
    assert not service.legacy_secret_file.exists()
    raw = service.secret_file.read_bytes()
    assert b"shpss_replaced_secure" not in raw
    assert service.value("SHOPIFY_CLIENT_SECRET") == "shpss_replaced_secure"
