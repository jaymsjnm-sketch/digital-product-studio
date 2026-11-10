"""Background job runner with progress reporting, step tracking and retry support.

Jobs are persisted in the database so the dashboard can show progress and the user
can retry a failed step. Work runs in a small thread pool (no Redis needed).
"""
from __future__ import annotations

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from .config import log, settings
from .db import Job, session_scope, utcnow
from .services import BudgetExceeded

_REGISTRY: dict[str, Callable[["JobContext"], dict]] = {}
_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()


def job(kind: str):
    def deco(fn):
        _REGISTRY[kind] = fn
        return fn
    return deco


class JobContext:
    def __init__(self, job_id: int, payload: dict):
        self.job_id = job_id
        self.payload = payload

    def progress(self, pct: float, message: str = "") -> None:
        with session_scope() as s:
            j = s.get(Job, self.job_id)
            j.progress = max(0.0, min(100.0, pct))
            if message:
                j.message = message
        if message:
            log.info("job %s: %s (%.0f%%)", self.job_id, message, pct)

    def step(self, name: str, status: str = "running", detail: str = "") -> None:
        with session_scope() as s:
            j = s.get(Job, self.job_id)
            steps = [dict(x) for x in (j.steps or [])]
            for st in steps:
                if st["name"] == name:
                    st.update(status=status, detail=detail)
                    break
            else:
                steps.append({"name": name, "status": status, "detail": detail})
            j.steps = steps


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=settings.max_workers, thread_name_prefix="dps-job")
        return _executor


def _run(job_id: int) -> None:
    with session_scope() as s:
        j = s.get(Job, job_id)
        kind, payload = j.kind, dict(j.payload or {})
        j.status, j.attempts, j.error = "running", j.attempts + 1, ""
    fn = _REGISTRY.get(kind)
    ctx = JobContext(job_id, payload)
    try:
        if fn is None:
            raise RuntimeError(f"Unknown job type: {kind}")
        result = fn(ctx) or {}
        with session_scope() as s:
            j = s.get(Job, job_id)
            j.status, j.progress, j.result = "done", 100.0, result
            j.message = result.get("message", "Finished")
    except BudgetExceeded as e:
        _fail(job_id, str(e), "")
    except Exception as e:  # noqa: BLE001
        log.error("job %s (%s) failed: %s", job_id, kind, e)
        _fail(job_id, f"{type(e).__name__}: {e}", traceback.format_exc())


def _fail(job_id: int, msg: str, tb: str) -> None:
    with session_scope() as s:
        j = s.get(Job, job_id)
        j.status = "failed"
        j.error = msg
        j.message = "Failed - you can retry this job"
        j.result = {**(j.result or {}), "traceback": tb[-4000:]}
        steps = [dict(x) for x in (j.steps or [])]
        for st in steps:
            if st.get("status") == "running":
                st["status"] = "failed"
        j.steps = steps


def submit(kind: str, payload: dict | None = None, *, sync: bool = False) -> int:
    with session_scope() as s:
        j = Job(kind=kind, payload=payload or {}, status="queued", created_at=utcnow())
        s.add(j)
        s.flush()
        job_id = j.id
    if sync:
        _run(job_id)
    else:
        _get_executor().submit(_run, job_id)
    return job_id


def retry(job_id: int, *, sync: bool = False) -> int:
    with session_scope() as s:
        j = s.get(Job, job_id)
        if j is None:
            raise KeyError(job_id)
        j.status, j.progress, j.message, j.error = "queued", 0, "Retrying", ""
        # keep completed steps so step functions can skip finished work
    if sync:
        _run(job_id)
    else:
        _get_executor().submit(_run, job_id)
    return job_id


def job_dict(j: Job) -> dict:
    return {"id": j.id, "kind": j.kind, "status": j.status, "progress": j.progress, "message": j.message,
            "error": j.error, "attempts": j.attempts, "steps": j.steps or [], "payload": j.payload,
            "result": {k: v for k, v in (j.result or {}).items() if k != "traceback"},
            "created_at": j.created_at.isoformat() + "Z", "updated_at": (j.updated_at or j.created_at).isoformat() + "Z"}


def recover_interrupted() -> None:
    """Mark jobs left 'running' by a previous crash/restart as failed so they can be retried."""
    with session_scope() as s:
        for j in s.query(Job).filter(Job.status.in_(["running", "queued"])).all():
            j.status, j.message, j.error = "failed", "Interrupted by restart - click Retry", "Interrupted"
