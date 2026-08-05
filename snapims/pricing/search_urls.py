"""eBay Canada sold/completed search URL generation."""

from __future__ import annotations

from urllib.parse import urlencode

EBAY_CA_SEARCH_ENDPOINT = "https://www.ebay.ca/sch/i.html"


def search_query(movie_title: str) -> str:
    title = " ".join(movie_title.split())
    return f"{title} VHS"


def generate_search_url(movie_title: str) -> str:
    """Build one reproducible eBay Canada sold and completed search URL."""

    parameters = {
        "_from": "R40",
        "_nkw": search_query(movie_title),
        "_sacat": "0",
        "_sop": "13",
        "LH_Complete": "1",
        "LH_Sold": "1",
        "rt": "nc",
    }
    return f"{EBAY_CA_SEARCH_ENDPOINT}?{urlencode(parameters)}"
