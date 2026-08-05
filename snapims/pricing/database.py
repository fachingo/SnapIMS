"""Immutable SQLite evidence store with a separate current-cache pointer."""

from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from snapims.sqlite_utils import ClosingConnection
from snapims.pricing.models import AnalysisStatus, MovieAnalysis, PriceStatistics, SoldListing
from snapims.pricing.normalization import normalize_title
from snapims.pricing.search_urls import generate_search_url

DEFAULT_DATABASE_PATH = Path("data/pricing_workbench.sqlite3")


def configured_database_path() -> Path:
    configured = os.environ.get("SNAPIMS_PRICING_DATABASE") or os.environ.get(
        "PRICING_WORKBENCH_DATABASE"
    )
    return Path(configured) if configured else DEFAULT_DATABASE_PATH


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def _status(value: str) -> AnalysisStatus:
    legacy = {
        "No matching sold VHS listings found.": AnalysisStatus.NO_VALID_MATCHES,
        "NO_MATCHES": AnalysisStatus.NO_VALID_MATCHES,
        "ZERO_MATCHES": AnalysisStatus.NO_VALID_MATCHES,
    }
    return legacy.get(value, AnalysisStatus(value))


class PricingDatabase:
    """Append-only evidence collections plus replaceable cache-head pointers."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else configured_database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path, timeout=30, check_same_thread=False, factory=ClosingConnection
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA foreign_keys=ON")
        mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).casefold()
        if mode != "wal":
            connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pricing_evidence (
                    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection_id TEXT NOT NULL UNIQUE,
                    title_key TEXT NOT NULL,
                    queried_title TEXT NOT NULL,
                    max_listings INTEGER NOT NULL,
                    search_url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    analysis_date TEXT NOT NULL,
                    collected_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'CAD',
                    average_cad TEXT,
                    median_cad TEXT,
                    lowest_cad TEXT,
                    highest_cad TEXT,
                    tapes_averaged INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_pricing_evidence_title
                    ON pricing_evidence(title_key,max_listings,evidence_id DESC);
                CREATE TABLE IF NOT EXISTS pricing_evidence_listings (
                    listing_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    evidence_id INTEGER NOT NULL REFERENCES pricing_evidence(evidence_id)
                        ON DELETE RESTRICT,
                    ordinal INTEGER NOT NULL,
                    sold_price_cad TEXT NOT NULL,
                    shipping_price_cad TEXT NOT NULL,
                    listing_title TEXT NOT NULL,
                    listing_url TEXT NOT NULL,
                    sold_date TEXT NOT NULL,
                    UNIQUE(evidence_id,ordinal)
                );
                CREATE TABLE IF NOT EXISTS pricing_cache_heads (
                    title_key TEXT NOT NULL,
                    max_listings INTEGER NOT NULL,
                    evidence_id INTEGER NOT NULL REFERENCES pricing_evidence(evidence_id)
                        ON DELETE RESTRICT,
                    expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(title_key,max_listings)
                );
                CREATE TABLE IF NOT EXISTS pricing_legacy_evidence_map (
                    legacy_analysis_id INTEGER PRIMARY KEY,
                    evidence_id INTEGER NOT NULL UNIQUE REFERENCES pricing_evidence(evidence_id)
                        ON DELETE RESTRICT
                );
                """
            )
            self._migrate_legacy(connection)

    def _migrate_legacy(self, connection: sqlite3.Connection) -> None:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='movie_analyses'"
        ).fetchone()
        if not exists:
            return
        columns = {row[1] for row in connection.execute("PRAGMA table_info(movie_analyses)")}
        required = {"id", "title_key", "movie", "status", "analysis_date"}
        if not required.issubset(columns):
            return
        rows = connection.execute(
            "SELECT * FROM movie_analyses ORDER BY id"
        ).fetchall()
        for row in rows:
            mapped = connection.execute(
                "SELECT evidence_id FROM pricing_legacy_evidence_map WHERE legacy_analysis_id=?",
                (row["id"],),
            ).fetchone()
            if mapped:
                continue
            collected = str(row["collected_at"] if "collected_at" in columns else "") or _now()
            expires = str(row["expires_at"] if "expires_at" in columns else "") or collected
            max_listings = int(row["max_listings"] if "max_listings" in columns else 3)
            status = _status(str(row["status"]))
            cursor = connection.execute(
                """INSERT INTO pricing_evidence(
                       collection_id,title_key,queried_title,max_listings,search_url,status,
                       analysis_date,collected_at,expires_at,currency,average_cad,median_cad,
                       lowest_cad,highest_cad,tapes_averaged,created_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    f"legacy-{row['id']}", row["title_key"], row["movie"], max_listings,
                    row["search_url"], status.value, row["analysis_date"], collected, expires,
                    str(row["currency"] if "currency" in columns else "CAD"),
                    row["average_cad"], row["median_cad"], row["lowest_cad"],
                    row["highest_cad"], int(row["tapes_averaged"] or 0), collected,
                ),
            )
            evidence_id = int(cursor.lastrowid)
            listing_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sold_listings'"
            ).fetchone()
            if listing_table:
                listing_rows = connection.execute(
                    "SELECT * FROM sold_listings WHERE analysis_id=? ORDER BY ordinal", (row["id"],)
                ).fetchall()
                connection.executemany(
                    """INSERT INTO pricing_evidence_listings(
                           evidence_id,ordinal,sold_price_cad,shipping_price_cad,
                           listing_title,listing_url,sold_date
                       ) VALUES(?,?,?,?,?,?,?)""",
                    [
                        (
                            evidence_id, listing["ordinal"], listing["sold_price_cad"],
                            listing["shipping_price_cad"], listing["listing_title"],
                            listing["listing_url"], listing["sold_date"],
                        )
                        for listing in listing_rows
                    ],
                )
            connection.execute(
                "INSERT INTO pricing_legacy_evidence_map(legacy_analysis_id,evidence_id) VALUES(?,?)",
                (row["id"], evidence_id),
            )
            connection.execute(
                """INSERT INTO pricing_cache_heads(title_key,max_listings,evidence_id,expires_at,updated_at)
                   VALUES(?,?,?,?,?) ON CONFLICT(title_key,max_listings) DO UPDATE SET
                   evidence_id=excluded.evidence_id,expires_at=excluded.expires_at,
                   updated_at=excluded.updated_at""",
                (row["title_key"], max_listings, evidence_id, expires, collected),
            )

    def _analysis_from_row(
        self, connection: sqlite3.Connection, row: sqlite3.Row, *, from_cache: bool
    ) -> MovieAnalysis:
        listing_rows = connection.execute(
            "SELECT * FROM pricing_evidence_listings WHERE evidence_id=? ORDER BY ordinal",
            (row["evidence_id"],),
        ).fetchall()
        listings = [
            SoldListing(
                sold_price=Decimal(item["sold_price_cad"]),
                shipping_price=Decimal(item["shipping_price_cad"]),
                listing_title=str(item["listing_title"]),
                listing_url=str(item["listing_url"]),
                sold_date=str(item["sold_date"]),
            )
            for item in listing_rows
        ]
        statistics = None
        if int(row["tapes_averaged"] or 0):
            statistics = PriceStatistics(
                average=Decimal(row["average_cad"]), median=Decimal(row["median_cad"]),
                lowest=Decimal(row["lowest_cad"]), highest=Decimal(row["highest_cad"]),
                count=int(row["tapes_averaged"]),
            )
        return MovieAnalysis(
            movie=str(row["queried_title"]), search_url=str(row["search_url"]),
            status=_status(str(row["status"])), statistics=statistics, listings=listings,
            analysis_date=date.fromisoformat(str(row["analysis_date"])), from_cache=from_cache,
            evidence_id=int(row["evidence_id"]), collection_id=str(row["collection_id"]),
            queried_title=str(row["queried_title"]), title_key=str(row["title_key"]),
            collected_at=str(row["collected_at"]),
        )

    def get_analysis(
        self, movie_title: str, *, max_listings: int = 3, include_expired: bool = False
    ) -> MovieAnalysis | None:
        key = normalize_title(movie_title)
        if not key:
            return None
        with self._connect() as connection:
            row = connection.execute(
                """SELECT e.* FROM pricing_cache_heads h
                   JOIN pricing_evidence e ON e.evidence_id=h.evidence_id
                   WHERE h.title_key=? AND h.max_listings=?""",
                (key, max_listings),
            ).fetchone()
            if row is None:
                return None
            if not include_expired:
                try:
                    if datetime.fromisoformat(str(row["expires_at"])) <= datetime.now().astimezone():
                        return None
                except ValueError:
                    return None
            return self._analysis_from_row(connection, row, from_cache=True)

    def get_evidence(self, evidence_id: int) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM pricing_evidence WHERE evidence_id=?", (evidence_id,)
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["listings"] = [
                dict(item)
                for item in connection.execute(
                    "SELECT * FROM pricing_evidence_listings WHERE evidence_id=? ORDER BY ordinal",
                    (evidence_id,),
                ).fetchall()
            ]
            return result

    def latest_analysis(self, movie_title: str) -> dict[str, object] | None:
        key = normalize_title(movie_title)
        if not key:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM pricing_evidence WHERE title_key=? ORDER BY evidence_id DESC LIMIT 1",
                (key,),
            ).fetchone()
        return dict(row) if row else None

    def evidence_history(self, movie_title: str) -> list[dict[str, object]]:
        key = normalize_title(movie_title)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pricing_evidence WHERE title_key=? ORDER BY evidence_id DESC", (key,)
            ).fetchall()
        return [dict(row) for row in rows]

    def legacy_evidence_id(self, legacy_id: int | None) -> int | None:
        if legacy_id is None:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT evidence_id FROM pricing_legacy_evidence_map WHERE legacy_analysis_id=?",
                (legacy_id,),
            ).fetchone()
        return int(row[0]) if row else None

    def save_analysis(
        self, analysis: MovieAnalysis, *, max_listings: int = 3, cache_expiry_days: int = 30
    ) -> int | None:
        if analysis.status not in {AnalysisStatus.COMPLETE, AnalysisStatus.NO_VALID_MATCHES}:
            return None
        title = analysis.queried_title or analysis.movie
        title_key = normalize_title(title)
        if not title_key:
            raise ValueError("Evidence requires a non-empty normalized queried title")
        analysis_day = analysis.analysis_date or date.today()
        statistics = analysis.statistics
        collected = datetime.now().astimezone()
        expires = collected + timedelta(days=cache_expiry_days)
        collection_id = analysis.collection_id or uuid4().hex
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """INSERT INTO pricing_evidence(
                       collection_id,title_key,queried_title,max_listings,search_url,status,
                       analysis_date,collected_at,expires_at,currency,average_cad,median_cad,
                       lowest_cad,highest_cad,tapes_averaged,created_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    collection_id, title_key, title, max_listings,
                    analysis.search_url or generate_search_url(title), analysis.status.value,
                    analysis_day.isoformat(), collected.isoformat(timespec="microseconds"),
                    expires.isoformat(timespec="microseconds"), "CAD",
                    str(statistics.average) if statistics else None,
                    str(statistics.median) if statistics else None,
                    str(statistics.lowest) if statistics else None,
                    str(statistics.highest) if statistics else None,
                    statistics.count if statistics else 0, _now(),
                ),
            )
            evidence_id = int(cursor.lastrowid)
            connection.executemany(
                """INSERT INTO pricing_evidence_listings(
                       evidence_id,ordinal,sold_price_cad,shipping_price_cad,
                       listing_title,listing_url,sold_date
                   ) VALUES(?,?,?,?,?,?,?)""",
                [
                    (
                        evidence_id, ordinal, str(listing.sold_price),
                        str(listing.shipping_price), listing.listing_title,
                        listing.listing_url, listing.sold_date,
                    )
                    for ordinal, listing in enumerate(analysis.listings, start=1)
                ],
            )
            connection.execute(
                """INSERT INTO pricing_cache_heads(title_key,max_listings,evidence_id,expires_at,updated_at)
                   VALUES(?,?,?,?,?) ON CONFLICT(title_key,max_listings) DO UPDATE SET
                   evidence_id=excluded.evidence_id,expires_at=excluded.expires_at,
                   updated_at=excluded.updated_at""",
                (title_key, max_listings, evidence_id, expires.isoformat(timespec="microseconds"), _now()),
            )
            connection.commit()
        analysis.evidence_id = evidence_id
        analysis.collection_id = collection_id
        analysis.queried_title = title
        analysis.title_key = title_key
        analysis.collected_at = collected.isoformat(timespec="microseconds")
        return evidence_id
