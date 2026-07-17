from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from snapims import db
from snapims.recognition.base import RecognitionResult

RESULT_SUCCEEDED = "SUCCEEDED"
RESULT_FAILED = "FAILED"
REVIEW_UNREVIEWED = "UNREVIEWED"
REVIEW_REQUIRED = "MANUAL_REVIEW"
REVIEW_ACCEPTED = "ACCEPTED"
REVIEW_REJECTED = "REJECTED"
REVIEW_SKIPPED = "SKIPPED"
REVIEW_FAILED = "FAILED"
HIGH_CONFIDENCE_THRESHOLD = 0.85

QUEUE_ALL_UNREVIEWED = "All unreviewed"
QUEUE_NEEDS_ATTENTION = "Needs attention"
QUEUE_REVIEW_REQUIRED = QUEUE_NEEDS_ATTENTION
QUEUE_HIGH_CONFIDENCE = "High confidence"
QUEUE_FAILED = "Failed"
QUEUE_ACCEPTED = "Already accepted"
QUEUE_SKIPPED = "Skipped"
QUEUE_FILTERS = (
    QUEUE_ALL_UNREVIEWED,
    QUEUE_REVIEW_REQUIRED,
    QUEUE_HIGH_CONFIDENCE,
    QUEUE_FAILED,
    QUEUE_ACCEPTED,
    QUEUE_SKIPPED,
)


@dataclass(frozen=True, slots=True)
class StoredRecognitionResult:
    recognition_result_id: int
    item_id: str
    batch_id: str
    provider: str
    model_name: str
    created_at: str
    suggested_title: str
    edition: str
    distributor: str
    release_year: int | None
    barcode_candidates: tuple[str, ...]
    confidence: float
    uncertainty_reasons: tuple[str, ...]
    raw_response_reference: str
    requires_review: bool
    accepted_at: str | None
    result_status: str
    review_status: str
    reviewed_at: str | None
    accepted_fields: tuple[str, ...]
    accepted_values: dict[str, Any]
    error_message: str

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["barcode_candidates_json"] = json.dumps(self.barcode_candidates)
        value["uncertainty_reasons_json"] = json.dumps(self.uncertainty_reasons)
        value["accepted_fields_json"] = json.dumps(self.accepted_fields)
        value["accepted_values_json"] = json.dumps(self.accepted_values)
        return value


@dataclass(frozen=True, slots=True)
class ReviewQueueEntry:
    result: StoredRecognitionResult
    item_title: str
    item_edition: str
    item_distributor: str
    item_release_year: int | None
    item_barcode: str
    shelf: str
    sequence: int
    front_image: str
    front_thumbnail: str


def _stored_result(row: Any) -> StoredRecognitionResult:
    return StoredRecognitionResult(
        recognition_result_id=int(row["recognition_result_id"]),
        item_id=str(row["item_id"]),
        batch_id=str(row["batch_id"] or ""),
        provider=str(row["provider"]),
        model_name=str(row["model_name"]),
        created_at=str(row["created_at"]),
        suggested_title=str(row["suggested_title"]),
        edition=str(row["edition"]),
        distributor=str(row["distributor"]),
        release_year=int(row["release_year"]) if row["release_year"] is not None else None,
        barcode_candidates=tuple(json.loads(row["barcode_candidates_json"])),
        confidence=float(row["confidence"]),
        uncertainty_reasons=tuple(json.loads(row["uncertainty_reasons_json"])),
        raw_response_reference=str(row["raw_response_reference"]),
        requires_review=bool(row["requires_review"]),
        accepted_at=str(row["accepted_at"]) if row["accepted_at"] is not None else None,
        result_status=str(row["result_status"]),
        review_status=str(row["review_status"]),
        reviewed_at=str(row["reviewed_at"]) if row["reviewed_at"] is not None else None,
        accepted_fields=tuple(json.loads(row["accepted_fields_json"])),
        accepted_values=dict(json.loads(row["accepted_values_json"])),
        error_message=str(row["error_message"]),
    )


def save_result(
    db_file: Path,
    item_id_value: str,
    result: RecognitionResult,
    *,
    model_name: str,
    created_at: str,
) -> StoredRecognitionResult:
    """Persist one successful suggestion and return the committed repository record."""
    db.initialize(db_file)
    with db.transaction(db_file) as connection:
        item = connection.execute(
            "SELECT batch_id FROM items WHERE item_id = ?",
            (item_id_value,),
        ).fetchone()
        if item is None:
            raise KeyError(f"Unknown Item ID: {item_id_value}")
        cursor = connection.execute(
            """
            INSERT INTO recognition_results(
                item_id, batch_id, provider, model_name, created_at, suggested_title,
                edition, distributor, release_year, barcode_candidates_json, confidence,
                uncertainty_reasons_json, raw_response_reference, requires_review
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id_value,
                item["batch_id"],
                result.provider_name,
                model_name,
                created_at,
                result.suggested_title,
                result.edition,
                result.distributor,
                result.year,
                json.dumps(result.barcode_candidates),
                result.confidence,
                json.dumps(result.uncertainty_reasons),
                result.raw_response_reference,
                int(result.requires_review),
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return a recognition result ID")
        row = connection.execute(
            "SELECT * FROM recognition_results WHERE recognition_result_id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Persisted recognition result could not be reloaded")
        stored = _stored_result(row)
    return stored


def get_result(db_file: Path, result_id: int) -> StoredRecognitionResult | None:
    db.initialize(db_file)
    with db.connect(db_file) as connection:
        row = connection.execute(
            "SELECT * FROM recognition_results WHERE recognition_result_id = ?",
            (result_id,),
        ).fetchone()
    return _stored_result(row) if row is not None else None


def latest_result_for_item(
    db_file: Path, item_id_value: str
) -> StoredRecognitionResult | None:
    db.initialize(db_file)
    with db.connect(db_file) as connection:
        row = connection.execute(
            """
            SELECT * FROM recognition_results
            WHERE item_id = ?
            ORDER BY recognition_result_id DESC
            LIMIT 1
            """,
            (item_id_value,),
        ).fetchone()
    return _stored_result(row) if row is not None else None


def list_results_for_item(db_file: Path, item_id_value: str) -> list[StoredRecognitionResult]:
    db.initialize(db_file)
    with db.connect(db_file) as connection:
        rows = connection.execute(
            """
            SELECT * FROM recognition_results
            WHERE item_id = ?
            ORDER BY created_at DESC, recognition_result_id DESC
            """,
            (item_id_value,),
        ).fetchall()
    return [_stored_result(row) for row in rows]


def has_result(db_file: Path, item_id_value: str) -> bool:
    db.initialize(db_file)
    with db.connect(db_file) as connection:
        row = connection.execute(
            """
            SELECT 1 FROM recognition_results
            WHERE item_id = ? AND result_status = ?
            LIMIT 1
            """,
            (item_id_value, RESULT_SUCCEEDED),
        ).fetchone()
    return row is not None


def save_failure(
    db_file: Path,
    item_id_value: str,
    *,
    provider: str,
    model_name: str,
    created_at: str,
    error_message: str,
) -> StoredRecognitionResult:
    db.initialize(db_file)
    with db.transaction(db_file) as connection:
        item = connection.execute(
            "SELECT batch_id FROM items WHERE item_id = ?",
            (item_id_value,),
        ).fetchone()
        if item is None:
            raise KeyError(f"Unknown Item ID: {item_id_value}")
        cursor = connection.execute(
            """
            INSERT INTO recognition_results(
                item_id, batch_id, provider, model_name, created_at,
                result_status, review_status, error_message
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id_value,
                item["batch_id"],
                provider,
                model_name,
                created_at,
                RESULT_FAILED,
                REVIEW_FAILED,
                error_message,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return a failed recognition result ID")
        row = connection.execute(
            "SELECT * FROM recognition_results WHERE recognition_result_id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Persisted recognition failure could not be reloaded")
        stored = _stored_result(row)
    return stored


def list_review_queue(
    db_file: Path,
    batch_id_value: str,
    queue_filter: str = QUEUE_ALL_UNREVIEWED,
) -> list[ReviewQueueEntry]:
    if queue_filter not in QUEUE_FILTERS:
        raise ValueError(f"Unknown recognition queue filter: {queue_filter}")
    filters: dict[str, tuple[str, tuple[Any, ...]]] = {
        QUEUE_ALL_UNREVIEWED: (
            "latest.result_status = ? AND latest.review_status = ?",
            (RESULT_SUCCEEDED, REVIEW_UNREVIEWED),
        ),
        QUEUE_REVIEW_REQUIRED: (
            """
            latest.result_status = ?
            AND (
                latest.review_status IN (?, ?)
                OR (
                    latest.review_status = ?
                    AND latest.requires_review = 1
                )
            )
            """,
            (
                RESULT_SUCCEEDED,
                REVIEW_REQUIRED,
                REVIEW_REJECTED,
                REVIEW_UNREVIEWED,
            ),
        ),
        QUEUE_HIGH_CONFIDENCE: (
            """
            latest.result_status = ? AND latest.review_status = ?
            AND latest.confidence >= ?
            """,
            (RESULT_SUCCEEDED, REVIEW_UNREVIEWED, HIGH_CONFIDENCE_THRESHOLD),
        ),
        QUEUE_FAILED: (
            "latest.result_status = ?",
            (RESULT_FAILED,),
        ),
        QUEUE_ACCEPTED: (
            "latest.result_status = ? AND latest.review_status = ?",
            (RESULT_SUCCEEDED, REVIEW_ACCEPTED),
        ),
        QUEUE_SKIPPED: (
            "latest.result_status = ? AND latest.review_status = ?",
            (RESULT_SUCCEEDED, REVIEW_SKIPPED),
        ),
    }
    where, parameters = filters[queue_filter]
    db.initialize(db_file)
    with db.connect(db_file) as connection:
        rows = connection.execute(
            f"""
            WITH ranked AS (
                SELECT rr.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY rr.item_id
                           ORDER BY rr.recognition_result_id DESC
                       ) AS result_rank
                FROM recognition_results rr
                WHERE rr.batch_id = ?
            ),
            latest AS (
                SELECT * FROM ranked WHERE result_rank = 1
            )
            SELECT latest.*, i.title AS item_title, i.edition AS item_edition,
                   i.distributor AS item_distributor, i.release_year AS item_release_year,
                   i.barcode AS item_barcode, i.shelf, i.sequence,
                   COALESCE(
                       MIN(CASE WHEN p.photo_order = 1 THEN p.processed_path END), ''
                   ) AS front_image,
                   COALESCE(
                       MIN(CASE WHEN p.photo_order = 1 THEN p.thumbnail_path END), ''
                   ) AS front_thumbnail
            FROM latest
            JOIN items i ON i.item_id = latest.item_id
            LEFT JOIN photos p ON p.item_id = i.item_id AND p.kind = 'product'
            WHERE {where}
            GROUP BY latest.recognition_result_id
            ORDER BY i.sequence, latest.recognition_result_id
            """,
            (batch_id_value, *parameters),
        ).fetchall()
    return [
        ReviewQueueEntry(
            result=_stored_result(row),
            item_title=str(row["item_title"]),
            item_edition=str(row["item_edition"]),
            item_distributor=str(row["item_distributor"]),
            item_release_year=(
                int(row["item_release_year"])
                if row["item_release_year"] is not None
                else None
            ),
            item_barcode=str(row["item_barcode"]),
            shelf=str(row["shelf"]),
            sequence=int(row["sequence"]),
            front_image=str(row["front_image"]),
            front_thumbnail=str(row["front_thumbnail"]),
        )
        for row in rows
    ]


def accept_result(
    db_file: Path,
    result_id: int,
    *,
    edited_values: dict[str, Any] | None = None,
    accepted_at: str,
) -> StoredRecognitionResult:
    db.initialize(db_file)
    with db.transaction(db_file) as connection:
        row = connection.execute(
            "SELECT * FROM recognition_results WHERE recognition_result_id = ?",
            (result_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown recognition result: {result_id}")
        if row["result_status"] != RESULT_SUCCEEDED:
            raise ValueError("A failed recognition attempt cannot be accepted")

        if edited_values is None:
            candidates: dict[str, Any] = {
                "title": row["suggested_title"],
                "edition": row["edition"],
                "distributor": row["distributor"],
                "release_year": row["release_year"],
            }
            barcodes = json.loads(row["barcode_candidates_json"])
            if barcodes:
                candidates["barcode"] = barcodes[0]
            values = {
                key: value
                for key, value in candidates.items()
                if value is not None and (not isinstance(value, str) or value.strip())
            }
        else:
            allowed = {"title", "edition", "distributor", "release_year", "barcode"}
            values = {key: value for key, value in edited_values.items() if key in allowed}
        if values:
            assignments = ", ".join(f"{key} = ?" for key in values)
            connection.execute(
                f"""
                UPDATE items
                SET {assignments}, recognition_provider = ?,
                    recognition_confidence = ?, updated_at = ?
                WHERE item_id = ?
                """,
                (
                    *values.values(),
                    row["provider"],
                    row["confidence"],
                    accepted_at,
                    row["item_id"],
                ),
            )
        else:
            connection.execute(
                """
                UPDATE items
                SET recognition_provider = ?, recognition_confidence = ?,
                    updated_at = ?
                WHERE item_id = ?
                """,
                (row["provider"], row["confidence"], accepted_at, row["item_id"]),
            )
        connection.execute(
            """
            UPDATE recognition_results
            SET accepted_at = ?, reviewed_at = ?, review_status = ?,
                accepted_fields_json = ?, accepted_values_json = ?
            WHERE recognition_result_id = ?
            """,
            (
                accepted_at,
                accepted_at,
                REVIEW_ACCEPTED,
                json.dumps(list(values)),
                json.dumps(values),
                result_id,
            ),
        )
    stored = get_result(db_file, result_id)
    if stored is None:
        raise RuntimeError("Accepted recognition result could not be reloaded")
    return stored


def set_review_status(
    db_file: Path,
    result_id: int,
    status: str,
    *,
    reviewed_at: str,
) -> StoredRecognitionResult:
    allowed = {REVIEW_REJECTED, REVIEW_SKIPPED, REVIEW_REQUIRED}
    if status not in allowed:
        raise ValueError(f"Unsupported recognition review status: {status}")
    db.initialize(db_file)
    with db.transaction(db_file) as connection:
        row = connection.execute(
            """
            SELECT result_status FROM recognition_results
            WHERE recognition_result_id = ?
            """,
            (result_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown recognition result: {result_id}")
        if row["result_status"] != RESULT_SUCCEEDED:
            raise ValueError("A failed recognition attempt cannot be reviewed")
        connection.execute(
            """
            UPDATE recognition_results
            SET review_status = ?, reviewed_at = ?
            WHERE recognition_result_id = ?
            """,
            (status, reviewed_at, result_id),
        )
    stored = get_result(db_file, result_id)
    if stored is None:
        raise RuntimeError("Reviewed recognition result could not be reloaded")
    return stored
