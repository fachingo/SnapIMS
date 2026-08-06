"""Persistent bounded pricing queue worker."""

from __future__ import annotations

import threading
from typing import Any

from snapims.pricing.models import AnalysisStatus
from snapims.pricing.playwright_controller import PlaywrightController
from snapims.pricing.throttle import PersistentRequestThrottle
from snapims.pricing.workflow import PricingWorkflow


class PricingWorker:
    def __init__(self, workflow: PricingWorkflow | None = None, *, controller_factory=PlaywrightController) -> None:
        self.workflow = workflow or PricingWorkflow()
        self.controller_factory = controller_factory
        self._thread: threading.Thread | None = None
        self._pause = threading.Event()
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._current_job_ids: list[int] = []

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def current_job_id(self) -> int | None:
        return self._current_job_ids[0] if self._current_job_ids else None

    def start(self) -> bool:
        with self._lock:
            if self.running:
                return False
            self._pause.clear()
            self._cancel.clear()
            self.workflow.resume_paused()
            self._thread = threading.Thread(
                target=self._run, name="snapims-pricing-worker", daemon=True
            )
            self._thread.start()
            return True

    def pause(self) -> int:
        self._pause.set()
        return self.workflow.pause_pending()

    def cancel(self) -> int:
        self._cancel.set()
        return self.workflow.cancel_pending()

    def shutdown(self, timeout: float = 10.0) -> int:
        self._pause.set()
        preserved = self.workflow.pause_pending()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(max(0.0, timeout))
        return preserved

    def status(self) -> dict[str, Any]:
        titles = []
        for job_id in self._current_job_ids:
            job = self.workflow.job(job_id)
            if job:
                titles.append(str(job.get("approved_title") or ""))
        return {
            "running": self.running,
            "state": "PAUSING" if self.running and self._pause.is_set() else "RUNNING" if self.running else "IDLE",
            "current_job_id": self.current_job_id,
            "current_job_ids": list(self._current_job_ids),
            "current_title": ", ".join(titles),
            "active_jobs": len(self._current_job_ids),
            "queue": self.workflow.queue_summary(),
        }

    def _run(self) -> None:
        try:
            while not self._pause.is_set() and not self._cancel.is_set():
                settings = self.workflow.settings()
                jobs = self.workflow.claim_pending_jobs(settings.max_simultaneous_tabs)
                if not jobs:
                    return
                self._current_job_ids = [int(job["job_id"]) for job in jobs]
                throttle = PersistentRequestThrottle(self.workflow.path, settings)
                controller = self.controller_factory(
                    settings=settings, database=self.workflow.cache, request_gate=throttle
                )
                titles = [str(job["approved_title"]) for job in jobs]
                refresh_titles = [
                    str(job["approved_title"]) for job in jobs if int(job["refresh"])
                ]
                job_ids = {str(job["approved_title"]): int(job["job_id"]) for job in jobs}
                try:
                    analyses = controller.analyze_titles(
                        titles, refresh_titles=refresh_titles,
                        cancel_event=self._cancel, pause_event=self._pause,
                        job_ids=job_ids,
                    )
                except Exception as exc:
                    for job in jobs:
                        self.workflow.fail_job(int(job["job_id"]), "FAILED", str(exc))
                    analyses = []
                by_title = {analysis.movie: analysis for analysis in analyses}
                for job in jobs:
                    job_id = int(job["job_id"])
                    analysis = by_title.get(str(job["approved_title"]))
                    if analysis is None:
                        if self._pause.is_set():
                            self.workflow.pause_job(job_id)
                        elif self._cancel.is_set():
                            self.workflow.fail_job(job_id, "CANCELLED", "Cancelled by operator.")
                        continue
                    if analysis.status in {AnalysisStatus.COMPLETE, AnalysisStatus.NO_VALID_MATCHES}:
                        self.workflow.complete_job(job_id, analysis)
                    elif analysis.status == AnalysisStatus.PAUSED:
                        self.workflow.pause_job(job_id)
                    elif analysis.status == AnalysisStatus.CANCELLED:
                        self.workflow.fail_job(job_id, "CANCELLED", "Cancelled by operator.")
                    else:
                        self.workflow.fail_job(job_id, analysis.status.name, analysis.error or analysis.status.value)
                self._current_job_ids = []
        finally:
            self._current_job_ids = []


_WORKER: PricingWorker | None = None
_WORKER_LOCK = threading.Lock()


def get_worker() -> PricingWorker:
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER is None:
            _WORKER = PricingWorker()
        return _WORKER
