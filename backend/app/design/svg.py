"""Minimal SVG document builder with typography helpers and QC metadata.

Every text element can carry:
  data-qc-box="x y w h"  - the area the text must stay inside (checked after rendering)
  data-field="Label"     - marks the text as user-editable (personalizer + editable template)
  data-role              - semantic role (heading, body, name, ...)
"""
from __future__ import annotations

import html
from dataclasses import dataclass, field

from . import fonts as F


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


@dataclass
class Doc:
    width: float                 # in user units
    height: float
    unit: str = "pt"             # "pt" (print, 72/in) or "px" (digital)
    bg: str = "#ffffff"
    title: str = ""
    elements: list[str] = field(default_factory=list)
    defs: list[str] = field(default_factory=list)
    fonts_used: set = field(default_factory=set)
    safe_margin: float = 18.0    # print-safe margin in user units (0.25in = 18pt)
    _id: int = 0
    fixes: dict = field(default_factory=dict)  # element id -> size multiplier from QC auto-fix
    meta: dict = field(default_factory=dict)

    @property
    def width_in(self) -> float:
        return self.width / 72 if self.unit == "pt" else self.width / 96

    @property
    def height_in(self) -> float:
        return self.height / 72 if self.unit == "pt" else self.height / 96

    def nid(self, prefix: str = "el") -> str:
        self._id += 1
        return f"{prefix}{self._id}"

    def add(self, s: str) -> None:
        self.elements.append(s)

    def add_def(self, s: str) -> None:
        self.defs.append(s)

    # ---------------------------------------------------------------- shapes
    def rect(self, x, y, w, h, fill="none", stroke=None, sw=1.0, rx=0, opacity=None, extra=""):
        st = f' stroke="{stroke}" stroke-width="{fmt(sw)}"' if stroke else ""
        op = f' opacity="{fmt(opacity)}"' if opacity is not None else ""
        self.add(f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}" rx="{fmt(rx)}" '
                 f'fill="{fill}"{st}{op} {extra}/>')

    def line(self, x1, y1, x2, y2, stroke, sw=1.0, opacity=None, dash=None):
        op = f' opacity="{fmt(opacity)}"' if opacity is not None else ""
        da = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{fmt(x1)}" y1="{fmt(y1)}" x2="{fmt(x2)}" y2="{fmt(y2)}" stroke="{stroke}" '
                 f'stroke-width="{fmt(sw)}" stroke-linecap="round"{op}{da}/>')

    def circle(self, cx, cy, r, fill="none", stroke=None, sw=1.0, opacity=None):
        st = f' stroke="{stroke}" stroke-width="{fmt(sw)}"' if stroke else ""
        op = f' opacity="{fmt(opacity)}"' if opacity is not None else ""
        self.add(f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r)}" fill="{fill}"{st}{op}/>')

    def path(self, d, fill="none", stroke=None, sw=1.0, opacity=None, extra=""):
        cap = '' if "stroke-linecap" in extra else ' stroke-linecap="round"'
        st = f' stroke="{stroke}" stroke-width="{fmt(sw)}"{cap} stroke-linejoin="round"' if stroke else ""
        op = f' opacity="{fmt(opacity)}"' if opacity is not None else ""
        self.add(f'<path d="{d}" fill="{fill}"{st}{op} {extra}/>')

    # ---------------------------------------------------------------- text
    def text(self, x, y, content, *, family, size, weight=400, fill="#000", anchor="middle", tracking=0.0,
             italic=False, upper=False, max_width=None, min_size=None, field_label=None, role="text",
             box=None, eid=None, opacity=None, baseline="alphabetic", field=None, allow_overlap=False) -> dict:
        """Single-line text. Auto-shrinks to max_width. Returns layout info (size, width, id)."""
        field_label = field_label or field
        eid = eid or self.nid("t")
        content = str(content)
        shown = content.upper() if upper else content
        fx = self.fixes.get(eid, 1.0)
        if isinstance(fx, dict):
            size *= fx.get("scale", 1.0)
            fill = fx.get("fill", fill)
        else:
            size *= fx
        if max_width:
            size = F.fit_size(shown, family, size, max_width, weight=weight, italic=italic, tracking=tracking,
                              min_size=min_size or size * 0.4)
        w = F.text_width(shown, family, size, weight, italic, tracking)
        self.fonts_used.add((family, weight, italic))
        if box is None and max_width:
            bx = x - max_width / 2 if anchor == "middle" else (x - max_width if anchor == "end" else x)
            box = (bx, y - size * 1.05, max_width, size * 1.45)
        attrs = [f'id="{eid}"', f'x="{fmt(x)}"', f'y="{fmt(y)}"', f'font-family="{esc(family)}"',
                 f'font-size="{fmt(round(size, 2))}"', f'font-weight="{weight}"', f'fill="{fill}"',
                 f'text-anchor="{anchor}"', f'data-role="{role}"']
        if baseline != "alphabetic":
            attrs.append(f'dominant-baseline="{baseline}"')
        if italic:
            attrs.append('font-style="italic"')
        if tracking:
            attrs.append(f'letter-spacing="{fmt(round(tracking * size, 3))}"')
        if opacity is not None:
            attrs.append(f'opacity="{fmt(opacity)}"')
        if field_label:
            attrs.append(f'data-field="{esc(field_label)}"')
        if box:
            attrs.append('data-qc-box="' + " ".join(fmt(round(v, 2)) for v in box) + '"')
        if upper:
            attrs.append('data-upper="1"')
        if allow_overlap:
            attrs.append('data-allow-overlap="1"')
        if max_width:
            attrs.append(f'data-max-width="{fmt(round(max_width, 2))}"')
        # Trailing letter-spacing shifts centred text right; compensate like CSS does not.
        if tracking and anchor == "middle":
            attrs[1] = f'x="{fmt(x + tracking * size / 2)}"'
        self.add(f"<text {' '.join(attrs)}>{esc(shown)}</text>")
        return {"id": eid, "size": size, "width": w, "x": x, "y": y}

    def paragraph(self, x, y, content, *, family, size, max_width, leading=1.35, weight=400, fill="#000",
                  anchor="middle", max_lines=None, field_label=None, role="body", tracking=0.0, italic=False,
                  field=None) -> dict:
        """Wrapped multi-line text (each line its own <text> for robust rendering everywhere)."""
        field_label = field_label or field
        eid = self.nid("p")
        fx = self.fixes.get(eid, 1.0)
        size = size * (fx.get("scale", 1.0) if isinstance(fx, dict) else fx)
        lines = F.wrap(content, family, size, max_width, weight=weight, tracking=tracking)
        while max_lines and len(lines) > max_lines and size > 4:
            size *= 0.94
            lines = F.wrap(content, family, size, max_width, weight=weight, tracking=tracking)
        lh = size * leading
        total_h = lh * (len(lines) - 1) + size
        for i, ln in enumerate(lines):
            self.text(x, y + i * lh, ln, family=family, size=size, weight=weight, fill=fill, anchor=anchor,
                      field_label=(f"{field_label} (line {i + 1})" if field_label and len(lines) > 1 else field_label),
                      role=role, tracking=tracking, italic=italic, eid=f"{eid}_{i}",
                      box=((x - max_width / 2) if anchor == "middle" else x, y + i * lh - size * 1.05, max_width,
                           size * 1.45))
        return {"id": eid, "size": size, "lines": len(lines), "height": total_h, "bottom": y + total_h - size}

    # ---------------------------------------------------------------- output
    def svg(self, embed_fonts: bool = True, extra_css: str = "") -> str:
        w_attr = f"{fmt(round(self.width_in, 4))}in" if self.unit == "pt" else f"{fmt(self.width)}px"
        h_attr = f"{fmt(round(self.height_in, 4))}in" if self.unit == "pt" else f"{fmt(self.height)}px"
        css = F.font_face_css(self.fonts_used, embed=embed_fonts) + "\ntext{font-variant-numeric:lining-nums}\n" + extra_css
        title = f"<title>{esc(self.title)}</title>" if self.title else ""
        defs = "<defs>" + "".join(self.defs) + "</defs>" if self.defs else ""
        return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'width="{w_attr}" height="{h_attr}" viewBox="0 0 {fmt(self.width)} {fmt(self.height)}" '
                f'data-unit="{self.unit}" data-safe-margin="{fmt(self.safe_margin)}">'
                f"{title}<style>{css}</style>{defs}"
                f'<rect id="background" x="0" y="0" width="{fmt(self.width)}" height="{fmt(self.height)}" fill="{self.bg}"/>'
                + "".join(self.elements) + "</svg>")
