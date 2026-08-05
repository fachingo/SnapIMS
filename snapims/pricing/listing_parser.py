"""Parse only deterministic eBay sold-listing evidence."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation

from snapims.pricing.models import SoldListing
from snapims.pricing.normalization import clean_display_title, listing_matches

_MONEY_RE = re.compile(r"(?:C\s*\$|CAD\s*\$?|\$)\s*([0-9][0-9,]*(?:\.\d{1,2})?)", re.I)
_SOLD_DATE_RE = re.compile(r"\bsold\s+(.+)$", re.I)
_NON_CAD_RE = re.compile(r"(?:US|EUR|GBP|AU)\s*\$|[€£]", re.I)


def parse_cad_amount(text: str, *, allow_free: bool = False) -> Decimal | None:
    value = clean_display_title(text)
    if not value:
        return None
    if allow_free and re.search(r"\bfree\s+(?:shipping|delivery)\b", value, re.I):
        return Decimal("0.00")
    if _NON_CAD_RE.search(value) or re.search(r"\bto\b", value, re.I):
        return None
    matches = _MONEY_RE.findall(value)
    if len(matches) != 1:
        return None
    try:
        return Decimal(matches[0].replace(",", "")).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def parse_sold_date(text: str) -> str:
    value = clean_display_title(text)
    match = _SOLD_DATE_RE.search(value)
    return match.group(1).strip() if match else value


def parse_listing(requested_movie: str, raw_listing: Mapping[str, object]) -> SoldListing | None:
    title = clean_display_title(raw_listing.get("listing_title", ""))
    url = clean_display_title(raw_listing.get("listing_url", ""))
    if not title or not url or not listing_matches(requested_movie, title):
        return None
    sold_price = parse_cad_amount(str(raw_listing.get("sold_price", "")))
    shipping_price = parse_cad_amount(str(raw_listing.get("shipping_price", "")), allow_free=True)
    if sold_price is None or shipping_price is None:
        return None
    return SoldListing(
        sold_price=sold_price,
        shipping_price=shipping_price,
        listing_title=title,
        listing_url=url,
        sold_date=parse_sold_date(str(raw_listing.get("sold_date", ""))),
    )


def parse_listings(
    requested_movie: str,
    raw_listings: Iterable[Mapping[str, object]],
    maximum: int,
) -> list[SoldListing]:
    """Inspect first-page cards until ``maximum`` valid matches are accepted."""
    parsed: list[SoldListing] = []
    for raw_listing in raw_listings:
        listing = parse_listing(requested_movie, raw_listing)
        if listing is None:
            continue
        parsed.append(listing)
        if len(parsed) >= maximum:
            break
    return parsed
