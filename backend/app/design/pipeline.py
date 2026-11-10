"""Design pipeline: generate -> render -> QC + auto-fix -> export -> package -> mockups.

Produces one immutable product *version* folder:
  previews/   screen previews used by the dashboard
  print/      PDF (vector, fonts embedded), PNG/JPG (300 DPI)
  editable/   SVG sources, browser personalizers (.html), fonts + licences
  mockups/    listing images (<1 MB each)
  deliverables/  <=5 files <=20 MB each, ready to upload to Etsy
  <name>_complete_bundle.zip   everything, organised
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Callable

from pypdf import PdfWriter

from ..config import log, settings
from ..qc import engine as QC
from . import fonts as F
from . import mockups as M
from . import registry as R
from .common import resolve_style
from .editor_html import build_editor
from .renderer import Renderer


def fingerprint(product_type: str, p: dict) -> str:
    pal = p.get("palette")
    key = {"t": product_type, "palette": pal if isinstance(pal, str) else json.dumps(pal, sort_keys=True),
           "fonts": p.get("fonts"), "style": p.get("style"), "theme": p.get("theme"),
           "industry": p.get("industry"), "kind": p.get("kind"), "compositions": p.get("compositions"),
           "count": p.get("count"), "content": json.dumps(p.get("content") or {}, sort_keys=True)}
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:32]


def safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:60] or "Product"


def _rel(p: Path) -> str:
    return str(Path(p).resolve().relative_to(settings.data_dir.resolve())).replace("\\", "/")


def _merge_fixes(params: dict, piece: str, fixes: dict) -> None:
    all_f = params.setdefault("_fixes", {})
    cur = all_f.setdefault(piece, {})
    for eid, fx in fixes.items():
        prev = cur.get(eid, {})
        if isinstance(prev, (int, float)):
            prev = {"scale": prev}
        merged = dict(prev)
        if "scale" in fx:
            merged["scale"] = round(prev.get("scale", 1.0) * fx["scale"], 4)
        if "fill" in fx:
            merged["fill"] = fx["fill"]
        cur[eid] = merged


def generate_version(*, product_type: str, params: dict, name: str, out_dir: Path,
                     progress: Callable[[float, str], None] | None = None, dpi: int | None = None,
                     max_fix_iterations: int = 3, make_mockups: bool = True) -> dict:
    progress = progress or (lambda pct, msg="": None)
    dpi = dpi or settings.render_dpi
    params = copy.deepcopy(params)
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    for sub in ("previews", "print", "editable", "mockups", "deliverables", "work"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)
    specs = R.pieces(product_type, params)
    palette, _ = resolve_style(params)
    files_qc: list[dict] = []
    pieces_out: list[dict] = []
    fonts_used: set = set()

    with Renderer() as rnd:
        # ---------------------------------------------------------- 1. render + QC + auto-fix
        for si, spec in enumerate(specs):
            key = spec["key"]
            progress(5 + 40 * si / len(specs), f"Designing {spec['label']}")
            check_pages = list(range(1, spec["pages"] + 1)) if spec.get("qc_pages") == "all" else \
                sorted({1, spec["pages"]})
            applied: list[dict] = []
            final_issues: list[dict] = []
            metrics = {}
            for page in check_pages:
                for it in range(max_fix_iterations + 1):
                    doc = R.build(product_type, key, params, page)
                    res = rnd.render(doc.svg(), unit=doc.unit, width=doc.width, height=doc.height,
                                     preview_path=(out_dir / "previews" / f"{key}.png") if page == 1 else None)
                    an = QC.analyze_layout(res["measure"], res["preview_png"], res.get("textless_png"), unit=doc.unit,
                                           safe_margin=doc.safe_margin, centered=R.centered_layout(product_type, key))
                    if not an["fixes"] or it == max_fix_iterations:
                        break
                    applied.append({"page": page, "iteration": it + 1, "fixed": [i["message"] for i in an["issues"]
                                                                               if i.get("element") in an["fixes"]
                                                                               or re.sub(r"_\d+$", "", i.get("element") or "") in an["fixes"]]})
                    _merge_fixes(params, key, an["fixes"])
                for i in an["issues"]:
                    i["page"] = page
                final_issues += an["issues"]
                if page == 1:
                    metrics = an["metrics"]
                    fonts_used |= doc.fonts_used
                if page != 1 and spec["pages"] > 1 and page == check_pages[-1]:
                    pass
            if spec["pages"] > 1:
                # extra multi-page previews (first few pages) for the gallery
                for page in range(2, min(spec["pages"], 6) + 1):
                    d = R.build(product_type, key, params, page)
                    rnd.render(d.svg(), unit=d.unit, width=d.width, height=d.height, measure=False,
                               preview_path=out_dir / "previews" / f"{key}_p{page}.png")
            pieces_out.append({"key": key, "label": spec["label"], "unit": spec["unit"], "pages": spec["pages"],
                               "preview": _rel(out_dir / "previews" / f"{key}.png"),
                               "extra_previews": [_rel(p) for p in sorted((out_dir / "previews").glob(f"{key}_p*.png"))],
                               "qc": {"issues": final_issues, "auto_fixes": applied, "metrics": metrics,
                                      "score": QC.score(final_issues)},
                               "files": [], "size_in": [spec.get("w_in"), spec.get("h_in")]})

        # ---------------------------------------------------------- 2. exports
        nm = safe_name(name)
        for si, spec in enumerate(specs):
            key, piece = spec["key"], pieces_out[si]
            progress(45 + 35 * si / len(specs), f"Exporting {spec['label']}")
            base = f"{nm}_{key}"
            doc1 = R.build(product_type, key, params, 1)
            if "pdf" in spec["formats"]:
                pdf_path = out_dir / "print" / f"{base}.pdf"
                if spec["pages"] == 1:
                    rnd.render(doc1.svg(), unit=doc1.unit, width=doc1.width, height=doc1.height, pdf_path=pdf_path,
                               measure=False)
                else:
                    writer = PdfWriter()
                    for page in range(1, spec["pages"] + 1):
                        d = R.build(product_type, key, params, page)
                        tmp = out_dir / "work" / f"{key}_{page}.pdf"
                        rnd.render(d.svg(), unit=d.unit, width=d.width, height=d.height, pdf_path=tmp, measure=False)
                        writer.append(str(tmp))
                    with open(pdf_path, "wb") as fh:
                        writer.write(fh)
                piece["files"].append(_file(pdf_path, "pdf", {"kind": "pdf", "w_in": spec["w_in"], "h_in": spec["h_in"],
                                                               "pages": spec["pages"]}, files_qc))
            if "png" in spec["formats"]:
                for page in range(1, spec["pages"] + 1):
                    d = doc1 if page == 1 else R.build(product_type, key, params, page)
                    suffix = f"_{page:02d}" if spec["pages"] > 1 else ""
                    png = out_dir / "print" / f"{base}{suffix}.png"
                    rnd.render(d.svg(), unit=d.unit, width=d.width, height=d.height, png_path=png, measure=False, dpi=dpi)
                    px = (round(spec["w_in"] * dpi), round(spec["h_in"] * dpi)) if spec["unit"] == "pt" else (int(spec["w"]), int(spec["h"]))
                    piece["files"].append(_file(png, "png", {"kind": "png", "px": px,
                                                               "dpi": dpi if spec["unit"] == "pt" else None}, files_qc))
            if "jpg" in spec["formats"]:
                for v in spec.get("ratios", []):
                    d = R.build(product_type, key, params, 1, ratio=v["ratio"])
                    jpg = out_dir / "print" / f"{base}_{v['ratio']}.jpg"
                    rnd.render(d.svg(), unit=d.unit, width=d.width, height=d.height, jpg_path=jpg, measure=False,
                               dpi=dpi, jpg_quality=90)
                    f = _file(jpg, "jpg", {"kind": "jpg", "px": (round(v["w_in"] * dpi), round(v["h_in"] * dpi)),
                                            "dpi": dpi}, files_qc)
                    f.update(ratio=v["ratio"], prints=v["prints"])
                    piece["files"].append(f)
            if "svg" in spec["formats"]:
                svg_path = out_dir / "editable" / f"{base}.svg"
                svg_path.write_text(doc1.svg(embed_fonts=True), encoding="utf-8")
                piece["files"].append(_file(svg_path, "svg", {"kind": "svg"}, files_qc))
            if "html" in spec["formats"]:
                html_path = out_dir / "editable" / f"{base}_personalize.html"
                html_path.write_text(build_editor(doc1.svg(embed_fonts=True), title=f"{name} - {spec['label']}",
                                                  w_in=spec.get("w_in"), h_in=spec.get("h_in"),
                                                  px=(int(spec["w"]), int(spec["h"])),
                                                  note=("Change the number field to print every table number."
                                                        if key == "table_number" else "")), encoding="utf-8")
                piece["files"].append(_file(html_path, "html", {"kind": "html"}, files_qc))

        # ---------------------------------------------------------- 3. fonts + licences
        fdir = out_dir / "editable" / "fonts"
        fdir.mkdir(exist_ok=True)
        for fam in sorted({f[0] for f in fonts_used}):
            src = F.font_file(fam).parent
            dst = fdir / src.name
            shutil.copytree(src, dst, dirs_exist_ok=True)

        # ---------------------------------------------------------- 4. mockups
        mock = []
        if make_mockups:
            progress(82, "Creating listing mockups")
            mock = make_listing_images(rnd, product_type, params, pieces_out, out_dir, palette, name)

        # ---------------------------------------------------------- 5. packaging
        progress(92, "Packaging bundle and Etsy deliverables")
        readme = out_dir / "work" / "READ_ME_FIRST.pdf"
        rnd.pdf_from_html(readme_html(product_type, name, pieces_out, sorted({f[0] for f in fonts_used})), 8.5, 11, readme)
        deliverables = package(product_type, name, out_dir, pieces_out, readme)
    files_qc += QC.validate_deliverables([out_dir / "deliverables" / d["name"] for d in deliverables])
    for d in deliverables:
        if d["name"].endswith(".zip"):
            files_qc += QC.validate_file(out_dir / "deliverables" / d["name"], {"kind": "zip"})

    bundle = out_dir / f"{nm}_complete_bundle.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
        for sub in ("print", "editable", "mockups"):
            for f in sorted((out_dir / sub).rglob("*")):
                if f.is_file():
                    z.write(f, f"{nm}/{sub}/{f.relative_to(out_dir / sub)}")
        z.write(readme, f"{nm}/READ_ME_FIRST.pdf")
    shutil.rmtree(out_dir / "work", ignore_errors=True)

    design_issues = [i for p in pieces_out for i in p["qc"]["issues"]]
    piece_scores = [p["qc"]["score"] for p in pieces_out]
    overall = round(min(piece_scores) * 0.5 + sum(piece_scores) / len(piece_scores) * 0.5, 1) if piece_scores else 0
    file_errors = [f for f in files_qc if f["severity"] == "error"]
    overall = max(0.0, overall - 10 * len(file_errors))
    progress(100, "Done")
    clean_params = {k: v for k, v in params.items()}
    return {"pieces": pieces_out, "mockups": mock, "deliverables": deliverables, "bundle_zip": _rel(bundle),
            "bundle_bytes": bundle.stat().st_size, "params": clean_params,
            "qc": {"score": overall, "design_issue_count": len(design_issues), "file_checks": files_qc,
                   "file_errors": len(file_errors), "auto_fix_rounds": sum(len(p["qc"]["auto_fixes"]) for p in pieces_out),
                   "disclaimer": "Automated checks catch measurable problems (overflow, overlap, contrast, sizes, "
                                 "files). They cannot judge taste. Review every preview before approving."}}


def _file(path: Path, fmt: str, expect: dict, files_qc: list) -> dict:
    issues = QC.validate_file(path, expect)
    files_qc.extend(issues)
    return {"name": Path(path).name, "path": _rel(path), "format": fmt, "bytes": Path(path).stat().st_size,
            "valid": not any(i["severity"] == "error" for i in issues)}


def _zip(dest: Path, entries: list[tuple[Path, str]]) -> Path:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in entries:
            if src.is_dir():
                for f in sorted(src.rglob("*")):
                    if f.is_file():
                        z.write(f, f"{arc}/{f.relative_to(src)}")
            else:
                z.write(src, arc)
    return dest


def package(product_type: str, name: str, out_dir: Path, pieces: list[dict], readme: Path) -> list[dict]:
    """Build <=5 Etsy deliverable files, each <=20 MB, splitting archives when needed."""
    nm = safe_name(name)
    dd = out_dir / "deliverables"
    data = settings.data_dir
    files = [(data / f["path"], f) for p in pieces for f in p["files"]]
    out: list[Path] = []

    def zip_group(label: str, items: list[tuple[Path, str]]):
        # split into parts under ~19 MB
        parts, cur, size = [], [], 0
        for src, arc in items:
            sz = src.stat().st_size if src.is_file() else sum(f.stat().st_size for f in src.rglob("*") if f.is_file())
            if cur and size + sz > 19_000_000:
                parts.append(cur)
                cur, size = [], 0
            cur.append((src, arc))
            size += sz
        if cur:
            parts.append(cur)
        for i, part in enumerate(parts):
            suffix = f"_part{i + 1}" if len(parts) > 1 else ""
            out.append(_zip(dd / f"{nm}_{label}{suffix}.zip", part + [(readme, "READ_ME_FIRST.pdf")]))

    if product_type == "wall_art_set":
        ratios: dict[str, list] = {}
        for src, f in files:
            if f["format"] == "jpg":
                ratios.setdefault(f["ratio"], []).append((src, src.name))
        for r, items in ratios.items():
            zip_group(f"ratio_{r}", items)
        if len(out) < 5:
            pass
    elif product_type == "budget_planner":
        for src, f in files:
            dst = dd / src.name
            shutil.copy(src, dst)
            out.append(dst)
        dst = dd / "READ_ME_FIRST.pdf"
        shutil.copy(readme, dst)
        out.append(dst)
    else:
        zip_group("Print_PDF", [(s, s.name) for s, f in files if f["format"] == "pdf"])
        zip_group("Print_PNG", [(s, s.name) for s, f in files if f["format"] == "png"])
        zip_group("Editable_Templates", [(s, s.name) for s, f in files if f["format"] in ("svg", "html")] +
                  [(out_dir / "editable" / "fonts", "fonts")])
        dst = dd / "READ_ME_FIRST.pdf"
        shutil.copy(readme, dst)
        out.append(dst)
    return [{"name": p.name, "path": _rel(p), "bytes": p.stat().st_size} for p in out]


def readme_html(product_type: str, name: str, pieces: list[dict], families: list[str]) -> str:
    rows = "".join(f"<li><b>{p['label']}</b>" + (f" - {p['pages']} pages" if p["pages"] > 1 else "") + "</li>"
                   for p in pieces)
    edit = {
        "wall_art_set": "<p>These are high-resolution (300 DPI) JPG files. Choose the file whose ratio matches your frame "
                        "(see the size guide) and print at home, at a local print shop or with an online print service.</p>",
        "budget_planner": "<p>Print the PDF on US Letter or A4 paper at <b>100% / actual size</b>. Print single pages as many "
                          "times as you need.</p>",
    }.get(product_type, """
<h2>How to edit</h2>
<ol><li><b>Easiest - in your browser:</b> open any <i>_personalize.html</i> file in Chrome, Edge, Safari or Firefox.
Type your details; text resizes automatically. Click <i>Print / Save as PDF</i> (margins: None, scale: 100%).</li>
<li><b>Full design control:</b> open the <i>.svg</i> files in Inkscape (free), Adobe Illustrator, Affinity Designer or Figma.
Install the fonts from the <i>fonts</i> folder first so text stays editable and looks right.</li>
<li><b>Ready to print as-is:</b> the PDF and 300 DPI PNG files can be printed directly.</li></ol>""")
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{font-family:Georgia,serif;color:#222;margin:0.8in;font-size:12pt;line-height:1.5}} h1{{font-weight:normal;font-size:26pt;margin:0 0 4pt}}
h2{{font-size:14pt;margin:18pt 0 6pt;font-family:Helvetica,Arial,sans-serif;letter-spacing:.06em;text-transform:uppercase}}
.small{{font-size:9.5pt;color:#555}}</style></head><body>
<h1>{name}</h1><p class="small">Digital download. No physical item will be shipped.</p>
<h2>What's included</h2><ul>{rows}</ul>{edit}
<h2>Printing tips</h2><ul><li>Print at 100% / "actual size" (turn off "fit to page").</li>
<li>Heavy matte cardstock (250-300 gsm / 80-110 lb cover) gives the most professional finish.</li>
<li>Colours vary slightly between screens and printers.</li></ul>
<h2>Terms of use</h2><p>For your personal use (or your own business's marketing for business templates). Please do not resell,
share or redistribute the files themselves.</p>
<h2>Fonts</h2><p>Fonts used: {", ".join(families) or "none"}. All are licensed under the SIL Open Font License 1.1, free for
personal and commercial use. Licence files are included in the fonts folder.</p>
<p class="small">Artwork and layouts are original designs created with our own design software.</p></body></html>"""


def make_listing_images(rnd: Renderer, product_type: str, params: dict, pieces: list[dict], out_dir: Path,
                        palette: dict, name: str) -> list[dict]:
    data = settings.data_dir
    prev = {p["key"]: data / p["preview"] for p in pieces}
    md = out_dir / "mockups"
    jobs: list[tuple[str, str, str]] = []
    if product_type == "wall_art_set":
        arts = [prev[k] for k in prev]
        jobs.append(("01_hero_gallery_wall", M.wall_scene(arts[:3], palette, f"Set of {len(arts)} prints"), "Gallery wall scene"))
        jobs.append(("02_single_print", M.wall_scene(arts[:1], palette, "Original artwork"), "Single print in frame"))
        jobs.append(("03_whats_included", M.included_sheet([(prev[k], f"Print {i + 1}") for i, k in enumerate(prev)],
                                                           palette, "What's included",
                                                           ["5 ratios per print", "300 DPI JPG", "Instant download"]),
                     "What's included"))
        from .products.wall_art import RATIOS
        jobs.append(("04_size_guide", M.info_sheet("Size guide", [(k, v["prints"]) for k, v in RATIOS.items()], palette,
                                                   "Every print comes in 5 ratios"), "Print size guide"))
    elif product_type == "wedding_suite":
        cards = [(prev[k], (p["size_in"][1] / p["size_in"][0])) for k, p in ((p["key"], p) for p in pieces)
                 if k in ("invitation", "menu", "thank_you", "table_number")]
        order = {"invitation": 0, "menu": 1, "table_number": 2, "thank_you": 3}
        cards.sort(key=lambda c: order.get(c[0].stem, 9))
        jobs.append(("01_hero_flatlay", M.flatlay_scene(cards, palette, "Editable wedding suite"), "Stationery flat lay"))
        signs = [prev[k] for k in ("welcome_sign", "seating_chart") if k in prev]
        if signs:
            jobs.append(("02_signage", M.wall_scene(signs, palette, "Welcome sign + seating chart"), "Large signs"))
        jobs.append(("03_whats_included", M.included_sheet([(prev[p["key"]], p["label"]) for p in pieces], palette,
                                                           "What's included",
                                                           ["PDF + 300 DPI PNG", "Editable SVG", "Browser personalizer"]),
                     "What's included"))
        jobs.append(("04_how_to_edit", M.info_sheet("Edit in minutes", [
            ("1  Open", "the personalizer in your browser"), ("2  Type", "your names, date and details"),
            ("3  Print", "save as PDF and print anywhere"), ("Pro option", "edit SVGs in Inkscape or Illustrator")],
            palette, "No app or account needed"), "How to edit"))
    elif product_type == "business_kit":
        if all(k in prev for k in ("ig_post", "ig_story", "flyer")):
            jobs.append(("01_hero_devices", M.devices_scene(prev["ig_post"], prev["ig_story"], prev["flyer"], palette,
                                                            "Marketing kit"), "Print + social scene"))
        jobs.append(("02_whats_included", M.included_sheet([(prev[p["key"]], p["label"].split(" (")[0]) for p in pieces],
                                                           palette, "What's included",
                                                           ["6 coordinated designs", "PDF + PNG", "Editable SVG"]),
                     "What's included"))
        jobs.append(("03_how_to_edit", M.info_sheet("Make it yours", [
            ("1  Open", "the personalizer in your browser"), ("2  Type", "your business details & prices"),
            ("3  Export", "print or save for social media"), ("Canva option", "import the PDF into Canva")],
            palette, "No design skills needed"), "How to edit"))
    elif product_type == "budget_planner":
        key = pieces[0]["key"]
        pages = [prev[key]] + [data / x for x in pieces[0]["extra_previews"]]
        jobs.append(("01_hero_pages", M.pages_scene(pages, palette, f"{pieces[0]['pages']} printable pages"), "Planner pages"))
        jobs.append(("02_whats_included", M.included_sheet([(pg, f"Page {i + 1}") for i, pg in enumerate(pages)], palette,
                                                           "What's inside", ["US Letter + A4", "Print unlimited copies",
                                                                             "Instant download"]), "What's inside"))
    out = []
    for fname, html, caption in jobs:
        path = md / f"{fname}.jpg"
        try:
            rnd.html_to_image(html, M.W, M.HT, path, quality=88, max_bytes=M.MAX_BYTES)
            out.append({"name": path.name, "path": _rel(path), "caption": caption, "bytes": path.stat().st_size})
        except Exception as e:  # noqa: BLE001
            log.warning("mockup %s failed: %s", fname, e)
    return out
