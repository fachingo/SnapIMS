"""UI-independent pricing service API."""

from __future__ import annotations

from pathlib import Path

from snapims.pricing.database import PricingDatabase
from snapims.pricing.models import MovieAnalysis
from snapims.pricing.playwright_controller import PlaywrightController
from snapims.pricing.settings import AppSettings


def lookup(
    movie_title: str,
    *,
    settings: AppSettings | None = None,
    database_path: str | Path | None = None,
    refresh: bool = False,
) -> MovieAnalysis:
    """Load a cached result or analyze one movie with Playwright.

    ``refresh=True`` deliberately bypasses and replaces a cached analysis.
    """

    database = PricingDatabase(database_path)
    controller = PlaywrightController(settings=settings, database=database)
    results = controller.analyze_titles(
        [movie_title], refresh_titles=[movie_title] if refresh else []
    )
    if not results:
        raise ValueError("movie_title must not be blank")
    return results[0]
