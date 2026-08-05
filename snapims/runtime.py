from __future__ import annotations

import os

TEST_PROVIDER_NAMES = frozenset({"mock", "fixture", "demo", "synthetic", "test"})


def test_providers_enabled() -> bool:
    """Return True only when the operator deliberately enables non-production providers."""
    return os.getenv("SNAPIMS_ENABLE_TEST_PROVIDERS", "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def is_test_provider(provider_name: str | None) -> bool:
    return str(provider_name or "").strip().casefold() in TEST_PROVIDER_NAMES


def require_provider_allowed(provider_name: str) -> None:
    if is_test_provider(provider_name) and not test_providers_enabled():
        raise PermissionError(
            "Test recognition providers are disabled in production mode. "
            "Set SNAPIMS_ENABLE_TEST_PROVIDERS=true only in an isolated development workspace."
        )
