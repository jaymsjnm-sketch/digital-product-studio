"""Product-type registry: what each generator makes, default styles and variation sets."""
from __future__ import annotations

import random

from .products import business, planner, wall_art, wedding

DPI = 300

PRODUCT_TYPES = {
    "wedding_suite": {
        "label": "Wedding stationery suite",
        "defaults": {"palette": "sage_ivory", "fonts": "elegant", "style": "botanical", "ornament": 2,
                     "pieces": ["invitation", "welcome_sign", "welcome_sign_18x24", "seating_chart", "menu",
                                "table_number", "thank_you"]},
        "variations": [
            {"palette": "sage_ivory", "fonts": "elegant", "style": "botanical", "ornament": 2},
            {"palette": "terracotta_sand", "fonts": "modern", "style": "arch", "ornament": 1},
            {"palette": "navy_champagne", "fonts": "classic", "style": "classic", "ornament": 1},
            {"palette": "luxe_black_gold", "fonts": "luxury", "style": "minimal", "ornament": 0},
            {"palette": "blush_mauve", "fonts": "romantic", "style": "botanical", "ornament": 2},
            {"palette": "minimal_mono", "fonts": "minimal", "style": "minimal", "ornament": 0},
        ],
        "hero": "invitation",
    },
    "wall_art_set": {
        "label": "Printable wall art set",
        "defaults": {"theme": "boho", "palette": "boho_sunset", "fonts": "friendly", "count": 3},
        "variations": [
            {"palette": "boho_sunset", "theme": "boho"}, {"palette": "sage_ivory", "theme": "boho"},
            {"palette": "whimsy_pop", "theme": "whimsical"}, {"palette": "olive_cream", "theme": "minimal"},
            {"palette": "terracotta_sand", "theme": "boho"}, {"palette": "dusty_blue", "theme": "minimal"},
        ],
        "hero": "print1",
    },
    "business_kit": {
        "label": "Small-business marketing kit",
        "defaults": {"industry": "beauty", "palette": "blush_mauve", "fonts": "editorial"},
        "variations": [
            {"palette": "blush_mauve", "fonts": "editorial"}, {"palette": "espresso_latte", "fonts": "elegant"},
            {"palette": "olive_cream", "fonts": "friendly"}, {"palette": "navy_champagne", "fonts": "modern"},
            {"palette": "minimal_mono", "fonts": "bold"}, {"palette": "terracotta_sand", "fonts": "editorial"},
        ],
        "hero": "flyer",
    },
    "budget_planner": {
        "label": "Printable planner",
        "defaults": {"kind": "budget", "palette": "sage_ivory", "fonts": "editorial"},
        "variations": [
            {"palette": "sage_ivory", "fonts": "editorial"}, {"palette": "blush_mauve", "fonts": "elegant"},
            {"palette": "dusty_blue", "fonts": "modern"}, {"palette": "terracotta_sand", "fonts": "friendly"},
        ],
        "hero": "planner_letter",
    },
}


def default_params(product_type: str, extra: dict | None = None, seed: int | None = None) -> dict:
    p = dict(PRODUCT_TYPES[product_type]["defaults"])
    p.update(extra or {})
    p["seed"] = seed if seed is not None else random.randint(1, 9999)
    return p


def pieces(product_type: str, p: dict) -> list[dict]:
    """Returns piece specs: key, label, unit, w, h (user units), pages, formats, export variants."""
    out = []
    if product_type == "wedding_suite":
        for k in p.get("pieces", wedding.PIECES.keys()):
            info = wedding.PIECES[k]
            w, h = info["size"]
            out.append({"key": k, "label": info["label"], "unit": "pt", "w": w * 72, "h": h * 72,
                        "pages": info.get("pages", 1), "formats": ["pdf", "png", "svg", "html"], "w_in": w, "h_in": h})
    elif product_type == "wall_art_set":
        for k in wall_art.piece_list(p):
            variants = []
            for ratio, r in wall_art.RATIOS.items():
                w, h = r["size"]
                variants.append({"ratio": ratio, "w_in": w, "h_in": h, "prints": r["prints"]})
            w, h = wall_art.RATIOS[wall_art.PREVIEW_RATIO]["size"]
            out.append({"key": k, "label": f"Print {k[5:]}", "unit": "pt", "w": w * 72, "h": h * 72, "pages": 1,
                        "formats": ["jpg", "svg"], "ratios": variants, "w_in": w, "h_in": h})
    elif product_type == "business_kit":
        for k in business.piece_list(p):
            info = business.PIECES[k]
            w, h = info["size"]
            fm = ["pdf", "png", "svg", "html"] if info["unit"] == "pt" else ["png", "svg", "html"]
            out.append({"key": k, "label": info["label"], "unit": info["unit"], "w": w, "h": h, "pages": 1,
                        "formats": fm, "w_in": w / 72 if info["unit"] == "pt" else None,
                        "h_in": h / 72 if info["unit"] == "pt" else None})
    elif product_type == "budget_planner":
        for k in planner.piece_list(p):
            w, h = planner.PAPER["a4" if k.endswith("a4") else "letter"]
            out.append({"key": k, "label": "Planner - " + ("A4" if k.endswith("a4") else "US Letter"), "unit": "pt",
                        "w": w, "h": h, "pages": planner.page_count(p), "formats": ["pdf"],
                        "w_in": round(w / 72, 2), "h_in": round(h / 72, 2), "qc_pages": "all"})
    return out


def build(product_type: str, piece: str, p: dict, page: int = 1, ratio: str | None = None):
    if product_type == "wedding_suite":
        return wedding.build(piece, p, page)
    if product_type == "wall_art_set":
        return wall_art.build(piece, p, page, ratio or wall_art.PREVIEW_RATIO)
    if product_type == "business_kit":
        return business.build(piece, p, page)
    if product_type == "budget_planner":
        return planner.build(piece, p, page)
    raise ValueError(f"No generator for product type '{product_type}'")


def centered_layout(product_type: str, piece: str) -> bool:
    return not (product_type == "business_kit" and piece in ("ig_post", "web_banner")) and product_type != "budget_planner"
