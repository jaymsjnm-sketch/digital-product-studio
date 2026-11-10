"""Research engine: gathers evidence from authorised sources, discovers sub-niches,
creates product concepts and ranks them with the scoring engine.

Sources (each optional, each labelled in the UI):
  public_web  - curated, dated public evidence (seed_evidence.json) + user-added evidence
  etsy_api    - Etsy Open API v3 listing search (needs ETSY_API_KEY)
  csv_import  - keyword exports from tools you subscribe to (eRank, EverBee, Marmalead) or Etsy stats
  claude_web  - optional AI web research with citations (needs ANTHROPIC_API_KEY; spend-limited)
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ..config import log, settings
from ..db import Evidence, Niche, Opportunity, Product, ResearchRun, get_setting, session_scope, utcnow
from ..scoring.engine import score_opportunity
from ..services import Budget, BudgetExceeded, ExternalServiceError, http_request
from .concepts import PRODUCT_TYPE_INFO, concepts_for_niche
from .etsy_client import EtsyClient, EtsyNotConfigured, listing_metrics

SEED_FILE = Path(__file__).with_name("seed_evidence.json")
GENERIC_WORDS = {"printable", "digital", "download", "template", "templates", "editable", "instant", "set", "of", "for",
                 "the", "and", "a", "print", "prints", "bundle", "pdf", "canva", "diy"}


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:110]


def classify_product_type(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ("wedding", "bridal", "seating chart", "welcome sign")):
        return "wedding_suite"
    if any(k in t for k in ("wall art", "print set", "poster", "gallery wall", "art print")):
        return "wall_art_set"
    if any(k in t for k in ("flyer", "price list", "social media", "instagram", "business", "realtor", "real estate", "salon")):
        return "business_kit"
    if any(k in t for k in ("budget", "planner", "tracker", "habit")) and "digital planner" not in t and "goodnotes" not in t:
        return "budget_planner"
    return "not_supported_yet"


# ----------------------------------------------------------------- seed / import
def load_seed(force: bool = False) -> int:
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    retrieved = dt.datetime.fromisoformat(data["meta"]["retrieved"])
    added = 0
    with session_scope() as s:
        for n in data["niches"]:
            row = s.scalar(select(Niche).where(Niche.slug == n["slug"]))
            if row is None:
                row = Niche(slug=n["slug"])
                s.add(row)
            elif not force:
                # keep live metrics, refresh curated fields
                pass
            row.name, row.category = n["name"], n["category"]
            row.keywords = n["keywords"]
            row.seasonality = n.get("seasonality", "evergreen")
            row.discovered = bool(n.get("discovered", False))
            row.parent_slug = n.get("parent")
            row.analyst = {**n.get("analyst", {}), "product_types": n.get("product_types", []),
                           "business_industry": n.get("business_industry"), "art_theme": n.get("art_theme"),
                           "planner_kind": n.get("planner_kind"), "risk_flags": n.get("risk_flags", [])}
            row.insights = n.get("insights", {})
            s.flush()
            existing = {(e.url, e.claim) for e in row.evidence}
            for e in n.get("evidence", []):
                if (e["url"], e["claim"]) in existing:
                    continue
                s.add(Evidence(niche_id=row.id, kind=e["kind"], claim=e["claim"], value=e.get("value"),
                               source_title=e.get("source_title", ""), url=e["url"], published=e.get("published"),
                               source_type="public_web", retrieved_at=retrieved))
                added += 1
    return added


def import_keyword_csv(content: str, source_name: str = "csv") -> dict:
    """Import keyword research exported from a tool you subscribe to.

    Accepted columns (case-insensitive, extra columns ignored):
      keyword (required), searches|avg_searches|volume, competition|competing_listings,
      ctr, avg_price|price, niche (optional - otherwise matched by keyword overlap)
    """
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")
    cols = {c.lower().strip(): c for c in reader.fieldnames}

    def col(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None
    kcol = col("keyword", "keywords", "search term", "tag")
    if not kcol:
        raise ValueError("CSV needs a 'keyword' column")
    scol, ccol = col("searches", "avg_searches", "avg searches", "volume", "search volume"), col("competition", "competing_listings", "competing listings")
    ctrcol, pcol, ncol = col("ctr"), col("avg_price", "price", "average price"), col("niche")

    def num(v):
        try:
            return float(str(v).replace(",", "").replace("%", "").replace("$", "").strip())
        except (TypeError, ValueError):
            return None

    imported, created = 0, 0
    with session_scope() as s:
        niches = s.scalars(select(Niche)).all()
        for r in reader:
            kw = (r.get(kcol) or "").strip().lower()
            if not kw:
                continue
            target = None
            if ncol and r.get(ncol):
                target = next((n for n in niches if n.slug == slugify(r[ncol]) or n.name.lower() == r[ncol].lower()), None)
            if target is None:
                kw_words = set(kw.split())
                best, best_overlap = None, 0
                for n in niches:
                    for nk in n.keywords or []:
                        ov = len(kw_words & set(nk.split()))
                        if ov > best_overlap:
                            best, best_overlap = n, ov
                target = best if best_overlap >= 2 else None
                if target is not None:
                    known = {w for k in (target.keywords or []) for w in k.split()}
                    novel = kw_words - known - GENERIC_WORDS
                    if novel and kw not in (target.keywords or []):
                        slug = slugify(kw)
                        child = s.scalar(select(Niche).where(Niche.slug == slug))
                        if child is None:
                            child = Niche(slug=slug, name=kw.title() + " (sub-niche)", category=target.category,
                                          keywords=[kw], seasonality=target.seasonality, discovered=True,
                                          parent_slug=target.slug,
                                          analyst={k: v for k, v in (target.analyst or {}).items()
                                                   if k not in ("demand", "competition")},
                                          insights=target.insights)
                            s.add(child)
                            s.flush()
                            niches.append(child)
                            created += 1
                        target = child
            if target is None:
                pt = classify_product_type(kw)
                target = Niche(slug=slugify(kw), name=kw.title(), category="Discovered", keywords=[kw],
                               discovered=True, analyst={"product_types": [pt]}, insights={})
                s.add(target)
                s.flush()
                niches.append(target)
                created += 1
            data = {"keyword": kw, "searches": num(r.get(scol)) if scol else None,
                    "competition": num(r.get(ccol)) if ccol else None, "ctr": num(r.get(ctrcol)) if ctrcol else None,
                    "avg_price": num(r.get(pcol)) if pcol else None}
            s.add(Evidence(niche_id=target.id, kind="keyword", source_type="csv_import", claim=f"Keyword data for '{kw}'",
                           value=data["searches"], source_title=source_name, url="", data=data,
                           published=utcnow().strftime("%Y-%m")))
            if kw not in (target.keywords or []):
                target.keywords = list(target.keywords or []) + [kw]
            imported += 1
    return {"imported_rows": imported, "new_niches": created}


# ----------------------------------------------------------------- live sources
class _Kw:
    """Detached keyword holder so network calls never run inside a DB transaction."""
    def __init__(self, keywords):
        self.keywords = keywords


def gather_etsy_metrics(niche, client: EtsyClient, max_keywords: int = 2) -> dict:
    merged: list[dict] = []
    for kw in (niche.keywords or [])[:max_keywords]:
        res = client.search_active_listings(kw, limit=100)
        m = listing_metrics(res)
        m["keyword"] = kw
        merged.append(m)
    if not merged:
        return {}
    def avg(key):
        vals = [m[key] for m in merged if m.get(key) is not None]
        return round(sum(vals) / len(vals), 3) if vals else None
    out = {k: avg(k) for k in ("price_p25", "price_median", "price_p75", "favorites_median", "favorites_top10_avg",
                               "views_median", "fav_per_month_median", "share_young_listings_succeeding",
                               "median_listing_age_days")}
    out["competing_listings"] = int(max(m["competing_listings"] for m in merged))
    out["per_keyword"] = [{k: m[k] for k in ("keyword", "competing_listings", "price_median", "favorites_median")}
                          for m in merged]
    tags = Counter()
    for m in merged:
        for i, t in enumerate(m["top_tags"]):
            tags[t] += 25 - i
    out["top_tags"] = [t for t, _ in tags.most_common(20)]
    out["example_listings"] = [e for m in merged for e in m["example_listings"]][:8]
    if merged[0].get("estimated_monthly_sales_per_typical_listing"):
        out["estimated_monthly_sales_per_typical_listing"] = merged[0]["estimated_monthly_sales_per_typical_listing"]
    out["fetched_at"] = utcnow().isoformat() + "Z"
    return out


def discover_from_tags(s, niche: Niche, metrics: dict, known_keywords: set[str], limit: int = 2) -> list[Niche]:
    """New sub-niches = multi-word tags that recur among competitors but aren't tracked yet."""
    found = []
    for tag in metrics.get("top_tags", []):
        if len(found) >= limit:
            break
        if len(tag.split()) < 2 or tag in known_keywords or any(tag in k or k in tag for k in known_keywords):
            continue
        slug = slugify(tag)
        if s.scalar(select(Niche).where(Niche.slug == slug)):
            continue
        child = Niche(slug=slug, name=tag.title() + " (sub-niche)", category=niche.category, keywords=[tag],
                      seasonality=niche.seasonality, discovered=True, parent_slug=niche.slug,
                      analyst={**{k: v for k, v in (niche.analyst or {}).items() if k not in ("demand", "competition")},
                               "demand_rationale": f"Discovered: recurring competitor tag in '{niche.name}'.",
                               "competition_rationale": "Measured from live Etsy data on the next run."},
                      insights=niche.insights)
        s.add(child)
        s.flush()
        s.add(Evidence(niche_id=child.id, kind="keyword", source_type="etsy_api",
                       claim=f"'{tag}' is a frequent tag among top Etsy listings for '{niche.keywords[0]}'",
                       url="https://www.etsy.com/search?q=" + tag.replace(" ", "+")))
        found.append(child)
        known_keywords.add(tag)
    return found


def claude_web_research(run_notes: list[str], max_searches: int = 5) -> list[dict]:
    """Optional: ask Claude (with the web_search tool) for emerging digital-product niches, with citations."""
    if not settings.anthropic_api_key:
        raise EtsyNotConfigured("ANTHROPIC_API_KEY not set")
    est = 0.01 * max_searches + 0.10
    Budget.check(est, "AI web research")
    prompt = (
        "You are an Etsy digital-products market researcher. Today is " + dt.date.today().isoformat() + ". "
        "Use web search to find up to 5 emerging or under-served Etsy DIGITAL product niches (printables, templates, "
        "wall art, planners) with credible 2025-2026 demand evidence. Only use public sources; do not scrape Etsy. "
        "Return ONLY JSON: {\"niches\":[{\"name\":str,\"keywords\":[str],\"seasonality\":str,\"demand\":0-1,"
        "\"demand_rationale\":str,\"competition\":0-1 (1=easy),\"evidence\":[{\"claim\":str,\"source_title\":str,"
        "\"url\":str,\"published\":\"YYYY-MM\"}]}]}. Never invent numbers or URLs.")
    resp = http_request("POST", "https://api.anthropic.com/v1/messages", timeout=180, headers={
        "x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": settings.anthropic_model, "max_tokens": 4000, "messages": [{"role": "user", "content": prompt}],
              "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}]})
    if resp.status_code >= 400:
        raise ExternalServiceError(f"Anthropic API error {resp.status_code}: {resp.text[:300]}")
    body = resp.json()
    usage = body.get("usage", {})
    searches = (usage.get("server_tool_use") or {}).get("web_search_requests", 0)
    cost = usage.get("input_tokens", 0) * 3e-6 + usage.get("output_tokens", 0) * 15e-6 + searches * 0.01
    Budget.record("anthropic", "web_research", cost, note=f"{searches} searches")
    text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        run_notes.append("AI web research returned no parseable JSON.")
        return []
    try:
        return json.loads(m.group(0)).get("niches", [])
    except json.JSONDecodeError:
        run_notes.append("AI web research JSON could not be parsed.")
        return []


# ----------------------------------------------------------------- main run
def niche_dict(n: Niche) -> dict:
    return {"id": n.id, "slug": n.slug, "name": n.name, "category": n.category, "keywords": n.keywords,
            "seasonality": n.seasonality, "discovered": n.discovered, "parent_slug": n.parent_slug,
            "analyst": n.analyst or {}, "insights": n.insights or {}, "metrics": n.metrics or {},
            "product_types": (n.analyst or {}).get("product_types") or ["not_supported_yet"],
            "business_industry": (n.analyst or {}).get("business_industry"),
            "art_theme": (n.analyst or {}).get("art_theme"), "planner_kind": (n.analyst or {}).get("planner_kind"),
            "evidence": [{"id": e.id, "kind": e.kind, "claim": e.claim, "value": e.value, "source_title": e.source_title,
                          "url": e.url, "published": e.published, "source_type": e.source_type,
                          "retrieved_at": e.retrieved_at.date().isoformat(), "data": e.data or {}}
                         for e in n.evidence]}


def csv_signals_for(nd: dict) -> dict:
    rows = [e["data"] for e in nd["evidence"] if e["source_type"] == "csv_import" and e.get("data")]
    if not rows:
        return {}
    srch = [r["searches"] for r in rows if r.get("searches")]
    comp = [r["competition"] for r in rows if r.get("competition")]
    return {"searches": max(srch) if srch else None, "competition": min(comp) if comp else None,
            "keywords": [r["keyword"] for r in rows]}


def run_research(progress=None, *, use_etsy: bool = True, use_ai: bool = False, trigger: str = "manual") -> dict:
    progress = progress or (lambda pct, msg="": None)
    notes: list[str] = []
    sources, unavailable = ["public_web (curated, dated 2026-10-14)"], []
    load_seed()
    with session_scope() as s:
        run = ResearchRun(trigger=trigger)
        s.add(run)
        s.flush()
        run_id = run.id

    # Optional AI discovery of new niches
    if use_ai:
        progress(5, "Running AI web research for new niches")
        try:
            found = claude_web_research(notes)
            with session_scope() as s:
                for f in found:
                    slug = slugify(f.get("name", ""))
                    if not slug or s.scalar(select(Niche).where(Niche.slug == slug)):
                        continue
                    pt = classify_product_type(f.get("name", "") + " " + " ".join(f.get("keywords", [])))
                    n = Niche(slug=slug, name=f["name"], category="Discovered", keywords=f.get("keywords", [])[:10],
                              seasonality=f.get("seasonality", "evergreen"), discovered=True,
                              analyst={"demand": f.get("demand"), "demand_rationale": f.get("demand_rationale", ""),
                                       "competition": f.get("competition"), "product_types": [pt],
                                       "competition_rationale": "AI-assessed from web sources"}, insights={})
                    s.add(n)
                    s.flush()
                    for e in f.get("evidence", [])[:5]:
                        if e.get("url", "").startswith("http"):
                            s.add(Evidence(niche_id=n.id, kind="demand", claim=e.get("claim", ""), url=e["url"],
                                           source_title=e.get("source_title", ""), published=e.get("published"),
                                           source_type="claude_web"))
            sources.append("claude_web (AI web research with citations)")
        except (EtsyNotConfigured, BudgetExceeded, ExternalServiceError) as e:
            unavailable.append(f"AI web research: {e}")

    # Live Etsy data
    client = None
    if use_etsy:
        try:
            client = EtsyClient()
            sources.append("etsy_api (Etsy Open API v3, live)")
        except EtsyNotConfigured:
            unavailable.append("Etsy Open API: no ETSY_API_KEY configured. Live listing counts, prices, favorites and "
                               "views are not included (see Settings > Credentials).")

    with session_scope() as s:
        niche_ids = [n.id for n in s.scalars(select(Niche)).all()]
    total = len(niche_ids)
    if client:
        with session_scope() as s:
            known = {k for n in s.scalars(select(Niche)).all() for k in (n.keywords or [])}
        queue = list(niche_ids)
        i = 0
        while i < len(queue):
            nid = queue[i]
            i += 1
            # read (short transaction) -> fetch over the network (no transaction held) -> write
            with session_scope() as s:
                n = s.get(Niche, nid)
                name, kws = n.name, list(n.keywords or [])
                producible = (n.analyst or {}).get("product_types", ["not_supported_yet"])[0] != "not_supported_yet"
            progress(10 + 60 * i / max(1, len(queue)), f"Etsy API: {name}")
            try:
                metrics = gather_etsy_metrics(_Kw(kws), client, max_keywords=2 if nid in niche_ids else 1)
            except ExternalServiceError as e:
                notes.append(f"{name}: {e}")
                if "rejected the API key" in str(e) or "cap reached" in str(e):
                    unavailable.append(str(e))
                    break
                continue
            with session_scope() as s:
                n = s.get(Niche, nid)
                n.metrics = metrics
                if producible and nid in niche_ids:
                    for child in discover_from_tags(s, n, metrics, known, limit=1):
                        queue.append(child.id)
    with session_scope() as s:
        if s.scalar(select(Evidence).where(Evidence.source_type == "csv_import")):
            sources.append("csv_import (your keyword-tool exports)")

    progress(75, "Scoring opportunities")
    count = rank_all(run_id)
    with session_scope() as s:
        run = s.get(ResearchRun, run_id)
        run.finished_at, run.status = utcnow(), "done"
        run.sources_used, run.unavailable_sources, run.notes = sources, unavailable, "\n".join(notes)
        run.niches_analyzed = len(niche_ids)
    progress(100, f"Ranked {count} opportunities")
    return {"run_id": run_id, "opportunities": count, "sources": sources, "unavailable": unavailable, "notes": notes,
            "message": f"Research complete: {count} opportunities ranked"}


def rank_all(run_id: int | None = None) -> int:
    """(Re)score every concept with the current weights. Upserts by niche+product type (no duplicates)."""
    weights = get_setting("weights")
    shop = get_setting("shop")
    offsite = shop["offsite_ads_rate"] if shop.get("include_offsite_ads") else 0.0
    n_opps = 0
    with session_scope() as s:
        produced = Counter((p.params or {}).get("opportunity_key") for p in s.scalars(select(Product)).all())
        for n in s.scalars(select(Niche)).all():
            nd = niche_dict(n)
            csv_sig = csv_signals_for(nd)
            for c in concepts_for_niche(nd):
                info = c["info"]
                key = f"{n.slug}:{c['product_type']}"
                res = score_opportunity(niche=nd, product_type=c["product_type"], metrics=nd["metrics"],
                                        csv_signals=csv_sig, weights=weights,
                                        production_cost=info["est_production_cost"], is_bundle=info["is_bundle"],
                                        offsite_ads_rate=offsite)
                competitor_urls = [e["url"] for e in nd["evidence"] if e["kind"] == "listing" and e["url"]]
                competitor_urls += [x["url"] for x in nd["metrics"].get("example_listings", []) if x.get("url")]
                sources = [{"title": e["source_title"], "url": e["url"], "published": e["published"],
                            "type": e["source_type"], "retrieved": e["retrieved_at"]}
                           for e in nd["evidence"] if e["url"] and e["kind"] != "listing"]
                fx = res["factors"]
                attractive = []
                if fx["demand"] >= 0.6:
                    attractive.append("Strong demand signals: " + (nd["analyst"].get("demand_rationale") or ""))
                if fx["automation"] >= 0.8:
                    attractive.append("Can be produced automatically at near-zero marginal cost.")
                if fx["bundle"] >= 0.75:
                    attractive.append("High bundle and personalization potential raises order value.")
                if fx["seasonal"] >= 0.9:
                    attractive.append(res["explanations"]["seasonal"])
                attractive += [f"Differentiation angle: {d}" for d in info["differentiation"][:2]]
                risks = list(info["risks"]) + list(nd["analyst"].get("risk_flags") or [])
                if res["pricing"]["basis"] == "assumption":
                    risks.append("Price is an assumption until live Etsy prices are fetched.")
                if fx["competition"] < 0.35:
                    risks.append("High competition: needs a distinctive style and strong listing photos.")
                already = produced.get(key, 0)
                details = {
                    "niche": n.name, "niche_slug": n.slug, "category": n.category, "discovered": n.discovered,
                    "product_label": info["label"], "target_customer": info["target"], "keywords": (n.keywords or [])[:13],
                    "competitor_urls": list(dict.fromkeys(competitor_urls))[:6],
                    "price_range": {"low": res["pricing"]["low"], "high": res["pricing"]["high"],
                                    "basis": res["pricing"]["basis"], "note": res["pricing"]["note"]},
                    "demand_evidence": [e["claim"] for e in nd["evidence"] if e["kind"] in ("demand", "trend", "keyword")][:5],
                    "competition_assessment": res["explanations"]["competition"],
                    "estimated_production_cost": info["est_production_cost"],
                    "suggested_price": res["pricing"]["price"], "fees_per_sale": res["fees_per_sale"],
                    "profit_per_sale": res["profit_per_sale"], "design_style": info["style"], "pieces": info["pieces"],
                    "why_attractive": attractive, "risks": risks, "sources": sources[:10],
                    "research_date": max([e["retrieved_at"] for e in nd["evidence"]] or [dt.date.today().isoformat()]),
                    "live_metrics": {k: v for k, v in nd["metrics"].items() if k not in ("example_listings",)},
                    "explanations": res["explanations"], "inputs": res["inputs"],
                    "confidence_detail": res["confidence"], "generator_params": c["params"],
                    "already_produced": already, "insights": nd["insights"],
                }
                opp = s.scalar(select(Opportunity).where(Opportunity.key == key))
                if opp is None:
                    opp = Opportunity(key=key, niche_id=n.id)
                    s.add(opp)
                opp.run_id = run_id or opp.run_id
                opp.concept, opp.product_type = c["concept"], c["product_type"]
                opp.details, opp.factor_scores = details, res["factors"]
                opp.score, opp.confidence = res["score"], res["confidence"]["score"]
                if already and opp.status == "new":
                    opp.status = "produced"
                n_opps += 1
    return n_opps


def recommend(top_n: int = 5) -> list[dict]:
    """Strongest producible ideas, excluding ones already produced or dismissed."""
    with session_scope() as s:
        opps = s.scalars(select(Opportunity).where(Opportunity.status.in_(["new", "saved"]),
                                                   Opportunity.product_type != "not_supported_yet")
                         .order_by(Opportunity.score.desc())).all()
        out, seen_types = [], Counter()
        for o in opps:
            if seen_types[o.product_type] >= 2:  # keep the shortlist diverse
                continue
            seen_types[o.product_type] += 1
            out.append({"id": o.id, "concept": o.concept, "score": o.score, "confidence": o.confidence,
                        "product_type": o.product_type})
            if len(out) >= top_n:
                break
        return out


def supported_types() -> dict:
    return {k: v["label"] for k, v in PRODUCT_TYPE_INFO.items()}
