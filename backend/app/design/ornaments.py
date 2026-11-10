"""Original vector ornaments: botanical sprigs, wreaths, frames, dividers.

All artwork is generated mathematically from scratch (no third-party clip art)."""
from __future__ import annotations

import math
import random

from .svg import Doc, fmt


def _pt(x, y):
    return f"{fmt(round(x, 2))},{fmt(round(y, 2))}"


def leaf_path(x, y, length, width, angle) -> str:
    """Almond-shaped leaf with its base at (x,y) pointing along `angle` (radians)."""
    ca, sa = math.cos(angle), math.sin(angle)
    tip = (x + ca * length, y + sa * length)
    nx, ny = -sa, ca
    c1 = (x + ca * length * 0.45 + nx * width, y + sa * length * 0.45 + ny * width)
    c2 = (x + ca * length * 0.45 - nx * width, y + sa * length * 0.45 - ny * width)
    return f"M{_pt(x, y)} Q{_pt(*c1)} {_pt(*tip)} Q{_pt(*c2)} {_pt(x, y)} Z"


def sprig(doc: Doc, x, y, length, angle_deg, *, color, accent=None, leaves=7, style="line", sw=1.0, seed=0,
          curl=0.18, leaf_scale=1.0, berries=False):
    """A curved stem with alternating leaves. style: 'line' (fine-line) | 'fill' | 'duo'."""
    rnd = random.Random(seed)
    a = math.radians(angle_deg)
    end = (x + math.cos(a) * length, y + math.sin(a) * length)
    # perpendicular control point for a gentle curve
    nx, ny = -math.sin(a), math.cos(a)
    ctrl = (x + math.cos(a) * length * 0.5 + nx * length * curl, y + math.sin(a) * length * 0.5 + ny * length * curl)
    doc.path(f"M{_pt(x, y)} Q{_pt(*ctrl)} {_pt(*end)}", stroke=color, sw=sw)

    def bez(t):
        bx = (1 - t) ** 2 * x + 2 * (1 - t) * t * ctrl[0] + t ** 2 * end[0]
        by = (1 - t) ** 2 * y + 2 * (1 - t) * t * ctrl[1] + t ** 2 * end[1]
        dx = 2 * (1 - t) * (ctrl[0] - x) + 2 * t * (end[0] - ctrl[0])
        dy = 2 * (1 - t) * (ctrl[1] - y) + 2 * t * (end[1] - ctrl[1])
        return bx, by, math.atan2(dy, dx)

    for i in range(leaves):
        t = 0.18 + 0.78 * i / max(1, leaves - 1)
        bx, by, tang = bez(t)
        side = 1 if i % 2 == 0 else -1
        size = length * 0.26 * leaf_scale * (1.0 - 0.45 * t) * (0.9 + rnd.random() * 0.2)
        ang = tang + side * math.radians(38 + rnd.uniform(-6, 6))
        d = leaf_path(bx, by, size, size * 0.32, ang)
        if style == "line":
            doc.path(d, fill="none", stroke=color, sw=sw)
            tipx, tipy = bx + math.cos(ang) * size * 0.8, by + math.sin(ang) * size * 0.8
            doc.path(f"M{_pt(bx, by)} L{_pt(tipx, tipy)}", stroke=color, sw=sw * 0.6, opacity=0.7)
        elif style == "duo":
            doc.path(d, fill=(accent or color), opacity=0.55)
            doc.path(d, fill="none", stroke=color, sw=sw * 0.8)
        else:
            doc.path(d, fill=color, opacity=0.9 if i % 3 else 0.75)
    # terminal leaf
    bx, by, tang = bez(1.0)
    size = length * 0.16 * leaf_scale
    d = leaf_path(bx, by, size, size * 0.34, tang)
    doc.path(d, fill=("none" if style == "line" else (accent or color) if style == "duo" else color),
             stroke=(color if style in ("line", "duo") else None), sw=sw)
    if berries:
        for i in range(3):
            t = 0.3 + 0.2 * i
            bx, by, tang = bez(t)
            r = length * 0.018
            doc.circle(bx + math.cos(tang + 1.6) * length * 0.07, by + math.sin(tang + 1.6) * length * 0.07, r,
                       fill=accent or color)


def corner_spray(doc: Doc, x, y, scale, base_angle, *, color, accent=None, style="line", sw=1.0, seed=1, mirror=False):
    """A spray of 3-4 sprigs fanning from one point (used in corners / under names)."""
    rnd = random.Random(seed)
    angles = [-28, -2, 22, 46] if not mirror else [28, 2, -22, -46]
    lengths = [0.78, 1.0, 0.82, 0.6]
    for i, (da, lf) in enumerate(zip(angles, lengths)):
        sprig(doc, x, y, scale * lf, base_angle + da + rnd.uniform(-4, 4), color=color, accent=accent,
              leaves=6 + (i % 2), style=style, sw=sw, seed=seed * 10 + i, curl=0.15 if i % 2 else -0.15,
              berries=(style == "duo" and i == 2))


def wreath(doc: Doc, cx, cy, r, *, color, accent=None, style="line", sw=1.0, seed=3, gap_deg=70, n=5, length=0.42):
    """Two half-wreaths of sprigs leaving an opening at the top."""
    start = -90 + gap_deg / 2
    span = (360 - gap_deg) / 2
    for side in (1, -1):
        for i in range(n):
            t = i / (n - 1)
            ang = math.radians(start + span * t) if side == 1 else math.radians(180 - (start + span * t))
            px, py = cx + r * math.cos(ang), cy + r * math.sin(ang)
            tangent = math.degrees(ang) + (90 if side == 1 else -90)
            sprig(doc, px, py, r * length, tangent, color=color, accent=accent, leaves=5, style=style, sw=sw,
                  seed=seed + i + (10 if side == 1 else 0), curl=0.12 * side, leaf_scale=0.9,
                  berries=(accent is not None and i % 2 == 0))


def arch_path(x, y, w, h) -> str:
    r = w / 2
    return (f"M{_pt(x, y + h)} L{_pt(x, y + r)} A{fmt(r)},{fmt(r)} 0 0 1 {_pt(x + w, y + r)} "
            f"L{_pt(x + w, y + h)} Z")


def arch(doc: Doc, x, y, w, h, *, fill="none", stroke=None, sw=1.0, opacity=None):
    doc.path(arch_path(x, y, w, h), fill=fill, stroke=stroke, sw=sw, opacity=opacity)


def double_frame(doc: Doc, inset, gap, *, color, sw=0.8):
    W, H = doc.width, doc.height
    doc.rect(inset, inset, W - 2 * inset, H - 2 * inset, stroke=color, sw=sw)
    doc.rect(inset + gap, inset + gap, W - 2 * (inset + gap), H - 2 * (inset + gap), stroke=color, sw=sw * 0.6)


def divider(doc: Doc, cx, y, width, *, color, sw=0.75, motif="diamond"):
    half = width / 2
    s = width * 0.035
    doc.line(cx - half, y, cx - s * 2.2, y, color, sw)
    doc.line(cx + s * 2.2, y, cx + half, y, color, sw)
    if motif == "diamond":
        doc.path(f"M{_pt(cx - s, y)} L{_pt(cx, y - s)} L{_pt(cx + s, y)} L{_pt(cx, y + s)} Z", fill=color)
    elif motif == "dot":
        doc.circle(cx, y, s * 0.6, fill=color)
    elif motif == "leaf":
        doc.path(leaf_path(cx - s * 1.6, y, s * 3.2, s * 0.9, 0), fill=color)


def monogram_ring(doc: Doc, cx, cy, r, *, color, sw=0.8):
    doc.circle(cx, cy, r, stroke=color, sw=sw)
    doc.circle(cx, cy, r * 0.9, stroke=color, sw=sw * 0.5, opacity=0.7)
