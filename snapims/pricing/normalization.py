"""Deterministic title cleanup, de-duplication, and conservative matching."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from datetime import date

FORMAT_WORDS = frozenset({"vhs", "tape", "movie", "video", "cassette"})
SELLER_METADATA = frozenset(
    {
        "authentic", "canada", "canadian", "case", "classic", "clamshell",
        "edition", "factory", "former", "horror", "mint", "new", "ntsc",
        "pal", "previewed", "rare", "sealed", "slip", "slipcover", "tested",
        "widescreen", "black", "white", "color", "colour", "preowned",
    }
)
BUNDLE_OR_MERCHANDISE = frozenset(
    {
        "bundle", "bundles", "collection", "lot", "lots", "trilogy", "set",
        "pack", "dvd", "bluray", "blu", "ray", "poster", "shirt", "book",
        "soundtrack", "laserdisc", "betamax", "game", "figurine", "figure",
    }
)
SEQUEL_WORDS = frozenset(
    {
        "returns", "return", "resurrection", "revenge", "reloaded", "revolutions",
        "awakens", "rises", "forever", "begins", "legacy", "chapter", "part",
        "episode", "versus", "vs",
    }
)
_YEAR_RE = re.compile(r"^(?:18|19|20|21)\d{2}$")
_ROMAN_RE = re.compile(r"^(?:ii|iii|iv|v|vi|vii|viii|ix|x)$")
_WHITESPACE_RE = re.compile(r"\s+")
_NEW_LISTING_RE = re.compile(r"^\s*new\s+listing\s*[:\-–—]?\s*", re.IGNORECASE)


def clean_display_title(value: object) -> str:
    if value is None:
        return ""
    return _WHITESPACE_RE.sub(" ", str(value).strip())


def _tokenize(value: str) -> list[str]:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    alphanumeric = re.sub(r"[^\w]+", " ", ascii_text.casefold(), flags=re.UNICODE)
    return [token for token in alphanumeric.split() if token]


def normalize_title(value: str) -> str:
    """Normalize only format words; never discard words that may be the movie title."""

    return " ".join(token for token in _tokenize(value) if token not in FORMAT_WORDS)


def deduplicate_titles(titles: Iterable[object]) -> list[str]:
    """De-duplicate by the same normalized identity used by cache and queue logic."""

    seen: set[str] = set()
    result: list[str] = []
    for raw_title in titles:
        title = clean_display_title(raw_title)
        key = normalize_title(title)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(title)
    return result


def _is_optional_year(token: str, requested_has_year: bool) -> bool:
    if requested_has_year or not _YEAR_RE.fullmatch(token):
        return False
    year = int(token)
    return 1888 <= year <= date.today().year + 2


def listing_matches(requested_movie: str, listing_title: str) -> bool:
    """Require the complete requested title as one exact contiguous token sequence.

    Only structured seller metadata and an optional release year may remain around
    that sequence. Title words such as ``No``, ``New``, ``Good``, ``Original``,
    ``Rental``, ``Collector``, and ``Canadian`` are never removed from the request.
    """

    requested_tokens = normalize_title(requested_movie).split()
    if not requested_tokens:
        return False
    without_badge = _NEW_LISTING_RE.sub("", clean_display_title(listing_title))
    listing_tokens = normalize_title(without_badge).split()
    if not listing_tokens:
        return False
    width = len(requested_tokens)
    requested_has_year = any(_YEAR_RE.fullmatch(token) for token in requested_tokens)
    candidates = [
        index
        for index in range(0, len(listing_tokens) - width + 1)
        if listing_tokens[index : index + width] == requested_tokens
    ]
    if not candidates:
        return False
    for index in candidates:
        extras = listing_tokens[:index] + listing_tokens[index + width :]
        if any(token in BUNDLE_OR_MERCHANDISE for token in extras):
            continue
        if any(token in SEQUEL_WORDS or _ROMAN_RE.fullmatch(token) for token in extras):
            continue
        if any(token.isdigit() and not _is_optional_year(token, requested_has_year) for token in extras):
            continue
        if all(token in SELLER_METADATA or _is_optional_year(token, requested_has_year) for token in extras):
            return True
    return False
