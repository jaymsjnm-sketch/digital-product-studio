"""Plain-English revision requests -> design parameter changes.

Works offline with a rule-based interpreter that understands colours, styles, typography,
spacing, sizes and "create N matching products". If ANTHROPIC_API_KEY is configured, requests
the rules don't understand are interpreted by Claude (cost-tracked, spend-limited).
"""
from __future__ import annotations

import copy
import json
import re

from ..config import settings
from ..services import Budget, ExternalServiceError, http_request
from .styles import FONT_PAIRINGS, PALETTES, STYLE_KEYWORDS, find_colors, palette_from_colors

NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def interpret(request: str, params: dict, product_type: str) -> dict:
    """Returns {params, changes:[...], understood: bool, extra_products: int}."""
    text = request.lower().strip()
    p = copy.deepcopy(params)
    p.pop("_fixes", None)  # layout changes invalidate previous auto-fixes
    changes: list[str] = []
    extra = 0

    # matching products / variations
    m = re.search(r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(more\s+)?(matching|coordinat\w*)", text)
    if m:
        extra = int(NUM.get(m.group(1), m.group(1)) if not m.group(1).isdigit() else m.group(1))
        changes.append(f"Create {extra} matching product(s) in the same style")

    # explicit palette names
    for name in PALETTES:
        if name.replace("_", " ") in text:
            p["palette"] = name
            changes.append(f"Palette -> {name.replace('_', ' ')}")

    # style keywords (minimalist, luxury, boho ...)
    for kw, delta in STYLE_KEYWORDS.items():
        if re.search(r"\b" + kw + r"\b", text):
            for k, v in delta.items():
                if k == "palette" and find_colors(request):
                    continue  # explicit colours win
                if k == "ornament":
                    p["ornament"] = v
                elif k == "spacing":
                    p["spacing"] = v
                else:
                    p[k] = v
            if product_type == "wedding_suite" and kw in ("minimal", "minimalist"):
                p["style"] = "minimal"
            if product_type == "wedding_suite" and kw in ("boho",):
                p["style"] = "arch"
            if product_type == "wedding_suite" and kw in ("luxury", "luxurious", "classic"):
                p["style"] = "classic" if kw == "classic" else "minimal"
            if product_type == "wall_art_set" and kw in ("whimsical", "playful"):
                p["theme"] = "whimsical"
            if product_type == "wall_art_set" and kw in ("minimal", "minimalist"):
                p["theme"] = "minimal"
            changes.append(f"Style: {kw}")

    # typography phrases
    if re.search(r"(typography|font|type|lettering).{0,25}(elegant|refined|sophisticated|classy)|"
                 r"(elegant|refined|sophisticated|classy).{0,25}(typography|font|type)", text):
        p["fonts"] = "luxury" if p.get("fonts") == "elegant" else "elegant"
        changes.append(f"Typography -> {p['fonts']}")
    if re.search(r"(modern|clean|sans).{0,20}(font|typography|type)", text):
        p["fonts"] = "modern"
        changes.append("Typography -> modern")
    for name in FONT_PAIRINGS:
        if re.search(rf"\b{name}\b\s+(fonts?|typography)", text):
            p["fonts"] = name
            changes.append(f"Typography -> {name}")

    # colours
    cols = find_colors(request)
    if cols and re.search(r"colou?r|palette|tone|shade|make it|use|change|switch|green|pink|blue|gold|cream|"
                          r"sage|navy|terracotta|blush|black|white|ivory|beige", text):
        base = PALETTES.get(p.get("palette")) if isinstance(p.get("palette"), str) else p.get("palette")
        p["palette"] = palette_from_colors(cols, base)
        changes.append("Colours -> " + ", ".join(cols))

    # sizes & spacing
    if re.search(r"(bigger|larger|increase).{0,15}(text|font|type)", text):
        p["text_scale"] = round(float(p.get("text_scale", 1.0)) * 1.1, 3)
        changes.append("Text 10% larger")
    if re.search(r"(smaller|reduce|decrease).{0,15}(text|font|type)", text):
        p["text_scale"] = round(float(p.get("text_scale", 1.0)) * 0.9, 3)
        changes.append("Text 10% smaller")
    if re.search(r"more (white ?space|space|breathing room|spacing)|less crowded|airier", text):
        p["spacing"] = round(float(p.get("spacing", 1.0)) * 1.15, 3)
        changes.append("More spacing")
    if re.search(r"(less|tighter|reduce) (spacing|space)|more compact", text):
        p["spacing"] = round(float(p.get("spacing", 1.0)) * 0.88, 3)
        changes.append("Tighter spacing")
    if re.search(r"(no|remove|without|fewer|less) (flowers|leaves|greenery|botanical|ornament|decoration)", text):
        p["ornament"] = 0
        changes.append("Removed decorative ornaments")
    if re.search(r"(more|add) (flowers|leaves|greenery|botanical|ornament|decoration)", text):
        p["ornament"] = 2
        changes.append("More botanical ornament")
    if re.search(r"\b(texture|grain|paper texture)\b", text) and product_type == "wall_art_set":
        p["grain"] = not re.search(r"(no|remove|without) (texture|grain)", text)
        changes.append("Paper grain texture " + ("on" if p["grain"] else "off"))
    if re.search(r"\b(new|different|another) (layout|composition|version|variation)\b|shuffle|regenerate", text):
        p["seed"] = int(p.get("seed", 1)) + 101
        changes.append("New composition seed")
    if product_type == "wall_art_set":
        m2 = re.search(r"(set of|make it|make) (\d+|three|four|five|six)\s*(prints|pieces)?", text)
        if m2 and (m2.group(3) or "set of" in m2.group(1)):
            p["count"] = int(NUM.get(m2.group(2), m2.group(2)) if not m2.group(2).isdigit() else m2.group(2))
            changes.append(f"Set of {p['count']} prints")
        if "landscape" in text:
            p["orientation"] = "landscape"
            changes.append("Landscape orientation")

    understood = bool(changes)
    if not understood and settings.anthropic_api_key:
        try:
            llm = _llm_interpret(request, p, product_type)
            p.update(llm.get("params", {}))
            changes += llm.get("changes", [])
            understood = bool(llm.get("changes"))
        except Exception as e:  # noqa: BLE001
            changes.append(f"(AI interpretation unavailable: {e})")
    return {"params": p, "changes": changes, "understood": understood, "extra_products": extra}


HELP = ("Try: 'Make this more minimalist', 'Change the colors to sage green and cream', 'Make the typography more "
        "elegant', 'Make this suitable for a luxury wedding', 'Create five matching products', 'More white space', "
        "'Bigger text', 'Remove the leaves', 'New layout', 'Set of 5 prints', 'Add paper texture'.")


def _llm_interpret(request: str, params: dict, product_type: str) -> dict:
    Budget.check(0.02, "AI revision interpretation")
    schema = {"palette": list(PALETTES), "fonts": list(FONT_PAIRINGS),
              "style": ["botanical", "arch", "classic", "minimal"], "ornament": [0, 1, 2],
              "text_scale": "0.7-1.4", "spacing": "0.7-1.5", "theme": ["boho", "whimsical", "minimal", "holiday"]}
    prompt = (f"Translate this design revision request for a {product_type} into parameter changes. Allowed: "
              f"{json.dumps(schema)}. Custom palettes may be given as {{'bg','paper','ink','accent','accent2','muted',"
              f"'art':[5 hex]}} with ink having >=7:1 contrast on bg. Current: "
              f"{json.dumps({k: v for k, v in params.items() if not k.startswith('_') and k != 'content'})}. "
              f"Request: {request!r}. Reply ONLY JSON {{\"params\":{{...}},\"changes\":[short strings]}}.")
    resp = http_request("POST", "https://api.anthropic.com/v1/messages", headers={
        "x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": settings.anthropic_model, "max_tokens": 600, "messages": [{"role": "user", "content": prompt}]})
    if resp.status_code >= 400:
        raise ExternalServiceError(f"Anthropic API {resp.status_code}")
    body = resp.json()
    u = body.get("usage", {})
    Budget.record("anthropic", "revision", u.get("input_tokens", 0) * 3e-6 + u.get("output_tokens", 0) * 15e-6)
    txt = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
    m = re.search(r"\{.*\}", txt, re.S)
    return json.loads(m.group(0)) if m else {}
