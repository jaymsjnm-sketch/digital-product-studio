"""Digital Product Studio - FastAPI application (REST API + dashboard)."""
from __future__ import annotations

import csv
import io
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from . import jobs, scheduler, workflow  # noqa: F401  (workflow registers job handlers)
from .config import APP_DIR, ETSY_ATTRIBUTION, log, settings
from .db import (DEFAULT_SETTINGS, Evidence, Job, Niche, Opportunity, Product, ResearchRun, SaleRecord, Spend,
                 get_setting, init_db, session_scope, set_setting)
from .design import imagegen, registry
from .design.revise import HELP as REVISION_HELP
from .design.styles import FONT_PAIRINGS, PALETTES
from .publish import canva, etsy_publish
from .research import engine as research
from .services import Budget


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    jobs.recover_interrupted()
    research.load_seed()
    with session_scope() as s:
        if not s.scalar(select(func.count(Opportunity.id))):
            research.rank_all()
    scheduler.start()
    log.info("Digital Product Studio ready at http://127.0.0.1:8000")
    yield
    scheduler.shutdown()


app = FastAPI(title="Digital Product Studio", version="1.0.0", lifespan=lifespan)
app.mount("/files", StaticFiles(directory=str(settings.data_dir), check_dir=False), name="files")


def _404(what: str):
    raise HTTPException(404, f"{what} not found")


# ------------------------------------------------------------------ status & settings
@app.get("/api/status")
def status():
    with session_scope() as s:
        counts = {"niches": s.scalar(select(func.count(Niche.id))),
                  "opportunities": s.scalar(select(func.count(Opportunity.id))),
                  "products": s.scalar(select(func.count(Product.id))),
                  "approved": s.scalar(select(func.count(Product.id)).where(Product.status.in_(["approved", "published"]))),
                  "jobs_running": s.scalar(select(func.count(Job.id)).where(Job.status.in_(["queued", "running"])))}
        last = s.scalars(select(ResearchRun).order_by(ResearchRun.id.desc()).limit(1)).first()
    return {
        "credentials": {
            "etsy_api_key": bool(settings.etsy_api_key), "etsy_connected": etsy_publish.is_connected(),
            "openai_images": imagegen.available(), "anthropic": bool(settings.anthropic_api_key),
            "canva": canva.configured(),
        },
        "budget": Budget.status(), "counts": counts, "attribution": ETSY_ATTRIBUTION,
        "last_research": ({"id": last.id, "started_at": last.started_at.isoformat() + "Z", "status": last.status,
                           "sources": last.sources_used, "unavailable": last.unavailable_sources} if last else None),
        "schedule": get_setting("schedule"), "product_types": {k: v["label"] for k, v in registry.PRODUCT_TYPES.items()},
        "palettes": {k: {kk: vv for kk, vv in v.items() if kk in ("bg", "ink", "accent", "accent2")} for k, v in PALETTES.items()},
        "font_pairings": {k: f"{v['display']} + {v['script']} + {v['body']}" for k, v in FONT_PAIRINGS.items()},
        "revision_help": REVISION_HELP,
    }


@app.get("/api/settings")
def get_settings():
    return {k: get_setting(k) for k in DEFAULT_SETTINGS}


@app.put("/api/settings")
def put_settings(body: dict = Body(...)):
    for k, v in body.items():
        if k not in DEFAULT_SETTINGS:
            raise HTTPException(400, f"Unknown setting {k}")
        if k == "budget":
            for kk in ("daily_usd", "monthly_usd"):
                if kk in v and float(v[kk]) < 0:
                    raise HTTPException(400, "Limits must be >= 0")
        set_setting(k, {**get_setting(k), **v} if isinstance(v, dict) else v)
    out = {"saved": list(body)}
    if "weights" in body or "shop" in body:
        out["rescored"] = research.rank_all()
    if "schedule" in body:
        out["schedule"] = scheduler.reload()
    return out


# ------------------------------------------------------------------ research
@app.post("/api/research/run")
def run_research(body: dict = Body(default={})):
    return {"job_id": jobs.submit("research", {"use_etsy": body.get("use_etsy", True), "use_ai": body.get("use_ai", False)})}


@app.get("/api/research/runs")
def research_runs():
    with session_scope() as s:
        return [{"id": r.id, "started_at": r.started_at.isoformat() + "Z", "status": r.status, "trigger": r.trigger,
                 "sources": r.sources_used, "unavailable": r.unavailable_sources, "notes": r.notes,
                 "niches_analyzed": r.niches_analyzed}
                for r in s.scalars(select(ResearchRun).order_by(ResearchRun.id.desc()).limit(30)).all()]


@app.get("/api/niches")
def niches():
    with session_scope() as s:
        return [research.niche_dict(n) for n in s.scalars(select(Niche).order_by(Niche.category, Niche.name)).all()]


@app.post("/api/niches/{niche_id}/evidence")
def add_evidence(niche_id: int, body: dict = Body(...)):
    if not body.get("claim") or not str(body.get("url", "")).startswith("http"):
        raise HTTPException(400, "Evidence needs a claim and a source URL")
    with session_scope() as s:
        if not s.get(Niche, niche_id):
            _404("Niche")
        s.add(Evidence(niche_id=niche_id, kind=body.get("kind", "demand"), claim=body["claim"], url=body["url"],
                       source_title=body.get("source_title", ""), published=body.get("published"), source_type="user"))
    research.rank_all()
    return {"ok": True}


@app.post("/api/research/import-csv")
async def import_csv(file: UploadFile = File(...)):
    content = (await file.read()).decode("utf-8-sig", errors="replace")
    try:
        res = research.import_keyword_csv(content, file.filename or "csv")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    res["rescored"] = research.rank_all()
    return res


@app.get("/api/opportunities")
def opportunities(limit: int = 100, category: str | None = None, status: str | None = None):
    with session_scope() as s:
        q = select(Opportunity).order_by(Opportunity.score.desc())
        rows = s.scalars(q).all()
        out = []
        for o in rows:
            if category and o.details.get("category") != category:
                continue
            if status and o.status != status:
                continue
            out.append({"id": o.id, "concept": o.concept, "product_type": o.product_type, "score": o.score,
                        "confidence": o.confidence, "status": o.status, "factors": o.factor_scores,
                        "details": o.details, "updated_at": o.updated_at.isoformat() + "Z"})
        return out[:limit]


@app.post("/api/opportunities/rescore")
def rescore():
    return {"rescored": research.rank_all()}


@app.patch("/api/opportunities/{oid}")
def update_opp(oid: int, body: dict = Body(...)):
    with session_scope() as s:
        o = s.get(Opportunity, oid)
        if not o:
            _404("Opportunity")
        if body.get("status") in ("new", "saved", "dismissed", "produced"):
            o.status = body["status"]
    return {"ok": True}


@app.get("/api/recommendations")
def recommendations(n: int = 5):
    return research.recommend(n)


# ------------------------------------------------------------------ products
@app.post("/api/products/generate")
def generate(body: dict = Body(...)):
    if not body.get("opportunity_id") and body.get("product_type") not in registry.PRODUCT_TYPES:
        raise HTTPException(400, "Provide opportunity_id or a supported product_type")
    if body.get("opportunity_id"):
        with session_scope() as s:
            o = s.get(Opportunity, int(body["opportunity_id"]))
            if not o:
                _404("Opportunity")
            if o.product_type not in registry.PRODUCT_TYPES:
                raise HTTPException(400, "This opportunity is research-only: no automated generator exists yet.")
    return {"job_id": jobs.submit("generate_product", body)}


@app.get("/api/products")
def products(status: str | None = None):
    with session_scope() as s:
        q = select(Product).order_by(Product.updated_at.desc())
        rows = s.scalars(q).all()
        return [workflow.product_dict(p, with_versions=False) for p in rows if not status or p.status == status]


@app.get("/api/products/{pid}")
def product(pid: int):
    with session_scope() as s:
        p = s.get(Product, pid)
        if not p:
            _404("Product")
        return workflow.product_dict(p)


@app.post("/api/products/{pid}/revise")
def revise(pid: int, body: dict = Body(...)):
    if not body.get("request") and not body.get("params"):
        raise HTTPException(400, "Describe the change you want")
    return {"job_id": jobs.submit("revise_product", {"product_id": pid, **body})}


@app.post("/api/products/{pid}/variations")
def variations(pid: int):
    return {"job_id": jobs.submit("variations", {"product_id": pid})}


@app.post("/api/products/{pid}/status")
def set_status(pid: int, body: dict = Body(...)):
    st = body.get("status")
    if st not in ("approved", "rejected", "review"):
        raise HTTPException(400, "status must be approved, rejected or review")
    with session_scope() as s:
        p = s.get(Product, pid)
        if not p:
            _404("Product")
        p.status, p.review_note = st, body.get("note", p.review_note)
        if st == "rejected" and p.opportunity_id:
            pass
    return {"ok": True}


@app.post("/api/products/{pid}/restore/{version}")
def restore(pid: int, version: int):
    with session_scope() as s:
        p = s.get(Product, pid)
        v = next((v for v in p.versions if v.version == version), None) if p else None
        if not v:
            _404("Version")
        p.current_version, p.params = version, v.params
    workflow.refresh_listing(pid)
    return {"ok": True}


@app.delete("/api/products/{pid}")
def delete_product(pid: int):
    import shutil
    with session_scope() as s:
        p = s.get(Product, pid)
        if not p:
            _404("Product")
        if p.status == "published":
            raise HTTPException(400, "Published products can't be deleted here")
        s.delete(p)
    shutil.rmtree(settings.output_dir / f"product_{pid}", ignore_errors=True)
    return {"ok": True}


# ------------------------------------------------------------------ listings
@app.put("/api/products/{pid}/listing")
def edit_listing(pid: int, body: dict = Body(...)):
    from .listing.engine import check_listing
    with session_scope() as s:
        p = s.get(Product, pid)
        if not p or not p.listing:
            _404("Listing")
        data = dict(p.listing.data)
        edited = set(data.get("_edited_fields", []))
        for f in ("title", "description", "tags", "price", "category"):
            if f in body:
                data[f] = body[f]
                edited.add(f)
        if "tags" in body:
            data["tags"] = [t.strip().lower() for t in body["tags"] if t.strip()][:13]
        data["_edited_fields"] = sorted(edited)
        data["checks"] = check_listing(data, canva_link=(p.params or {}).get("canva_link"))
        p.listing.data = data
        p.listing.status = "draft"
        return data


@app.post("/api/products/{pid}/listing/regenerate")
def regen_listing(pid: int):
    with session_scope() as s:
        p = s.get(Product, pid)
        if p and p.listing:
            p.listing.data = {**p.listing.data, "_edited_fields": []}
    return workflow.refresh_listing(pid)


@app.post("/api/products/{pid}/listing/approve")
def approve_listing(pid: int):
    with session_scope() as s:
        p = s.get(Product, pid)
        if not p or not p.listing:
            _404("Listing")
        errs = [c for c in p.listing.data.get("checks", []) if c["severity"] == "error"]
        if errs:
            raise HTTPException(400, "Fix listing errors first: " + "; ".join(e["message"] for e in errs))
        p.listing.status = "approved"
        if p.status in ("review", "needs_attention", "draft"):
            p.status = "approved"
    return {"ok": True}


@app.post("/api/products/{pid}/send-to-etsy")
def send_to_etsy(pid: int, body: dict = Body(default={})):
    if not etsy_publish.is_connected():
        raise HTTPException(400, "Connect your Etsy shop first (Settings).")
    return {"job_id": jobs.submit("send_to_etsy", {"product_id": pid, "taxonomy_id": body.get("taxonomy_id")})}


# ------------------------------------------------------------------ jobs
@app.get("/api/jobs")
def list_jobs(limit: int = 30):
    with session_scope() as s:
        return [jobs.job_dict(j) for j in s.scalars(select(Job).order_by(Job.id.desc()).limit(limit)).all()]


@app.get("/api/jobs/{jid}")
def get_job(jid: int):
    with session_scope() as s:
        j = s.get(Job, jid)
        if not j:
            _404("Job")
        return jobs.job_dict(j)


@app.post("/api/jobs/{jid}/retry")
def retry_job(jid: int):
    with session_scope() as s:
        j = s.get(Job, jid)
        if not j:
            _404("Job")
        if j.status not in ("failed",):
            raise HTTPException(400, "Only failed jobs can be retried")
    jobs.retry(jid)
    return {"job_id": jid}


# ------------------------------------------------------------------ analytics
@app.get("/api/analytics")
def analytics():
    with session_scope() as s:
        prods = s.scalars(select(Product)).all()
        by_status: dict[str, int] = {}
        for p in prods:
            by_status[p.status] = by_status.get(p.status, 0) + 1
        spend = s.execute(select(Spend.provider, func.sum(Spend.cost_usd), func.sum(Spend.units))
                          .group_by(Spend.provider)).all()
        sales = s.scalars(select(SaleRecord)).all()
        runs = s.scalar(select(func.count(ResearchRun.id)))
        rev = sum(x.price * x.quantity for x in sales)
        by_item: dict[str, dict] = {}
        for x in sales:
            d = by_item.setdefault(x.item_title, {"orders": 0, "revenue": 0.0})
            d["orders"] += x.quantity
            d["revenue"] += x.price * x.quantity
        top_opps = s.scalars(select(Opportunity).order_by(Opportunity.score.desc()).limit(10)).all()
        return {
            "products_by_status": by_status, "research_runs": runs,
            "spend": [{"provider": p, "usd": round(c or 0, 4), "calls": int(u or 0)} for p, c, u in spend],
            "production_cost_total": round(sum(p.production_cost or 0 for p in prods), 4),
            "sales": {"orders": sum(x.quantity for x in sales), "revenue": round(rev, 2),
                      "by_item": sorted(({"item": k, **v} for k, v in by_item.items()), key=lambda d: -d["revenue"])[:20],
                      "source": "Imported Etsy order CSV" if sales else None},
            "top_scores": [{"concept": o.concept, "score": o.score, "confidence": o.confidence} for o in top_opps],
            "budget": Budget.status(),
        }


@app.post("/api/analytics/import-sales")
async def import_sales(file: UploadFile = File(...)):
    """Etsy: Shop Manager > Settings > Options > Download Data > Orders (sold items CSV)."""
    text = (await file.read()).decode("utf-8-sig", errors="replace")
    rd = csv.DictReader(io.StringIO(text))
    n = 0
    with session_scope() as s:
        for r in rd:
            title = r.get("Item Name") or r.get("Title") or ""
            if not title:
                continue
            try:
                price = float((r.get("Price") or r.get("Item Total") or "0").replace("$", "").replace(",", ""))
            except ValueError:
                price = 0.0
            s.add(SaleRecord(order_id=r.get("Order ID", ""), sale_date=r.get("Sale Date", ""), item_title=title[:300],
                             quantity=int(r.get("Quantity") or 1), price=price, source="csv"))
            n += 1
    return {"imported": n}


# ------------------------------------------------------------------ OAuth
@app.get("/api/etsy/oauth/start")
def etsy_oauth_start():
    try:
        return RedirectResponse(etsy_publish.oauth_start())
    except etsy_publish.EtsyAuthRequired as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/etsy/oauth/callback")
def etsy_oauth_callback(code: str = Query(...), state: str = Query(...)):
    etsy_publish.oauth_callback(code, state)
    return RedirectResponse("/#/settings?etsy=connected")


@app.get("/api/canva/oauth/start")
def canva_start():
    try:
        return RedirectResponse(canva.oauth_start())
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/canva/oauth/callback")
def canva_cb(code: str, state: str):
    canva.oauth_callback(code, state)
    return RedirectResponse("/#/settings?canva=connected")


# ------------------------------------------------------------------ dashboard (prebuilt React app)
STATIC = APP_DIR / "static"
if (STATIC / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC / "assets")), name="assets")


@app.get("/", response_class=HTMLResponse)
def index():
    idx = STATIC / "index.html"
    if not idx.exists():
        return HTMLResponse("<h1>Dashboard not built</h1><p>Run <code>npm run build</code> in /frontend.</p>")
    return FileResponse(idx)
