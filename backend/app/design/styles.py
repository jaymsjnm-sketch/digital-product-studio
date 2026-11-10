"""Colour palettes, font pairings and colour utilities for the design engine."""
from __future__ import annotations

import colorsys
import re


# ------------------------------------------------------------------ colour utils
def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, int(round(c)))):02x}" for c in rgb[:3])


def rel_luminance(rgb) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb[:3]
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_ratio(a, b) -> float:
    a = hex_to_rgb(a) if isinstance(a, str) else a
    b = hex_to_rgb(b) if isinstance(b, str) else b
    la, lb = rel_luminance(a), rel_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def mix(a: str, b: str, t: float) -> str:
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    return rgb_to_hex([ra[i] + (rb[i] - ra[i]) * t for i in range(3)])


def lighten(c: str, t: float) -> str:
    return mix(c, "#ffffff", t)


def darken(c: str, t: float) -> str:
    return mix(c, "#000000", t)


def adjust_for_contrast(fg: str, bg: str, target: float = 4.5) -> str:
    """Darken/lighten fg until it reaches the target contrast against bg."""
    if contrast_ratio(fg, bg) >= target:
        return fg
    dark_bg = rel_luminance(hex_to_rgb(bg)) < 0.4
    c = fg
    for i in range(1, 21):
        c = lighten(fg, i * 0.05) if dark_bg else darken(fg, i * 0.05)
        if contrast_ratio(c, bg) >= target:
            return c
    return "#ffffff" if dark_bg else "#111111"


# ------------------------------------------------------------------ named colours (for plain-English revisions)
NAMED_COLORS = {
    "sage": "#9caf88", "sage green": "#9caf88", "dusty sage": "#a3b19b", "olive": "#6b7046", "eucalyptus": "#8fa89b",
    "forest green": "#2f4a3a", "emerald": "#1f5f4a", "green": "#4f7a52", "mint": "#bfe0cf",
    "cream": "#f6f0e4", "ivory": "#fbf8f1", "off white": "#f7f5f0", "white": "#ffffff", "beige": "#e9dcc7",
    "sand": "#e4d4bc", "oat": "#e8ddcb", "taupe": "#a89584", "mocha": "#7b5e4a", "brown": "#6a4a35",
    "terracotta": "#c46a4a", "rust": "#b4532a", "burnt orange": "#c35a2a", "orange": "#e07b39", "peach": "#f4c2a5",
    "apricot": "#f2b48b", "coral": "#e8735f", "blush": "#f0d0c7", "blush pink": "#efc9c0", "dusty rose": "#c9938c",
    "rose": "#d17c86", "pink": "#ef9fb4", "hot pink": "#e2457a", "mauve": "#a8798a", "burgundy": "#6e1f2f",
    "wine": "#6a2234", "maroon": "#5e1a24", "red": "#c0392b", "lavender": "#b8a9d6", "lilac": "#c8b6db",
    "purple": "#6c4f8c", "plum": "#5b3256", "navy": "#1f2d4a", "navy blue": "#1f2d4a", "dusty blue": "#8aa1b9",
    "blue": "#3d6a9e", "sky blue": "#a8cbe8", "powder blue": "#c3d7e8", "teal": "#2d6e6e", "slate": "#5d6d7e",
    "gold": "#b8955a", "champagne": "#e3d3b4", "mustard": "#d6a336", "yellow": "#f2c94c", "butter yellow": "#f6e3a1",
    "charcoal": "#33363b", "black": "#151515", "grey": "#8a8d91", "gray": "#8a8d91", "silver": "#b9bcc0",
}


def find_colors(text: str) -> list[str]:
    """Return named colours mentioned in text, longest names first, in order of appearance."""
    t = text.lower()
    hits = []
    taken = [False] * len(t)
    for name in sorted(NAMED_COLORS, key=len, reverse=True):
        for m in re.finditer(r"\b" + re.escape(name) + r"\b", t):
            if not any(taken[m.start():m.end()]):
                hits.append((m.start(), name))
                for i in range(m.start(), m.end()):
                    taken[i] = True
    for m in re.finditer(r"#[0-9a-fA-F]{6}\b", text):
        hits.append((m.start(), m.group(0)))
    return [NAMED_COLORS.get(n, n) for _, n in sorted(hits)]


def palette_from_colors(colors: list[str], base: dict | None = None) -> dict:
    """Build a full, contrast-safe palette from 1-4 user-named colours."""
    base = dict(base or PALETTES["sage_ivory"])
    if not colors:
        return base
    by_light = sorted(colors, key=lambda c: rel_luminance(hex_to_rgb(c)), reverse=True)
    lightest, darkest = by_light[0], by_light[-1]
    p = dict(base)
    if rel_luminance(hex_to_rgb(lightest)) > 0.6:
        p["bg"] = lightest
        p["paper"] = mix(lightest, "#ffffff", 0.4)
    p["accent"] = darkest if len(colors) > 1 or rel_luminance(hex_to_rgb(darkest)) < 0.6 else colors[0]
    mids = [c for c in colors if c not in (lightest,)] or [colors[0]]
    p["accent"] = mids[0]
    p["accent2"] = mids[1] if len(mids) > 1 else mix(mids[0], p["bg"], 0.45)
    p["ink"] = adjust_for_contrast(darken(p["accent"], 0.55), p["bg"], 7.0)
    p["muted"] = mix(p["accent"], p["bg"], 0.35)
    p["art"] = [p["accent"], p["accent2"], mix(p["accent"], p["ink"], 0.4), mix(p["accent2"], p["bg"], 0.5),
                lighten(p["accent"], 0.5)]
    p["name"] = "custom"
    return p


# ------------------------------------------------------------------ palettes
PALETTES: dict[str, dict] = {
    "sage_ivory": {"bg": "#fbf8f1", "paper": "#ffffff", "ink": "#2e3a2f", "accent": "#7d9471", "accent2": "#c9b99a",
                   "muted": "#b9c4ae", "art": ["#7d9471", "#c9b99a", "#3f5641", "#e3d7c1", "#a9b99b"]},
    "terracotta_sand": {"bg": "#f4ebe0", "paper": "#fbf6ef", "ink": "#3a2a22", "accent": "#c06a47", "accent2": "#d9a679",
                        "muted": "#d8c3ad", "art": ["#c06a47", "#e2b48c", "#7b4a35", "#efd9c2", "#9c6b4e"]},
    "blush_mauve": {"bg": "#fbf4f1", "paper": "#ffffff", "ink": "#4a3036", "accent": "#b9838a", "accent2": "#e6c5bd",
                    "muted": "#e0c6c4", "art": ["#b9838a", "#e6c5bd", "#7d4f58", "#f3e1db", "#d3a7a3"]},
    "luxe_black_gold": {"bg": "#141414", "paper": "#1c1c1c", "ink": "#f3ece0", "accent": "#c8a463", "accent2": "#8c7442",
                        "muted": "#5a5248", "art": ["#c8a463", "#f3ece0", "#8c7442", "#3a3631", "#e2cfa4"]},
    "navy_champagne": {"bg": "#f7f3ec", "paper": "#ffffff", "ink": "#1f2d4a", "accent": "#1f2d4a", "accent2": "#c9ae7c",
                       "muted": "#c8cdd6", "art": ["#1f2d4a", "#c9ae7c", "#8aa1b9", "#efe4cf", "#4c6688"]},
    "dusty_blue": {"bg": "#f5f6f4", "paper": "#ffffff", "ink": "#26323f", "accent": "#7d96ad", "accent2": "#cfd8df",
                   "muted": "#c2ccd5", "art": ["#7d96ad", "#cfd8df", "#3e5469", "#e8ecee", "#a7b8c7"]},
    "minimal_mono": {"bg": "#ffffff", "paper": "#ffffff", "ink": "#1d1d1d", "accent": "#1d1d1d", "accent2": "#9a9a9a",
                     "muted": "#d9d9d9", "art": ["#1d1d1d", "#9a9a9a", "#d9d9d9", "#5c5c5c", "#efefef"]},
    "boho_sunset": {"bg": "#f3e9dc", "paper": "#fbf5ec", "ink": "#3b2b20", "accent": "#c4683c", "accent2": "#e3a857",
                    "muted": "#d9bfa3", "art": ["#c4683c", "#e3a857", "#8a4b2f", "#e9c9a6", "#b9806a", "#6f7a5a"]},
    "whimsy_pop": {"bg": "#fbf3e6", "paper": "#fffaf2", "ink": "#2c2340", "accent": "#e2577b", "accent2": "#f4b63f",
                   "muted": "#f1d9c4", "art": ["#e2577b", "#f4b63f", "#3f7cc2", "#7cb87a", "#f39a6b", "#2c2340"]},
    "olive_cream": {"bg": "#f3eee2", "paper": "#faf7f0", "ink": "#2f3121", "accent": "#6d7148", "accent2": "#c7a97a",
                    "muted": "#d1ccb4", "art": ["#6d7148", "#c7a97a", "#a3502f", "#e4dac2", "#3d4229"]},
    "holiday_whimsy": {"bg": "#f6efe4", "paper": "#fffaf3", "ink": "#2b2a24", "accent": "#b8423a", "accent2": "#2f6a4f",
                       "muted": "#e6d6c0", "art": ["#b8423a", "#2f6a4f", "#e6b450", "#e88f86", "#8fb39a", "#2b2a24"]},
    "espresso_latte": {"bg": "#efe6da", "paper": "#f8f2ea", "ink": "#2e2119", "accent": "#6b4a36", "accent2": "#c19a77",
                       "muted": "#d7c6b3", "art": ["#6b4a36", "#c19a77", "#a07a5c", "#e7d8c6", "#3d2c22"]},
}
for _k, _v in PALETTES.items():
    _v.setdefault("name", _k)

# ------------------------------------------------------------------ font pairings (all SIL OFL - commercial use OK)
FONT_PAIRINGS: dict[str, dict] = {
    "elegant": {"display": "Cormorant Garamond", "script": "Pinyon Script", "body": "Cormorant Garamond",
                "caps": "Montserrat", "display_weight": 500, "body_weight": 500, "caps_weight": 500},
    "romantic": {"display": "Playfair Display", "script": "Great Vibes", "body": "Lato", "caps": "Lato",
                 "display_weight": 400, "body_weight": 400, "caps_weight": 400},
    "modern": {"display": "Italiana", "script": "Allura", "body": "Jost", "caps": "Jost",
               "display_weight": 400, "body_weight": 300, "caps_weight": 400},
    "classic": {"display": "Libre Baskerville", "script": "Parisienne", "body": "Libre Baskerville", "caps": "Montserrat",
                "display_weight": 400, "body_weight": 400, "caps_weight": 500},
    "luxury": {"display": "Cormorant Infant", "script": "Pinyon Script", "body": "Cormorant Infant", "caps": "Marcellus",
               "display_weight": 500, "body_weight": 500, "caps_weight": 400},
    "editorial": {"display": "DM Serif Display", "script": "Allura", "body": "DM Sans", "caps": "DM Sans",
                  "display_weight": 400, "body_weight": 400, "caps_weight": 500},
    "bold": {"display": "Bebas Neue", "script": "Great Vibes", "body": "Outfit", "caps": "Outfit",
             "display_weight": 400, "body_weight": 400, "caps_weight": 600},
    "friendly": {"display": "Fraunces", "script": "Allura", "body": "Outfit", "caps": "Outfit",
                 "display_weight": 600, "body_weight": 400, "caps_weight": 500},
    "minimal": {"display": "Josefin Sans", "script": "Allura", "body": "Josefin Sans", "caps": "Josefin Sans",
                "display_weight": 300, "body_weight": 300, "caps_weight": 400},
}

STYLE_KEYWORDS = {
    "minimal": {"ornament": 0, "fonts": "minimal", "spacing": 1.15},
    "minimalist": {"ornament": 0, "fonts": "minimal", "spacing": 1.15},
    "elegant": {"fonts": "elegant"},
    "luxury": {"fonts": "luxury", "palette": "luxe_black_gold", "ornament": 1},
    "luxurious": {"fonts": "luxury", "palette": "luxe_black_gold", "ornament": 1},
    "romantic": {"fonts": "romantic", "palette": "blush_mauve", "ornament": 2},
    "modern": {"fonts": "modern", "ornament": 1},
    "classic": {"fonts": "classic", "ornament": 1},
    "boho": {"palette": "boho_sunset", "fonts": "modern", "ornament": 2},
    "rustic": {"palette": "olive_cream", "fonts": "classic", "ornament": 2},
    "bold": {"fonts": "bold"},
    "playful": {"fonts": "friendly", "palette": "whimsy_pop"},
    "whimsical": {"fonts": "friendly", "palette": "whimsy_pop"},
    "editorial": {"fonts": "editorial"},
    "botanical": {"ornament": 2},
}
