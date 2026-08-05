from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

_ARTICLES = ("the ", "a ", "an ")
_ROMAN_TO_INT = {
    "i": "1",
    "ii": "2",
    "iii": "3",
    "iv": "4",
    "v": "5",
    "vi": "6",
    "vii": "7",
    "viii": "8",
    "ix": "9",
    "x": "10",
}
_INT_TO_ROMAN = {value: key for key, value in _ROMAN_TO_INT.items()}


def normalize_title(value: str) -> str:
    """Create a conservative normalized title key.

    The key normalizes case, Unicode, apostrophes, dashes, punctuation and
    whitespace. It deliberately keeps leading articles and sequel tokens so
    distinct films do not collapse merely because their visible title differs.
    """

    text = unicodedata.normalize("NFKC", value or "").casefold()
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'")
    text = re.sub(r"[‐‑‒–—―]", "-", text)
    text = re.sub(r"\s*[:|/\\-]+\s*", " ", text)
    text = re.sub(r"[^\w\s']", " ", text, flags=re.UNICODE)
    text = text.replace("'", "")
    return re.sub(r"\s+", " ", text).strip()


def strip_leading_article(normalized: str) -> str:
    for article in _ARTICLES:
        if normalized.startswith(article) and len(normalized) > len(article):
            return normalized[len(article) :]
    return normalized


def _replace_final_token(normalized: str, mapping: dict[str, str]) -> str | None:
    tokens = normalized.split()
    if not tokens or tokens[-1] not in mapping:
        return None
    return " ".join([*tokens[:-1], mapping[tokens[-1]]])


def title_variants(value: str) -> tuple[str, ...]:
    """Return bounded exact-search variants without destructive over-normalization."""

    normalized = normalize_title(value)
    variants: list[str] = []
    for candidate in (normalized, strip_leading_article(normalized)):
        if candidate and candidate not in variants:
            variants.append(candidate)
        roman = _replace_final_token(candidate, _ROMAN_TO_INT)
        numeric = _replace_final_token(candidate, _INT_TO_ROMAN)
        for transformed in (roman, numeric):
            if transformed and transformed not in variants:
                variants.append(transformed)
    return tuple(variants)


def normalized_unique(values: Iterable[str]) -> tuple[str, ...]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_title(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(value.strip())
    return tuple(output)
