"""Opportunity scoring: weighted 0-100 score plus a separate evidence-confidence score.

Each factor is normalised to 0..1 from whatever evidence exists, in priority order:
live Etsy API metrics > imported keyword-tool CSV > analyst-assessed public evidence.
The response always records which inputs were used so the user can see *why*.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from typing import Any

ETSY_LISTING_FEE = 0.20          # per listing and again per sale (auto-renew), USD
ETSY_TRANSACTION_RATE = 0.065    # of item price
ETSY_PROCESSING_RATE = 0.03      # US Etsy Payments
ETSY_PROCESSING_FIXED = 0.25

# How well the built-in design engine can produce each product type automatically (0..1).
AUTOMATION_FEASIBILITY = {
    "wedding_suite": {"score": 0.9, "note": "Fully automated: SVG layouts, live text, 6 coordinated pieces."},
    "wall_art_set": {"score": 0.85, "note": "Automated generative artwork (image-gen optional) in 5 frame ratios."},
    "business_kit": {"score": 0.88, "note": "Automated print + social layouts with an industry content pack."},
    "budget_planner": {"score": 0.92, "note": "Automated multi-page printable PDF (Letter + A4)."},
    "not_supported_yet": {"score": 0.15, "note": "No generator yet. Research only."},
}

FACTORS = ["demand", "competition", "profitability", "automation", "bundle", "seasonal"]
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def etsy_fees(price: float, offsite_ads_rate: float = 0.0) -> float:
    """Per-sale Etsy fees for a digital item (US seller, Etsy Payments)."""
    return round(ETSY_LISTING_FEE + price * (ETSY_TRANSACTION_RATE + ETSY_PROCESSING_RATE + offsite_ads_rate)
                 + ETSY_PROCESSING_FIXED, 2)


def profit_after_fees(price: float, production_cost_per_sale: float = 0.0, offsite_ads_rate: float = 0.0) -> float:
    return round(price - etsy_fees(price, offsite_ads_rate) - production_cost_per_sale, 2)


def _blend(signals: list[tuple[float | None, float, str]]) -> tuple[float, list[str]]:
    present = [(v, w, label) for v, w, label in signals if v is not None]
    if not present:
        return 0.5, ["no evidence - neutral 0.5 assumed"]
    tot = sum(w for _, w, _ in present)
    return clamp(sum(v * w for v, w, _ in present) / tot), [lbl for _, _, lbl in present]


def parse_season(seasonality: str) -> tuple[int, int] | None:
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s*[-–]\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
                  seasonality.lower())
    if not m:
        return None
    return MONTHS.index(m.group(1)) + 1, MONTHS.index(m.group(2)) + 1


def seasonal_score(seasonality: str, today: dt.date | None = None) -> tuple[float, str]:
    today = today or dt.date.today()
    s = (seasonality or "evergreen").lower()
    window = parse_season(s)
    if s.startswith("evergreen") or window is None:
        return 0.75, "Evergreen demand, which supports long-term sales."
    start, end = window
    m = today.month
    months = [(start - 1 + i) % 12 + 1 for i in range(((end - start) % 12) + 1)]
    lead = (start - m) % 12
    if m in months:
        pos = months.index(m) / max(1, len(months) - 1)
        val = clamp(0.95 - 0.6 * pos)
        return val, f"Inside the peak season ({MONTHS[start-1].title()}-{MONTHS[end-1].title()}). " \
                    f"{'Early in the window: good timing.' if pos < 0.4 else 'Late in the window: listings need time to rank.'}"
    if 1 <= lead <= 3:
        return 1.0, f"Peak season starts in about {lead} month(s): ideal time to list."
    return 0.4, f"Off-season (peak {MONTHS[start-1].title()}-{MONTHS[end-1].title()}). Build ahead or skip for now."


def suggested_price(niche_analyst: dict, metrics: dict, is_bundle: bool) -> dict:
    """Pick a price from observed data when available; otherwise from labelled assumptions."""
    if metrics.get("price_median"):
        med = metrics["price_median"]
        p25, p75 = metrics.get("price_p25") or med, metrics.get("price_p75") or med
        price = p75 if is_bundle else med
        return {"price": round(max(2.0, price) - 0.01, 2), "low": p25, "high": p75, "basis": "observed",
                "note": f"From live Etsy API prices (median ${med:.2f}, upper quartile ${p75:.2f})."}
    a = niche_analyst or {}
    if a.get("price_observed") and a.get("price_low") is not None:
        lo, hi = float(a["price_low"]), float(a["price_high"])
        price = lo + (hi - lo) * (0.7 if is_bundle else 0.45)
        return {"price": round(math.ceil(price) - 0.01, 2), "low": lo, "high": hi, "basis": "observed_public",
                "note": a.get("price_note", "Observed in cited public sources.")}
    lo, hi = float(a.get("assumed_price_low", 5)), float(a.get("assumed_price_high", 15))
    price = lo + (hi - lo) * (0.7 if is_bundle else 0.45)
    return {"price": round(math.ceil(price) - 0.01, 2), "low": lo, "high": hi, "basis": "assumption",
            "note": "ASSUMPTION: no observed prices yet. Connect the Etsy API to replace this with live data."}


def score_opportunity(*, niche: dict, product_type: str, metrics: dict, csv_signals: dict, weights: dict,
                      production_cost: float, is_bundle: bool, offsite_ads_rate: float = 0.0,
                      today: dt.date | None = None) -> dict[str, Any]:
    analyst = niche.get("analyst") or {}
    insights = niche.get("insights") or {}
    explain: dict[str, str] = {}
    inputs: dict[str, list[str]] = {}

    # ---- Demand & growth ----
    api_d = None
    if metrics.get("fav_per_month_median") is not None:
        api_d = clamp(math.log10(1 + metrics["fav_per_month_median"]) / math.log10(31))
        if metrics.get("favorites_top10_avg"):
            api_d = 0.6 * api_d + 0.4 * clamp(math.log10(1 + metrics["favorites_top10_avg"]) / math.log10(5001))
    csv_d = None
    if csv_signals.get("searches"):
        csv_d = clamp(math.log10(max(1, csv_signals["searches"])) / math.log10(50000))
    demand, inputs["demand"] = _blend([(api_d, 0.5, "Etsy API engagement"), (csv_d, 0.3, "keyword-tool CSV"),
                                       (analyst.get("demand"), 0.2 if (api_d or csv_d) else 1.0, "analyst-assessed public evidence")])
    explain["demand"] = analyst.get("demand_rationale", "")

    # ---- Competition & differentiation (higher = easier) ----
    api_c = None
    if metrics.get("competing_listings"):
        cnt = metrics["competing_listings"]
        count_score = 1 - clamp((math.log10(max(cnt, 10)) - 2) / 4)  # 100 -> 1.0 ... 1,000,000 -> 0.0
        incumbent = clamp(math.log10(1 + (metrics.get("favorites_top10_avg") or 0)) / math.log10(20001))
        young = metrics.get("share_young_listings_succeeding")
        api_c = 0.5 * count_score + 0.25 * (1 - incumbent) + 0.25 * (clamp((young or 0) * 3) if young is not None else 0.5)
    csv_c = None
    if csv_signals.get("competition"):
        csv_c = 1 - clamp((math.log10(max(csv_signals["competition"], 10)) - 2) / 4)
    competition, inputs["competition"] = _blend([(api_c, 0.5, "Etsy API listing count/incumbents"),
                                                 (csv_c, 0.3, "keyword-tool CSV"),
                                                 (analyst.get("competition"), 0.2 if (api_c or csv_c) else 1.0,
                                                  "analyst-assessed public evidence")])
    gaps = insights.get("gaps") or []
    diff_bonus = min(0.12, 0.04 * len(gaps))
    competition = clamp(competition + diff_bonus)
    explain["competition"] = (analyst.get("competition_rationale", "") +
                              (f" +{diff_bonus:.2f} for {len(gaps)} identified differentiation gap(s)." if gaps else ""))

    # ---- Profitability ----
    pricing = suggested_price(analyst, metrics, is_bundle)
    profit = profit_after_fees(pricing["price"], production_cost, offsite_ads_rate)
    profitability = clamp(profit / 18.0)
    if pricing["basis"] == "assumption":  # don't let assumed prices inflate the ranking
        profitability = 0.5 + (profitability - 0.5) * 0.4
    explain["profitability"] = (f"Suggested ${pricing['price']:.2f}. Etsy fees about ${etsy_fees(pricing['price'], offsite_ads_rate):.2f}, "
                                f"production about ${production_cost:.2f}, so roughly ${profit:.2f} profit per sale ({pricing['basis']}).")
    inputs["profitability"] = [pricing["basis"]]

    # ---- Automation feasibility ----
    feas = AUTOMATION_FEASIBILITY.get(product_type, AUTOMATION_FEASIBILITY["not_supported_yet"])
    automation = feas["score"]
    explain["automation"] = feas["note"]
    inputs["automation"] = ["design engine capability table"]

    # ---- Bundle & personalization ----
    bundle = clamp(0.6 * float(analyst.get("bundle", 0.5)) + 0.4 * float(analyst.get("personalization", 0.5)))
    explain["bundle"] = f"Bundle potential {analyst.get('bundle', 0.5)}, personalization {analyst.get('personalization', 0.5)} (analyst-assessed)."
    inputs["bundle"] = ["analyst-assessed"]

    # ---- Seasonal / long-term ----
    seasonal, explain["seasonal"] = seasonal_score(niche.get("seasonality", "evergreen"), today)
    inputs["seasonal"] = ["seasonality window vs today's date"]

    factors = {"demand": demand, "competition": competition, "profitability": profitability,
               "automation": automation, "bundle": bundle, "seasonal": seasonal}
    wsum = sum(max(0.0, float(weights.get(f, 0))) for f in FACTORS) or 1.0
    score = sum(factors[f] * max(0.0, float(weights.get(f, 0))) for f in FACTORS) / wsum * 100

    confidence = evidence_confidence(niche, metrics, csv_signals, pricing, today)
    return {"score": round(score, 1), "factors": {k: round(v, 3) for k, v in factors.items()},
            "explanations": explain, "inputs": inputs, "pricing": pricing, "profit_per_sale": profit,
            "fees_per_sale": etsy_fees(pricing["price"], offsite_ads_rate), "confidence": confidence}


def evidence_confidence(niche: dict, metrics: dict, csv_signals: dict, pricing: dict,
                        today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    ev = niche.get("evidence") or []
    pts, why = 10.0, ["base 10"]
    n_public = sum(1 for e in ev if e.get("source_type") in ("public_web", "claude_web", "user"))
    pub_pts = min(25.0, 6.0 * n_public)
    if pub_pts:
        pts += pub_pts
        why.append(f"+{pub_pts:.0f} for {n_public} cited public source(s)")
    recent = 0
    for e in ev:
        p = e.get("published")
        if p and re.match(r"\d{4}-\d{2}", p):
            y, mo = int(p[:4]), int(p[5:7])
            if (today.year - y) * 12 + (today.month - mo) <= 12:
                recent += 1
    if recent:
        rp = min(10.0, 3.0 * recent)
        pts += rp
        why.append(f"+{rp:.0f} for {recent} source(s) published in the last 12 months")
    if metrics.get("competing_listings"):
        pts += 35
        why.append("+35 live Etsy API marketplace data")
    if csv_signals:
        pts += 12
        why.append("+12 imported keyword-tool data")
    if pricing.get("basis") in ("observed", "observed_public"):
        pts += 8
        why.append("+8 observed prices")
    else:
        pts -= 5
        why.append("-5 prices are assumptions")
    missing = []
    if not metrics.get("competing_listings"):
        missing.append("live competing-listing counts, prices, favorites and views (needs Etsy API key)")
    missing.append("verified sales volumes (Etsy does not publish them; any sales numbers are estimates)")
    if not csv_signals:
        missing.append("monthly search volumes (import an eRank/EverBee/Marmalead CSV)")
    return {"score": round(clamp(pts, 0, 100), 0), "reasons": why, "unavailable_data": missing}
