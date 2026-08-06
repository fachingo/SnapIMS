"""SnapIMS-native Pricing Review routes."""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from snapims import __version__, db
from snapims.config import DataPaths
from snapims.money import parse_price_cents
from snapims.pricing.playwright_controller import PlaywrightController
from snapims.pricing.settings import LISTING_LIMIT_OPTIONS, TAB_OPTIONS
from snapims.pricing.workflow import BATCH_MODES, PricingWorkflow
from snapims.pricing.worker import get_worker

router = APIRouter()
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "web" / "templates"
TEMPLATES = Jinja2Templates(directory=str(TEMPLATE_ROOT))


def _paths() -> DataPaths:
    return DataPaths.from_root().ensure()


def _workflow() -> PricingWorkflow:
    return PricingWorkflow(_paths())


def _actor(request: Request) -> str:
    return str(getattr(request.state, "username", "") or "local-operator")


def _context(request: Request, **values):
    return {
        "request": request, "version": __version__,
        "csrf_token": getattr(request.state, "csrf_token", ""), **values,
    }


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


@router.get("/pricing", response_class=HTMLResponse)
async def pricing_review(
    request: Request, batch_id: str | None = None, status: str = "",
    cache_status: str = "", price_status: str = "",
    evidence_min: int = Query(0, ge=0), page: int = Query(1, ge=1),
    notice: str = "", message: str = "",
) -> HTMLResponse:
    workflow = _workflow()
    batches = db.list_batches(_paths().db_file)
    if batch_id is None and batches:
        batch_id = str(batches[0]["batch_id"])
    elif batch_id == "ALL":
        batch_id = ""
    batch_id = batch_id or ""
    items, total = workflow.list_items(
        batch_id=batch_id, status=status, cache_status=cache_status,
        price_status=price_status, evidence_min=evidence_min, page=page, page_size=50,
    )
    settings = workflow.settings()
    return TEMPLATES.TemplateResponse(
        request, "pricing_review.html",
        _context(
            request, batches=batches, batch_id=batch_id,
            batch_mode=workflow.get_batch_mode(batch_id), batch_modes=BATCH_MODES,
            status_filter=status, cache_status=cache_status, price_status=price_status,
            evidence_min=evidence_min, items=items, total=total, page=page,
            pages=max(1, math.ceil(total / 50)), settings=settings,
            listing_options=LISTING_LIMIT_OPTIONS, tab_options=TAB_OPTIONS,
            worker_status=get_worker().status(), diagnostics=workflow.diagnostics(),
            notice=notice, message=message,
        ),
    )


@router.get("/pricing/item/{item_id}", response_class=HTMLResponse)
async def pricing_item(request: Request, item_id: str, notice: str = "", message: str = ""):
    workflow = _workflow()
    item = db.get_item(_paths().db_file, item_id)
    if item is None:
        raise HTTPException(404)
    state = workflow.item_state(item_id, str(item["batch_id"]))
    evidence = workflow.evidence_for_item(item_id)
    valid, stale_reason = workflow.evidence_validity(item_id) if evidence else (False, "")
    title = str(item.get("title") or "")
    return TEMPLATES.TemplateResponse(
        request, "pricing_item.html",
        _context(
            request, item=item, state=state, evidence=evidence,
            evidence_valid=valid, stale_reason=stale_reason,
            evidence_history=workflow.cache.evidence_history(title),
            photos=db.get_item_photos(_paths().db_file, item_id),
            submission_id=uuid4().hex, notice=notice, message=message,
        ),
    )


@router.post("/pricing/batch-mode")
async def set_batch_mode(request: Request, batch_id: str = Form(...), mode: str = Form(...)):
    try:
        _workflow().set_batch_mode(batch_id, mode, actor=_actor(request))
        return _redirect(f"/review?batch_id={quote(batch_id)}&notice={quote('Pricing mode updated for this batch.')}")
    except (ValueError, sqlite3.IntegrityError) as exc:
        return _redirect(f"/review?batch_id={quote(batch_id)}&message={quote(str(exc))}")


@router.post("/pricing/settings")
async def save_pricing_settings(
    request: Request, profile: str = Form(...), concurrency: int = Form(1),
    delay_min: int = Form(15), delay_max: int = Form(30),
    max_listings: int = Form(3), cache_days: int = Form(30),
    headless: bool = Form(False),
):
    try:
        settings = _workflow().save_settings(
            profile=profile, concurrency=concurrency, delay_min=delay_min,
            delay_max=delay_max, max_listings=max_listings, cache_days=cache_days,
            headless=headless, actor=_actor(request),
        )
        notice = (
            f"{settings.profile.title()} pricing settings saved: "
            f"{settings.max_simultaneous_tabs} page(s), "
            f"{settings.delay_min_seconds}-{settings.delay_max_seconds}s delay."
        )
        return _redirect("/pricing?notice=" + quote(notice))
    except ValueError as exc:
        return _redirect("/pricing?message=" + quote(str(exc)))


@router.post("/pricing/item/{item_id}/queue")
async def queue_pricing(request: Request, item_id: str, refresh: bool = Form(False)):
    try:
        state = _workflow().queue_item(item_id, refresh=refresh, actor=_actor(request))
        notice = "Evidence recollection queued." if refresh else f"Pricing state: {state['status']}."
        return _redirect(f"/pricing/item/{quote(item_id)}?notice={quote(notice)}")
    except (KeyError, ValueError, RuntimeError) as exc:
        return _redirect(f"/pricing/item/{quote(item_id)}?message={quote(str(exc))}")


@router.post("/pricing/item/{item_id}/decision")
async def pricing_decision(
    request: Request, item_id: str, decision: str = Form(...),
    manual_price: str = Form(""), advance: bool = Form(False),
    submission_id: str = Form(...),
):
    workflow = _workflow()
    item = db.get_item(_paths().db_file, item_id)
    if item is None:
        raise HTTPException(404)
    try:
        cents = parse_price_cents(manual_price, allow_blank=True)
        workflow.accept_price(
            item_id, decision, manual_price_cents=cents,
            actor=_actor(request), request_id=submission_id,
        )
        if advance:
            next_item = workflow.next_eligible_item(item_id)
            if next_item:
                return _redirect(
                    f"/pricing/item/{quote(next_item)}?notice="
                    + quote("Price approved. Next eligible Item opened.")
                )
            return _redirect(
                f"/pricing?batch_id={quote(str(item['batch_id']))}&notice="
                + quote("Price approved. This was the final eligible Item.")
            )
        return _redirect(f"/pricing/item/{quote(item_id)}?notice={quote('Pricing decision saved.')}")
    except (KeyError, ValueError, RuntimeError) as exc:
        return _redirect(f"/pricing/item/{quote(item_id)}?message={quote(str(exc))}")


@router.post("/pricing/bulk/preview", response_class=HTMLResponse)
async def preview_bulk_pricing(
    request: Request, item_ids: list[str] = Form(default=[]), action: str = Form(...),
    fixed_price: str = Form(""), batch_id: str = Form(""),
):
    unique_ids = list(dict.fromkeys(item_ids))
    if not unique_ids:
        return _redirect(f"/pricing?batch_id={quote(batch_id)}&message={quote('Select at least one Item.')}")
    if action not in {"QUEUE", "CANCEL", "SKIP", "AVERAGE", "MEDIAN", "KEEP", "FIXED"}:
        return _redirect(f"/pricing?batch_id={quote(batch_id)}&message={quote('Unknown bulk action.')}")
    if action == "FIXED":
        try:
            if parse_price_cents(fixed_price, allow_blank=True) is None:
                raise ValueError("Fixed price is required")
        except ValueError as exc:
            return _redirect(f"/pricing?batch_id={quote(batch_id)}&message={quote(str(exc))}")
    workflow = _workflow()
    rows = []
    actual_batches = set()
    for item_id in unique_ids:
        item = db.get_item(_paths().db_file, item_id)
        if item is None:
            return _redirect(f"/pricing?batch_id={quote(batch_id)}&message={quote(f'Item {item_id} no longer exists.')}")
        actual_batches.add(str(item["batch_id"]))
        rows.append({
            "item": item, "state": workflow.item_state(item_id, str(item["batch_id"])),
            "evidence": workflow.evidence_for_item(item_id),
        })
    if len(actual_batches) != 1:
        return _redirect(f"/pricing?batch_id={quote(batch_id)}&message={quote('Select Items from one Batch per bulk action.')}")
    return TEMPLATES.TemplateResponse(
        request, "pricing_bulk_confirm.html",
        _context(
            request, rows=rows, item_ids=unique_ids, action=action,
            fixed_price=fixed_price, batch_id=next(iter(actual_batches)),
            request_id=uuid4().hex,
        ),
    )


@router.post("/pricing/bulk")
async def bulk_pricing(
    request: Request, item_ids: list[str] = Form(default=[]), action: str = Form(...),
    fixed_price: str = Form(""), batch_id: str = Form(""),
    confirmed: bool = Form(False), request_id: str = Form(...),
):
    if not confirmed:
        return _redirect(f"/pricing?batch_id={quote(batch_id)}&message={quote('Bulk action was not confirmed.')}")
    try:
        result = _workflow().bulk_action(
            item_ids, action, fixed_price_cents=parse_price_cents(fixed_price, allow_blank=True),
            actor=_actor(request), request_id=request_id,
        )
        notice = (
            f"Bulk pricing complete: {result.changed} changed, {result.unchanged} unchanged; "
            f"checkpoint {result.checkpoint_id}."
        )
        return _redirect(f"/pricing?batch_id={quote(batch_id)}&notice={quote(notice)}")
    except (KeyError, ValueError, RuntimeError) as exc:
        return _redirect(f"/pricing?batch_id={quote(batch_id)}&message={quote(str(exc))}")


@router.post("/pricing/worker/start")
async def start_worker(request: Request):
    started = get_worker().start()
    return _redirect("/pricing?notice=" + quote("Pricing queue started." if started else "Pricing queue is already running."))


@router.post("/pricing/worker/pause")
async def pause_worker(request: Request):
    count = get_worker().pause()
    return _redirect("/pricing?notice=" + quote(f"Pricing paused. {count} active or pending jobs preserved."))


@router.post("/pricing/worker/cancel")
async def cancel_worker(request: Request):
    count = get_worker().cancel()
    return _redirect("/pricing?notice=" + quote(f"Cancelled {count} active or pending pricing jobs."))


@router.post("/pricing/diagnostics/probe")
async def probe_pricing_runtime(request: Request):
    workflow = _workflow()
    result = await PlaywrightController(
        settings=workflow.settings(), database=workflow.cache
    ).probe_runtime()
    workflow.save_runtime_probe(result)
    return _redirect("/diagnostics?notice=" + quote(f"Browser {result['browser_status']} - eBay {result['ebay_status']}."))


@router.get("/api/pricing/status", response_class=JSONResponse)
async def pricing_status() -> dict:
    workflow = _workflow()
    return {"worker": get_worker().status(), "diagnostics": workflow.diagnostics()}
