"""Small-business marketing kit: flyer, price list, promo poster, Instagram post + story, web banner.

Industry content packs supply realistic, editable placeholder copy. Photo areas are clearly
marked placeholders the buyer replaces with their own photos (never stock we don't own)."""
from __future__ import annotations

import random

from .. import art as A
from .. import ornaments as O
from ..common import Stack, para_block, resolve_style, text_block
from ..styles import adjust_for_contrast, darken, mix
from ..svg import Doc

PIECES = {
    "flyer": {"label": "Flyer (8.5x11 in)", "size": (8.5 * 72, 11 * 72), "unit": "pt"},
    "price_list": {"label": "Price list (8.5x11 in)", "size": (8.5 * 72, 11 * 72), "unit": "pt"},
    "poster": {"label": "Promo poster (18x24 in)", "size": (18 * 72, 24 * 72), "unit": "pt"},
    "ig_post": {"label": "Instagram post (1080x1080)", "size": (1080, 1080), "unit": "px"},
    "ig_story": {"label": "Instagram story (1080x1920)", "size": (1080, 1920), "unit": "px"},
    "web_banner": {"label": "Web / Facebook banner (1640x624)", "size": (1640, 624), "unit": "px"},
}

PACKS = {
    "beauty": {
        "brand": "Maison Lash Studio", "tagline": "Lashes, brows & skin by appointment",
        "headline": "Now Booking", "sub": "Effortless lashes for every day",
        "offer": "15% off your first full set", "cta": "Book online today",
        "contact": "@maisonlashstudio  ·  (555) 014-2290", "address": "214 Rosewood Ave, Suite 3",
        "features": ["Certified lash artists", "Premium, lightweight lashes", "Relaxing private studio"],
        "price_title": "Price List",
        "services": [["Lash Extensions", [["Classic full set", "$120"], ["Hybrid full set", "$140"],
                                          ["Volume full set", "$160"], ["Fill (2-3 weeks)", "$65"]]],
                     ["Lift & Tint", [["Lash lift", "$75"], ["Lash lift + tint", "$90"], ["Brow lamination", "$80"]]],
                     ["Brows", [["Brow shaping", "$30"], ["Brow tint", "$20"], ["Shape + tint", "$45"]]]],
        "story_steps": ["Choose your service", "Pick a time that suits you", "Arrive & relax"],
        "art": "organic",
    },
    "real_estate": {
        "brand": "Jordan Ellis Realty", "tagline": "Helping you find home",
        "headline": "Just Listed", "sub": "1482 Maple Grove Lane",
        "offer": "4 bed  ·  3 bath  ·  2,450 sq ft", "cta": "Schedule a private showing",
        "contact": "Jordan Ellis, Realtor  ·  (555) 019-7731", "address": "jordanellisrealty.com",
        "features": ["Open-concept kitchen", "Quiet cul-de-sac location", "Walk to parks & schools"],
        "price_title": "Seller Services",
        "services": [["Listing Package", [["Professional photography", "Included"], ["Virtual tour", "Included"],
                                          ["Open house hosting", "Included"]]],
                     ["Marketing", [["Social media campaign", "Included"], ["Print flyers", "Included"],
                                    ["Email to buyer network", "Included"]]]],
        "story_steps": ["Book a showing", "Tour your future home", "Make it yours"],
        "art": "photo",
    },
    "boutique": {
        "brand": "Juniper & Co.", "tagline": "Curated goods for slow living",
        "headline": "New Arrivals", "sub": "The autumn collection is here",
        "offer": "20% off this weekend only", "cta": "Shop in store & online",
        "contact": "@juniperandco  ·  juniperandco.shop", "address": "88 Market Street",
        "features": ["Small-batch makers", "Thoughtful gift wrapping", "Local pickup available"],
        "price_title": "Gift Guide",
        "services": [["Under $25", [["Hand-poured candle", "$18"], ["Linen tea towel", "$16"], ["Ceramic mug", "$24"]]],
                     ["Under $50", [["Wool throw blanket", "$48"], ["Botanical print set", "$35"],
                                    ["Stoneware vase", "$42"]]]],
        "story_steps": ["Browse the new collection", "Reserve your favourites", "Pick up or ship"],
        "art": "arches",
    },
}


def piece_list(p: dict) -> list[str]:
    return list(p.get("pieces") or PIECES.keys())


def _photo(doc: Doc, x, y, w, h, palette, *, arch=False, label="YOUR PHOTO HERE"):
    """Clearly-marked replaceable photo area."""
    fill = mix(palette["accent2"], palette["bg"], 0.35)
    if arch:
        O.arch(doc, x, y, w, h, fill=fill)
    else:
        doc.rect(x, y, w, h, fill=fill)
    s = min(w, h)
    cx, cy = x + w / 2, y + h / 2
    doc.path(f"M{cx - s * 0.12},{cy + s * 0.06} L{cx - s * 0.03},{cy - s * 0.05} L{cx + s * 0.04},{cy + s * 0.03} "
             f"L{cx + s * 0.08},{cy - s * 0.01} L{cx + s * 0.13},{cy + s * 0.06} Z", fill=palette["bg"], opacity=0.8)
    doc.circle(cx + s * 0.07, cy - s * 0.07, s * 0.025, fill=palette["bg"], opacity=0.8)
    doc.text(cx, cy + s * 0.15, label, family="Montserrat", size=s * 0.035, weight=500, fill=palette["bg"],
             tracking=0.2, max_width=w * 0.8, role="placeholder")


def _art(doc: Doc, kind, x, y, w, h, palette, seed):
    """Decorative original artwork panel (uses the wall-art generator inside a clipped area)."""
    sub = Doc(width=w, height=h, unit=doc.unit, bg=mix(palette["bg"], palette["accent2"], 0.25))
    comp = {"organic": A.comp_organic, "arches": A.comp_arches}.get(kind, A.comp_organic)
    pal = dict(palette)
    pal["bg"] = sub.bg
    comp(sub, pal, random.Random(seed))
    cid = doc.nid("clip")
    doc.add_def(f'<clipPath id="{cid}"><path d="{O.arch_path(x, y, w, h)}"/></clipPath>')
    doc.add(f'<g clip-path="url(#{cid})"><g transform="translate({x:.2f},{y:.2f})">'
            f'<rect width="{w:.2f}" height="{h:.2f}" fill="{sub.bg}"/>' + "".join(sub.elements) + "</g></g>")
    doc.fonts_used |= sub.fonts_used


def _visual(doc, pack, x, y, w, h, palette, seed):
    if pack["art"] == "photo":
        _photo(doc, x, y, w, h, palette, arch=True)
    else:
        _art(doc, pack["art"], x, y, w, h, palette, seed)


def build(piece: str, p: dict, page: int = 1) -> Doc:
    palette, fonts = resolve_style(p)
    pack = {**PACKS.get(p.get("industry", "beauty"), PACKS["beauty"]), **(p.get("content") or {})}
    seed = int(p.get("seed", 7))
    ts, sp = float(p.get("text_scale", 1.0)), float(p.get("spacing", 1.0))
    w, h = PIECES[piece]["size"]
    unit = PIECES[piece]["unit"]
    doc = Doc(width=w, height=h, unit=unit, bg=palette["bg"], title=PIECES[piece]["label"],
              fixes=p.get("_fixes", {}).get(piece, {}), safe_margin=18 if unit == "pt" else 60)
    W, H = doc.width, doc.height
    m = min(W, H)
    ink, acc = palette["ink"], adjust_for_contrast(palette["accent"], palette["bg"], 3.0)
    fd, fb, fc, fs = fonts["display"], fonts["body"], fonts["caps"], fonts["script"]
    wd, wb, wc = fonts["display_weight"], fonts["body_weight"], max(fonts["caps_weight"], 500)
    st = Stack()

    if piece in ("flyer", "poster"):
        pad = m * 0.09
        vis_w, vis_h = W * 0.56, H * 0.37
        _visual(doc, pack, (W - vis_w) / 2, pad, vis_w, vis_h, palette, seed)
        cx, cw = W / 2, W - 2 * pad * 1.2
        text_block(st, doc, cx, pack["brand"], family=fc, size=m * 0.026 * ts, max_width=cw, weight=wc, fill=acc,
                   tracking=0.3, upper=True, field="Brand", gap=m * 0.03 * sp)
        text_block(st, doc, cx, pack["headline"], family=fd, size=m * 0.14 * ts, max_width=cw, weight=wd, fill=ink,
                   field="Headline", role="heading", gap=m * 0.02 * sp)
        text_block(st, doc, cx, pack["sub"], family=fs, size=m * 0.07 * ts, max_width=cw, fill=acc, field="Subheading",
                   asc=0.72, desc=0.32, gap=m * 0.045 * sp)
        feats = "  ·  ".join(pack["features"])
        para_block(st, doc, cx, feats, family=fb, size=m * 0.027 * ts, max_width=cw * 0.9, weight=wb, fill=ink,
                   field="Features", max_lines=2, gap=m * 0.04 * sp)

        def badge(y):
            bw, bh = cw * 0.72, m * 0.085
            txt = palette["bg"] if palette["bg"].lower() != "#ffffff" else "#ffffff"
            doc.rect(cx - bw / 2, y, bw, bh, fill=adjust_for_contrast(palette["accent"], txt, 4.8), rx=bh / 2)
            doc.text(cx, y + bh * 0.62, pack["offer"], family=fc, size=m * 0.03 * ts, weight=wc, fill=txt,
                     tracking=0.12, upper=True, max_width=bw * 0.86, field="Offer")
        st.add(m * 0.085, badge, m * 0.04 * sp)
        text_block(st, doc, cx, pack["cta"], family=fd, size=m * 0.045 * ts, max_width=cw, weight=wd, fill=ink,
                   field="Call to action", gap=m * 0.018 * sp)
        text_block(st, doc, cx, pack["contact"], family=fc, size=m * 0.022 * ts, max_width=cw, weight=wc, fill=ink,
                   tracking=0.15, upper=False, field="Contact", gap=m * 0.008 * sp)
        text_block(st, doc, cx, pack["address"], family=fb, size=m * 0.022 * ts, max_width=cw, weight=wb, fill=ink,
                   field="Address")
        st.render(pad + vis_h + m * 0.05, H - pad * 0.9)

    elif piece == "price_list":
        pad = m * 0.1
        doc.rect(pad * 0.45, pad * 0.45, W - pad * 0.9, H - pad * 0.9, stroke=mix(palette["accent"], palette["bg"], 0.3),
                 sw=1.0)
        cx, cw = W / 2, W - 2 * pad * 1.3
        text_block(st, doc, cx, pack["brand"], family=fc, size=m * 0.026 * ts, max_width=cw, weight=wc, fill=acc,
                   tracking=0.3, upper=True, field="Brand", gap=m * 0.02 * sp)
        text_block(st, doc, cx, pack["price_title"], family=fd, size=m * 0.11 * ts, max_width=cw, weight=wd, fill=ink,
                   field="Title", role="heading", gap=m * 0.015 * sp)
        st.add(m * 0.01, lambda y: O.divider(doc, cx, y, cw * 0.3, color=acc, sw=0.8, motif="diamond"), m * 0.05 * sp)
        size = m * 0.03 * ts
        for gi, (group, items) in enumerate(pack["services"]):
            if gi:
                st.gap(m * 0.045 * sp)
            text_block(st, doc, cx, group, family=fc, size=m * 0.027 * ts, max_width=cw, weight=wc, fill=acc,
                       tracking=0.25, upper=True, field=f"Category {gi + 1}", gap=m * 0.03 * sp)
            for ii, (name, price) in enumerate(items):
                def row(y, name=name, price=price, gi=gi, ii=ii):
                    left, right = cx - cw * 0.42, cx + cw * 0.42
                    base = y + size * 0.78
                    a = doc.text(left, base, name, family=fb, size=size, weight=wb, fill=ink, anchor="start",
                                 max_width=cw * 0.6, field=f"Service {gi + 1}.{ii + 1}",
                                 box=(left, base - size * 1.05, cw * 0.6, size * 1.45))
                    b = doc.text(right, base, price, family=fd, size=size, weight=wd, fill=ink, anchor="end",
                                 max_width=cw * 0.2, field=f"Price {gi + 1}.{ii + 1}",
                                 box=(right - cw * 0.2, base - size * 1.05, cw * 0.2, size * 1.45))
                    x1, x2 = left + a["width"] + size * 0.6, right - b["width"] - size * 0.6
                    if x2 > x1:
                        doc.line(x1, base - size * 0.08, x2, base - size * 0.08, mix(ink, palette["bg"], 0.6), 0.9,
                                 dash=f"0.1 {size * 0.32:.1f}")
                st.add(size * 1.05, row, size * 0.75 * sp)
        st.gap(m * 0.05)
        text_block(st, doc, cx, pack["contact"], family=fb, size=m * 0.022 * ts, max_width=cw, weight=wb, fill=ink,
                   field="Contact")
        st.render(pad, H - pad)

    elif piece == "ig_post":
        doc.rect(0, 0, W, H * 0.5, fill=mix(palette["accent2"], palette["bg"], 0.55))
        _visual(doc, pack, W * 0.56, H * 0.1, W * 0.34, H * 0.62, palette, seed + 1)
        lx = W * 0.09
        doc.text(lx, H * 0.17, pack["brand"], family=fc, size=W * 0.024 * ts, weight=wc, fill=acc, tracking=0.25,
                 upper=True, anchor="start", max_width=W * 0.42, field="Brand")
        y = H * 0.32
        hl = pack["headline"].split()
        for i, word in enumerate(hl[:2] if len(hl) > 1 else hl):
            doc.text(lx, y + i * W * 0.1, word if len(hl) > 1 else pack["headline"], family=fd, size=W * 0.1 * ts,
                     weight=wd, fill=ink, anchor="start", max_width=W * 0.44, field=f"Headline {i + 1}", role="heading")
        doc.text(lx, y + W * 0.24, pack["sub"], family=fs, size=W * 0.052 * ts, fill=acc, anchor="start",
                 max_width=W * 0.44, field="Subheading")
        doc.paragraph(lx, H * 0.8, pack["offer"], family=fb, size=W * 0.032 * ts, max_width=W * 0.8, weight=wb,
                      fill=ink, anchor="start", field="Offer", max_lines=2)
        doc.line(lx, H * 0.86, W * 0.91, H * 0.86, mix(ink, palette["bg"], 0.5), 2)
        doc.text(lx, H * 0.915, pack["contact"], family=fc, size=W * 0.022 * ts, weight=wc, fill=ink, anchor="start",
                 max_width=W * 0.82, field="Contact")

    elif piece == "ig_story":
        pad = W * 0.1
        _visual(doc, pack, W * 0.15, H * 0.08, W * 0.7, H * 0.36, palette, seed + 2)
        cx, cw = W / 2, W - 2 * pad
        text_block(st, doc, cx, pack["brand"], family=fc, size=W * 0.03 * ts, max_width=cw, weight=wc, fill=acc,
                   tracking=0.25, upper=True, field="Brand", gap=W * 0.03)
        text_block(st, doc, cx, pack["cta"], family=fd, size=W * 0.085 * ts, max_width=cw, weight=wd, fill=ink,
                   field="Headline", role="heading", gap=W * 0.06)
        for i, step in enumerate(pack["story_steps"]):
            def srow(y, i=i, step=step):
                r = W * 0.035
                doc.circle(cx - cw * 0.36, y + r, r, fill=adjust_for_contrast(palette["accent"], palette["bg"], 4.8))
                doc.text(cx - cw * 0.36, y + r * 1.38, str(i + 1), family=fd, size=r * 1.1, weight=wd,
                         fill=palette["bg"], allow_overlap=True)
                doc.text(cx - cw * 0.27, y + r * 1.35, step, family=fb, size=W * 0.04 * ts, weight=wb, fill=ink,
                         anchor="start", max_width=cw * 0.75, field=f"Step {i + 1}",
                         box=(cx - cw * 0.27, y, cw * 0.75, r * 2))
            st.add(W * 0.07, srow, W * 0.04)
        st.gap(W * 0.03)

        def button(y):
            bw, bh = cw * 0.7, W * 0.12
            doc.rect(cx - bw / 2, y, bw, bh, fill=ink, rx=bh / 2)
            doc.text(cx, y + bh * 0.6, "Book now", family=fc, size=W * 0.036 * ts, weight=wc,
                     fill=adjust_for_contrast(palette["bg"], ink, 4.5), tracking=0.2, upper=True, max_width=bw * 0.8,
                     field="Button")
        st.add(W * 0.12, button, W * 0.05)
        text_block(st, doc, cx, pack["contact"], family=fb, size=W * 0.03 * ts, max_width=cw, weight=wb, fill=ink,
                   field="Contact")
        st.render(H * 0.48, H - pad)

    elif piece == "web_banner":
        _visual(doc, pack, W * 0.66, H * 0.1, W * 0.26, H * 0.8, palette, seed + 3)
        lx = W * 0.07
        doc.text(lx, H * 0.27, pack["brand"], family=fc, size=H * 0.05 * ts, weight=wc, fill=acc, tracking=0.25,
                 upper=True, anchor="start", max_width=W * 0.5, field="Brand")
        doc.text(lx, H * 0.53, pack["tagline"], family=fd, size=H * 0.13 * ts, weight=wd, fill=ink, anchor="start",
                 max_width=W * 0.55, field="Tagline", role="heading")
        bw, bh = W * 0.24, H * 0.14
        doc.rect(lx, H * 0.64, bw, bh, fill=adjust_for_contrast(palette["accent"], palette["bg"], 4.8), rx=bh / 2)
        doc.text(lx + bw / 2, H * 0.64 + bh * 0.62, pack["cta"], family=fc, size=H * 0.045 * ts, weight=wc,
                 fill=palette["bg"], max_width=bw * 0.85,
                 field="Button")
    return doc
