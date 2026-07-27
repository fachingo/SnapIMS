from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient

from snapims import db
from snapims.config import ShopifyConfig
from snapims.demo import create_demo_batch
from snapims.processor import create_isolated_test_copy, process_batch
from snapims.recognition.base import BaseRecognizer, RecognitionResult
from snapims.recognition.service import (
    accept_item,
    mark_interrupted_requests_paused,
    queue_item_recognition,
    run_recognition,
)
from snapims.shopify.service import ShopifyService
from snapims.web.app import app


class EvidenceRecognizer(BaseRecognizer):
    name = "evidence"

    def __init__(
        self,
        title: str,
        *,
        input_tokens: int = 1000,
        output_tokens: int = 500,
    ) -> None:
        self.title = title
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def model_name(self) -> str:
        return "evidence-v1"

    def recognize(self, item, images):
        return RecognitionResult(
            suggested_title=self.title,
            confidence=0.92 if self.title != "UNKNOWN" else 0.1,
            provider_name=self.name,
            title_evidence=("Front title block",),
            field_evidence={"year": [], "edition": [], "distributor": [], "barcode": []},
            uncertainty_reasons=("Insufficient title evidence",)
            if self.title == "UNKNOWN"
            else (),
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )


def _one_item(tmp_path: Path, data_paths):
    result = process_batch(
        create_demo_batch(tmp_path / "camera", item_count=1), paths=data_paths
    )
    return result, db.list_items(data_paths.db_file, batch_id=result.batch_id)[0]


def test_capture_source_contract_and_attempt_payload_are_immutable(
    tmp_path: Path, data_paths
) -> None:
    result, item = _one_item(tmp_path, data_paths)
    result_id, _ = run_recognition(
        data_paths.db_file,
        item["item_id"],
        EvidenceRecognizer("Evidence Title"),
        tier="baseline",
        trigger="INITIAL",
        image_profile="standard",
    )
    with db.connect(data_paths.db_file) as connection:
        batch = connection.execute(
            "SELECT capture_source FROM batches WHERE batch_id=?", (result.batch_id,)
        ).fetchone()
        sources = {
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT capture_source FROM photos WHERE batch_id=?",
                (result.batch_id,),
            )
        }
        attempt = connection.execute(
            "SELECT * FROM recognition_results WHERE recognition_result_id=?",
            (result_id,),
        ).fetchone()
        assert batch[0] == "DESKTOP_IMPORT_QR"
        assert sources == {"DESKTOP_IMPORT_QR"}
        assert attempt["attempt_uuid"]
        assert json.loads(attempt["selected_images_json"])[0]["capture_source"] == "DESKTOP_IMPORT_QR"
        try:
            connection.execute(
                "UPDATE recognition_results SET suggested_title='changed' WHERE recognition_result_id=?",
                (result_id,),
            )
        except sqlite3.IntegrityError as exc:
            assert "immutable" in str(exc)
        else:
            raise AssertionError("Recognition evidence update unexpectedly succeeded")
    assert {
        "DESKTOP_IMPORT_QR",
        "DESKTOP_IMPORT_MANUAL",
        "ANDROID_BUTTON",
        "ANDROID_QR",
        "ANDROID_OFFLINE_SYNC",
        "MANUAL",
        "TEST",
    }.issubset(db.CAPTURE_SOURCES)


def test_successful_item_can_rerun_idempotently_without_overwriting_approval(
    tmp_path: Path, data_paths
) -> None:
    _, item = _one_item(tmp_path, data_paths)
    run_recognition(data_paths.db_file, item["item_id"], EvidenceRecognizer("First"))
    assert accept_item(
        data_paths.db_file,
        item["item_id"],
        price_cents=999,
        discount_percent=0,
    ) == []
    request_id = "same-browser-request"
    assert queue_item_recognition(
        data_paths.db_file,
        item["item_id"],
        request_id=request_id,
        idempotency_key=request_id,
        provider_name="mock",
    )
    assert not queue_item_recognition(
        data_paths.db_file,
        item["item_id"],
        request_id=request_id,
        idempotency_key=request_id,
        provider_name="mock",
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with db.connect(data_paths.db_file) as connection:
            state = connection.execute(
                "SELECT status FROM recognition_requests WHERE request_id=?",
                (request_id,),
            ).fetchone()[0]
        if state == "COMPLETE":
            break
        time.sleep(0.01)
    assert state == "COMPLETE"
    assert len(db.recognition_history(data_paths.db_file, item["item_id"])) == 2
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert saved["title"] == "First"
    assert saved["review_status"] == "DONE"


def test_older_attempt_can_be_selected_and_explicitly_reaccepted(
    tmp_path: Path, data_paths
) -> None:
    _, item = _one_item(tmp_path, data_paths)
    first_id, _ = run_recognition(
        data_paths.db_file, item["item_id"], EvidenceRecognizer("First")
    )
    second_id, _ = run_recognition(
        data_paths.db_file, item["item_id"], EvidenceRecognizer("Second")
    )
    db.select_recognition_attempt(data_paths.db_file, item["item_id"], first_id)
    assert accept_item(
        data_paths.db_file,
        item["item_id"],
        price_cents=999,
        discount_percent=0,
        replace_approved=True,
    ) == []
    assert db.get_item(data_paths.db_file, item["item_id"])["title"] == "First"
    history = db.recognition_history(data_paths.db_file, item["item_id"])
    assert {row["recognition_result_id"] for row in history} == {first_id, second_id}
    assert next(row for row in history if row["recognition_result_id"] == first_id)[
        "attempt_state"
    ] == "ACCEPTED"


def test_unknown_is_preserved_as_valid_non_saleable_attempt(
    tmp_path: Path, data_paths
) -> None:
    _, item = _one_item(tmp_path, data_paths)
    result_id, _ = run_recognition(
        data_paths.db_file, item["item_id"], EvidenceRecognizer("UNKNOWN")
    )
    attempt = db.latest_recognition(data_paths.db_file, item["item_id"])
    assert attempt["recognition_result_id"] == result_id
    assert attempt["suggested_title"] == "UNKNOWN"
    assert accept_item(
        data_paths.db_file,
        item["item_id"],
        price_cents=999,
        discount_percent=0,
        replace_approved=True,
    ) == []
    saved = db.get_item(data_paths.db_file, item["item_id"])
    assert saved["ready"] == 0
    assert saved["review_status"] == "UNFINISHED"
    assert "UNKNOWN" in saved["validation_errors"]


def test_isolated_test_copy_has_separate_identity_and_permanent_quarantine(
    tmp_path: Path, data_paths
) -> None:
    original, original_item = _one_item(tmp_path, data_paths)
    copied = create_isolated_test_copy(data_paths, original.batch_id)
    copy_batch = db.get_batch(data_paths.db_file, copied.batch_id)
    copy_item = db.list_items(data_paths.db_file, batch_id=copied.batch_id)[0]
    assert copy_batch["source_batch_id"] == original.batch_id
    assert copy_batch["capture_source"] == "TEST"
    assert copy_batch["is_test_copy"] == 1
    assert copy_batch["publish_eligible"] == 0
    assert copy_batch["reservation_eligible"] == 0
    assert copy_item["item_id"] != original_item["item_id"]
    assert {
        photo["sha256"] for photo in db.get_item_photos(data_paths.db_file, copy_item["item_id"])
    } == {
        photo["sha256"] for photo in db.get_item_photos(data_paths.db_file, original_item["item_id"])
    }
    report = ShopifyService(data_paths.db_file, ShopifyConfig.from_env()).dry_run(
        copy_item["item_id"]
    )
    assert not report.ready
    assert any("quarantined" in error for error in report.errors)
    try:
        db.update_item(
            data_paths.db_file,
            copy_item["item_id"],
            {"ready": 1},
            source="TEST",
        )
    except sqlite3.IntegrityError as exc:
        assert "cannot become saleable" in str(exc)
    else:
        raise AssertionError("Quarantined test copy unexpectedly became ready")


def test_cost_metadata_uses_configured_table_not_billing_truth(
    tmp_path: Path, data_paths
) -> None:
    _, item = _one_item(tmp_path, data_paths)
    with db.transaction(data_paths.db_file) as connection:
        connection.execute(
            "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?)",
            (
                "configuration.SNAPIMS_CAD_TOKEN_PRICE_TABLE",
                json.dumps(
                    {
                        "evidence-v1": {
                            "input_cad_per_million": 2,
                            "output_cad_per_million": 4,
                        }
                    }
                ),
                db.now(),
            ),
        )
        connection.execute(
            "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?)",
            (
                "configuration.SNAPIMS_CAD_TOKEN_PRICE_VERSION",
                "owner-2026-07-27",
                db.now(),
            ),
        )
    run_recognition(
        data_paths.db_file,
        item["item_id"],
        EvidenceRecognizer("Costed", input_tokens=1000, output_tokens=500),
    )
    attempt = db.latest_recognition(data_paths.db_file, item["item_id"])
    assert attempt["configured_price_version"] == "owner-2026-07-27"
    assert attempt["estimated_cost_cad"] == 0.004


def test_restart_pauses_durable_requests_and_workspace_exposes_controls(
    tmp_path: Path, data_paths
) -> None:
    result, item = _one_item(tmp_path, data_paths)
    with db.transaction(data_paths.db_file) as connection:
        connection.execute(
            """INSERT INTO recognition_requests(
                   request_id,idempotency_key,item_id,batch_id,provider,status,
                   created_at,updated_at
               ) VALUES('interrupted','interrupted',?,?,'mock','RUNNING',?,?)""",
            (item["item_id"], result.batch_id, db.now(), db.now()),
        )
    assert mark_interrupted_requests_paused(data_paths.db_file) == 1
    with TestClient(app) as client:
        page = client.get(f"/recognition?batch_id={result.batch_id}")
        duplicate = client.post(
            "/import/preview",
            data={"source_folder": str(tmp_path / "camera")},
        )
    assert page.status_code == 200
    assert "Force Rerun All" in page.text
    assert "CONFIGURED LADDER" in page.text
    assert "not provider billing truth" in page.text
    assert "Open Existing Batch" in duplicate.text
    assert "Rerun Unfinished" in duplicate.text
    assert "Rerun All" in duplicate.text
    assert "Isolated Test Copy" in duplicate.text
    assert ">Cancel<" in duplicate.text
