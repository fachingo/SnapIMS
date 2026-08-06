"""Typed deterministic pricing models for SnapIMS v0.11.0."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum


class AnalysisStatus(StrEnum):
    LINK_READY = "Link ready"
    QUEUED = "Queued"
    ANALYZING = "Analyzing"
    COMPLETE = "Complete"
    NO_VALID_MATCHES = "No valid matching sold VHS listings"
    VERIFICATION_REQUIRED = "eBay verification required"
    ACCESS_BLOCKED = "eBay access blocked"
    PARSING_LAYOUT_FAILURE = "eBay page layout could not be parsed"
    BROWSER_MISSING = "Playwright Chromium missing"
    NETWORK_UNAVAILABLE = "Network unavailable"
    FAILED = "Failed"
    CANCELLED = "Cancelled"
    PAUSED = "Paused"
    STALE = "Stale"


@dataclass(frozen=True, slots=True)
class SoldListing:
    sold_price: Decimal
    shipping_price: Decimal
    listing_title: str
    listing_url: str
    sold_date: str

    @property
    def total_price(self) -> Decimal:
        return self.sold_price + self.shipping_price


@dataclass(frozen=True, slots=True)
class PriceStatistics:
    average: Decimal
    median: Decimal
    lowest: Decimal
    highest: Decimal
    count: int


@dataclass(slots=True)
class MovieAnalysis:
    movie: str
    search_url: str
    status: AnalysisStatus = AnalysisStatus.LINK_READY
    statistics: PriceStatistics | None = None
    listings: list[SoldListing] = field(default_factory=list)
    analysis_date: date | None = None
    error: str | None = None
    from_cache: bool = False
    evidence_id: int | None = None
    collection_id: str = ""
    queried_title: str = ""
    title_key: str = ""
    collected_at: str = ""

    @property
    def tapes_averaged_label(self) -> str:
        count = self.statistics.count if self.statistics else 0
        noun = "tape" if count == 1 else "tapes"
        return f"{count} {noun} averaged"
