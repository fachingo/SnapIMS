from __future__ import annotations

from contextlib import asynccontextmanager
import hashlib
import json
import hmac
import logging
from logging.handlers import RotatingFileHandler
import mimetypes
import os
from pathlib import Path
import secrets
import threading
import time
from typing import Any
from urllib.parse import parse_qs, quote, urlparse
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from snapims import __version__, db
from snapims.config import DataPaths, ShopifyConfig
from snapims.catalog import db as catalog_db
from snapims.catalog.admin import reconcile_maintenance_jobs
from snapims.catalog.service import (
    get_catalog_status,
    latest_job as latest_catalog_job,
    queue_operator_title_correction,
    recover_catalog_jobs,
    reconcile_pending_links,
    search_local,
    select_candidate,
    start_catalog_job,
)
from snapims.bulk import apply_bulk_operation
from snapims.money import parse_discount_percent, parse_price_cents
from snapims.observability import (
    RedactingFilter,
    create_support_bundle,
    query_events,
    redact,
    redact_text,
    safe_exception,
    try_emit_event,
)
from snapims.folder_picker import FolderPickerUnavailable, choose_folder
from snapims.inventory import (
    CONDITIONS,
    POOL_MODES,
    CSVImportError,
    apply_staged_csv,
    export_inventory_csv,
    mark_batch_externally_reviewed,
    preview_inventory_csv,
    validate_items,
    validation_errors,
)
from snapims.pipeline import parse_batch
from snapims.processor import process_batch, reconcile_import_journals
from snapims.recognition.providers import recognizer_registry
from snapims.recognition.service import (
    accept_item,
    postpone_item,
    retry_failed_item,
    skip_batch_recognition,
    start_batch_recognition,
)
from snapims.shopify.service import ShopifyService
from snapims.runtime import test_providers_enabled
from snapims.auth import (
    COOKIE,
    authentication_enabled,
    authentication_problem,
    issue_session,
    read_session_claims,
    verify_password,
)
from snapims.config import SnapIMSConfig

PACKAGE_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = PACKAGE_ROOT / "static"
TEMPLATES = Jinja2Templates(directory=str(PACKAGE_ROOT / "templates"))
LOGGER = logging.getLogger(__name__)
CSRF_COOKIE = "snapims_csrf"
STATE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_LOGIN_FAILURES: dict[str, tuple[int, float, float]] = {}
_LOGIN_LOCK = threading.Lock()
_LOGIN_MAX_RECORDS = 10_000


def _configured_secrets() -> tuple[str, ...]:
    config = SnapIMSConfig.load()
    shopify = ShopifyConfig.from_env()
    return tuple(
        value
        for value in (
            config.auth_secret,
            config.admin_password_hash,
            config.openai_api_key,
            shopify.access_token,
        )
        if value
    )


def _identity_marker(identity: str) -> str:
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def _event(component: str, event_type: str, **fields: Any) -> int | None:
    paths = DataPaths.from_root().ensure()
    return try_emit_event(
        paths.db_file,
        component=component,
        event_type=event_type,
        paths=paths,
        known_secrets=_configured_secrets(),
        **fields,
    )


def _client_identity(request: Request, username: str = "") -> str:
    forwarded = request.headers.get("cf-connecting-ip") or request.headers.get(
        "x-forwarded-for", ""
    ).split(",", 1)[0]
    address = forwarded.strip() or (request.client.host if request.client else "unknown")
    return f"{address.casefold()}|{username.strip().casefold()}"


def _login_retry_after(identity: str) -> int:
    now_value = time.monotonic()
    with _LOGIN_LOCK:
        record = _LOGIN_FAILURES.get(identity)
        if not record:
            return 0
        _, blocked_until, _ = record
        return max(0, int(blocked_until - now_value + 0.999))


def _record_login_failure(identity: str) -> int:
    now_value = time.monotonic()
    with _LOGIN_LOCK:
        if len(_LOGIN_FAILURES) >= _LOGIN_MAX_RECORDS:
            oldest = sorted(_LOGIN_FAILURES, key=lambda key: _LOGIN_FAILURES[key][2])
            for key in oldest[: max(1, len(oldest) // 10)]:
                _LOGIN_FAILURES.pop(key, None)
        failures, _, _ = _LOGIN_FAILURES.get(identity, (0, 0.0, now_value))
        failures += 1
        delay = 0 if failures < 3 else min(60, 2 ** (failures - 3))
        _LOGIN_FAILURES[identity] = (failures, now_value + delay, now_value)
        return delay


def _clear_login_failures(identity: str) -> None:
    with _LOGIN_LOCK:
        _LOGIN_FAILURES.pop(identity, None)


def _new_csrf() -> str:
    return secrets.token_urlsafe(32)


def _origin_allowed(request: Request, config: SnapIMSConfig) -> bool:
    host = request.headers.get("host", "").split(":", 1)[0].strip().casefold()
    if host not in config.allowed_hosts:
        return False
    origin = request.headers.get("origin")
    if not origin:
        return True
    parsed = urlparse(origin)
    if not parsed.hostname or parsed.hostname.casefold() not in config.allowed_hosts:
        return False
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    expected_scheme = forwarded_proto or request.url.scheme
    return parsed.scheme == expected_scheme


async def _submitted_csrf(request: Request) -> str:
    header = request.headers.get("x-csrf-token", "")
    if header:
        return header
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/x-www-form-urlencoded"):
        text_body = (await request.body()).decode("utf-8", errors="replace")
        return parse_qs(text_body, keep_blank_values=True).get("csrf_token", [""])[0]
    if content_type.startswith("multipart/form-data"):
        raw_body = await request.body()
        marker = b'name="csrf_token"'
        position = raw_body.find(marker)
        if position >= 0:
            value_start = raw_body.find(b"\r\n\r\n", position)
            if value_start >= 0:
                value_end = raw_body.find(b"\r\n", value_start + 4)
                if value_end >= 0:
                    return raw_body[value_start + 4 : value_end].decode(
                        "utf-8", errors="replace"
                    )
    return ""


def _security_headers(response: Any, path: str) -> None:
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; "
        "form-action 'self'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-Frame-Options"] = "DENY"
    if path in {"/login", "/settings"} or path.startswith("/settings/"):
        response.headers["Cache-Control"] = "no-store"


@asynccontextmanager
async def lifespan(app: FastAPI):
    paths = get_paths()
    paths.logs.mkdir(parents=True, exist_ok=True)
    snapims_logger = logging.getLogger("snapims")
    target_log = (paths.logs / "snapims.log").resolve()
    for existing_handler in list(snapims_logger.handlers):
        if (
            isinstance(existing_handler, RotatingFileHandler)
            and Path(existing_handler.baseFilename).resolve() != target_log
        ):
            snapims_logger.removeHandler(existing_handler)
            existing_handler.close()
    if not any(
        isinstance(existing_handler, RotatingFileHandler)
        and Path(existing_handler.baseFilename).resolve() == target_log
        for existing_handler in snapims_logger.handlers
    ):
        handler = RotatingFileHandler(target_log, maxBytes=5_000_000, backupCount=5)
        target_log.chmod(0o600)
        handler.addFilter(RedactingFilter(known_secrets=_configured_secrets()))
        snapims_logger.addHandler(handler)
        snapims_logger.setLevel(logging.INFO)
    LOGGER.info("SnapIMS %s starting", __version__)
    db.initialize(paths.db_file, paths=paths)
    import_recovery = reconcile_import_journals(paths)
    paused_jobs = db.mark_interrupted_jobs_paused(paths.db_file)
    expired_csv = db.cleanup_csv_staging(paths.db_file)
    pruned_checkpoints = db.prune_batch_checkpoints(paths.db_file)
    _event(
        "app",
        "application.started",
        status="RUNNING",
        outcome="STARTED",
        detail={
            "version": __version__,
            "schema_version": db.SCHEMA_VERSION,
            "import_recovery": import_recovery,
            "paused_recognition_jobs": paused_jobs,
            "expired_csv_stages": expired_csv,
            "pruned_checkpoints": pruned_checkpoints,
        },
        retention_class="BUSINESS",
    )
    app.state.catalog_error = ""
    try:
        catalog_db.initialize(paths.catalog_db_file, paths=paths)
        reconcile_pending_links(paths)
        reconcile_maintenance_jobs(paths)
        recover_catalog_jobs(paths, start_workers=not bool(os.getenv("PYTEST_CURRENT_TEST")))
    except Exception as exc:
        app.state.catalog_error = str(exc)
        LOGGER.exception("Movie catalog startup failed; inventory remains available")
        safe = safe_exception(exc, known_secrets=_configured_secrets())
        _event(
            "catalog",
            "catalog.startup_failed",
            severity="ERROR",
            status="DEGRADED",
            outcome="CATALOG_UNAVAILABLE",
            error_class=safe["error_class"],
            safe_summary=safe["safe_summary"],
        )
    try:
        yield
    finally:
        _event(
            "app",
            "application.stopped",
            status="STOPPED",
            outcome="SHUTDOWN",
            retention_class="BUSINESS",
        )
        LOGGER.info("SnapIMS shutting down")


app = FastAPI(title="SnapIMS", version=__version__, lifespan=lifespan)


async def stream_file(path: Path, chunk_size: int = 1024 * 128):
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            yield chunk


def safe_file_response(
    path: Path,
    *,
    media_type: str | None = None,
    filename: str | None = None,
) -> StreamingResponse:
    if not path.is_file():
        raise HTTPException(404)
    headers = {}
    if filename:
        safe_name = filename.replace('"', "")
        headers["Content-Disposition"] = f'attachment; filename="{safe_name}"'
    return StreamingResponse(
        stream_file(path),
        media_type=media_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        headers=headers,
    )


@app.get("/static/{path:path}", name="static", include_in_schema=False)
async def static_asset(path: str) -> StreamingResponse:
    candidate = (STATIC_ROOT / path).resolve()
    static_root = STATIC_ROOT.resolve()
    if candidate != static_root and static_root not in candidate.parents:
        raise HTTPException(404)
    return safe_file_response(candidate)


@app.middleware("http")
async def authentication(request: Request, call_next):
    config = SnapIMSConfig.load()
    public = request.url.path.startswith("/static") or request.url.path in {
        "/favicon.ico",
        "/login",
        "/health",
    }
    auth_problem = authentication_problem(config.auth_secret, config.admin_password_hash)
    enabled = authentication_enabled(config.auth_secret, config.admin_password_hash)
    claims = None
    session = request.cookies.get(COOKIE)
    if enabled and session:
        claims = read_session_claims(
            config.auth_secret,
            session,
            generation=config.session_generation,
            password_hash=config.admin_password_hash,
        )
        if claims is None:
            _event(
                "auth",
                "auth.session_revoked",
                severity="WARNING",
                status="REVOKED",
                outcome="INVALID_OR_EXPIRED_SESSION",
                retention_class="SECURITY",
            )
    anonymous_csrf = request.cookies.get(CSRF_COOKIE, "")
    request.state.csrf_token = (
        str(claims.get("csrf", "")) if claims else anonymous_csrf or _new_csrf()
    )
    if request.method in STATE_METHODS and enabled:
        if not _origin_allowed(request, config):
            LOGGER.warning(
                "Security request rejected reason=origin path=%s client=%s",
                request.url.path,
                _identity_marker(_client_identity(request)),
            )
            _event(
                "auth",
                "auth.request_rejected",
                severity="WARNING",
                status="REJECTED",
                outcome="ORIGIN",
                detail={"path": request.url.path, "method": request.method},
                retention_class="SECURITY",
            )
            origin_response = JSONResponse({"detail": "Forbidden"}, status_code=403)
            _security_headers(origin_response, request.url.path)
            return origin_response
        expected = str(claims.get("csrf", "")) if claims else anonymous_csrf
        submitted = await _submitted_csrf(request)
        if not expected or not submitted or not hmac.compare_digest(expected, submitted):
            LOGGER.warning(
                "Security request rejected reason=csrf path=%s client=%s",
                request.url.path,
                _identity_marker(_client_identity(request)),
            )
            _event(
                "auth",
                "auth.request_rejected",
                severity="WARNING",
                status="REJECTED",
                outcome="CSRF",
                detail={"path": request.url.path, "method": request.method},
                retention_class="SECURITY",
            )
            csrf_response = JSONResponse({"detail": "Forbidden"}, status_code=403)
            _security_headers(csrf_response, request.url.path)
            return csrf_response
    if auth_problem and not public:
        config_response = RedirectResponse(
            f"/login?error={quote('Authentication configuration error. Check .env.')}",
            status_code=303,
        )
        _security_headers(config_response, request.url.path)
        return config_response
    if enabled and not public:
        username = str(claims.get("sub", "")) if claims else None
        if username != config.admin_username:
            login_response = RedirectResponse("/login", status_code=303)
            _security_headers(login_response, request.url.path)
            return login_response
    response = await call_next(request)
    if enabled and not claims and not anonymous_csrf:
        forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
        response.set_cookie(
            CSRF_COOKIE,
            request.state.csrf_token,
            httponly=True,
            secure=request.url.scheme == "https" or forwarded_proto == "https",
            samesite="strict",
            max_age=3600,
        )
    _security_headers(response, request.url.path)
    return response


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = "") -> HTMLResponse:
    config = SnapIMSConfig.load()
    auth_problem = authentication_problem(config.auth_secret, config.admin_password_hash)
    return TEMPLATES.TemplateResponse(
        request,
        "login.html",
        context(
            request,
            error=error or auth_problem,
            auth_disabled=not authentication_enabled(
                config.auth_secret, config.admin_password_hash
            )
            and not auth_problem,
            show_nav=False,
        ),
    )


@app.post("/login")
async def login(request: Request, username: str = Form(""), password: str = Form("")) -> RedirectResponse:
    config = SnapIMSConfig.load()
    auth_problem = authentication_problem(config.auth_secret, config.admin_password_hash)
    if auth_problem:
        return RedirectResponse(
            f"/login?error={quote('Authentication configuration error. Check .env.')}",
            status_code=303,
        )
    if not authentication_enabled(config.auth_secret, config.admin_password_hash):
        return RedirectResponse("/", status_code=303)
    identity = _client_identity(request, username)
    retry_after = _login_retry_after(identity)
    if retry_after:
        LOGGER.warning(
            "Authentication failed outcome=throttled identity=%s",
            _identity_marker(identity),
        )
        _event(
            "auth",
            "auth.login_failed",
            severity="WARNING",
            status="THROTTLED",
            outcome="RATE_LIMITED",
            safe_summary="Login attempt was throttled.",
            detail={
                "identity_marker": _identity_marker(identity),
                "retry_after_seconds": retry_after,
            },
            retention_class="SECURITY",
        )
        response = RedirectResponse("/login?error=Invalid%20credentials", status_code=303)
        response.headers["Retry-After"] = str(retry_after)
        return response
    if username == config.admin_username and verify_password(password, config.admin_password_hash):
        _clear_login_failures(identity)
        LOGGER.info("Authentication succeeded identity=%s", _identity_marker(identity))
        _event(
            "auth",
            "auth.login_succeeded",
            status="AUTHENTICATED",
            outcome="SUCCESS",
            detail={"identity_marker": _identity_marker(identity)},
            retention_class="SECURITY",
        )
        response = RedirectResponse("/", status_code=303)
        forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
        response.set_cookie(
            COOKIE,
            issue_session(
                config.auth_secret,
                username,
                generation=config.session_generation,
                password_hash=config.admin_password_hash,
            ),
            httponly=True,
            secure=request.url.scheme == "https" or forwarded_proto == "https",
            samesite="lax",
            max_age=86400,
        )
        response.delete_cookie(CSRF_COOKIE)
        return response
    delay = _record_login_failure(identity)
    LOGGER.warning(
        "Authentication failed outcome=invalid identity=%s backoff_seconds=%s",
        _identity_marker(identity),
        delay,
    )
    _event(
        "auth",
        "auth.login_failed",
        severity="WARNING",
        status="REJECTED",
        outcome="INVALID_CREDENTIALS",
        safe_summary="Login credentials were rejected.",
        detail={
            "identity_marker": _identity_marker(identity),
            "backoff_seconds": delay,
        },
        retention_class="SECURITY",
    )
    return RedirectResponse("/login?error=Invalid%20credentials", status_code=303)


@app.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    identity = _client_identity(request)
    LOGGER.info("Authentication logout identity=%s", _identity_marker(identity))
    _event(
        "auth",
        "auth.logout",
        status="LOGGED_OUT",
        outcome="SUCCESS",
        detail={"identity_marker": _identity_marker(identity)},
        retention_class="SECURITY",
    )
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE)
    response.delete_cookie(CSRF_COOKIE)
    return response


def get_paths() -> DataPaths:
    return DataPaths.from_root().ensure()


def context(request: Request, **values: Any) -> dict[str, Any]:
    return {
        "request": request,
        "version": __version__,
        "csrf_token": getattr(request.state, "csrf_token", ""),
        **values,
    }


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def selected_batch(paths: DataPaths, batch_id: str | None) -> str:
    batches = db.list_batches(paths.db_file)
    if not batches:
        return ""
    if batch_id and any(row["batch_id"] == batch_id for row in batches):
        return batch_id
    active = db.get_setting(paths.db_file, "active_batch", "")
    if active and any(row["batch_id"] == active for row in batches):
        return active
    return str(batches[0]["batch_id"])


def validate_folder(raw: str | None) -> tuple[str, str]:
    if not raw or not raw.strip():
        return "", "No source folder selected."
    candidate = Path(raw.strip()).expanduser()
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        return str(candidate), f"Could not resolve source folder: {exc}"
    if not resolved.exists():
        return str(resolved), "Source folder does not exist."
    if not resolved.is_dir():
        return str(resolved), "Source path is not a folder."
    if not os.access(resolved, os.R_OK | os.X_OK):
        return str(resolved), "Source folder cannot be read by SnapIMS."
    return str(resolved), ""


def physical_context(items: list[dict[str, Any]], current: dict[str, Any] | None) -> dict[str, Any]:
    if not current:
        return {"position": 0, "total": len(items), "unfinished": 0}
    all_batch = db.list_items(get_paths().db_file, batch_id=current["batch_id"])
    unfinished = sum(1 for row in all_batch if row["review_status"] == "UNFINISHED")
    return {"position": int(current["sequence"]), "total": len(all_batch), "unfinished": unfinished}


def resolve_item(
    paths: DataPaths,
    batch_id: str,
    queue: str,
    item_id: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    items = db.list_items(paths.db_file, batch_id=batch_id, queue=queue)
    if not items:
        return items, None
    candidate = item_id or db.get_cursor(paths.db_file, batch_id, queue)
    current = next((row for row in items if row["item_id"] == candidate), items[0])
    db.set_cursor(paths.db_file, batch_id, queue, current["item_id"])
    return items, current


def next_item(items: list[dict[str, Any]], current_id: str) -> dict[str, Any] | None:
    if not items:
        return None
    for index, item in enumerate(items):
        if item["item_id"] == current_id:
            return items[(index + 1) % len(items)] if len(items) > 1 else item
    return items[0]


def previous_item(items: list[dict[str, Any]], current_id: str) -> dict[str, Any] | None:
    if not items:
        return None
    for index, item in enumerate(items):
        if item["item_id"] == current_id:
            return items[index - 1]
    return items[0]


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    paths = get_paths()
    batches = db.list_batches(paths.db_file)
    summary = db.database_summary(paths.db_file)
    active = selected_batch(paths, None)
    health = db.batch_health(paths.db_file, active) if active else {}
    return TEMPLATES.TemplateResponse(
        request,
        "home.html",
        context(request, batches=batches, summary=summary, active=active, health=health),
    )


@app.get("/import", response_class=HTMLResponse)
async def import_page(
    request: Request,
    source_folder: str = "",
    batch_name: str = "",
    message: str = "",
    notice: str = "",
    manual: bool = False,
) -> HTMLResponse:
    paths = get_paths()
    configured = db.get_setting(paths.db_file, "incoming_folder", str(paths.incoming))
    selected = source_folder or configured
    recent = db.recent_folders(paths.db_file)
    resolved, folder_error = validate_folder(selected)
    return TEMPLATES.TemplateResponse(
        request,
        "import.html",
        context(
            request,
            configured=configured,
            selected=resolved or selected,
            recent=recent,
            available=not folder_error,
            batch_name=batch_name,
            preview=None,
            imported=None,
            message=message or (folder_error if selected and source_folder else ""),
            notice=notice,
            manual=manual,
        ),
    )


@app.post("/import/use-folder")
async def use_folder(
    path: str | None = Form(None),
    save_as_incoming: bool = Form(False),
) -> RedirectResponse:
    paths = get_paths()
    resolved, error = validate_folder(path)
    if error:
        return redirect(f"/import?source_folder={quote(path or '')}&message={quote(error)}")
    if save_as_incoming:
        db.set_setting(paths.db_file, "incoming_folder", resolved)
    db.remember_folder(paths.db_file, Path(resolved))
    return redirect(f"/import?source_folder={quote(resolved)}&notice={quote('Folder selected.')}")


@app.post("/import/browse")
async def browse_folder(current_folder: str = Form("")) -> RedirectResponse:
    try:
        selected = choose_folder(current_folder)
    except FolderPickerUnavailable:
        notice = "Native folder picker is unavailable. Paste the folder path below."
        return redirect(
            f"/import?source_folder={quote(current_folder)}&manual=true&notice={quote(notice)}"
        )
    if not selected:
        return redirect(
            f"/import?source_folder={quote(current_folder)}&notice={quote('Folder selection cancelled.')}"
        )
    resolved, error = validate_folder(selected)
    if error:
        return redirect(f"/import?source_folder={quote(selected)}&message={quote(error)}")
    paths = get_paths()
    db.remember_folder(paths.db_file, Path(resolved))
    return redirect(f"/import?source_folder={quote(resolved)}&notice={quote('Folder selected.')}")


@app.post("/import/remove-recent")
async def remove_recent_folder(path: str = Form("")) -> RedirectResponse:
    paths = get_paths()
    remaining = [folder for folder in db.recent_folders(paths.db_file, limit=20) if folder != path]
    db.set_setting(paths.db_file, "recent_import_folders", json.dumps(remaining[:5]))
    return redirect("/import?notice=" + quote("Recent folder removed."))


def import_context(
    request: Request,
    *,
    selected: str,
    batch_name: str,
    preview: dict[str, Any] | None = None,
    imported: Any = None,
    message: str = "",
    notice: str = "",
) -> HTMLResponse:
    paths = get_paths()
    configured = db.get_setting(paths.db_file, "incoming_folder", str(paths.incoming))
    return TEMPLATES.TemplateResponse(
        request,
        "import.html",
        context(
            request,
            configured=configured,
            selected=selected,
            recent=db.recent_folders(paths.db_file),
            available=Path(selected).is_dir() if selected else False,
            batch_name=batch_name,
            preview=preview,
            imported=imported,
            message=message,
            notice=notice,
        ),
    )


@app.post("/import/preview", response_class=HTMLResponse)
async def import_preview(
    request: Request,
    source_folder: str | None = Form(None),
    batch_name: str = Form(""),
    recursive: bool = Form(False),
) -> HTMLResponse:
    selected, error = validate_folder(source_folder)
    if error:
        _event(
            "import",
            "import.preview_failed",
            severity="WARNING",
            status="REJECTED",
            outcome="INVALID_FOLDER",
            safe_summary=error,
        )
        return import_context(
            request, selected=source_folder or "", batch_name=batch_name, message=error
        )
    try:
        batch = parse_batch(Path(selected), batch_name=batch_name or None, recursive=recursive)
        paths = get_paths()
        duplicate = db.find_batch_by_fingerprint(paths.db_file, batch.source_fingerprint)
        preview = {
            "items": len(batch.items),
            "photos": batch.photo_count,
            "commands": len(batch.commands),
            "warnings": batch.warnings,
            "recursive": recursive,
            "duplicate_batch_id": duplicate["batch_id"] if duplicate else "",
        }
        _event(
            "import",
            "import.preview_completed",
            operation_id=f"import:{batch.source_fingerprint[:16]}",
            batch_id=str(duplicate["batch_id"]) if duplicate else "",
            status="DUPLICATE" if duplicate else "READY",
            outcome="EXISTING_BATCH" if duplicate else "NEW_IMPORT",
            image_count=len(batch.source_photos),
            detail={
                "item_count": len(batch.items),
                "product_photo_count": batch.photo_count,
                "command_count": len(batch.commands),
                "warning_count": len(batch.warnings),
                "recursive": recursive,
            },
        )
        return import_context(request, selected=selected, batch_name=batch_name, preview=preview)
    except Exception as exc:
        safe = safe_exception(exc, known_secrets=_configured_secrets())
        _event(
            "import",
            "import.preview_failed",
            severity="ERROR",
            status="FAILED",
            outcome="PARSE_FAILED",
            error_class=safe["error_class"],
            safe_summary=safe["safe_summary"],
        )
        return import_context(request, selected=selected, batch_name=batch_name, message=str(exc))


@app.post("/import/commit", response_class=HTMLResponse)
async def import_commit(
    request: Request,
    source_folder: str | None = Form(None),
    batch_name: str = Form(""),
    recursive: bool = Form(False),
) -> HTMLResponse:
    selected, error = validate_folder(source_folder)
    if error:
        return import_context(
            request, selected=source_folder or "", batch_name=batch_name, message=error
        )
    try:
        result = process_batch(
            Path(selected), paths=get_paths(), batch_name=batch_name or None, recursive=recursive
        )
        db.set_setting(get_paths().db_file, "active_batch", result.batch_id)
        notice = (
            "Existing imported batch opened; no duplicate was created."
            if result.duplicate
            else "Batch preserved and imported."
        )
        return import_context(
            request,
            selected=selected,
            batch_name=batch_name,
            imported=result,
            notice=notice,
        )
    except Exception as exc:
        return import_context(request, selected=selected, batch_name=batch_name, message=str(exc))


@app.get("/review", response_class=HTMLResponse)
async def review_page(
    request: Request,
    batch_id: str | None = None,
    queue: str = Query("UNRESOLVED", pattern="^(UNRESOLVED|DONE|FAILED|BLOCKED|ALL)$"),
    item_id: str | None = None,
    photo: int = 1,
    edit: bool = False,
    errors: str = "",
    notice: str = "",
) -> HTMLResponse:
    paths = get_paths()
    batches = db.list_batches(paths.db_file)
    batch_id = selected_batch(paths, batch_id)
    if not batch_id:
        return TEMPLATES.TemplateResponse(
            request,
            "review.html",
            context(
                request,
                batches=[],
                batch_id="",
                queue=queue,
                items=[],
                all_items=[],
                current=None,
                photos=[],
                suggestion=None,
                history=[],
                item_history=[],
                job=None,
                status_text="",
                status_action="",
                providers=recognizer_registry(),
                physical={},
                edit=edit,
                errors=[],
                notice=notice,
                photo_index=1,
                health={},
                catalog_status=None,
                display_title="",
                catalog_job=None,
                catalog_candidates=[],
                tag_definitions=[],
            ),
        )
    db.set_setting(paths.db_file, "active_batch", batch_id)
    items, current = resolve_item(paths, batch_id, queue, item_id)
    all_items = db.list_items(paths.db_file, batch_id=batch_id)
    photos = db.get_item_photos(paths.db_file, current["item_id"]) if current else []
    photo_index = max(1, min(photo, len(photos) or 1))
    suggestion = db.latest_recognition(paths.db_file, current["item_id"]) if current else None
    history = db.recognition_history(paths.db_file, current["item_id"]) if current else []
    changes = db.item_history(paths.db_file, current["item_id"]) if current else []
    job = db.get_recognition_job(paths.db_file, batch_id)
    status_text, status_action = recognition_status(paths, batch_id, job)
    physical = physical_context(items, current)
    catalog_status = None
    display_title = ""
    catalog_job = None
    catalog_candidates: list[dict[str, Any]] = []
    if current:
        try:
            catalog_status = get_catalog_status(paths, current["item_id"])
            catalog_job = latest_catalog_job(paths.catalog_db_file, item_id=current["item_id"])
            if catalog_job and str(catalog_job.get("status")) == "AMBIGUOUS":
                with catalog_db.connect(paths.catalog_db_file, readonly=True) as connection:
                    catalog_candidates = [
                        dict(row)
                        for row in connection.execute(
                            "SELECT * FROM movie_candidates WHERE job_id=? AND rejected_reason='' "
                            "ORDER BY score DESC,candidate_id LIMIT 5",
                            (int(catalog_job["job_id"]),),
                        )
                    ]
        except Exception as exc:
            LOGGER.debug("Catalog status unavailable for %s: %s", current["item_id"], exc)
        display_title = str(
            current.get("title")
            or (catalog_status.canonical_title if catalog_status else "")
            or (suggestion.get("suggested_title") if suggestion else "")
            or "Title required"
        )
    decoded_errors = [part for part in errors.split("|") if part]
    return TEMPLATES.TemplateResponse(
        request,
        "review.html",
        context(
            request,
            batches=batches,
            batch_id=batch_id,
            queue=queue,
            items=items,
            all_items=all_items,
            current=current,
            photos=photos,
            suggestion=suggestion,
            history=history,
            item_history=changes,
            job=job,
            status_text=status_text,
            status_action=status_action,
            providers=recognizer_registry(),
            physical=physical,
            edit=edit,
            errors=decoded_errors,
            notice=notice,
            photo_index=photo_index,
            conditions=CONDITIONS,
            pool_modes=POOL_MODES,
            health=db.batch_health(paths.db_file, batch_id),
            catalog_status=catalog_status,
            display_title=display_title,
            catalog_job=catalog_job,
            catalog_candidates=catalog_candidates,
            tag_definitions=db.list_tag_definitions(paths.db_file),
        ),
    )


def recognition_status(
    paths: DataPaths, batch_id: str, job: dict[str, Any] | None
) -> tuple[str, str]:
    items = db.list_items(paths.db_file, batch_id=batch_id)
    unfinished = sum(1 for item in items if item["review_status"] == "UNFINISHED")
    if items and unfinished == 0:
        return f"Review complete · {len(items)} of {len(items)} items finished", "complete"
    if not job or job["status"] == "READY":
        return f"{len(items)} items ready to identify", "identify"
    if job["status"] in {"RUNNING", "IDENTIFYING"}:
        remaining = max(0, int(job["total"]) - int(job["completed"]))
        return (
            f"Identifying · {job['completed']} of {job['total']} complete · {remaining} remaining",
            "",
        )
    if job["status"] == "PAUSED":
        remaining = max(0, int(job["total"]) - int(job["completed"]))
        return (
            f"Identification paused · {job['completed']} of {job['total']} complete · {remaining} remaining",
            "continue",
        )
    if job["status"] == "BLOCKED":
        return (
            "Recognition is blocked before an attempt · configure a live provider or continue manually",
            "blocked",
        )
    if job["status"] in {"COMPLETE_WITH_FAILURES", "FAILED"}:
        return (
            f"Recognition failed or incomplete · {job['recognized']} ready · {job['failed']} failed",
            "failure",
        )
    if job["status"] == "SKIPPED":
        return (
            "Recognition intentionally skipped · complete the unfinished tapes manually",
            "manual",
        )
    if job["status"] in {"COMPLETE", "REVIEW_COMPLETE"}:
        return f"Recognition complete · {job['recognized']} items ready to review", ""
    return str(job["status"]), ""


@app.post("/review/identify")
async def identify(
    batch_id: str = Form(...),
    provider: str = Form("openai"),
    delay: float = Form(0),
) -> RedirectResponse:
    paths = get_paths()
    configured_delay = float(os.getenv("SNAPIMS_MOCK_DELAY", "0") or 0)
    effective_delay = delay if delay > 0 else configured_delay
    try:
        started = start_batch_recognition(paths.db_file, batch_id, provider, delay=effective_delay)
        notice = (
            "Identification started."
            if started
            else "Recognition could not start. Review the failure details below."
        )
    except Exception as exc:
        notice = f"Recognition could not start: {exc}"
    return redirect(f"/review?batch_id={quote(batch_id)}&notice={quote(notice)}")


@app.post("/review/retry-batch")
async def retry_batch(
    batch_id: str = Form(...),
    provider: str = Form("openai"),
    failed_only: bool = Form(False),
) -> RedirectResponse:
    try:
        started = start_batch_recognition(
            get_paths().db_file,
            batch_id,
            provider,
            retry_failed=failed_only,
        )
        scope = "failed items" if failed_only else "batch"
        notice = (
            f"Retry started for {scope}."
            if started
            else "Retry could not start. Review the updated failure details."
        )
    except Exception as exc:
        notice = f"Retry failed: {exc}"
    return redirect(f"/review?batch_id={quote(batch_id)}&notice={quote(notice)}")


@app.post("/review/manual")
async def continue_manual_review(batch_id: str = Form(...)) -> RedirectResponse:
    items = db.list_items(get_paths().db_file, batch_id=batch_id, queue="UNRESOLVED")
    target = items[0]["item_id"] if items else ""
    url = f"/review?batch_id={quote(batch_id)}&queue=UNRESOLVED&edit=true&notice={quote('Manual review opened. AI recognition is not required.')}"
    if target:
        url += f"&item_id={quote(target)}"
    return redirect(url)


@app.post("/review/skip-recognition")
async def skip_recognition(batch_id: str = Form(...)) -> RedirectResponse:
    skip_batch_recognition(get_paths().db_file, batch_id)
    return redirect(
        f"/review?batch_id={quote(batch_id)}&queue=UNRESOLVED&notice="
        + quote("Recognition skipped. Items remain unfinished for manual review.")
    )


@app.get("/review/job/{batch_id}")
async def job_status(batch_id: str) -> dict[str, Any]:
    paths = get_paths()
    job = db.get_recognition_job(paths.db_file, batch_id)
    text, action = recognition_status(paths, batch_id, job)
    return {
        "job": job,
        "text": text,
        "action": action,
        "health": db.batch_health(paths.db_file, batch_id),
    }


@app.post("/review/approve")
async def approve(
    batch_id: str = Form(...),
    item_id: str = Form(...),
    title: str = Form(""),
    price: str = Form(""),
    tag_ids: str = Form(""),
    discount: str = Form("0"),
) -> RedirectResponse:
    try:
        price_cents = parse_price_cents(price, allow_blank=True)
        discount_percent = parse_discount_percent(discount)
    except ValueError:
        return redirect(
            f"/review?batch_id={quote(batch_id)}&item_id={quote(item_id)}&edit=true&errors="
            + quote("Price or discount is invalid")
        )
    try:
        errors = accept_item(
            get_paths().db_file,
            item_id,
            price_cents=price_cents,
            discount_percent=discount_percent,
            title_override=title.strip() or None,
            tag_ids=[value for value in tag_ids.split(",") if value],
        )
    except ValueError as exc:
        return redirect(
            f"/review?batch_id={quote(batch_id)}&item_id={quote(item_id)}&errors="
            + quote(str(exc))
        )
    if errors:
        message = "|".join(
            "This tape still needs information in the exception editor."
            if error == "Title is required"
            else error
            for error in errors
        )
        return redirect(
            f"/review?batch_id={quote(batch_id)}&item_id={quote(item_id)}&edit=true&errors={quote(message)}"
        )
    try:
        saved = db.get_item(get_paths().db_file, item_id)
        if saved and saved.get("title"):
            queue_operator_title_correction(
                get_paths(),
                item_id,
                str(saved["title"]),
                int(saved["release_year"]) if saved.get("release_year") is not None else None,
            )
    except Exception as exc:
        LOGGER.debug("Catalog lookup could not be queued after approval for %s: %s", item_id, exc)
    unresolved = db.list_items(get_paths().db_file, batch_id=batch_id, queue="UNRESOLVED")
    target = unresolved[0]["item_id"] if unresolved else ""
    if target:
        db.set_cursor(get_paths().db_file, batch_id, "UNRESOLVED", target)
        return redirect(
            f"/review?batch_id={quote(batch_id)}&queue=UNRESOLVED&item_id={quote(target)}&notice="
            + quote("Approved. Next unfinished tape opened.")
        )
    return redirect(
        f"/review?batch_id={quote(batch_id)}&queue=DONE&notice={quote('Review complete.')}"
    )


@app.post("/review/later")
async def later(batch_id: str = Form(...), item_id: str = Form(...)) -> RedirectResponse:
    paths = get_paths()
    postpone_item(paths.db_file, item_id)
    items = db.list_items(paths.db_file, batch_id=batch_id, queue="UNRESOLVED")
    target = next_item(items, item_id)
    target_id = target["item_id"] if target else item_id
    db.set_cursor(paths.db_file, batch_id, "UNRESOLVED", target_id)
    return redirect(
        f"/review?batch_id={quote(batch_id)}&queue=UNRESOLVED&item_id={quote(target_id)}&notice="
        + quote("Tape postponed and remains unfinished.")
    )


@app.post("/review/navigate")
async def navigate(
    batch_id: str = Form(...),
    queue: str = Form(...),
    item_id: str = Form(...),
    direction: str = Form(...),
) -> RedirectResponse:
    paths = get_paths()
    items = db.list_items(paths.db_file, batch_id=batch_id, queue=queue)
    target = previous_item(items, item_id) if direction == "previous" else next_item(items, item_id)
    target_id = target["item_id"] if target else item_id
    db.set_cursor(paths.db_file, batch_id, queue, target_id)
    return redirect(
        f"/review?batch_id={quote(batch_id)}&queue={quote(queue)}&item_id={quote(target_id)}"
    )


@app.post("/review/retry")
async def retry(
    batch_id: str = Form(...),
    item_id: str = Form(...),
    provider: str = Form("openai"),
) -> RedirectResponse:
    try:
        retry_failed_item(get_paths().db_file, item_id, provider)
        notice = "Recognition recovered. Review the suggestion."
    except Exception as exc:
        notice = str(exc)
    return redirect(
        f"/review?batch_id={quote(batch_id)}&queue=UNRESOLVED&item_id={quote(item_id)}&notice={quote(notice)}"
    )


@app.post("/review/save")
async def save_item(
    batch_id: str = Form(...),
    item_id: str = Form(...),
    queue: str = Form(...),
    title: str = Form(""),
    release_year: str = Form(""),
    barcode: str = Form(""),
    distributor: str = Form(""),
    edition: str = Form(""),
    price: str = Form(""),
    discount: str = Form("0"),
    quantity: int = Form(1),
    condition: str = Form("Not Graded"),
    shelf: str = Form("Q1"),
    location_reason: str = Form(""),
    rare: bool = Form(False),
    review: bool = Form(False),
    vendor: str = Form("Canada VHS"),
    product_type: str = Form("VHS Tape"),
    tag_ids: str = Form(""),
    condition_notes: str = Form(""),
    description: str = Form(""),
    pool_mode: str = Form("POOLED"),
    revision: int = Form(0),
) -> RedirectResponse:
    paths = get_paths()
    current = db.get_item(paths.db_file, item_id)
    if current is None:
        raise HTTPException(404)
    try:
        values = {
            "title": title.strip(),
            "release_year": int(release_year) if release_year.strip() else None,
            "barcode": barcode.strip(),
            "distributor": distributor.strip(),
            "edition": edition.strip(),
            "price_cents": parse_price_cents(price, allow_blank=True),
            "discount_percent": parse_discount_percent(discount),
            "quantity": quantity,
            "condition": condition,
            "shelf": shelf.strip().upper(),
            "rare": int(rare),
            "review": int(review),
            "vendor": vendor.strip() or "Canada VHS",
            "product_type": product_type.strip() or "VHS Tape",
            "tag_ids": [value for value in tag_ids.split(",") if value],
            "_tag_source": "OPERATOR_REVIEW",
            "condition_notes": condition_notes.strip(),
            "description": description.strip(),
            "pool_mode": pool_mode,
            "ready": 1,
            "review_status": "DONE",
            "postponed_at": None,
            "review_source": "INDIVIDUAL_REVIEW",
            "working_source": "INDIVIDUAL_REVIEW",
        }
    except ValueError:
        return redirect(
            f"/review?batch_id={quote(batch_id)}&queue={quote(queue)}&item_id={quote(item_id)}&edit=true&errors="
            + quote("Numeric field is invalid")
        )
    candidate = {**current, **values}
    errors = validation_errors(candidate, db.get_item_photos(paths.db_file, item_id))
    if errors:
        return redirect(
            f"/review?batch_id={quote(batch_id)}&queue={quote(queue)}&item_id={quote(item_id)}&edit=true&errors="
            + quote("|".join(errors))
        )
    try:
        db.update_item(
            paths.db_file,
            item_id,
            values,
            source="INDIVIDUAL_REVIEW",
            reason=location_reason,
            expected_revision=revision,
        )
        validate_items(paths.db_file, [item_id])
        if values["title"] and (
            values["title"] != str(current.get("title") or "")
            or values["release_year"] != current.get("release_year")
        ):
            try:
                queue_operator_title_correction(
                    paths,
                    item_id,
                    str(values["title"]),
                    int(str(values["release_year"]))
                    if values["release_year"] is not None
                    else None,
                )
            except Exception as exc:
                LOGGER.exception("Catalog correction lookup failed for %s: %s", item_id, exc)
    except Exception as exc:
        return redirect(
            f"/review?batch_id={quote(batch_id)}&queue={quote(queue)}&item_id={quote(item_id)}&edit=true&errors={quote(str(exc))}"
        )
    return redirect(
        f"/review?batch_id={quote(batch_id)}&queue=DONE&item_id={quote(item_id)}&notice="
        + quote("Changes saved to the same immutable Item ID.")
    )


@app.get("/batch-editor", response_class=HTMLResponse)
async def batch_editor(request: Request, batch_id: str | None = None, notice: str = "") -> HTMLResponse:
    paths = get_paths()
    batches = db.list_batches(paths.db_file)
    batch_id = selected_batch(paths, batch_id)
    if batch_id:
        db.set_setting(paths.db_file, "active_batch", batch_id)
    items = db.list_editor_items(paths.db_file, batch_id) if batch_id else []
    checkpoints = db.list_batch_checkpoints(paths.db_file, batch_id) if batch_id else []
    return TEMPLATES.TemplateResponse(
        request,
        "batch_editor.html",
        context(
            request,
            batches=batches,
            batch_id=batch_id,
            items=items,
            health=db.batch_health(paths.db_file, batch_id) if batch_id else {},
            confidence_buckets=db.confidence_buckets(paths.db_file, batch_id) if batch_id else {},
            metrics=db.batch_metrics(paths.db_file, batch_id) if batch_id else {},
            checkpoints=checkpoints,
            notice=notice,
            tag_definitions=db.list_tag_definitions(paths.db_file),
        ),
    )


def normalize_editor_value(field: str, value: Any) -> Any:
    if field == "price_cents":
        if isinstance(value, int):
            return value
        return parse_price_cents(value, allow_blank=True)
    if field in {"discount_percent"}:
        return parse_discount_percent(value)
    if field in {"quantity", "release_year"}:
        return int(value) if value not in (None, "") else None
    if field in {"rare", "review", "ready"}:
        return int(bool(value))
    if field == "tag_ids":
        if not isinstance(value, list):
            raise ValueError("Tags must be submitted as approved Tag IDs")
        return [str(tag_id) for tag_id in value]
    if field == "shelf":
        return str(value).strip().upper()
    return str(value or "").strip()


@app.get("/api/batches/{batch_id}/items")
async def api_batch_items(batch_id: str) -> dict[str, Any]:
    paths = get_paths()
    return {
        "items": db.list_editor_items(paths.db_file, batch_id),
        "health": db.batch_health(paths.db_file, batch_id),
    }


@app.post("/api/items/{item_id}")
async def api_update_item(item_id: str, request: Request) -> JSONResponse:
    paths = get_paths()
    payload = await request.json()
    current = db.get_item(paths.db_file, item_id)
    if current is None:
        return JSONResponse({"ok": False, "error": "Unknown item"}, status_code=404)
    field = str(payload.get("field") or "")
    allowed = {
        "title",
        "price_cents",
        "discount_percent",
        "description",
        "shelf",
        "quantity",
        "condition",
        "tag_ids",
        "rare",
        "review",
        "edition",
        "distributor",
        "release_year",
    }
    if field not in allowed:
        return JSONResponse({"ok": False, "error": "Field is not editable"}, status_code=400)
    try:
        value = normalize_editor_value(field, payload.get("value"))
        reason = str(payload.get("reason") or "Batch Editor")
        db.update_item(
            paths.db_file,
            item_id,
            {field: value, "working_source": "BATCH_EDITOR"},
            source="BATCH_EDITOR",
            reason=reason,
            expected_revision=int(payload.get("revision"))
            if payload.get("revision") is not None
            else None,
        )
        validate_items(paths.db_file, [item_id])
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=409)
    if field in {"title", "release_year"}:
        updated = db.get_item(paths.db_file, item_id)
        if updated and updated.get("title"):
            try:
                queue_operator_title_correction(
                    paths,
                    item_id,
                    str(updated["title"]),
                    int(updated["release_year"])
                    if updated.get("release_year") is not None
                    else None,
                )
            except Exception as exc:
                LOGGER.exception("Catalog correction lookup failed for %s: %s", item_id, exc)
    saved = db.get_item(paths.db_file, item_id)
    if saved is None:
        raise HTTPException(404)
    return JSONResponse(
        {"ok": True, "item": saved, "health": db.batch_health(paths.db_file, saved["batch_id"])}
    )


@app.get("/api/items/{item_id}/photos")
async def api_item_photos(item_id: str) -> dict[str, Any]:
    item = db.get_item(get_paths().db_file, item_id)
    if item is None:
        raise HTTPException(404)
    photos = db.get_item_photos(get_paths().db_file, item_id)
    return {
        "item_id": item_id,
        "photos": [
            {
                "photo_id": photo["photo_id"],
                "original_name": photo["original_name"],
                "image_role": photo.get("image_role") or "support",
                "original_bytes": photo.get("original_bytes") or 0,
                "preview_bytes": photo.get("preview_bytes") or 0,
                "recognition_bytes": photo.get("recognition_bytes") or 0,
            }
            for photo in photos
        ],
    }


@app.post("/api/batches/{batch_id}/bulk")
async def api_bulk_edit(batch_id: str, request: Request) -> JSONResponse:
    payload = await request.json()
    request_id = str(payload.get("request_id") or uuid4().hex)
    try:
        result = apply_bulk_operation(
            get_paths().db_file,
            batch_id=batch_id,
            item_ids=[str(value) for value in payload.get("item_ids", [])],
            action=str(payload.get("action") or ""),
            value=payload.get("value"),
            reason=str(payload.get("reason") or "Bulk edit"),
            request_id=request_id,
        )
    except Exception as exc:
        safe = safe_exception(exc, known_secrets=_configured_secrets())
        _event(
            "inventory",
            "inventory.bulk_failed",
            severity="ERROR",
            operation_id=request_id,
            batch_id=batch_id,
            status="FAILED",
            outcome=str(payload.get("action") or "UNKNOWN"),
            error_class=safe["error_class"],
            safe_summary=safe["safe_summary"],
            retention_class="BUSINESS",
        )
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=409)
    _event(
        "inventory",
        "inventory.bulk_completed",
        operation_id=result.request_id,
        batch_id=batch_id,
        status="COMPLETE",
        outcome=str(payload.get("action") or "UNKNOWN"),
        detail={
            "requested": result.requested,
            "validated": result.validated,
            "changed": result.changed,
            "unchanged": result.unchanged,
            "failed": result.failed,
            "checkpoint_id": result.checkpoint_id,
        },
        retention_class="BUSINESS",
    )
    return JSONResponse(
        {
            "ok": True,
            "requested": result.requested,
            "validated": result.validated,
            "changed": result.changed,
            "unchanged": result.unchanged,
            "failed": result.failed,
            "errors": list(result.errors),
            "checkpoint_id": result.checkpoint_id,
            "request_id": result.request_id,
            "health": db.batch_health(get_paths().db_file, batch_id),
        }
    )


@app.post("/api/checkpoints/{checkpoint_id}/restore")
async def restore_checkpoint(checkpoint_id: int) -> JSONResponse:
    try:
        count = db.restore_batch_checkpoint(get_paths().db_file, checkpoint_id)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return JSONResponse({"ok": True, "restored": count})


@app.get("/api/catalog/status/{item_id}")
async def api_catalog_status(item_id: str) -> dict[str, Any]:
    paths = get_paths()
    if db.get_item(paths.db_file, item_id) is None:
        raise HTTPException(404)
    status = get_catalog_status(paths, item_id)
    return {
        "available": status.available,
        "status": status.status,
        "label": status.label,
        "movie_id": status.movie_id,
        "canonical_title": status.canonical_title,
        "release_year": status.primary_release_year,
        "candidate_count": status.candidate_count,
        "error": status.error,
    }


@app.get("/api/catalog/search")
async def api_catalog_search(
    q: str = Query(..., min_length=1), year: int | None = None
) -> dict[str, Any]:
    paths = get_paths()
    matches = search_local(paths.catalog_db_file, q, year)
    return {
        "matches": [
            {
                "movie_id": match.movie_id,
                "canonical_title": match.canonical_title,
                "release_year": match.primary_release_year,
                "score": match.match_score,
                "method": match.method,
                "reason": match.reason,
                "unique": match.unique,
            }
            for match in matches
        ]
    }


@app.post("/catalog/jobs/{job_id}/select")
async def catalog_select_candidate(
    job_id: int,
    candidate_id: int = Form(...),
    batch_id: str = Form(...),
    queue: str = Form("UNRESOLVED"),
    item_id: str = Form(...),
) -> RedirectResponse:
    try:
        movie_id = select_candidate(get_paths(), job_id, candidate_id)
        notice = f"Catalog candidate selected and linked as {movie_id}."
    except Exception as exc:
        notice = f"Catalog selection failed: {exc}"
    return redirect(
        f"/review?batch_id={quote(batch_id)}&queue={quote(queue)}&item_id={quote(item_id)}&notice={quote(notice)}"
    )


@app.post("/catalog/jobs/{job_id}/retry")
async def catalog_retry_job(
    job_id: int, batch_id: str = Form(""), item_id: str = Form("")
) -> RedirectResponse:
    paths = get_paths()
    row = None
    try:
        with catalog_db.transaction(paths.catalog_db_file) as connection:
            row = connection.execute(
                "SELECT item_id FROM catalog_lookup_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError("Unknown catalog job")
            connection.execute(
                "UPDATE catalog_lookup_jobs SET status='QUEUED',finished_at=NULL,last_error='',updated_at=? WHERE job_id=?",
                (catalog_db.now(), job_id),
            )
        start_catalog_job(paths, job_id)
        notice = "Catalog lookup queued for retry."
    except Exception as exc:
        notice = f"Catalog retry failed: {exc}"
    target_item = item_id or (str(row[0]) if row else "")
    return redirect(
        f"/review?batch_id={quote(batch_id)}&item_id={quote(target_item)}&notice={quote(notice)}"
    )


@app.get("/publish", response_class=HTMLResponse)
async def publish_page(
    request: Request,
    batch_id: str | None = None,
    simulate: bool = False,
    notice: str = "",
    message: str = "",
) -> HTMLResponse:
    paths = get_paths()
    batches = db.list_batches(paths.db_file)
    batch_id = selected_batch(paths, batch_id)
    items = db.list_items(paths.db_file, batch_id=batch_id) if batch_id else []
    service = ShopifyService(paths.db_file, ShopifyConfig.from_env())
    reports = [service.dry_run(item["item_id"]) for item in items] if simulate else []
    evaluated = reports or [service.dry_run(item["item_id"]) for item in items]
    ready = sum(1 for report in evaluated if report.ready)
    blocked = len(items) - ready
    sources = sorted({str(item.get("working_source") or "IMPORT") for item in items})
    return TEMPLATES.TemplateResponse(
        request,
        "publish.html",
        context(
            request,
            batches=batches,
            batch_id=batch_id,
            items=items,
            reports=reports,
            ready=ready,
            blocked=blocked,
            sources=sources,
            health=db.batch_health(paths.db_file, batch_id) if batch_id else {},
            checkpoints=db.list_batch_checkpoints(paths.db_file, batch_id) if batch_id else [],
            notice=notice,
            message=message,
        ),
    )


@app.get("/publish/csv/{batch_id}")
async def download_csv(batch_id: str) -> StreamingResponse:
    paths = get_paths()
    destination = paths.exports / f"{batch_id}-inventory_work.csv"
    export_inventory_csv(paths.db_file, batch_id, destination)
    return safe_file_response(destination, media_type="text/csv", filename=destination.name)


@app.post("/publish/csv/preview")
async def upload_csv_preview(
    request: Request,
    batch_id: str = Form(...),
    csv_file: UploadFile = File(...),
) -> HTMLResponse:
    paths = get_paths()
    try:
        raw = csv_file.file.read(5_000_001)
        if len(raw) > 5_000_000:
            raise CSVImportError("CSV upload exceeds the 5 MB safety limit")
        text = raw.decode("utf-8-sig")
        payload, summary, errors = preview_inventory_csv(paths.db_file, batch_id, text)
        token = uuid4().hex
        db.save_csv_staging(
            paths.db_file,
            token=token,
            batch_id=batch_id,
            filename=csv_file.filename or "uploaded.csv",
            payload=payload,
            diff=summary,
            blocking_errors=errors,
            upload_bytes=len(raw),
        )
        _event(
            "inventory",
            "csv.staged",
            operation_id=f"csv:{token}",
            batch_id=batch_id,
            status="STAGED",
            outcome="BLOCKED" if errors else "READY",
            detail={
                "token_marker": token[:8],
                "row_count": len(payload),
                "upload_bytes": len(raw),
                "blocking_error_count": len(errors),
                "summary": summary,
            },
            retention_class="BUSINESS",
        )
        return TEMPLATES.TemplateResponse(
            request,
            "csv_diff.html",
            context(
                request,
                batch_id=batch_id,
                token=token,
                filename=csv_file.filename or "uploaded.csv",
                rows=payload,
                summary=summary,
                errors=errors,
            ),
        )
    except (UnicodeDecodeError, CSVImportError, OSError) as exc:
        safe = safe_exception(exc, known_secrets=_configured_secrets())
        _event(
            "inventory",
            "csv.stage_failed",
            severity="ERROR",
            batch_id=batch_id,
            status="FAILED",
            outcome="VALIDATION_FAILED",
            error_class=safe["error_class"],
            safe_summary=safe["safe_summary"],
            retention_class="BUSINESS",
        )
        return await publish_page(
            request, batch_id=batch_id, message=f"CSV upload failed: {exc}"
        )


@app.get("/publish/csv/diff/{token}", response_class=HTMLResponse)
async def csv_diff_page(request: Request, token: str) -> HTMLResponse:
    stage = db.get_csv_staging(get_paths().db_file, token)
    if stage is None:
        raise HTTPException(404)
    return TEMPLATES.TemplateResponse(
        request,
        "csv_diff.html",
        context(
            request,
            batch_id=stage["batch_id"],
            token=token,
            filename=stage["filename"],
            rows=stage["payload"],
            summary=stage["diff"],
            errors=stage["blocking_errors"],
        ),
    )


@app.post("/publish/csv/apply")
async def apply_csv(token: str = Form(...), confirmation: bool = Form(False)) -> RedirectResponse:
    if not confirmation:
        return redirect(f"/publish/csv/diff/{quote(token)}")
    try:
        batch_id, changed, checkpoint_id = apply_staged_csv(
            get_paths().db_file,
            token,
            paths=get_paths(),
        )
    except Exception as exc:
        stage = db.get_csv_staging(get_paths().db_file, token)
        batch_id = str(stage["batch_id"]) if stage else ""
        safe = safe_exception(exc, known_secrets=_configured_secrets())
        _event(
            "inventory",
            "csv.apply_failed",
            severity="ERROR",
            operation_id=f"csv:{token}",
            batch_id=batch_id,
            status="FAILED",
            outcome="NOT_APPLIED",
            error_class=safe["error_class"],
            safe_summary=safe["safe_summary"],
            retention_class="BUSINESS",
        )
        return redirect(
            f"/publish?batch_id={quote(batch_id)}&message=" + quote(f"CSV was not applied: {exc}")
        )
    _event(
        "inventory",
        "csv.applied",
        operation_id=f"csv:{token}",
        batch_id=batch_id,
        status="APPLIED",
        outcome="COMPLETE",
        detail={"changed_items": changed, "checkpoint_id": checkpoint_id},
        retention_class="BUSINESS",
    )
    return redirect(
        f"/publish?batch_id={quote(batch_id)}&notice="
        + quote(f"CSV applied to {changed} items. Rollback checkpoint {checkpoint_id} created.")
    )


@app.post("/publish/csv/cancel")
async def cancel_csv(token: str = Form(...), batch_id: str = Form(...)) -> RedirectResponse:
    db.delete_csv_staging(get_paths().db_file, token)
    _event(
        "inventory",
        "csv.cancelled",
        operation_id=f"csv:{token}",
        batch_id=batch_id,
        status="CANCELLED",
        outcome="NO_CHANGES",
        retention_class="BUSINESS",
    )
    return redirect(
        f"/publish?batch_id={quote(batch_id)}&notice={quote('CSV upload cancelled. No working values changed.')}"
    )


@app.get("/publish/csv/difference-report/{token}")
async def difference_report(token: str) -> StreamingResponse:
    stage = db.get_csv_staging(get_paths().db_file, token)
    if stage is None:
        raise HTTPException(404)
    destination = get_paths().exports / f"{stage['batch_id']}-csv-difference-{token[:8]}.json"
    destination.write_text(
        json.dumps(stage["diff"] | {"rows": stage["payload"]}, indent=2), encoding="utf-8"
    )
    return safe_file_response(
        destination,
        media_type="application/json",
        filename=destination.name,
    )


@app.post("/publish/external-review")
async def external_review(
    batch_id: str = Form(...),
    confirmation: bool = Form(False),
) -> RedirectResponse:
    if not confirmation:
        return redirect(
            f"/publish?batch_id={quote(batch_id)}&message={quote('External review confirmation is required.')}"
        )
    try:
        count, errors = mark_batch_externally_reviewed(get_paths().db_file, batch_id)
    except Exception as exc:
        return redirect(
            f"/publish?batch_id={quote(batch_id)}&message={quote(f'External review was not applied: {exc}')}"
        )
    if errors:
        return redirect(f"/publish?batch_id={quote(batch_id)}&message={quote(errors[0])}")
    return redirect(
        f"/publish?batch_id={quote(batch_id)}&notice="
        + quote(f"{count} items marked externally reviewed.")
    )


@app.post("/publish/restore-checkpoint")
async def publish_restore_checkpoint(
    batch_id: str = Form(...),
    checkpoint_id: int = Form(...),
) -> RedirectResponse:
    try:
        restored = db.restore_batch_checkpoint(get_paths().db_file, checkpoint_id)
        notice = f"Checkpoint restored for {restored} items."
        return redirect(f"/publish?batch_id={quote(batch_id)}&notice={quote(notice)}")
    except Exception as exc:
        return redirect(f"/publish?batch_id={quote(batch_id)}&message={quote(str(exc))}")


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, message: str = "") -> HTMLResponse:
    paths = get_paths()
    providers = {name: provider.available() for name, provider in recognizer_registry().items()}
    return TEMPLATES.TemplateResponse(
        request,
        "settings.html",
        context(
            request,
            incoming=db.get_setting(paths.db_file, "incoming_folder", str(paths.incoming)),
            recent=db.recent_folders(paths.db_file),
            providers=providers,
            message=message,
        ),
    )


@app.post("/settings")
async def save_settings(incoming_folder: str = Form(...)) -> RedirectResponse:
    resolved, error = validate_folder(incoming_folder)
    if error:
        _event(
            "system",
            "settings.save_failed",
            severity="WARNING",
            status="REJECTED",
            outcome="INVALID_FOLDER",
            safe_summary=error,
            retention_class="SECURITY",
        )
        return redirect(f"/settings?message={quote(error)}")
    db.set_setting(get_paths().db_file, "incoming_folder", resolved)
    _event(
        "system",
        "settings.saved",
        status="SAVED",
        outcome="SUCCESS",
        detail={"changed_fields": ["incoming_folder"]},
        retention_class="SECURITY",
    )
    return redirect(f"/settings?message={quote('Settings saved.')}")


@app.get("/diagnostics", response_class=HTMLResponse)
async def diagnostics(
    request: Request,
    notice: str = "",
    message: str = "",
    activity_source: str = "",
    activity_severity: str = "",
    activity_operation: str = "",
) -> HTMLResponse:
    paths = get_paths()
    with db.connect(paths.db_file) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
        schema = connection.execute("PRAGMA user_version").fetchone()[0]
        manifest = db.schema_manifest_report(connection)
        jobs = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM recognition_jobs ORDER BY updated_at DESC LIMIT 10"
            )
        ]
        csv_stages = [
            dict(row)
            for row in connection.execute(
                "SELECT token,batch_id,filename,status,created_at,updated_at,expires_at,row_count,"
                "upload_bytes,blocking_errors_json FROM csv_staging ORDER BY created_at DESC LIMIT 10"
            )
        ]
        imports = [
            dict(row)
            for row in connection.execute(
                "SELECT import_id,batch_id,status,updated_at,error AS error_message FROM import_journal "
                "ORDER BY updated_at DESC LIMIT 10"
            )
        ]
        operations = [
            dict(row)
            for row in connection.execute(
                "SELECT request_id,operation_type,batch_id,status,created_at,completed_at,error_message "
                "FROM operation_requests ORDER BY created_at DESC LIMIT 10"
            )
        ]
        active_operations = [
            dict(row)
            for row in connection.execute(
                """SELECT event_id,occurred_at,component,event_type,operation_id,batch_id,
                          item_id,status,safe_summary
                   FROM operational_events
                   WHERE operation_id!=''
                     AND event_id IN (
                         SELECT MAX(event_id) FROM operational_events
                         WHERE operation_id!='' GROUP BY operation_id
                     )
                     AND status IN (
                         'RUNNING','QUEUED','IDENTIFYING','RETRYING',
                         'SEARCHING_LOCAL','SEARCHING_WIKIPEDIA','LINK_PENDING'
                     )
                   ORDER BY event_id DESC LIMIT 25"""
            )
        ]
        recognition_queue_depth = int(
            connection.execute(
                "SELECT COUNT(*) FROM items WHERE recognition_status IN ('PENDING','BLOCKED')"
            ).fetchone()[0]
        )
        bulk_queue_depth = int(
            connection.execute(
                "SELECT COUNT(*) FROM operation_requests WHERE status IN ('REQUESTED','RUNNING')"
            ).fetchone()[0]
        )
    providers = {name: provider.available() for name, provider in recognizer_registry().items()}
    storage = db.storage_summary(paths.db_file)
    checkpoint_info = db.checkpoint_summary(paths.db_file)
    stage_info = db.csv_stage_summary(paths.db_file)
    import_info = db.import_journal_summary(paths.db_file)
    backups = sorted(
        paths.backups.glob("*.sqlite3"), key=lambda value: value.stat().st_mtime, reverse=True
    )
    catalog_error = str(getattr(request.app.state, "catalog_error", "") or "")
    catalog: dict[str, Any] = {
        "available": False,
        "integrity": "unavailable",
        "foreign_key_violations": 0,
        "schema_version": "-",
        "fts_available": False,
        "database_size_bytes": paths.catalog_db_file.stat().st_size
        if paths.catalog_db_file.exists()
        else 0,
    }
    catalog_jobs: list[dict[str, Any]] = []
    try:
        catalog = {"available": True, **catalog_db.catalog_summary(paths.catalog_db_file)}
        with catalog_db.connect(paths.catalog_db_file, readonly=True) as connection:
            catalog_jobs = [
                dict(row)
                for row in connection.execute(
                    "SELECT job_id,item_id,proposed_title,status,candidate_count,attempt_count,last_error,updated_at "
                    "FROM catalog_lookup_jobs ORDER BY updated_at DESC LIMIT 15"
                )
            ]
    except Exception as exc:
        catalog_error = catalog_error or redact_text(
            str(exc), known_secrets=_configured_secrets()
        )
    links = db.movie_link_summary(paths.db_file)
    activity_events = list(
        reversed(
            query_events(
                paths.db_file,
                last=100,
                severity=activity_severity,
                source=activity_source,
                operation_id=activity_operation,
            )
        )
    )
    catalog_queue_depth = sum(
        1
        for job in catalog_jobs
        if str(job.get("status") or "")
        in {"QUEUED", "PAUSED", "SEARCHING_WIKIPEDIA", "CANDIDATES_FOUND", "LINK_PENDING"}
    )
    diagnostic_summary = {
        "version": __version__,
        "database": str(paths.db_file),
        "schema": schema,
        "schema_manifest": manifest,
        "integrity": integrity,
        "foreign_key_violations": len(foreign),
        "providers": providers,
        "test_provider_mode": test_providers_enabled(),
        "test_contaminated_items": db.test_contamination_count(paths.db_file),
        "media": db.media_totals(paths.db_file),
        "storage": storage,
        "csv_stages": stage_info,
        "import_journal": import_info,
        "checkpoints": checkpoint_info,
        "last_backup": str(backups[0]) if backups else "",
        "movie_catalog": {**catalog, "path": str(paths.catalog_db_file), "error": catalog_error},
        "movie_links": links,
    }
    return TEMPLATES.TemplateResponse(
        request,
        "diagnostics.html",
        context(
            request,
            paths=paths,
            integrity=integrity,
            foreign=len(foreign),
            schema=schema,
            manifest=manifest,
            summary=db.database_summary(paths.db_file),
            providers=providers,
            test_provider_mode=test_providers_enabled(),
            test_contaminated_items=db.test_contamination_count(paths.db_file),
            jobs=redact(jobs, known_secrets=_configured_secrets()),
            csv_stages=redact(csv_stages, known_secrets=_configured_secrets()),
            imports=redact(imports, known_secrets=_configured_secrets()),
            operations=redact(operations, known_secrets=_configured_secrets()),
            active_operations=redact(
                active_operations, known_secrets=_configured_secrets()
            ),
            activity_events=activity_events,
            activity_source=activity_source,
            activity_severity=activity_severity,
            activity_operation=activity_operation,
            activity_queue_depth={
                "recognition": recognition_queue_depth,
                "catalog": catalog_queue_depth,
                "bulk": bulk_queue_depth,
            },
            media_totals=db.media_totals(paths.db_file),
            storage=storage,
            checkpoint_info=checkpoint_info,
            stage_info=stage_info,
            import_info=import_info,
            last_backup=str(backups[0]) if backups else "No backup recorded",
            diagnostic_summary=json.dumps(
                redact(diagnostic_summary, known_secrets=_configured_secrets()),
                indent=2,
            ),
            catalog=catalog,
            catalog_error=redact_text(
                catalog_error, known_secrets=_configured_secrets()
            ),
            catalog_jobs=redact(catalog_jobs, known_secrets=_configured_secrets()),
            links=links,
            notice=notice,
            message=message,
        ),
    )


@app.get("/api/diagnostics/events")
async def diagnostics_events(
    after: int = 0,
    last: int = Query(100, ge=1, le=500),
    source: str = "",
    severity: str = "",
    operation: str = "",
    batch: str = "",
    item: str = "",
    order: str = "",
) -> dict[str, Any]:
    events = query_events(
        get_paths().db_file,
        after_event_id=after,
        last=last,
        source=source,
        severity=severity,
        operation_id=operation,
        batch_id=batch,
        item_id=item,
        order_id=order,
    )
    return {
        "events": events,
        "last_event_id": max((int(event["event_id"]) for event in events), default=after),
        "bounded": True,
        "maximum": 500,
    }


@app.post("/diagnostics/support-bundle")
async def diagnostics_support_bundle() -> StreamingResponse:
    paths = get_paths()
    with db.connect(paths.db_file) as connection:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        manifest = db.schema_manifest_report(connection)
    config = SnapIMSConfig.load()
    bundle = create_support_bundle(
        paths,
        project_path=config.project_path,
        health={
            "inventory_database": {
                "integrity": integrity,
                "foreign_key_violations": foreign,
                "schema_manifest": manifest,
            },
            "catalog_error_class": (
                "CatalogUnavailable" if getattr(app.state, "catalog_error", "") else ""
            ),
        },
        configured_settings={
            "public_url": config.public_url,
            "allowed_hosts": config.allowed_hosts,
            "authentication_enabled": authentication_enabled(
                config.auth_secret, config.admin_password_hash
            ),
            "manage_guacamole_services": config.manage_guacamole_services,
        },
        known_secrets=_configured_secrets(),
    )
    _event(
        "system",
        "support_bundle.created",
        status="COMPLETE",
        outcome="EXPORTED",
        detail={"filename": bundle.name},
        retention_class="SECURITY",
    )
    return safe_file_response(
        bundle,
        media_type="application/zip",
        filename=bundle.name,
    )


@app.post("/diagnostics/catalog/backup")
async def catalog_backup_action() -> RedirectResponse:
    paths = get_paths()
    try:
        destination = catalog_db.backup_catalog(paths, "manual-diagnostics-backup")
        notice = f"Catalog backup created: {destination.name if destination else 'catalog does not exist'}"
        return redirect(f"/diagnostics?notice={quote(notice)}")
    except Exception as exc:
        return redirect(f"/diagnostics?message={quote(str(exc))}")


@app.post("/diagnostics/catalog/rebuild-index")
async def catalog_rebuild_action() -> RedirectResponse:
    paths = get_paths()
    try:
        count = catalog_db.rebuild_search_index(paths.catalog_db_file)
        return redirect(
            f"/diagnostics?notice={quote(f'Catalog search index rebuilt for {count} movies.')}"
        )
    except Exception as exc:
        return redirect(f"/diagnostics?message={quote(str(exc))}")


@app.post("/diagnostics/catalog/retry-failed")
async def catalog_retry_failed_action() -> RedirectResponse:
    paths = get_paths()
    try:
        with catalog_db.transaction(paths.catalog_db_file) as connection:
            rows = connection.execute(
                "SELECT job_id FROM catalog_lookup_jobs WHERE status IN ('FAILED','PAUSED','LINK_PENDING') ORDER BY job_id"
            ).fetchall()
            connection.execute(
                "UPDATE catalog_lookup_jobs SET status='QUEUED',finished_at=NULL,last_error='',updated_at=? "
                "WHERE status IN ('FAILED','PAUSED')",
                (catalog_db.now(),),
            )
        for row in rows:
            start_catalog_job(paths, int(row[0]))
        return redirect(
            f"/diagnostics?notice={quote(f'Queued {len(rows)} catalog jobs for retry or reconciliation.')}"
        )
    except Exception as exc:
        return redirect(f"/diagnostics?message={quote(str(exc))}")


@app.get("/media/{photo_id}")
async def media(
    photo_id: int,
    original: bool = False,
    recognition: bool = False,
) -> StreamingResponse:
    paths = get_paths()
    with db.connect(paths.db_file) as connection:
        row = connection.execute(
            "SELECT original_copy_path,processed_path,preview_path,thumbnail_path,recognition_path "
            "FROM photos WHERE photo_id=? AND kind='product'",
            (photo_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404)
    if original:
        candidate = row[0]
    elif recognition:
        candidate = row[4] or row[1]
    else:
        candidate = row[2] or row[3] or row[1]
    if not candidate or not Path(candidate).is_file():
        raise HTTPException(404)
    return safe_file_response(Path(candidate), media_type="image/jpeg")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> StreamingResponse:
    return safe_file_response(STATIC_ROOT / "favicon.svg", media_type="image/svg+xml")


@app.get("/health")
async def health() -> JSONResponse:
    paths = get_paths()
    database: dict[str, Any] = {
        "state": "unavailable",
        "required": True,
        "integrity": "unavailable",
        "foreign_key_violations": None,
        "schema": {"ok": False, "problems": ["Database was not checked"]},
    }
    try:
        with db.connect(paths.db_file) as connection:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            foreign = len(connection.execute("PRAGMA foreign_key_check").fetchall())
            manifest = db.schema_manifest_report(connection)
        database = {
            "state": "healthy"
            if integrity == "ok" and foreign == 0 and manifest["ok"]
            else "degraded",
            "required": True,
            "integrity": integrity,
            "foreign_key_violations": foreign,
            "schema": manifest,
        }
    except Exception as exc:
        database["error_class"] = type(exc).__name__
        database["safe_summary"] = "Inventory database health check failed"
    catalog_state = "degraded" if getattr(app.state, "catalog_error", "") else "healthy"
    required_ok = database["state"] == "healthy"
    payload = {
        "status": "ok" if required_ok else "unavailable",
        "version": __version__,
        "components": {
            "process": {"state": "alive", "required": True},
            "inventory_database": database,
            "catalog": {
                "state": catalog_state,
                "required": False,
                "safe_summary": redact_text(
                    str(getattr(app.state, "catalog_error", "") or ""),
                    known_secrets=_configured_secrets(),
                ),
            },
        },
        # Kept for v0.9 clients while they migrate to components.
        "schema": database["schema"],
    }
    return JSONResponse(payload, status_code=200 if required_ok else 503)
