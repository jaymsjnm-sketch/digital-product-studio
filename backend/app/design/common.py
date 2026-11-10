"""Shared layout helpers: vertical stacks and themed decorations."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import ornaments as O
from .styles import FONT_PAIRINGS, PALETTES, mix
from .svg import Doc


def resolve_style(params: dict) -> tuple[dict, dict]:
    pal = params.get("palette")
    palette = dict(pal) if isinstance(pal, dict) else dict(PALETTES.get(pal or "sage_ivory", PALETTES["sage_ivory"]))
    fonts = dict(FONT_PAIRINGS.get(params.get("fonts", "elegant"), FONT_PAIRINGS["elegant"]))
    return palette, fonts


@dataclass
class Block:
    height: float
    draw: Callable[[float], None]
    gap_after: float = 0.0


@dataclass
class Stack:
    """Collects blocks top-to-bottom, then centres them vertically in [top, bottom]."""
    blocks: list[Block] = field(default_factory=list)

    def add(self, height: float, draw: Callable[[float], None], gap_after: float = 0.0) -> None:
        self.blocks.append(Block(height, draw, gap_after))

    def gap(self, g: float) -> None:
        if self.blocks:
            self.blocks[-1].gap_after += g

    @property
    def total(self) -> float:
        return sum(b.height + b.gap_after for b in self.blocks) - (self.blocks[-1].gap_after if self.blocks else 0)

    def render(self, top: float, bottom: float, align: str = "center") -> tuple[float, float]:
        avail = bottom - top
        scale = 1.0
        if self.total > avail:  # compress gaps first
            gaps = sum(b.gap_after for b in self.blocks[:-1])
            over = self.total - avail
            scale = max(0.35, 1 - over / gaps) if gaps else 1.0
        total = sum(b.height for b in self.blocks) + sum(b.gap_after for b in self.blocks[:-1]) * scale
        y = top + (avail - total) / 2 if align == "center" else top
        start = y
        for i, b in enumerate(self.blocks):
            b.draw(y)
            y += b.height + (b.gap_after * scale if i < len(self.blocks) - 1 else 0)
        return start, y


def text_block(stack: Stack, doc: Doc, cx: float, content: str, *, family: str, size: float, max_width: float,
               weight=400, fill="#000", tracking=0.0, upper=False, italic=False, field=None, role="text", gap=0.0,
               asc=0.78, desc=0.25, opacity=None):
    """Adds a single text line whose height is approx. ascent+descent."""
    h = size * (asc + desc)

    def draw(y_top: float):
        doc.text(cx, y_top + size * asc, content, family=family, size=size, weight=weight, fill=fill, tracking=tracking,
                 upper=upper, italic=italic, max_width=max_width, field_label=field, role=role, opacity=opacity)
    stack.add(h, draw, gap)


def para_block(stack: Stack, doc: Doc, cx: float, content: str, *, family: str, size: float, max_width: float,
               weight=400, fill="#000", leading=1.4, tracking=0.0, field=None, gap=0.0, max_lines=None, italic=False):
    from . import fonts as F
    lines = F.wrap(content, family, size, max_width, weight=weight, tracking=tracking)
    if max_lines:
        while len(lines) > max_lines and size > 4:
            size *= 0.94
            lines = F.wrap(content, family, size, max_width, weight=weight, tracking=tracking)
    h = size * leading * (len(lines) - 1) + size * 1.03

    def draw(y_top: float):
        doc.paragraph(cx, y_top + size * 0.78, content, family=family, size=size, max_width=max_width, weight=weight,
                      fill=fill, leading=leading, field_label=field, tracking=tracking, max_lines=max_lines,
                      italic=italic)
    stack.add(h, draw, gap)


def decorate(doc: Doc, style: str, palette: dict, ornament: int, seed: int, *, scale: float = 1.0,
             frame_inset: float | None = None, spray: float = 0.36) -> dict:
    """Paints the themed background/frame. Returns the content area {top,bottom,left,right}."""
    W, H = doc.width, doc.height
    m = min(W, H)
    inset = frame_inset if frame_inset is not None else m * 0.06
    area = {"top": inset * 1.6, "bottom": H - inset * 1.6, "left": inset * 1.4, "right": W - inset * 1.4}
    line_c = palette["accent"]
    sw = max(0.5, m * 0.0024) * scale
    if style == "arch":
        aw, ax = W - 2 * inset * 1.15, inset * 1.15
        O.arch(doc, ax, inset * 1.3, aw, H - inset * 2.6, fill=palette.get("paper", "#fff"),
               stroke=None)
        O.arch(doc, ax + m * 0.012, inset * 1.3 + m * 0.012, aw - m * 0.024, H - inset * 2.6 - m * 0.024,
               stroke=line_c, sw=sw * 0.8)
        area = {"top": inset * 1.3 + aw * 0.28, "bottom": H - inset * 2.0, "left": ax + aw * 0.1, "right": ax + aw * 0.9}
        if ornament >= 1:
            O.corner_spray(doc, ax + aw * 0.06, H - inset * 1.35, m * 0.2, -70, color=line_c,
                           accent=palette["accent2"], style="duo" if ornament >= 2 else "line", sw=sw, seed=seed)
            O.corner_spray(doc, ax + aw * 0.94, H - inset * 1.35, m * 0.2, -110, color=line_c,
                           accent=palette["accent2"], style="duo" if ornament >= 2 else "line", sw=sw, seed=seed + 5,
                           mirror=True)
    elif style == "classic":
        O.double_frame(doc, inset * 0.7, m * 0.012, color=line_c, sw=sw)
        area = {"top": inset * 1.5, "bottom": H - inset * 1.5, "left": inset * 1.4, "right": W - inset * 1.4}
        if ornament >= 1:
            for (x, y, ang, mir) in ((inset * 0.7, inset * 0.7, 45, False), (W - inset * 0.7, H - inset * 0.7, -135, False)):
                O.corner_spray(doc, x + (m * 0.02 if ang == 45 else -m * 0.02), y + (m * 0.02 if ang == 45 else -m * 0.02),
                               m * 0.16, ang, color=line_c, accent=palette["accent2"], style="line", sw=sw * 0.9,
                               seed=seed + (0 if ang == 45 else 7))
    elif style == "botanical":
        if ornament >= 1:
            st = "duo" if ornament >= 2 else "line"
            O.corner_spray(doc, -m * 0.01, -m * 0.01, m * spray, 52, color=line_c, accent=palette["accent2"], style=st,
                           sw=sw, seed=seed)
            O.corner_spray(doc, W + m * 0.01, H + m * 0.01, m * spray, -128, color=line_c, accent=palette["accent2"],
                           style=st, sw=sw, seed=seed + 3)
        clear = max(inset * 2.0, m * spray * 0.78) if ornament >= 1 else inset * 2.0
        area = {"top": clear, "bottom": H - clear, "left": inset * 1.6, "right": W - inset * 1.6}
    else:  # minimal
        doc.rect(inset * 0.6, inset * 0.6, W - inset * 1.2, H - inset * 1.2, stroke=mix(line_c, palette["bg"], 0.4),
                 sw=sw * 0.6)
        area = {"top": inset * 1.6, "bottom": H - inset * 1.6, "left": inset * 1.5, "right": W - inset * 1.5}
    return area
