from app.design.renderer import Renderer
from app.design.svg import Doc
from app.design import revise, registry
from app.qc import engine as QC
from app.listing.engine import _tags, check_listing


def _analyze(doc):
    with Renderer() as r:
        res = r.render(doc.svg(), unit=doc.unit, width=doc.width, height=doc.height)
    return QC.analyze_layout(res["measure"], res["preview_png"], res["textless_png"], unit=doc.unit,
                             safe_margin=doc.safe_margin)


def test_qc_detects_overflow_and_proposes_fix():
    d = Doc(width=300, height=300, unit="pt", bg="#ffffff")
    d.text(150, 150, "A very long line of wedding text", family="Montserrat", size=20, fill="#111111",
           box=(100, 130, 100, 30))
    an = _analyze(d)
    codes = {i["code"] for i in an["issues"]}
    assert "text_overflow" in codes
    eid = next(iter(an["fixes"]))
    d2 = Doc(width=300, height=300, unit="pt", bg="#ffffff", fixes={eid: an["fixes"][eid]})
    d2.text(150, 150, "A very long line of wedding text", family="Montserrat", size=20, fill="#111111",
            box=(100, 130, 100, 30))
    assert "text_overflow" not in {i["code"] for i in _analyze(d2)["issues"]}


def test_qc_detects_low_contrast_overlap_and_glyphs():
    d = Doc(width=300, height=300, unit="pt", bg="#ffffff")
    d.text(150, 100, "Pale text here", family="Montserrat", size=14, fill="#dddddd")
    d.text(150, 200, "Overlap one", family="Montserrat", size=20, fill="#111111")
    d.text(152, 203, "Overlap two", family="Montserrat", size=20, fill="#111111")
    d.text(150, 260, "Paid ✓", family="DM Sans", size=12, fill="#111111")
    codes = {i["code"] for i in _analyze(d)["issues"]}
    assert {"low_contrast", "text_overlap", "missing_glyphs"} <= codes


def test_spelling_check():
    issues = QC.spelling_issues([{"id": "t1", "text": "Recieve your invitaton today", "role": "body", "field": None}])
    assert {i["word"].lower() for i in issues} >= {"recieve", "invitaton"}


def test_revision_interpreter():
    p = registry.default_params("wedding_suite", seed=1)
    r = revise.interpret("Change the colors to sage green and cream", p, "wedding_suite")
    assert r["understood"] and isinstance(r["params"]["palette"], dict)
    assert r["params"]["palette"]["bg"] == "#f6f0e4"
    r = revise.interpret("Make this more minimalist", p, "wedding_suite")
    assert r["params"]["ornament"] == 0 and r["params"]["style"] == "minimal"
    r = revise.interpret("Make the typography more elegant", p, "wedding_suite")
    assert r["params"]["fonts"] in ("elegant", "luxury")
    r = revise.interpret("Make this suitable for a luxury wedding", p, "wedding_suite")
    assert r["params"]["palette"] == "luxe_black_gold"
    assert revise.interpret("Create five matching products", p, "wedding_suite")["extra_products"] == 5
    assert not revise.interpret("qwerty zxcv", p, "wedding_suite")["understood"]


def test_listing_tags_and_checks():
    tags = _tags(["wedding invitation", "a very very long tag phrase here", "wedding invitation", "canva template",
                  "seating chart"], [r"\bcanva\b"])
    assert tags == ["wedding invitation", "seating chart"]
    bad = {"title": "Canva Wedding Invitation & Sign & Menu", "description": "nice", "tags": ["x"] * 3, "mockups": []}
    msgs = " ".join(c["message"] for c in check_listing(bad))
    assert "Canva" in msgs and "'&' appears more than once" in msgs and "digital download" in msgs
