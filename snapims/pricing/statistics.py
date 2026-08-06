"""Decimal-based pricing statistics."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from statistics import median

from snapims.pricing.models import PriceStatistics, SoldListing

CENT = Decimal("0.01")


def _round_currency(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_statistics(listings: list[SoldListing]) -> PriceStatistics | None:
    if not listings:
        return None

    totals = [listing.total_price for listing in listings]
    average = sum(totals, start=Decimal("0")) / len(totals)
    return PriceStatistics(
        average=_round_currency(average),
        median=_round_currency(median(totals)),
        lowest=_round_currency(min(totals)),
        highest=_round_currency(max(totals)),
        count=len(totals),
    )
