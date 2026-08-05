from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from snapims import db as inventory_db
from snapims.catalog import db as catalog_db
from snapims.catalog.models import CatalogLookupRequest, CatalogStatus, LocalMatch, MovieCandidate
from snapims.catalog.normalization import normalize_title, strip_leading_article, title_variants
from snapims.catalog.wikipedia import WikipediaClient
from snapims.config import DataPaths
from snapims.observability import safe_exception, try_emit_event

_ACTIVE: dict[int, threading.Thread] = {}
_LOCK = threading.Lock()


def _float_setting(db_file: Path, key: str, default: float) -> float:
    try:
        return float(catalog_db.get_setting(db_file, key, str(default)))
    except (TypeError, ValueError):
        return default


def _movie_row(connection: sqlite3.Connection, movie_id: str) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM movies WHERE movie_id=?", (movie_id,)).fetchone()
    return dict(row) if row else None


def get_movie(catalog_db_file: Path, movie_id: str) -> dict[str, Any] | None:
    catalog_db.initialize(catalog_db_file, create=False)
    with catalog_db.connect(catalog_db_file, readonly=True) as connection:
        movie = _movie_row(connection, movie_id)
        if movie is None:
            return None
        movie["aliases"] = [
            str(row[0]) for row in connection.execute(
                "SELECT alias FROM movie_aliases WHERE movie_id=? ORDER BY alias", (movie_id,)
            )
        ]
        movie["directors"] = [
            str(row[0]) for row in connection.execute(
                "SELECT person_name FROM movie_credits WHERE movie_id=? AND credit_type='director' ORDER BY billing_order,person_name",
                (movie_id,),
            )
        ]
        movie["genres"] = [
            str(row[0]) for row in connection.execute(
                "SELECT genre FROM movie_genres WHERE movie_id=? ORDER BY genre", (movie_id,)
            )
        ]
        movie["countries"] = [
            str(row[0]) for row in connection.execute(
                "SELECT country FROM movie_countries WHERE movie_id=? ORDER BY country", (movie_id,)
            )
        ]
        movie["languages"] = [
            str(row[0]) for row in connection.execute(
                "SELECT language FROM movie_languages WHERE movie_id=? ORDER BY language", (movie_id,)
            )
        ]
        source = connection.execute(
            "SELECT * FROM movie_sources WHERE movie_id=? AND active=1 ORDER BY movie_source_id DESC LIMIT 1",
            (movie_id,),
        ).fetchone()
        movie["source"] = dict(source) if source else None
    return movie


def _candidate_rows_for_variants(connection: sqlite3.Connection, variants: tuple[str, ...]) -> list[sqlite3.Row]:
    if not variants:
        return []
    placeholders = ",".join("?" for _ in variants)
    return connection.execute(
        f"""SELECT DISTINCT m.*,'canonical' AS match_origin
            FROM movies m
            WHERE m.active=1 AND (m.normalized_title IN ({placeholders}) OR m.articleless_title IN ({placeholders}))
            UNION
            SELECT DISTINCT m.*,'alias' AS match_origin
            FROM movie_aliases a JOIN movies m ON m.movie_id=a.movie_id
            WHERE m.active=1 AND (a.normalized_alias IN ({placeholders}) OR a.articleless_alias IN ({placeholders}))""",
        [*variants, *variants, *variants, *variants],
    ).fetchall()


def search_local(catalog_db_file: Path, title: str, year: int | None = None, *, limit: int = 10) -> list[LocalMatch]:
    catalog_db.initialize(catalog_db_file)
    variants = title_variants(title)
    with catalog_db.connect(catalog_db_file, readonly=True) as connection:
        rows = _candidate_rows_for_variants(connection, variants)
        if not rows and catalog_db.get_setting(catalog_db_file, "fts_available", "0") == "1":
            terms = " ".join(token for token in normalize_title(title).split() if token)
            if terms:
                query = " AND ".join(f'"{token}"' for token in terms.split())
                try:
                    fts_rows = connection.execute(
                        "SELECT movie_id,bm25(movie_search) AS rank FROM movie_search WHERE movie_search MATCH ? ORDER BY rank LIMIT ?",
                        (query, limit),
                    ).fetchall()
                except sqlite3.OperationalError:
                    fts_rows = []
                ids = [str(row[0]) for row in fts_rows]
                if ids:
                    placeholders = ",".join("?" for _ in ids)
                    rows = connection.execute(
                        f"SELECT m.*,'fts' AS match_origin FROM movies m WHERE movie_id IN ({placeholders})",
                        ids,
                    ).fetchall()

    matches: list[LocalMatch] = []
    expected = normalize_title(title)
    for row in rows:
        actual = str(row["normalized_title"])
        origin = str(row["match_origin"])
        score = 0.0
        reasons: list[str] = []
        if actual == expected:
            score = 0.91
            reasons.append("exact normalized canonical title")
        elif actual in variants:
            score = 0.90
            reasons.append("exact conservative title variant")
        elif strip_leading_article(actual) == strip_leading_article(expected):
            score = 0.90
            reasons.append("canonical title differs only by leading article")
        elif origin == "alias":
            score = 0.91
            reasons.append("exact normalized alias")
        else:
            score = 0.70
            reasons.append("local full-text candidate")
        candidate_year = row["primary_release_year"]
        if year is not None and candidate_year is not None:
            if int(candidate_year) == int(year):
                score += 0.08
                reasons.append("release year agrees")
            elif abs(int(candidate_year) - int(year)) <= 1:
                score += 0.02
                reasons.append("release year is within one year")
            else:
                score -= 0.35
                reasons.append("release year conflicts")
        matches.append(
            LocalMatch(
                movie_id=str(row["movie_id"]),
                canonical_title=str(row["canonical_title"]),
                primary_release_year=int(candidate_year) if candidate_year is not None else None,
                match_score=max(0.0, min(score, 1.0)),
                method=f"LOCAL_{origin.upper()}",
                reason="; ".join(reasons),
                unique=False,
            )
        )
    matches.sort(key=lambda result: (result.match_score, result.primary_release_year or -1), reverse=True)
    deduped: list[LocalMatch] = []
    seen: set[str] = set()
    for match in matches:
        if match.movie_id in seen:
            continue
        seen.add(match.movie_id)
        deduped.append(match)
    if deduped:
        threshold = _float_setting(catalog_db_file, "local_exact_threshold", 0.90)
        margin = _float_setting(catalog_db_file, "candidate_margin", 0.08)
        top = deduped[0]
        second = deduped[1] if len(deduped) > 1 else None
        unique = top.match_score >= threshold and (
            second is None or top.match_score - second.match_score >= margin
        )
        deduped[0] = LocalMatch(**{**asdict(top), "unique": unique})
    return deduped[:limit]


def _upsert_fts(connection: sqlite3.Connection, movie_id: str) -> None:
    available = connection.execute(
        "SELECT value FROM catalog_settings WHERE key='fts_available'"
    ).fetchone()
    if not available or str(available[0]) != "1":
        return
    movie = connection.execute(
        "SELECT canonical_title FROM movies WHERE movie_id=?", (movie_id,)
    ).fetchone()
    aliases = [
        str(row[0]) for row in connection.execute(
            "SELECT alias FROM movie_aliases WHERE movie_id=?", (movie_id,)
        )
    ]
    connection.execute("DELETE FROM movie_search WHERE movie_id=?", (movie_id,))
    connection.execute(
        "INSERT INTO movie_search(movie_id,title,aliases) VALUES(?,?,?)",
        (movie_id, str(movie[0]), " | ".join(aliases)),
    )


def create_or_update_movie(catalog_db_file: Path, candidate: MovieCandidate) -> tuple[str, bool]:
    """Insert one durable Movie, preventing duplicate source or title/year rows."""

    catalog_db.initialize(catalog_db_file)
    normalized = normalize_title(candidate.canonical_title)
    articleless = strip_leading_article(normalized)
    with catalog_db.transaction(catalog_db_file) as connection:
        existing = connection.execute(
            """SELECT movie_id FROM movie_sources
               WHERE provider_name=? AND source_page_id=?""",
            (candidate.provider, candidate.source_page_id),
        ).fetchone()
        if existing:
            movie_id = str(existing[0])
            created = False
        else:
            duplicate = connection.execute(
                """SELECT movie_id FROM movies
                   WHERE normalized_title=? AND primary_release_year IS ? AND media_type=? AND active=1
                   ORDER BY movie_id LIMIT 1""",
                (normalized, candidate.release_year, candidate.media_type),
            ).fetchone()
            if duplicate:
                movie_id = str(duplicate[0])
                created = False
            else:
                movie_id = catalog_db.next_movie_id(connection)
                timestamp = catalog_db.now()
                connection.execute(
                    """INSERT INTO movies(
                           movie_id,canonical_title,normalized_title,articleless_title,original_title,
                           primary_release_year,release_date,media_type,runtime_minutes,concise_summary,
                           active,data_quality_status,catalog_revision,created_at,updated_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        movie_id,
                        candidate.canonical_title,
                        normalized,
                        articleless,
                        candidate.original_title,
                        candidate.release_year,
                        candidate.release_date,
                        candidate.media_type,
                        candidate.runtime_minutes,
                        candidate.summary,
                        1,
                        "SOURCE_VERIFIED",
                        1,
                        timestamp,
                        timestamp,
                    ),
                )
                created = True
        timestamp = catalog_db.now()
        connection.execute(
            """INSERT INTO movie_sources(
                   movie_id,provider_name,source_page_title,source_page_id,source_url,
                   source_revision_id,retrieved_at,parser_version,raw_response_hash,
                   attribution_data,refresh_eligible,field_provenance_json,active
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1)
               ON CONFLICT(provider_name,source_page_id) DO UPDATE SET
                   movie_id=excluded.movie_id,source_page_title=excluded.source_page_title,
                   source_url=excluded.source_url,source_revision_id=excluded.source_revision_id,
                   retrieved_at=excluded.retrieved_at,parser_version=excluded.parser_version,
                   raw_response_hash=excluded.raw_response_hash,
                   attribution_data=excluded.attribution_data,active=1""",
            (
                movie_id,
                candidate.provider,
                candidate.source_page_title,
                candidate.source_page_id,
                candidate.source_url,
                candidate.source_revision_id,
                candidate.retrieved_at or timestamp,
                candidate.parser_version or catalog_db.CATALOG_PARSER_VERSION,
                candidate.raw_response_hash,
                candidate.attribution,
                1,
                json.dumps(
                    {
                        "canonical_title": candidate.source_url,
                        "release_year": candidate.source_url,
                        "runtime_minutes": candidate.source_url,
                        "directors": candidate.source_url,
                        "genres": candidate.source_url,
                        "countries": candidate.source_url,
                        "languages": candidate.source_url,
                        "summary": candidate.source_url,
                    }
                ),
            ),
        )
        aliases = [candidate.canonical_title, candidate.original_title, *candidate.aliases]
        for alias in aliases:
            alias = alias.strip()
            if not alias:
                continue
            normalized_alias = normalize_title(alias)
            connection.execute(
                """INSERT OR IGNORE INTO movie_aliases(
                       movie_id,alias,normalized_alias,articleless_alias,alias_type,language,
                       source,source_page_id,created_at
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    movie_id,
                    alias,
                    normalized_alias,
                    strip_leading_article(normalized_alias),
                    "canonical" if alias == candidate.canonical_title else "alternate",
                    "en",
                    candidate.provider,
                    candidate.source_page_id,
                    timestamp,
                ),
            )
        for director_index, director in enumerate(candidate.directors, start=1):
            connection.execute(
                """INSERT OR IGNORE INTO movie_credits(
                       movie_id,person_name,credit_type,billing_order,source,created_at
                   ) VALUES(?,?,'director',?,?,?)""",
                (movie_id, director, director_index, candidate.provider, timestamp),
            )
        for table, column, values in (
            ("movie_genres", "genre", candidate.genres),
            ("movie_countries", "country", candidate.countries),
            ("movie_languages", "language", candidate.languages),
        ):
            for value in values:
                connection.execute(
                    f"INSERT OR IGNORE INTO {table}(movie_id,{column},source) VALUES(?,?,?)",
                    (movie_id, value, candidate.provider),
                )
        movie = connection.execute(
            "SELECT catalog_revision FROM movies WHERE movie_id=?", (movie_id,)
        ).fetchone()
        revision = int(movie[0]) if movie else 1
        connection.execute(
            """INSERT INTO catalog_events(
                   occurred_at,event_type,movie_id,catalog_revision,source,details_json
               ) VALUES(?,?,?,?,?,?)""",
            (
                timestamp,
                "MOVIE_CREATED" if created else "MOVIE_SOURCE_REFRESHED",
                movie_id,
                revision,
                candidate.provider,
                json.dumps({"source_page_id": candidate.source_page_id, "title": candidate.canonical_title}),
            ),
        )
        _upsert_fts(connection, movie_id)
    return movie_id, created


def build_lookup_request(inventory_db_file: Path, recognition_result_id: int) -> CatalogLookupRequest:
    with inventory_db.connect(inventory_db_file) as connection:
        row = connection.execute(
            """SELECT r.*,i.batch_id FROM recognition_results r
               JOIN items i ON i.item_id=r.item_id
               WHERE r.recognition_result_id=?""",
            (recognition_result_id,),
        ).fetchone()
    if row is None:
        raise KeyError(f"Unknown recognition result: {recognition_result_id}")
    return CatalogLookupRequest(
        item_id=str(row["item_id"]),
        recognition_result_id=int(row["recognition_result_id"]),
        proposed_title=str(row["suggested_title"] or "").strip(),
        proposed_year=int(row["release_year"]) if row["release_year"] is not None else None,
        distributor_clues=str(row["distributor"] or ""),
        edition_clues=str(row["edition"] or ""),
        confidence=float(row["confidence"]) if row["confidence"] is not None else None,
    )


def _ensure_job(catalog_db_file: Path, request: CatalogLookupRequest, status: str) -> int:
    payload = json.dumps(asdict(request), ensure_ascii=False)
    timestamp = catalog_db.now()
    with catalog_db.transaction(catalog_db_file) as connection:
        connection.execute(
            """INSERT INTO catalog_lookup_jobs(
                   recognition_result_id,item_id,proposed_title,normalized_title,proposed_year,
                   request_json,status,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(recognition_result_id) DO NOTHING""",
            (
                request.recognition_result_id,
                request.item_id,
                request.proposed_title,
                normalize_title(request.proposed_title),
                request.proposed_year,
                payload,
                status,
                timestamp,
                timestamp,
            ),
        )
        row = connection.execute(
            "SELECT job_id FROM catalog_lookup_jobs WHERE recognition_result_id=?",
            (request.recognition_result_id,),
        ).fetchone()
    assert row is not None
    return int(row[0])


def _inventory_link(
    paths: DataPaths,
    request: CatalogLookupRequest,
    movie_id: str,
    *,
    status: str,
    method: str,
    score: float,
    operator_confirmed: bool = False,
) -> None:
    movie = get_movie(paths.catalog_db_file, movie_id)
    if movie is None:
        raise RuntimeError(f"Catalog Movie does not exist: {movie_id}")
    inventory_db.set_item_movie_link(
        paths.db_file,
        item_id=request.item_id,
        movie_id=movie_id,
        link_status=status,
        link_method=method,
        # Negative IDs are stable catalog-only identities for manual title jobs.
        # They are not rows in inventory.recognition_results and must never be
        # persisted as an inventory recognition foreign reference.
        recognition_result_id=(
            request.recognition_result_id if request.recognition_result_id > 0 else None
        ),
        match_score=score,
        operator_confirmed=operator_confirmed,
        catalog_revision=int(movie["catalog_revision"]),
    )


def _record_decision(
    catalog_db_file: Path,
    *,
    job_id: int,
    request: CatalogLookupRequest,
    movie_id: str | None,
    candidate_id: int | None,
    decision_type: str,
    reason: str,
    score: float | None,
    operator_confirmed: bool = False,
) -> None:
    with catalog_db.transaction(catalog_db_file) as connection:
        connection.execute(
            """INSERT INTO movie_match_decisions(
                   job_id,item_id,recognition_result_id,selected_movie_id,selected_candidate_id,
                   decision_type,decision_reason,match_score,operator_confirmed,decided_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                job_id,
                request.item_id,
                request.recognition_result_id,
                movie_id,
                candidate_id,
                decision_type,
                reason,
                score,
                int(operator_confirmed),
                catalog_db.now(),
            ),
        )


def queue_recognition_lookup(paths: DataPaths, recognition_result_id: int, *, start_worker: bool = True) -> int | None:
    """Search locally inline; queue only the bounded external miss path."""

    try:
        catalog_db.initialize(paths.catalog_db_file, paths=paths)
    except Exception as exc:
        request = build_lookup_request(paths.db_file, recognition_result_id)
        inventory_db.mark_item_catalog_unavailable(
            paths.db_file, request.item_id, recognition_result_id, str(exc)
        )
        safe = safe_exception(exc)
        try_emit_event(
            paths.db_file,
            component="catalog",
            event_type="catalog.unavailable",
            severity="ERROR",
            item_id=request.item_id,
            provider="local_catalog",
            status="UNAVAILABLE",
            outcome="CATALOG_INITIALIZATION_FAILED",
            error_class=safe["error_class"],
            safe_summary=safe["safe_summary"],
            paths=paths,
        )
        return None
    request = build_lookup_request(paths.db_file, recognition_result_id)
    if not request.proposed_title:
        job_id = _ensure_job(paths.catalog_db_file, request, "NOT_FOUND")
        with catalog_db.transaction(paths.catalog_db_file) as connection:
            connection.execute(
                "UPDATE catalog_lookup_jobs SET finished_at=?,updated_at=?,last_error=? WHERE job_id=?",
                (catalog_db.now(), catalog_db.now(), "Recognition did not provide a title", job_id),
            )
        try_emit_event(
            paths.db_file,
            component="catalog",
            event_type="catalog.not_found",
            severity="WARNING",
            operation_id=f"catalog:{job_id}",
            item_id=request.item_id,
            provider="local_catalog",
            status="NOT_FOUND",
            outcome="NO_TITLE",
            safe_summary="Recognition did not provide a title for catalog lookup.",
            paths=paths,
        )
        return job_id
    job_id = _ensure_job(paths.catalog_db_file, request, "SEARCHING_LOCAL")
    try_emit_event(
        paths.db_file,
        component="catalog",
        event_type="catalog.local_search_started",
        operation_id=f"catalog:{job_id}",
        item_id=request.item_id,
        provider="local_catalog",
        status="SEARCHING_LOCAL",
        detail={"recognition_result_id": recognition_result_id},
        paths=paths,
    )
    matches = search_local(paths.catalog_db_file, request.proposed_title, request.proposed_year)
    if matches and matches[0].unique:
        match = matches[0]
        _inventory_link(
            paths,
            request,
            match.movie_id,
            status="LOCAL_MATCH",
            method=match.method,
            score=match.match_score,
        )
        with catalog_db.transaction(paths.catalog_db_file) as connection:
            connection.execute(
                """UPDATE catalog_lookup_jobs SET status='LOCAL_MATCHED',selected_movie_id=?,
                       link_state='LINKED',updated_at=?,finished_at=?,candidate_count=? WHERE job_id=?""",
                (match.movie_id, catalog_db.now(), catalog_db.now(), len(matches), job_id),
            )
        _record_decision(
            paths.catalog_db_file,
            job_id=job_id,
            request=request,
            movie_id=match.movie_id,
            candidate_id=None,
            decision_type="AUTO_LOCAL",
            reason=match.reason,
            score=match.match_score,
        )
        try_emit_event(
            paths.db_file,
            component="catalog",
            event_type="catalog.local_match_linked",
            operation_id=f"catalog:{job_id}",
            item_id=request.item_id,
            movie_id=match.movie_id,
            provider="local_catalog",
            status="LOCAL_MATCHED",
            outcome="LINKED",
            detail={
                "candidate_count": len(matches),
                "match_method": match.method,
                "match_score": match.match_score,
            },
            retention_class="BUSINESS",
            paths=paths,
        )
        return job_id
    with catalog_db.transaction(paths.catalog_db_file) as connection:
        connection.execute(
            "UPDATE catalog_lookup_jobs SET status='QUEUED',candidate_count=?,updated_at=? WHERE job_id=?",
            (len(matches), catalog_db.now(), job_id),
        )
    try_emit_event(
        paths.db_file,
        component="catalog",
        event_type="catalog.candidate_request_queued",
        operation_id=f"catalog:{job_id}",
        item_id=request.item_id,
        provider="wikipedia",
        status="QUEUED",
        outcome="LOCAL_AMBIGUOUS" if matches else "LOCAL_MISS",
        detail={"local_candidate_count": len(matches)},
        paths=paths,
    )
    if start_worker:
        start_catalog_job(paths, job_id)
    return job_id


def _candidate_payload(candidate: MovieCandidate) -> dict[str, Any]:
    data = asdict(candidate)
    data.pop("raw", None)
    return data


def _select_wikipedia_candidate(
    catalog_db_file: Path, candidates: list[MovieCandidate]
) -> tuple[MovieCandidate | None, str]:
    credible = [candidate for candidate in candidates if not candidate.rejected_reason and candidate.score > 0]
    if not credible:
        return None, "No credible film candidate"
    threshold = _float_setting(catalog_db_file, "automatic_wikipedia_threshold", 0.92)
    margin = _float_setting(catalog_db_file, "candidate_margin", 0.08)
    top = credible[0]
    second = credible[1] if len(credible) > 1 else None
    if top.score < threshold:
        return None, f"Top candidate did not meet configured evidence threshold ({top.score:.2f})"
    if second is not None and top.score - second.score < margin:
        return None, "Top candidates are too close to select safely"
    if top.media_type != "film":
        return None, f"Top candidate is classified as {top.media_type}, not a commercial movie"
    return top, "; ".join(top.evidence)


def _run_job(paths: DataPaths, job_id: int, client: WikipediaClient | None = None) -> None:
    try:
        with catalog_db.connect(paths.catalog_db_file, readonly=True) as connection:
            row = connection.execute(
                "SELECT * FROM catalog_lookup_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        if row is None:
            return
        if str(row["status"]) in {"LOCAL_MATCHED", "MOVIE_CREATED", "LINKED", "NOT_FOUND", "AMBIGUOUS"}:
            return
        request = CatalogLookupRequest(**json.loads(str(row["request_json"])))
        try_emit_event(
            paths.db_file,
            component="catalog",
            event_type="catalog.external_search_started",
            operation_id=f"catalog:{job_id}",
            item_id=request.item_id,
            provider="wikipedia",
            attempt_number=int(row["attempt_count"] or 0) + 1,
            status="SEARCHING_WIKIPEDIA",
            paths=paths,
        )
        attempt_started = catalog_db.now()
        with catalog_db.transaction(paths.catalog_db_file) as connection:
            connection.execute(
                """UPDATE catalog_lookup_jobs SET status='SEARCHING_WIKIPEDIA',attempt_count=attempt_count+1,
                       started_at=COALESCE(started_at,?),updated_at=?,last_error='' WHERE job_id=?""",
                (attempt_started, attempt_started, job_id),
            )
            cursor = connection.execute(
                """INSERT INTO catalog_lookup_attempts(
                       job_id,phase,provider_name,started_at,status,request_hash
                   ) VALUES(?,'EXTERNAL_SEARCH','wikipedia',?,'RUNNING',?)""",
                (
                    job_id,
                    attempt_started,
                    uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(asdict(request), sort_keys=True)).hex,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a catalog attempt ID")
            attempt_id = cursor.lastrowid
        wikipedia = client or WikipediaClient(paths.catalog_db_file)
        limit = int(catalog_db.get_setting(paths.catalog_db_file, "wikipedia_max_candidates", "5"))
        candidates = wikipedia.search_candidates(
            request.proposed_title, request.proposed_year, limit=max(1, min(limit, 5))
        )
        candidate_ids: dict[str, int] = {}
        with catalog_db.transaction(paths.catalog_db_file) as connection:
            for candidate in candidates:
                cursor = connection.execute(
                    """INSERT INTO movie_candidates(
                           job_id,provider_name,source_page_id,source_page_title,source_url,
                           canonical_title,release_year,media_type,score,evidence_json,
                           rejected_reason,candidate_payload_json,created_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(job_id,provider_name,source_page_id) DO UPDATE SET
                           source_page_title=excluded.source_page_title,source_url=excluded.source_url,
                           canonical_title=excluded.canonical_title,release_year=excluded.release_year,
                           media_type=excluded.media_type,score=excluded.score,
                           evidence_json=excluded.evidence_json,rejected_reason=excluded.rejected_reason,
                           candidate_payload_json=excluded.candidate_payload_json""",
                    (
                        job_id,
                        candidate.provider,
                        candidate.source_page_id,
                        candidate.source_page_title,
                        candidate.source_url,
                        candidate.canonical_title,
                        candidate.release_year,
                        candidate.media_type,
                        candidate.score,
                        json.dumps(candidate.evidence),
                        candidate.rejected_reason,
                        json.dumps(_candidate_payload(candidate), ensure_ascii=False),
                        catalog_db.now(),
                    ),
                )
                candidate_id = int(cursor.lastrowid or connection.execute(
                    "SELECT candidate_id FROM movie_candidates WHERE job_id=? AND provider_name=? AND source_page_id=?",
                    (job_id, candidate.provider, candidate.source_page_id),
                ).fetchone()[0])
                candidate_ids[candidate.source_page_id] = candidate_id
            connection.execute(
                "UPDATE catalog_lookup_jobs SET status='CANDIDATES_FOUND',candidate_count=?,updated_at=? WHERE job_id=?",
                (len(candidates), catalog_db.now(), job_id),
            )
        selected, reason = _select_wikipedia_candidate(paths.catalog_db_file, candidates)
        if selected is None:
            status = "AMBIGUOUS" if candidates else "NOT_FOUND"
            with catalog_db.transaction(paths.catalog_db_file) as connection:
                connection.execute(
                    """UPDATE catalog_lookup_jobs SET status=?,updated_at=?,finished_at=?,last_error=?
                       WHERE job_id=?""",
                    (status, catalog_db.now(), catalog_db.now(), reason, job_id),
                )
                connection.execute(
                    """UPDATE catalog_lookup_attempts SET finished_at=?,status='SUCCESS',metadata_json=?
                       WHERE attempt_id=?""",
                    (catalog_db.now(), json.dumps({"candidates": len(candidates), "decision": status}), attempt_id),
                )
            try_emit_event(
                paths.db_file,
                component="catalog",
                event_type=(
                    "catalog.ambiguous" if candidates else "catalog.not_found"
                ),
                severity="WARNING",
                operation_id=f"catalog:{job_id}",
                item_id=request.item_id,
                provider="wikipedia",
                attempt_number=int(row["attempt_count"] or 0) + 1,
                status=status,
                outcome=status,
                safe_summary=reason,
                detail={"candidate_count": len(candidates)},
                paths=paths,
            )
            return
        # Repeat duplicate check and insertion inside the same catalog transaction path.
        movie_id, created = create_or_update_movie(paths.catalog_db_file, selected)
        selected_candidate_id = candidate_ids.get(selected.source_page_id)
        with catalog_db.transaction(paths.catalog_db_file) as connection:
            connection.execute(
                """UPDATE catalog_lookup_jobs SET status='MOVIE_CREATED',selected_movie_id=?,
                       link_state='LINK_PENDING',updated_at=? WHERE job_id=?""",
                (movie_id, catalog_db.now(), job_id),
            )
        _record_decision(
            paths.catalog_db_file,
            job_id=job_id,
            request=request,
            movie_id=movie_id,
            candidate_id=selected_candidate_id,
            decision_type="AUTO_WIKIPEDIA",
            reason=reason,
            score=selected.score,
        )
        try:
            _inventory_link(
                paths,
                request,
                movie_id,
                status="NEW_WIKIPEDIA_RECORD" if created else "LOCAL_MATCH",
                method="WIKIPEDIA_INGEST" if created else "WIKIPEDIA_REUSED",
                score=selected.score,
            )
        except Exception as exc:
            with catalog_db.transaction(paths.catalog_db_file) as connection:
                connection.execute(
                    """UPDATE catalog_lookup_jobs SET status='LINK_PENDING',link_state='LINK_PENDING',
                           last_error=?,updated_at=? WHERE job_id=?""",
                    (str(exc), catalog_db.now(), job_id),
                )
            safe = safe_exception(exc)
            try_emit_event(
                paths.db_file,
                component="catalog",
                event_type="catalog.link_failed",
                severity="ERROR",
                operation_id=f"catalog:{job_id}",
                item_id=request.item_id,
                movie_id=movie_id,
                provider="wikipedia",
                status="LINK_PENDING",
                outcome="LINK_FAILED",
                error_class=safe["error_class"],
                safe_summary=safe["safe_summary"],
                paths=paths,
            )
            return
        with catalog_db.transaction(paths.catalog_db_file) as connection:
            connection.execute(
                """UPDATE catalog_lookup_jobs SET status='LINKED',link_state='LINKED',
                       updated_at=?,finished_at=?,last_error='' WHERE job_id=?""",
                (catalog_db.now(), catalog_db.now(), job_id),
            )
            connection.execute(
                """UPDATE catalog_lookup_attempts SET finished_at=?,status='SUCCESS',metadata_json=?
                   WHERE attempt_id=?""",
                (
                    catalog_db.now(),
                    json.dumps({"movie_id": movie_id, "created": created, "candidate_count": len(candidates)}),
                    attempt_id,
                ),
            )
        try_emit_event(
            paths.db_file,
            component="catalog",
            event_type="catalog.linked",
            operation_id=f"catalog:{job_id}",
            item_id=request.item_id,
            movie_id=movie_id,
            provider="wikipedia",
            attempt_number=int(row["attempt_count"] or 0) + 1,
            status="LINKED",
            outcome="MOVIE_CREATED" if created else "MOVIE_REUSED",
            detail={"candidate_count": len(candidates), "match_score": selected.score},
            retention_class="BUSINESS",
            paths=paths,
        )
    except Exception as exc:
        code = getattr(exc, "code", exc.__class__.__name__)
        with catalog_db.transaction(paths.catalog_db_file) as connection:
            connection.execute(
                """UPDATE catalog_lookup_jobs SET status='FAILED',last_error=?,updated_at=?,finished_at=?
                   WHERE job_id=?""",
                (str(exc), catalog_db.now(), catalog_db.now(), job_id),
            )
            connection.execute(
                """UPDATE catalog_lookup_attempts SET finished_at=?,status='FAILED',error_code=?,error_message=?
                   WHERE job_id=? AND status='RUNNING'""",
                (catalog_db.now(), code, str(exc), job_id),
            )
        safe = safe_exception(exc)
        try_emit_event(
            paths.db_file,
            component="catalog",
            event_type="catalog.failed",
            severity="ERROR",
            operation_id=f"catalog:{job_id}",
            provider="wikipedia",
            status="FAILED",
            outcome=str(code),
            error_class=safe["error_class"],
            safe_summary=safe["safe_summary"],
            paths=paths,
        )
    finally:
        with _LOCK:
            _ACTIVE.pop(job_id, None)


def start_catalog_job(paths: DataPaths, job_id: int, *, client: WikipediaClient | None = None) -> bool:
    with _LOCK:
        active = _ACTIVE.get(job_id)
        if active and active.is_alive():
            return False
        thread = threading.Thread(target=_run_job, args=(paths, job_id, client), daemon=True)
        _ACTIVE[job_id] = thread
        thread.start()
    return True


def process_catalog_job_sync(paths: DataPaths, job_id: int, *, client: WikipediaClient | None = None) -> None:
    _run_job(paths, job_id, client)


def recover_catalog_jobs(paths: DataPaths, *, start_workers: bool = True) -> int:
    try:
        catalog_db.initialize(paths.catalog_db_file, paths=paths, create=False)
    except FileNotFoundError:
        return 0
    with catalog_db.transaction(paths.catalog_db_file) as connection:
        connection.execute(
            """UPDATE catalog_lookup_jobs SET status='PAUSED',lease_owner='',lease_expires_at=NULL,
                   updated_at=?,last_error=CASE WHEN last_error='' THEN 'Interrupted by process restart' ELSE last_error END
               WHERE status IN ('SEARCHING_WIKIPEDIA','CANDIDATES_FOUND')""",
            (catalog_db.now(),),
        )
        rows = connection.execute(
            """SELECT job_id FROM catalog_lookup_jobs
               WHERE status IN ('QUEUED','PAUSED','LINK_PENDING') ORDER BY job_id"""
        ).fetchall()
    if start_workers:
        for row in rows:
            start_catalog_job(paths, int(row[0]))
    return len(rows)


def reconcile_pending_links(paths: DataPaths) -> int:
    try:
        catalog_db.initialize(paths.catalog_db_file, create=False)
    except Exception:
        return 0
    with catalog_db.connect(paths.catalog_db_file, readonly=True) as connection:
        rows = connection.execute(
            """SELECT * FROM catalog_lookup_jobs
               WHERE status='LINK_PENDING' OR link_state='LINK_PENDING' ORDER BY job_id"""
        ).fetchall()
    linked = 0
    for row in rows:
        request = CatalogLookupRequest(**json.loads(str(row["request_json"])))
        movie_id = str(row["selected_movie_id"] or "")
        if not movie_id:
            continue
        try:
            _inventory_link(
                paths,
                request,
                movie_id,
                status="LOCAL_MATCH",
                method="RECONCILIATION",
                score=1.0,
            )
        except Exception as exc:
            with catalog_db.transaction(paths.catalog_db_file) as connection:
                connection.execute(
                    "UPDATE catalog_lookup_jobs SET last_error=?,updated_at=? WHERE job_id=?",
                    (str(exc), catalog_db.now(), int(row["job_id"])),
                )
            continue
        with catalog_db.transaction(paths.catalog_db_file) as connection:
            connection.execute(
                "UPDATE catalog_lookup_jobs SET status='LINKED',link_state='LINKED',last_error='',updated_at=?,finished_at=? WHERE job_id=?",
                (catalog_db.now(), catalog_db.now(), int(row["job_id"])),
            )
        linked += 1
    return linked


def latest_job(catalog_db_file: Path, *, item_id: str = "", recognition_result_id: int | None = None) -> dict[str, Any] | None:
    try:
        catalog_db.initialize(catalog_db_file, create=False)
    except Exception:
        return None
    value: int | str
    if recognition_result_id is not None:
        where, value = "recognition_result_id=?", recognition_result_id
    else:
        where, value = "item_id=?", item_id
    with catalog_db.connect(catalog_db_file, readonly=True) as connection:
        row = connection.execute(
            f"SELECT * FROM catalog_lookup_jobs WHERE {where} ORDER BY job_id DESC LIMIT 1", (value,)
        ).fetchone()
    return dict(row) if row else None


def get_catalog_status(paths: DataPaths, item_id: str) -> CatalogStatus:
    link = inventory_db.get_item_movie_link(paths.db_file, item_id)
    try:
        catalog_db.initialize(paths.catalog_db_file, create=False)
    except Exception as exc:
        return CatalogStatus(
            False,
            "CATALOG_UNAVAILABLE",
            "Catalog unavailable",
            movie_id=str(link.get("movie_id") or "") if link else "",
            error=str(exc),
        )
    if link and link.get("movie_id"):
        try:
            movie = get_movie(paths.catalog_db_file, str(link["movie_id"]))
        except Exception as exc:
            return CatalogStatus(False, "CATALOG_UNAVAILABLE", "Catalog unavailable", error=str(exc))
        if movie is None:
            return CatalogStatus(
                False,
                "MISSING_MOVIE",
                "Catalog link missing",
                movie_id=str(link["movie_id"]),
                error="The linked Movie record is absent from movie_catalog.sqlite3",
            )
        source = movie.get("source") or {}
        return CatalogStatus(
            True,
            str(link["link_status"]),
            "Local match" if str(link["link_status"]) == "LOCAL_MATCH" else "New catalog record",
            movie_id=str(movie["movie_id"]),
            canonical_title=str(movie["canonical_title"]),
            primary_release_year=movie["primary_release_year"],
            match_method=str(link["link_method"]),
            match_score=float(link["match_score"]) if link["match_score"] is not None else None,
            source_url=str(source.get("source_url") or ""),
        )
    job = latest_job(paths.catalog_db_file, item_id=item_id)
    if not job:
        if link and str(link.get("link_status")) == "CATALOG_UNAVAILABLE":
            return CatalogStatus(False, "CATALOG_UNAVAILABLE", "Catalog unavailable", error=str(link.get("last_error") or ""))
        return CatalogStatus(True, "NOT_REQUIRED", "Catalog pending")
    status = str(job["status"])
    labels = {
        "QUEUED": "Searching",
        "SEARCHING_LOCAL": "Searching",
        "SEARCHING_WIKIPEDIA": "Searching Wikipedia",
        "CANDIDATES_FOUND": "Candidates found",
        "AMBIGUOUS": "Ambiguous",
        "NOT_FOUND": "Not found",
        "FAILED": "Failed",
        "PAUSED": "Paused",
        "LINK_PENDING": "Link pending",
    }
    return CatalogStatus(
        True,
        status,
        labels.get(status, status.replace("_", " ").title()),
        movie_id=str(job.get("selected_movie_id") or ""),
        candidate_count=int(job.get("candidate_count") or 0),
        error=str(job.get("last_error") or ""),
        materially_ambiguous=status == "AMBIGUOUS",
    )


def select_candidate(paths: DataPaths, job_id: int, candidate_id: int, *, operator: str = "OPERATOR") -> str:
    with catalog_db.connect(paths.catalog_db_file, readonly=True) as connection:
        job = connection.execute("SELECT * FROM catalog_lookup_jobs WHERE job_id=?", (job_id,)).fetchone()
        candidate_row = connection.execute(
            "SELECT * FROM movie_candidates WHERE candidate_id=? AND job_id=?", (candidate_id, job_id)
        ).fetchone()
    if job is None or candidate_row is None:
        raise KeyError("Unknown catalog job or candidate")
    request = CatalogLookupRequest(**json.loads(str(job["request_json"])))
    payload = json.loads(str(candidate_row["candidate_payload_json"]))
    candidate = MovieCandidate(**payload)
    movie_id, created = create_or_update_movie(paths.catalog_db_file, candidate)
    _inventory_link(
        paths,
        request,
        movie_id,
        status="NEW_WIKIPEDIA_RECORD" if created else "LOCAL_MATCH",
        method="OPERATOR_CANDIDATE_SELECTION",
        score=float(candidate_row["score"]),
        operator_confirmed=True,
    )
    _record_decision(
        paths.catalog_db_file,
        job_id=job_id,
        request=request,
        movie_id=movie_id,
        candidate_id=candidate_id,
        decision_type="OPERATOR_SELECTED",
        reason=f"Selected by {operator}",
        score=float(candidate_row["score"]),
        operator_confirmed=True,
    )
    with catalog_db.transaction(paths.catalog_db_file) as connection:
        connection.execute(
            """UPDATE catalog_lookup_jobs SET status='LINKED',selected_movie_id=?,link_state='LINKED',
                   updated_at=?,finished_at=?,last_error='' WHERE job_id=?""",
            (movie_id, catalog_db.now(), catalog_db.now(), job_id),
        )
    return movie_id


def queue_operator_title_correction(paths: DataPaths, item_id: str, title: str, year: int | None) -> int:
    inventory_db.mark_item_movie_link_stale(paths.db_file, item_id, reason="Operator changed title")
    with inventory_db.connect(paths.db_file) as connection:
        latest = connection.execute(
            "SELECT recognition_result_id FROM recognition_results WHERE item_id=? ORDER BY recognition_result_id DESC LIMIT 1",
            (item_id,),
        ).fetchone()
    # catalog_lookup_jobs requires one stable, unique request identity. Manual
    # records have no recognition_results row, so derive a deterministic negative
    # identifier from the immutable Item ID. It cannot collide with SQLite
    # AUTOINCREMENT recognition IDs, which are always positive.
    synthetic_recognition_id = (
        int(latest[0])
        if latest
        else -max(1, int.from_bytes(hashlib.sha256(item_id.encode("utf-8")).digest()[:8], "big") & ((1 << 63) - 1))
    )
    request = CatalogLookupRequest(
        item_id=item_id,
        recognition_result_id=synthetic_recognition_id,
        proposed_title=title,
        proposed_year=year,
        confidence=1.0,
    )
    catalog_db.initialize(paths.catalog_db_file, paths=paths)
    # A correction can share the original recognition id; remove only a stale terminal job for that id.
    with catalog_db.transaction(paths.catalog_db_file) as connection:
        existing = connection.execute(
            "SELECT job_id FROM catalog_lookup_jobs WHERE recognition_result_id=?", (synthetic_recognition_id,)
        ).fetchone()
        if existing:
            connection.execute(
                """UPDATE catalog_lookup_jobs SET proposed_title=?,normalized_title=?,proposed_year=?,
                       request_json=?,status='SEARCHING_LOCAL',selected_movie_id=NULL,link_state='NOT_LINKED',
                       candidate_count=0,last_error='',updated_at=?,finished_at=NULL WHERE job_id=?""",
                (
                    title,
                    normalize_title(title),
                    year,
                    json.dumps(asdict(request)),
                    catalog_db.now(),
                    int(existing[0]),
                ),
            )
            job_id = int(existing[0])
        else:
            job_id = 0
    # Never open a nested SQLite write transaction: that blocks Review for the full busy timeout.
    if not job_id:
        job_id = _ensure_job(paths.catalog_db_file, request, "SEARCHING_LOCAL")
    matches = search_local(paths.catalog_db_file, title, year)
    if matches and matches[0].unique:
        match = matches[0]
        _inventory_link(
            paths,
            request,
            match.movie_id,
            status="LOCAL_MATCH",
            method="OPERATOR_CORRECTION_LOCAL",
            score=match.match_score,
            operator_confirmed=True,
        )
        with catalog_db.transaction(paths.catalog_db_file) as connection:
            connection.execute(
                "UPDATE catalog_lookup_jobs SET status='LINKED',selected_movie_id=?,link_state='LINKED',updated_at=?,finished_at=? WHERE job_id=?",
                (match.movie_id, catalog_db.now(), catalog_db.now(), job_id),
            )
    else:
        with catalog_db.transaction(paths.catalog_db_file) as connection:
            connection.execute(
                "UPDATE catalog_lookup_jobs SET status='QUEUED',updated_at=? WHERE job_id=?",
                (catalog_db.now(), job_id),
            )
        if not os.getenv("PYTEST_CURRENT_TEST"):
            start_catalog_job(paths, job_id)
    return job_id


def wait_for_catalog_job(catalog_db_file: Path, job_id: int, *, timeout: float = 10.0) -> dict[str, Any]:
    import time

    deadline = time.monotonic() + timeout
    terminal = {"LOCAL_MATCHED", "LINKED", "AMBIGUOUS", "NOT_FOUND", "FAILED", "PAUSED"}
    while time.monotonic() < deadline:
        with catalog_db.connect(catalog_db_file, readonly=True) as connection:
            row = connection.execute("SELECT * FROM catalog_lookup_jobs WHERE job_id=?", (job_id,)).fetchone()
        if row and str(row["status"]) in terminal:
            return dict(row)
        time.sleep(0.01)
    raise TimeoutError(f"Catalog job {job_id} did not finish")


def catalog_output_for_item(paths: DataPaths, item_id: str) -> dict[str, Any]:
    """Return a compact, read-only Movie projection for CSV/Shopify/domain output."""

    status = get_catalog_status(paths, item_id)
    output: dict[str, Any] = {
        "movie_id": status.movie_id,
        "canonical_title": status.canonical_title,
        "original_title": "",
        "release_year": status.primary_release_year,
        "runtime_minutes": None,
        "directors": [],
        "countries": [],
        "languages": [],
        "genres": [],
        "catalog_match_status": status.status,
        "source_page_url": status.source_url,
        "provenance_status": "UNAVAILABLE" if not status.available else "PENDING",
    }
    if not status.movie_id or not status.available:
        return output
    movie = get_movie(paths.catalog_db_file, status.movie_id)
    if movie is None:
        output["catalog_match_status"] = "MISSING_MOVIE"
        output["provenance_status"] = "INVALID_LINK"
        return output
    source = movie.get("source") or {}
    output.update(
        {
            "canonical_title": str(movie.get("canonical_title") or ""),
            "original_title": str(movie.get("original_title") or ""),
            "release_year": movie.get("primary_release_year"),
            "runtime_minutes": movie.get("runtime_minutes"),
            "directors": list(movie.get("directors") or []),
            "countries": list(movie.get("countries") or []),
            "languages": list(movie.get("languages") or []),
            "genres": list(movie.get("genres") or []),
            "source_page_url": str(source.get("source_url") or ""),
            "provenance_status": "SOURCE_RECORDED" if source else "LOCAL_ONLY",
        }
    )
    return output
