"""Full workflow: opportunity -> original designs -> QC -> variations -> bundle -> listing -> saved -> approval."""
import zipfile
from pathlib import Path

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from app import jobs, workflow  # noqa: F401
from app.config import settings
from app.db import Job, Opportunity, Product, session_scope


def _run(kind, payload):
    jid = jobs.submit(kind, payload, sync=True)
    with session_scope() as s:
        j = s.get(Job, jid)
        assert j.status == "done", j.error
        return dict(j.result)


@pytest.fixture(scope="module")
def products():
    out = {}
    with session_scope() as s:
        opps = s.scalars(select(Opportunity).where(Opportunity.product_type != "not_supported_yet")
                         .order_by(Opportunity.score.desc())).all()
        by_type = {}
        for o in opps:
            by_type.setdefault(o.product_type, o.id)
    for ptype in ("wedding_suite", "wall_art_set", "business_kit"):
        res = _run("generate_product", {"opportunity_id": by_type[ptype]})
        out[ptype] = res["product_id"]
    return out


def _product(pid):
    with session_scope() as s:
        return workflow.product_dict(s.get(Product, pid))


def test_opportunity_explains_selection(products):
    with session_scope() as s:
        p = s.get(Product, products["wedding_suite"])
        o = s.get(Opportunity, p.opportunity_id)
        assert o.status == "produced"
        assert o.details["why_attractive"] and o.details["explanations"]["demand"]


@pytest.mark.parametrize("ptype", ["wedding_suite", "wall_art_set", "business_kit"])
def test_generated_files_are_valid(products, ptype):
    d = _product(products[ptype])
    assert d["status"] in ("review", "needs_attention")
    v = d["versions"][0]
    assert v["qc"]["file_errors"] == 0, v["qc"]["file_checks"]
    assert v["qc_score"] >= 80, [p["qc"]["issues"] for p in v["files"]["pieces"]]
    data = settings.data_dir
    for piece in v["files"]["pieces"]:
        assert (data / piece["preview"]).exists()
        for f in piece["files"]:
            path = data / f["path"]
            assert path.exists() and path.stat().st_size > 0 and f["valid"], f
            if f["format"] == "pdf":
                r = PdfReader(str(path))
                box = r.pages[0].mediabox
                assert abs(float(box.width) / 72 - piece["size_in"][0]) < 0.02
    # Etsy delivery limits
    dl = v["files"]["deliverables"]
    assert 1 <= len(dl) <= 5 and all(x["bytes"] <= 20 * 1024 * 1024 for x in dl)
    with zipfile.ZipFile(data / v["files"]["bundle_zip"]) as z:
        assert z.testzip() is None and len(z.namelist()) > 3
    assert len(v["files"]["mockups"]) >= 2 and all(m["bytes"] < 1_000_000 for m in v["files"]["mockups"])


def test_editable_sources_included(products):
    v = _product(products["wedding_suite"])["versions"][0]
    fmts = {f["format"] for p in v["files"]["pieces"] for f in p["files"]}
    assert {"pdf", "png", "svg", "html"} <= fmts
    html = (settings.data_dir / next(f["path"] for p in v["files"]["pieces"] for f in p["files"] if f["format"] == "html")).read_text()
    assert "data-field" in html and "Print / Save as PDF" in html


def test_listing_generated(products):
    for pid in products.values():
        l = _product(pid)["listing"]
        assert len(l["title"]) <= 140 and len(l["tags"]) == 13 and all(len(t) <= 20 for t in l["tags"])
        assert "DIGITAL DOWNLOAD" in l["description"] and l["faq"] and l["price"] > 0
        assert not [c for c in l["checks"] if c["severity"] == "error"], l["checks"]
        assert "canva" not in " ".join(l["tags"])


def test_variations_and_revision(products):
    pid = products["business_kit"]
    res = _run("variations", {"product_id": pid})
    assert len(res["variations"]) >= 4
    assert all((settings.data_dir / v["preview"]).exists() for v in res["variations"])
    res = _run("revise_product", {"product_id": pid, "request": "Change the colors to navy and cream"})
    d = _product(pid)
    assert d["current_version"] == 2 and len(d["versions"]) == 2


def test_duplicate_prevention(products):
    with session_scope() as s:
        p = s.get(Product, products["wall_art_set"])
        params, fp = dict(p.params), p.fingerprint
    new = workflow._unique_params("wall_art_set", params)
    from app.design.pipeline import fingerprint
    assert fingerprint("wall_art_set", new) != fp


def test_bundle_matching_products(products):
    res = _run("revise_product", {"product_id": products["wall_art_set"], "request": "Create two matching products"})
    assert len(res["created"]) == 2
    base = _product(products["wall_art_set"])["params"]["palette"]
    for pid in res["created"]:
        d = _product(pid)
        assert d["params"]["palette"] == base and d["versions"]


def test_approve_and_reject(products):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        pid = products["wedding_suite"]
        assert c.post(f"/api/products/{pid}/listing/approve").status_code == 200
        assert c.get(f"/api/products/{pid}").json()["status"] == "approved"
        assert c.post(f"/api/products/{products['business_kit']}/status", json={"status": "rejected"}).status_code == 200
        assert c.get("/api/status").json()["counts"]["approved"] >= 1
        assert c.get("/api/opportunities?limit=20").status_code == 200
        assert c.post(f"/api/products/{pid}/send-to-etsy").status_code == 400  # not connected -> refused, nothing published
