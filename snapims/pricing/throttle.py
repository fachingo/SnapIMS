"""Durable request-start throttle shared by queue jobs and process restarts."""

from __future__ import annotations

import asyncio
import random
import sqlite3
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from snapims.pricing.settings import AppSettings
from snapims.sqlite_utils import ClosingConnection

AsyncSleep = Callable[[float], Awaitable[None]]


class PersistentRequestThrottle:
    """Reserve actual outbound request starts using a SQLite-backed timestamp.

    Cache hits never call this object. A reservation is written immediately before
    the caller performs navigation, so separate controller instances and a restarted
    worker cannot treat every title as a first request.
    """

    def __init__(
        self,
        path: str | Path,
        settings: AppSettings,
        *,
        clock: Callable[[], float] = time.time,
        sleep: AsyncSleep = asyncio.sleep,
        random_uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.path = Path(path)
        self.settings = settings
        self._clock = clock
        self._sleep = sleep
        self._random_uniform = random_uniform
        self._process_lock = asyncio.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path, timeout=30, check_same_thread=False, factory=ClosingConnection
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pricing_request_throttle (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    last_request_epoch REAL,
                    last_request_at TEXT NOT NULL DEFAULT '',
                    updated_by TEXT NOT NULL DEFAULT ''
                );
                INSERT OR IGNORE INTO pricing_request_throttle(singleton) VALUES(1);
                CREATE TABLE IF NOT EXISTS pricing_request_log (
                    request_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_epoch REAL NOT NULL,
                    request_at TEXT NOT NULL,
                    title_key TEXT NOT NULL,
                    job_id INTEGER,
                    outcome TEXT NOT NULL DEFAULT 'STARTED'
                );
                """
            )

    async def wait_for_turn(
        self,
        *,
        title_key: str,
        job_id: int | None,
        cancel_event: threading.Event,
        pause_event: threading.Event,
    ) -> str:
        delay = self._random_uniform(
            self.settings.delay_min_seconds, self.settings.delay_max_seconds
        )
        async with self._process_lock:
            while True:
                if cancel_event.is_set():
                    return "CANCELLED"
                if pause_event.is_set():
                    return "PAUSED"
                with self._connect() as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    row = connection.execute(
                        "SELECT last_request_epoch FROM pricing_request_throttle WHERE singleton=1"
                    ).fetchone()
                    previous = float(row[0]) if row and row[0] is not None else None
                    current = self._clock()
                    remaining = 0.0 if previous is None else max(0.0, previous + delay - current)
                    if remaining <= 0:
                        request_at = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(current))
                        connection.execute(
                            """UPDATE pricing_request_throttle
                               SET last_request_epoch=?,last_request_at=?,updated_by=?
                               WHERE singleton=1""",
                            (current, request_at, f"job:{job_id}" if job_id else "controller"),
                        )
                        connection.execute(
                            """INSERT INTO pricing_request_log(
                                   request_epoch,request_at,title_key,job_id,outcome
                               ) VALUES(?,?,?,?, 'STARTED')""",
                            (current, request_at, title_key, job_id),
                        )
                        connection.commit()
                        return "READY"
                    connection.commit()
                await self._sleep(min(0.25, remaining))

    def starts(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM pricing_request_log ORDER BY request_log_id"
            ).fetchall()
        return [dict(row) for row in rows]
