"""Etsy Open API v3 client (official API only - no scraping).

Requires an API keystring (+ shared secret) from https://www.etsy.com/developers/your-apps.
Public listing search uses only the API key; creating draft listings needs OAuth (see publish/).

Compliance notes implemented here:
* Rate limited (ETSY_MAX_QPS) and capped per day (ETSY_MAX_DAILY_CALLS).
* Responses cached at most 6 hours (Etsy API Terms: listing content must not be >6h stale).
* The required attribution notice is shown in the dashboard footer (config.ETSY_ATTRIBUTION).
"""
from __future__ import annotations

import hashlib
import json
import statistics
import time
from collections import Counter
from typing import Any

from ..config import log, settings
from ..services import Budget, Cache, ExternalServiceError, RateLimiter, http_request

API_BASE = "https://api.etsy.com/v3/application"


class EtsyNotConfigured(RuntimeError):
    pass


class EtsyClient:
    _limiter: RateLimiter | None = None

    def __init__(self) -> None:
        if not settings.etsy_api_key:
            raise EtsyNotConfigured("ETSY_API_KEY is not set")
        if EtsyClient._limiter is None:
            EtsyClient._limiter = RateLimiter(settings.etsy_qps)

    @staticmethod
    def available() -> bool:
        return bool(settings.etsy_api_key)

    def _headers(self, access_token: str | None = None) -> dict:
        key = settings.etsy_api_key
        if settings.etsy_shared_secret:
            key = f"{key}:{settings.etsy_shared_secret}"
        h = {"x-api-key": key, "Accept": "application/json"}
        if access_token:
            h["Authorization"] = f"Bearer {access_token}"
        return h

    def get(self, path: str, params: dict | None = None, *, cache_hours: float | None = None) -> dict:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        ck = "etsy:" + hashlib.sha1(f"{path}?{json.dumps(params, sort_keys=True)}".encode()).hexdigest()
        ttl = settings.etsy_cache_hours if cache_hours is None else min(cache_hours, settings.etsy_cache_hours)
        cached = Cache.get(ck)
        if cached is not None:
            return cached
        if Budget.calls_today("etsy") >= settings.etsy_daily_calls:
            raise ExternalServiceError("Daily Etsy API call cap reached (ETSY_MAX_DAILY_CALLS). Try again tomorrow.")
        resp = http_request("GET", f"{API_BASE}{path}", params=params, headers=self._headers(), limiter=self._limiter)
        Budget.record("etsy", "api_call", 0.0, units=1, note=path)
        if resp.status_code == 401 or resp.status_code == 403:
            raise ExternalServiceError(f"Etsy rejected the API key ({resp.status_code}). Check ETSY_API_KEY / "
                                       f"ETSY_SHARED_SECRET and that your app is approved. {resp.text[:200]}")
        if resp.status_code >= 400:
            raise ExternalServiceError(f"Etsy API error {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        Cache.set(ck, data, ttl)
        return data

    def search_active_listings(self, keywords: str, limit: int = 100, sort_on: str = "score") -> dict:
        """findAllListingsActive. Returns {'count': total_matching, 'results': [...]}"""
        return self.get("/listings/active", {"keywords": keywords, "limit": min(limit, 100), "sort_on": sort_on,
                                             "sort_order": "desc" if sort_on != "price" else "asc"})

    def seller_taxonomy(self) -> dict:
        return self.get("/seller-taxonomy/nodes", cache_hours=6)


def _price(listing: dict) -> float | None:
    p = listing.get("price") or {}
    try:
        return float(p["amount"]) / float(p.get("divisor") or 100)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None


def listing_metrics(search: dict, now: float | None = None) -> dict[str, Any]:
    """Turn a keyword search response into observable market metrics.

    Everything here is an *engagement indicator* (favorites, views), never verified sales.
    """
    now = now or time.time()
    results = [r for r in (search.get("results") or []) if isinstance(r, dict)]
    digital = [r for r in results if (r.get("type") in (None, "download", "both"))] or results
    prices = [p for p in (_price(r) for r in digital) if p is not None and p > 0]
    favs = [int(r.get("num_favorers") or 0) for r in digital]
    views = [int(r.get("views") or 0) for r in digital if r.get("views") is not None]
    ages_days, fav_velocity = [], []
    for r in digital:
        ts = r.get("original_creation_timestamp") or r.get("creation_timestamp") or r.get("created_timestamp")
        if ts:
            age = max(1.0, (now - float(ts)) / 86400)
            ages_days.append(age)
            fav_velocity.append(int(r.get("num_favorers") or 0) / (age / 30.0))
    young = [r for r in digital if (r.get("original_creation_timestamp") or r.get("creation_timestamp") or now)
             and (now - float(r.get("original_creation_timestamp") or r.get("creation_timestamp") or now)) / 86400 < 365]
    young_success = [r for r in young if int(r.get("num_favorers") or 0) >= 50]
    tag_counter: Counter = Counter()
    for r in digital:
        for t in r.get("tags") or []:
            tag_counter[t.lower().strip()] += 1

    def q(vals: list[float], pct: float) -> float | None:
        if not vals:
            return None
        s = sorted(vals)
        k = (len(s) - 1) * pct
        f, c = int(k), min(int(k) + 1, len(s) - 1)
        return round(s[f] + (s[c] - s[f]) * (k - f), 2)

    m = {
        "competing_listings": int(search.get("count") or 0),
        "sample_size": len(digital),
        "price_p25": q(prices, 0.25), "price_median": q(prices, 0.5), "price_p75": q(prices, 0.75),
        "favorites_median": q([float(f) for f in favs], 0.5),
        "favorites_top10_avg": round(statistics.mean(sorted(favs, reverse=True)[:10]), 1) if favs else None,
        "views_median": q([float(v) for v in views], 0.5) if views else None,
        "fav_per_month_median": q(fav_velocity, 0.5),
        "share_young_listings_succeeding": round(len(young_success) / len(young), 3) if young else None,
        "median_listing_age_days": q(ages_days, 0.5),
        "top_tags": [t for t, _ in tag_counter.most_common(25)],
        "example_listings": [{"title": r.get("title", "")[:140], "url": r.get("url"), "price": _price(r),
                              "favorites": r.get("num_favorers"), "views": r.get("views")} for r in digital[:8]],
    }
    # Rough, clearly-labelled sales estimate: favourites velocity x assumed favourite->purchase ratio.
    if m["fav_per_month_median"] is not None:
        v = m["fav_per_month_median"]
        m["estimated_monthly_sales_per_typical_listing"] = {
            "low": round(v * 0.05, 1), "high": round(v * 0.25, 1),
            "method": "ESTIMATE ONLY: median favourites gained per month x an assumed 5-25% favourite-to-purchase "
                      "ratio. Etsy does not publish sales per listing, and favourites are not sales."}
    log.debug("metrics for search: %s", {k: v for k, v in m.items() if k not in ("top_tags", "example_listings")})
    return m
