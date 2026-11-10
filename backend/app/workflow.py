"""Workflow orchestration (background jobs):

Research -> Rank -> Select -> Generate designs -> QC -> Review -> Bundle -> Listing -> Approve -> Send to Etsy (draft)
"""
from __future__ import annotations

import copy
import datetime as dt
import random
import threading

from sqlalchemy import select

from .config import log, settings
from .db import Listing, Opportunity, Product, ProductVersion, get_setting, session_scope, utcnow
from .design import imagegen, pipeline, registry, revise
from .design.renderer import Renderer
from .jobs import JobContext, job
from .listing.engine import generate_listing
from .research import engine as research
from .services import Budget


# ------------------------------------------------------------------ serialisers
def product_dict(p: Product, with_versions: bool = True) -> dict:
    cur = next((v for v in p.versions if v.version == p.current_version), None)
    d = {"id": p.id, "name": p.name, "product_type": p.product_type, "status": p.status,
         "current_version": p.current_version, "params": {k: v for k, v in (p.params or {}).items() if k != "_fixes"},
         "opportunity_id": p.opportunity_id, "review_note": p.review_note, "production_cost": p.production_cost,
         "created_at": p.created_at.isoformat() + "Z", "updated_at": (p.updated_at or p.created_at).isoformat() + "Z",
         "qc_score": cur.qc_score if cur else None, "hero_preview": cur.files["pieces"][0]["preview"] if cur and cur.files.get("pieces") else None,
         "listing": ({"status": p.listing.status, "etsy_listing_id": p.listing.etsy_listing_id, **p.listing.data}
                     if p.listing else None)}
    if with_versions:
        d["versions"] = [{"version": v.version, "files": v.files, "qc": v.qc, "qc_score": v.qc_score,
                          "revision_note": v.revision_note, "created_at": v.created_at.isoformat() + "Z"}
                         for v in sorted(p.versions, key=lambda v: -v.version)]
    return d


# ------------------------------------------------------------------ helpers
def _unique_params(product_type: str, params: dict) -> dict:
    """Prevent duplicates: if an identical design exists, move to the next unused style variation."""
    with session_scope() as s:
        taken = {p.fingerprint for p in s.scalars(select(Product).where(Product.product_type == product_type,
                                                                         Product.status != "rejected")).all()}
    if pipeline.fingerprint(product_type, params) not in taken:
        return params
    for var in registry.PRODUCT_TYPES[product_type]["variations"]:
        cand = {**params, **var}
        if pipeline.fingerprint(product_type, cand) not in taken:
            log.info("Duplicate design avoided - using variation %s", var)
            return cand
    params = {**params, "seed": random.randint(1, 99999)}
    return params


def _ai_artwork(product_id: int, params: dict, ctx: JobContext | None) -> float:
    """Generate optional AI artwork for wall art (opt-in), within spending limits."""
    if params.get("art_source") != "ai" or not imagegen.available():
        return 0.0
    cfg = get_setting("budget")
    out = settings.output_dir / f"product_{product_id}" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    imgs = params.setdefault("ai_images", {})
    cost = 0.0
    for i in range(min(int(params.get("count", 3)), int(cfg["max_images_per_product"]))):
        if str(i) in imgs:
            continue
        if ctx:
            ctx.progress(3, f"Generating AI artwork {i + 1}")
        prompt = params.get("ai_prompt", "Minimal boho abstract wall art, organic shapes, warm earthy palette, "
                                         "flat matte gouache texture, gallery quality") + f", variation {i + 1}"
        res = imagegen.generate(prompt, out / f"art_{i}.png")
        imgs[str(i)] = res
        cost += res["cost_usd"]
    return cost


_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


def _product_lock(pid: int) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(pid, threading.Lock())


def build_version(product_id: int, params: dict, note: str, ctx: JobContext | None = None) -> dict:
    with _product_lock(product_id):  # one build per product at a time (versions stay consistent)
        return _build_version(product_id, params, note, ctx)


def _build_version(product_id: int, params: dict, note: str, ctx: JobContext | None = None) -> dict:
    with session_scope() as s:
        p = s.get(Product, product_id)
        ptype, name = p.product_type, p.name
        next_v = (max([v.version for v in p.versions] or [0])) + 1
    cost = _ai_artwork(product_id, params, ctx)
    qcfg = get_setting("quality")
    out_dir = settings.output_dir / f"product_{product_id}" / f"v{next_v}"
    res = pipeline.generate_version(product_type=ptype, params=params, name=name, out_dir=out_dir,
                                    progress=(lambda pct, msg="": ctx.progress(pct * 0.9, msg)) if ctx else None,
                                    max_fix_iterations=int(qcfg["max_fix_iterations"]))
    with session_scope() as s:
        p = s.get(Product, product_id)
        v = ProductVersion(product_id=product_id, version=next_v, params=res["params"],
                           files={k: res[k] for k in ("pieces", "mockups", "deliverables", "bundle_zip", "bundle_bytes")},
                           qc=res["qc"], qc_score=res["qc"]["score"], revision_note=note)
        s.add(v)
        p.current_version = next_v
        p.params = res["params"]
        p.fingerprint = pipeline.fingerprint(ptype, res["params"])
        p.production_cost = round((p.production_cost or 0) + cost, 4)
        p.status = "review" if res["qc"]["score"] >= float(qcfg["min_qc_score"]) else "needs_attention"
    refresh_listing(product_id)
    return res


def refresh_listing(product_id: int) -> dict:
    with session_scope() as s:
        p = s.get(Product, product_id)
        cur = next(v for v in p.versions if v.version == p.current_version)
        opp = s.get(Opportunity, p.opportunity_id).details if p.opportunity_id else None
        pd = {"product_type": p.product_type, "params": p.params, "production_cost": p.production_cost}
        ai_used = bool((p.params or {}).get("ai_images"))
        listing = generate_listing(product=pd, version=cur.files, opportunity=opp, shop=get_setting("shop"),
                                   ai_used=ai_used, canva_link=(p.params or {}).get("canva_link"))
        if p.listing is None:
            s.add(Listing(product_id=p.id, data=listing))
        else:
            # keep user edits to title/tags/description/price if they edited them
            edited = (p.listing.data or {}).get("_edited_fields", [])
            for f in edited:
                listing[f] = p.listing.data.get(f, listing.get(f))
            listing["_edited_fields"] = edited
            p.listing.data = listing
            if p.listing.status == "approved":
                p.listing.status = "draft"
        return listing


def create_product(*, opportunity_id: int | None = None, product_type: str | None = None, extra: dict | None = None,
                   name: str | None = None) -> int:
    with session_scope() as s:
        details = {}
        if opportunity_id:
            o = s.get(Opportunity, opportunity_id)
            if o.product_type not in registry.PRODUCT_TYPES:
                raise ValueError("This opportunity has no automated generator yet (research only).")
            product_type = o.product_type
            details = o.details
            name = name or o.concept
            o.status = "produced"
        params = registry.default_params(product_type, {**(details.get("generator_params") or {}), **(extra or {})})
        params["opportunity_key"] = f"{details.get('niche_slug')}:{product_type}" if details else None
        params = _unique_params(product_type, params)
        p = Product(opportunity_id=opportunity_id, name=name or registry.PRODUCT_TYPES[product_type]["label"],
                    product_type=product_type, status="draft", params=params,
                    fingerprint=pipeline.fingerprint(product_type, params))
        s.add(p)
        s.flush()
        return p.id


# ------------------------------------------------------------------ jobs
@job("research")
def job_research(ctx: JobContext) -> dict:
    ctx.step("Research opportunities")
    res = research.run_research(ctx.progress, use_etsy=ctx.payload.get("use_etsy", True),
                                use_ai=ctx.payload.get("use_ai", False), trigger=ctx.payload.get("trigger", "manual"))
    ctx.step("Research opportunities", "done")
    ctx.step("Rank opportunities", "done", f"{res['opportunities']} ranked")
    return res


@job("generate_product")
def job_generate(ctx: JobContext) -> dict:
    pl = ctx.payload
    pid = pl.get("product_id")
    if not pid:
        ctx.step("Select product")
        pid = create_product(opportunity_id=pl.get("opportunity_id"), product_type=pl.get("product_type"),
                             extra=pl.get("params"), name=pl.get("name"))
        with session_scope() as s:
            from .db import Job
            j = s.get(Job, ctx.job_id)
            j.payload = {**pl, "product_id": pid}  # a retry continues with the same product
        ctx.step("Select product", "done", f"product #{pid}")
    with session_scope() as s:
        params = copy.deepcopy(s.get(Product, pid).params)
    ctx.step("Generate original designs")
    res = build_version(pid, params, pl.get("note", "Initial generation"), ctx)
    ctx.step("Generate original designs", "done")
    ctx.step("Quality check", "done", f"score {res['qc']['score']}")
    ctx.step("Create bundle", "done", f"{len(res['deliverables'])} Etsy files")
    ctx.step("Generate listing", "done")
    return {"product_id": pid, "qc_score": res["qc"]["score"], "message": f"Product #{pid} ready for review"}


@job("revise_product")
def job_revise(ctx: JobContext) -> dict:
    pid, request = ctx.payload["product_id"], ctx.payload.get("request", "")
    with session_scope() as s:
        p = s.get(Product, pid)
        params, ptype, name, opp_id = copy.deepcopy(p.params), p.product_type, p.name, p.opportunity_id
    if ctx.payload.get("params"):
        interp = {"params": {**params, **ctx.payload["params"]}, "changes": ["Applied selected variation"],
                  "understood": True, "extra_products": 0}
        interp["params"].pop("_fixes", None)
    else:
        interp = revise.interpret(request, params, ptype)
    if not interp["understood"]:
        return {"product_id": pid, "understood": False, "message": "I couldn't map that request to a design change. "
                + revise.HELP}
    ctx.step("Apply revision", "done", "; ".join(interp["changes"]))
    created = []
    if interp["extra_products"]:
        ctx.step("Create matching products")
        variants = _matching_variants(ptype, interp["params"], interp["extra_products"])
        for i, extra in enumerate(variants):
            npid = create_product(product_type=ptype, extra=extra, name=f"{name} - matching #{i + 1}")
            with session_scope() as s:
                s.get(Product, npid).opportunity_id = opp_id
            build_version(npid, _params_of(npid), f"Matching product for #{pid}", None)
            created.append(npid)
            ctx.progress(10 + 80 * (i + 1) / len(variants), f"Matching product {i + 1}/{len(variants)} done")
        ctx.step("Create matching products", "done", f"{len(created)} created")
        return {"product_id": pid, "created": created, "changes": interp["changes"],
                "message": f"Created {len(created)} matching product(s)"}
    ctx.step("Regenerate designs")
    res = build_version(pid, interp["params"], request or "Applied variation", ctx)
    ctx.step("Regenerate designs", "done", f"QC {res['qc']['score']}")
    return {"product_id": pid, "changes": interp["changes"], "qc_score": res["qc"]["score"],
            "message": "Revision applied: " + "; ".join(interp["changes"])}


def _params_of(pid: int) -> dict:
    with session_scope() as s:
        return copy.deepcopy(s.get(Product, pid).params)


def _matching_variants(ptype: str, params: dict, n: int) -> list[dict]:
    """Same palette & typography, different product content -> a coordinated collection."""
    base = {k: v for k, v in params.items() if k in ("palette", "fonts", "style", "ornament", "theme", "industry")}
    out = []
    for i in range(n):
        v = dict(base, seed=int(params.get("seed", 1)) + 37 * (i + 1))
        if ptype == "wall_art_set":
            from .design.art import COMPOSITIONS
            from .design.art import THEME_SETS
            theme = params.get("theme", "boho")
            pool = THEME_SETS.get(theme, THEME_SETS["boho"])
            comps = pool + [c for c in COMPOSITIONS if c not in pool and not c.startswith("holiday") and theme != "holiday"]
            v["compositions"] = [comps[(i * 3 + k) % len(comps)] for k in range(int(params.get("count", 3)))]
        if ptype == "business_kit":
            inds = ["beauty", "boutique", "real_estate"]
            v["industry"] = inds[(inds.index(params.get("industry", "beauty")) + i + 1) % len(inds)]
        if ptype == "budget_planner":
            v["kind"] = "habit" if params.get("kind") != "habit" else "budget"
        out.append(v)
    return out


@job("variations")
def job_variations(ctx: JobContext) -> dict:
    """Quick previews of alternative styles for the hero piece (cheap: no full export)."""
    pid = ctx.payload["product_id"]
    with session_scope() as s:
        p = s.get(Product, pid)
        ptype, params = p.product_type, copy.deepcopy(p.params)
    params.pop("_fixes", None)
    hero = registry.PRODUCT_TYPES[ptype]["hero"]
    out_dir = settings.output_dir / f"product_{pid}" / "variations"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    vars_ = registry.PRODUCT_TYPES[ptype]["variations"]
    with Renderer() as r:
        for i, var in enumerate(vars_):
            cand = {**params, **var}
            doc = registry.build(ptype, hero, cand, 1)
            path = out_dir / f"var_{i}.png"
            r.render(doc.svg(), unit=doc.unit, width=doc.width, height=doc.height, preview_path=path, measure=False,
                     preview_max=700)
            results.append({"index": i, "params": var, "preview": str(path.relative_to(settings.data_dir))})
            ctx.progress(100 * (i + 1) / len(vars_), f"Variation {i + 1}/{len(vars_)}")
    return {"product_id": pid, "variations": results, "message": f"{len(results)} variations ready"}


@job("send_to_etsy")
def job_send(ctx: JobContext) -> dict:
    from .publish import etsy_publish
    pid = ctx.payload["product_id"]
    with session_scope() as s:
        p = s.get(Product, pid)
        if p.status != "approved" or not p.listing or p.listing.status != "approved":
            raise ValueError("Approve both the product and its listing before sending to Etsy.")
        data = dict(p.listing.data)
    res = etsy_publish.send_draft(data, settings.data_dir, ctx.payload.get("taxonomy_id"))
    with session_scope() as s:
        p = s.get(Product, pid)
        p.listing.status, p.listing.etsy_listing_id, p.status = "sent_to_etsy", str(res["listing_id"]), "published"
    return res


@job("daily_automation")
def job_daily(ctx: JobContext) -> dict:
    """Scheduled run: research -> recommend top N -> (optional) draft products -> listing drafts. Never publishes."""
    cfg = get_setting("schedule")
    ctx.step("Research")
    res = research.run_research(lambda pct, msg="": ctx.progress(pct * 0.5, msg), trigger="scheduled")
    ctx.step("Research", "done", f"{res['opportunities']} ranked")
    top = research.recommend(int(cfg.get("top_n", 5)))
    ctx.step("Recommend", "done", ", ".join(o["concept"] for o in top))
    made = []
    if cfg.get("auto_generate_drafts"):
        ctx.step("Generate drafts")
        today = utcnow() - dt.timedelta(days=1)
        with session_scope() as s:
            recent = s.scalars(select(Product).where(Product.created_at >= today)).all()
            already_today = len(recent)
        limit = max(0, int(cfg.get("max_drafts_per_run", 2)) - already_today)
        for o in top[:limit]:
            try:
                pid = create_product(opportunity_id=o["id"])
                build_version(pid, _params_of(pid), "Automated daily draft", None)
                made.append(pid)
            except Exception as e:  # noqa: BLE001
                log.warning("auto draft for %s failed: %s", o["concept"], e)
        ctx.step("Generate drafts", "done", f"{len(made)} drafts")
    return {"recommendations": top, "drafts": made, "budget": Budget.status(),
            "message": f"Daily run: {len(top)} recommendations, {len(made)} draft products (awaiting your review)"}
