from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from .storage import ProjectStore

LOGGER = logging.getLogger(__name__)

JobCallable = Callable[[threading.Event, Callable[[int], None]], Any]


def now() -> str:
    return datetime.now(UTC).isoformat()


class JobManager:
    def __init__(self, store: ProjectStore, *, max_workers: int = 4) -> None:
        self.store = store
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="adbgath-job")
        self._futures: dict[str, Future[Any]] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._lock = threading.RLock()

    def submit(self, action: str, payload: dict[str, Any], function: JobCallable) -> dict[str, Any]:
        job_id = f"job_{uuid.uuid4().hex[:16]}"
        cancel_event = threading.Event()
        job = {
            "id": job_id,
            "action": action,
            "status": "queued",
            "progress": 0,
            "payload": payload,
            "result": None,
            "error": None,
            "created_at": now(),
            "started_at": None,
            "completed_at": None,
        }
        self.store.save_job(job)

        def progress(value: int) -> None:
            current = self.store.get_job(job_id)
            current["progress"] = max(0, min(100, int(value)))
            self.store.save_job(current)

        def runner() -> None:
            current = self.store.get_job(job_id)
            current.update(status="running", started_at=now(), progress=1)
            self.store.save_job(current)
            try:
                result = function(cancel_event, progress)
                current = self.store.get_job(job_id)
                if cancel_event.is_set():
                    current.update(status="cancelled", completed_at=now())
                else:
                    current.update(status="completed", progress=100, result=result, completed_at=now())
                self.store.save_job(current)
            except Exception as exc:  # job boundary
                LOGGER.exception("Background job %s failed", job_id)
                current = self.store.get_job(job_id)
                current.update(
                    status="failed",
                    error=f"{type(exc).__name__}: {exc}",
                    result=None,
                    completed_at=now(),
                )
                self.store.save_job(current)

        with self._lock:
            self._cancel[job_id] = cancel_event
            self._futures[job_id] = self.executor.submit(runner)
        return job

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            event = self._cancel.get(job_id)
            future = self._futures.get(job_id)
        if event is None:
            return self.store.get_job(job_id)
        event.set()
        if future:
            future.cancel()
        job = self.store.get_job(job_id)
        if job["status"] == "queued":
            job.update(status="cancelled", completed_at=now())
            self.store.save_job(job)
        elif job["status"] == "running":
            job.update(status="cancelling")
            self.store.save_job(job)
        return self.store.get_job(job_id)

    def get(self, job_id: str) -> dict[str, Any]:
        return self.store.get_job(job_id)

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.store.list_jobs(limit)
