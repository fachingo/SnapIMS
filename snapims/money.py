from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

CENT = Decimal("0.01")
PERCENT_STEP = Decimal("0.01")
MAX_PRICE_CENTS = 100_000_000  # CAD $1,000,000.00; prevents accidental overflow-sized entries.


class MoneyValueError(ValueError):
    pass


def parse_price_cents(value: Any, *, allow_blank: bool = True) -> int | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if allow_blank:
            return None
        raise MoneyValueError("Price is required")
    if isinstance(value, bool):
        raise MoneyValueError("Price must be a currency amount")
    cleaned = str(value).strip().replace("CAD", "").replace("$", "").replace(",", "")
    try:
        amount = Decimal(cleaned).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise MoneyValueError(f"Invalid price: {value!r}") from exc
    cents = int(amount * 100)
    if cents < 0:
        raise MoneyValueError("Price cannot be negative")
    if cents > MAX_PRICE_CENTS:
        raise MoneyValueError("Price is too large")
    return cents


def format_price_cents(cents: int | None) -> str:
    return "" if cents is None else f"{Decimal(int(cents)) / 100:.2f}"


def parse_discount_percent(value: Any) -> float:
    if value is None or (isinstance(value, str) and not value.strip()):
        return 0.0
    try:
        percent = Decimal(str(value)).quantize(PERCENT_STEP, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise MoneyValueError(f"Invalid discount percent: {value!r}") from exc
    if percent < 0 or percent > 100:
        raise MoneyValueError("Discount must be between 0 and 100 percent")
    return float(percent)


def final_price_cents(price_cents: int, discount_percent: Any) -> int:
    price = Decimal(int(price_cents))
    discount = Decimal(str(parse_discount_percent(discount_percent)))
    return int((price * (Decimal("1") - discount / Decimal("100"))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def add_price_cents(price_cents: int | None, amount: Any) -> int:
    delta = parse_price_cents(amount, allow_blank=False)
    assert delta is not None
    result = int(price_cents or 0) + delta
    if result > MAX_PRICE_CENTS:
        raise MoneyValueError("Price is too large")
    return result


def subtract_percent_cents(price_cents: int | None, percent: Any) -> int:
    return final_price_cents(int(price_cents or 0), percent)


def round_price_cents(price_cents: int | None, increment: Any) -> int:
    increment_cents = parse_price_cents(increment, allow_blank=False)
    assert increment_cents is not None
    if increment_cents <= 0:
        raise MoneyValueError("Rounding increment must be greater than zero")
    value = Decimal(int(price_cents or 0)) / Decimal(increment_cents)
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)) * increment_cents
