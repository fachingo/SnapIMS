"""Transactional selective-pricing workflow for SnapIMS v0.11.0."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from snapims import db as inventory_db
from snapims.config import DataPaths
from snapims.pricing.database import PricingDatabase
from snapims.pricing.models import AnalysisStatus, MovieAnalysis
from snapims.pricing.normalization import normalize_title
from snapims.pricing.search_urls import generate_search_url
from snapims.pricing.settings import AppSettings
from snapims.sqlite_utils import ClosingConnection

BatchMode = Literal["MANUAL_FIXED", "SELECTIVE", "DEFAULT_QUEUE"]
Disposition = Literal["MANUAL", "QUEUE", "SKIP"]
BATCH_MODES = ("MANUAL_FIXED", "SELECTIVE", "DEFAULT_QUEUE")
DISPOSITIONS = ("MANUAL", "QUEUE", "SKIP")
ACTIVE_JOB_STATES = ("PENDING", "RUNNING", "PAUSED")
ATTENTION_STATES = (
    "VERIFICATION_REQUIRED", "ACCESS_BLOCKED", "PARSING_LAYOUT_FAILURE",
    "BROWSER_MISSING", "NETWORK_UNAVAILABLE", "FAILED", "STALE",
)


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def pricing_db_path(paths: DataPaths) -> Path:
    return paths.db_file


def money_to_cents(value: Decimal) -> int:
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True, slots=True)
class PricingBulkResult:
    requested: int
    validated: int
    changed: int
    unchanged: int
    failed: int
    errors: tuple[str, ...]
    checkpoint_id: int
    request_id: str

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["errors"] = list(self.errors)
        return result


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _add_column(connection: sqlite3.Connection, table: str, name: str, definition: str) -> None:
    if name not in _columns(connection, table):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


class PricingWorkflow:
    def __init__(self, paths: DataPaths | None = None) -> None:
        self.paths = (paths or DataPaths.from_root()).ensure()
        self.path = pricing_db_path(self.paths)
        self.cache = PricingDatabase(self.path)
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pricing_schema(
                    version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL,description TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pricing_settings(
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    profile TEXT NOT NULL DEFAULT 'CONSERVATIVE',concurrency INTEGER NOT NULL DEFAULT 1,
                    delay_min INTEGER NOT NULL DEFAULT 15,delay_max INTEGER NOT NULL DEFAULT 30,
                    max_listings INTEGER NOT NULL DEFAULT 3,cache_days INTEGER NOT NULL DEFAULT 30,
                    headless INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pricing_batch_modes(
                    batch_id TEXT PRIMARY KEY REFERENCES batches(batch_id) ON DELETE CASCADE,
                    mode TEXT NOT NULL CHECK(mode IN ('MANUAL_FIXED','SELECTIVE','DEFAULT_QUEUE')),
                    updated_at TEXT NOT NULL,updated_by TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pricing_item_states(
                    item_id TEXT PRIMARY KEY REFERENCES items(item_id) ON DELETE CASCADE,
                    batch_id TEXT NOT NULL REFERENCES batches(batch_id) ON DELETE CASCADE,
                    approved_title TEXT NOT NULL DEFAULT '',title_key TEXT NOT NULL DEFAULT '',
                    item_revision INTEGER NOT NULL DEFAULT 0,request_max_listings INTEGER NOT NULL DEFAULT 3,
                    disposition TEXT NOT NULL DEFAULT 'SKIP',status TEXT NOT NULL DEFAULT 'NOT_REQUESTED',
                    pricing_source TEXT NOT NULL DEFAULT '',evidence_version_id INTEGER
                        REFERENCES pricing_evidence(evidence_id) ON DELETE RESTRICT,
                    current_price_cents INTEGER,error_code TEXT NOT NULL DEFAULT '',
                    error_message TEXT NOT NULL DEFAULT '',queued_at TEXT,updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_pricing_item_states_batch
                    ON pricing_item_states(batch_id,status,item_id);
                CREATE TABLE IF NOT EXISTS pricing_jobs(
                    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
                    batch_id TEXT NOT NULL REFERENCES batches(batch_id) ON DELETE CASCADE,
                    approved_title TEXT NOT NULL,title_key TEXT NOT NULL,max_listings INTEGER NOT NULL DEFAULT 3,
                    status TEXT NOT NULL,refresh INTEGER NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,started_at TEXT,finished_at TEXT,updated_at TEXT NOT NULL,
                    error_code TEXT NOT NULL DEFAULT '',error_message TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_pricing_jobs_status ON pricing_jobs(status,job_id);
                CREATE INDEX IF NOT EXISTS idx_pricing_jobs_item ON pricing_jobs(item_id,job_id DESC);
                CREATE TABLE IF NOT EXISTS pricing_decisions(
                    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
                    batch_id TEXT NOT NULL REFERENCES batches(batch_id) ON DELETE CASCADE,
                    approved_title TEXT NOT NULL,decision TEXT NOT NULL,
                    evidence_version_id INTEGER REFERENCES pricing_evidence(evidence_id) ON DELETE RESTRICT,
                    previous_price_cents INTEGER,new_price_cents INTEGER,actor TEXT NOT NULL,
                    item_revision INTEGER NOT NULL DEFAULT 0,decided_at TEXT NOT NULL,
                    detail_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_pricing_decisions_item
                    ON pricing_decisions(item_id,decision_id DESC);
                CREATE TABLE IF NOT EXISTS pricing_decision_requests(
                    request_id TEXT PRIMARY KEY,item_id TEXT NOT NULL,status TEXT NOT NULL,
                    result_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS pricing_events(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,occurred_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,status TEXT NOT NULL,actor TEXT NOT NULL DEFAULT 'system',
                    item_id TEXT NOT NULL DEFAULT '',batch_id TEXT NOT NULL DEFAULT '',
                    detail_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS pricing_runtime_probes(
                    probe_id INTEGER PRIMARY KEY AUTOINCREMENT,probed_at TEXT NOT NULL,
                    browser_status TEXT NOT NULL,ebay_status TEXT NOT NULL,message TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS pricing_request_throttle(
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    last_request_epoch REAL,last_request_at TEXT NOT NULL DEFAULT '',
                    updated_by TEXT NOT NULL DEFAULT ''
                );
                INSERT OR IGNORE INTO pricing_request_throttle(singleton) VALUES(1);
                CREATE TABLE IF NOT EXISTS pricing_request_log(
                    request_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_epoch REAL NOT NULL,request_at TEXT NOT NULL,
                    title_key TEXT NOT NULL,job_id INTEGER,
                    outcome TEXT NOT NULL DEFAULT 'STARTED'
                );
                CREATE TABLE IF NOT EXISTS operation_requests(
                    request_id TEXT PRIMARY KEY,operation_type TEXT NOT NULL,batch_id TEXT NOT NULL,
                    status TEXT NOT NULL,result_json TEXT NOT NULL DEFAULT '{}',error_message TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,updated_at TEXT NOT NULL,completed_at TEXT
                );
                """
            )
            # Safe upgrades from the rejected schema-1 candidate.
            for name, definition in {
                "item_revision": "INTEGER NOT NULL DEFAULT 0",
                "request_max_listings": "INTEGER NOT NULL DEFAULT 3",
                "evidence_version_id": "INTEGER REFERENCES pricing_evidence(evidence_id) ON DELETE RESTRICT",
            }.items():
                _add_column(connection, "pricing_item_states", name, definition)
            _add_column(connection, "pricing_jobs", "max_listings", "INTEGER NOT NULL DEFAULT 3")
            _add_column(
                connection, "pricing_decisions", "evidence_version_id",
                "INTEGER REFERENCES pricing_evidence(evidence_id) ON DELETE RESTRICT",
            )
            _add_column(connection, "pricing_decisions", "item_revision", "INTEGER NOT NULL DEFAULT 0")
            _add_column(connection, "pricing_events", "actor", "TEXT NOT NULL DEFAULT 'system'")
            connection.execute("DROP INDEX IF EXISTS idx_pricing_jobs_one_active")
            duplicate_groups = connection.execute(
                """SELECT title_key,max_listings,MIN(job_id) keep_id
                   FROM pricing_jobs WHERE status IN ('PENDING','RUNNING','PAUSED')
                   GROUP BY title_key,max_listings HAVING COUNT(*)>1"""
            ).fetchall()
            for duplicate in duplicate_groups:
                connection.execute(
                    """UPDATE pricing_jobs SET status='CANCELLED',finished_at=?,updated_at=?,
                       error_code='DEDUPED',error_message='Merged into shared normalized-title job.'
                       WHERE title_key=? AND max_listings=? AND job_id<>?
                       AND status IN ('PENDING','RUNNING','PAUSED')""",
                    (
                        now(), now(), duplicate["title_key"], duplicate["max_listings"],
                        duplicate["keep_id"],
                    ),
                )
            connection.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_pricing_jobs_one_active_title
                   ON pricing_jobs(title_key,max_listings)
                   WHERE status IN ('PENDING','RUNNING','PAUSED')"""
            )
            connection.execute(
                """INSERT OR IGNORE INTO pricing_settings(
                       singleton,profile,concurrency,delay_min,delay_max,max_listings,
                       cache_days,headless,updated_at
                   ) VALUES(1,'CONSERVATIVE',1,15,30,3,30,1,?)""",
                (now(),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO pricing_schema VALUES(2,?,?)",
                (now(), "Immutable evidence, durable throttle, safe queue and bulk remediation"),
            )
            self._migrate_legacy_references(connection)
            self._backfill_existing_items(connection)
            self._reconcile_interrupted(connection)

    def _migrate_legacy_references(self, connection: sqlite3.Connection) -> None:
        if "evidence_id" not in _columns(connection, "pricing_item_states"):
            return
        rows = connection.execute(
            "SELECT item_id,evidence_id FROM pricing_item_states WHERE evidence_id IS NOT NULL "
            "AND evidence_version_id IS NULL"
        ).fetchall()
        for row in rows:
            mapped = connection.execute(
                "SELECT evidence_id FROM pricing_legacy_evidence_map WHERE legacy_analysis_id=?",
                (row["evidence_id"],),
            ).fetchone()
            if mapped:
                connection.execute(
                    "UPDATE pricing_item_states SET evidence_version_id=? WHERE item_id=?",
                    (mapped[0], row["item_id"]),
                )
        if "evidence_id" in _columns(connection, "pricing_decisions"):
            decisions = connection.execute(
                "SELECT decision_id,evidence_id FROM pricing_decisions WHERE evidence_id IS NOT NULL "
                "AND evidence_version_id IS NULL"
            ).fetchall()
            for row in decisions:
                mapped = connection.execute(
                    "SELECT evidence_id FROM pricing_legacy_evidence_map WHERE legacy_analysis_id=?",
                    (row["evidence_id"],),
                ).fetchone()
                if mapped:
                    connection.execute(
                        "UPDATE pricing_decisions SET evidence_version_id=? WHERE decision_id=?",
                        (mapped[0], row["decision_id"]),
                    )

    def _backfill_existing_items(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT item_id,batch_id,title,price_cents,record_revision FROM items "
            "WHERE review_status='DONE' AND TRIM(COALESCE(title,''))!=''"
        ).fetchall()
        timestamp = now()
        for row in rows:
            title = str(row["title"]).strip()
            key = normalize_title(title)
            if not key:
                continue
            connection.execute(
                """INSERT OR IGNORE INTO pricing_item_states(
                       item_id,batch_id,approved_title,title_key,item_revision,request_max_listings,
                       disposition,status,pricing_source,current_price_cents,updated_at
                   ) VALUES(?,?,?,?,?,3,'SKIP','NOT_REQUESTED','',?,?)""",
                (
                    row["item_id"], row["batch_id"], title, key,
                    int(row["record_revision"]), row["price_cents"], timestamp,
                ),
            )

    def _reconcile_interrupted(self, connection: sqlite3.Connection) -> None:
        timestamp = now()
        running = connection.execute(
            "SELECT job_id,title_key,max_listings FROM pricing_jobs WHERE status='RUNNING'"
        ).fetchall()
        for job in running:
            connection.execute(
                """UPDATE pricing_jobs SET status='PAUSED',updated_at=?,error_code='INTERRUPTED',
                   error_message='Application stopped during collection; resume explicitly.'
                   WHERE job_id=?""",
                (timestamp, job["job_id"]),
            )
            connection.execute(
                """UPDATE pricing_item_states SET status='PAUSED',updated_at=?,
                   error_code='INTERRUPTED',error_message='Application stopped during collection; resume explicitly.'
                   WHERE title_key=? AND request_max_listings=? AND status='RUNNING'""",
                (timestamp, job["title_key"], job["max_listings"]),
            )

    def _event(
        self, event_type: str, status: str, *, actor: str = "system",
        item_id: str = "", batch_id: str = "", detail: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO pricing_events(
                       occurred_at,event_type,status,actor,item_id,batch_id,detail_json
                   ) VALUES(?,?,?,?,?,?,?)""",
                (now(), event_type, status, actor, item_id, batch_id, json.dumps(detail or {}, sort_keys=True)),
            )

    def settings(self) -> AppSettings:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM pricing_settings WHERE singleton=1").fetchone()
        assert row is not None
        try:
            return AppSettings(
                max_simultaneous_tabs=int(row["concurrency"]), delay_min_seconds=int(row["delay_min"]),
                delay_max_seconds=int(row["delay_max"]), max_sold_listings=int(row["max_listings"]),
                cache_expiry_days=int(row["cache_days"]), headless=bool(row["headless"]),
                profile=str(row["profile"]),
            )
        except ValueError:
            # Repair impossible legacy profile/value combinations truthfully.
            return AppSettings.for_profile(
                "CONSERVATIVE", max_sold_listings=int(row["max_listings"]),
                cache_expiry_days=int(row["cache_days"]), headless=bool(row["headless"]),
            )

    def save_settings(
        self, *, profile: str, concurrency: int, delay_min: int, delay_max: int,
        max_listings: int, cache_days: int, headless: bool, actor: str = "local-operator",
    ) -> AppSettings:
        profile = profile.strip().upper()
        candidate = (
            AppSettings.for_profile(
                profile, max_sold_listings=max_listings,
                cache_expiry_days=cache_days, headless=headless,
            )
            if profile != "CUSTOM"
            else AppSettings(
                max_simultaneous_tabs=concurrency, delay_min_seconds=delay_min,
                delay_max_seconds=delay_max, max_sold_listings=max_listings,
                cache_expiry_days=cache_days, headless=headless, profile="CUSTOM",
            )
        )
        with self._connect() as connection:
            connection.execute(
                """UPDATE pricing_settings SET profile=?,concurrency=?,delay_min=?,delay_max=?,
                   max_listings=?,cache_days=?,headless=?,updated_at=? WHERE singleton=1""",
                (
                    candidate.profile, candidate.max_simultaneous_tabs,
                    candidate.delay_min_seconds, candidate.delay_max_seconds,
                    candidate.max_sold_listings, candidate.cache_expiry_days,
                    int(candidate.headless), now(),
                ),
            )
        self._event("pricing.settings_updated", "COMPLETE", actor=actor, detail=asdict(candidate))
        return candidate

    def get_batch_mode(self, batch_id: str) -> str:
        if not batch_id:
            return "SELECTIVE"
        with self._connect() as connection:
            row = connection.execute(
                "SELECT mode FROM pricing_batch_modes WHERE batch_id=?", (batch_id,)
            ).fetchone()
        return str(row[0]) if row else "SELECTIVE"

    def set_batch_mode(self, batch_id: str, mode: str, actor: str = "local-operator") -> None:
        if mode not in BATCH_MODES:
            raise ValueError("Unknown pricing mode")
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM batches WHERE batch_id=?", (batch_id,)).fetchone() is None:
                raise ValueError("The selected Batch no longer exists")
            connection.execute(
                """INSERT INTO pricing_batch_modes(batch_id,mode,updated_at,updated_by)
                   VALUES(?,?,?,?) ON CONFLICT(batch_id) DO UPDATE SET
                   mode=excluded.mode,updated_at=excluded.updated_at,updated_by=excluded.updated_by""",
                (batch_id, mode, now(), actor),
            )
        self._event("pricing.batch_mode_changed", "COMPLETE", actor=actor, batch_id=batch_id, detail={"mode": mode})

    def default_disposition(self, batch_id: str) -> str:
        mode = self.get_batch_mode(batch_id)
        return "QUEUE" if mode == "DEFAULT_QUEUE" else "MANUAL" if mode == "MANUAL_FIXED" else "SKIP"

    def item_state(self, item_id: str, batch_id: str = "") -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM pricing_item_states WHERE item_id=?", (item_id,)).fetchone()
        if row:
            result = dict(row)
        else:
            result = {
                "item_id": item_id, "batch_id": batch_id, "approved_title": "", "title_key": "",
                "item_revision": 0, "request_max_listings": 3,
                "disposition": self.default_disposition(batch_id), "status": "NOT_REQUESTED",
                "pricing_source": "", "evidence_version_id": None,
                "current_price_cents": None, "error_code": "", "error_message": "",
                "queued_at": None, "updated_at": "",
            }
        result["evidence_id"] = result.get("evidence_version_id")
        title = str(result.get("approved_title") or "")
        result["search_url"] = generate_search_url(title) if title else ""
        return result

    @staticmethod
    def _cancel_orphaned_title_job(
        connection: sqlite3.Connection, title_key: str, max_listings: int, timestamp: str
    ) -> None:
        waiters = connection.execute(
            """SELECT 1 FROM pricing_item_states WHERE title_key=? AND request_max_listings=?
               AND status IN ('PENDING','RUNNING','PAUSED') LIMIT 1""",
            (title_key, max_listings),
        ).fetchone()
        if waiters is None:
            connection.execute(
                """UPDATE pricing_jobs SET status='CANCELLED',finished_at=?,updated_at=?,
                   error_code='NO_WAITERS',error_message='No Item remains queued for this title.'
                   WHERE title_key=? AND max_listings=? AND status IN ('PENDING','RUNNING','PAUSED')""",
                (timestamp, timestamp, title_key, max_listings),
            )

    def record_review_approval(
        self, *, item_id: str, batch_id: str, approved_title: str,
        submitted_price_cents: int | None, price_touched: bool,
        requested_disposition: str, actor: str = "local-operator",
        previous_price_cents: int | None | object = ..., item_revision: int | None = None,
        explicit_recollection: bool = False,
    ) -> dict[str, Any]:
        title = approved_title.strip()
        title_key = normalize_title(title)
        if not title or not title_key:
            raise ValueError("Approved title must contain a real movie title before pricing")
        if requested_disposition not in DISPOSITIONS:
            requested_disposition = self.default_disposition(batch_id)
        settings = self.settings()
        timestamp = now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            item = connection.execute("SELECT * FROM items WHERE item_id=?", (item_id,)).fetchone()
            if item is None:
                raise KeyError("Unknown Item ID")
            if str(item["batch_id"]) != batch_id:
                raise ValueError("Item does not belong to the submitted Batch")
            if normalize_title(str(item["title"] or "")) != title_key:
                raise ValueError("Submitted approved title does not match the saved Item title")
            if item_revision is not None and int(item["record_revision"]) != int(item_revision):
                raise RuntimeError("This Item changed in another session. Reload before saving pricing.")
            authoritative_previous = item["price_cents"] if previous_price_cents is ... else previous_price_cents
            manual_changed = authoritative_previous != submitted_price_cents
            manual_protected = submitted_price_cents is not None and not explicit_recollection
            disposition = (
                "MANUAL"
                if price_touched or manual_changed or (requested_disposition == "QUEUE" and manual_protected)
                else requested_disposition
            )
            prior = connection.execute(
                "SELECT * FROM pricing_item_states WHERE item_id=?", (item_id,)
            ).fetchone()
            prior_key = str(prior["title_key"] or "") if prior else ""
            prior_max = int(prior["request_max_listings"] or settings.max_sold_listings) if prior else settings.max_sold_listings
            if prior_key and prior_key != title_key:
                self._invalidate_in_connection(
                    connection, item_id, str(item["title"]), actor=actor,
                    source="REVIEW_APPROVAL", previous_title_key=prior_key,
                )
            if disposition == "MANUAL":
                status = "MANUAL_PRICE" if submitted_price_cents is not None else "NOT_REQUESTED"
                source = "MANUAL" if submitted_price_cents is not None else ""
            elif disposition == "SKIP":
                status, source = "SKIPPED", "SKIPPED"
            else:
                status, source = "PENDING", ""
            connection.execute(
                """INSERT INTO pricing_item_states(
                       item_id,batch_id,approved_title,title_key,item_revision,request_max_listings,
                       disposition,status,pricing_source,evidence_version_id,current_price_cents,
                       error_code,error_message,queued_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,NULL,?,'','',?,?)
                   ON CONFLICT(item_id) DO UPDATE SET batch_id=excluded.batch_id,
                   approved_title=excluded.approved_title,title_key=excluded.title_key,
                   item_revision=excluded.item_revision,request_max_listings=excluded.request_max_listings,
                   disposition=excluded.disposition,status=excluded.status,
                   pricing_source=excluded.pricing_source,
                   evidence_version_id=CASE WHEN pricing_item_states.title_key=excluded.title_key
                       THEN pricing_item_states.evidence_version_id ELSE NULL END,
                   current_price_cents=excluded.current_price_cents,error_code='',error_message='',
                   queued_at=excluded.queued_at,updated_at=excluded.updated_at""",
                (
                    item_id, batch_id, title, title_key, int(item["record_revision"]),
                    settings.max_sold_listings, disposition, status, source,
                    submitted_price_cents, timestamp if disposition == "QUEUE" else None, timestamp,
                ),
            )
            if disposition != "QUEUE":
                self._cancel_orphaned_title_job(connection, prior_key or title_key, prior_max, timestamp)
            else:
                cached = self.cache.get_analysis(title, max_listings=settings.max_sold_listings)
                if cached:
                    cached_status = (
                        "EVIDENCE_READY" if cached.status == AnalysisStatus.COMPLETE
                        else "NO_VALID_MATCHES"
                    )
                    connection.execute(
                        """UPDATE pricing_item_states SET status=?,pricing_source='CACHE',
                           evidence_version_id=?,updated_at=? WHERE item_id=?""",
                        (cached_status, cached.evidence_id, timestamp, item_id),
                    )
                else:
                    active = connection.execute(
                        """SELECT job_id FROM pricing_jobs WHERE title_key=? AND max_listings=?
                           AND status IN ('PENDING','RUNNING','PAUSED') LIMIT 1""",
                        (title_key, settings.max_sold_listings),
                    ).fetchone()
                    if active is None:
                        connection.execute(
                            """INSERT INTO pricing_jobs(
                               item_id,batch_id,approved_title,title_key,max_listings,status,refresh,
                               attempts,created_at,updated_at
                               ) VALUES(?,?,?,?,?,'PENDING',0,0,?,?)""",
                            (item_id, batch_id, title, title_key, settings.max_sold_listings, timestamp, timestamp),
                        )
            connection.commit()
        final = self.item_state(item_id, batch_id)
        self._event(
            "pricing.review_disposition", str(final["status"]), actor=actor,
            item_id=item_id, batch_id=batch_id,
            detail={"disposition": disposition, "manual_changed": manual_changed, "title": title},
        )
        return final

    def _invalidate_in_connection(
        self, connection: sqlite3.Connection, item_id: str, new_title: str, *,
        actor: str, source: str, previous_title_key: str | None = None,
    ) -> bool:
        state = connection.execute(
            "SELECT * FROM pricing_item_states WHERE item_id=?", (item_id,)
        ).fetchone()
        if state is None:
            return False
        old_key = previous_title_key or str(state["title_key"] or "")
        new_key = normalize_title(new_title)
        if old_key == new_key:
            return False
        timestamp = now()
        connection.execute(
            """UPDATE pricing_item_states SET status='STALE',error_code='TITLE_CHANGED',
               error_message='Saved title changed; attached evidence is historical and cannot be accepted.',
               item_revision=(SELECT record_revision FROM items WHERE item_id=?),updated_at=?
               WHERE item_id=?""",
            (item_id, timestamp, item_id),
        )
        self._cancel_orphaned_title_job(
            connection, old_key, int(state["request_max_listings"] or 3), timestamp
        )
        connection.execute(
            """INSERT INTO pricing_events(
               occurred_at,event_type,status,actor,item_id,batch_id,detail_json
               ) VALUES(?, 'pricing.title_invalidated','STALE',?,?,?,?)""",
            (
                timestamp, actor, item_id, state["batch_id"],
                json.dumps({"old_title_key": old_key, "new_title_key": new_key, "source": source}, sort_keys=True),
            ),
        )
        return True

    def invalidate_title_change(
        self, item_id: str, new_title: str, *, actor: str = "local-operator", source: str = "ITEM_UPDATE"
    ) -> bool:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = self._invalidate_in_connection(
                connection, item_id, new_title, actor=actor, source=source
            )
            connection.commit()
        return changed

    def protect_manual_price(
        self, item_id: str, new_price_cents: int | None, *,
        actor: str = "local-operator", source: str = "ITEM_UPDATE",
    ) -> bool:
        if source.startswith("PRICING_"):
            return False
        timestamp = now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            item = connection.execute("SELECT * FROM items WHERE item_id=?", (item_id,)).fetchone()
            if item is None:
                raise KeyError("Unknown Item ID")
            state = connection.execute(
                "SELECT * FROM pricing_item_states WHERE item_id=?", (item_id,)
            ).fetchone()
            title = str(item["title"] or "").strip()
            title_key = normalize_title(title)
            if not title_key:
                connection.commit()
                return False
            settings = self.settings()
            connection.execute(
                """INSERT INTO pricing_item_states(
                   item_id,batch_id,approved_title,title_key,item_revision,request_max_listings,
                   disposition,status,pricing_source,current_price_cents,updated_at
                   ) VALUES(?,?,?,?,?,?,'MANUAL',?,'MANUAL',?,?)
                   ON CONFLICT(item_id) DO UPDATE SET item_revision=excluded.item_revision,
                   disposition='MANUAL',status=excluded.status,pricing_source=excluded.pricing_source,
                   current_price_cents=excluded.current_price_cents,updated_at=excluded.updated_at""",
                (
                    item_id, item["batch_id"], title, title_key, int(item["record_revision"]),
                    settings.max_sold_listings,
                    "MANUAL_PRICE" if new_price_cents is not None else "NOT_REQUESTED",
                    new_price_cents, timestamp,
                ),
            )
            max_listings = int(state["request_max_listings"] or 3) if state else settings.max_sold_listings
            self._cancel_orphaned_title_job(connection, title_key, max_listings, timestamp)
            connection.execute(
                """INSERT INTO pricing_events(
                   occurred_at,event_type,status,actor,item_id,batch_id,detail_json
                   ) VALUES(?,'pricing.manual_price_protected',?,?,?,?,?)""",
                (
                    timestamp, "MANUAL_PRICE" if new_price_cents is not None else "NOT_REQUESTED",
                    actor, item_id, item["batch_id"], json.dumps({"source": source}),
                ),
            )
            connection.commit()
        return True

    def queue_item(self, item_id: str, *, refresh: bool = False, actor: str = "local-operator") -> dict[str, Any]:
        item = inventory_db.get_item(self.paths.db_file, item_id)
        if item is None:
            raise KeyError("Unknown Item ID")
        if str(item.get("review_status")) != "DONE" or not normalize_title(str(item.get("title") or "")):
            raise ValueError("Pricing requires an approved saved title")
        state = self.record_review_approval(
            item_id=item_id, batch_id=str(item["batch_id"]), approved_title=str(item["title"]),
            submitted_price_cents=item.get("price_cents"), price_touched=False,
            requested_disposition="QUEUE", actor=actor,
            previous_price_cents=item.get("price_cents"), item_revision=int(item["record_revision"]),
            explicit_recollection=True,
        )
        if refresh:
            timestamp = now()
            settings = self.settings()
            title_key = normalize_title(str(item["title"]))
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """UPDATE pricing_jobs SET status='CANCELLED',finished_at=?,updated_at=?,
                       error_code='REFRESH_SUPERSEDED',error_message='Superseded by explicit recollection.'
                       WHERE title_key=? AND max_listings=? AND status IN ('PENDING','PAUSED')""",
                    (timestamp, timestamp, title_key, settings.max_sold_listings),
                )
                running = connection.execute(
                    """SELECT 1 FROM pricing_jobs WHERE title_key=? AND max_listings=?
                       AND status='RUNNING' LIMIT 1""",
                    (title_key, settings.max_sold_listings),
                ).fetchone()
                if running:
                    raise ValueError("This title is currently being collected. Pause before refreshing.")
                connection.execute(
                    """INSERT INTO pricing_jobs(
                       item_id,batch_id,approved_title,title_key,max_listings,status,refresh,
                       attempts,created_at,updated_at
                       ) VALUES(?,?,?,?,?,'PENDING',1,0,?,?)""",
                    (
                        item_id, item["batch_id"], item["title"], title_key,
                        settings.max_sold_listings, timestamp, timestamp,
                    ),
                )
                connection.execute(
                    """UPDATE pricing_item_states SET status='PENDING',pricing_source='',
                       evidence_version_id=NULL,queued_at=?,updated_at=?
                       WHERE title_key=? AND request_max_listings=? AND disposition='QUEUE'""",
                    (timestamp, timestamp, title_key, settings.max_sold_listings),
                )
                connection.commit()
            state = self.item_state(item_id, str(item["batch_id"]))
        return state

    def job(self, job_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM pricing_jobs WHERE job_id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def claim_pending_jobs(self, limit: int) -> list[dict[str, Any]]:
        timestamp = now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT * FROM pricing_jobs WHERE status='PENDING' ORDER BY job_id LIMIT ?",
                (max(1, limit),),
            ).fetchall()
            for row in rows:
                connection.execute(
                    """UPDATE pricing_jobs SET status='RUNNING',attempts=attempts+1,
                       started_at=?,finished_at=NULL,updated_at=?,error_code='',error_message=''
                       WHERE job_id=? AND status='PENDING'""",
                    (timestamp, timestamp, row["job_id"]),
                )
                connection.execute(
                    """UPDATE pricing_item_states SET status='RUNNING',updated_at=?
                       WHERE title_key=? AND request_max_listings=? AND status='PENDING'""",
                    (timestamp, row["title_key"], row["max_listings"]),
                )
            connection.commit()
        return [{**dict(row), "status": "RUNNING"} for row in rows]

    def next_pending_job(self) -> dict[str, Any] | None:
        rows = self.claim_pending_jobs(1)
        return rows[0] if rows else None

    def complete_job(self, job_id: int, analysis: MovieAnalysis) -> None:
        timestamp = now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = connection.execute("SELECT * FROM pricing_jobs WHERE job_id=?", (job_id,)).fetchone()
            if job is None or str(job["status"]) not in {"RUNNING", "PENDING"}:
                connection.commit()
                return
            if analysis.title_key != str(job["title_key"]):
                raise ValueError("Collected evidence title does not match the queued title")
            status = (
                "COMPLETED" if analysis.status == AnalysisStatus.COMPLETE else "NO_VALID_MATCHES"
            )
            connection.execute(
                """UPDATE pricing_jobs SET status=?,finished_at=?,updated_at=?,error_code='',error_message=''
                   WHERE job_id=?""",
                (status, timestamp, timestamp, job_id),
            )
            waiters = connection.execute(
                """SELECT p.item_id,p.title_key,i.title,i.record_revision FROM pricing_item_states p
                   JOIN items i ON i.item_id=p.item_id
                   WHERE p.title_key=? AND p.request_max_listings=?
                   AND p.status IN ('RUNNING','PENDING')""",
                (job["title_key"], job["max_listings"]),
            ).fetchall()
            for waiter in waiters:
                if normalize_title(str(waiter["title"] or "")) != str(job["title_key"]):
                    connection.execute(
                        """UPDATE pricing_item_states SET status='STALE',error_code='TITLE_CHANGED',
                           error_message='Saved title changed while evidence was collected.',updated_at=?
                           WHERE item_id=?""",
                        (timestamp, waiter["item_id"]),
                    )
                else:
                    connection.execute(
                        """UPDATE pricing_item_states SET status=?,pricing_source=?,
                           evidence_version_id=?,item_revision=?,error_code='',error_message='',updated_at=?
                           WHERE item_id=?""",
                        (
                            "EVIDENCE_READY" if status == "COMPLETED" else "NO_VALID_MATCHES",
                            "CACHE" if analysis.from_cache else "EBAY_SOLD",
                            analysis.evidence_id, int(waiter["record_revision"]), timestamp, waiter["item_id"],
                        ),
                    )
            connection.commit()
        self._event(
            "pricing.job_completed", status, item_id=str(job["item_id"]),
            batch_id=str(job["batch_id"]),
            detail={"evidence_id": analysis.evidence_id, "count": analysis.statistics.count if analysis.statistics else 0},
        )

    def pause_job(self, job_id: int, message: str = "Paused by operator.") -> None:
        timestamp = now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = connection.execute("SELECT * FROM pricing_jobs WHERE job_id=?", (job_id,)).fetchone()
            if job and str(job["status"]) in {"RUNNING", "PENDING"}:
                connection.execute(
                    "UPDATE pricing_jobs SET status='PAUSED',updated_at=?,error_code='PAUSED',error_message=? WHERE job_id=?",
                    (timestamp, message[:500], job_id),
                )
                connection.execute(
                    """UPDATE pricing_item_states SET status='PAUSED',updated_at=?,error_code='PAUSED',
                       error_message=? WHERE title_key=? AND request_max_listings=?
                       AND status IN ('RUNNING','PENDING')""",
                    (timestamp, message[:500], job["title_key"], job["max_listings"]),
                )
            connection.commit()

    def fail_job(self, job_id: int, status: str, message: str) -> None:
        timestamp = now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = connection.execute("SELECT * FROM pricing_jobs WHERE job_id=?", (job_id,)).fetchone()
            if job is None:
                connection.commit()
                return
            connection.execute(
                """UPDATE pricing_jobs SET status=?,finished_at=?,updated_at=?,error_code=?,error_message=?
                   WHERE job_id=?""",
                (status, timestamp, timestamp, status, message[:500], job_id),
            )
            connection.execute(
                """UPDATE pricing_item_states SET status=?,error_code=?,error_message=?,updated_at=?
                   WHERE title_key=? AND request_max_listings=? AND status IN ('RUNNING','PENDING')""",
                (status, status, message[:500], timestamp, job["title_key"], job["max_listings"]),
            )
            if status in {"VERIFICATION_REQUIRED", "ACCESS_BLOCKED", "BROWSER_MISSING"}:
                self._pause_all_in_connection(
                    connection, timestamp,
                    f"Queue paused after {status.replace('_', ' ').lower()}.",
                )
            connection.commit()
        self._event(
            "pricing.job_failed", status, item_id=str(job["item_id"]),
            batch_id=str(job["batch_id"]), detail={"message": message[:300]},
        )

    @staticmethod
    def _pause_all_in_connection(connection: sqlite3.Connection, timestamp: str, message: str) -> int:
        cursor = connection.execute(
            """UPDATE pricing_jobs SET status='PAUSED',updated_at=?,error_code='PAUSED',error_message=?
               WHERE status IN ('PENDING','RUNNING')""",
            (timestamp, message[:500]),
        )
        connection.execute(
            """UPDATE pricing_item_states SET status='PAUSED',updated_at=?,error_code='PAUSED',error_message=?
               WHERE status IN ('PENDING','RUNNING')""",
            (timestamp, message[:500]),
        )
        return int(cursor.rowcount)

    def pause_pending(self) -> int:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            count = self._pause_all_in_connection(connection, now(), "Paused by operator.")
            connection.commit()
        return count

    def resume_paused(self) -> int:
        timestamp = now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE pricing_jobs SET status='PENDING',updated_at=?,error_code='',error_message='' WHERE status='PAUSED'",
                (timestamp,),
            )
            connection.execute(
                "UPDATE pricing_item_states SET status='PENDING',updated_at=?,error_code='',error_message='' WHERE status='PAUSED'",
                (timestamp,),
            )
            connection.commit()
        return int(cursor.rowcount)

    def cancel_pending(self) -> int:
        timestamp = now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """UPDATE pricing_jobs SET status='CANCELLED',finished_at=?,updated_at=?,
                   error_code='CANCELLED',error_message='Cancelled by operator.'
                   WHERE status IN ('PENDING','RUNNING','PAUSED')""",
                (timestamp, timestamp),
            )
            connection.execute(
                """UPDATE pricing_item_states SET status='CANCELLED',updated_at=?,
                   error_code='CANCELLED',error_message='Cancelled by operator.'
                   WHERE status IN ('PENDING','RUNNING','PAUSED')""",
                (timestamp,),
            )
            connection.commit()
        return int(cursor.rowcount)

    def queue_summary(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status,COUNT(*) count FROM pricing_item_states GROUP BY status"
            ).fetchall()
        result = {str(row["status"]): int(row["count"]) for row in rows}
        for key in (
            "NOT_REQUESTED", "PENDING", "RUNNING", "PAUSED", "EVIDENCE_READY",
            "NO_VALID_MATCHES", "PRICE_ACCEPTED", "MANUAL_PRICE", "SKIPPED",
            "VERIFICATION_REQUIRED", "ACCESS_BLOCKED", "PARSING_LAYOUT_FAILURE",
            "BROWSER_MISSING", "NETWORK_UNAVAILABLE", "FAILED", "CANCELLED", "STALE",
        ):
            result.setdefault(key, 0)
        return result

    @staticmethod
    def _cache_age(collected_at: str | None) -> str:
        if not collected_at:
            return ""
        try:
            seconds = max(0, int((datetime.now().astimezone() - datetime.fromisoformat(collected_at)).total_seconds()))
        except ValueError:
            return "Unknown age"
        if seconds < 3600:
            return f"{max(1, seconds // 60)} min old"
        if seconds < 86400:
            return f"{seconds // 3600} hr old"
        return f"{seconds // 86400} day{'s' if seconds // 86400 != 1 else ''} old"

    def list_items(
        self, *, batch_id: str = "", status: str = "", cache_status: str = "",
        price_status: str = "", evidence_min: int = 0, page: int = 1, page_size: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        page_size, page, evidence_min = max(1, min(100, page_size)), max(1, page), max(0, evidence_min)
        where = ["i.review_status='DONE'", "TRIM(COALESCE(i.title,''))!=''"]
        values: list[object] = []
        if batch_id:
            where.append("i.batch_id=?")
            values.append(batch_id)
        if status:
            where.append("COALESCE(p.status,'NOT_REQUESTED')=?")
            values.append(status)
        if cache_status == "WITH_EVIDENCE":
            where.append("p.evidence_version_id IS NOT NULL")
        elif cache_status == "WITHOUT_EVIDENCE":
            where.append("p.evidence_version_id IS NULL")
        if price_status == "SET":
            where.append("i.price_cents IS NOT NULL")
        elif price_status == "MISSING":
            where.append("i.price_cents IS NULL")
        if evidence_min:
            where.append("COALESCE(e.tapes_averaged,0)>=?")
            values.append(evidence_min)
        clause = " WHERE " + " AND ".join(where)
        with self._connect() as connection:
            has_photos = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='photos'"
            ).fetchone() is not None
            photo_sql = (
                "(SELECT photo_id FROM photos ph WHERE ph.item_id=i.item_id AND ph.kind='product' "
                "ORDER BY ph.photo_order,ph.photo_id LIMIT 1)"
                if has_photos else "NULL"
            )
            from_sql = """ FROM items i LEFT JOIN pricing_item_states p ON p.item_id=i.item_id
                LEFT JOIN pricing_evidence e ON e.evidence_id=p.evidence_version_id"""
            total = int(connection.execute(f"SELECT COUNT(*){from_sql}{clause}", values).fetchone()[0])
            rows = connection.execute(
                f"""SELECT i.item_id,i.batch_id,i.title,i.price_cents,i.sequence,i.review_status,
                    i.record_revision,COALESCE(p.approved_title,i.title) approved_title,
                    COALESCE(p.title_key,'') title_key,COALESCE(p.disposition,'SKIP') disposition,
                    COALESCE(p.status,'NOT_REQUESTED') status,COALESCE(p.pricing_source,'') pricing_source,
                    p.evidence_version_id evidence_id,p.current_price_cents,p.error_code,p.error_message,
                    p.queued_at,p.updated_at,e.average_cad,e.median_cad,e.lowest_cad,e.highest_cad,
                    e.tapes_averaged,e.collected_at,e.expires_at,e.analysis_date,e.queried_title,
                    {photo_sql} thumbnail_photo_id {from_sql}{clause}
                    ORDER BY i.batch_id,i.sequence,i.item_id LIMIT ? OFFSET ?""",
                [*values, page_size, (page - 1) * page_size],
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["search_url"] = generate_search_url(str(item["title"]))
            item["cache_age"] = self._cache_age(item.get("collected_at"))
            item["stale_evidence"] = bool(
                item.get("evidence_id") and item.get("queried_title")
                and normalize_title(str(item["title"])) != normalize_title(str(item["queried_title"]))
            )
            result.append(item)
        return result, total

    def evidence_for_item(self, item_id: str) -> dict[str, Any] | None:
        state = self.item_state(item_id)
        evidence_id = state.get("evidence_version_id")
        return self.cache.get_evidence(int(evidence_id)) if evidence_id else None

    def evidence_validity(self, item_id: str) -> tuple[bool, str]:
        item = inventory_db.get_item(self.paths.db_file, item_id)
        if item is None:
            return False, "Item no longer exists."
        state = self.item_state(item_id, str(item["batch_id"]))
        evidence = self.evidence_for_item(item_id)
        if not evidence:
            return False, "No evidence is attached."
        item_key = normalize_title(str(item.get("title") or ""))
        if str(item["batch_id"]) != str(state.get("batch_id")):
            return False, "Pricing Batch does not match the Item Batch."
        if item_key != str(state.get("title_key") or "") or item_key != str(evidence.get("title_key") or ""):
            return False, "The saved title changed after collection; this evidence is historical only."
        if int(item.get("record_revision") or 0) != int(state.get("item_revision") or 0):
            return False, "The Item changed after evidence collection. Re-open or recollect before accepting."
        if str(state.get("status")) != "EVIDENCE_READY":
            return False, f"Evidence cannot be accepted while status is {state.get('status')}."
        return True, ""

    def accept_price(
        self, item_id: str, decision: str, *, manual_price_cents: int | None = None,
        actor: str = "local-operator", request_id: str | None = None,
    ) -> int | None:
        request_id = request_id or uuid4().hex
        timestamp = now()
        with self._connect() as connection:
            prior_request = connection.execute(
                "SELECT status,result_json FROM pricing_decision_requests WHERE request_id=?", (request_id,)
            ).fetchone()
            if prior_request and str(prior_request["status"]) == "SUCCESS":
                return json.loads(str(prior_request["result_json"])).get("new_price_cents")
            connection.execute("BEGIN IMMEDIATE")
            item = connection.execute("SELECT * FROM items WHERE item_id=?", (item_id,)).fetchone()
            state = connection.execute(
                "SELECT * FROM pricing_item_states WHERE item_id=?", (item_id,)
            ).fetchone()
            if item is None or state is None:
                raise KeyError("Item or pricing state no longer exists")
            evidence = (
                connection.execute(
                    "SELECT * FROM pricing_evidence WHERE evidence_id=?", (state["evidence_version_id"],)
                ).fetchone()
                if state["evidence_version_id"] is not None else None
            )
            item_key = normalize_title(str(item["title"] or ""))
            if str(item["batch_id"]) != str(state["batch_id"]):
                raise ValueError("Pricing Batch does not match the Item Batch")
            if item_key != str(state["title_key"] or ""):
                raise ValueError("Saved Item title no longer matches the pricing title")
            if int(item["record_revision"]) != int(state["item_revision"]):
                raise RuntimeError("Item changed after evidence collection; reload before accepting a price")
            previous = item["price_cents"]
            if decision in {"AVERAGE", "MEDIAN"}:
                if str(state["status"]) != "EVIDENCE_READY" or evidence is None:
                    raise ValueError("Valid evidence is unavailable")
                if item_key != str(evidence["title_key"]):
                    raise ValueError("Evidence was collected for a different title")
                field = "average_cad" if decision == "AVERAGE" else "median_cad"
                if not evidence[field]:
                    raise ValueError(f"{decision.title()} evidence is unavailable")
                new_price = money_to_cents(Decimal(str(evidence[field])))
                source = f"EBAY_{decision}"
            elif decision == "MANUAL":
                if manual_price_cents is None:
                    raise ValueError("Manual price is required")
                new_price, source = manual_price_cents, "MANUAL"
            elif decision in {"KEEP", "SKIP"}:
                new_price, source = previous, "KEEP_EXISTING" if decision == "KEEP" else "SKIPPED"
            else:
                raise ValueError("Unknown pricing decision")
            saved = dict(item)
            if decision not in {"KEEP", "SKIP"}:
                result = inventory_db.update_item_in_connection(
                    connection, item_id,
                    {"price_cents": new_price, "working_source": "PRICING_REVIEW"},
                    source="PRICING_REVIEW", expected_revision=int(item["record_revision"]),
                )
                if result:
                    saved = dict(result)
                else:
                    saved_row = connection.execute("SELECT * FROM items WHERE item_id=?", (item_id,)).fetchone()
                    saved = dict(saved_row) if saved_row else saved
            evidence_dict = dict(evidence) if evidence else None
            cursor = connection.execute(
                """INSERT INTO pricing_decisions(
                   item_id,batch_id,approved_title,decision,evidence_version_id,
                   previous_price_cents,new_price_cents,actor,item_revision,decided_at,detail_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item_id, item["batch_id"], item["title"], decision,
                    state["evidence_version_id"], previous, new_price, actor,
                    int(saved.get("record_revision") or item["record_revision"]), timestamp,
                    json.dumps({"source": source, "evidence_snapshot": evidence_dict}, sort_keys=True),
                ),
            )
            final_status = "SKIPPED" if decision == "SKIP" else "PRICE_ACCEPTED"
            connection.execute(
                """UPDATE pricing_item_states SET disposition=?,status=?,pricing_source=?,
                   current_price_cents=?,item_revision=?,updated_at=? WHERE item_id=?""",
                (
                    "SKIP" if decision == "SKIP" else "MANUAL", final_status, source,
                    new_price, int(saved.get("record_revision") or item["record_revision"]),
                    timestamp, item_id,
                ),
            )
            payload = {
                "decision_id": int(cursor.lastrowid), "new_price_cents": new_price,
                "evidence_id": state["evidence_version_id"],
            }
            connection.execute(
                """INSERT INTO pricing_decision_requests(
                   request_id,item_id,status,result_json,created_at,completed_at
                   ) VALUES(?,?,'SUCCESS',?,?,?) ON CONFLICT(request_id) DO NOTHING""",
                (request_id, item_id, json.dumps(payload, sort_keys=True), timestamp, timestamp),
            )
            connection.commit()
        self._event(
            "pricing.decision", "COMPLETE", actor=actor, item_id=item_id,
            batch_id=str(item["batch_id"]), detail={"decision": decision, **payload},
        )
        return new_price

    def next_eligible_item(self, item_id: str) -> str | None:
        with self._connect() as connection:
            current = connection.execute(
                "SELECT batch_id,sequence FROM items WHERE item_id=?", (item_id,)
            ).fetchone()
            if current is None:
                return None
            row = connection.execute(
                """SELECT i.item_id FROM items i
                   LEFT JOIN pricing_item_states p ON p.item_id=i.item_id
                   WHERE i.batch_id=? AND i.sequence>? AND i.review_status='DONE'
                   AND TRIM(COALESCE(i.title,''))!=''
                   AND COALESCE(p.status,'NOT_REQUESTED') NOT IN ('PRICE_ACCEPTED','SKIPPED','MANUAL_PRICE')
                   ORDER BY i.sequence,i.item_id LIMIT 1""",
                (current["batch_id"], current["sequence"]),
            ).fetchone()
        return str(row[0]) if row else None

    def bulk_action(
        self, item_ids: list[str], action: str, *, fixed_price_cents: int | None = None,
        actor: str = "local-operator", request_id: str,
    ) -> PricingBulkResult:
        unique_ids = list(dict.fromkeys(value for value in item_ids if value))
        if len(unique_ids) != len(item_ids):
            raise ValueError("Bulk selection contains duplicate or blank Item IDs")
        if not unique_ids:
            raise ValueError("Select at least one Item")
        if action not in {"QUEUE", "CANCEL", "SKIP", "AVERAGE", "MEDIAN", "KEEP", "FIXED"}:
            raise ValueError("Unknown bulk pricing action")
        if action == "FIXED" and fixed_price_cents is None:
            raise ValueError("Fixed price is required")
        with self._connect() as connection:
            previous = connection.execute(
                "SELECT status,result_json FROM operation_requests WHERE request_id=?", (request_id,)
            ).fetchone()
            if previous and str(previous["status"]) == "SUCCESS":
                payload = json.loads(str(previous["result_json"]))
                payload["errors"] = tuple(payload.get("errors") or [])
                return PricingBulkResult(**payload)
            placeholders = ",".join("?" for _ in unique_ids)
            rows = connection.execute(
                f"SELECT * FROM items WHERE item_id IN ({placeholders})", unique_ids
            ).fetchall()
        if len(rows) != len(unique_ids):
            raise ValueError("One or more selected Items no longer exist")
        batches = {str(row["batch_id"]) for row in rows}
        if len(batches) != 1:
            raise ValueError("Bulk pricing actions must be confirmed one Batch at a time")
        batch_id = next(iter(batches))
        for row in rows:
            if str(row["review_status"]) != "DONE" or not normalize_title(str(row["title"] or "")):
                raise ValueError(f"{row['item_id']} does not have an approved title")
            if action in {"AVERAGE", "MEDIAN"}:
                valid, reason = self.evidence_validity(str(row["item_id"]))
                if not valid:
                    raise ValueError(f"{row['item_id']}: {reason}")
        changed = 0
        checkpoint_id = 0
        timestamp = now()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """INSERT INTO operation_requests(
                       request_id,operation_type,batch_id,status,result_json,error_message,
                       created_at,updated_at,completed_at
                       ) VALUES(?,?,?,'RUNNING','{}','',?,?,NULL)
                       ON CONFLICT(request_id) DO UPDATE SET status='RUNNING',error_message='',
                       updated_at=excluded.updated_at,completed_at=NULL""",
                    (request_id, f"PRICING_{action}", batch_id, timestamp, timestamp),
                )
                checkpoint_id = inventory_db.create_batch_checkpoint_in_connection(
                    connection, batch_id, reason=f"Before pricing bulk action {action}",
                    source="PRICING_BULK",
                )
                settings = self.settings()
                for original in rows:
                    item_id = str(original["item_id"])
                    item = connection.execute("SELECT * FROM items WHERE item_id=?", (item_id,)).fetchone()
                    assert item is not None
                    state = connection.execute(
                        "SELECT * FROM pricing_item_states WHERE item_id=?", (item_id,)
                    ).fetchone()
                    before_status = str(state["status"]) if state else "NOT_REQUESTED"
                    before_price = item["price_cents"]
                    if action == "CANCEL":
                        if before_status in ACTIVE_JOB_STATES:
                            connection.execute(
                                """UPDATE pricing_item_states SET status='CANCELLED',error_code='CANCELLED',
                                   error_message='Cancelled by confirmed bulk action.',updated_at=? WHERE item_id=?""",
                                (timestamp, item_id),
                            )
                            changed += 1
                            if state:
                                self._cancel_orphaned_title_job(
                                    connection, str(state["title_key"]), int(state["request_max_listings"]), timestamp
                                )
                    elif action == "QUEUE":
                        key = normalize_title(str(item["title"]))
                        cached = self.cache.get_analysis(str(item["title"]), max_listings=settings.max_sold_listings)
                        new_status = (
                            "EVIDENCE_READY" if cached and cached.status == AnalysisStatus.COMPLETE
                            else "NO_VALID_MATCHES" if cached else "PENDING"
                        )
                        connection.execute(
                            """INSERT INTO pricing_item_states(
                               item_id,batch_id,approved_title,title_key,item_revision,request_max_listings,
                               disposition,status,pricing_source,evidence_version_id,current_price_cents,
                               queued_at,updated_at
                               ) VALUES(?,?,?,?,?,?,'QUEUE',?,?,?,?,?,?)
                               ON CONFLICT(item_id) DO UPDATE SET approved_title=excluded.approved_title,
                               title_key=excluded.title_key,item_revision=excluded.item_revision,
                               request_max_listings=excluded.request_max_listings,disposition='QUEUE',
                               status=excluded.status,pricing_source=excluded.pricing_source,
                               evidence_version_id=excluded.evidence_version_id,
                               current_price_cents=excluded.current_price_cents,queued_at=excluded.queued_at,
                               error_code='',error_message='',updated_at=excluded.updated_at""",
                            (
                                item_id, item["batch_id"], item["title"], key,
                                int(item["record_revision"]), settings.max_sold_listings,
                                new_status, "CACHE" if cached else "",
                                cached.evidence_id if cached else None, item["price_cents"], timestamp, timestamp,
                            ),
                        )
                        if not cached:
                            active = connection.execute(
                                """SELECT 1 FROM pricing_jobs WHERE title_key=? AND max_listings=?
                                   AND status IN ('PENDING','RUNNING','PAUSED')""",
                                (key, settings.max_sold_listings),
                            ).fetchone()
                            if not active:
                                connection.execute(
                                    """INSERT INTO pricing_jobs(
                                       item_id,batch_id,approved_title,title_key,max_listings,status,
                                       refresh,attempts,created_at,updated_at
                                       ) VALUES(?,?,?,?,?,'PENDING',0,0,?,?)""",
                                    (item_id, item["batch_id"], item["title"], key, settings.max_sold_listings, timestamp, timestamp),
                                )
                        if before_status != new_status or (state and state["evidence_version_id"] != (cached.evidence_id if cached else None)):
                            changed += 1
                    else:
                        evidence = (
                            connection.execute(
                                "SELECT * FROM pricing_evidence WHERE evidence_id=?", (state["evidence_version_id"],)
                            ).fetchone() if state and state["evidence_version_id"] else None
                        )
                        if action == "AVERAGE":
                            new_price = money_to_cents(Decimal(str(evidence["average_cad"])))
                            source = "EBAY_AVERAGE"
                        elif action == "MEDIAN":
                            new_price = money_to_cents(Decimal(str(evidence["median_cad"])))
                            source = "EBAY_MEDIAN"
                        elif action == "FIXED":
                            new_price, source = fixed_price_cents, "BULK_FIXED"
                        elif action == "KEEP":
                            new_price, source = before_price, "KEEP_EXISTING"
                        else:
                            new_price, source = before_price, "SKIPPED"
                        if action not in {"KEEP", "SKIP"} and new_price != before_price:
                            saved = inventory_db.update_item_in_connection(
                                connection, item_id,
                                {"price_cents": new_price, "working_source": "PRICING_BULK"},
                                source="PRICING_BULK", expected_revision=int(item["record_revision"]),
                            )
                            revision = int(saved["record_revision"]) if saved else int(item["record_revision"]) + 1
                            changed += 1
                        else:
                            revision = int(item["record_revision"])
                            if action == "SKIP" and before_status != "SKIPPED":
                                changed += 1
                        connection.execute(
                            """INSERT INTO pricing_decisions(
                               item_id,batch_id,approved_title,decision,evidence_version_id,
                               previous_price_cents,new_price_cents,actor,item_revision,decided_at,detail_json
                               ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                item_id, item["batch_id"], item["title"], action,
                                state["evidence_version_id"] if state else None,
                                before_price, new_price, actor, revision, timestamp,
                                json.dumps({"source": source, "bulk": True, "request_id": request_id}, sort_keys=True),
                            ),
                        )
                        connection.execute(
                            """UPDATE pricing_item_states SET disposition=?,status=?,pricing_source=?,
                               current_price_cents=?,item_revision=?,updated_at=? WHERE item_id=?""",
                            (
                                "SKIP" if action == "SKIP" else "MANUAL",
                                "SKIPPED" if action == "SKIP" else "PRICE_ACCEPTED",
                                source, new_price, revision, timestamp, item_id,
                            ),
                        )
                result = PricingBulkResult(
                    requested=len(unique_ids), validated=len(unique_ids), changed=changed,
                    unchanged=len(unique_ids) - changed, failed=0, errors=(),
                    checkpoint_id=checkpoint_id, request_id=request_id,
                )
                connection.execute(
                    """UPDATE operation_requests SET status='SUCCESS',result_json=?,updated_at=?,completed_at=?
                       WHERE request_id=?""",
                    (json.dumps(result.as_dict(), sort_keys=True), timestamp, timestamp, request_id),
                )
                connection.commit()
            self._event(
                "pricing.bulk", "COMPLETE", actor=actor, batch_id=batch_id,
                detail=result.as_dict(),
            )
            return result
        except Exception as exc:
            failure_time = now()
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO operation_requests(
                       request_id,operation_type,batch_id,status,result_json,error_message,
                       created_at,updated_at,completed_at
                       ) VALUES(?,?,?,'FAILED','{}',?,?,?,?)
                       ON CONFLICT(request_id) DO UPDATE SET status='FAILED',error_message=excluded.error_message,
                       updated_at=excluded.updated_at,completed_at=excluded.completed_at""",
                    (request_id, f"PRICING_{action}", batch_id, str(exc)[:500], timestamp, failure_time, failure_time),
                )
            raise

    def save_runtime_probe(self, result: dict[str, str]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO pricing_runtime_probes(probed_at,browser_status,ebay_status,message) VALUES(?,?,?,?)",
                (now(), result.get("browser_status", "UNKNOWN"), result.get("ebay_status", "UNKNOWN"), result.get("message", "")[:1000]),
            )

    def latest_runtime_probe(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM pricing_runtime_probes ORDER BY probe_id DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def diagnostics(self) -> dict[str, Any]:
        settings = self.settings()
        with self._connect() as connection:
            cache_entries = int(connection.execute("SELECT COUNT(*) FROM pricing_cache_heads").fetchone()[0])
            evidence_versions = int(connection.execute("SELECT COUNT(*) FROM pricing_evidence").fetchone()[0])
            cache_hits = int(connection.execute(
                "SELECT COUNT(*) FROM pricing_events WHERE event_type='pricing.review_disposition' "
                "AND detail_json LIKE '%CACHE%'"
            ).fetchone()[0])
            request_starts = int(connection.execute("SELECT COUNT(*) FROM pricing_request_log").fetchone()[0])
            schema = int(connection.execute("SELECT MAX(version) FROM pricing_schema").fetchone()[0])
        configured = os.getenv("SNAPIMS_PRICING_CHROMIUM_EXECUTABLE", "").strip()
        browser_path = configured or shutil.which("chromium") or shutil.which("google-chrome") or ""
        try:
            import importlib.util
            playwright_importable = importlib.util.find_spec("playwright") is not None
        except Exception:
            playwright_importable = False
        return {
            "schema_version": schema, "database_path": str(self.path), "queue": self.queue_summary(),
            "settings": asdict(settings), "cache_entries": cache_entries,
            "evidence_versions": evidence_versions, "cache_hits": cache_hits,
            "request_starts": request_starts, "playwright_importable": playwright_importable,
            "configured_browser_path": browser_path,
            "browser_path_exists": bool(browser_path and Path(browser_path).is_file()),
            "runtime_probe": self.latest_runtime_probe(),
        }
