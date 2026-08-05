"""Public API for Pricing Workbench.

Future callers can use ``pricing.lookup(movie_title)`` without importing the
Streamlit application.
"""

from typing import Any

from snapims.pricing.models import MovieAnalysis


def lookup(movie_title: str, **kwargs: Any) -> MovieAnalysis:
    """Analyze or load one movie without importing the UI layer."""

    from snapims.pricing.service import lookup as service_lookup

    return service_lookup(movie_title, **kwargs)


__all__ = ["MovieAnalysis", "lookup"]
__version__ = "0.11.0"
