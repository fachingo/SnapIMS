from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from snapims import db
from snapims.config import DataPaths
from snapims.observability import safe_exception, try_emit_event
from snapims.recognition.base import BaseRecognizer, RecognitionResult
from snapims.recognition.providers import recognizer_for, recognizer_registry
from snapims.runtime import is_test_provider, require_provider_allowed
from snapims.settings import ConfigurationService

_ACTIVE: dict[str, threading.Thread] = {}
_ACTIVE_REQUESTS: dict[str, threading.Thread] = {}
_PAUSED_BATCHES: set[str] = set()
_LOCK = threading.Lock()
_LEASE_SECONDS = 15 * 60


def _lease_timestamp(offset_seconds: int = 0) -> str:
    return (datetime.now().astimezone() + timedelta(seconds=offset_seconds)).isoformat(
        timespec="microseconds"
    )


def claim_item_recognition_lease(
    db_file: Path,
    item_id: str,
    *,
    owner_kind: str,
    owner_id: str,
    lease_seconds: int = _LEASE_SECONDS,
) -> bool:
    """Atomically claim one normal recognition mutation for an Item ID."""
    if owner_kind not in {"BATCH", "REQUEST"}:
        raise ValueError("Unsupported recognition lease owner")
    timestamp = _lease_timestamp()
    expires_at = _lease_timestamp(max(30, lease_seconds))
    with db.transaction(db_file) as connection:
        connection.execute(
            "DELETE FROM recognition_item_leases WHERE status='PAUSED' OR expires_at<=?",
            (timestamp,),
        )
        cursor = connection.execute(
            """INSERT OR IGNORE INTO recognition_item_leases(
                   item_id,owner_kind,owner_id,status,acquired_at,expires_at,updated_at
               ) VALUES(?,?,?,'ACTIVE',?,?,?)""",
            (item_id, owner_kind, owner_id, timestamp, expires_at, timestamp),
        )
    return cursor.rowcount == 1


def release_item_recognition_lease(
    db_file: Path, item_id: str, *, owner_kind: str, owner_id: str
) -> None:
    with db.transaction(db_file) as connection:
        connection.execute(
            "DELETE FROM recognition_item_leases WHERE item_id=? AND owner_kind=? AND owner_id=?",
            (item_id, owner_kind, owner_id),
        )


def pause_active_recognition_leases(db_file: Path) -> int:
    timestamp = _lease_timestamp()
    with db.transaction(db_file) as connection:
        cursor = connection.execute(
            """UPDATE recognition_item_leases
               SET status='PAUSED',expires_at=?,updated_at=? WHERE status='ACTIVE'""",
            (timestamp, timestamp),
        )
    return cursor.rowcount


def classify_recognition_error(exc: Exception) -> tuple[str, str]:
    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.casefold()
    normalized = lowered.replace("_", " ").replace("-", " ")
    if "api key" in normalized and ("not configured" in normalized or "missing" in normalized):
        return "API_KEY_MISSING", "OpenAI API key is not configured. Add it in Settings or the environment."
    if "authentication" in lowered or "unauthorized" in lowered or "invalid api key" in lowered:
        return "AUTHENTICATION_FAILED", "The provider rejected the configured API key."
    if "rate limit" in lowered or "429" in lowered:
        return "RATE_LIMIT", "The provider rate limit was reached. Wait and retry failed items."
    if "quota" in lowered or "billing" in lowered or "insufficient_quota" in lowered:
        return "QUOTA", "The provider quota or billing limit was reached."
    if "timeout" in lowered or "timed out" in lowered:
        return "TIMEOUT", "The provider request timed out."
    if "network" in lowered or "connection" in lowered or "name resolution" in lowered:
        return "NETWORK", "SnapIMS could not reach the recognition provider."
    if "model" in lowered and ("not found" in lowered or "unavailable" in lowered):
        return "MODEL_UNAVAILABLE", "The configured model is unavailable."
    if "server" in lowered or "502" in lowered or "503" in lowered:
        return "PROVIDER_SERVER", "The recognition provider returned a server error."
    if isinstance(exc, (KeyError, ValueError, json.JSONDecodeError)):
        return "INVALID_RESPONSE", f"Recognition data was invalid: {message}"
    return "LOCAL_FAILURE", message


def recognition_retry_after(exc: Exception) -> int | None:
    match = re.search(
        r"(?:retry[- ]after|wait)\D{0,12}(\d{1,5})",
        str(exc),
        flags=re.IGNORECASE,
    )
    return int(match.group(1)) if match else None


def recognition_image_records(
    db_file: Path,
    item_id: str,
    *,
    limit: int = 3,
    profile: str = "standard",
) -> list[tuple[dict[str, Any], Path]]:
    photos = db.get_item_photos(db_file, item_id)
    eligible = [photo for photo in photos if int(photo.get("ai_eligible", 1))]
    if profile == "front":
        limit = 1
    elif profile == "expanded":
        limit = max(limit, 4)
    elif profile not in {"standard", "recognition", "originals"}:
        raise ValueError(f"Unsupported recognition image profile: {profile}")
    # Front first, then spine/back/support. All originals remain preserved.
    eligible.sort(key=lambda photo: (int(photo.get("photo_order") or 999), int(photo["photo_id"])))
    records: list[tuple[dict[str, Any], Path]] = []
    seen_hashes: set[str] = set()
    for photo in eligible:
        digest = str(photo.get("sha256") or "")
        if digest and digest in seen_hashes:
            continue
        if digest:
            seen_hashes.add(digest)
        if profile == "originals":
            candidate = Path(photo.get("original_copy_path") or "")
        else:
            candidate = Path(photo.get("recognition_path") or photo.get("processed_path") or "")
        if candidate.is_file():
            records.append((photo, candidate))
        if len(records) >= limit:
            break
    return records


def recognition_images(
    db_file: Path, item_id: str, *, limit: int = 3, profile: str = "standard"
) -> list[Path]:
    return [
        path
        for _, path in recognition_image_records(
            db_file, item_id, limit=limit, profile=profile
        )
    ]


def _estimated_cost_cad(
    model_name: str, input_tokens: int, output_tokens: int, service: ConfigurationService
) -> float:
    try:
        table = json.loads(service.value("SNAPIMS_CAD_TOKEN_PRICE_TABLE", "{}"))
        prices = table.get(model_name, {}) if isinstance(table, dict) else {}
        input_price = float(
            prices.get("input_cad_per_million", prices.get("input_per_million", 0))
        )
        output_price = float(
            prices.get("output_cad_per_million", prices.get("output_per_million", 0))
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0.0
    return round(
        (input_tokens * input_price + output_tokens * output_price) / 1_000_000,
        8,
    )


def run_recognition(
    db_file: Path,
    item_id: str,
    recognizer: BaseRecognizer,
    *,
    tier: str = "baseline",
    trigger: str = "INITIAL",
    forced_by: str = "system",
    image_profile: str = "standard",
    request_id: str = "",
    route_reason: str = "",
) -> tuple[int, RecognitionResult]:
    item = db.get_item(db_file, item_id)
    if item is None:
        raise KeyError(f"Unknown Item ID: {item_id}")
    if tier not in {"baseline", "escalation", "frontier", "manual"}:
        raise ValueError(f"Unsupported recognition tier: {tier}")
    configuration = ConfigurationService.load_runtime()
    configured_limit = int(configuration.value("SNAPIMS_RECOGNITION_IMAGE_COUNT", "3"))
    image_records = recognition_image_records(
        db_file,
        item_id,
        limit=configured_limit,
        profile=image_profile,
    )
    images = [path for _, path in image_records]
    image_bytes = sum(path.stat().st_size for path in images if path.is_file())
    model_name = getattr(recognizer, "model_name", lambda: "")()
    operation_id = f"recognition:{item['batch_id']}"
    attempt_number = len(db.recognition_history(db_file, item_id)) + 1
    paths = DataPaths.from_root(db_file.parent.parent).ensure()
    started_at = time.monotonic()
    attempt_uuid = uuid4().hex
    prior = db.latest_recognition(db_file, item_id)
    prior_result_id = int(prior["recognition_result_id"]) if prior else None
    selected_images = [
        {
            "photo_id": int(photo["photo_id"]),
            "sha256": str(photo.get("sha256") or ""),
            "image_role": str(photo.get("image_role") or "unknown"),
            "capture_source": str(photo.get("capture_source") or "MANUAL"),
            "bytes": path.stat().st_size,
            "derivative": "original" if image_profile == "originals" else "recognition",
        }
        for photo, path in image_records
    ]
    source_kind = (
        "TEST"
        if is_test_provider(recognizer.name) or bool(item.get("is_test_copy"))
        else "LIVE"
    )
    try_emit_event(
        db_file,
        component="recognition",
        event_type="recognition.started",
        operation_id=operation_id,
        batch_id=str(item["batch_id"]),
        item_id=item_id,
        provider=recognizer.name,
        model_name=model_name,
        recognition_tier=tier,
        attempt_number=attempt_number,
        image_count=len(images),
        image_bytes=image_bytes,
        status="RUNNING",
        paths=paths,
    )
    item["approved_ai_tags"] = [
        {
            "tag_id": definition["tag_id"],
            "label": definition["canonical_label"],
            "category": definition["category"],
        }
        for definition in db.list_tag_definitions(db_file, active_only=True)
        if definition["ai_eligible"] and not definition["deterministic_only"]
    ]
    try:
        result = recognizer.recognize(item, images)
    except Exception as exc:
        latency_ms = int((time.monotonic() - started_at) * 1000)
        code, message = classify_recognition_error(exc)
        with db.transaction(db_file) as connection:
            cursor = connection.execute(
                """INSERT INTO recognition_results(
                       item_id,provider,source_kind,model_name,created_at,suggested_title,
                       confidence,uncertainty_reasons_json,requires_review,attempt_uuid,
                       tier,trigger,forced_by,prompt_version,response_schema_version,
                       image_profile,selected_images_json,contradiction_flags_json,
                       configured_price_version,latency_ms,prior_result_id,request_id,
                       route_reason,input_image_count,input_image_bytes
                   ) VALUES(?,?,?,?,?,'UNKNOWN',0,?,1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item_id,
                    recognizer.name,
                    source_kind,
                    model_name,
                    db.now(),
                    json.dumps([message]),
                    attempt_uuid,
                    tier,
                    trigger,
                    forced_by,
                    configuration.value("SNAPIMS_RECOGNITION_PROMPT_VERSION", "v1"),
                    "v1",
                    image_profile,
                    json.dumps(selected_images, sort_keys=True),
                    json.dumps(["SCHEMA_INVALID"] if code == "INVALID_RESPONSE" else [code]),
                    configuration.value("SNAPIMS_CAD_TOKEN_PRICE_VERSION", "operator-configured"),
                    latency_ms,
                    prior_result_id,
                    request_id or None,
                    route_reason or code,
                    len(images),
                    image_bytes,
                ),
            )
            failed_result_id = int(cursor.lastrowid or 0)
            connection.execute(
                """INSERT INTO recognition_attempt_states(
                       recognition_result_id,state,updated_at
                   ) VALUES(?,'FAILED',?)""",
                (failed_result_id, db.now()),
            )
            connection.execute(
                """INSERT INTO recognition_attempt_events(
                       recognition_result_id,event_type,actor,occurred_at,details_json
                   ) VALUES(?,'FAILED',?,?,?)""",
                (
                    failed_result_id,
                    forced_by,
                    db.now(),
                    json.dumps({"error_code": code, "message": message}, sort_keys=True),
                ),
            )
        raise
    latency_ms = int((time.monotonic() - started_at) * 1000)
    title = str(result.suggested_title or "").strip() or "UNKNOWN"
    configured_price_version = configuration.value(
        "SNAPIMS_CAD_TOKEN_PRICE_VERSION", "operator-configured"
    )
    estimated_cost_cad = _estimated_cost_cad(
        model_name, result.input_tokens, result.output_tokens, configuration
    )
    with db.transaction(db_file) as connection:
        cursor = connection.execute(
            """INSERT INTO recognition_results(
                   item_id,provider,source_kind,model_name,created_at,suggested_title,edition,
                   distributor,release_year,barcode_candidates_json,suggested_tag_ids_json,suggested_price_cents,
                   suggested_discount_percent,confidence,uncertainty_reasons_json,
                   raw_response_reference,pricing_source,input_tokens,output_tokens,
                   input_image_count,input_image_bytes,requires_review,attempt_uuid,tier,
                   trigger,forced_by,prompt_version,response_schema_version,image_profile,
                   selected_images_json,title_evidence_json,field_evidence_json,
                   contradiction_flags_json,configured_price_version,estimated_cost_cad,
                   latency_ms,prior_result_id,request_id,route_reason
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item_id,
                result.provider_name,
                source_kind,
                model_name,
                db.now(),
                title,
                result.edition,
                result.distributor,
                result.year,
                json.dumps(result.barcode_candidates),
                json.dumps(result.suggested_tag_ids),
                result.suggested_price_cents,
                result.suggested_discount_percent,
                result.confidence,
                json.dumps(result.uncertainty_reasons),
                result.raw_response_reference,
                result.pricing_source,
                result.input_tokens,
                result.output_tokens,
                len(images),
                image_bytes,
                int(result.requires_review),
                attempt_uuid,
                tier,
                trigger,
                forced_by,
                configuration.value("SNAPIMS_RECOGNITION_PROMPT_VERSION", "v1"),
                "v1",
                image_profile,
                json.dumps(selected_images, sort_keys=True),
                json.dumps(result.title_evidence),
                json.dumps(result.field_evidence or {}, sort_keys=True),
                json.dumps(result.contradiction_flags),
                configured_price_version,
                estimated_cost_cad,
                latency_ms,
                prior_result_id,
                request_id or None,
                route_reason,
            ),
        )
        connection.execute(
            "UPDATE items SET recognition_status='COMPLETE',recognition_error='',updated_at=? WHERE item_id=?",
            (db.now(), item_id),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return a recognition result ID")
        recognition_result_id = cursor.lastrowid
        timestamp = db.now()
        connection.execute(
            """INSERT INTO recognition_attempt_states(
                   recognition_result_id,state,updated_at
               ) VALUES(?,'UNREVIEWED',?)""",
            (recognition_result_id, timestamp),
        )
        connection.execute(
            """INSERT INTO recognition_attempt_events(
                   recognition_result_id,event_type,actor,occurred_at,details_json
               ) VALUES(?,'COMPLETED',?,?,?)""",
            (
                recognition_result_id,
                forced_by,
                timestamp,
                json.dumps({"trigger": trigger, "tier": tier}, sort_keys=True),
            ),
        )
        current = connection.execute(
            """SELECT current.recognition_result_id,states.state
               FROM item_recognition_selection current
               LEFT JOIN recognition_attempt_states states
                 ON states.recognition_result_id=current.recognition_result_id
               WHERE current.item_id=?""",
            (item_id,),
        ).fetchone()
        auto_select = current is None or (
            str(item.get("review_status") or "") != "DONE"
            and str(current["state"] or "") != "ACCEPTED"
        )
        if auto_select:
            if current is not None:
                connection.execute(
                    """UPDATE recognition_attempt_states
                       SET state='SUPERSEDED',updated_at=?
                       WHERE recognition_result_id=? AND state<>'ACCEPTED'""",
                    (timestamp, int(current["recognition_result_id"])),
                )
            connection.execute(
                """INSERT INTO item_recognition_selection(
                       item_id,recognition_result_id,selected_by,selected_at
                   ) VALUES(?,?,?,?)
                   ON CONFLICT(item_id) DO UPDATE SET
                       recognition_result_id=excluded.recognition_result_id,
                       selected_by=excluded.selected_by,selected_at=excluded.selected_at""",
                (item_id, recognition_result_id, forced_by, timestamp),
            )
            connection.execute(
                """UPDATE recognition_attempt_states
                   SET state='SELECTED',selected_at=?,selected_by=?,updated_at=?
                   WHERE recognition_result_id=?""",
                (timestamp, forced_by, timestamp, recognition_result_id),
            )
        db.record_ai_tag_suggestions_in_connection(
            connection,
            item_id,
            list(result.suggested_tag_ids),
            recognition_result_id=recognition_result_id,
        )
    # Catalog work is additive. A catalog failure must never erase or roll back
    # the committed visual recognition result. Unique local matches are linked
    # immediately; network misses continue in the restart-safe catalog worker.
    try:
        from snapims.catalog.service import queue_recognition_lookup

        queue_recognition_lookup(
            paths,
            recognition_result_id,
            start_worker=not bool(os.getenv("PYTEST_CURRENT_TEST")),
        )
    except Exception as exc:
        try:
            db.mark_item_catalog_unavailable(db_file, item_id, recognition_result_id, str(exc))
        except Exception:
            pass
    try_emit_event(
        db_file,
        component="recognition",
        event_type="recognition.completed",
        operation_id=operation_id,
        batch_id=str(item["batch_id"]),
        item_id=item_id,
        provider=result.provider_name,
        model_name=model_name,
        attempt_number=attempt_number,
        recognition_tier=tier,
        duration_ms=latency_ms,
        image_count=len(images),
        image_bytes=image_bytes,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        estimated_cost_cad=f"{estimated_cost_cad:.8f}",
        status="COMPLETE",
        outcome="REVIEW_REQUIRED" if result.requires_review else "COMPLETE",
        detail={
            "recognition_result_id": recognition_result_id,
            "confidence": result.confidence,
            "uncertainty_reason_count": len(result.uncertainty_reasons),
            "configured_price_version": configured_price_version,
            "cost_basis": "configured estimate; not provider billing truth",
            "contradiction_flags": list(result.contradiction_flags),
        },
        paths=paths,
    )
    return recognition_result_id, result


def _routing_triggers(
    result: RecognitionResult,
    configuration: ConfigurationService,
    *,
    db_file: Path | None = None,
    item_id: str = "",
) -> list[str]:
    triggers: list[str] = []
    title = str(result.suggested_title or "").strip()
    if not title:
        triggers.append("TITLE_MISSING")
    elif title.casefold() == "unknown":
        triggers.append("UNKNOWN")
    threshold = float(configuration.value("SNAPIMS_RECOGNITION_CONFIDENCE", "0.85"))
    if result.confidence < threshold:
        triggers.append("LOW_CONFIDENCE")
    triggers.extend(
        str(flag).strip().upper()
        for flag in result.contradiction_flags
        if str(flag).strip()
    )
    uncertainty = " ".join(result.uncertainty_reasons).casefold()
    if "unsupported" in uncertainty or "not vhs" in uncertainty:
        triggers.append("UNSUPPORTED_MEDIA")
    if db_file is not None and item_id:
        paths = DataPaths.from_root(db_file.parent.parent)
        try:
            with db.connect(db_file) as connection:
                link = connection.execute(
                    "SELECT movie_id,link_status FROM item_movie_links WHERE item_id=?",
                    (item_id,),
                ).fetchone()
            if link and link["movie_id"] and str(link["link_status"]) != "STALE":
                from snapims.catalog import db as catalog_db
                from snapims.catalog.normalization import normalize_title

                with catalog_db.connect(paths.catalog_db_file, readonly=True) as connection:
                    movie = connection.execute(
                        "SELECT canonical_title FROM movies WHERE movie_id=? AND active=1",
                        (link["movie_id"],),
                    ).fetchone()
                if movie and normalize_title(str(movie[0])) != normalize_title(title):
                    triggers.append("CATALOG_CONTRADICTION")
            if paths.catalog_db_file.is_file():
                from snapims.catalog import db as catalog_db

                with catalog_db.connect(paths.catalog_db_file, readonly=True) as connection:
                    ambiguous = connection.execute(
                        """SELECT 1 FROM catalog_lookup_jobs
                           WHERE item_id=? AND status='AMBIGUOUS'
                           ORDER BY job_id DESC LIMIT 1""",
                        (item_id,),
                    ).fetchone()
                if ambiguous:
                    triggers.append("SAME_TITLE_YEAR_AMBIGUITY")
        except Exception:
            # Catalog is additive; unavailable catalog evidence cannot block recognition.
            pass
    return list(dict.fromkeys(triggers))


def _tier_model(configuration: ConfigurationService, tier: str) -> str:
    keys = {
        "baseline": "SNAPIMS_OPENAI_BASELINE_MODEL",
        "escalation": "SNAPIMS_OPENAI_ESCALATION_MODEL",
        "frontier": "SNAPIMS_OPENAI_FRONTIER_MODEL",
    }
    return configuration.value(keys.get(tier, "SNAPIMS_OPENAI_BASELINE_MODEL"), "")


def route_item_recognition(
    db_file: Path,
    item_id: str,
    *,
    provider_name: str = "openai",
    model_name: str = "",
    tier: str = "baseline",
    trigger: str = "INITIAL",
    forced_by: str = "system",
    image_profile: str = "standard",
    request_id: str = "",
    allow_automatic_escalation: bool = True,
) -> list[int]:
    """Run a bounded model ladder without ever applying suggestions to working fields."""
    require_provider_allowed(provider_name)
    configuration = ConfigurationService.load_runtime()
    chosen_model = model_name or (
        _tier_model(configuration, tier) if provider_name == "openai" else ""
    )
    recognizer = recognizer_for(provider_name, model_name=chosen_model)
    available, reason = recognizer.available()
    if not available:
        raise RuntimeError(reason)
    first_id, result = run_recognition(
        db_file,
        item_id,
        recognizer,
        tier=tier,
        trigger=trigger,
        forced_by=forced_by,
        image_profile=image_profile,
        request_id=request_id,
    )
    attempt_ids = [first_id]
    triggers = _routing_triggers(
        result, configuration, db_file=db_file, item_id=item_id
    )
    maximum = int(configuration.value("SNAPIMS_RECOGNITION_MAX_ATTEMPTS", "3"))
    if (
        tier == "baseline"
        and triggers
        and allow_automatic_escalation
        and maximum >= 2
        and provider_name == "openai"
    ):
        escalation_model = _tier_model(configuration, "escalation")
        if (
            escalation_model
            and escalation_model != chosen_model
            and escalation_model in configuration.compatible_models()
        ):
            escalated = recognizer_for("openai", model_name=escalation_model)
            try:
                escalation_id, _ = run_recognition(
                    db_file,
                    item_id,
                    escalated,
                    tier="escalation",
                    trigger="+".join(triggers),
                    forced_by="system-router",
                    image_profile="expanded",
                    request_id=request_id,
                    route_reason="; ".join(triggers),
                )
            except Exception as exc:
                code, message = classify_recognition_error(exc)
                db.update_item(
                    db_file,
                    item_id,
                    {
                        "recognition_status": "COMPLETE",
                        "recognition_error": (
                            "Escalation failed; the valid baseline attempt was preserved. "
                            f"{message}"
                        ),
                    },
                    source="RECOGNITION_PARTIAL_ROUTE",
                )
                try_emit_event(
                    db_file,
                    component="recognition",
                    event_type="recognition.escalation_failed_baseline_preserved",
                    severity="WARNING",
                    item_id=item_id,
                    provider="openai",
                    model_name=escalation_model,
                    recognition_tier="escalation",
                    status="COMPLETE_WITH_WARNING",
                    outcome=code,
                    safe_summary=message,
                    detail={"baseline_result_id": first_id, "routing_triggers": triggers},
                    paths=DataPaths.from_root(db_file.parent.parent).ensure(),
                )
            else:
                attempt_ids.append(escalation_id)
    return attempt_ids


def _request_worker(db_file: Path, request_id: str) -> None:
    with db.connect(db_file) as connection:
        row = connection.execute(
            "SELECT * FROM recognition_requests WHERE request_id=?", (request_id,)
        ).fetchone()
    if row is None:
        return
    request = dict(row)
    timestamp = db.now()
    item_id = str(request["item_id"])
    if not claim_item_recognition_lease(
        db_file, item_id, owner_kind="REQUEST", owner_id=request_id
    ):
        with db.transaction(db_file) as connection:
            connection.execute(
                """UPDATE recognition_requests SET status='PAUSED',updated_at=?,
                       error_code='ITEM_BUSY',
                       error_message='Another recognition operation already owns this item.'
                   WHERE request_id=?""",
                (timestamp, request_id),
            )
        with _LOCK:
            _ACTIVE_REQUESTS.pop(request_id, None)
        return
    try:
        with db.transaction(db_file) as connection:
            connection.execute(
                """UPDATE recognition_requests
                   SET status='RUNNING',started_at=COALESCE(started_at,?),
                       updated_at=?,attempt_number=attempt_number+1
                   WHERE request_id=?""",
                (timestamp, timestamp, request_id),
            )
        attempt_ids = route_item_recognition(
            db_file,
            str(request["item_id"]),
            provider_name=str(request["provider"]),
            model_name=str(request["model_name"]),
            tier=str(request["tier"]),
            trigger=str(request["trigger"]),
            forced_by=str(request["forced_by"]),
            image_profile=str(request["image_profile"]),
            request_id=request_id,
        )
        with db.transaction(db_file) as connection:
            connection.execute(
                """UPDATE recognition_requests
                   SET status='COMPLETE',recognition_result_id=?,finished_at=?,
                       updated_at=?,error_code='',error_message=''
                   WHERE request_id=?""",
                (attempt_ids[-1], db.now(), db.now(), request_id),
            )
    except Exception as exc:
        code, message = classify_recognition_error(exc)
        retry_after = recognition_retry_after(exc)
        with db.transaction(db_file) as connection:
            failed_attempt = connection.execute(
                """SELECT recognition_result_id FROM recognition_results
                   WHERE request_id=? ORDER BY recognition_result_id DESC LIMIT 1""",
                (request_id,),
            ).fetchone()
            connection.execute(
                """UPDATE recognition_requests
                   SET status='FAILED',error_code=?,error_message=?,
                       retry_after_seconds=?,recognition_result_id=?,
                       finished_at=?,updated_at=?
                   WHERE request_id=?""",
                (
                    code,
                    message,
                    retry_after,
                    int(failed_attempt[0]) if failed_attempt else None,
                    db.now(),
                    db.now(),
                    request_id,
                ),
            )
        if not any(
            attempt["attempt_state"] != "FAILED"
            for attempt in db.recognition_history(db_file, str(request["item_id"]))
        ):
            db.update_item(
                db_file,
                str(request["item_id"]),
                {"recognition_status": "FAILED", "recognition_error": message},
                source="RECOGNITION",
            )
    finally:
        release_item_recognition_lease(
            db_file, item_id, owner_kind="REQUEST", owner_id=request_id
        )
        with _LOCK:
            _ACTIVE_REQUESTS.pop(request_id, None)


def queue_item_recognition(
    db_file: Path,
    item_id: str,
    *,
    request_id: str,
    idempotency_key: str,
    provider_name: str = "openai",
    model_name: str = "",
    tier: str = "baseline",
    trigger: str = "OPERATOR_REQUEST",
    forced_by: str = "operator",
    image_profile: str = "standard",
) -> bool:
    if not request_id or not idempotency_key:
        raise ValueError("Recognition request and idempotency IDs are required")
    item = db.get_item(db_file, item_id)
    if item is None:
        raise KeyError(f"Unknown Item ID: {item_id}")
    require_provider_allowed(provider_name)
    providers = recognizer_registry()
    if provider_name not in providers:
        raise KeyError(f"Unknown provider: {provider_name}")
    if provider_name == "openai" and model_name:
        compatible = ConfigurationService.load_runtime().compatible_models()
        if model_name not in compatible:
            raise ValueError("The selected model has not passed the image and strict-schema probe")
    timestamp = db.now()
    with db.transaction(db_file) as connection:
        cursor = connection.execute(
            """INSERT OR IGNORE INTO recognition_requests(
                   request_id,idempotency_key,item_id,batch_id,provider,model_name,
                   tier,trigger,forced_by,image_profile,status,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,'QUEUED',?,?)""",
            (
                request_id,
                idempotency_key,
                item_id,
                item["batch_id"],
                provider_name,
                model_name,
                tier,
                trigger,
                forced_by,
                image_profile,
                timestamp,
                timestamp,
            ),
        )
    if cursor.rowcount == 0:
        return False
    with _LOCK:
        thread = threading.Thread(
            target=_request_worker,
            args=(db_file, request_id),
            daemon=True,
        )
        _ACTIVE_REQUESTS[request_id] = thread
        thread.start()
    return True


def mark_interrupted_requests_paused(db_file: Path) -> int:
    with db.transaction(db_file) as connection:
        cursor = connection.execute(
            """UPDATE recognition_requests
               SET status='PAUSED',updated_at=?,error_code='APP_RESTART',
                   error_message='Attempt interrupted by application restart; safe to resume.'
               WHERE status IN ('QUEUED','RUNNING')""",
            (db.now(),),
        )
    pause_active_recognition_leases(db_file)
    return cursor.rowcount


def resume_recognition_request(db_file: Path, request_id: str) -> bool:
    with _LOCK:
        active = _ACTIVE_REQUESTS.get(request_id)
        if active and active.is_alive():
            return False
    with db.transaction(db_file) as connection:
        cursor = connection.execute(
            """UPDATE recognition_requests
               SET status='QUEUED',updated_at=?,finished_at=NULL,
                   error_code='',error_message='',retry_after_seconds=NULL
               WHERE request_id=? AND status IN ('PAUSED','FAILED')""",
            (db.now(), request_id),
        )
    if cursor.rowcount == 0:
        return False
    with _LOCK:
        thread = threading.Thread(
            target=_request_worker, args=(db_file, request_id), daemon=True
        )
        _ACTIVE_REQUESTS[request_id] = thread
        thread.start()
    return True


def _job_counts(db_file: Path, batch_id: str) -> tuple[list[dict[str, Any]], int, int]:
    items = db.list_items(db_file, batch_id=batch_id)
    recognized = sum(1 for item in items if item["recognition_status"] == "COMPLETE")
    failed = sum(1 for item in items if item["recognition_status"] == "FAILED")
    return items, recognized, failed


def _recognition_worker(
    db_file: Path,
    batch_id: str,
    provider_name: str,
    delay: float,
    rerun_all: bool = False,
    model_name: str = "",
    tier: str = "baseline",
    image_profile: str = "standard",
) -> None:
    provider = recognizer_for(provider_name, model_name=model_name)
    items, recognized, failed = _job_counts(db_file, batch_id)
    if rerun_all:
        recognized = 0
        failed = 0
    existing_job = db.get_recognition_job(db_file, batch_id) or {}
    completed_ids: set[str] = set()
    with db.connect(db_file) as connection:
        rows = connection.execute(
            """SELECT DISTINCT r.item_id FROM recognition_results r
               LEFT JOIN recognition_attempt_states s
                 ON s.recognition_result_id=r.recognition_result_id
               WHERE r.item_id IN (SELECT item_id FROM items WHERE batch_id=?)
                 AND COALESCE(s.state,'UNREVIEWED')<>'FAILED'""",
            (batch_id,),
        ).fetchall()
        completed_ids = set() if rerun_all else {str(row[0]) for row in rows}
    recognized = len(completed_ids)
    db.upsert_recognition_job(
        db_file,
        batch_id,
        provider=provider_name,
        status="IDENTIFYING",
        total=len(items),
        completed=recognized + failed,
        recognized=recognized,
        failed=failed,
        started_at=existing_job.get("started_at") or db.now(),
        finished_at=None,
        error_code="",
        error_message="",
        error_at=None,
        model_name=getattr(provider, "model_name", lambda: "")(),
    )
    paths = DataPaths.from_root(db_file.parent.parent).ensure()
    operation_id = f"recognition:{batch_id}"
    worker_started = time.monotonic()
    try_emit_event(
        db_file,
        component="recognition",
        event_type="recognition.batch_started",
        operation_id=operation_id,
        batch_id=batch_id,
        provider=provider_name,
        model_name=getattr(provider, "model_name", lambda: "")(),
        status="IDENTIFYING",
        detail={"total": len(items), "already_completed": recognized, "failed": failed},
        paths=paths,
    )
    try:
        for item in items:
            with _LOCK:
                paused = batch_id in _PAUSED_BATCHES
            if paused:
                db.upsert_recognition_job(
                    db_file,
                    batch_id,
                    status="PAUSED",
                    current_item_id="",
                    finished_at=None,
                )
                return
            if item["item_id"] in completed_ids or (
                item["recognition_status"] == "FAILED" and not rerun_all
            ):
                continue
            db.upsert_recognition_job(
                db_file,
                batch_id,
                status="IDENTIFYING",
                current_item_id=item["item_id"],
            )
            lease_owner = f"{batch_id}:{item['item_id']}"
            if not claim_item_recognition_lease(
                db_file,
                str(item["item_id"]),
                owner_kind="BATCH",
                owner_id=lease_owner,
            ):
                db.upsert_recognition_job(
                    db_file,
                    batch_id,
                    status="PAUSED",
                    error_code="ITEM_BUSY",
                    error_message="An item is already being recognized by another durable request.",
                    error_at=db.now(),
                )
                return
            try:
                route_item_recognition(
                    db_file,
                    item["item_id"],
                    provider_name=provider_name,
                    model_name=model_name,
                    tier=tier,
                    trigger="RERUN_ALL" if rerun_all else "BATCH_UNFINISHED",
                    forced_by="operator" if rerun_all else "system",
                    image_profile=image_profile,
                )
            except Exception as exc:
                code, message = classify_recognition_error(exc)
                safe = safe_exception(exc)
                history = db.recognition_history(db_file, str(item["item_id"]))
                valid_attempt = next(
                    (attempt for attempt in history if attempt["attempt_state"] != "FAILED"),
                    None,
                )
                if valid_attempt is not None:
                    recognized += 1
                    db.update_item(
                        db_file,
                        item["item_id"],
                        {
                            "recognition_status": "COMPLETE",
                            "recognition_error": (
                                "A later route failed; an earlier valid attempt was preserved. "
                                f"{message}"
                            ),
                        },
                        source="RECOGNITION_PARTIAL_ROUTE",
                    )
                    db.upsert_recognition_job(
                        db_file,
                        batch_id,
                        error_code="PARTIAL_ROUTE_FAILURE",
                        error_message=message,
                        error_at=db.now(),
                    )
                    try_emit_event(
                        db_file,
                        component="recognition",
                        event_type="recognition.partial_route_failure",
                        severity="WARNING",
                        operation_id=operation_id,
                        batch_id=batch_id,
                        item_id=str(item["item_id"]),
                        provider=provider_name,
                        model_name=getattr(provider, "model_name", lambda: "")(),
                        status="COMPLETE_WITH_WARNING",
                        outcome="PARTIAL_ROUTE_FAILURE",
                        error_class=safe["error_class"],
                        safe_summary=message,
                        detail={"preserved_result_id": valid_attempt["recognition_result_id"]},
                        paths=paths,
                    )
                else:
                    failed += 1
                    db.update_item(
                        db_file,
                        item["item_id"],
                        {"recognition_status": "FAILED", "recognition_error": message},
                        source="RECOGNITION",
                    )
                    db.upsert_recognition_job(
                        db_file,
                        batch_id,
                        error_code=code,
                        error_message=message,
                        error_at=db.now(),
                    )
                    try_emit_event(
                        db_file,
                        component="recognition",
                        event_type="recognition.failed",
                        severity="ERROR",
                        operation_id=operation_id,
                        batch_id=batch_id,
                        item_id=str(item["item_id"]),
                        provider=provider_name,
                        model_name=getattr(provider, "model_name", lambda: "")(),
                        attempt_number=len(
                            db.recognition_history(db_file, str(item["item_id"]))
                        )
                        + 1,
                        status="FAILED",
                        outcome=code,
                        error_class=safe["error_class"],
                        safe_summary=message,
                        paths=paths,
                    )
            else:
                recognized += 1
                db.upsert_recognition_job(db_file, batch_id, last_success_at=db.now())
            finally:
                release_item_recognition_lease(
                    db_file,
                    str(item["item_id"]),
                    owner_kind="BATCH",
                    owner_id=lease_owner,
                )
            completed = recognized + failed
            db.upsert_recognition_job(
                db_file,
                batch_id,
                status="IDENTIFYING",
                completed=completed,
                recognized=recognized,
                failed=failed,
                current_item_id=item["item_id"],
            )
            if delay:
                time.sleep(delay)
        if failed and not recognized:
            status = "FAILED"
        elif failed:
            status = "COMPLETE_WITH_FAILURES"
        else:
            status = "COMPLETE"
        db.upsert_recognition_job(
            db_file,
            batch_id,
            status=status,
            completed=len(items),
            recognized=recognized,
            failed=failed,
            current_item_id="",
            finished_at=db.now(),
        )
        try_emit_event(
            db_file,
            component="recognition",
            event_type="recognition.batch_completed",
            severity="WARNING" if failed else "INFO",
            operation_id=operation_id,
            batch_id=batch_id,
            provider=provider_name,
            model_name=getattr(provider, "model_name", lambda: "")(),
            duration_ms=int((time.monotonic() - worker_started) * 1000),
            status=status,
            outcome=status,
            detail={"total": len(items), "recognized": recognized, "failed": failed},
            paths=paths,
        )
    finally:
        with _LOCK:
            _ACTIVE.pop(batch_id, None)


def start_batch_recognition(
    db_file: Path,
    batch_id: str,
    provider_name: str = "openai",
    *,
    delay: float = 0,
    retry_failed: bool = False,
    rerun_all: bool = False,
    model_name: str = "",
    tier: str = "baseline",
    image_profile: str = "standard",
) -> bool:
    require_provider_allowed(provider_name)
    providers = recognizer_registry()
    if provider_name not in providers:
        raise KeyError(f"Unknown provider: {provider_name}")
    provider = recognizer_for(provider_name, model_name=model_name)
    available, reason = provider.available()
    if not available:
        code, message = classify_recognition_error(RuntimeError(reason))
        items = db.list_items(db_file, batch_id=batch_id)
        timestamp = db.now()
        with db.transaction(db_file) as connection:
            for item in items:
                if item["recognition_status"] == "COMPLETE":
                    continue
                db.update_item_in_connection(
                    connection,
                    item["item_id"],
                    {"recognition_status": "BLOCKED", "recognition_error": message},
                    source="RECOGNITION_BLOCKED",
                )
            connection.execute(
                """INSERT INTO recognition_jobs(
                       batch_id,provider,status,total,completed,recognized,failed,current_item_id,
                       started_at,updated_at,finished_at,model_name,error_code,error_message,error_at
                   ) VALUES(?,?, 'BLOCKED', ?,0,0,0,'',?,?,?,?,?,?,?)
                   ON CONFLICT(batch_id) DO UPDATE SET
                       provider=excluded.provider,status='BLOCKED',total=excluded.total,
                       completed=0,recognized=0,failed=0,current_item_id='',
                       updated_at=excluded.updated_at,finished_at=excluded.finished_at,
                       model_name=excluded.model_name,error_code=excluded.error_code,
                       error_message=excluded.error_message,error_at=excluded.error_at""",
                (
                    batch_id,
                    provider_name,
                    len(items),
                    timestamp,
                    timestamp,
                    timestamp,
                    getattr(provider, "model_name", lambda: "")(),
                    code,
                    message,
                    timestamp,
                ),
            )
        try_emit_event(
            db_file,
            component="recognition",
            event_type="recognition.blocked",
            severity="ERROR",
            operation_id=f"recognition:{batch_id}",
            batch_id=batch_id,
            provider=provider_name,
            model_name=getattr(provider, "model_name", lambda: "")(),
            status="BLOCKED",
            outcome=code,
            error_class=code,
            safe_summary=message,
            paths=DataPaths.from_root(db_file.parent.parent).ensure(),
        )
        return False

    retryable = {"FAILED"} if retry_failed else {"FAILED", "BLOCKED", "SKIPPED"}
    candidates = [
        item for item in db.list_items(db_file, batch_id=batch_id)
        if item["recognition_status"] in retryable
    ]
    if candidates:
        with db.transaction(db_file) as connection:
            for item in candidates:
                db.update_item_in_connection(
                    connection,
                    item["item_id"],
                    {"recognition_status": "PENDING", "recognition_error": ""},
                    source="SYSTEM_RECOVERY",
                )

    with _LOCK:
        _PAUSED_BATCHES.discard(batch_id)
        existing = _ACTIVE.get(batch_id)
        if existing and existing.is_alive():
            try_emit_event(
                db_file,
                component="recognition",
                event_type="recognition.duplicate_queue_ignored",
                severity="WARNING",
                operation_id=f"recognition:{batch_id}",
                batch_id=batch_id,
                provider=provider_name,
                status="ALREADY_RUNNING",
                paths=DataPaths.from_root(db_file.parent.parent).ensure(),
            )
            return False
        items, recognized, failed = _job_counts(db_file, batch_id)
        prior = db.get_recognition_job(db_file, batch_id) or {}
        db.upsert_recognition_job(
            db_file,
            batch_id,
            provider=provider_name,
            status="IDENTIFYING",
            total=len(items),
            completed=recognized + failed,
            recognized=recognized,
            failed=failed,
            current_item_id="",
            started_at=prior.get("started_at") or db.now(),
            finished_at=None,
            error_code="",
            error_message="",
            error_at=None,
            model_name=getattr(provider, "model_name", lambda: "")(),
        )
        thread = threading.Thread(
            target=_recognition_worker,
            args=(
                db_file,
                batch_id,
                provider_name,
                delay,
                rerun_all,
                model_name,
                tier,
                image_profile,
            ),
            daemon=True,
        )
        _ACTIVE[batch_id] = thread
        thread.start()
    try_emit_event(
        db_file,
        component="recognition",
        event_type="recognition.retried" if retry_failed else "recognition.queued",
        operation_id=f"recognition:{batch_id}",
        batch_id=batch_id,
        provider=provider_name,
        model_name=getattr(provider, "model_name", lambda: "")(),
        status="QUEUED",
        detail={"total": len(items), "retry_candidates": len(candidates)},
        paths=DataPaths.from_root(db_file.parent.parent).ensure(),
    )
    return True


def pause_batch_recognition(db_file: Path, batch_id: str) -> bool:
    with _LOCK:
        thread = _ACTIVE.get(batch_id)
        if thread is None or not thread.is_alive():
            return False
        _PAUSED_BATCHES.add(batch_id)
    db.upsert_recognition_job(db_file, batch_id, status="PAUSING")
    return True


def retry_failed_item(
    db_file: Path, item_id: str, provider_name: str = "openai"
) -> bool:
    """Queue the durable Phase-4 routed retry and return immediately."""
    request_id = uuid4().hex
    return queue_item_recognition(
        db_file,
        item_id,
        request_id=request_id,
        idempotency_key=f"retry:{item_id}:{request_id}",
        provider_name=provider_name,
        trigger="FAILED_ITEM_RETRY",
        forced_by="operator",
        image_profile="standard",
    )


def skip_batch_recognition(db_file: Path, batch_id: str) -> None:
    items = db.list_items(db_file, batch_id=batch_id)
    timestamp = db.now()
    with db.transaction(db_file) as connection:
        for item in items:
            if item["recognition_status"] == "COMPLETE":
                continue
            db.update_item_in_connection(
                connection,
                item["item_id"],
                {"recognition_status": "SKIPPED", "recognition_error": ""},
                source="SYSTEM_RECOVERY",
                reason="Recognition skipped by operator",
            )
        connection.execute(
            """INSERT INTO recognition_jobs(
                   batch_id,provider,status,total,completed,recognized,failed,current_item_id,
                   started_at,updated_at,finished_at,error_code,error_message,error_at
               ) VALUES(?, '', 'SKIPPED', ?,0,0,0,'',?,?,?,?,?,?)
               ON CONFLICT(batch_id) DO UPDATE SET
                   status='SKIPPED',current_item_id='',updated_at=excluded.updated_at,
                   finished_at=excluded.finished_at,error_code=excluded.error_code,
                   error_message=excluded.error_message,error_at=excluded.error_at""",
            (
                batch_id,
                len(items),
                timestamp,
                timestamp,
                timestamp,
                "SKIPPED_BY_OPERATOR",
                "Recognition was skipped. Items remain unfinished for manual review.",
                timestamp,
            ),
        )


def _accept_values(
    item: dict[str, Any],
    suggestion: dict[str, Any] | None,
    *,
    price_cents: int | None,
    discount_percent: float,
    review_source: str,
    title_override: str | None = None,
    tag_ids: list[str] | None = None,
    replace_approved: bool = False,
) -> dict[str, Any]:
    candidates = json.loads(suggestion["barcode_candidates_json"]) if suggestion else []
    provider = suggestion["provider"] if suggestion else item.get("recognition_provider", "")
    confidence = suggestion["confidence"] if suggestion else item.get("recognition_confidence")
    values: dict[str, Any] = {
        "title": str(
            title_override
            or (
                suggestion["suggested_title"]
                if replace_approved and suggestion
                else item.get("title") or (suggestion["suggested_title"] if suggestion else "")
            )
        ).strip(),
        "release_year": (
            suggestion["release_year"]
            if replace_approved and suggestion
            else item.get("release_year") or (suggestion["release_year"] if suggestion else None)
        ),
        "edition": (
            suggestion["edition"]
            if replace_approved and suggestion
            else item.get("edition") or (suggestion["edition"] if suggestion else "")
        ),
        "distributor": (
            suggestion["distributor"]
            if replace_approved and suggestion
            else item.get("distributor") or (suggestion["distributor"] if suggestion else "")
        ),
        "barcode": (
            (candidates[0] if candidates else "")
            if replace_approved and suggestion
            else item.get("barcode") or (candidates[0] if candidates else "")
        ),
        "price_cents": (
            price_cents
            if price_cents is not None
            else (
                suggestion["suggested_price_cents"]
                if replace_approved and suggestion
                else item.get("price_cents") or (suggestion["suggested_price_cents"] if suggestion else None)
            )
        ),
        "discount_percent": discount_percent,
        "recognition_provider": provider,
        "recognition_confidence": confidence,
        "ready": 1,
        "review_status": "DONE",
        "postponed_at": None,
        "validation_status": "READY",
        "validation_errors": "[]",
        "review_source": review_source,
        "working_source": review_source,
    }
    if bool(item.get("is_test_copy")) or not bool(item.get("publish_eligible", 1)):
        values.update(
            ready=0,
            validation_status="BLOCKED",
            validation_errors=json.dumps(
                ["Isolated test copy is permanently quarantined from sale and Shopify."]
            ),
        )
    if str(values["title"]).strip().casefold() == "unknown":
        values.update(
            ready=0,
            review_status="UNFINISHED",
            validation_status="BLOCKED",
            validation_errors=json.dumps(
                ["Recognition returned UNKNOWN; operator resolution is required before sale."]
            ),
        )
    if tag_ids is not None:
        values["tag_ids"] = tag_ids
        values["_tag_source"] = "OPERATOR_REVIEW"
    return values


def accept_item_in_connection(
    connection: Any,
    db_file: Path,
    item: dict[str, Any],
    suggestion: dict[str, Any] | None,
    *,
    price_cents: int | None,
    discount_percent: float,
    review_source: str,
    title_override: str | None = None,
    tag_ids: list[str] | None = None,
    replace_approved: bool = False,
) -> None:
    values = _accept_values(
        item,
        suggestion,
        price_cents=price_cents,
        discount_percent=discount_percent,
        review_source=review_source,
        title_override=title_override,
        tag_ids=tag_ids,
        replace_approved=replace_approved,
    )
    db.update_item_in_connection(
        connection,
        item["item_id"],
        values,
        source="AI_ACCEPTED" if suggestion else review_source,
        reason=f"Review completed through {review_source}",
    )
    if suggestion:
        timestamp = db.now()
        superseded = connection.execute(
            """SELECT states.recognition_result_id
               FROM recognition_attempt_states states
               JOIN recognition_results results
                 ON results.recognition_result_id=states.recognition_result_id
               WHERE results.item_id=? AND states.state='ACCEPTED'
                 AND states.recognition_result_id<>?""",
            (item["item_id"], suggestion["recognition_result_id"]),
        ).fetchall()
        for prior in superseded:
            connection.execute(
                """UPDATE recognition_attempt_states
                   SET state='SUPERSEDED',updated_at=?
                   WHERE recognition_result_id=?""",
                (timestamp, int(prior[0])),
            )
            connection.execute(
                """INSERT INTO recognition_attempt_events(
                       recognition_result_id,event_type,actor,occurred_at,details_json
                   ) VALUES(?,'SUPERSEDED',?,?,?)""",
                (
                    int(prior[0]),
                    review_source,
                    timestamp,
                    json.dumps(
                        {
                            "superseded_by": suggestion["recognition_result_id"],
                        },
                        sort_keys=True,
                    ),
                ),
            )
        connection.execute(
            """INSERT INTO recognition_attempt_states(
                   recognition_result_id,state,accepted_at,accepted_by,updated_at
               ) VALUES(?,'ACCEPTED',?,?,?)
               ON CONFLICT(recognition_result_id) DO UPDATE SET
                   state='ACCEPTED',accepted_at=excluded.accepted_at,
                   accepted_by=excluded.accepted_by,updated_at=excluded.updated_at""",
            (
                suggestion["recognition_result_id"],
                timestamp,
                review_source,
                timestamp,
            ),
        )
        connection.execute(
            """INSERT INTO recognition_attempt_events(
                   recognition_result_id,event_type,actor,occurred_at,details_json
               ) VALUES(?,'ACCEPTED',?,?,'{}')""",
            (suggestion["recognition_result_id"], review_source, timestamp),
        )
    unfinished = int(
        connection.execute(
            "SELECT COUNT(*) FROM items WHERE batch_id=? AND review_status='UNFINISHED'",
            (item["batch_id"],),
        ).fetchone()[0]
    )
    if unfinished == 0:
        connection.execute(
            "UPDATE recognition_jobs SET status='REVIEW_COMPLETE',updated_at=?,finished_at=COALESCE(finished_at,?) "
            "WHERE batch_id=?",
            (db.now(), db.now(), item["batch_id"]),
        )


def accept_item(
    db_file: Path,
    item_id: str,
    *,
    price_cents: int | None,
    discount_percent: float,
    review_source: str = "AI_ACCEPTED",
    title_override: str | None = None,
    tag_ids: list[str] | None = None,
    replace_approved: bool = False,
    expected_revision: int | None = None,
) -> list[str]:
    item = db.get_item(db_file, item_id)
    if item is None:
        raise KeyError(f"Unknown Item ID: {item_id}")
    suggestion = db.selected_recognition(db_file, item_id) or db.latest_recognition(db_file, item_id)
    values = _accept_values(
        item,
        suggestion,
        price_cents=price_cents,
        discount_percent=discount_percent,
        review_source=review_source,
        title_override=title_override,
        tag_ids=tag_ids,
        replace_approved=replace_approved,
    )
    candidate = {**item, **values}
    errors = validate_items_for_candidate(db_file, candidate)
    if errors:
        return errors
    with db.transaction(db_file) as connection:
        current = connection.execute("SELECT * FROM items WHERE item_id=?", (item_id,)).fetchone()
        if current is None:
            raise KeyError(f"Unknown Item ID: {item_id}")
        current_item = dict(current)
        if (
            expected_revision is not None
            and int(current_item["record_revision"]) != expected_revision
        ):
            raise RuntimeError("This item changed in another session. Reload before saving.")
        accept_item_in_connection(
            connection,
            db_file,
            current_item,
            suggestion,
            price_cents=price_cents,
            discount_percent=discount_percent,
            review_source=review_source,
            title_override=title_override,
            tag_ids=tag_ids,
            replace_approved=replace_approved,
        )
    return []


def validate_items_for_candidate(db_file: Path, candidate: dict[str, Any]) -> list[str]:
    from snapims.inventory import validation_errors

    return validation_errors(candidate, db.get_item_photos(db_file, candidate["item_id"]))


def postpone_item(db_file: Path, item_id: str) -> None:
    db.update_item(
        db_file,
        item_id,
        {"review_status": "UNFINISHED", "postponed_at": db.now()},
        source="REVIEW",
    )
