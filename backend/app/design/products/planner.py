"""Printable planners (budget or habit). Multi-page PDF in US Letter and A4."""
from __future__ import annotations

from .. import ornaments as O
from ..common import resolve_style
from ..styles import mix
from ..svg import Doc

PAPER = {"letter": (8.5 * 72, 11 * 72), "a4": (595.28, 841.89)}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]

BUDGET_PAGES = [
    ("cover", "Paycheck Budget Planner"), ("annual", "Annual Overview"), ("monthly", "Monthly Budget"),
    ("paycheck", "Paycheck Budget"), ("expenses", "Expense Tracker"), ("bills", "Bill Tracker"),
    ("savings", "Savings Tracker"), ("debt", "Debt Payoff Tracker"),
]
HABIT_PAGES = [
    ("cover", "Habit & Focus Planner"), ("habit", "Monthly Habit Tracker"), ("weekly", "Weekly Plan"),
    ("daily", "Daily Focus"), ("goals", "Goal Setting"), ("todo", "To-Do List"),
]


def pages(p: dict) -> list[tuple[str, str]]:
    return HABIT_PAGES if p.get("kind") == "habit" else BUDGET_PAGES


def piece_list(p: dict) -> list[str]:
    return ["planner_letter", "planner_a4"]


def page_count(p: dict) -> int:
    return len(pages(p))


def build(piece: str, p: dict, page: int = 1) -> Doc:
    palette, fonts = resolve_style(p)
    paper = "a4" if piece.endswith("a4") else "letter"
    W, H = PAPER[paper]
    kind, title = pages(p)[page - 1]
    doc = Doc(width=W, height=H, unit="pt", bg="#ffffff", title=f"{title} ({paper})",
              fixes=p.get("_fixes", {}).get(piece, {}), safe_margin=27)
    ink, acc, soft = palette["ink"], palette["accent"], mix(palette["accent2"], "#ffffff", 0.55)
    line_c = mix(ink, "#ffffff", 0.78)
    fd, fb, fc, fs = fonts["display"], fonts["body"], fonts["caps"], fonts["script"]
    mx, top = 0.075 * W, 0.075 * H
    cw = W - 2 * mx

    if kind == "cover":
        doc.rect(0, 0, W, H, fill=palette["bg"])
        O.arch(doc, W * 0.18, H * 0.16, W * 0.64, H * 0.6, fill=soft)
        O.corner_spray(doc, W * 0.5, H * 0.72, W * 0.24, -90, color=acc, accent=palette["accent2"], style="duo",
                       sw=1.1, seed=int(p.get("seed", 7)))
        doc.text(W / 2, H * 0.36, p.get("year_label", "Undated"), family=fc, size=13, weight=500, fill=acc,
                 tracking=0.3, upper=True, max_width=cw, field="Year")
        words = title.split()
        doc.text(W / 2, H * 0.44, " ".join(words[:-1]), family=fd, size=40, weight=fonts["display_weight"], fill=ink,
                 max_width=W * 0.56, field="Title line 1", role="heading")
        doc.text(W / 2, H * 0.52, words[-1], family=fs, size=54, fill=acc, max_width=W * 0.5, field="Title line 2")
        doc.text(W / 2, H * 0.88, "Name ____________________", family=fb, size=13, weight=fonts["body_weight"],
                 fill=ink, max_width=cw, field="Name line")
        return doc

    # header
    doc.rect(0, 0, W, top * 1.55, fill=soft)
    doc.text(mx, top * 1.0, title, family=fd, size=26, weight=fonts["display_weight"], fill=ink, anchor="start",
             max_width=cw * 0.65, field="Page title", role="heading")
    doc.text(W - mx, top * 1.0, "MONTH ________" if kind not in ("annual", "goals") else "YEAR ______", family=fc,
             size=9.5, weight=500, fill=ink, anchor="end", tracking=0.15, max_width=cw * 0.3)
    y0 = top * 1.55 + 26

    def table(y, cols: list[tuple[str, float]], rows: int, row_h: float = 22, heading: str | None = None):
        if heading:
            doc.text(mx, y + 10, heading, family=fc, size=9.5, weight=600, fill=acc, anchor="start", tracking=0.2,
                     upper=True, max_width=cw)
            y += 20
        doc.rect(mx, y, cw, row_h, fill=mix(palette["accent2"], "#ffffff", 0.75))
        x = mx
        for name, frac in cols:
            doc.text(x + 6, y + row_h * 0.66, name, family=fc, size=8, weight=600, fill=ink, anchor="start",
                     tracking=0.12, upper=True, max_width=cw * frac - 10)
            x += cw * frac
        for r in range(1, rows + 1):
            doc.line(mx, y + row_h * (r + 1), mx + cw, y + row_h * (r + 1), line_c, 0.7)
        x = mx
        for name, frac in cols[:-1]:
            x += cw * frac
            doc.line(x, y + row_h, x, y + row_h * (rows + 1), line_c, 0.7)
        doc.rect(mx, y, cw, row_h * (rows + 1), stroke=line_c, sw=0.8)
        return y + row_h * (rows + 1)

    def boxes(y, labels):
        n = len(labels)
        gap = 10
        bw = (cw - gap * (n - 1)) / n
        for i, lb in enumerate(labels):
            x = mx + i * (bw + gap)
            doc.rect(x, y, bw, 52, stroke=line_c, sw=0.8, rx=6)
            doc.text(x + bw / 2, y + 16, lb, family=fc, size=7.5, weight=600, fill=acc, tracking=0.15, upper=True,
                     max_width=bw - 12)
        return y + 52

    avail = H - top - y0
    if kind == "annual":
        bw, bh, gap = (cw - 20) / 3, (avail - 30) / 4, 10
        for i, mo in enumerate(MONTHS):
            r, c = divmod(i, 3)
            x, y = mx + c * (bw + gap), y0 + r * (bh + gap)
            doc.rect(x, y, bw, bh, stroke=line_c, sw=0.8, rx=6)
            doc.text(x + bw / 2, y + 18, mo, family=fc, size=9, weight=600, fill=acc, tracking=0.2, upper=True,
                     max_width=bw - 10)
            for k, lb in enumerate(["Income", "Expenses", "Saved"]):
                yy = y + 40 + k * (bh - 50) / 3
                doc.text(x + 10, yy, lb, family=fb, size=9, weight=fonts["body_weight"], fill=ink, anchor="start",
                         max_width=bw * 0.4)
                doc.line(x + bw * 0.45, yy + 2, x + bw - 10, yy + 2, line_c, 0.7)
    elif kind == "monthly":
        y = boxes(y0, ["Total income", "Total expenses", "Savings", "Left over"]) + 22
        half = (avail - 52 - 22 - 40) / 2
        rows = int((half - 42) / 20)
        y = table(y, [("Income source", 0.6), ("Expected", 0.2), ("Actual", 0.2)], max(3, rows // 2), 20, "Income") + 18
        table(y, [("Expense", 0.45), ("Budget", 0.2), ("Actual", 0.2), ("Diff", 0.15)],
              max(6, int((H - top - y - 40) / 20) - 1), 20, "Expenses")
    elif kind == "paycheck":
        y = boxes(y0, ["Pay date", "Paycheck amount", "Remaining"]) + 22
        table(y, [("Bill / expense", 0.45), ("Due", 0.15), ("Amount", 0.2), ("Paid", 0.2)],
              int((H - top - y - 40) / 21) - 1, 21, "Planned spending")
    elif kind == "expenses":
        table(y0, [("Date", 0.15), ("Description", 0.4), ("Category", 0.25), ("Amount", 0.2)],
              int((avail - 30) / 21) - 1, 21)
    elif kind == "bills":
        table(y0, [("Bill", 0.34), ("Due date", 0.16), ("Amount", 0.18), ("Auto-pay", 0.14), ("Paid", 0.18)],
              int((avail - 30) / 21) - 1, 21)
    elif kind == "savings":
        y = boxes(y0, ["Saving for", "Goal amount", "Target date"]) + 26
        cols, rows = 10, 10
        cell = min(cw / cols, (H - top - y - 110) / rows)
        gx = mx + (cw - cell * cols) / 2
        for r in range(rows):
            for c in range(cols):
                doc.circle(gx + cell * (c + 0.5), y + cell * (r + 0.5), cell * 0.36, stroke=line_c, sw=0.8)
        doc.text(W / 2, y + cell * rows + 26, "Colour in one circle each time you save 1% of your goal",
                 family=fb, size=10, weight=fonts["body_weight"], fill=ink, max_width=cw, italic=False)
    elif kind == "debt":
        y = boxes(y0, ["Debt name", "Starting balance", "Interest rate", "Min. payment"]) + 22
        table(y, [("Date", 0.2), ("Payment", 0.25), ("Balance", 0.3), ("Progress", 0.25)],
              int((H - top - y - 40) / 21) - 1, 21, "Payment log")
    elif kind == "habit":
        days = 31
        name_w = cw * 0.28
        cell = (cw - name_w) / days
        rows = 18
        row_h = min(26, (avail - 40) / (rows + 1))
        for d in range(days):
            doc.text(mx + name_w + cell * (d + 0.5), y0 + row_h * 0.65, str(d + 1), family=fb, size=6.5, weight=600,
                     fill=ink, max_width=cell * 1.2)
        doc.text(mx + 4, y0 + row_h * 0.65, "HABIT", family=fc, size=8, weight=600, fill=acc, anchor="start",
                 tracking=0.2, max_width=name_w)
        for r in range(rows):
            yy = y0 + row_h * (r + 1)
            if r % 2 == 0:
                doc.rect(mx, yy, cw, row_h, fill=mix(palette["accent2"], "#ffffff", 0.85))
            for d in range(days):
                doc.rect(mx + name_w + cell * d + cell * 0.15, yy + (row_h - cell * 0.7) / 2, cell * 0.7, cell * 0.7,
                         stroke=line_c, sw=0.6, rx=1.5)
    elif kind == "weekly":
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "Notes"]
        bw, bh, gap = (cw - 12) / 2, (avail - 36) / 4, 12
        for i, dname in enumerate(days):
            r, c = divmod(i, 2)
            x, y = mx + c * (bw + gap), y0 + r * (bh + gap)
            doc.rect(x, y, bw, bh, stroke=line_c, sw=0.8, rx=6)
            doc.text(x + 10, y + 18, dname, family=fc, size=8.5, weight=600, fill=acc, anchor="start", tracking=0.2,
                     upper=True, max_width=bw - 20)
            for k in range(int((bh - 34) / 18)):
                doc.line(x + 10, y + 38 + k * 18, x + bw - 10, y + 38 + k * 18, line_c, 0.6)
    elif kind in ("daily", "goals", "todo"):
        sections = {"daily": ["Top 3 priorities", "Schedule", "Notes"], "goals": ["My goal", "Why it matters",
                    "Action steps", "Milestones"], "todo": ["To do"]}[kind]
        sh = (avail - 20) / len(sections)
        for i, sec in enumerate(sections):
            y = y0 + i * sh
            doc.text(mx, y + 12, sec, family=fc, size=9.5, weight=600, fill=acc, anchor="start", tracking=0.2,
                     upper=True, max_width=cw)
            for k in range(int((sh - 34) / 22)):
                yy = y + 36 + k * 22
                if kind == "todo" or sec in ("Top 3 priorities", "Action steps"):
                    doc.rect(mx, yy - 11, 10, 10, stroke=line_c, sw=0.8, rx=2)
                    doc.line(mx + 18, yy, mx + cw, yy, line_c, 0.6)
                else:
                    doc.line(mx, yy, mx + cw, yy, line_c, 0.6)
    doc.text(W / 2, H - top * 0.45, p.get("footer", ""), family=fb, size=7.5, weight=400, fill=line_c, max_width=cw)
    return doc
