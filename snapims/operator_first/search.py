from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from snapims import db
from snapims.config import DataPaths
try:
    from snapims.catalog.normalization import normalize_title
except Exception:
    def normalize_title(value: str) -> str:
        return " ".join(str(value or "").casefold().split())


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    identity: str
    title: str
    movie_id: str
    local_count: int


def _effective_title_sql() -> str:
    return "COALESCE(NULLIF(TRIM(i.title),''),NULLIF(TRIM(rr.suggested_title),''),'')"


def _selected_recognition_join() -> str:
    return """LEFT JOIN item_recognition_selection sel ON sel.item_id=i.item_id
              LEFT JOIN recognition_results rr ON rr.recognition_result_id=sel.recognition_result_id"""


def _item_rows_for_ids(db_file: Path, ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    with db.connect(db_file) as connection:
        rows = connection.execute(
            f"""SELECT i.*, {_effective_title_sql()} AS effective_title,
                       COALESCE(l.movie_id,'') AS movie_id,
                       COALESCE(l.link_status,'') AS movie_link_status
                  FROM items i
                  {_selected_recognition_join()}
                  LEFT JOIN item_movie_links l ON l.item_id=i.item_id
                 WHERE i.item_id IN ({placeholders})
                 ORDER BY i.sequence,i.item_id""",
            ids,
        ).fetchall()
    return [dict(row) for row in rows]


def _exact_effective_rows(db_file: Path, query: str, *, movie_id: str = "") -> list[dict[str, Any]]:
    """Return bounded-by-identity rows without loading the inventory into Python.

    Exact raw-title comparison is the fast path. A small LIKE fallback is normalized
    in Python so punctuation/article variants still resolve without collapsing sequel
    titles (Alien / Aliens / Alien 3).
    """
    query = str(query or "").strip()
    if not query and not movie_id:
        return []
    target = normalize_title(query)
    with db.connect(db_file) as connection:
        if movie_id:
            rows = connection.execute(
                f"""SELECT i.*, {_effective_title_sql()} AS effective_title,
                           COALESCE(l.movie_id,'') AS movie_id,
                           COALESCE(l.link_status,'') AS movie_link_status
                      FROM items i
                      {_selected_recognition_join()}
                      LEFT JOIN item_movie_links l ON l.item_id=i.item_id
                     WHERE l.movie_id=? AND COALESCE(l.link_status,'')<>'STALE'
                     ORDER BY i.sequence,i.item_id""",
                (movie_id,),
            ).fetchall()
            return [dict(row) for row in rows]

        rows = connection.execute(
            f"""SELECT i.*, {_effective_title_sql()} AS effective_title,
                       COALESCE(l.movie_id,'') AS movie_id,
                       COALESCE(l.link_status,'') AS movie_link_status
                  FROM items i
                  {_selected_recognition_join()}
                  LEFT JOIN item_movie_links l ON l.item_id=i.item_id
                 WHERE lower({_effective_title_sql()})=lower(?)
                 ORDER BY i.sequence,i.item_id""",
            (query,),
        ).fetchall()
        exact = [dict(row) for row in rows]
        if exact or not target:
            return exact

        # Fallback is deliberately bounded. It exists for normalized punctuation/article
        # variants, not for aggregation. Every returned row must normalize *exactly*.
        escaped = target.replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        fallback = connection.execute(
            f"""SELECT i.*, {_effective_title_sql()} AS effective_title,
                       COALESCE(l.movie_id,'') AS movie_id,
                       COALESCE(l.link_status,'') AS movie_link_status
                  FROM items i
                  {_selected_recognition_join()}
                  LEFT JOIN item_movie_links l ON l.item_id=i.item_id
                 WHERE lower({_effective_title_sql()}) LIKE ? ESCAPE '\\'
                 ORDER BY i.updated_at DESC
                 LIMIT 500""",
            (pattern,),
        ).fetchall()
    return [dict(row) for row in fallback if normalize_title(str(row["effective_title"] or "")) == target]


def _committed_item_ids(db_file: Path, ids: list[str]) -> set[str]:
    if not ids:
        return set()
    placeholders = ",".join("?" for _ in ids)
    with db.connect(db_file) as connection:
        rows = connection.execute(
            f"""SELECT DISTINCT item_id FROM inventory_events
                 WHERE event_type='INVENTORY_COMMITTED' AND item_id IN ({placeholders})""",
            ids,
        ).fetchall()
    return {str(row[0]) for row in rows}


def _shopify_rows(db_file: Path, ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    with db.connect(db_file) as connection:
        return [dict(row) for row in connection.execute(
            f"""SELECT s.*,i.title,i.batch_id,i.price_cents FROM shopify_sync s
                 JOIN items i ON i.item_id=s.item_id
                 WHERE s.item_id IN ({placeholders}) AND trim(s.product_id)<>''
                 ORDER BY COALESCE(s.last_synced_at,'') DESC""", ids
        ).fetchall()]


def _pricing_rows(db_file: Path, ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    with db.connect(db_file) as connection:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "pricing_item_states" not in tables:
            return []
        cols = {str(row[1]) for row in connection.execute("PRAGMA table_info(pricing_item_states)")}
        selected = [name for name in ("item_id","approved_title","status","pricing_source","current_price_cents","average_cad","median_cad","updated_at") if name in cols]
        placeholders = ",".join("?" for _ in ids)
        return [dict(row) for row in connection.execute(
            f"SELECT {','.join(selected)} FROM pricing_item_states WHERE item_id IN ({placeholders}) ORDER BY updated_at DESC", ids
        ).fetchall()]


def _metadata_for_movie(db_file: Path, movie_id: str) -> dict[str, Any] | None:
    if not movie_id:
        return None
    paths = DataPaths.from_root(db_file.parent.parent)
    if not paths.catalog_db_file.is_file():
        return None
    try:
        from snapims.catalog.service import get_movie
        return get_movie(paths.catalog_db_file, movie_id)
    except Exception:
        return None


def _catalog_identity(db_file: Path, query: str) -> tuple[str, str]:
    """Resolve a unique local catalog identity when available, without network work."""
    paths = DataPaths.from_root(db_file.parent.parent)
    if not paths.catalog_db_file.is_file() or not str(query or "").strip():
        return "", ""
    try:
        from snapims.catalog.service import search_local
        matches = search_local(paths.catalog_db_file, query, limit=5)
        if matches and matches[0].unique:
            return str(matches[0].movie_id), str(matches[0].canonical_title)
    except Exception:
        pass
    return "", ""


def find_title_candidates(db_file: Path, query: str, *, limit: int = 15) -> list[dict[str, Any]]:
    """Bounded discovery only; sequel/remake titles remain separate choices."""
    needle = normalize_title(query)
    if not needle:
        return []
    escaped = needle.replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    max_rows = max(50, min(int(limit) * 20, 500))
    with db.connect(db_file) as connection:
        rows = connection.execute(
            f"""SELECT i.item_id,i.batch_id,i.review_status,i.price_cents,
                       {_effective_title_sql()} AS effective_title,
                       COALESCE(l.movie_id,'') AS movie_id
                  FROM items i
                  {_selected_recognition_join()}
                  LEFT JOIN item_movie_links l ON l.item_id=i.item_id
                 WHERE lower({_effective_title_sql()}) LIKE ? ESCAPE '\\'
                    OR lower(trim(i.sku)) LIKE ? ESCAPE '\\'
                    OR lower(trim(i.item_id)) LIKE ? ESCAPE '\\'
                    OR lower(trim(i.batch_id)) LIKE ? ESCAPE '\\'
                 ORDER BY CASE WHEN lower({_effective_title_sql()})=lower(?) THEN 0 ELSE 1 END,
                          {_effective_title_sql()} COLLATE NOCASE, i.updated_at DESC
                 LIMIT ?""",
            (pattern, pattern, pattern, pattern, str(query or "").strip(), max_rows),
        ).fetchall()
    by_identity: dict[str, dict[str, Any]] = {}
    for row in rows:
        data = dict(row)
        title = str(data.get("effective_title") or data.get("item_id") or "")
        title_key = normalize_title(title) or str(data.get("item_id") or "")
        movie_id = str(data.get("movie_id") or "")
        # A linked remake/edition identity remains a separate search choice even if the title text matches.
        key = f"movie:{movie_id}" if movie_id else f"title:{title_key}"
        current = by_identity.get(key)
        if current is None:
            by_identity[key] = {
                "identity": key,
                "title": title,
                "normalized_title": title_key,
                "movie_id": movie_id,
                "sample_item_id": str(data.get("item_id") or ""),
                "batch_id": str(data.get("batch_id") or ""),
                "review_status": str(data.get("review_status") or ""),
                "price_cents": data.get("price_cents"),
                "count": 1,
            }
        else:
            current["count"] += 1
    return list(by_identity.values())[: max(1, min(int(limit), 50))]


def resolve_candidates(db_file: Path, query: str) -> list[SearchCandidate]:
    """Return distinct canonical/exact identities; never merge substring neighbors."""
    needle = normalize_title(query)
    if not needle:
        return []

    catalog_movie, catalog_title = _catalog_identity(db_file, query)
    rows = _exact_effective_rows(db_file, query)
    if catalog_movie:
        linked_rows = _exact_effective_rows(db_file, query, movie_id=catalog_movie)
        known = {str(row["item_id"]) for row in rows}
        rows.extend(row for row in linked_rows if str(row["item_id"]) not in known)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in rows:
        movie_id = str(item.get("movie_id") or "")
        if movie_id and str(item.get("movie_link_status") or "") == "STALE":
            movie_id = ""
        identity = f"movie:{movie_id}" if movie_id else f"title:{needle}"
        grouped.setdefault(identity, []).append(item)

    # A catalog identity may exist before this exact title has any linked copies. Do not
    # invent a local record count, but keep the identity available if exact rows exist.
    if catalog_movie and rows and f"movie:{catalog_movie}" not in grouped:
        grouped[f"movie:{catalog_movie}"] = []

    candidates: list[SearchCandidate] = []
    for identity, candidate_rows in grouped.items():
        movie_id = identity[6:] if identity.startswith("movie:") else ""
        metadata = _metadata_for_movie(db_file, movie_id)
        title = str(
            (metadata or {}).get("canonical_title")
            or (catalog_title if movie_id == catalog_movie else "")
            or (candidate_rows[0].get("effective_title") if candidate_rows else "")
            or query
        )
        candidates.append(SearchCandidate(identity, title, movie_id, len(candidate_rows)))
    return sorted(candidates, key=lambda c: (-c.local_count, c.title.casefold(), c.identity))


def title_intelligence(db_file: Path, query: str, *, identity: str = "") -> dict[str, Any]:
    candidates = resolve_candidates(db_file, query)
    if not candidates:
        return {"query": query, "status": "NOT_FOUND", "candidates": [], "sales_history_available": False}
    if identity:
        selected = next((candidate for candidate in candidates if candidate.identity == identity), None)
    else:
        selected = candidates[0] if len(candidates) == 1 else None
    if selected is None:
        return {"query": query, "status": "AMBIGUOUS", "candidates": [asdict(c) for c in candidates], "sales_history_available": False}

    if selected.movie_id:
        records = _exact_effective_rows(db_file, selected.title or query, movie_id=selected.movie_id)
    else:
        records = [
            row for row in _exact_effective_rows(db_file, query)
            if not str(row.get("movie_id") or "") or str(row.get("movie_link_status") or "") == "STALE"
        ]
    ids = [str(item["item_id"]) for item in records]
    committed = _committed_item_ids(db_file, ids)
    shopify = _shopify_rows(db_file, ids)
    pricing = _pricing_rows(db_file, ids)
    metadata = _metadata_for_movie(db_file, selected.movie_id)
    current_prices = [int(item["price_cents"]) for item in records if item.get("price_cents") is not None]
    batches = sorted({str(item.get("batch_id") or "") for item in records if item.get("batch_id")})
    locations = sorted({str(item.get("location") or item.get("shelf") or "") for item in records if str(item.get("location") or item.get("shelf") or "").strip()})
    return {
        "query": query,
        "status": "FOUND",
        "identity": selected.identity,
        "title": selected.title,
        "movie_id": selected.movie_id,
        "local_count": len(records),
        "committed_count": sum(1 for item in records if str(item["item_id"]) in committed),
        "pending_count": sum(1 for item in records if str(item["item_id"]) not in committed),
        "shopify_listed_count": len(shopify),
        "shopify": shopify,
        # SnapIMS v0.15 does not persist Shopify order/sales history. Do not invent it.
        "sold_count": None,
        "sales_history_available": False,
        "sales_history_note": "Historical Shopify order/sales data is not synchronized in the v0.15 data model.",
        "batches": batches,
        "locations": locations,
        "pricing_history": pricing,
        "average_current_price_cents": round(sum(current_prices) / len(current_prices)) if current_prices else None,
        "records": records,
        "metadata": metadata,
        "candidates": [asdict(c) for c in candidates],
    }
