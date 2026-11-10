"""Cross-cutting services: spending limits, caching, rate limiting and HTTP retries."""
from __future__ import annotations

import datetime as dt
import random
import threading
import time
from typing import Any, Callable

import requests
from sqlalchemy import func, select

from .config import log
from .db import CacheEntry, Spend, get_setting, session_scope, utcnow


class BudgetExceeded(RuntimeError):
    """Raised before a paid call would push spending past a configured limit."""


class Budget:
    """Tracks API spend and blocks calls that would exceed daily / monthly limits."""

    _lock = threading.Lock()

    @staticmethod
    def spent(since: dt.datetime) -> float:
        with session_scope() as s:
            total = s.scalar(select(func.coalesce(func.sum(Spend.cost_usd), 0.0)).where(Spend.created_at >= since))
            return float(total or 0.0)

    @classmethod
    def status(cls) -> dict:
        cfg = get_setting("budget")
        now = utcnow()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)
        today, month = cls.spent(day_start), cls.spent(month_start)
        return {
            "today_usd": round(today, 4), "month_usd": round(month, 4),
            "daily_limit_usd": cfg["daily_usd"], "monthly_limit_usd": cfg["monthly_usd"],
            "daily_remaining_usd": round(max(0.0, cfg["daily_usd"] - today), 4),
            "monthly_remaining_usd": round(max(0.0, cfg["monthly_usd"] - month), 4),
        }

    @classmethod
    def check(cls, estimated_cost: float, what: str) -> None:
        st = cls.status()
        if estimated_cost > st["daily_remaining_usd"] + 1e-9:
            raise BudgetExceeded(f"Daily spending limit reached: {what} would cost about ${estimated_cost:.2f}, "
                                 f"${st['daily_remaining_usd']:.2f} left today. Raise the limit in Settings.")
        if estimated_cost > st["monthly_remaining_usd"] + 1e-9:
            raise BudgetExceeded(f"Monthly spending limit reached: {what} would cost about ${estimated_cost:.2f}, "
                                 f"${st['monthly_remaining_usd']:.2f} left this month.")

    @classmethod
    def record(cls, provider: str, kind: str, cost_usd: float, units: float = 1, note: str = "") -> None:
        with cls._lock, session_scope() as s:
            s.add(Spend(provider=provider, kind=kind, cost_usd=cost_usd, units=units, note=note[:300]))

    @classmethod
    def calls_today(cls, provider: str) -> int:
        day_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        with session_scope() as s:
            return int(s.scalar(select(func.coalesce(func.sum(Spend.units), 0)).where(
                Spend.provider == provider, Spend.created_at >= day_start)) or 0)


class Cache:
    @staticmethod
    def get(key: str) -> Any | None:
        with session_scope() as s:
            row = s.get(CacheEntry, key)
            if row is None:
                return None
            if row.expires_at < utcnow():
                s.delete(row)
                return None
            return row.value

    @staticmethod
    def set(key: str, value: Any, ttl_hours: float) -> None:
        with session_scope() as s:
            row = s.get(CacheEntry, key)
            exp = utcnow() + dt.timedelta(hours=ttl_hours)
            if row is None:
                s.add(CacheEntry(key=key, value=value, expires_at=exp))
            else:
                row.value, row.expires_at = value, exp

    @staticmethod
    def purge_expired() -> int:
        with session_scope() as s:
            rows = s.scalars(select(CacheEntry).where(CacheEntry.expires_at < utcnow())).all()
            for r in rows:
                s.delete(r)
            return len(rows)


class RateLimiter:
    """Simple thread-safe token bucket."""

    def __init__(self, per_second: float):
        self.interval = 1.0 / max(per_second, 0.01)
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if self._next > now:
                time.sleep(self._next - now)
                now = time.monotonic()
            self._next = now + self.interval


class ExternalServiceError(RuntimeError):
    pass


def http_request(method: str, url: str, *, retries: int = 4, backoff: float = 1.5,
                 limiter: RateLimiter | None = None, timeout: float = 30, **kwargs) -> requests.Response:
    """HTTP with retries on 429/5xx/connection errors and exponential backoff + jitter."""
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        if limiter:
            limiter.wait()
        try:
            resp = requests.request(method, url, timeout=timeout, **kwargs)
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else backoff ** attempt
                last_err = ExternalServiceError(f"{resp.status_code} from {url.split('?')[0]}")
                log.warning("HTTP %s from %s (attempt %d) - retrying in %.1fs", resp.status_code, url.split('?')[0],
                            attempt + 1, delay)
                time.sleep(delay + random.random() * 0.3)
                continue
            return resp
        except requests.RequestException as e:  # network problem
            last_err = e
            delay = backoff ** attempt
            log.warning("Network error calling %s: %s (attempt %d)", url.split('?')[0], e, attempt + 1)
            time.sleep(delay)
    raise ExternalServiceError(f"Request to {url.split('?')[0]} failed after {retries + 1} attempts: {last_err}")


def with_retries(fn: Callable, attempts: int = 3, delay: float = 1.0) -> Any:
    last = None
    for i in range(attempts):
        try:
            return fn()
        except BudgetExceeded:
            raise
        except Exception as e:  # noqa: BLE001
            last = e
            log.warning("Attempt %d/%d failed: %s", i + 1, attempts, e)
            time.sleep(delay * (i + 1))
    raise last  # type: ignore[misc]
