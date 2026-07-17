from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snapims import db

CONFIRMED_PHYSICAL_REVIEW = "CONFIRMED_PHYSICAL_REVIEW"
LIKELY_RECOGNITION_DERIVED = "LIKELY_RECOGNITION_DERIVED"
AMBIGUOUS_REVIEW_FLAG = "AMBIGUOUS_REVIEW_FLAG"
PHYSICAL_EVIDENCE_NOT_REFLECTED = "PHYSICAL_EVIDENCE_NOT_REFLECTED"
NOT_FLAGGED = "NOT_FLAGGED"


@dataclass(frozen=True, slots=True)
class ReviewFlagReconciliationRow:
    item_id: str
    batch_id: str
    current_review: bool
    classification: str
    command_review_evidence: bool | None
    manifest_review_evidence: bool | None
    accepted_result_ids: tuple[int, ...]
    acceptance_matches_item_update: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReviewFlagReconciliationReport:
    rows: tuple[ReviewFlagReconciliationRow, ...]

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.rows:
            counts[row.classification] = counts.get(row.classification, 0) + 1
        return counts


def _manifest_review_values(db_file: Path, batch_id: str) -> dict[str, bool] | None:
    manifest_path = (
        db_file.parent.parent / "processed" / batch_id / "batch_manifest.json"
    )
    if not manifest_path.is_file():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        items = payload["items"]
        if not isinstance(items, list):
            return None
        return {
            str(item["item_id"]): bool(item["review"])
            for item in items
            if isinstance(item, dict) and "item_id" in item and "review" in item
        }
    except (KeyError, OSError, TypeError, ValueError):
        return None


def _command_review_values(
    items: list[dict[str, Any]],
    commands_by_batch: dict[str, list[int]],
    audited_batches: set[str],
) -> dict[str, bool | None]:
    values: dict[str, bool | None] = {}
    previous_first_by_batch: dict[str, int] = {}
    for item in sorted(items, key=lambda value: (value["batch_id"], value["sequence"])):
        batch_id = str(item["batch_id"])
        first_stream = item["first_stream"]
        if batch_id not in audited_batches or first_stream is None:
            values[str(item["item_id"])] = None
            continue
        lower_bound = previous_first_by_batch.get(batch_id, -1)
        first_stream_value = int(first_stream)
        values[str(item["item_id"])] = any(
            lower_bound < stream_index < first_stream_value
            for stream_index in commands_by_batch.get(batch_id, [])
        )
        previous_first_by_batch[batch_id] = first_stream_value
    return values


def build_review_flag_reconciliation_report(
    db_file: Path,
) -> ReviewFlagReconciliationReport:
    """Classify review flags without changing any item or recognition record."""
    db.initialize(db_file)
    with db.connect(db_file) as connection:
        item_rows = connection.execute(
            """
            SELECT i.item_id, i.batch_id, i.sequence, i.review, i.updated_at,
                   MIN(p.stream_index) AS first_stream
            FROM items i
            LEFT JOIN photos p ON p.item_id = i.item_id AND p.kind = 'product'
            GROUP BY i.item_id
            ORDER BY i.batch_id, i.sequence
            """
        ).fetchall()
        command_rows = connection.execute(
            """
            SELECT batch_id, stream_index, command_kind
            FROM command_events
            ORDER BY batch_id, stream_index
            """
        ).fetchall()
        acceptance_rows = connection.execute(
            """
            SELECT recognition_result_id, item_id, accepted_at
            FROM recognition_results
            WHERE accepted_at IS NOT NULL
            ORDER BY recognition_result_id
            """
        ).fetchall()

    items = [dict(row) for row in item_rows]
    audited_batches = {str(row["batch_id"]) for row in command_rows}
    commands_by_batch: dict[str, list[int]] = {}
    for row in command_rows:
        if row["command_kind"] == "flag_review":
            commands_by_batch.setdefault(str(row["batch_id"]), []).append(
                int(row["stream_index"])
            )
    command_values = _command_review_values(items, commands_by_batch, audited_batches)

    acceptances_by_item: dict[str, list[tuple[int, str]]] = {}
    for row in acceptance_rows:
        acceptances_by_item.setdefault(str(row["item_id"]), []).append(
            (int(row["recognition_result_id"]), str(row["accepted_at"]))
        )

    manifests = {
        batch_id: _manifest_review_values(db_file, batch_id)
        for batch_id in {str(item["batch_id"]) for item in items}
    }
    report_rows: list[ReviewFlagReconciliationRow] = []
    for item in items:
        item_id = str(item["item_id"])
        batch_id = str(item["batch_id"])
        current_review = bool(item["review"])
        command_evidence = command_values[item_id]
        manifest_values = manifests[batch_id]
        manifest_evidence = (
            manifest_values.get(item_id) if manifest_values is not None else None
        )
        acceptances = acceptances_by_item.get(item_id, [])
        acceptance_matches_update = any(
            accepted_at == str(item["updated_at"]) for _, accepted_at in acceptances
        )
        physical_evidence = command_evidence is True or manifest_evidence is True
        reasons: list[str] = []

        if command_evidence is True:
            reasons.append("A CVHS1:FLAG:REVIEW command applies to this item")
        if manifest_evidence is True:
            reasons.append("The imported batch manifest marks this item for review")
        if acceptances:
            reasons.append(
                f"{len(acceptances)} accepted recognition result(s) are recorded"
            )
        if acceptance_matches_update:
            reasons.append(
                "An acceptance timestamp exactly matches the item's last update"
            )

        if current_review and physical_evidence:
            classification = CONFIRMED_PHYSICAL_REVIEW
        elif current_review and acceptance_matches_update:
            classification = LIKELY_RECOGNITION_DERIVED
            reasons.append("No QR or manifest review evidence was found")
        elif current_review:
            classification = AMBIGUOUS_REVIEW_FLAG
            reasons.append(
                "The flag may be manual special handling or unaudited legacy state"
            )
        elif physical_evidence:
            classification = PHYSICAL_EVIDENCE_NOT_REFLECTED
            reasons.append(
                "Physical review evidence exists but the current item flag is clear"
            )
        else:
            classification = NOT_FLAGGED
            reasons.append("No current physical review flag is set")

        report_rows.append(
            ReviewFlagReconciliationRow(
                item_id=item_id,
                batch_id=batch_id,
                current_review=current_review,
                classification=classification,
                command_review_evidence=command_evidence,
                manifest_review_evidence=manifest_evidence,
                accepted_result_ids=tuple(result_id for result_id, _ in acceptances),
                acceptance_matches_item_update=acceptance_matches_update,
                reasons=tuple(reasons),
            )
        )
    return ReviewFlagReconciliationReport(rows=tuple(report_rows))
