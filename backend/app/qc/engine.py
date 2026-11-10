"""Automated design quality control.

Layout checks run on real Chromium measurements of the rendered design (not on guesses):
text clipping/overflow, text overlapping text, text sitting on top of graphics, print-safe
margins, contrast against the actual pixels behind each text, spelling, missing fonts/glyphs,
tiny type, visual balance and density, low-resolution images. File checks validate every
export (dimensions, DPI, embedded fonts, archive integrity, Etsy upload limits).

The score is a heuristic summary to help you review - it does NOT guarantee professional
quality. Always look at the previews yourself before approving.
"""
from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from functools import lru_cache
from pathlib import Path

from PIL import Image

from ..design import fonts as F
from ..design.styles import adjust_for_contrast, contrast_ratio, hex_to_rgb, rgb_to_hex

SEVERITY_PENALTY = {"error": 14, "warning": 5, "info": 1}
ETSY_MAX_FILES = 5
ETSY_MAX_BYTES = 20 * 1024 * 1024

ALLOWED_WORDS = {
    "rsvp", "instagram", "etsy", "goodnotes", "canva", "realtor", "realty", "sq", "ft", "lumière", "maison", "lash",
    "lashes", "brows", "brow", "esthetician", "burrata", "risotto", "jus", "parmesan", "sourdough", "stoneware",
    "cul-de-sac", "favourites", "colour", "favourite", "organise", "personalise", "auto-pay", "to-do", "undated",
    "juniper", "co", "mo", "vs", "a4", "a5", "pdf", "png", "jpg", "svg",
}


@lru_cache(maxsize=1)
def _spell():
    try:
        from spellchecker import SpellChecker
        return SpellChecker()
    except Exception:  # noqa: BLE001
        return None


def spelling_issues(texts: list[dict]) -> list[dict]:
    sc = _spell()
    if sc is None:
        return []
    issues = []
    for t in texts:
        if t.get("role") in ("name", "guest", "placeholder", "art-text") or (t.get("field") or "").startswith(("Name", "Brand", "Venue", "City", "Address", "Contact")):
            continue
        for mm in re.finditer(r"[A-Za-zÀ-ÿ'-]+", t["text"]):
            w = mm.group(0)
            sentence_start = mm.start() == 0 or re.search(r"[.!?:·]\s*$", t["text"][:mm.start()])
            wl = w.lower().strip("'-")
            if len(wl) < 3 or wl in ALLOWED_WORDS or w.isupper() and len(w) <= 4:
                continue
            if w[0].isupper() and not t["text"].isupper() and not sentence_start and t.get("role") not in ("heading",):
                continue  # likely a proper noun
            if wl in sc:
                continue
            parts = re.split(r"[-']", wl)
            if all((p in sc or len(p) < 3) for p in parts):
                continue
            issues.append({"id": t["id"], "word": w, "suggestion": sc.correction(wl)})
    return issues


def _tight(t: dict) -> tuple[float, float, float, float]:
    """Approximate ink box: real horizontal extent, vertical from baseline metrics."""
    x, _, w, _ = t["bbox"]
    s = t["size"]
    return x, t["y"] - s * 0.72, w, s * 0.92


def _inter(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _region(img: Image.Image, box, scale_xy) -> Image.Image | None:
    sx, sy = scale_xy
    x, y, w, h = box
    l, t = max(0, int(x * sx)), max(0, int(y * sy))
    r, b = min(img.width, int((x + w) * sx)), min(img.height, int((y + h) * sy))
    if r - l < 2 or b - t < 2:
        return None
    return img.crop((l, t, r, b))


def _mode_color(region: Image.Image) -> tuple[tuple[int, int, int], float]:
    small = region.copy()
    small.thumbnail((80, 80))
    q = [tuple(c // 6 * 6 for c in px[:3]) for px in (small.get_flattened_data() if hasattr(small, 'get_flattened_data') else small.getdata())]
    cnt = Counter(q)
    col, n = cnt.most_common(1)[0]
    return col, n / max(1, len(q))


def analyze_layout(measure: dict, preview_png: bytes, textless_png: bytes | None, *, unit: str, safe_margin: float,
                   centered: bool = True) -> dict:
    issues: list[dict] = []
    fixes: dict[str, dict] = {}
    vb_w, vb_h = measure["vb"]
    prev = Image.open(io.BytesIO(preview_png)).convert("RGB")
    bare = Image.open(io.BytesIO(textless_png)).convert("RGB") if textless_png else None
    sx, sy = prev.width / vb_w, prev.height / vb_h
    texts = [t for t in measure["texts"] if t["text"].strip()]

    def add(sev, code, msg, eid=None, **kw):
        issues.append({"severity": sev, "code": code, "message": msg, "element": eid, **kw})

    def fix(eid, **kw):
        target = re.sub(r"_(\d+)$", "", eid) if re.match(r"^p\d+_\d+$", eid) else eid
        cur = fixes.setdefault(target, {})
        if "scale" in kw and "scale" in cur:
            kw = {**kw, "scale": min(kw["scale"], cur["scale"])}
        cur.update(kw)

    for t in texts:
        x, y, w, h = t["bbox"]
        # 1) overflow / clipping beyond the intended box
        if t.get("box"):
            bx, by, bw, bh = (float(v) for v in t["box"].split())
            tol = max(0.5, bw * 0.01)
            if x < bx - tol or x + w > bx + bw + tol:
                ratio = bw / max(w, 1e-6)
                add("error", "text_overflow", f"Text overflows its area by {max(0, w - bw):.1f} units: \"{t['text'][:40]}\"",
                    t["id"])
                fix(t["id"], scale=min(0.97, ratio * 0.97))
        # 2) page edges & print-safe margin
        if x < -0.5 or x + w > vb_w + 0.5 or y < -0.5 or y + h > vb_h + 0.5:
            add("error", "clipped_by_page", f"Text runs off the page: \"{t['text'][:40]}\"", t["id"])
            fix(t["id"], scale=0.9)
        elif safe_margin > 0:
            tx, ty, tw, th = _tight(t)
            if tx < safe_margin or tx + tw > vb_w - safe_margin or ty < safe_margin or ty + th > vb_h - safe_margin:
                add("warning", "outside_safe_area", f"Text is inside the trim-risk margin: \"{t['text'][:40]}\"", t["id"])
        # 3) minimum readable size
        min_size = 6.0 if unit == "pt" else 20.0
        if t["size"] < min_size and t.get("role") not in ("placeholder",):
            add("warning", "tiny_text", f"Very small text ({t['size']:.1f}{unit}): \"{t['text'][:40]}\"", t["id"])
        # 4) contrast against actual pixels behind the text, 5) text over graphics
        if bare is not None and t.get("fill", "").startswith("#"):
            reg = _region(bare, _tight(t), (sx, sy))
            if reg is not None:
                bg, share = _mode_color(reg)
                cr = contrast_ratio(t["fill"], bg)
                large = (t["size"] >= 18 if unit == "pt" else t["size"] >= 40)
                need = 3.0 if large else 4.5
                if t.get("role") in ("art-text",):
                    need = 2.0
                if cr < need:
                    add("warning" if cr >= need * 0.75 else "error", "low_contrast",
                        f"Contrast {cr:.1f}:1 (needs {need}:1) for \"{t['text'][:40]}\"", t["id"], contrast=round(cr, 2))
                    new_fill = adjust_for_contrast(t["fill"], rgb_to_hex(bg), need + 0.3)
                    if new_fill.lower() != t["fill"].lower() and contrast_ratio(new_fill, bg) >= need:
                        fix(t["id"], fill=new_fill)
                if share < 0.9 and not t.get("allowOverlap") and t.get("role") != "art-text":
                    add("warning", "text_over_graphic",
                        f"Text sits on top of other graphics ({(1 - share) * 100:.0f}% busy background): \"{t['text'][:40]}\"",
                        t["id"])
        # 6) glyph coverage
        fam = t.get("family")
        if fam:
            try:
                miss = F.missing_glyphs(t["text"], fam)
                if miss:
                    add("error", "missing_glyphs", f"Font {fam} lacks characters {''.join(miss)}", t["id"])
            except KeyError:
                add("error", "font_not_bundled", f"Font {fam} is not a bundled, licensed font", t["id"])

    # 7) text overlapping text
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            a, b = texts[i], texts[j]
            if a.get("allowOverlap") or b.get("allowOverlap"):
                continue
            ta, tb = _tight(a), _tight(b)
            inter = _inter(ta, tb)
            if inter > 0.12 * min(ta[2] * ta[3], tb[2] * tb[3]):
                add("error", "text_overlap", f"Text overlaps: \"{a['text'][:25]}\" / \"{b['text'][:25]}\"", a["id"])
                big = a if a["size"] >= b["size"] else b
                fix(big["id"], scale=0.92)

    # 8) fonts actually loaded
    loaded = set(measure.get("loaded_fonts", []))
    for fam in {t.get("family") for t in texts if t.get("family")}:
        if fam not in loaded:
            add("error", "font_not_loaded", f"Font '{fam}' did not load; the design would fall back to another font")

    # 9) spelling
    for sp in spelling_issues(texts):
        add("warning", "spelling", f"Possible misspelling: '{sp['word']}'" +
            (f" (did you mean '{sp['suggestion']}'?)" if sp.get("suggestion") and sp["suggestion"] != sp["word"].lower() else ""),
            sp["id"])

    # 10) low-res raster images
    for im in measure.get("images", []):
        pxw = im["natural"][0]
        if pxw:
            inches = im["bbox"][2] / (72 if unit == "pt" else 96)
            dpi = pxw / max(inches, 1e-6)
            if dpi < 150:
                add("error", "low_resolution", f"Image is only {dpi:.0f} DPI at print size (needs 300)", im["id"])
            elif dpi < 280:
                add("warning", "low_resolution", f"Image is {dpi:.0f} DPI at print size (300 recommended)", im["id"])

    # 11) composition balance & density (on the full rendered preview)
    metrics = composition_metrics(prev)
    if centered and abs(metrics["h_balance"]) > 0.12:
        add("warning", "unbalanced", f"Visual weight is off-centre horizontally ({metrics['h_balance']:+.2f})")
    if metrics["ink_coverage"] < 0.005:
        add("warning", "too_empty", "Design looks nearly empty")
    if metrics["ink_coverage"] > 0.85:
        add("info", "very_dense", "Design is very dense; consider more whitespace")
    return {"issues": issues, "fixes": fixes, "metrics": metrics, "text_count": len(texts)}


def composition_metrics(img: Image.Image) -> dict:
    small = img.copy()
    small.thumbnail((200, 200))
    px = small.load()
    w, h = small.size
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    bg = Counter(corners).most_common(1)[0][0]
    tot = mx = my = 0.0
    for yy in range(h):
        for xx in range(w):
            p = px[xx, yy]
            d = (abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2])) / 765
            if d > 0.04:
                tot += d
                mx += d * xx
                my += d * yy
    cov = tot / (w * h)
    if tot == 0:
        return {"ink_coverage": 0.0, "h_balance": 0.0, "v_balance": 0.0}
    return {"ink_coverage": round(cov, 4), "h_balance": round((mx / tot) / w - 0.5, 3),
            "v_balance": round((my / tot) / h - 0.5, 3)}


def score(issues: list[dict]) -> float:
    pen = sum(SEVERITY_PENALTY.get(i["severity"], 0) for i in issues)
    return max(0.0, round(100.0 - pen, 1))


# ------------------------------------------------------------------ file validation
def validate_file(path: Path, expect: dict) -> list[dict]:
    """expect: {kind: pdf|png|jpg|svg|zip|html, w_in, h_in, dpi, px:(w,h), pages}"""
    path = Path(path)
    out: list[dict] = []

    def err(code, msg, sev="error"):
        out.append({"severity": sev, "code": code, "message": f"{path.name}: {msg}", "file": path.name})
    if not path.exists() or path.stat().st_size == 0:
        err("missing_file", "file missing or empty")
        return out
    kind = expect.get("kind")
    try:
        if kind == "pdf":
            from pypdf import PdfReader
            rd = PdfReader(str(path))
            if expect.get("pages") and len(rd.pages) != expect["pages"]:
                err("page_count", f"has {len(rd.pages)} pages, expected {expect['pages']}")
            box = rd.pages[0].mediabox
            w_in, h_in = float(box.width) / 72, float(box.height) / 72
            if abs(w_in - expect["w_in"]) > 0.02 or abs(h_in - expect["h_in"]) > 0.02:
                err("pdf_size", f'page is {w_in:.2f}x{h_in:.2f} in, expected {expect["w_in"]}x{expect["h_in"]} in')
            fonts_ok, any_font = True, False
            for pg in rd.pages[:3]:
                res = pg.get("/Resources") or {}
                fdict = res.get("/Font") or {}
                for _, fref in fdict.items():
                    any_font = True
                    f = fref.get_object()
                    desc = f.get("/FontDescriptor")
                    if desc is None and f.get("/DescendantFonts"):
                        desc = f["/DescendantFonts"][0].get_object().get("/FontDescriptor")
                    if desc is not None:
                        d = desc.get_object()
                        if not any(k in d for k in ("/FontFile", "/FontFile2", "/FontFile3")):
                            fonts_ok = False
            if any_font and not fonts_ok:
                err("fonts_not_embedded", "some fonts are not embedded (prints may substitute fonts)")
        elif kind in ("png", "jpg"):
            with Image.open(path) as im:
                im.verify()
            with Image.open(path) as im:
                if expect.get("px") and tuple(im.size) != tuple(expect["px"]):
                    err("raster_size", f"is {im.size[0]}x{im.size[1]} px, expected {expect['px'][0]}x{expect['px'][1]}")
                dpi = im.info.get("dpi")
                if expect.get("dpi") and (not dpi or round(float(dpi[0])) < expect["dpi"] - 1):
                    err("dpi_metadata", f"DPI metadata is {dpi}, expected {expect['dpi']}", "warning")
        elif kind == "svg":
            import xml.etree.ElementTree as ET
            root = ET.parse(path).getroot()
            if not root.tag.endswith("svg"):
                err("svg_invalid", "root element is not <svg>")
        elif kind == "zip":
            with zipfile.ZipFile(path) as z:
                bad = z.testzip()
                if bad:
                    err("zip_corrupt", f"corrupt member {bad}")
        elif kind == "html":
            txt = path.read_text(encoding="utf-8")
            if "<svg" not in txt:
                err("html_invalid", "personalizer has no design")
    except Exception as e:  # noqa: BLE001
        err("unreadable", f"could not be opened ({e})")
    return out


def validate_deliverables(files: list[Path]) -> list[dict]:
    out = []
    if len(files) > ETSY_MAX_FILES:
        out.append({"severity": "error", "code": "etsy_file_count",
                    "message": f"{len(files)} deliverable files; Etsy allows {ETSY_MAX_FILES} per listing"})
    for f in files:
        sz = Path(f).stat().st_size
        if sz > ETSY_MAX_BYTES:
            out.append({"severity": "error", "code": "etsy_file_size",
                        "message": f"{Path(f).name} is {sz / 1e6:.1f} MB; Etsy's limit is 20 MB per file"})
    return out
