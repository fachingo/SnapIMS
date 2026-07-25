from __future__ import annotations

from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from snapims import __version__, db
from snapims.config import DataPaths, ShopifyConfig
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
from snapims.processor import process_batch
from snapims.recognition.providers import recognizer_registry
from snapims.recognition.service import (
    accept_item,
    postpone_item,
    retry_failed_item,
    skip_batch_recognition,
    start_batch_recognition,
)
from snapims.shopify.service import ShopifyService

PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(PACKAGE_ROOT / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    paths = get_paths()
    db.initialize(paths.db_file, paths=paths)
    db.mark_interrupted_jobs_paused(paths.db_file)
    yield


app = FastAPI(title="SnapIMS", version=__version__, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(PACKAGE_ROOT / "static")), name="static")


def get_paths() -> DataPaths:
    return DataPaths.from_root().ensure()


def context(request: Request, **values: Any) -> dict[str, Any]:
    return {"request": request, "version": __version__, **values}


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
def home(request: Request) -> HTMLResponse:
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
def import_page(
    request: Request,
    source_folder: str = "",
    batch_name: str = "",
    message: str = "",
    notice: str = "",
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
        ),
    )


@app.post("/import/use-folder")
def use_folder(
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
def browse_folder(current_folder: str = Form("")) -> RedirectResponse:
    try:
        selected = choose_folder(current_folder)
    except FolderPickerUnavailable as exc:
        return redirect(f"/import?source_folder={quote(current_folder)}&message={quote(str(exc))}")
    if not selected:
        return redirect(f"/import?source_folder={quote(current_folder)}&notice={quote('Folder selection cancelled.')}")
    resolved, error = validate_folder(selected)
    if error:
        return redirect(f"/import?source_folder={quote(selected)}&message={quote(error)}")
    paths = get_paths()
    db.remember_folder(paths.db_file, Path(resolved))
    return redirect(f"/import?source_folder={quote(resolved)}&notice={quote('Folder selected.')}")


@app.post("/import/remove-recent")
def remove_recent_folder(path: str = Form("")) -> RedirectResponse:
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
def import_preview(
    request: Request,
    source_folder: str | None = Form(None),
    batch_name: str = Form(""),
    recursive: bool = Form(False),
) -> HTMLResponse:
    selected, error = validate_folder(source_folder)
    if error:
        return import_context(request, selected=source_folder or "", batch_name=batch_name, message=error)
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
        return import_context(request, selected=selected, batch_name=batch_name, preview=preview)
    except Exception as exc:
        return import_context(request, selected=selected, batch_name=batch_name, message=str(exc))


@app.post("/import/commit", response_class=HTMLResponse)
def import_commit(
    request: Request,
    source_folder: str | None = Form(None),
    batch_name: str = Form(""),
    recursive: bool = Form(False),
) -> HTMLResponse:
    selected, error = validate_folder(source_folder)
    if error:
        return import_context(request, selected=source_folder or "", batch_name=batch_name, message=error)
    try:
        result = process_batch(Path(selected), paths=get_paths(), batch_name=batch_name or None, recursive=recursive)
        db.set_setting(get_paths().db_file, "active_batch", result.batch_id)
        notice = "Existing imported batch opened; no duplicate was created." if result.duplicate else "Batch preserved and imported."
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
def review_page(
    request: Request,
    batch_id: str | None = None,
    queue: str = Query("UNRESOLVED", pattern="^(UNRESOLVED|DONE|FAILED|ALL)$"),
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
        ),
    )


def recognition_status(paths: DataPaths, batch_id: str, job: dict[str, Any] | None) -> tuple[str, str]:
    items = db.list_items(paths.db_file, batch_id=batch_id)
    unfinished = sum(1 for item in items if item["review_status"] == "UNFINISHED")
    if items and unfinished == 0:
        return f"Review complete · {len(items)} of {len(items)} items finished", "complete"
    if not job or job["status"] == "READY":
        return f"{len(items)} items ready to identify", "identify"
    if job["status"] in {"RUNNING", "IDENTIFYING"}:
        remaining = max(0, int(job["total"]) - int(job["completed"]))
        return f"Identifying · {job['completed']} of {job['total']} complete · {remaining} remaining", ""
    if job["status"] == "PAUSED":
        remaining = max(0, int(job["total"]) - int(job["completed"]))
        return f"Identification paused · {job['completed']} of {job['total']} complete · {remaining} remaining", "continue"
    if job["status"] in {"COMPLETE_WITH_FAILURE", "FAILED"}:
        return f"Recognition failed or incomplete · {job['recognized']} ready · {job['failed']} failed", "failure"
    if job["status"] in {"COMPLETE", "REVIEW_COMPLETE"}:
        return f"Recognition complete · {job['recognized']} items ready to review", ""
    return str(job["status"]), ""


@app.post("/review/identify")
def identify(
    batch_id: str = Form(...),
    provider: str = Form("mock"),
    delay: float = Form(0),
) -> RedirectResponse:
    paths = get_paths()
    configured_delay = float(os.getenv("SNAPIMS_MOCK_DELAY", "0") or 0)
    effective_delay = delay if delay > 0 else configured_delay
    try:
        started = start_batch_recognition(paths.db_file, batch_id, provider, delay=effective_delay)
        notice = "Identification started." if started else "Recognition could not start. Review the failure details below."
    except Exception as exc:
        notice = f"Recognition could not start: {exc}"
    return redirect(f"/review?batch_id={quote(batch_id)}&notice={quote(notice)}")


@app.post("/review/retry-batch")
def retry_batch(
    batch_id: str = Form(...),
    provider: str = Form("mock"),
    failed_only: bool = Form(False),
) -> RedirectResponse:
    try:
        started = start_batch_recognition(
            get_paths().db_file,
            batch_id,
            provider,
            retry_failed=True,
        )
        notice = "Retry started." if started else "Retry could not start. Review the updated failure details."
    except Exception as exc:
        notice = f"Retry failed: {exc}"
    return redirect(f"/review?batch_id={quote(batch_id)}&notice={quote(notice)}")


@app.post("/review/manual")
def continue_manual_review(batch_id: str = Form(...)) -> RedirectResponse:
    items = db.list_items(get_paths().db_file, batch_id=batch_id, queue="UNRESOLVED")
    target = items[0]["item_id"] if items else ""
    url = f"/review?batch_id={quote(batch_id)}&queue=UNRESOLVED&edit=true&notice={quote('Manual review opened. AI recognition is not required.') }"
    if target:
        url += f"&item_id={quote(target)}"
    return redirect(url)


@app.post("/review/skip-recognition")
def skip_recognition(batch_id: str = Form(...)) -> RedirectResponse:
    skip_batch_recognition(get_paths().db_file, batch_id)
    return redirect(
        f"/review?batch_id={quote(batch_id)}&queue=UNRESOLVED&notice="
        + quote("Recognition skipped. Items remain unfinished for manual review.")
    )


@app.get("/review/job/{batch_id}")
def job_status(batch_id: str) -> dict[str, Any]:
    paths = get_paths()
    job = db.get_recognition_job(paths.db_file, batch_id)
    text, action = recognition_status(paths, batch_id, job)
    return {"job": job, "text": text, "action": action, "health": db.batch_health(paths.db_file, batch_id)}


@app.post("/review/approve")
def approve(
    batch_id: str = Form(...),
    item_id: str = Form(...),
    price: str = Form(""),
    discount: str = Form("0"),
) -> RedirectResponse:
    try:
        price_cents = int(round(float(price) * 100)) if price.strip() else None
        discount_percent = float(discount or 0)
    except ValueError:
        return redirect(
            f"/review?batch_id={quote(batch_id)}&item_id={quote(item_id)}&edit=true&errors="
            + quote("Price or discount is invalid")
        )
    errors = accept_item(
        get_paths().db_file,
        item_id,
        price_cents=price_cents,
        discount_percent=discount_percent,
    )
    if errors:
        message = "|".join(
            "This tape has no title from AI or previous edits. Enter a title before approval."
            if error == "Title is required"
            else error
            for error in errors
        )
        return redirect(
            f"/review?batch_id={quote(batch_id)}&item_id={quote(item_id)}&edit=true&errors={quote(message)}"
        )
    unresolved = db.list_items(get_paths().db_file, batch_id=batch_id, queue="UNRESOLVED")
    target = unresolved[0]["item_id"] if unresolved else ""
    if target:
        db.set_cursor(get_paths().db_file, batch_id, "UNRESOLVED", target)
        return redirect(
            f"/review?batch_id={quote(batch_id)}&queue=UNRESOLVED&item_id={quote(target)}&notice="
            + quote("Approved. Next unfinished tape opened.")
        )
    return redirect(f"/review?batch_id={quote(batch_id)}&queue=DONE&notice={quote('Review complete.')}")


@app.post("/review/later")
def later(batch_id: str = Form(...), item_id: str = Form(...)) -> RedirectResponse:
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
def navigate(
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
    return redirect(f"/review?batch_id={quote(batch_id)}&queue={quote(queue)}&item_id={quote(target_id)}")


@app.post("/review/retry")
def retry(
    batch_id: str = Form(...),
    item_id: str = Form(...),
    provider: str = Form("mock"),
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
def save_item(
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
    tags: str = Form(""),
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
            "price_cents": int(round(float(price) * 100)) if price.strip() else None,
            "discount_percent": float(discount or 0),
            "quantity": quantity,
            "condition": condition,
            "shelf": shelf.strip().upper(),
            "rare": int(rare),
            "review": int(review),
            "vendor": vendor.strip() or "Canada VHS",
            "product_type": product_type.strip() or "VHS Tape",
            "tags": tags.strip(),
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
    except Exception as exc:
        return redirect(
            f"/review?batch_id={quote(batch_id)}&queue={quote(queue)}&item_id={quote(item_id)}&edit=true&errors={quote(str(exc))}"
        )
    return redirect(
        f"/review?batch_id={quote(batch_id)}&queue=DONE&item_id={quote(item_id)}&notice="
        + quote("Changes saved to the same immutable Item ID.")
    )


@app.get("/batch-editor", response_class=HTMLResponse)
def batch_editor(request: Request, batch_id: str | None = None, notice: str = "") -> HTMLResponse:
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
        ),
    )


def normalize_editor_value(field: str, value: Any) -> Any:
    if field == "price_cents":
        if value in (None, ""):
            return None
        return int(round(float(value) * 100)) if isinstance(value, str) else int(value)
    if field in {"discount_percent"}:
        return float(value or 0)
    if field in {"quantity", "release_year"}:
        return int(value) if value not in (None, "") else None
    if field in {"rare", "review", "ready"}:
        return int(bool(value))
    if field == "shelf":
        return str(value).strip().upper()
    return str(value or "").strip()


@app.get("/api/batches/{batch_id}/items")
def api_batch_items(batch_id: str) -> dict[str, Any]:
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
        "tags",
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
            expected_revision=int(payload.get("revision")) if payload.get("revision") is not None else None,
        )
        validate_items(paths.db_file, [item_id])
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=409)
    saved = db.get_item(paths.db_file, item_id)
    return JSONResponse({"ok": True, "item": saved, "health": db.batch_health(paths.db_file, saved["batch_id"])})


@app.get("/api/items/{item_id}/photos")
def api_item_photos(item_id: str) -> dict[str, Any]:
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
    paths = get_paths()
    payload = await request.json()
    item_ids = [str(value) for value in payload.get("item_ids", [])]
    action = str(payload.get("action") or "")
    if not item_ids:
        return JSONResponse({"ok": False, "error": "Select at least one item"}, status_code=400)
    items = {item["item_id"]: item for item in db.list_items(paths.db_file, batch_id=batch_id)}
    unknown = [item_id for item_id in item_ids if item_id not in items]
    if unknown:
        return JSONResponse({"ok": False, "error": f"Item is not in this batch: {unknown[0]}"}, status_code=400)
    checkpoint_id = db.create_batch_checkpoint(
        paths.db_file,
        batch_id,
        reason=f"Before bulk action {action}",
        source="BULK_EDIT",
    )
    changed = 0
    errors: list[str] = []
    for item_id in item_ids:
        item = items[item_id]
        updates: dict[str, Any]
        reason = str(payload.get("reason") or "Bulk edit")
        try:
            if action == "set_price":
                updates = {"price_cents": int(round(float(payload.get("value")) * 100))}
            elif action == "add_price":
                updates = {"price_cents": int(item.get("price_cents") or 0) + int(round(float(payload.get("value")) * 100))}
            elif action == "subtract_percent":
                percent = float(payload.get("value") or 0)
                current_price = int(item.get("price_cents") or 0)
                updates = {"price_cents": max(0, int(round(current_price * (100 - percent) / 100)))}
            elif action == "round_price":
                increment_cents = int(round(float(payload.get("value") or 0.50) * 100))
                if increment_cents <= 0:
                    raise ValueError("Rounding increment must be greater than zero")
                current_price = int(item.get("price_cents") or 0)
                updates = {"price_cents": int(round(current_price / increment_cents)) * increment_cents}
            elif action == "set_discount":
                updates = {"discount_percent": float(payload.get("value") or 0)}
            elif action == "set_location":
                updates = {"shelf": str(payload.get("value") or "").upper()}
            elif action == "flag_review":
                updates = {"review": 1}
            elif action == "clear_review":
                updates = {"review": 0}
            elif action == "mark_rare":
                updates = {"rare": 1}
            elif action == "clear_rare":
                updates = {"rare": 0}
            elif action == "append_tags":
                incoming = str(payload.get("value") or "").strip()
                existing = [part.strip() for part in str(item.get("tags") or "").split(",") if part.strip()]
                for part in [part.strip() for part in incoming.split(",") if part.strip()]:
                    if part not in existing:
                        existing.append(part)
                updates = {"tags": ", ".join(existing)}
            elif action == "prefix_description":
                prefix = str(payload.get("value") or "")
                updates = {"description": prefix + str(item.get("description") or "")}
            elif action == "replace_description":
                old, separator, new = str(payload.get("value") or "").partition("=>")
                if not separator or not old:
                    raise ValueError("Use find=>replace for description replacement")
                updates = {"description": str(item.get("description") or "").replace(old, new)}
            elif action == "approve":
                approve_errors = accept_item(
                    paths.db_file,
                    item_id,
                    price_cents=item.get("price_cents"),
                    discount_percent=float(item.get("discount_percent") or 0),
                    review_source="BATCH_EDITOR_REVIEW",
                )
                if approve_errors:
                    errors.append(f"{item_id}: {approve_errors[0]}")
                    continue
                changed += 1
                continue
            else:
                return JSONResponse({"ok": False, "error": "Unknown bulk action"}, status_code=400)
            updates["working_source"] = "BULK_EDIT"
            db.update_item(paths.db_file, item_id, updates, source="BULK_EDIT", reason=reason)
            changed += 1
        except Exception as exc:
            errors.append(f"{item_id}: {exc}")
    validate_items(paths.db_file, item_ids)
    return JSONResponse(
        {
            "ok": not errors,
            "changed": changed,
            "errors": errors,
            "checkpoint_id": checkpoint_id,
            "health": db.batch_health(paths.db_file, batch_id),
        },
        status_code=200 if changed else 400,
    )


@app.post("/api/checkpoints/{checkpoint_id}/restore")
def restore_checkpoint(checkpoint_id: int) -> JSONResponse:
    try:
        count = db.restore_batch_checkpoint(get_paths().db_file, checkpoint_id)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return JSONResponse({"ok": True, "restored": count})


@app.get("/publish", response_class=HTMLResponse)
def publish_page(
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
def download_csv(batch_id: str) -> FileResponse:
    paths = get_paths()
    destination = paths.exports / f"{batch_id}-inventory_work.csv"
    export_inventory_csv(paths.db_file, batch_id, destination)
    return FileResponse(destination, media_type="text/csv", filename=destination.name)


@app.post("/publish/csv/preview")
def upload_csv_preview(
    request: Request,
    batch_id: str = Form(...),
    csv_file: UploadFile = File(...),
) -> HTMLResponse:
    paths = get_paths()
    try:
        raw = csv_file.file.read()
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
        return publish_page(request, batch_id=batch_id, message=f"CSV upload failed: {exc}")


@app.get("/publish/csv/diff/{token}", response_class=HTMLResponse)
def csv_diff_page(request: Request, token: str) -> HTMLResponse:
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
def apply_csv(token: str = Form(...), confirmation: bool = Form(False)) -> RedirectResponse:
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
        return redirect(
            f"/publish?batch_id={quote(batch_id)}&message=" + quote(f"CSV was not applied: {exc}")
        )
    return redirect(
        f"/publish?batch_id={quote(batch_id)}&notice="
        + quote(f"CSV applied to {changed} items. Rollback checkpoint {checkpoint_id} created.")
    )


@app.post("/publish/csv/cancel")
def cancel_csv(token: str = Form(...), batch_id: str = Form(...)) -> RedirectResponse:
    db.delete_csv_staging(get_paths().db_file, token)
    return redirect(f"/publish?batch_id={quote(batch_id)}&notice={quote('CSV upload cancelled. No working values changed.')}")


@app.get("/publish/csv/difference-report/{token}")
def difference_report(token: str) -> FileResponse:
    stage = db.get_csv_staging(get_paths().db_file, token)
    if stage is None:
        raise HTTPException(404)
    destination = get_paths().exports / f"{stage['batch_id']}-csv-difference-{token[:8]}.json"
    destination.write_text(json.dumps(stage["diff"] | {"rows": stage["payload"]}, indent=2), encoding="utf-8")
    return FileResponse(destination, media_type="application/json", filename=destination.name)


@app.post("/publish/external-review")
def external_review(
    batch_id: str = Form(...),
    confirmation: bool = Form(False),
) -> RedirectResponse:
    if not confirmation:
        return redirect(f"/publish?batch_id={quote(batch_id)}&message={quote('External review confirmation is required.')}")
    count, errors = mark_batch_externally_reviewed(get_paths().db_file, batch_id)
    if errors:
        return redirect(f"/publish?batch_id={quote(batch_id)}&message={quote(errors[0])}")
    return redirect(
        f"/publish?batch_id={quote(batch_id)}&notice="
        + quote(f"{count} items marked externally reviewed.")
    )


@app.post("/publish/restore-checkpoint")
def publish_restore_checkpoint(
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
def settings_page(request: Request, message: str = "") -> HTMLResponse:
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
def save_settings(incoming_folder: str = Form(...)) -> RedirectResponse:
    resolved, error = validate_folder(incoming_folder)
    if error:
        return redirect(f"/settings?message={quote(error)}")
    db.set_setting(get_paths().db_file, "incoming_folder", resolved)
    return redirect(f"/settings?message={quote('Settings saved.')}")


@app.get("/diagnostics", response_class=HTMLResponse)
def diagnostics(request: Request) -> HTMLResponse:
    paths = get_paths()
    with db.connect(paths.db_file) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
        schema = connection.execute("PRAGMA user_version").fetchone()[0]
        jobs = [dict(row) for row in connection.execute("SELECT rowid AS job_rowid,* FROM recognition_jobs ORDER BY updated_at DESC LIMIT 10")]
        csv_failures = [dict(row) for row in connection.execute("SELECT token,batch_id,filename,created_at,blocking_errors_json FROM csv_staging ORDER BY created_at DESC LIMIT 10")]
    providers = {name: provider.available() for name, provider in recognizer_registry().items()}
    diagnostic_summary = {
        "version": __version__,
        "database": str(paths.db_file),
        "schema": schema,
        "integrity": integrity,
        "foreign_key_violations": len(foreign),
        "providers": providers,
        "media": db.media_totals(paths.db_file),
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
            summary=db.database_summary(paths.db_file),
            providers=providers,
            jobs=jobs,
            csv_failures=csv_failures,
            media_totals=db.media_totals(paths.db_file),
            diagnostic_summary=json.dumps(diagnostic_summary, indent=2),
        ),
    )


@app.get("/media/{photo_id}")
def media(photo_id: int, original: bool = False, recognition: bool = False) -> FileResponse:
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
    return FileResponse(Path(candidate), media_type="image/jpeg")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
