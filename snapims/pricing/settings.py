"""Validated operator settings for respectful, first-page-only pricing collection."""

from __future__ import annotations

import os
from dataclasses import dataclass

TAB_OPTIONS = (1, 2, 3)
LISTING_LIMIT_OPTIONS = (3, 5, 10, 25)
CACHE_DAY_OPTIONS = (1, 7, 14, 30, 60, 90)
PROFILE_OPTIONS: dict[str, tuple[int, int, int]] = {
    "CONSERVATIVE": (1, 15, 30),
    "BALANCED": (2, 8, 15),
}


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Runtime controls. Queue depth never changes request rate."""

    max_simultaneous_tabs: int = 1
    delay_min_seconds: int = 15
    delay_max_seconds: int = 30
    max_sold_listings: int = 3
    navigation_timeout_seconds: int = 45
    headless: bool = True
    cache_expiry_days: int = 30
    profile: str = "CONSERVATIVE"

    def __post_init__(self) -> None:
        if self.max_simultaneous_tabs not in TAB_OPTIONS:
            raise ValueError(f"max_simultaneous_tabs must be one of {TAB_OPTIONS}")
        if self.delay_min_seconds < 2 or self.delay_max_seconds < self.delay_min_seconds:
            raise ValueError("delay range must be at least 2 seconds and ordered")
        if self.max_sold_listings not in LISTING_LIMIT_OPTIONS:
            raise ValueError(f"max_sold_listings must be one of {LISTING_LIMIT_OPTIONS}")
        if self.navigation_timeout_seconds <= 0:
            raise ValueError("navigation_timeout_seconds must be positive")
        if self.cache_expiry_days <= 0:
            raise ValueError("cache_expiry_days must be positive")
        if self.profile not in {"CONSERVATIVE", "BALANCED", "CUSTOM"}:
            raise ValueError("profile must be CONSERVATIVE, BALANCED, or CUSTOM")
        if self.profile in PROFILE_OPTIONS:
            expected = PROFILE_OPTIONS[self.profile]
            actual = (
                self.max_simultaneous_tabs,
                self.delay_min_seconds,
                self.delay_max_seconds,
            )
            if actual != expected:
                raise ValueError(
                    f"{self.profile} requires concurrency/delay {expected}; "
                    "choose CUSTOM to enter different values"
                )

    @classmethod
    def for_profile(
        cls,
        profile: str,
        *,
        max_sold_listings: int = 3,
        headless: bool | None = None,
        cache_expiry_days: int = 30,
    ) -> "AppSettings":
        profile_key = profile.strip().upper()
        if profile_key == "CUSTOM":
            raise ValueError("CUSTOM requires explicit settings")
        concurrency, delay_min, delay_max = PROFILE_OPTIONS[profile_key]
        visible = os.getenv("SNAPIMS_PRICING_HEADLESS", "1").strip().casefold() not in {
            "0", "false", "no"
        }
        return cls(
            max_simultaneous_tabs=concurrency,
            delay_min_seconds=delay_min,
            delay_max_seconds=delay_max,
            max_sold_listings=max_sold_listings,
            headless=visible if headless is None else headless,
            cache_expiry_days=cache_expiry_days,
            profile=profile_key,
        )
