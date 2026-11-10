"""Printable wall art sets: N coordinated prints, each exported in 5 frame ratios at 300 DPI."""
from __future__ import annotations

import base64
import random
from pathlib import Path

from .. import art as A
from ..common import resolve_style
from ..svg import Doc

RATIOS = {  # ratio key -> largest print size in inches (portrait); smaller sizes print from the same file
    "2x3": {"size": (24, 36), "prints": "4x6, 8x12, 12x18, 16x24, 20x30, 24x36 in"},
    "3x4": {"size": (18, 24), "prints": "6x8, 9x12, 12x16, 18x24 in"},
    "4x5": {"size": (16, 20), "prints": "4x5, 8x10, 16x20 in"},
    "11x14": {"size": (11, 14), "prints": "11x14 in"},
    "ISO": {"size": (23.39, 33.11), "prints": "A5, A4, A3, A2, A1"},
}
PREVIEW_RATIO = "2x3"


def piece_list(p: dict) -> list[str]:
    n = int(p.get("count", 3))
    return [f"print{i + 1}" for i in range(n)]


def compositions(p: dict) -> list[str]:
    theme = p.get("theme", "boho")
    order = list(p.get("compositions") or A.THEME_SETS.get(theme, A.THEME_SETS["boho"]))
    n = int(p.get("count", 3))
    while len(order) < n:
        order += order
    return order[:n]


def build(piece: str, p: dict, page: int = 1, ratio: str = PREVIEW_RATIO) -> Doc:
    palette, fonts = resolve_style(p)
    idx = int(piece.replace("print", "")) - 1
    comp = compositions(p)[idx]
    w, h = RATIOS[ratio]["size"]
    if p.get("orientation") == "landscape":
        w, h = h, w
    doc = Doc(width=w * 72, height=h * 72, unit="pt", bg=palette["bg"], title=f"Print {idx + 1} ({ratio})",
              safe_margin=0)
    rnd = random.Random(int(p.get("seed", 7)) * 100 + idx)
    ai = (p.get("ai_images") or {}).get(str(idx))
    if ai and Path(ai["path"]).exists():
        # AI artwork (opt-in): cover-fit inside a margin; QC checks its effective DPI.
        b64 = base64.b64encode(Path(ai["path"]).read_bytes()).decode()
        mgn = min(doc.width, doc.height) * 0.08
        doc.add(f'<image id="ai{idx}" href="data:image/png;base64,{b64}" x="{mgn:.2f}" y="{mgn:.2f}" '
                f'width="{doc.width - 2 * mgn:.2f}" height="{doc.height - 2 * mgn:.2f}" '
                f'preserveAspectRatio="xMidYMid slice" data-pxw="{ai["px"][0]}" data-pxh="{ai["px"][1]}"/>')
        doc.meta = {"composition": "ai", "ratio": ratio}
        return doc
    fn = A.COMPOSITIONS[comp]
    if comp == "holiday_type":
        fn(doc, palette, rnd, fonts)
    else:
        fn(doc, palette, rnd)
    if p.get("grain", False):
        A.add_grain(doc, opacity=float(p.get("grain_opacity", 0.1)))
    doc.meta = {"composition": comp, "ratio": ratio}
    return doc
