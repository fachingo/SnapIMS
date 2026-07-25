from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class CatalogLookupRequest:
    item_id: str
    recognition_result_id: int
    proposed_title: str
    proposed_year: int | None = None
    distributor_clues: str = ""
    country_clues: tuple[str, ...] = ()
    language_clues: tuple[str, ...] = ()
    edition_clues: str = ""
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class MovieCandidate:
    provider: str
    source_page_id: str
    source_page_title: str
    source_url: str
    canonical_title: str
    original_title: str = ""
    release_year: int | None = None
    release_date: str | None = None
    media_type: str = "film"
    runtime_minutes: int | None = None
    countries: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    directors: tuple[str, ...] = ()
    genres: tuple[str, ...] = ()
    summary: str = ""
    aliases: tuple[str, ...] = ()
    source_revision_id: str = ""
    retrieved_at: str = ""
    raw_response_hash: str = ""
    attribution: str = ""
    parser_version: str = ""
    score: float = 0.0
    evidence: tuple[str, ...] = ()
    rejected_reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)


@dataclass(frozen=True, slots=True)
class LocalMatch:
    movie_id: str
    canonical_title: str
    primary_release_year: int | None
    match_score: float
    method: str
    reason: str
    unique: bool


@dataclass(frozen=True, slots=True)
class CatalogStatus:
    available: bool
    status: str
    label: str
    movie_id: str = ""
    canonical_title: str = ""
    primary_release_year: int | None = None
    match_method: str = ""
    match_score: float | None = None
    candidate_count: int = 0
    source_url: str = ""
    error: str = ""
    materially_ambiguous: bool = False
