"""Listing images: styled scene mockups + honest 'what's included' / size / how-to-edit images.

Scenes are drawn with HTML/CSS/SVG (no third-party photos), sized 2400x1800 (landscape,
Etsy recommends >=2000px) and compressed under 1 MB. Every image states that the product is
a digital download, so buyers aren't misled into expecting a physical item.
"""
from __future__ import annotations

import base64
import html as H
from pathlib import Path

from . import fonts as F
from .styles import darken, lighten, mix

W, HT = 2400, 1800
MAX_BYTES = 1_000_000


def _uri(path: Path) -> str:
    from PIL import Image
    import io
    im = Image.open(path).convert("RGB")
    im.thumbnail((1400, 1400))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _base(body: str, bg: str, extra_css: str = "") -> str:
    css = F.font_face_css({("Montserrat", 500, False), ("Montserrat", 600, False), ("Cormorant Garamond", 500, False),
                           ("Cormorant Garamond", 500, True)})
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{css}
html,body{{margin:0;width:{W}px;height:{HT}px;overflow:hidden}}
body{{background:{bg};font-family:Montserrat;position:relative}}
.ribbon{{position:absolute;left:0;right:0;bottom:0;height:120px;background:rgba(255,255,255,.88);display:flex;
 align-items:center;justify-content:center;gap:40px;font:600 30px Montserrat;letter-spacing:.22em;color:#2b2b2b;text-transform:uppercase}}
.ribbon i{{width:10px;height:10px;border-radius:50%;background:#2b2b2b;display:inline-block}}
.shadow{{box-shadow:0 30px 60px rgba(0,0,0,.18),0 8px 18px rgba(0,0,0,.12)}}
{extra_css}</style></head><body>{body}</body></html>"""


def _ribbon(items: list[str]) -> str:
    return '<div class="ribbon">' + "<i></i>".join(f"<span>{H.escape(x)}</span>" for x in items) + "</div>"


def _branch_svg(color: str, w=360, h=760) -> str:
    """Decorative vase branches drawn with the engine's own botanical generator (original artwork)."""
    from . import ornaments as O
    from .svg import Doc
    d = Doc(width=360, height=760, unit="px", bg="none")
    for i, (ang, ln, curl) in enumerate(((-92, 700, 0.08), (-70, 560, -0.12), (-112, 520, 0.14))):
        O.sprig(d, 180, 760, ln, ang, color=darken(color, .25), accent=color, leaves=9, style="fill", sw=4,
                seed=11 + i, curl=curl, leaf_scale=0.8)
    return f'<svg width="{w}" height="{h}" viewBox="0 0 360 760">{"".join(d.elements)}</svg>'


def wall_scene(arts: list[Path], palette: dict, label: str) -> str:
    wall = mix(palette["bg"], "#e9e4dc", 0.5)
    frame = "#2b2420"
    n = len(arts)
    fw = {1: 640, 2: 600}.get(n, 560)
    fh = int(fw * 1.5)
    gap = 70 if n > 1 else 0
    total = n * fw + (n - 1) * gap
    left = (W - total) // 2 - (120 if n <= 2 else 0)
    top = 110
    frames = ""
    for i, a in enumerate(arts):
        frames += (f'<div class="shadow" style="position:absolute;left:{left + i * (fw + gap)}px;top:{top}px;width:{fw}px;'
                   f'height:{fh}px;background:{frame};padding:16px;box-sizing:border-box"><div style="background:#fbfaf7;'
                   f'width:100%;height:100%;padding:36px;box-sizing:border-box"><img src="{_uri(a)}" style="width:100%;'
                   f'height:100%;object-fit:cover;display:block"></div></div>')
    ctop = top + fh + 100
    decor_x = left + total + 90
    console = (f'<div style="position:absolute;left:260px;right:260px;top:{ctop}px;height:56px;background:#b89a7a;'
               f'box-shadow:0 20px 40px rgba(0,0,0,.18)"></div><div style="position:absolute;left:300px;right:300px;'
               f'top:{ctop + 56}px;height:{HT - ctop}px;background:linear-gradient(#a98a6b,#9c7e60)"></div>'
               f'<div style="position:absolute;left:0;right:0;top:{min(HT - 200, ctop + 330)}px;bottom:0;background:linear-gradient(#cdbfae,#bfae9a)"></div>')
    if decor_x + 300 < W - 260:
        console += (f'<div style="position:absolute;left:{decor_x - 60}px;top:{ctop - 700}px">'
                    f'{_branch_svg(palette["art"][0] if palette.get("art") else "#7d9471", 300, 640)}</div>'
                    f'<div style="position:absolute;left:{decor_x}px;top:{ctop - 170}px;width:180px;height:172px;'
                    f'border-radius:40% 40% 46% 46%;background:{lighten(palette["accent2"], .2)}"></div>')
    light = ('<div style="position:absolute;inset:0;background:radial-gradient(ellipse at 30% 10%,rgba(255,255,255,.55),'
             'rgba(255,255,255,0) 60%),linear-gradient(90deg,rgba(0,0,0,.05),rgba(0,0,0,0) 30%,rgba(0,0,0,.06))"></div>')
    return _base(light + console + frames + _ribbon(["Digital download", label, "Print at home or a print shop"]), wall)


def flatlay_scene(cards: list[tuple[Path, float]], palette: dict, label: str) -> str:
    """cards: (image, aspect h/w)."""
    bg = mix(palette["bg"], "#e8e1d6", 0.6)
    tex = ('<div style="position:absolute;inset:0;opacity:.35;background-image:repeating-linear-gradient(0deg,rgba(0,0,0,.035) 0 2px,'
           'transparent 2px 6px),repeating-linear-gradient(90deg,rgba(0,0,0,.03) 0 2px,transparent 2px 7px)"></div>')
    pos = [(620, 160, 760, -3), (1420, 300, 460, 4), (180, 520, 380, -8), (1850, 1080, 330, 7)]
    out = ""
    for (img, aspect), (x, y, w, rot) in zip(cards, pos):
        h = int(w * aspect)
        out += (f'<img class="shadow" src="{_uri(img)}" style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
                f'transform:rotate({rot}deg);object-fit:cover">')
    env = (f'<div class="shadow" style="position:absolute;left:1340px;top:1180px;width:520px;height:370px;background:{lighten(palette["accent"], .55)};'
           f'transform:rotate(-6deg)"><svg width="520" height="370"><path d="M0,0 L260,200 L520,0" fill="none" '
           f'stroke="rgba(0,0,0,.12)" stroke-width="3"/></svg></div>')
    sprig = f'<div style="position:absolute;left:60px;top:40px;transform:rotate(-30deg)">{_branch_svg(palette["accent"], 300, 640)}</div>'
    return _base(tex + sprig + env + out + _ribbon(["Digital download", label, "Edit · Print · Celebrate"]), bg)


def devices_scene(post: Path, story: Path, flyer: Path, palette: dict, label: str) -> str:
    bg = mix(palette["bg"], palette["accent2"], 0.35)
    phone = lambda img, x, y, rot: (f'<div class="shadow" style="position:absolute;left:{x}px;top:{y}px;width:470px;height:960px;'
                                    f'border-radius:70px;background:#1d1d1f;padding:22px;transform:rotate({rot}deg)">'
                                    f'<img src="{_uri(img)}" style="width:100%;height:100%;object-fit:cover;border-radius:50px"></div>')
    fl = (f'<img class="shadow" src="{_uri(flyer)}" style="position:absolute;left:220px;top:200px;width:900px;height:1165px;'
          f'transform:rotate(-4deg)">')
    sq = (f'<div class="shadow" style="position:absolute;left:1180px;top:300px;width:620px;background:#fff;padding:22px;'
          f'border-radius:24px"><img src="{_uri(post)}" style="width:100%;display:block;border-radius:6px"></div>')
    return _base(fl + sq + phone(story, 1790, 230, 5) + _ribbon(["Digital templates", label, "Print + social ready"]), bg)


def pages_scene(pages: list[Path], palette: dict, label: str) -> str:
    bg = mix(palette["bg"], palette["accent2"], 0.25)
    out = ""
    for i, pth in enumerate(pages[:5]):
        x, rot = 260 + i * 380, -10 + i * 5
        out += (f'<img class="shadow" src="{_uri(pth)}" style="position:absolute;left:{x}px;top:{220 + abs(2 - i) * 40}px;'
                f'width:780px;height:1010px;transform:rotate({rot}deg);background:#fff">')
    return _base(out + _ribbon(["Instant download", label, "US Letter + A4"]), bg)


def included_sheet(items: list[tuple[Path, str]], palette: dict, title: str, footer: list[str]) -> str:
    cells = ""
    cols = 4 if len(items) > 6 else 3
    for img, cap in items[:8]:
        cells += (f'<div style="display:flex;flex-direction:column;align-items:center;gap:22px">'
                  f'<div style="height:520px;display:flex;align-items:center"><img class="shadow" src="{_uri(img)}" '
                  f'style="max-height:520px;max-width:{1900 // cols}px;background:#fff"></div>'
                  f'<div style="font:600 30px Montserrat;letter-spacing:.12em;text-transform:uppercase;color:{palette["ink"]};'
                  f'text-align:center">{H.escape(cap)}</div></div>')
    foot = "".join(f'<li>{H.escape(f)}</li>' for f in footer)
    body = (f'<div style="position:absolute;top:70px;left:0;right:0;text-align:center;font:500 italic 96px \'Cormorant Garamond\';'
            f'color:{palette["ink"]}">{H.escape(title)}</div>'
            f'<div style="position:absolute;top:250px;left:120px;right:120px;display:grid;grid-template-columns:repeat({cols},1fr);'
            f'gap:50px 40px">{cells}</div>'
            f'<ul style="position:absolute;bottom:60px;left:0;right:0;margin:0;padding:0;list-style:none;display:flex;'
            f'justify-content:center;gap:60px;font:500 30px Montserrat;color:{palette["ink"]}">{foot}</ul>')
    return _base(body, mix(palette["bg"], "#ffffff", 0.3))


def info_sheet(title: str, rows: list[tuple[str, str]], palette: dict, subtitle: str = "") -> str:
    lis = "".join(f'<div style="display:flex;justify-content:space-between;gap:40px;padding:26px 0;border-bottom:2px solid '
                  f'{mix(palette["accent"], "#ffffff", .6)}"><span style="font:600 36px Montserrat;letter-spacing:.08em">'
                  f'{H.escape(a)}</span><span style="font:500 italic 46px \'Cormorant Garamond\'">{H.escape(b)}</span></div>'
                  for a, b in rows)
    body = (f'<div style="position:absolute;inset:120px 260px;color:{palette["ink"]}"><div style="text-align:center;'
            f'font:500 italic 110px \'Cormorant Garamond\'">{H.escape(title)}</div><div style="text-align:center;font:500 30px '
            f'Montserrat;letter-spacing:.25em;text-transform:uppercase;margin:10px 0 60px;color:{palette["accent"]}">'
            f'{H.escape(subtitle)}</div>{lis}</div>')
    return _base(body, mix(palette["bg"], "#ffffff", 0.4))
