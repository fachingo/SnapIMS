"""Thread-safe background job state for the Streamlit UI."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from snapims.pricing.database import PricingDatabase
from snapims.pricing.models import AnalysisStatus, MovieAnalysis
from snapims.pricing.playwright_controller import PlaywrightController
from snapims.pricing.settings import AppSettings

TERMINAL_STATUSES = {
    AnalysisStatus.COMPLETE,
    AnalysisStatus.NO_VALID_MATCHES,
    AnalysisStatus.VERIFICATION_REQUIRED,
    AnalysisStatus.ACCESS_BLOCKED,
    AnalysisStatus.PARSING_LAYOUT_FAILURE,
    AnalysisStatus.BROWSER_MISSING,
    AnalysisStatus.NETWORK_UNAVAILABLE,
    AnalysisStatus.FAILED,
    AnalysisStatus.CANCELLED,
    AnalysisStatus.PAUSED,
}


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    total: int
    completed: int
    current_movie: str
    results: dict[str, MovieAnalysis]
    running: bool
    cancel_requested: bool
    elapsed_seconds: float
    estimated_remaining_seconds: float | None


class AnalysisJob:
    """Own a controller thread without accessing Streamlit session state."""

    def __init__(
        self,
        movie_titles: Iterable[str],
        settings: AppSettings,
        database: PricingDatabase,
        *,
        refresh_titles: Iterable[str] = (),
        controller_factory: Callable[..., PlaywrightController] = PlaywrightController,
    ) -> None:
        self._titles = list(movie_titles)
        self._settings = settings
        self._database = database
        self._refresh_titles = list(refresh_titles)
        self._controller_factory = controller_factory
        self._lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._finished_event = threading.Event()
        self._results: dict[str, MovieAnalysis] = {}
        self._terminal_movies: set[str] = set()
        self._current_movie = "Waiting to start"
        self._start_time = 0.0
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("analysis job can only be started once")
        self._start_time = time.monotonic()
        self._thread = threading.Thread(target=self._run, name="pricing-analysis", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel_event.set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._finished_event.wait(timeout)

    def snapshot(self) -> JobSnapshot:
        with self._lock:
            completed = len(self._terminal_movies)
            results = dict(self._results)
            current = self._current_movie
        elapsed = max(0.0, time.monotonic() - self._start_time) if self._start_time else 0.0
        remaining = None
        if completed:
            average = elapsed / completed
            remaining = average * max(0, len(self._titles) - completed)
        return JobSnapshot(
            total=len(self._titles),
            completed=completed,
            current_movie=current,
            results=results,
            running=not self._finished_event.is_set(),
            cancel_requested=self._cancel_event.is_set(),
            elapsed_seconds=elapsed,
            estimated_remaining_seconds=remaining,
        )

    def _on_update(self, result: MovieAnalysis) -> None:
        with self._lock:
            self._results[result.movie] = result
            if result.status == AnalysisStatus.ANALYZING:
                self._current_movie = result.movie
            if result.status in TERMINAL_STATUSES:
                self._terminal_movies.add(result.movie)

    def _run(self) -> None:
        try:
            controller = self._controller_factory(settings=self._settings, database=self._database)
            results = controller.analyze_titles(
                self._titles,
                refresh_titles=self._refresh_titles,
                cancel_event=self._cancel_event,
                on_update=self._on_update,
            )
            with self._lock:
                self._results = {result.movie: result for result in results}
                self._terminal_movies.update(
                    result.movie for result in results if result.status in TERMINAL_STATUSES
                )
                self._current_movie = "Complete"
        finally:
            self._finished_event.set()
