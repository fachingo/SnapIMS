from __future__ import annotations

import asyncio
import re
import sys
import types
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest

from snapims.config import DataPaths


class _CompatClient:
    """Sync ASGI client with browser-like CSRF handling for application tests."""

    __test__ = False

    def __init__(
        self,
        app: Any,
        base_url: str = "http://testserver",
        raise_server_exceptions: bool = True,
        root_path: str = "",
        follow_redirects: bool = True,
        auto_csrf: bool = True,
        **_: Any,
    ) -> None:
        self.app = app
        self.base_url = base_url
        self.raise_server_exceptions = raise_server_exceptions
        self.root_path = root_path
        self.follow_redirects = follow_redirects
        self.auto_csrf = auto_csrf
        self.cookies = httpx.Cookies()
        self._lifespan: Any = None
        self._csrf_token = ""

    def __enter__(self) -> "_CompatClient":
        self._lifespan = self.app.router.lifespan_context(self.app)
        asyncio.run(self._lifespan.__aenter__())
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._lifespan is not None:
            asyncio.run(self._lifespan.__aexit__(None, None, None))
            self._lifespan = None

    async def _send_once(self, request: httpx.Request) -> httpx.Response:
        body = request.read()
        sent_request = False
        status_code = 500
        response_headers: list[tuple[bytes, bytes]] = []
        body_parts: list[bytes] = []

        async def receive() -> dict[str, Any]:
            nonlocal sent_request
            if not sent_request:
                sent_request = True
                return {"type": "http.request", "body": body, "more_body": False}
            await asyncio.sleep(3600)
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            nonlocal status_code, response_headers
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                response_headers = list(message.get("headers") or [])
            elif message["type"] == "http.response.body":
                body_parts.append(message.get("body", b""))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": request.method,
            "scheme": request.url.scheme,
            "path": request.url.path,
            "raw_path": request.url.path.encode("ascii"),
            "query_string": request.url.query,
            "headers": [(key.lower(), value) for key, value in request.headers.raw],
            "client": ("testclient", 50000),
            "server": (request.url.host or "testserver", request.url.port or 80),
            "root_path": self.root_path,
        }
        await self.app(scope, receive, send)
        return httpx.Response(
            status_code=status_code,
            headers=response_headers,
            content=b"".join(body_parts),
            request=request,
        )

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        follow_redirects = kwargs.pop("follow_redirects", self.follow_redirects)
        request_url = httpx.URL(url if url.startswith("http") else f"{self.base_url}{url}")
        if params := kwargs.pop("params", None):
            request_url = request_url.copy_merge_params(params)

        for _ in range(20):
            request = httpx.Request(
                method,
                request_url,
                headers=kwargs.get("headers"),
                cookies=self.cookies,
                data=kwargs.get("data"),
                files=kwargs.get("files"),
                json=kwargs.get("json"),
                content=kwargs.get("content"),
            )
            response = await self._send_once(request)
            self.cookies.update(response.cookies)
            if not follow_redirects or response.status_code not in {301, 302, 303, 307, 308}:
                return response
            location = response.headers.get("location")
            if not location:
                return response
            request_url = request_url.join(location)
            if response.status_code in {301, 302, 303}:
                method = "GET"
                kwargs = {key: value for key, value in kwargs.items() if key == "headers"}
        raise RuntimeError("Too many redirects")

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        headers = httpx.Headers(kwargs.get("headers"))
        data = kwargs.get("data")
        has_explicit_csrf = bool(headers.get("x-csrf-token")) or (
            isinstance(data, Mapping) and "csrf_token" in data
        )
        if (
            self.auto_csrf
            and method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
            and not has_explicit_csrf
        ):
            if not self._csrf_token:
                self.get("/")
            if self._csrf_token:
                headers["X-CSRF-Token"] = self._csrf_token
                kwargs["headers"] = headers

        response = asyncio.run(self._request(method, url, **kwargs))
        if response.headers.get("content-type", "").startswith("text/html"):
            match = re.search(
                r'<meta name="csrf-token" content="([^"]+)"',
                response.text,
            )
            if match:
                self._csrf_token = match.group(1)
        return response

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)


testclient_module = types.ModuleType("fastapi.testclient")
testclient_module.TestClient = _CompatClient
sys.modules["fastapi.testclient"] = testclient_module


@pytest.fixture
def data_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DataPaths:
    root = tmp_path / "workspace"
    monkeypatch.setenv("SNAPIMS_DATA_DIR", str(root))
    monkeypatch.setenv("SNAPIMS_ENABLE_TEST_PROVIDERS", "true")
    monkeypatch.setenv("SNAPIMS_SKIP_DOTENV", "1")
    monkeypatch.setenv("SNAPIMS_AUTH_SECRET", "")
    monkeypatch.setenv("SNAPIMS_ADMIN_PASSWORD_HASH", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("SHOPIFY_ADMIN_ACCESS_TOKEN", "")
    monkeypatch.setenv("CLOUDFLARE_TUNNEL_CONFIG", str(root / "missing-cloudflared.yml"))
    return DataPaths.from_root(root).ensure()
