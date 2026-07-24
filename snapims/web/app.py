from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from snapims import __version__, db
from snapims.config import DataPaths, ShopifyConfig
from snapims.inventory import CONDITIONS, POOL_MODES, export_inventory_csv, validation_errors
from snapims.pipeline import parse_batch
from snapims.processor import process_batch
from snapims.recognition.providers import recognizer_registry
from snapims.recognition.service import (
    accept_item,
    postpone_item,
    retry_failed_item,
    start_batch_recognition,
)
from snapims.shopify.service import ShopifyService

PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(PACKAGE_ROOT / "templates"))


def get_paths() -> DataPaths:
    return DataPaths.from_root().ensure()


@asynccontextmanager
async def lifespan(app: FastAPI):
    paths = get_paths()
    db.initialize(paths.db_file, paths=paths)
    db.mark_interrupted_jobs_paused(paths.db_file)
    yield


app = FastAPI(title="SnapIMS", version=__version__, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(PACKAGE_ROOT / "static")), name="static")


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


def physical_context(items: list[dict[str, Any]], current: dict[str, Any] | None) -> dict[str, Any]:
    if not current:
        return {"position": 0, "total": len(items), "unfinished": 0}
    all_batch = db.list_items(get_paths().db_file, batch_id=current["batch_id"])
    unfinished = sum(1 for row in all_batch if row["review_status"] == "UNFINISHED")
    return {"position": int(current["sequence"]), "total": len(all_batch), "unfinished": unfinished}


def resolve_item(paths: DataPaths, batch_id: str, queue: str, item_id: str | None) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
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
    active_items = db.list_items(paths.db_file, batch_id=active) if active else []
    ready = sum(1 for item in active_items if item["validation_status"] == "READY")
    unfinished = sum(1 for item in active_items if item["review_status"] == "UNFINISHED")
    return TEMPLATES.TemplateResponse(request, "home.html", context(request, batches=batches, summary=summary, active=active, ready=ready, unfinished=unfinished))


@app.get("/import", response_class=HTMLResponse)
def import_page(request: Request, source_folder: str = "", batch_name: str = "", message: str = "") -> HTMLResponse:
    paths = get_paths()
    configured = db.get_setting(paths.db_file, "incoming_folder", str(paths.incoming))
    selected = source_folder or configured
    recent = db.recent_folders(paths.db_file)
    available = Path(selected).expanduser().is_dir()
    return TEMPLATES.TemplateResponse(request, "import.html", context(request, configured=configured, selected=selected, recent=recent, available=available, batch_name=batch_name, preview=None, imported=None, message=message))


@app.post("/import/use-folder", response_class=HTMLResponse)
def use_folder(path: str = Form(...), save_as_incoming: bool = Form(False)) -> RedirectResponse:
    paths = get_paths()
    resolved = Path(path).expanduser().resolve()
    if save_as_incoming:
        db.set_setting(paths.db_file, "incoming_folder", str(resolved))
    return redirect(f"/import?source_folder={quote(str(resolved))}")


@app.post("/import/preview", response_class=HTMLResponse)
def import_preview(request: Request, source_folder: str = Form(...), batch_name: str = Form(""), recursive: bool = Form(False)) -> HTMLResponse:
    paths = get_paths()
    selected = str(Path(source_folder).expanduser().resolve())
    configured = db.get_setting(paths.db_file, "incoming_folder", str(paths.incoming))
    recent = db.recent_folders(paths.db_file)
    try:
        batch = parse_batch(Path(selected), batch_name=batch_name or None, recursive=recursive)
        preview = {"items": len(batch.items), "photos": batch.photo_count, "commands": len(batch.commands), "warnings": batch.warnings, "recursive": recursive}
        available = True
        error = ""
    except Exception as exc:
        preview = None
        available = Path(selected).is_dir()
        error = str(exc)
    return TEMPLATES.TemplateResponse(request, "import.html", context(request, configured=configured, selected=selected, recent=recent, available=available, batch_name=batch_name, preview=preview, imported=None, message=error))


@app.post("/import/commit", response_class=HTMLResponse)
def import_commit(request: Request, source_folder: str = Form(...), batch_name: str = Form(""), recursive: bool = Form(False)) -> HTMLResponse:
    paths = get_paths()
    selected = str(Path(source_folder).expanduser().resolve())
    configured = db.get_setting(paths.db_file, "incoming_folder", str(paths.incoming))
    recent = db.recent_folders(paths.db_file)
    try:
        result = process_batch(Path(selected), paths=paths, batch_name=batch_name or None, recursive=recursive)
        db.set_setting(paths.db_file, "active_batch", result.batch_id)
        imported = result
        error = ""
    except Exception as exc:
        imported = None
        error = str(exc)
    return TEMPLATES.TemplateResponse(request, "import.html", context(request, configured=configured, selected=selected, recent=recent, available=Path(selected).is_dir(), batch_name=batch_name, preview=None, imported=imported, message=error))


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
        return TEMPLATES.TemplateResponse(request, "review.html", context(request, batches=[], batch_id="", queue=queue, items=[], all_items=[], current=None, photos=[], suggestion=None, history=[], job=None, status_text="", status_action="", providers=recognizer_registry(), physical={}, edit=edit, errors=[], notice=notice, photo_index=1))
    db.set_setting(paths.db_file, "active_batch", batch_id)
    items, current = resolve_item(paths, batch_id, queue, item_id)
    all_items = db.list_items(paths.db_file, batch_id=batch_id)
    photos = db.get_item_photos(paths.db_file, current["item_id"]) if current else []
    photo_index = max(1, min(photo, len(photos) or 1))
    suggestion = db.latest_recognition(paths.db_file, current["item_id"]) if current else None
    history = db.recognition_history(paths.db_file, current["item_id"]) if current else []
    job = db.get_recognition_job(paths.db_file, batch_id)
    status_text, status_action = recognition_status(paths, batch_id, job)
    physical = physical_context(items, current)
    decoded_errors = [part for part in errors.split("|") if part]
    return TEMPLATES.TemplateResponse(request, "review.html", context(request, batches=batches, batch_id=batch_id, queue=queue, items=items, all_items=all_items, current=current, photos=photos, suggestion=suggestion, history=history, job=job, status_text=status_text, status_action=status_action, providers=recognizer_registry(), physical=physical, edit=edit, errors=decoded_errors, notice=notice, photo_index=photo_index, conditions=CONDITIONS, pool_modes=POOL_MODES))


def recognition_status(paths: DataPaths, batch_id: str, job: dict[str, Any] | None) -> tuple[str, str]:
    items = db.list_items(paths.db_file, batch_id=batch_id)
    unfinished = sum(1 for item in items if item["review_status"] == "UNFINISHED")
    if items and unfinished == 0:
        return f"Review complete · {len(items)} of {len(items)} items finished", ""
    if not job or job["status"] == "READY":
        return f"{len(items)} items ready to identify", "identify"
    if job["status"] == "RUNNING":
        remaining = max(0, int(job["total"]) - int(job["completed"]))
        return f"Identifying · {job['completed']} of {job['total']} complete · {remaining} remaining", ""
    if job["status"] == "PAUSED":
        remaining = max(0, int(job["total"]) - int(job["completed"]))
        return f"Identification paused · {job['completed']} of {job['total']} complete · {remaining} remaining", "continue"
    if job["status"] == "COMPLETE_WITH_FAILURE":
        return f"Recognition complete · {job['recognized']} ready · {job['failed']} failed", "failure"
    if job["status"] in {"COMPLETE", "REVIEW_COMPLETE"}:
        return f"Recognition complete · {job['recognized']} items ready to review", ""
    return str(job["status"]), ""


@app.post("/review/identify")
def identify(batch_id: str = Form(...), provider: str = Form("mock"), delay: float = Form(0)) -> RedirectResponse:
    paths = get_paths()
    start_batch_recognition(paths.db_file, batch_id, provider, delay=delay)
    return redirect(f"/review?batch_id={quote(batch_id)}")


@app.get("/review/job/{batch_id}")
def job_status(batch_id: str) -> dict[str, Any]:
    paths = get_paths()
    job = db.get_recognition_job(paths.db_file, batch_id)
    text, action = recognition_status(paths, batch_id, job)
    return {"job": job, "text": text, "action": action}


@app.post("/review/approve")
def approve(
    batch_id: str = Form(...),
    item_id: str = Form(...),
    price: str = Form(""),
    discount: str = Form("0"),
) -> RedirectResponse:
    paths = get_paths()
    try:
        price_cents = int(round(float(price) * 100)) if price.strip() else None
        discount_percent = float(discount or 0)
    except ValueError:
        return redirect(f"/review?batch_id={quote(batch_id)}&item_id={quote(item_id)}&edit=true&errors={quote('Price or discount is invalid')}")
    errors = accept_item(paths.db_file, item_id, price_cents=price_cents, discount_percent=discount_percent)
    if errors:
        return redirect(f"/review?batch_id={quote(batch_id)}&item_id={quote(item_id)}&edit=true&errors={quote('|'.join(errors))}")
    unresolved = db.list_items(paths.db_file, batch_id=batch_id, queue="UNRESOLVED")
    target = unresolved[0]["item_id"] if unresolved else ""
    if target:
        db.set_cursor(paths.db_file, batch_id, "UNRESOLVED", target)
        return redirect(f"/review?batch_id={quote(batch_id)}&queue=UNRESOLVED&item_id={quote(target)}&notice={quote('Approved. Next unfinished tape opened.')}")
    return redirect(f"/review?batch_id={quote(batch_id)}&queue=DONE&notice={quote('Review complete.')}")


@app.post("/review/later")
def later(batch_id: str = Form(...), item_id: str = Form(...)) -> RedirectResponse:
    paths = get_paths()
    postpone_item(paths.db_file, item_id)
    items = db.list_items(paths.db_file, batch_id=batch_id, queue="UNRESOLVED")
    target = next_item(items, item_id)
    target_id = target["item_id"] if target else item_id
    db.set_cursor(paths.db_file, batch_id, "UNRESOLVED", target_id)
    return redirect(f"/review?batch_id={quote(batch_id)}&queue=UNRESOLVED&item_id={quote(target_id)}&notice={quote('Tape postponed and remains unfinished.')}")


@app.post("/review/navigate")
def navigate(batch_id: str = Form(...), queue: str = Form(...), item_id: str = Form(...), direction: str = Form(...)) -> RedirectResponse:
    paths = get_paths()
    items = db.list_items(paths.db_file, batch_id=batch_id, queue=queue)
    target = previous_item(items, item_id) if direction == "previous" else next_item(items, item_id)
    target_id = target["item_id"] if target else item_id
    db.set_cursor(paths.db_file, batch_id, queue, target_id)
    return redirect(f"/review?batch_id={quote(batch_id)}&queue={quote(queue)}&item_id={quote(target_id)}")


@app.post("/review/retry")
def retry(batch_id: str = Form(...), item_id: str = Form(...), provider: str = Form("mock")) -> RedirectResponse:
    paths = get_paths()
    try:
        retry_failed_item(paths.db_file, item_id, provider)
        notice = "Recognition recovered. Review the suggestion."
    except Exception as exc:
        notice = str(exc)
    return redirect(f"/review?batch_id={quote(batch_id)}&queue=UNRESOLVED&item_id={quote(item_id)}&notice={quote(notice)}")


@app.post("/review/save")
def save_item(
    batch_id: str = Form(...), item_id: str = Form(...), queue: str = Form(...),
    title: str = Form(""), release_year: str = Form(""), barcode: str = Form(""),
    distributor: str = Form(""), edition: str = Form(""), price: str = Form(""),
    discount: str = Form("0"), quantity: int = Form(1), condition: str = Form("Not Graded"),
    shelf: str = Form("Q1"), location_reason: str = Form(""), rare: bool = Form(False),
    review: bool = Form(False), vendor: str = Form("Canada VHS"), product_type: str = Form("VHS Tape"),
    tags: str = Form(""), condition_notes: str = Form(""), description: str = Form(""),
    pool_mode: str = Form("POOLED"), revision: int = Form(0),
) -> RedirectResponse:
    paths = get_paths()
    current = db.get_item(paths.db_file, item_id)
    if current is None:
        raise HTTPException(404)
    try:
        values = {
            "title": title.strip(), "release_year": int(release_year) if release_year.strip() else None,
            "barcode": barcode.strip(), "distributor": distributor.strip(), "edition": edition.strip(),
            "price_cents": int(round(float(price) * 100)) if price.strip() else None,
            "discount_percent": float(discount or 0), "quantity": quantity, "condition": condition,
            "shelf": shelf.strip().upper(), "rare": int(rare), "review": int(review),
            "vendor": vendor.strip() or "Canada VHS", "product_type": product_type.strip() or "VHS Tape",
            "tags": tags.strip(), "condition_notes": condition_notes.strip(), "description": description.strip(),
            "pool_mode": pool_mode, "ready": 1, "review_status": "DONE", "postponed_at": None,
        }
    except ValueError:
        return redirect(f"/review?batch_id={quote(batch_id)}&queue={quote(queue)}&item_id={quote(item_id)}&edit=true&errors={quote('Numeric field is invalid')}")
    candidate = {**current, **values}
    errors = validation_errors(candidate, db.get_item_photos(paths.db_file, item_id))
    if errors:
        return redirect(f"/review?batch_id={quote(batch_id)}&queue={quote(queue)}&item_id={quote(item_id)}&edit=true&errors={quote('|'.join(errors))}")
    try:
        db.update_item(paths.db_file, item_id, values, source="ITEM_EDITOR", reason=location_reason, expected_revision=revision)
        from snapims.inventory import validate_items
        validate_items(paths.db_file, [item_id])
    except Exception as exc:
        return redirect(f"/review?batch_id={quote(batch_id)}&queue={quote(queue)}&item_id={quote(item_id)}&edit=true&errors={quote(str(exc))}")
    return redirect(f"/review?batch_id={quote(batch_id)}&queue=DONE&item_id={quote(item_id)}&notice={quote('Changes saved to the same immutable Item ID.')}")


@app.get("/publish", response_class=HTMLResponse)
def publish_page(request: Request, batch_id: str | None = None, simulate: bool = False) -> HTMLResponse:
    paths = get_paths()
    batches = db.list_batches(paths.db_file)
    batch_id = selected_batch(paths, batch_id)
    items = db.list_items(paths.db_file, batch_id=batch_id) if batch_id else []
    service = ShopifyService(paths.db_file, ShopifyConfig.from_env())
    reports = [service.dry_run(item["item_id"]) for item in items] if simulate else []
    ready = sum(1 for report in (reports or [service.dry_run(item["item_id"]) for item in items]) if report.ready)
    blocked = len(items) - ready
    return TEMPLATES.TemplateResponse(request, "publish.html", context(request, batches=batches, batch_id=batch_id, items=items, reports=reports, ready=ready, blocked=blocked))


@app.get("/publish/csv/{batch_id}")
def download_csv(batch_id: str) -> FileResponse:
    paths = get_paths()
    destination = paths.exports / f"{batch_id}-inventory_work.csv"
    export_inventory_csv(paths.db_file, batch_id, destination)
    return FileResponse(destination, media_type="text/csv", filename=destination.name)


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, message: str = "") -> HTMLResponse:
    paths = get_paths()
    providers = {name: provider.available() for name, provider in recognizer_registry().items()}
    return TEMPLATES.TemplateResponse(request, "settings.html", context(request, incoming=db.get_setting(paths.db_file, "incoming_folder", str(paths.incoming)), recent=db.recent_folders(paths.db_file), providers=providers, message=message))


@app.post("/settings")
def save_settings(incoming_folder: str = Form(...)) -> RedirectResponse:
    paths = get_paths()
    resolved = str(Path(incoming_folder).expanduser().resolve())
    db.set_setting(paths.db_file, "incoming_folder", resolved)
    return redirect(f"/settings?message={quote('Settings saved.')}")


@app.get("/diagnostics", response_class=HTMLResponse)
def diagnostics(request: Request) -> HTMLResponse:
    paths = get_paths()
    with db.connect(paths.db_file) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign = connection.execute("PRAGMA foreign_key_check").fetchall()
        schema = connection.execute("PRAGMA user_version").fetchone()[0]
    return TEMPLATES.TemplateResponse(request, "diagnostics.html", context(request, paths=paths, integrity=integrity, foreign=len(foreign), schema=schema, summary=db.database_summary(paths.db_file)))


@app.get("/media/{photo_id}")
def media(photo_id: int) -> FileResponse:
    paths = get_paths()
    with db.connect(paths.db_file) as connection:
        row = connection.execute("SELECT processed_path FROM photos WHERE photo_id=? AND kind='product'", (photo_id,)).fetchone()
    if not row or not Path(row[0]).is_file():
        raise HTTPException(404)
    return FileResponse(Path(row[0]), media_type="image/jpeg")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
