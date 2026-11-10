"""Scheduled market research (e.g. daily). Uses APScheduler inside the app process."""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import log
from .db import get_setting

_sched: BackgroundScheduler | None = None


def _run_daily():
    from . import jobs
    log.info("Scheduled daily automation starting")
    jobs.submit("daily_automation", {"trigger": "scheduled"})


def start() -> None:
    global _sched
    if _sched is None:
        _sched = BackgroundScheduler(daemon=True)
        _sched.start()
    reload()


def reload() -> dict:
    if _sched is None:
        return {"enabled": False}
    cfg = get_setting("schedule")
    _sched.remove_all_jobs()
    if cfg.get("enabled"):
        _sched.add_job(_run_daily, CronTrigger(hour=int(cfg.get("hour", 7)), minute=int(cfg.get("minute", 30))),
                       id="daily", replace_existing=True, misfire_grace_time=3600, coalesce=True)
        nxt = _sched.get_job("daily").next_run_time
        log.info("Daily automation scheduled, next run %s", nxt)
        return {"enabled": True, "next_run": nxt.isoformat() if nxt else None}
    return {"enabled": False}


def shutdown() -> None:
    if _sched:
        _sched.shutdown(wait=False)
