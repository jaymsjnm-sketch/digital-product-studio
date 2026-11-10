"""Bundled fonts (all SIL Open Font License 1.1 - free for commercial use, embedding and
redistribution with products). Provides @font-face CSS and accurate text measurement."""
from __future__ import annotations

import base64
import functools
import json
from pathlib import Path

from fontTools.ttLib import TTFont

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"


@functools.lru_cache(maxsize=1)
def manifest() -> dict:
    return json.loads((FONT_DIR / "manifest.json").read_text(encoding="utf-8"))


def available_families() -> list[str]:
    return sorted(manifest().keys())


def font_file(family: str, weight: int = 400, italic: bool = False) -> Path:
    fam = manifest().get(family)
    if not fam:
        raise KeyError(f"Font family not bundled: {family}")
    style = "italic" if italic else "normal"
    files = [f for f in fam["files"] if f["style"] == style] or fam["files"]
    best = min(files, key=lambda f: abs(f["weight"] - weight))
    return FONT_DIR / best["file"]


@functools.lru_cache(maxsize=64)
def _font(path: str):
    f = TTFont(path, lazy=True)
    cmap = f.getBestCmap()
    hmtx = f["hmtx"].metrics
    upm = f["head"].unitsPerEm
    kern = {}
    # Use legacy 'kern' table when present (GPOS kerning ignored: small error, QC catches overflow).
    if "kern" in f:
        for st in f["kern"].kernTables:
            if hasattr(st, "kernTable"):
                kern.update(st.kernTable)
    os2 = f["OS/2"]
    return cmap, hmtx, upm, kern, (os2.sTypoAscender, os2.sTypoDescender, getattr(os2, "sCapHeight", 0) or int(upm * 0.7))


def text_width(text: str, family: str, size: float, weight: int = 400, italic: bool = False,
               tracking: float = 0.0) -> float:
    """Advance width of a single line in the same units as `size`. tracking is in em (CSS letter-spacing/size)."""
    cmap, hmtx, upm, kern, _ = _font(str(font_file(family, weight, italic)))
    total, prev = 0, None
    for ch in text:
        g = cmap.get(ord(ch)) or cmap.get(ord("?"))
        adv = hmtx.get(g, (upm // 2, 0))[0]
        if prev is not None and kern:
            adv += kern.get((prev, g), 0)
        total += adv
        prev = g
    w = total / upm * size
    if tracking and len(text) > 1:
        w += tracking * size * (len(text) - 1)
    return w


def cap_height(family: str, size: float, weight: int = 400) -> float:
    _, _, upm, _, (asc, desc, cap) = _font(str(font_file(family, weight)))
    return cap / upm * size


def missing_glyphs(text: str, family: str, weight: int = 400) -> list[str]:
    cmap, *_ = _font(str(font_file(family, weight)))
    return sorted({ch for ch in text if ch.strip() and ord(ch) not in cmap})


def fit_size(text: str, family: str, size: float, max_width: float, *, weight: int = 400, italic: bool = False,
             tracking: float = 0.0, min_size: float = 4.0) -> float:
    w = text_width(text, family, size, weight, italic, tracking)
    if w <= max_width:
        return size
    return max(min_size, size * max_width / w * 0.995)


def wrap(text: str, family: str, size: float, max_width: float, *, weight: int = 400, tracking: float = 0.0) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if not cur or text_width(trial, family, size, weight, tracking=tracking) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


@functools.lru_cache(maxsize=256)
def _b64(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()


def font_face_css(families_weights: set[tuple[str, int, bool]], embed: bool = True, rel_dir: str = "fonts") -> str:
    rules = []
    seen = set()
    for fam, wt, it in sorted(families_weights):
        p = font_file(fam, wt, it)
        key = (fam, p.name)
        if key in seen:
            continue
        seen.add(key)
        src = (f"url(data:font/ttf;base64,{_b64(str(p))}) format('truetype')" if embed
               else f"url('{rel_dir}/{p.parent.name}/{p.name}') format('truetype')")
        real_wt = int(p.stem.split("-")[1]) if "-" in p.stem else wt
        rules.append(f"@font-face{{font-family:'{fam}';src:{src};font-weight:{real_wt};"
                     f"font-style:{'italic' if it else 'normal'};font-display:block;}}")
    return "\n".join(rules)


def license_text(family: str) -> str:
    p = font_file(family).parent / "OFL.txt"
    return p.read_text(encoding="utf-8") if p.exists() else "SIL Open Font License 1.1"
