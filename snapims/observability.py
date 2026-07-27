from __future__ import annotations

import json
import logging
import re
import sqlite3
import subprocess
import threading
import uuid
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from snapims import __version__, db
from snapims.config import DataPaths

PROCESS_MARKER = f"{uuid.uuid4()}"
DEFAULT_EVENT_LIMIT = 20_000
MAX_QUERY_LIMIT = 2_000

_SENSITIVE_KEY = re.compile(
    r"(^|[_-])("
    r"authorization|password|passwd|secret|token|api[_-]?key|access[_-]?key|"
    r"session|cookie|csrf|client[_-]?secret|private[_-]?key|cloudflare|"
    r"tunnel[_-]?credential|guac.*password"
    r")($|[_-])",
    re.IGNORECASE,
)
_PII_KEY = re.compile(
    r"(^|[_-])("
    r"customer|email|e[_-]?mail|phone|telephone|address|postal|zip|"
    r"first[_-]?name|last[_-]?name|full[_-]?name"
    r")($|[_-])",
    re.IGNORECASE,
)
_AUTH_LINE = re.compile(
    r"(?im)^(\s*(?:authorization|proxy-authorization|cookie|set-cookie)\s*[:=]\s*).*$"
)
_ENV_SECRET = re.compile(
    r"(?im)\b("
    r"[A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API_KEY|ACCESS_KEY|"
    r"AUTHORIZATION|COOKIE|CSRF|PRIVATE_KEY|TUNNEL_CREDENTIAL)[A-Z0-9_]*"
    r")\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s;&|]+)"
)
_BEARER = re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+")
_QUERY_SECRET = re.compile(
    r"(?i)([?&](?:access_token|token|api_key|key|secret|password|session|csrf)=)"
    r"[^&#\s\"']+"
)
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE = re.compile(r"(?<!\w)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\w)")
_URL_CREDENTIALS = re.compile(
    r"(?P<scheme>[a-z][a-z0-9+.-]*://)(?P<credentials>[^/@\s]+@)",
    re.IGNORECASE,
)

_jsonl_loggers: dict[Path, logging.Logger] = {}
_jsonl_lock = threading.Lock()


class RedactingFilter(logging.Filter):
    def __init__(self, *, known_secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self.known_secrets = tuple(known_secrets)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage(), known_secrets=self.known_secrets)
        record.args = ()
        if record.exc_info and record.exc_info[1]:
            safe = safe_exception(record.exc_info[1], known_secrets=self.known_secrets)
            record.msg = (
                f"{record.msg} error_class={safe['error_class']} "
                f"safe_summary={safe['safe_summary']}"
            )
            record.exc_text = None
            record.exc_info = None
        return True


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _redact_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if not parsed.scheme or not parsed.netloc:
        return value
    hostname = parsed.hostname or ""
    if parsed.port is not None:
        hostname = f"{hostname}:{parsed.port}"
    netloc = f"[REDACTED]@{hostname}" if parsed.username is not None else hostname
    query = urlencode(
        [
            (key, "[REDACTED]" if _SENSITIVE_KEY.search(key) else item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        ]
    )
    return urlunsplit((parsed.scheme, netloc, parsed.path, query, parsed.fragment))


def redact_text(value: str, *, known_secrets: Iterable[str] = ()) -> str:
    redacted = value
    for secret in sorted(
        {secret for secret in known_secrets if secret and len(secret) >= 4},
        key=len,
        reverse=True,
    ):
        redacted = redacted.replace(secret, "[REDACTED]")
    redacted = _AUTH_LINE.sub(r"\1[REDACTED]", redacted)
    redacted = _ENV_SECRET.sub(r"\1=[REDACTED]", redacted)
    redacted = _BEARER.sub(r"\1 [REDACTED]", redacted)
    redacted = _QUERY_SECRET.sub(r"\1[REDACTED]", redacted)
    redacted = _URL_CREDENTIALS.sub(r"\g<scheme>[REDACTED]@", redacted)
    redacted = _EMAIL.sub("[REDACTED-EMAIL]", redacted)
    redacted = _PHONE.sub("[REDACTED-PHONE]", redacted)
    if redacted.startswith(("http://", "https://")):
        redacted = _redact_url(redacted)
    return redacted


def redact(value: Any, *, known_secrets: Iterable[str] = ()) -> Any:
    secrets = tuple(known_secrets)
    if isinstance(value, Mapping):
        return {
            str(key): (
                "[REDACTED]"
                if _SENSITIVE_KEY.search(str(key)) or _PII_KEY.search(str(key))
                else redact(item, known_secrets=secrets)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact(item, known_secrets=secrets) for item in value]
    if isinstance(value, Path):
        return redact_text(str(value), known_secrets=secrets)
    if isinstance(value, str):
        return redact_text(value, known_secrets=secrets)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_text(str(value), known_secrets=secrets)


def safe_exception(exc: BaseException, *, known_secrets: Iterable[str] = ()) -> dict[str, str]:
    return {
        "error_class": type(exc).__name__,
        "safe_summary": redact_text(str(exc), known_secrets=known_secrets)[:500],
    }


def _event_json_logger(path: Path) -> logging.Logger:
    resolved = path.resolve()
    with _jsonl_lock:
        existing = _jsonl_loggers.get(resolved)
        if existing is not None:
            return existing
        resolved.parent.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger(f"snapims.events.{uuid.uuid5(uuid.NAMESPACE_URL, str(resolved))}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        handler = RotatingFileHandler(
            resolved,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        resolved.chmod(0o600)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        _jsonl_loggers[resolved] = logger
        return logger


def _ensure_event_store(db_file: Path, paths: DataPaths | None) -> None:
    try:
        connection = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
        try:
            present = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='operational_events'"
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        present = None
    if not present:
        db.initialize(db_file, paths=paths)


def emit_event(
    db_file: Path,
    *,
    component: str,
    event_type: str,
    severity: str = "INFO",
    operation_id: str = "",
    parent_operation_id: str = "",
    retry_of_event_id: int | None = None,
    recovery_of_event_id: int | None = None,
    batch_id: str = "",
    item_id: str = "",
    movie_id: str = "",
    order_id: str = "",
    order_line_id: str = "",
    reservation_id: str = "",
    pick_task_id: str = "",
    provider: str = "",
    model_name: str = "",
    recognition_tier: str = "",
    attempt_number: int = 0,
    duration_ms: int = 0,
    image_count: int = 0,
    image_bytes: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    estimated_cost_cad: str = "",
    status: str = "",
    outcome: str = "",
    error_class: str = "",
    safe_summary: str = "",
    detail: Mapping[str, Any] | Sequence[Any] | None = None,
    retention_class: str = "STANDARD",
    paths: DataPaths | None = None,
    known_secrets: Iterable[str] = (),
) -> int:
    severity = severity.upper()
    retention_class = retention_class.upper()
    if severity not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError(f"Unsupported event severity: {severity}")
    if retention_class not in {"DEBUG", "STANDARD", "BUSINESS", "SECURITY"}:
        raise ValueError(f"Unsupported retention class: {retention_class}")
    _ensure_event_store(db_file, paths)
    safe_detail = redact(detail or {}, known_secrets=known_secrets)
    safe_summary = redact_text(safe_summary, known_secrets=known_secrets)[:500]
    safe_error_class = redact_text(error_class, known_secrets=known_secrets)[:120]
    fields = (
        utc_now(),
        severity,
        component[:120],
        event_type[:160],
        operation_id[:160],
        parent_operation_id[:160],
        retry_of_event_id,
        recovery_of_event_id,
        batch_id[:160],
        item_id[:160],
        movie_id[:160],
        order_id[:160],
        order_line_id[:160],
        reservation_id[:160],
        pick_task_id[:160],
        provider[:120],
        model_name[:160],
        recognition_tier[:80],
        max(0, int(attempt_number)),
        max(0, int(duration_ms)),
        max(0, int(image_count)),
        max(0, int(image_bytes)),
        max(0, int(input_tokens)),
        max(0, int(output_tokens)),
        estimated_cost_cad[:40],
        status[:120],
        outcome[:120],
        safe_error_class,
        safe_summary,
        json.dumps(safe_detail, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        PROCESS_MARKER,
        retention_class,
    )
    with db.transaction(db_file) as connection:
        cursor = connection.execute(
            """INSERT INTO operational_events(
                   occurred_at,severity,component,event_type,operation_id,
                   parent_operation_id,retry_of_event_id,recovery_of_event_id,
                   batch_id,item_id,movie_id,order_id,order_line_id,reservation_id,
                   pick_task_id,provider,model_name,recognition_tier,attempt_number,
                   duration_ms,image_count,image_bytes,input_tokens,output_tokens,
                   estimated_cost_cad,status,outcome,error_class,safe_summary,
                   detail_json,process_marker,retention_class
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            fields,
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Operational event insert did not return an event id")
        event_id = int(cursor.lastrowid)
    if paths is not None:
        record = {
            "event_id": event_id,
            "occurred_at": fields[0],
            "severity": severity,
            "component": component,
            "event_type": event_type,
            "operation_id": operation_id,
            "status": status,
            "outcome": outcome,
            "error_class": safe_error_class,
            "safe_summary": safe_summary,
            "detail": safe_detail,
            "process_marker": PROCESS_MARKER,
        }
        _event_json_logger(paths.logs / "snapims-events.jsonl").info(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
    if event_id % 100 == 0:
        prune_events(db_file)
    return event_id


def try_emit_event(
    db_file: Path,
    *,
    component: str,
    event_type: str,
    **fields: Any,
) -> int | None:
    """Record an event without allowing observability failure to break the operation."""
    try:
        return emit_event(
            db_file,
            component=component,
            event_type=event_type,
            **fields,
        )
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Operational event recording unavailable component=%s event_type=%s error_class=%s",
            component,
            event_type,
            type(exc).__name__,
        )
        return None


def query_events(
    db_file: Path,
    *,
    last: int = 100,
    since: str = "",
    errors: bool = False,
    severity: str = "",
    source: str = "",
    batch_id: str = "",
    item_id: str = "",
    order_id: str = "",
    operation_id: str = "",
    after_event_id: int = 0,
) -> list[dict[str, Any]]:
    limit = min(max(int(last), 1), MAX_QUERY_LIMIT)
    clauses = ["event_id > ?"]
    parameters: list[Any] = [max(0, int(after_event_id))]
    if since:
        clauses.append("occurred_at >= ?")
        parameters.append(since)
    if errors:
        clauses.append("severity IN ('ERROR','CRITICAL')")
    elif severity:
        clauses.append("severity = ?")
        parameters.append(severity.upper())
    for column, value in (
        ("component", source),
        ("batch_id", batch_id),
        ("item_id", item_id),
        ("order_id", order_id),
        ("operation_id", operation_id),
    ):
        if value:
            clauses.append(f"{column} = ?")
            parameters.append(value)
    parameters.append(limit)
    connection = db.connect(db_file)
    try:
        rows = connection.execute(
            f"""SELECT * FROM operational_events
                WHERE {' AND '.join(clauses)}
                ORDER BY event_id DESC LIMIT ?""",
            parameters,
        ).fetchall()
    finally:
        connection.close()
    events: list[dict[str, Any]] = []
    for row in reversed(rows):
        event = dict(row)
        try:
            event["detail"] = json.loads(str(event.pop("detail_json")))
        except (json.JSONDecodeError, TypeError):
            event["detail"] = {}
        events.append(event)
    return events


def prune_events(
    db_file: Path,
    *,
    now_at: datetime | None = None,
    maximum_events: int = DEFAULT_EVENT_LIMIT,
) -> int:
    reference = now_at or datetime.now(UTC)
    cutoffs = {
        "DEBUG": reference - timedelta(days=7),
        "STANDARD": reference - timedelta(days=90),
        "BUSINESS": reference - timedelta(days=365),
        "SECURITY": reference - timedelta(days=365),
    }
    deleted = 0
    with db.transaction(db_file) as connection:
        for retention_class, cutoff in cutoffs.items():
            cursor = connection.execute(
                "DELETE FROM operational_events WHERE retention_class=? AND occurred_at < ?",
                (
                    retention_class,
                    cutoff.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                ),
            )
            deleted += max(0, cursor.rowcount)
        cursor = connection.execute(
            """DELETE FROM operational_events
               WHERE event_id NOT IN (
                   SELECT event_id FROM operational_events
                   ORDER BY event_id DESC LIMIT ?
               )""",
            (max(100, int(maximum_events)),),
        )
        deleted += max(0, cursor.rowcount)
    return deleted


def _git_commit(project_path: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_path,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def create_support_bundle(
    paths: DataPaths,
    *,
    project_path: Path,
    destination: Path | None = None,
    health: Mapping[str, Any] | None = None,
    configured_settings: Mapping[str, Any] | None = None,
    known_secrets: Iterable[str] = (),
    event_limit: int = 1_000,
) -> Path:
    destination = destination or (
        paths.exports / f"snapims-support-{datetime.now(UTC):%Y%m%d-%H%M%S}.zip"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    connection = db.connect(paths.db_file)
    try:
        schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        schema_manifest = db.schema_manifest_report(connection)
        stored_settings = {
            str(row["key"]): str(row["value"])
            for row in connection.execute("SELECT key,value FROM settings ORDER BY key")
        }
        jobs = [
            dict(row)
            for row in connection.execute(
                """SELECT batch_id,provider,status,total,completed,recognized,failed,
                          current_item_id,started_at,updated_at,finished_at,model_name,
                          error_code,error_message,error_at,last_success_at
                   FROM recognition_jobs ORDER BY updated_at DESC LIMIT 500"""
            )
        ]
    finally:
        connection.close()
    events = query_events(paths.db_file, last=min(event_limit, MAX_QUERY_LIMIT))
    payloads = {
        "manifest.json": {
            "created_at": utc_now(),
            "snapims_version": __version__,
            "commit": _git_commit(project_path),
            "schema_version": schema_version,
            "schema_manifest": schema_manifest,
            "contents": [
                "manifest.json",
                "settings.json",
                "events.json",
                "recognition-jobs.json",
                "health.json",
            ],
            "excluded": [
                "environment variables",
                "credentials",
                "customer personal information",
                "image binaries",
            ],
        },
        "settings.json": {
            "database": redact(stored_settings, known_secrets=known_secrets),
            "configured": redact(configured_settings or {}, known_secrets=known_secrets),
        },
        "events.json": redact(events, known_secrets=known_secrets),
        "recognition-jobs.json": redact(jobs, known_secrets=known_secrets),
        "health.json": redact(health or {}, known_secrets=known_secrets),
    }
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in payloads.items():
            archive.writestr(
                name,
                json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            )
    temporary.chmod(0o600)
    temporary.replace(destination)
    destination.chmod(0o600)
    return destination
