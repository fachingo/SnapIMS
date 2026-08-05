"""Native SnapIMS hooks for Review, Batch Editor, bulk, and CSV writes."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from snapims.pricing.normalization import normalize_title
from snapims.pricing.workflow import PricingWorkflow, now


def workflow() -> PricingWorkflow:
    return PricingWorkflow()


def pricing_batch_mode(batch_id: str) -> str:
    return workflow().get_batch_mode(batch_id)


def pricing_item_state(item_id: str, batch_id: str = "") -> dict[str, Any]:
    return workflow().item_state(item_id, batch_id)


def pricing_default_disposition(batch_id: str) -> str:
    return workflow().default_disposition(batch_id)


def record_review_pricing(
    *, item_id: str, batch_id: str, approved_title: str,
    submitted_price_cents: int | None, price_touched: bool,
    requested_disposition: str, previous_price_cents: int | None | object = ...,
    item_revision: int | None = None, actor: str = "local-operator",
) -> dict[str, Any]:
    return workflow().record_review_approval(
        item_id=item_id, batch_id=batch_id, approved_title=approved_title,
        submitted_price_cents=submitted_price_cents, price_touched=price_touched,
        requested_disposition=requested_disposition,
        previous_price_cents=previous_price_cents, item_revision=item_revision, actor=actor,
    )


def record_item_change_in_connection(
    connection: sqlite3.Connection, item_id: str,
    previous: dict[str, Any] | sqlite3.Row, saved: dict[str, Any] | sqlite3.Row,
    *, source: str,
) -> None:
    """Enforce title staleness and manual-price protection in the Item transaction.

    The local import from ``snapims.db.update_item_in_connection`` reaches this
    function only after the pricing migration exists. Direct POSTs, JavaScript-
    disabled forms, Batch Editor, ordinary bulk edits, and CSV imports therefore
    share one server-side boundary.
    """

    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "pricing_item_states" not in tables:
        return
    old_title, new_title = str(previous["title"] or ""), str(saved["title"] or "")
    old_price, new_price = previous["price_cents"], saved["price_cents"]
    timestamp = now()
    state = connection.execute(
        "SELECT * FROM pricing_item_states WHERE item_id=?", (item_id,)
    ).fetchone()
    old_key = str(state["title_key"] or "") if state else normalize_title(old_title)
    new_key = normalize_title(new_title)
    if state and old_key != new_key:
        connection.execute(
            """UPDATE pricing_item_states SET status='STALE',item_revision=?,
               error_code='TITLE_CHANGED',
               error_message='Saved title changed; attached evidence is historical and cannot be accepted.',
               updated_at=? WHERE item_id=?""",
            (int(saved["record_revision"]), timestamp, item_id),
        )
        waiter = connection.execute(
            """SELECT 1 FROM pricing_item_states WHERE title_key=?
               AND request_max_listings=? AND status IN ('PENDING','RUNNING','PAUSED') LIMIT 1""",
            (old_key, int(state["request_max_listings"] or 3)),
        ).fetchone()
        if waiter is None:
            connection.execute(
                """UPDATE pricing_jobs SET status='STALE',finished_at=?,updated_at=?,
                   error_code='TITLE_CHANGED',error_message='All waiting Items changed title.'
                   WHERE title_key=? AND max_listings=? AND status IN ('PENDING','RUNNING','PAUSED')""",
                (timestamp, timestamp, old_key, int(state["request_max_listings"] or 3)),
            )
    if old_price != new_price and not source.startswith("PRICING_") and new_key:
        max_listings = int(state["request_max_listings"] or 3) if state else 3
        connection.execute(
            """INSERT INTO pricing_item_states(
               item_id,batch_id,approved_title,title_key,item_revision,request_max_listings,
               disposition,status,pricing_source,current_price_cents,updated_at
               ) VALUES(?,?,?,?,?,?,'MANUAL',?,'MANUAL',?,?)
               ON CONFLICT(item_id) DO UPDATE SET item_revision=excluded.item_revision,
               disposition='MANUAL',status=excluded.status,pricing_source='MANUAL',
               current_price_cents=excluded.current_price_cents,updated_at=excluded.updated_at""",
            (
                item_id, saved["batch_id"], new_title, new_key, int(saved["record_revision"]),
                max_listings, "MANUAL_PRICE" if new_price is not None else "NOT_REQUESTED",
                new_price, timestamp,
            ),
        )
        waiter = connection.execute(
            """SELECT 1 FROM pricing_item_states WHERE title_key=? AND request_max_listings=?
               AND status IN ('PENDING','RUNNING','PAUSED') LIMIT 1""",
            (old_key or new_key, max_listings),
        ).fetchone()
        if waiter is None:
            connection.execute(
                """UPDATE pricing_jobs SET status='CANCELLED',finished_at=?,updated_at=?,
                   error_code='MANUAL_PRICE',error_message='Manual Item price suppresses collection.'
                   WHERE title_key=? AND max_listings=? AND status IN ('PENDING','RUNNING','PAUSED')""",
                (timestamp, timestamp, old_key or new_key, max_listings),
            )
    if "pricing_events" in tables and (old_key != new_key or old_price != new_price):
        connection.execute(
            """INSERT INTO pricing_events(
               occurred_at,event_type,status,actor,item_id,batch_id,detail_json
               ) VALUES(?,?,?,?,?,?,?)""",
            (
                timestamp, "pricing.item_write_guard", "COMPLETE", source,
                item_id, saved["batch_id"],
                json.dumps({"title_changed": old_key != new_key, "price_changed": old_price != new_price}, sort_keys=True),
            ),
        )


def pricing_diagnostics() -> dict[str, Any]:
    return workflow().diagnostics()
