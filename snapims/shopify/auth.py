from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from cryptography.fernet import Fernet, InvalidToken

from snapims.settings import ConfigurationError, ConfigurationService

TOKEN_CACHE_FILENAME = "shopify-token-cache.enc"
TOKEN_LOCK_FILENAME = "shopify-token-refresh.lock"
DEFAULT_EXPIRY_SECONDS = 86_399
REFRESH_MARGIN_SECONDS = 300


class ShopifyCredentialError(RuntimeError):
    """The configured store or client credentials were rejected."""


class ShopifyTokenError(RuntimeError):
    """A Shopify access token could not be obtained safely."""


def normalize_shop_domain(value: str) -> str:
    cleaned = value.strip().casefold()
    if not cleaned:
        return ""
    if "://" in cleaned or any(character in cleaned for character in "/?#"):
        raise ShopifyCredentialError(
            "Use the permanent .myshopify.com domain without https:// or a path."
        )
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.myshopify\.com", cleaned):
        raise ShopifyCredentialError(
            "Shopify store domain must be the permanent store-name.myshopify.com domain."
        )
    return cleaned


@dataclass(frozen=True, slots=True)
class ShopifyToken:
    access_token: str
    issued_at: float
    expires_at: float
    scopes: tuple[str, ...]
    source: str = "client_credentials"

    def valid_for(self, seconds: int = REFRESH_MARGIN_SECONDS, *, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        return bool(self.access_token) and self.expires_at - current > seconds


@dataclass(frozen=True, slots=True)
class ShopifyTokenStatus:
    mode: str
    state: str
    expires_at: str
    granted_scopes: tuple[str, ...]
    last_refresh_at: str
    last_refresh_result: str


class ShopifyTokenManager:
    """Restart-safe, single-store Shopify client-credentials token manager.

    Tokens are encrypted on disk and refreshed under both a process lock and a
    filesystem lock. The cache is bound to a fingerprint of the store, client
    ID, and Client Secret, so replacing credentials invalidates it without
    exposing those values in the cache metadata.
    """

    _thread_lock = threading.RLock()

    def __init__(
        self,
        service: ConfigurationService | None = None,
        *,
        exchange: Callable[[str, str, str], Mapping[str, Any]] | None = None,
        clock: Callable[[], float] = time.time,
        timeout: int = 30,
        credentials: tuple[str, str, str, str] | None = None,
        cache_enabled: bool = True,
    ) -> None:
        self.service = service or ConfigurationService.load_runtime()
        self.exchange = exchange or self._http_exchange
        self.clock = clock
        self.timeout = timeout
        self._credential_override = credentials
        self.cache_enabled = cache_enabled
        self._memory_cache: dict[str, Any] = {}

    @property
    def cache_file(self) -> Path:
        return self.service.paths.secrets / TOKEN_CACHE_FILENAME

    @property
    def lock_file(self) -> Path:
        return self.service.paths.secrets / TOKEN_LOCK_FILENAME

    def _credentials(self) -> tuple[str, str, str, str]:
        if self._credential_override is not None:
            domain, client_id, client_secret, legacy = self._credential_override
            return normalize_shop_domain(domain), client_id.strip(), client_secret.strip(), legacy.strip()
        domain = normalize_shop_domain(self.service.value("SHOPIFY_STORE_DOMAIN", ""))
        client_id = self.service.value("SHOPIFY_CLIENT_ID", "").strip()
        client_secret = self.service.value("SHOPIFY_CLIENT_SECRET", "").strip()
        legacy = self.service.value("SHOPIFY_ADMIN_ACCESS_TOKEN", "").strip()
        return domain, client_id, client_secret, legacy

    @staticmethod
    def _fingerprint(domain: str, client_id: str, client_secret: str) -> str:
        material = "\0".join((domain, client_id, client_secret)).encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    def _fernet(self) -> Fernet:
        return Fernet(self.service._load_or_create_secret_key())

    def _read_cache(self) -> dict[str, Any]:
        if not self.cache_enabled:
            return dict(self._memory_cache)
        path = self.cache_file
        if not path.exists():
            return {}
        if path.is_symlink() or not path.is_file():
            raise ShopifyTokenError("Shopify token cache is not a regular file.")
        status = path.stat()
        if status.st_uid != os.geteuid() or stat.S_IMODE(status.st_mode) != 0o600:
            raise ShopifyTokenError("Shopify token cache must be owner-only with permissions 0600.")
        try:
            decoded = self._fernet().decrypt(path.read_bytes())
            payload = json.loads(decoded.decode("utf-8"))
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ShopifyTokenError("Shopify token cache could not be decrypted.") from exc
        return payload if isinstance(payload, dict) else {}

    def _write_cache(self, payload: Mapping[str, Any]) -> None:
        if not self.cache_enabled:
            self._memory_cache = dict(payload)
            return
        self.service._ensure_secret_permissions()
        encoded = self._fernet().encrypt(
            json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        temporary = self.cache_file.with_name(f".{self.cache_file.name}.{os.getpid()}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        temporary.replace(self.cache_file)
        self.cache_file.chmod(0o600)

    def clear(self) -> None:
        self._memory_cache.clear()
        if self.cache_enabled:
            self.cache_file.unlink(missing_ok=True)

    def _token_from_cache(self, fingerprint: str) -> ShopifyToken | None:
        payload = self._read_cache()
        if not payload or payload.get("credential_fingerprint") != fingerprint:
            return None
        try:
            return ShopifyToken(
                access_token=str(payload["access_token"]),
                issued_at=float(payload["issued_at"]),
                expires_at=float(payload["expires_at"]),
                scopes=tuple(sorted(str(scope) for scope in payload.get("granted_scopes", []))),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def get_access_token(
        self, *, force_refresh: bool = False, rejected_token: str = ""
    ) -> str:
        domain, client_id, client_secret, legacy = self._credentials()
        if client_id and client_secret:
            if not domain:
                raise ShopifyCredentialError("Configure the Shopify store domain first.")
            fingerprint = self._fingerprint(domain, client_id, client_secret)
            with self._thread_lock:
                self.service._ensure_secret_permissions()
                descriptor = os.open(self.lock_file, os.O_RDWR | os.O_CREAT, 0o600)
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX)
                    cached = self._token_from_cache(fingerprint)
                    if cached and cached.valid_for(now=self.clock()):
                        if not force_refresh or (rejected_token and cached.access_token != rejected_token):
                            return cached.access_token
                    return self._refresh_locked(domain, client_id, client_secret, fingerprint)
                finally:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                    os.close(descriptor)
        if legacy:
            return legacy
        if client_id or client_secret:
            raise ShopifyCredentialError("Both Shopify Client ID and Client Secret are required.")
        raise ShopifyCredentialError(
            "Shopify is not connected. Save the Dev Dashboard Client ID and Client Secret."
        )

    def _refresh_locked(self, domain: str, client_id: str, client_secret: str, fingerprint: str) -> str:
        refreshed_at = self.clock()
        try:
            response = dict(self.exchange(domain, client_id, client_secret))
            token = str(response.get("access_token") or "").strip()
            if not token:
                raise ShopifyTokenError("Shopify did not return an access token.")
            expires_in = int(response.get("expires_in") or DEFAULT_EXPIRY_SECONDS)
            if expires_in < 60:
                raise ShopifyTokenError("Shopify returned an unusably short token lifetime.")
            raw_scopes = response.get("scope") or response.get("scopes") or ""
            if isinstance(raw_scopes, str):
                scopes = tuple(sorted(filter(None, re.split(r"[\s,]+", raw_scopes))))
            elif isinstance(raw_scopes, (list, tuple, set)):
                scopes = tuple(sorted(str(scope) for scope in raw_scopes if scope))
            else:
                scopes = ()
            payload = {
                "shop_domain": domain,
                "credential_fingerprint": fingerprint,
                "access_token": token,
                "issued_at": refreshed_at,
                "expires_at": refreshed_at + expires_in,
                "granted_scopes": scopes,
                "last_refresh_at": refreshed_at,
                "last_refresh_result": "PASS",
            }
            self._write_cache(payload)
            return token
        except ShopifyCredentialError:
            self._write_failure_cache(domain, fingerprint, refreshed_at, "REJECTED")
            raise
        except Exception as exc:
            self._write_failure_cache(domain, fingerprint, refreshed_at, "FAILED")
            if isinstance(exc, ShopifyTokenError):
                raise
            raise ShopifyTokenError("Shopify access-token refresh failed.") from exc

    def _write_failure_cache(self, domain: str, fingerprint: str, refreshed_at: float, result: str) -> None:
        previous = self._read_cache()
        safe = {
            "shop_domain": domain,
            "credential_fingerprint": fingerprint,
            "access_token": "",
            "issued_at": 0,
            "expires_at": 0,
            "granted_scopes": [],
            "last_refresh_at": refreshed_at,
            "last_refresh_result": result,
        }
        if previous.get("credential_fingerprint") == fingerprint:
            safe["granted_scopes"] = previous.get("granted_scopes", [])
        self._write_cache(safe)

    def status(self) -> ShopifyTokenStatus:
        try:
            domain, client_id, client_secret, legacy = self._credentials()
        except ShopifyCredentialError:
            return ShopifyTokenStatus("none", "invalid_configuration", "", (), "", "")
        if client_id and client_secret and domain:
            fingerprint = self._fingerprint(domain, client_id, client_secret)
            payload = self._read_cache()
            if payload.get("credential_fingerprint") != fingerprint:
                return ShopifyTokenStatus("client_credentials", "not_requested", "", (), "", "")
            expires_at = float(payload.get("expires_at") or 0)
            now = self.clock()
            state = "valid" if expires_at - now > REFRESH_MARGIN_SECONDS else ("expired" if expires_at <= now else "refresh_due")
            return ShopifyTokenStatus(
                "client_credentials",
                state,
                _format_epoch(expires_at),
                tuple(sorted(str(scope) for scope in payload.get("granted_scopes", []))),
                _format_epoch(float(payload.get("last_refresh_at") or 0)),
                str(payload.get("last_refresh_result") or ""),
            )
        if legacy:
            return ShopifyTokenStatus("legacy_static_token", "configured", "unknown", (), "", "DEPRECATED")
        state = "incomplete" if client_id or client_secret or domain else "not_configured"
        return ShopifyTokenStatus("none", state, "", (), "", "")

    def _http_exchange(self, domain: str, client_id: str, client_secret: str) -> Mapping[str, Any]:
        endpoint = f"https://{domain}/admin/oauth/access_token"
        body = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in {400, 401, 403, 404}:
                raise ShopifyCredentialError(
                    "Shopify rejected the Client ID or Client Secret. Confirm the app is installed in this store and copy both values from Dev Dashboard → App → Settings."
                ) from exc
            raise ShopifyTokenError(f"Shopify token endpoint returned HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ShopifyTokenError("Shopify token endpoint is currently unavailable.") from exc
        except json.JSONDecodeError as exc:
            raise ShopifyTokenError("Shopify token endpoint returned an invalid response.") from exc
        if not isinstance(payload, dict):
            raise ShopifyTokenError("Shopify token endpoint returned an invalid response.")
        return payload


def _format_epoch(value: float) -> str:
    if value <= 0:
        return ""
    return datetime.fromtimestamp(value).astimezone().isoformat(timespec="seconds")
