"""Bounded, cancellable Playwright collection for eBay Canada sold searches."""

from __future__ import annotations

import asyncio
import os
import random
import threading
from collections.abc import Awaitable, Callable, Iterable, Mapping
from datetime import date
from typing import Any, Protocol

from snapims.pricing.database import PricingDatabase
from snapims.pricing.listing_parser import parse_listings
from snapims.pricing.models import AnalysisStatus, MovieAnalysis
from snapims.pricing.normalization import deduplicate_titles, normalize_title
from snapims.pricing.search_urls import generate_search_url
from snapims.pricing.settings import AppSettings
from snapims.pricing.statistics import calculate_statistics


class CollectionError(RuntimeError):
    def __init__(self, message: str, status: AnalysisStatus) -> None:
        super().__init__(message)
        self.status = status


class ProgressCallback(Protocol):
    def __call__(self, analysis: MovieAnalysis) -> None: ...


class RequestGate(Protocol):
    async def wait_for_turn(
        self, *, title_key: str, job_id: int | None,
        cancel_event: threading.Event, pause_event: threading.Event,
    ) -> str: ...


ListingFetcher = Callable[[str, str, int], Awaitable[list[Mapping[str, object]]]]


def _automation_url(search_url: str) -> str:
    return search_url


def _safe_error_message(exc: BaseException) -> str:
    message = " ".join(str(exc).split())
    if "timeout" in exc.__class__.__name__.casefold():
        return "eBay search timed out. Open the sold search manually, then retry."
    return (message or exc.__class__.__name__)[:500]


def classify_navigation_error(message: str) -> AnalysisStatus:
    lowered = message.casefold()
    if any(signal in lowered for signal in (
        "err_blocked_by_administrator", "err_name_not_resolved", "err_connection_refused",
        "err_internet_disconnected", "name or service not known", "temporary failure in name",
        "network is unreachable", "offline",
    )):
        return AnalysisStatus.NETWORK_UNAVAILABLE
    if "executable doesn't exist" in lowered or "playwright install" in lowered:
        return AnalysisStatus.BROWSER_MISSING
    if "verification" in lowered or "captcha" in lowered:
        return AnalysisStatus.VERIFICATION_REQUIRED
    if "access denied" in lowered or "access blocked" in lowered:
        return AnalysisStatus.ACCESS_BLOCKED
    return AnalysisStatus.FAILED


def classify_rendered_page(body_text: str, page_title: str = "", url: str = "") -> AnalysisStatus | None:
    text = " ".join((body_text, page_title, url)).casefold()
    if any(signal in text for signal in (
        "verify yourself", "security measure", "checking your browser", "press and hold",
        "captcha", "robot check", "confirm you are human", "sign in to your account",
        "signin.ebay.", "auth.ebay.",
    )):
        return AnalysisStatus.VERIFICATION_REQUIRED
    if any(signal in text for signal in (
        "access denied", "access blocked", "request has been blocked", "temporarily blocked",
        "you don't have permission to access",
    )):
        return AnalysisStatus.ACCESS_BLOCKED
    return None


class _RequestScheduler:
    """Controller-local spacing used outside the persistent SnapIMS worker."""

    def __init__(self, settings: AppSettings, sleep=asyncio.sleep, random_uniform=random.uniform):
        self.settings = settings
        self.sleep = sleep
        self.random_uniform = random_uniform
        self.lock = asyncio.Lock()
        self.last_started: float | None = None

    async def wait_for_turn(
        self, *, cancel_event: threading.Event, pause_event: threading.Event
    ) -> str:
        async with self.lock:
            if cancel_event.is_set():
                return "CANCELLED"
            if pause_event.is_set():
                return "PAUSED"
            if self.last_started is not None:
                delay = self.random_uniform(
                    self.settings.delay_min_seconds, self.settings.delay_max_seconds
                )
                elapsed = 0.0
                while elapsed < delay:
                    if cancel_event.is_set():
                        return "CANCELLED"
                    if pause_event.is_set():
                        return "PAUSED"
                    interval = min(0.25, delay - elapsed)
                    await self.sleep(interval)
                    elapsed += interval
            self.last_started = asyncio.get_running_loop().time()
            return "READY"


class PlaywrightController:
    """Analyze titles using a real bounded worker pool and exact persisted evidence."""

    def __init__(
        self,
        settings: AppSettings | None = None,
        database: PricingDatabase | None = None,
        *,
        listing_fetcher: ListingFetcher | None = None,
        request_gate: RequestGate | None = None,
        sleep=asyncio.sleep,
        random_uniform=random.uniform,
    ) -> None:
        self.settings = settings or AppSettings()
        self.database = database or PricingDatabase()
        self._listing_fetcher = listing_fetcher
        self._request_gate = request_gate
        self._sleep = sleep
        self._random_uniform = random_uniform

    @staticmethod
    def _playwright() -> Any:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise CollectionError(
                "Playwright is not installed. Install SnapIMS runtime dependencies.",
                AnalysisStatus.BROWSER_MISSING,
            ) from exc
        return async_playwright

    def analyze_titles(
        self,
        movie_titles: Iterable[str],
        *,
        refresh_titles: Iterable[str] = (),
        cancel_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
        on_update: ProgressCallback | None = None,
        job_ids: Mapping[str, int] | None = None,
    ) -> list[MovieAnalysis]:
        return asyncio.run(
            self._analyze_titles(
                movie_titles, refresh_titles=refresh_titles,
                cancel_event=cancel_event, pause_event=pause_event,
                on_update=on_update, job_ids=job_ids or {},
            )
        )

    async def _analyze_titles(
        self,
        movie_titles: Iterable[str],
        *,
        refresh_titles: Iterable[str],
        cancel_event: threading.Event | None,
        pause_event: threading.Event | None,
        on_update: ProgressCallback | None,
        job_ids: Mapping[str, int],
    ) -> list[MovieAnalysis]:
        titles = deduplicate_titles(movie_titles)
        force_keys = {normalize_title(title) for title in refresh_titles}
        cancellation = cancel_event or threading.Event()
        pausing = pause_event or threading.Event()
        results: dict[str, MovieAnalysis] = {}
        pending: list[str] = []
        for title in titles:
            if cancellation.is_set():
                result = self._simple_result(title, AnalysisStatus.CANCELLED)
            elif pausing.is_set():
                result = self._simple_result(title, AnalysisStatus.PAUSED)
            elif normalize_title(title) not in force_keys:
                cached = self.database.get_analysis(
                    title, max_listings=self.settings.max_sold_listings
                )
                if cached is not None:
                    result = cached
                else:
                    pending.append(title)
                    result = self._simple_result(title, AnalysisStatus.QUEUED)
            else:
                pending.append(title)
                result = self._simple_result(title, AnalysisStatus.QUEUED)
            results[title] = result
            self._notify(on_update, result)
        if pending:
            if self._listing_fetcher is not None:
                await self._run_workers(
                    pending, results, cancellation, pausing, on_update,
                    self._listing_fetcher, job_ids,
                )
            else:
                await self._run_with_playwright(
                    pending, results, cancellation, pausing, on_update, job_ids
                )
        return [results[title] for title in titles]

    def _launch_options(self) -> dict[str, object]:
        options: dict[str, object] = {"headless": self.settings.headless}
        executable = os.getenv("SNAPIMS_PRICING_CHROMIUM_EXECUTABLE", "").strip()
        if executable:
            options["executable_path"] = executable
        return options

    async def probe_runtime(self) -> dict[str, str]:
        browser_status, ebay_status, message = "FAIL", "NOT_TESTED", ""
        try:
            async_playwright = self._playwright()
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(**self._launch_options())
                browser_status = "PASS"
                page = await browser.new_page(locale="en-CA")
                try:
                    await page.goto(
                        "https://www.ebay.ca/", wait_until="domcontentloaded",
                        timeout=self.settings.navigation_timeout_seconds * 1000,
                    )
                    body = await page.locator("body").inner_text()
                    state = classify_rendered_page(body, await page.title(), page.url)
                    if state:
                        ebay_status = state.name
                        message = state.value
                    else:
                        ebay_status = "REACHABLE"
                        message = "Browser launched and ebay.ca returned a rendered page."
                except Exception as exc:
                    message = _safe_error_message(exc)
                    ebay_status = classify_navigation_error(message).name
                finally:
                    await browser.close()
        except CollectionError as exc:
            browser_status, message = "MISSING", str(exc)
        except Exception as exc:
            message = _safe_error_message(exc)
            status = classify_navigation_error(message)
            browser_status = "MISSING" if status == AnalysisStatus.BROWSER_MISSING else "FAIL"
        return {"browser_status": browser_status, "ebay_status": ebay_status, "message": message}

    async def _run_with_playwright(
        self, pending, results, cancellation, pausing, on_update, job_ids
    ) -> None:
        try:
            async_playwright = self._playwright()
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(**self._launch_options())
                await self._run_browser_workers(
                    browser, pending, results, cancellation, pausing, on_update, job_ids
                )
        except Exception as exc:
            message = _safe_error_message(exc)
            status = exc.status if isinstance(exc, CollectionError) else classify_navigation_error(message)
            for title in pending:
                if results[title].status in {AnalysisStatus.QUEUED, AnalysisStatus.ANALYZING}:
                    result = self._failed_result(title, message, status)
                    results[title] = result
                    self._notify(on_update, result)

    async def _run_browser_workers(
        self, browser, pending, results, cancellation, pausing, on_update, job_ids
    ) -> None:
        context = await browser.new_context(locale="en-CA")
        pages = [
            await context.new_page()
            for _ in range(min(self.settings.max_simultaneous_tabs, len(pending)))
        ]
        page_queue: asyncio.Queue[Any] = asyncio.Queue()
        for page in pages:
            page.set_default_timeout(self.settings.navigation_timeout_seconds * 1000)
            await page_queue.put(page)

        async def fetcher(movie: str, search_url: str, maximum: int):
            page = await page_queue.get()
            try:
                return await self._extract_raw_listings(page, search_url, maximum)
            finally:
                await page_queue.put(page)

        try:
            await self._run_workers(
                pending, results, cancellation, pausing, on_update, fetcher, job_ids
            )
        finally:
            await context.close()

    async def _run_workers(
        self, pending, results, cancellation, pausing, on_update, fetcher, job_ids
    ) -> None:
        queue: asyncio.Queue[str] = asyncio.Queue()
        for title in pending:
            await queue.put(title)
        scheduler = _RequestScheduler(
            self.settings, sleep=self._sleep, random_uniform=self._random_uniform
        )

        async def worker() -> None:
            while True:
                try:
                    title = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    if self._request_gate:
                        gate = await self._request_gate.wait_for_turn(
                            title_key=normalize_title(title), job_id=job_ids.get(title),
                            cancel_event=cancellation, pause_event=pausing,
                        )
                    else:
                        gate = await scheduler.wait_for_turn(
                            cancel_event=cancellation, pause_event=pausing
                        )
                    if gate != "READY":
                        status = AnalysisStatus.PAUSED if gate == "PAUSED" else AnalysisStatus.CANCELLED
                        result = self._simple_result(title, status)
                        results[title] = result
                        self._notify(on_update, result)
                        continue
                    analyzing = self._simple_result(title, AnalysisStatus.ANALYZING)
                    results[title] = analyzing
                    self._notify(on_update, analyzing)
                    try:
                        raw = await fetcher(title, analyzing.search_url, self.settings.max_sold_listings)
                        if pausing.is_set():
                            completed = self._simple_result(title, AnalysisStatus.PAUSED)
                        elif cancellation.is_set():
                            completed = self._simple_result(title, AnalysisStatus.CANCELLED)
                        else:
                            listings = parse_listings(title, raw, self.settings.max_sold_listings)
                            statistics = calculate_statistics(listings)
                            completed = MovieAnalysis(
                                movie=title, queried_title=title, title_key=normalize_title(title),
                                search_url=analyzing.search_url,
                                status=(AnalysisStatus.COMPLETE if statistics else AnalysisStatus.NO_VALID_MATCHES),
                                statistics=statistics, listings=listings, analysis_date=date.today(),
                            )
                            self.database.save_analysis(
                                completed, max_listings=self.settings.max_sold_listings,
                                cache_expiry_days=self.settings.cache_expiry_days,
                            )
                        results[title] = completed
                        self._notify(on_update, completed)
                    except Exception as exc:
                        message = _safe_error_message(exc)
                        status = exc.status if isinstance(exc, CollectionError) else classify_navigation_error(message)
                        if status in {AnalysisStatus.VERIFICATION_REQUIRED, AnalysisStatus.ACCESS_BLOCKED}:
                            pausing.set()
                        failed = self._failed_result(title, message, status)
                        results[title] = failed
                        self._notify(on_update, failed)
                finally:
                    queue.task_done()

        count = min(self.settings.max_simultaneous_tabs, len(pending))
        await asyncio.gather(*(worker() for _ in range(count)))

    async def _extract_raw_listings(self, page, search_url: str, maximum: int):
        try:
            await page.goto(
                _automation_url(search_url), wait_until="domcontentloaded",
                timeout=self.settings.navigation_timeout_seconds * 1000,
            )
        except Exception as exc:
            message = _safe_error_message(exc)
            raise CollectionError(message, classify_navigation_error(message)) from exc
        return await self._extract_loaded_page(page, maximum)

    async def _extract_loaded_page(self, page, maximum: int):
        await page.mouse.wheel(0, 900)
        await page.wait_for_timeout(350)
        await page.mouse.wheel(0, -350)
        body = await page.locator("body").inner_text()
        page_state = classify_rendered_page(body, await page.title(), page.url)
        if page_state:
            raise CollectionError(page_state.value, page_state)
        locator = page.locator("li.s-item, li.s-card")
        count = await locator.count()
        if count == 0:
            lowered = body.casefold()
            if any(signal in lowered for signal in (
                "0 results", "no exact matches found", "no results found",
                "we've looked everywhere", "no matching results",
            )):
                return []
            raise CollectionError(
                "No eBay result cards were detected; the rendered layout is unsupported.",
                AnalysisStatus.PARSING_LAYOUT_FAILURE,
            )
        return await locator.evaluate_all(
            """
            (cards) => {
              const text = (card, selectors) => {
                for (const selector of selectors) {
                  const node = card.querySelector(selector);
                  if (node && node.textContent && node.textContent.trim()) return node.textContent.trim();
                }
                return "";
              };
              const href = (card, selectors) => {
                for (const selector of selectors) {
                  const node = card.querySelector(selector);
                  if (node && node.href) return node.href;
                }
                return "";
              };
              return cards.slice(0, 120).map((card) => ({
                listing_title: text(card, [".s-item__title", ".s-card__title", "[role='heading']"]),
                listing_url: href(card, ["a.s-item__link", "a.s-card__link", "a[href*='/itm/']"]),
                sold_price: text(card, [".s-item__price", ".s-card__price", "[class*='price']"]),
                shipping_price: text(card, [".s-item__shipping", ".s-item__logisticsCost", ".s-card__shipping", "[class*='shipping']"]),
                sold_date: text(card, [".s-item__caption--signal", ".s-item__title--tagblock .POSITIVE", ".s-card__caption", ".POSITIVE"])
              }));
            }
            """
        )

    @staticmethod
    def _notify(callback, result) -> None:
        if callback is not None:
            callback(result)

    @staticmethod
    def _simple_result(title: str, status: AnalysisStatus) -> MovieAnalysis:
        return MovieAnalysis(
            movie=title, queried_title=title, title_key=normalize_title(title),
            search_url=generate_search_url(title), status=status,
        )

    @classmethod
    def _failed_result(cls, title: str, error: str, status: AnalysisStatus) -> MovieAnalysis:
        result = cls._simple_result(title, status)
        result.error = error
        return result
