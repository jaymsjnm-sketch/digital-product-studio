"""Original generative artwork for printable wall art.

Every composition is generated from a seed and a palette, entirely from scratch:
arches, sun & hills, cut-paper organic shapes, botanical line work, whimsical florals,
holiday motifs. A fine paper-grain texture gives a printed, tactile finish.
Compositions adapt to any aspect ratio (elements are anchored relative to width/height).
"""
from __future__ import annotations

import base64
import functools
import io
import math
import random

from . import ornaments as O
from .styles import darken, lighten, mix
from .svg import Doc, fmt


def _p(x, y):
    return f"{fmt(round(x, 2))},{fmt(round(y, 2))}"


def smooth_closed(points: list[tuple[float, float]], tension: float = 0.5) -> str:
    """Closed Catmull-Rom spline through points -> cubic Bezier path."""
    n = len(points)
    d = f"M{_p(*points[0])}"
    for i in range(n):
        p0, p1, p2, p3 = points[(i - 1) % n], points[i], points[(i + 1) % n], points[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) * tension / 3, p1[1] + (p2[1] - p0[1]) * tension / 3)
        c2 = (p2[0] - (p3[0] - p1[0]) * tension / 3, p2[1] - (p3[1] - p1[1]) * tension / 3)
        d += f" C{_p(*c1)} {_p(*c2)} {_p(*p2)}"
    return d + " Z"


def smooth_open(points: list[tuple[float, float]], tension: float = 0.5) -> str:
    n = len(points)
    d = f"M{_p(*points[0])}"
    for i in range(n - 1):
        p0, p1, p2 = points[max(0, i - 1)], points[i], points[i + 1]
        p3 = points[min(n - 1, i + 2)]
        c1 = (p1[0] + (p2[0] - p0[0]) * tension / 3, p1[1] + (p2[1] - p0[1]) * tension / 3)
        c2 = (p2[0] - (p3[0] - p1[0]) * tension / 3, p2[1] - (p3[1] - p1[1]) * tension / 3)
        d += f" C{_p(*c1)} {_p(*c2)} {_p(*p2)}"
    return d


def blob(cx, cy, r, rnd: random.Random, points=7, wobble=0.22) -> str:
    pts = []
    phase = rnd.random() * math.tau
    for i in range(points):
        a = phase + math.tau * i / points
        rr = r * (1 + rnd.uniform(-wobble, wobble))
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return smooth_closed(pts)


@functools.lru_cache(maxsize=4)
def grain_tile(px: int = 512, strength: int = 70, seed: int = 11) -> str:
    """Seamless-enough monochrome noise tile as a PNG data URI (alpha noise)."""
    from PIL import Image
    rnd = random.Random(seed)
    img = Image.new("LA", (px, px))
    data = []
    for _ in range(px * px):
        v = rnd.randint(0, 255)
        data.append((0 if v < 128 else 255, int(abs(v - 128) / 128 * strength)))
    img.putdata(data)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def add_grain(doc: Doc, opacity: float = 0.35):
    tile = doc.width / 6 if doc.unit == "pt" else 256
    pid = doc.nid("grain")
    doc.add_def(f'<pattern id="{pid}" patternUnits="userSpaceOnUse" width="{fmt(tile)}" height="{fmt(tile)}">'
                f'<image href="{grain_tile()}" x="0" y="0" width="{fmt(tile)}" height="{fmt(tile)}" '
                f'preserveAspectRatio="none" style="image-rendering:pixelated"/></pattern>')
    doc.rect(0, 0, doc.width, doc.height, fill=f"url(#{pid})", opacity=opacity, extra='data-texture="grain"')


# ----------------------------------------------------------------------------- compositions
def comp_arches(doc: Doc, pal: dict, rnd: random.Random):
    W, H = doc.width, doc.height
    art = pal["art"]
    cx, base = W / 2, H * 0.7
    R = W * 0.4
    bands = 5
    bw = R / (bands + 0.8)
    colors = [art[i % len(art)] for i in range(bands)]
    rnd.shuffle(colors)
    for i in range(bands):
        r = R - i * bw - bw / 2
        doc.path(f"M{_p(cx - r, base)} A{fmt(r)},{fmt(r)} 0 0 1 {_p(cx + r, base)}", stroke=colors[i], sw=bw * 0.92,
                 extra='stroke-linecap="butt"')
    # sun
    sx = cx + (W * 0.24 if rnd.random() > 0.5 else -W * 0.24)
    doc.circle(sx, base - R * 1.32, W * 0.07, fill=art[1] if colors[0] != art[1] else art[0])
    # ground and dots
    doc.rect(0, base, W, H - base, fill=mix(pal["bg"], art[3 % len(art)], 0.35))
    for _ in range(18):
        doc.circle(rnd.uniform(W * 0.08, W * 0.92), rnd.uniform(base + (H - base) * 0.25, H * 0.95),
                   W * rnd.uniform(0.004, 0.008), fill=darken(art[3 % len(art)], 0.25), opacity=0.6)


def comp_sun_hills(doc: Doc, pal: dict, rnd: random.Random):
    W, H = doc.width, doc.height
    art = pal["art"]
    doc.rect(0, 0, W, H, fill=mix(pal["bg"], art[3 % len(art)], 0.25))
    sun_r = W * 0.17
    sx, sy = W * rnd.uniform(0.38, 0.62), H * 0.42
    doc.circle(sx, sy, sun_r, fill=art[1])
    doc.circle(sx, sy, sun_r * 1.28, stroke=art[1], sw=W * 0.004, opacity=0.6)
    layers = [art[0], art[2 % len(art)], darken(art[0], 0.25), art[4 % len(art)]]
    for li, col in enumerate(layers):
        y0 = H * (0.52 + li * 0.085)
        amp = H * (0.07 - li * 0.008)
        pts = []
        steps = 6
        ph = rnd.random() * math.tau
        for k in range(steps + 1):
            x = -W * 0.05 + (W * 1.1) * k / steps
            pts.append((x, y0 + amp * math.sin(ph + k * rnd.uniform(0.9, 1.4))))
        d = smooth_open(pts) + f" L{_p(W * 1.05, H + 2)} L{_p(-W * 0.05, H + 2)} Z"
        doc.path(d, fill=col)
    # birds
    for i in range(3):
        bx, by, s = W * (0.22 + 0.08 * i), H * (0.24 + 0.03 * (i % 2)), W * 0.02
        doc.path(f"M{_p(bx - s, by)} Q{_p(bx - s / 2, by - s * 0.6)} {_p(bx, by)} Q{_p(bx + s / 2, by - s * 0.6)} {_p(bx + s, by)}",
                 stroke=pal["ink"], sw=W * 0.0025)


def comp_organic(doc: Doc, pal: dict, rnd: random.Random):
    """Cut-paper still life: balanced overlapping organic forms with a fine-line arch and sprig."""
    W, H = doc.width, doc.height
    art = pal["art"]
    cx, cy = W / 2, H * 0.52
    O.arch(doc, W * 0.2, cy - W * 0.5, W * 0.6, W * 0.92, stroke=pal["ink"], sw=W * 0.0025, opacity=0.55)
    cols = art[:]
    rnd.shuffle(cols)
    shapes = [(cx - W * 0.04, cy + W * 0.13, W * 0.18, 7), (cx + W * 0.12, cy - W * 0.03, W * 0.14, 6),
              (cx - W * 0.08, cy - W * 0.16, W * 0.1, 6)]
    for i, (x, y, r, n) in enumerate(shapes):
        doc.path(blob(x, y, r, rnd, points=n, wobble=0.14), fill=cols[i % len(cols)], opacity=0.95)
    doc.circle(cx + W * 0.16, cy - W * 0.25, W * 0.045, fill=cols[3 % len(cols)])
    O.sprig(doc, cx + W * 0.06, cy + W * 0.36, W * 0.34, -70, color=pal["ink"], leaves=7, style="line",
            sw=W * 0.0025, seed=rnd.randint(0, 99), curl=-0.15)


def comp_botanical(doc: Doc, pal: dict, rnd: random.Random):
    W, H = doc.width, doc.height
    art = pal["art"]
    aw, ah = W * 0.56, H * 0.62
    O.arch(doc, (W - aw) / 2, H * 0.18, aw, ah, fill=mix(pal["bg"], art[1], 0.55))
    base_x, base_y = W / 2, H * 0.8
    for i, (ang, ln) in enumerate(((-100, 0.5), (-78, 0.42), (-122, 0.36), (-60, 0.3), (-140, 0.28))):
        O.sprig(doc, base_x, base_y, H * ln, ang, color=pal["ink"], accent=art[0], leaves=7, style="duo",
                sw=W * 0.0022, seed=rnd.randint(0, 999), curl=0.12 if i % 2 else -0.12)
    doc.rect(W * 0.38, base_y, W * 0.24, H * 0.06, fill=art[2 % len(art)], rx=W * 0.01)


def _daisy(doc: Doc, x, y, r, petal, center, n=9, rot=0.0):
    for i in range(n):
        a = rot + math.tau * i / n
        px, py = x + math.cos(a) * r * 0.55, y + math.sin(a) * r * 0.55
        doc.add(f'<ellipse cx="{fmt(round(px, 2))}" cy="{fmt(round(py, 2))}" rx="{fmt(round(r * 0.5, 2))}" '
                f'ry="{fmt(round(r * 0.2, 2))}" transform="rotate({fmt(round(math.degrees(a), 1))} {fmt(round(px, 2))} '
                f'{fmt(round(py, 2))})" fill="{petal}"/>')
    doc.circle(x, y, r * 0.24, fill=center)


def _star(cx, cy, r, points=5, inner=0.5, rot=-90.0) -> str:
    pts = []
    for i in range(points * 2):
        rr = r if i % 2 == 0 else r * inner
        a = math.radians(rot + 180 * i / points)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return smooth_closed(pts, tension=0.12)


def comp_whimsical(doc: Doc, pal: dict, rnd: random.Random):
    W, H = doc.width, doc.height
    art = pal["art"]
    # wavy band
    band_y = H * 0.66
    pts = [(-W * 0.05 + i * W * 0.1, band_y + math.sin(i * 1.1) * H * 0.02) for i in range(13)]
    doc.path(smooth_open(pts) + f" L{_p(W * 1.1, H + 2)} L{_p(-W * 0.1, H + 2)} Z", fill=art[0])
    pts2 = [(p[0], p[1] + H * 0.06) for p in pts]
    doc.path(smooth_open(pts2) + f" L{_p(W * 1.1, H + 2)} L{_p(-W * 0.1, H + 2)} Z", fill=art[1])
    # flowers
    spots = [(W * 0.3, H * 0.4, W * 0.16), (W * 0.68, H * 0.3, W * 0.12), (W * 0.62, H * 0.56, W * 0.09),
             (W * 0.22, H * 0.68, W * 0.08), (W * 0.8, H * 0.78, W * 0.1)]
    for i, (x, y, r) in enumerate(spots):
        petal = art[(i + 2) % len(art)]
        center = art[(i + 3) % len(art)]
        if petal == center:
            center = pal["ink"]
        _daisy(doc, x, y, r, petal, center, n=8 + i % 3, rot=rnd.random())
    for _ in range(7):
        doc.path(_star(rnd.uniform(W * 0.1, W * 0.9), rnd.uniform(H * 0.1, H * 0.25), W * rnd.uniform(0.015, 0.03)),
                 fill=art[rnd.randrange(len(art))])
    for _ in range(14):
        doc.circle(rnd.uniform(0, W), rnd.uniform(H * 0.75, H), W * 0.006, fill=pal["bg"], opacity=0.8)


def comp_holiday_trees(doc: Doc, pal: dict, rnd: random.Random):
    W, H = doc.width, doc.height
    art = pal["art"]
    ground = H * 0.78
    doc.path(smooth_open([(-W * 0.05, ground), (W * 0.3, ground - H * 0.02), (W * 0.7, ground + H * 0.01),
                          (W * 1.05, ground - H * 0.015)]) + f" L{_p(W * 1.05, H + 2)} L{_p(-W * 0.05, H + 2)} Z",
             fill=lighten(art[4 % len(art)], 0.5))
    trees = [(W * 0.3, W * 0.2, H * 0.42, art[1]), (W * 0.62, W * 0.24, H * 0.5, darken(art[1], 0.15)),
             (W * 0.82, W * 0.13, H * 0.28, art[4 % len(art)])]
    for x, w, h, col in trees:
        top = ground - h
        tiers = 3
        for t in range(tiers):
            ty = top + h * t / tiers * 0.85
            tw = w * (0.45 + 0.55 * (t + 1) / tiers)
            th = h / tiers * 1.25
            d = (f"M{_p(x, ty)} Q{_p(x + tw * 0.1, ty + th * 0.4)} {_p(x + tw / 2, ty + th)} "
                 f"Q{_p(x, ty + th * 1.08)} {_p(x - tw / 2, ty + th)} Q{_p(x - tw * 0.1, ty + th * 0.4)} {_p(x, ty)} Z")
            doc.path(d, fill=col)
        doc.rect(x - w * 0.06, ground - h * 0.06, w * 0.12, h * 0.1, fill=darken(art[0], 0.4))
        doc.path(_star(x, top - w * 0.02, w * 0.09), fill=art[2 % len(art)])
        for _ in range(5):
            bx = x + rnd.uniform(-w * 0.3, w * 0.3)
            by = top + rnd.uniform(h * 0.35, h * 0.9)
            doc.circle(bx, by, w * 0.035, fill=art[rnd.choice([0, 2, 3])])
    for _ in range(40):
        doc.circle(rnd.uniform(0, W), rnd.uniform(0, ground), W * rnd.uniform(0.003, 0.007), fill="#ffffff", opacity=0.9)


def comp_holiday_baubles(doc: Doc, pal: dict, rnd: random.Random):
    W, H = doc.width, doc.height
    art = pal["art"]
    xs = [W * 0.25, W * 0.5, W * 0.75]
    for i, x in enumerate(xs):
        length = H * (0.28 + 0.12 * ((i + 1) % 3))
        r = W * (0.11 if i == 1 else 0.085)
        doc.line(x, 0, x, length, pal["ink"], W * 0.002)
        doc.rect(x - r * 0.25, length - r * 0.05, r * 0.5, r * 0.28, fill=art[2 % len(art)], rx=r * 0.05)
        cy = length + r * 1.15
        col = art[i % 2 == 0 and 0 or 1]
        doc.circle(x, cy, r, fill=col)
        for k in range(3):
            yy = cy - r * 0.45 + k * r * 0.45
            half = math.sqrt(max(0, r * r - (yy - cy) ** 2))
            doc.path(f"M{_p(x - half, yy)} Q{_p(x, yy + r * 0.12)} {_p(x + half, yy)}", stroke=lighten(col, 0.55),
                     sw=r * 0.06)
        doc.circle(x - r * 0.35, cy - r * 0.4, r * 0.12, fill="#ffffff", opacity=0.55)
    for _ in range(9):
        doc.path(_star(rnd.uniform(W * 0.08, W * 0.92), rnd.uniform(H * 0.72, H * 0.92), W * 0.02), fill=art[2 % len(art)])


def comp_holiday_type(doc: Doc, pal: dict, rnd: random.Random, fonts: dict | None = None):
    W, H = doc.width, doc.height
    art = pal["art"]
    fonts = fonts or {"display": "Fraunces", "script": "Allura"}
    O.wreath(doc, W / 2, H / 2, W * 0.34, color=art[1], accent=art[4 % len(art)], style="fill", sw=W * 0.003,
             seed=rnd.randint(0, 99), gap_deg=50, n=8, length=0.55)
    doc.text(W / 2, H / 2 - W * 0.02, "Merry", family=fonts["display"], size=W * 0.15, weight=600, fill=art[0],
             max_width=W * 0.5, role="art-text")
    doc.text(W / 2, H / 2 + W * 0.13, "& bright", family=fonts["script"], size=W * 0.12, fill=pal["ink"],
             max_width=W * 0.5, role="art-text")


COMPOSITIONS = {"arches": comp_arches, "sun_hills": comp_sun_hills, "organic": comp_organic,
                "botanical": comp_botanical, "whimsical": comp_whimsical, "holiday_trees": comp_holiday_trees,
                "holiday_baubles": comp_holiday_baubles, "holiday_type": comp_holiday_type}

THEME_SETS = {"boho": ["arches", "sun_hills", "botanical", "organic"],
              "whimsical": ["whimsical", "organic", "arches", "sun_hills"],
              "holiday": ["holiday_trees", "holiday_type", "holiday_baubles"],
              "minimal": ["organic", "botanical", "arches"]}
