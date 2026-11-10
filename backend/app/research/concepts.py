"""Turns a researched niche into concrete, producible product concepts."""
from __future__ import annotations

PRODUCT_TYPE_INFO = {
    "wedding_suite": {
        "label": "Wedding stationery suite",
        "target": "Engaged couples planning a DIY or budget-conscious wedding (most weddings are May-Oct and couples buy 4-8 months ahead).",
        "style": "Fine-line botanical or modern-minimal suite: elegant serif + script pairing, sage/ivory or neutral palettes.",
        "pieces": "Invitation 5x7, welcome sign 24x36 + 18x24, seating chart 24x36, menu 4x9, table numbers 1-20, thank-you card",
        "differentiation": ["complete matching day-of suite in one purchase (a gap called out by sellers)",
                            "auto-fitting seating chart that handles 100-150+ guests",
                            "free browser-based personalizer: no Canva or Corjl account needed",
                            "editable SVG sources and the fonts included (OFL-licensed)"],
        "risks": ["very crowded category with strong incumbents",
                  "buyers expect easy editing, so support requests can grow",
                  "seasonal buying (Jan-Apr invitations, Mar-Sep signage)"],
        "est_production_cost": 0.0,
        "is_bundle": True,
    },
    "wall_art_set": {
        "label": "Printable wall art set",
        "target": "Renters and home decorators who want an affordable coordinated gallery wall they can print locally.",
        "style": "Textured, print-like generative abstract art: cut-paper organic shapes, arches and suns in coordinated palettes.",
        "pieces": "3 coordinating prints, each in 5 frame ratios (2:3, 3:4, 4:5, 11x14, ISO A) at 300 DPI",
        "differentiation": ["every ratio included, with a frame-size guide", "coordinated set rather than single prints",
                            "original generative artwork (not stock or traced)", "trend palettes (whimsical, warm neutrals)"],
        "risks": ["one of the most saturated digital categories", "low price points",
                  "needs a distinct style or sub-niche to stand out"],
        "est_production_cost": 0.0,
        "is_bundle": True,
    },
    "business_kit": {
        "label": "Small-business marketing kit",
        "target": "Solo service businesses (salons, lash and nail techs, agents, boutiques) who need on-brand marketing quickly.",
        "style": "Editorial, brand-ready layouts: serif headline + clean sans body, neutral or bold palettes.",
        "pieces": "Flyer 8.5x11, price list 8.5x11, promo poster 18x24, Instagram post 1080x1080, Instagram story 1080x1920, web banner 1640x624",
        "differentiation": ["one coordinated kit (print + social + web) instead of one-offs",
                            "industry-specific copy pack", "editable SVG + browser personalizer, with Canva import optional"],
        "risks": ["competes with Canva's free templates", "buyers want Canva links (requires Canva Connect setup)"],
        "est_production_cost": 0.0,
        "is_bundle": True,
    },
    "budget_planner": {
        "label": "Printable planner",
        "target": "People building a budgeting or habit routine who prefer paper planning.",
        "style": "Clean minimal pages with soft colour headers. Letter + A4.",
        "pieces": "Annual overview, monthly budget, expense tracker, bill tracker, savings tracker, debt payoff (or habit pages)",
        "differentiation": ["Letter and A4 both included", "a sharper angle (paycheck-based budgeting)",
                            "a clean, uncluttered layout with generous writing space"],
        "risks": ["saturated, with near-identical bestsellers", "low price points"],
        "est_production_cost": 0.0,
        "is_bundle": True,
    },
    "not_supported_yet": {
        "label": "Research-only (no generator yet)",
        "target": "",
        "style": "",
        "pieces": "",
        "differentiation": [],
        "risks": ["The design engine cannot produce this product type automatically yet."],
        "est_production_cost": 0.0,
        "is_bundle": False,
    },
}

INDUSTRY_LABEL = {"beauty": "beauty / lash / nail salon", "real_estate": "real estate agent", "boutique": "boutique / shop",
                  "cafe": "cafe / bakery", "fitness": "fitness coach"}


def concepts_for_niche(niche: dict) -> list[dict]:
    out = []
    for pt in niche.get("product_types") or ["not_supported_yet"]:
        info = PRODUCT_TYPE_INFO.get(pt, PRODUCT_TYPE_INFO["not_supported_yet"])
        params: dict = {}
        name = niche["name"]
        if pt == "business_kit":
            ind = niche.get("business_industry") or "beauty"
            params["industry"] = ind
            name = f"{INDUSTRY_LABEL.get(ind, ind).title()} marketing kit"
        elif pt == "wall_art_set":
            params["theme"] = niche.get("art_theme") or ("whimsical" if "whimsical" in niche["slug"] else "boho")
            name = {"holiday": "Whimsical holiday printable wall art set",
                    "whimsical": "Whimsical abstract printable wall art set (3 prints)",
                    "boho": "Boho abstract printable wall art set (3 prints)"}[params["theme"]]
        elif pt == "wedding_suite":
            params["pieces"] = (["welcome_sign", "seating_chart", "menu", "table_number", "invitation", "thank_you"]
                                if "signage" in niche["slug"] else
                                ["invitation", "welcome_sign", "seating_chart", "menu", "table_number", "thank_you"])
            name = ("Botanical wedding day-of signage bundle" if "signage" in niche["slug"]
                    else "Editable botanical wedding invitation suite")
        elif pt == "budget_planner":
            params["kind"] = niche.get("planner_kind") or "budget"
            name = "Paycheck budget planner printable" if params["kind"] == "budget" else "Habit & productivity planner printable"
        out.append({"product_type": pt, "concept": name, "info": info, "params": params})
    return out
