from __future__ import annotations

import os
from pathlib import Path

import pytest

from snapims.catalog import db as catalog_db
from snapims.catalog.wikipedia import WikipediaClient


@pytest.mark.skipif(
    os.getenv("SNAPIMS_LIVE_WIKIPEDIA_TEST", "").strip() != "1",
    reason="Set SNAPIMS_LIVE_WIKIPEDIA_TEST=1 to run the bounded live English Wikipedia integration test.",
)
def test_live_english_wikipedia_gremlins_lookup(tmp_path: Path) -> None:
    catalog_file = tmp_path / "movie_catalog.sqlite3"
    catalog_db.initialize(catalog_file)
    client = WikipediaClient(
        catalog_file,
        user_agent=os.getenv(
            "SNAPIMS_WIKIPEDIA_USER_AGENT",
            "SnapIMS-SLMC/0.1.0 live-test (contact: owner-configured)",
        ),
        timeout=15,
        max_retries=1,
        min_interval=1.0,
    )
    candidates = client.search_candidates("Gremlins", 1984, limit=5)
    accepted = [candidate for candidate in candidates if not candidate.rejected_reason]
    assert accepted
    assert accepted[0].canonical_title == "Gremlins"
    assert accepted[0].release_year == 1984
    assert accepted[0].source_page_id
    assert accepted[0].source_revision_id
