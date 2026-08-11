from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from statistics import mean
from typing import Any
from urllib.parse import urlencode

from snapims import db
try:
    from snapims.catalog.normalization import normalize_title as catalog_normalize_title
except Exception:  # isolated rescue-harness fallback only
    def catalog_normalize_title(value: str) -> str:
        return " ".join(str(value or "").casefold().split())


@dataclass(frozen=True, slots=True)
class PriorPriceEvidence:
    item_id: str
    batch_id: str
    title: str
    price_cents: int
    updated_at: str
    movie_id: str = ""
    edition: str = ""
    distributor: str = ""
    release_year: int | None = None


@dataclass(frozen=True, slots=True)
class DatabasePriceSuggestion:
    applicable: bool
    strong_identity: bool
    suggested_price_cents: int | None
    average_price_cents: int | None
    previous_count: int
    reason: str
    evidence: tuple[PriorPriceEvidence, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "evidence": [asdict(row) for row in self.evidence],
        }


def ebay_sold_url(title: str) -> str:
    query = " ".join(part for part in (str(title or "").strip(), "VHS") if part)
    params = urlencode({"_nkw": query, "LH_Complete": "1", "LH_Sold": "1"})
    return f"https://www.ebay.ca/sch/i.html?{params}"


def _same_structured_identity(a: Any, b: Any) -> bool:
    """Treat unknown edition/distributor detail as ambiguity, not proof of sameness."""
    a_text = str(a or "").strip().casefold()
    b_text = str(b or "").strip().casefold()
    if not a_text and not b_text:
        return True
    if not a_text or not b_text:
        return False
    return a_text == b_text


def _compatible_edition(current: dict[str, Any], candidate: dict[str, Any]) -> bool:
    if not _same_structured_identity(current.get("edition"), candidate.get("edition")):
        return False
    if not _same_structured_identity(current.get("distributor"), candidate.get("distributor")):
        return False
    a, b = current.get("release_year"), candidate.get("release_year")
    if a is not None and b is not None and int(a) != int(b):
        return False
    return True


def database_price_suggestion(db_file: Path, item_id: str, *, limit: int = 20) -> DatabasePriceSuggestion:
    current = db.get_item(db_file, item_id)
    if current is None:
        raise KeyError(f"Unknown item: {item_id}")
    current_title = str(current.get("title") or current.get("suggested_title") or "").strip()
    if not current_title:
        return DatabasePriceSuggestion(False, False, None, None, 0, "No approved/working title", ())

    current_link = db.get_item_movie_link(db_file, item_id) or {}
    current_movie = str(current_link.get("movie_id") or "")
    normalized = catalog_normalize_title(current_title)

    # Query only plausible identity matches. This stays correct as the database grows: a
    # prior copy must not disappear merely because 500 newer unrelated tapes exist.
    with db.connect(db_file) as connection:
        if current_movie:
            rows = [
                dict(row)
                for row in connection.execute(
                    """SELECT i.item_id,i.batch_id,i.title,i.price_cents,i.updated_at,
                              i.edition,i.distributor,i.release_year,
                              COALESCE(l.movie_id,'') AS movie_id
                       FROM items i
                       LEFT JOIN item_movie_links l ON l.item_id=i.item_id
                       WHERE i.item_id<>? AND i.price_cents IS NOT NULL
                         AND UPPER(COALESCE(i.working_source,'')) NOT LIKE 'AI%'
                         AND UPPER(COALESCE(i.working_source,'')) NOT LIKE 'RECOGNITION%'
                         AND (l.movie_id=? OR lower(trim(i.title))=lower(trim(?)))
                       ORDER BY i.updated_at DESC LIMIT ?""",
                    (item_id, current_movie, current_title, max(20, min(limit * 5, 200))),
                ).fetchall()
            ]
        else:
            rows = [
                dict(row)
                for row in connection.execute(
                    """SELECT i.item_id,i.batch_id,i.title,i.price_cents,i.updated_at,
                              i.edition,i.distributor,i.release_year,
                              COALESCE(l.movie_id,'') AS movie_id
                       FROM items i
                       LEFT JOIN item_movie_links l ON l.item_id=i.item_id
                       WHERE i.item_id<>? AND i.price_cents IS NOT NULL
                         AND UPPER(COALESCE(i.working_source,'')) NOT LIKE 'AI%'
                         AND UPPER(COALESCE(i.working_source,'')) NOT LIKE 'RECOGNITION%'
                         AND lower(trim(i.title))=lower(trim(?))
                       ORDER BY i.updated_at DESC LIMIT ?""",
                    (item_id, current_title, max(20, min(limit * 5, 200))),
                ).fetchall()
            ]

    strong: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    for row in rows:
        row_title = str(row.get("title") or "").strip()
        row_movie = str(row.get("movie_id") or "")
        exact_title = bool(row_title) and catalog_normalize_title(row_title) == normalized
        same_movie = bool(current_movie and row_movie and current_movie == row_movie)
        if same_movie and _compatible_edition(current, row):
            strong.append(row)
        elif exact_title:
            # An exact normalized title is guidance unless edition identity is also compatible.
            if _compatible_edition(current, row) and not current_movie and not row_movie:
                # No catalog identity exists on either side; exact title + compatible structured
                # fields is useful but remains conservative. Only auto-apply when all candidates
                # agree on the same normalized title and there is no conflicting structured data.
                strong.append(row)
            else:
                ambiguous.append(row)

    chosen = strong[:limit]
    guidance = (strong + ambiguous)[:limit]
    evidence_rows = tuple(
        PriorPriceEvidence(
            item_id=str(row["item_id"]), batch_id=str(row["batch_id"]),
            title=str(row.get("title") or ""), price_cents=int(row["price_cents"]),
            updated_at=str(row.get("updated_at") or ""), movie_id=str(row.get("movie_id") or ""),
            edition=str(row.get("edition") or ""), distributor=str(row.get("distributor") or ""),
            release_year=int(row["release_year"]) if row.get("release_year") is not None else None,
        )
        for row in guidance
    )
    if not chosen:
        avg = round(mean([int(row["price_cents"]) for row in guidance])) if guidance else None
        return DatabasePriceSuggestion(
            False, False, None, avg, len(guidance),
            "Prior same-title pricing exists but identity/edition is not strong enough to prefill" if guidance else "No prior priced match",
            evidence_rows,
        )

    # The most recent deliberate accepted/listed price is the default suggestion; the average
    # remains visible context so the operator can spot drift.
    latest = int(chosen[0]["price_cents"])
    avg = round(mean([int(row["price_cents"]) for row in chosen]))
    return DatabasePriceSuggestion(
        True, True, latest, avg, len(chosen),
        "Strong prior SnapIMS product/edition identity",
        evidence_rows,
    )


def autofill_database_price(db_file: Path, item_id: str) -> DatabasePriceSuggestion:
    current = db.get_item(db_file, item_id)
    if current is None:
        raise KeyError(f"Unknown item: {item_id}")
    suggestion = database_price_suggestion(db_file, item_id)
    if current.get("price_cents") is not None or not suggestion.applicable or suggestion.suggested_price_cents is None:
        return suggestion
    db.update_item(
        db_file,
        item_id,
        {"price_cents": suggestion.suggested_price_cents, "working_source": "PRICING_DATABASE"},
        source="PRICING_DATABASE",
        reason=f"Database-first pricing: {suggestion.reason}; {suggestion.previous_count} prior record(s)",
        expected_revision=int(current.get("record_revision") or 0),
    )
    return suggestion


def pricing_badge(db_file: Path, item: dict[str, Any]) -> str:
    if item.get("price_cents") is None:
        return "UNPRICED"
    source = str(item.get("working_source") or "").upper()
    if source.startswith("PRICING_DATABASE"):
        return "DATABASE"
    if source.startswith("PRICING_"):
        try:
            from snapims.pricing.integration import pricing_item_state
            state = pricing_item_state(str(item["item_id"]), str(item.get("batch_id") or ""))
            psource = str(state.get("pricing_source") or state.get("status") or "").upper()
            if "EBAY" in psource or "MARKET" in psource or "EVIDENCE" in psource:
                return "EBAY"
            if "FIXED" in psource:
                return "FIXED"
        except Exception:
            pass
    return "MANUAL"
