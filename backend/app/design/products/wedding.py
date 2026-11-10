"""Wedding stationery suite: invitation, welcome signs, seating chart, menu, table numbers, thank-you card."""
from __future__ import annotations

from ..common import Stack, decorate, para_block, resolve_style, text_block
from .. import ornaments as O
from ..styles import mix
from ..svg import Doc

NUM_WORDS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
             "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen", "Twenty"]

DEFAULT_CONTENT = {
    "name1": "Olivia", "name2": "Samuel", "date_long": "Saturday, the twelfth of June",
    "weekday": "Saturday", "month": "June", "day": "12", "year": "2027", "date_short": "06.12.2027",
    "time": "at four o'clock in the afternoon", "venue": "The Willow Estate", "city": "Napa Valley, California",
    "host_line": "Together with their families", "request_line": "request the pleasure of your company at their wedding",
    "reception": "Dinner and dancing to follow",
    "rsvp": "Kindly reply by the first of May",
    "menu": [
        ["To Start", "Heirloom Tomato Salad", "burrata, basil oil, toasted sourdough"],
        ["Main Course", "Herb-Roasted Chicken", "lemon thyme jus, crushed potatoes, spring greens"],
        ["", "Wild Mushroom Risotto", "parmesan, chive, white truffle oil"],
        ["Dessert", "Wedding Cake", "vanilla bean sponge, fresh berries, whipped cream"],
    ],
    "thank_you_note": "We are so grateful you could share our day",
    "tables": 12, "guests_per_table": 8,
}

FIRST = ["Amelia", "Benjamin", "Charlotte", "Daniel", "Eleanor", "Felix", "Grace", "Henry", "Isla", "Jack", "Lucy",
         "Leo", "Maya", "Noah", "Nora", "Oscar", "Penelope", "Quinn", "Rose", "Theo", "Violet", "William", "Zoe",
         "Arthur", "Clara", "Elliot", "Hazel", "Miles", "Ruby", "Simon", "Stella", "Tobias"]
LAST = ["Adams", "Bennett", "Carter", "Dawson", "Ellis", "Foster", "Grant", "Hayes", "Irving", "Jensen", "Keller",
        "Lawson", "Morgan", "Nolan", "Owens", "Parker", "Reed", "Sutton", "Turner", "Walsh", "Young", "Brooks",
        "Collins", "Hart"]

PIECES = {
    "invitation": {"label": "Invitation", "size": (5, 7), "unit": "pt"},
    "welcome_sign": {"label": "Welcome sign", "size": (24, 36), "unit": "pt"},
    "welcome_sign_18x24": {"label": "Welcome sign 18x24", "size": (18, 24), "unit": "pt"},
    "seating_chart": {"label": "Seating chart", "size": (24, 36), "unit": "pt"},
    "menu": {"label": "Menu card", "size": (4, 9), "unit": "pt"},
    "table_number": {"label": "Table numbers 1-20", "size": (4, 6), "unit": "pt", "pages": 20},
    "thank_you": {"label": "Thank-you card", "size": (5.5, 4.25), "unit": "pt"},
}


def guest_names(n_tables: int, per_table: int) -> list[list[str]]:
    out, k = [], 0
    for t in range(n_tables):
        names = []
        for g in range(per_table):
            names.append(f"{FIRST[(k * 7 + 3) % len(FIRST)]} {LAST[(k * 5 + t) % len(LAST)]}")
            k += 1
        out.append(names)
    return out


def _doc(piece: str, p: dict, palette: dict) -> Doc:
    w, h = PIECES[piece]["size"]
    return Doc(width=w * 72, height=h * 72, unit="pt", bg=palette["bg"], title=PIECES[piece]["label"],
               fixes=p.get("_fixes", {}).get(piece, {}))


def build(piece: str, p: dict, page: int = 1) -> Doc:
    palette, fonts = resolve_style(p)
    c = {**DEFAULT_CONTENT, **(p.get("content") or {})}
    style, orn, seed = p.get("style", "botanical"), int(p.get("ornament", 2)), int(p.get("seed", 7))
    ts, sp = float(p.get("text_scale", 1.0)), float(p.get("spacing", 1.0))
    doc = _doc(piece, p, palette)
    W, H = doc.width, doc.height
    m = min(W, H)
    ink, acc = palette["ink"], palette["accent"]
    fam_d, fam_s, fam_b, fam_c = fonts["display"], fonts["script"], fonts["body"], fonts["caps"]
    wd, wb, wc = fonts["display_weight"], fonts["body_weight"], fonts["caps_weight"]
    caps_tr = 0.22

    if piece == "table_number":
        area = decorate(doc, style, palette, min(orn, 1), seed + page, scale=0.9)
    elif piece == "seating_chart":
        area = decorate(doc, style, palette, orn, seed, spray=0.2)
    else:
        area = decorate(doc, style, palette, orn, seed)
    cx = (area["left"] + area["right"]) / 2
    cw = area["right"] - area["left"]
    st = Stack()

    if piece == "invitation":
        text_block(st, doc, cx, c["host_line"], family=fam_c, size=m * 0.021 * ts, max_width=cw, weight=wc, fill=ink,
                   tracking=caps_tr, upper=True, field="Host line", gap=m * 0.05 * sp)
        text_block(st, doc, cx, c["name1"], family=fam_s, size=m * 0.115 * ts, max_width=cw, fill=acc, field="Name 1",
                   role="name", asc=0.72, desc=0.18, gap=m * 0.0 * sp)
        text_block(st, doc, cx, "&", family=fam_d, size=m * 0.05 * ts, max_width=cw, fill=ink, italic=True,
                   weight=wd, gap=m * 0.005 * sp)
        text_block(st, doc, cx, c["name2"], family=fam_s, size=m * 0.115 * ts, max_width=cw, fill=acc, field="Name 2",
                   role="name", asc=0.72, desc=0.18, gap=m * 0.05 * sp)
        para_block(st, doc, cx, c["request_line"].upper(), family=fam_c, size=m * 0.02 * ts, max_width=cw * 0.82,
                   weight=wc, fill=ink, tracking=caps_tr * 0.8, leading=1.75, field="Request line", gap=m * 0.055 * sp,
                   max_lines=2)
        _date_row(st, doc, cx, cw, c, fam_c, fam_d, wc, wd, ink, acc, m * ts, gap=m * 0.05 * sp)
        text_block(st, doc, cx, c["time"], family=fam_b, size=m * 0.03 * ts, max_width=cw, weight=wb, fill=ink,
                   italic=True, field="Time", gap=m * 0.035 * sp)
        text_block(st, doc, cx, c["venue"], family=fam_d, size=m * 0.05 * ts, max_width=cw, weight=wd, fill=ink,
                   field="Venue", gap=m * 0.012 * sp)
        text_block(st, doc, cx, c["city"], family=fam_c, size=m * 0.019 * ts, max_width=cw, weight=wc, fill=ink,
                   tracking=caps_tr, upper=True, field="City", gap=m * 0.05 * sp)
        text_block(st, doc, cx, c["reception"], family=fam_b, size=m * 0.03 * ts, max_width=cw, weight=wb, fill=acc,
                   italic=True, field="Reception line")
        st.render(area["top"], area["bottom"])

    elif piece in ("welcome_sign", "welcome_sign_18x24"):
        text_block(st, doc, cx, "Welcome", family=fam_s, size=m * 0.13 * ts, max_width=cw, fill=acc, role="heading",
                   field="Welcome", asc=0.75, desc=0.2, gap=m * 0.03 * sp)
        text_block(st, doc, cx, "to the wedding of", family=fam_c, size=m * 0.024 * ts, max_width=cw, weight=wc,
                   fill=ink, tracking=caps_tr, upper=True, field="Subheading", gap=m * 0.06 * sp)
        text_block(st, doc, cx, c["name1"], family=fam_d, size=m * 0.1 * ts, max_width=cw, weight=wd, fill=ink,
                   upper=True, tracking=0.06, field="Name 1", role="name", gap=m * 0.012 * sp)
        text_block(st, doc, cx, "&", family=fam_s, size=m * 0.11 * ts, max_width=cw, fill=acc, asc=0.7, desc=0.15,
                   gap=m * 0.012 * sp)
        text_block(st, doc, cx, c["name2"], family=fam_d, size=m * 0.1 * ts, max_width=cw, weight=wd, fill=ink,
                   upper=True, tracking=0.06, field="Name 2", role="name", gap=m * 0.065 * sp)
        st.add(m * 0.01, lambda y: O.divider(doc, cx, y + m * 0.005, cw * 0.38, color=acc, sw=max(1, m * 0.0016),
                                              motif="leaf"), m * 0.05 * sp)
        text_block(st, doc, cx, f"{c['month']} {c['day']}, {c['year']}", family=fam_c, size=m * 0.03 * ts,
                   max_width=cw, weight=wc, fill=ink, tracking=caps_tr, upper=True, field="Date", gap=m * 0.02 * sp)
        text_block(st, doc, cx, c["venue"], family=fam_b, size=m * 0.04 * ts, max_width=cw, weight=wb, fill=ink,
                   italic=True, field="Venue")
        st.render(area["top"], area["bottom"])

    elif piece == "seating_chart":
        n_t = int(c.get("tables", 12))
        per = int(c.get("guests_per_table", 8))
        guests = c.get("guests") or guest_names(n_t, per)
        top_st = Stack()
        text_block(top_st, doc, cx, "Please find your seat", family=fam_s, size=m * 0.075 * ts, max_width=cw, fill=acc,
                   role="heading", field="Heading", asc=0.75, desc=0.22, gap=m * 0.02)
        text_block(top_st, doc, cx, f"{c['name1']} & {c['name2']}", family=fam_c, size=m * 0.022 * ts, max_width=cw,
                   weight=wc, fill=ink, tracking=caps_tr, upper=True, field="Names", gap=m * 0.008)
        text_block(top_st, doc, cx, f"{c['month']} {c['day']}, {c['year']}", family=fam_c, size=m * 0.016 * ts,
                   max_width=cw, weight=wc, fill=ink, tracking=caps_tr, upper=True, field="Date")
        header_h = top_st.total
        _, header_bottom = top_st.render(area["top"], area["top"] + header_h, align="top")
        grid_top = header_bottom + m * 0.05
        cols = 3 if n_t <= 12 else 4
        rows = -(-n_t // cols)
        gw = cw * 1.04
        col_w = gw / cols
        row_h = (area["bottom"] - grid_top) / rows
        name_size = min(m * 0.022 * ts, row_h / (per + 3.2) / 1.42)
        for t in range(n_t):
            r, col = divmod(t, cols)
            tx = cx - gw / 2 + col_w * (col + 0.5)
            ty = grid_top + r * row_h
            doc.text(tx, ty + name_size * 1.5, f"Table {NUM_WORDS[t + 1] if t + 1 <= 20 else t + 1}", family=fam_c,
                     size=name_size * 1.05, weight=max(wc, 500), fill=acc, tracking=0.2, upper=True,
                     max_width=col_w * 0.86, field=f"Table {t + 1} heading", role="heading")
            O.divider(doc, tx, ty + name_size * 2.35, col_w * 0.28, color=mix(acc, palette["bg"], 0.3),
                      sw=max(0.6, m * 0.0008), motif="dot")
            for g, name in enumerate(guests[t][:per]):
                doc.text(tx, ty + name_size * (3.9 + g * 1.42), name, family=fam_b, size=name_size, weight=wb,
                         fill=ink, max_width=col_w * 0.86, field=f"Table {t + 1} guest {g + 1}", role="guest")

    elif piece == "menu":
        text_block(st, doc, cx, "Menu", family=fam_s, size=m * 0.2 * ts, max_width=cw, fill=acc, role="heading",
                   field="Heading", asc=0.75, desc=0.2, gap=m * 0.02 * sp)
        text_block(st, doc, cx, f"{c['name1']} & {c['name2']}  ·  {c['date_short']}", family=fam_c, size=m * 0.035 * ts,
                   max_width=cw, weight=wc, fill=ink, tracking=0.18, upper=True, field="Names & date",
                   gap=m * 0.12 * sp)
        for i, (course, dish, desc) in enumerate(c["menu"]):
            if course:
                if i:
                    st.gap(m * 0.05 * sp)
                text_block(st, doc, cx, course, family=fam_c, size=m * 0.036 * ts, max_width=cw, weight=max(wc, 500),
                           fill=acc, tracking=0.25, upper=True, field=f"Course {i + 1}", gap=m * 0.045 * sp)
                st.add(m * 0.01, lambda y, w=cw * 0.25: O.divider(doc, cx, y, w, color=mix(acc, palette["bg"], 0.3),
                                                                   sw=0.6, motif="dot"), m * 0.05 * sp)
            else:
                text_block(st, doc, cx, "or", family=fam_b, size=m * 0.045 * ts, max_width=cw, weight=wb, fill=acc,
                           italic=True, gap=m * 0.03 * sp)
            text_block(st, doc, cx, dish, family=fam_d, size=m * 0.07 * ts, max_width=cw, weight=wd, fill=ink,
                       field=f"Dish {i + 1}", gap=m * 0.02 * sp)
            para_block(st, doc, cx, desc, family=fam_b, size=m * 0.045 * ts, max_width=cw * 0.9, weight=wb, fill=ink,
                       italic=True, leading=1.3, field=f"Description {i + 1}", max_lines=2, gap=m * 0.04 * sp)
        st.render(area["top"], area["bottom"])

    elif piece == "table_number":
        text_block(st, doc, cx, "Table", family=fam_s, size=m * 0.17 * ts, max_width=cw, fill=acc, role="heading",
                   asc=0.75, desc=0.2, gap=m * 0.01 * sp)
        text_block(st, doc, cx, str(page), family=fam_d, size=m * 0.42 * ts, max_width=cw, weight=wd, fill=ink,
                   field="Table number", asc=0.74, desc=0.3, gap=m * 0.03 * sp)
        st.add(m * 0.01, lambda y: O.divider(doc, cx, y, cw * 0.45, color=acc, sw=0.8, motif="leaf"), m * 0.05 * sp)
        text_block(st, doc, cx, f"{c['name1']} & {c['name2']}", family=fam_c, size=m * 0.045 * ts, max_width=cw,
                   weight=wc, fill=ink, tracking=caps_tr, upper=True, field="Names")
        st.render(area["top"], area["bottom"])

    elif piece == "thank_you":
        area = {"top": m * 0.14, "bottom": H - m * 0.14, "left": W * 0.18, "right": W * 0.82} if style != "arch" else area
        cx = (area["left"] + area["right"]) / 2
        cw = area["right"] - area["left"]
        text_block(st, doc, cx, "Thank you", family=fam_s, size=m * 0.2 * ts, max_width=cw, fill=acc, role="heading",
                   field="Heading", asc=0.75, desc=0.22, gap=m * 0.05 * sp)
        text_block(st, doc, cx, c["thank_you_note"], family=fam_b, size=m * 0.045 * ts, max_width=cw * 0.95,
                   weight=wb, fill=ink, italic=True, field="Note", gap=m * 0.06 * sp)
        text_block(st, doc, cx, f"{c['name1']} & {c['name2']}  ·  {c['date_short']}", family=fam_c,
                   size=m * 0.033 * ts, max_width=cw, weight=wc, fill=ink, tracking=caps_tr, upper=True,
                   field="Names & date")
        st.render(area["top"], area["bottom"])
    return doc


def _date_row(st: Stack, doc: Doc, cx, cw, c, fam_c, fam_d, wc, wd, ink, acc, m, gap):
    """WEEKDAY | 12 | JUNE 2027 with hairlines - a classic stationery date lockup."""
    big = m * 0.075
    small = m * 0.021

    def draw(y):
        base = y + big * 0.74
        side = cw * 0.30
        doc.text(cx, base, c["day"], family=fam_d, size=big, weight=wd, fill=acc, field="Day", role="date")
        for sign, word, label in ((-1, c["weekday"], "Weekday"), (1, f"{c['month']} {c['year']}", "Month & year")):
            sx = cx + sign * (big * 0.55 + side / 2 + m * 0.01)
            doc.text(sx, base - big * 0.27, word, family=fam_c, size=small, weight=wc, fill=ink, tracking=0.2,
                     upper=True, max_width=side, field=label, role="date")
            doc.line(sx - side / 2, base - big * 0.62, sx + side / 2, base - big * 0.62, acc, 0.6)
            doc.line(sx - side / 2, base - big * 0.02, sx + side / 2, base - big * 0.02, acc, 0.6)
    st.add(big * 0.82, draw, gap)
