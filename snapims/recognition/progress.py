from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from sqlite3 import Row

from snapims import db


@dataclass(frozen=True, slots=True)
class RecognitionJob:
    job_id: int
    batch_id: str
    provider: str
    model_name: str
    total: int
    completed: int
    skipped: int
    failed: int
    status: str
    last_item_id: str
    started_at: str
    completed_at: str | None
    only_missing_title: bool
    force_reprocess: bool

    @property
    def remaining(self) -> int:
        return max(0, self.total - self.completed)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _job(row: Row) -> RecognitionJob:
    return RecognitionJob(
        job_id=int(row["recognition_job_id"]),
        batch_id=str(row["batch_id"]),
        provider=str(row["provider"]),
        model_name=str(row["model_name"]),
        total=int(row["total"]),
        completed=int(row["completed"]),
        skipped=int(row["skipped"]),
        failed=int(row["failed"]),
        status=str(row["status"]),
        last_item_id=str(row["last_item_id"] or ""),
        started_at=str(row["started_at"]),
        completed_at=(str(row["completed_at"]) if row["completed_at"] else None),
        only_missing_title=bool(row["only_missing_title"]),
        force_reprocess=bool(row["force_reprocess"]),
    )


def latest_job(db_file: Path, batch_id: str) -> RecognitionJob | None:
    db.initialize(db_file)
    with db.connect(db_file) as connection:
        row = connection.execute(
            "SELECT * FROM recognition_jobs WHERE batch_id=? ORDER BY recognition_job_id DESC LIMIT 1",
            (batch_id,),
        ).fetchone()
    return _job(row) if row else None


def start_or_resume_job(
    db_file: Path,
    batch_id: str,
    provider: str,
    model_name: str,
    items: list[dict],
    *,
    only_missing_title: bool,
    force_reprocess: bool,
) -> RecognitionJob:
    latest = latest_job(db_file, batch_id)
    can_resume = (
        latest is not None
        and latest.status in {"RUNNING", "INTERRUPTED"}
        and latest.provider == provider
        and latest.model_name == model_name
        and latest.only_missing_title == only_missing_title
        and not force_reprocess
    )
    if can_resume and latest is not None:
        with db.transaction(db_file) as connection:
            connection.execute(
                "UPDATE recognition_jobs SET status='RUNNING', completed_at=NULL WHERE recognition_job_id=?",
                (latest.job_id,),
            )
        resumed = latest_job(db_file, batch_id)
        assert resumed is not None
        return resumed
    with db.transaction(db_file) as connection:
        cursor = connection.execute(
            """
            INSERT INTO recognition_jobs(
                batch_id, provider, model_name, started_at, total,
                only_missing_title, force_reprocess
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (batch_id, provider, model_name, _now(), len(items), int(only_missing_title), int(force_reprocess)),
        )
        job_id = int(cursor.lastrowid or 0)
        connection.executemany(
            """
            INSERT INTO recognition_job_items(recognition_job_id, item_id, sequence)
            VALUES(?, ?, ?)
            """,
            [(job_id, item["item_id"], item["sequence"]) for item in items],
        )
    created = latest_job(db_file, batch_id)
    assert created is not None
    return created


def pending_item_ids(db_file: Path, job_id: int) -> set[str]:
    with db.connect(db_file) as connection:
        rows = connection.execute(
            "SELECT item_id FROM recognition_job_items WHERE recognition_job_id=? AND status='PENDING'",
            (job_id,),
        ).fetchall()
    return {str(row["item_id"]) for row in rows}


def record_boundary(
    db_file: Path,
    job_id: int,
    item_id: str,
    status: str,
    *,
    result_id: int | None = None,
    message: str = "",
) -> RecognitionJob:
    with db.transaction(db_file) as connection:
        connection.execute(
            """
            UPDATE recognition_job_items SET status=?, result_id=?, message=?
            WHERE recognition_job_id=? AND item_id=?
            """,
            (status, result_id, message, job_id, item_id),
        )
        counts = connection.execute(
            """
            SELECT COUNT(*) AS completed,
                   SUM(CASE WHEN status='SKIPPED' THEN 1 ELSE 0 END) AS skipped,
                   SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) AS failed
            FROM recognition_job_items
            WHERE recognition_job_id=? AND status != 'PENDING'
            """,
            (job_id,),
        ).fetchone()
        connection.execute(
            """
            UPDATE recognition_jobs SET completed=?, skipped=?, failed=?, last_item_id=?
            WHERE recognition_job_id=?
            """,
            (counts["completed"], counts["skipped"] or 0, counts["failed"] or 0, item_id, job_id),
        )
    with db.connect(db_file) as connection:
        row = connection.execute(
            "SELECT * FROM recognition_jobs WHERE recognition_job_id=?", (job_id,)
        ).fetchone()
    assert row is not None
    return _job(row)


def finish_job(db_file: Path, job_id: int, status: str = "COMPLETED") -> None:
    with db.transaction(db_file) as connection:
        connection.execute(
            "UPDATE recognition_jobs SET status=?, completed_at=? WHERE recognition_job_id=?",
            (status, _now(), job_id),
        )


def cursor_key(batch_id: str, queue: str) -> str:
    return f"review_cursor:{batch_id}:{queue}"


def get_review_cursor(db_file: Path, batch_id: str, queue: str) -> str | None:
    return db.get_setting(db_file, cursor_key(batch_id, queue))


def set_review_cursor(db_file: Path, batch_id: str, queue: str, item_id: str) -> None:
    db.set_setting(db_file, cursor_key(batch_id, queue), item_id)
