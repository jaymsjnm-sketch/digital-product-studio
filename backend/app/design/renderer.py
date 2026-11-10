"""Headless-Chromium renderer: SVG -> vector PDF, 300-DPI PNG/JPG, previews, and layout measurements.

Chromium gives exact font rendering (same engine buyers' browsers use) and true vector PDFs
with embedded fonts. One Renderer instance per job; it is not thread-safe.
"""
from __future__ import annotations

import io
import os
from pathlib import Path

from PIL import Image

from ..config import log

Image.MAX_IMAGE_PIXELS = 200_000_000

MEASURE_JS = r"""
() => {
  const svg = document.querySelector('svg');
  const vb = svg.viewBox.baseVal;
  const out = {texts: [], images: [], loaded_fonts: [], vb: [vb.width, vb.height]};
  for (const t of svg.querySelectorAll('text')) {
    const b = t.getBBox();
    out.texts.push({id: t.id, text: t.textContent, role: t.dataset.role || '', field: t.dataset.field || null,
      box: t.dataset.qcBox || null, bbox: [b.x, b.y, b.width, b.height], fill: t.getAttribute('fill'),
      family: t.getAttribute('font-family'), size: parseFloat(t.getAttribute('font-size')),
      y: parseFloat(t.getAttribute('y')), x: parseFloat(t.getAttribute('x')),
      anchor: t.getAttribute('text-anchor'), allowOverlap: t.dataset.allowOverlap === '1'});
  }
  for (const im of svg.querySelectorAll('image')) {
    const b = im.getBBox();
    out.images.push({id: im.id, bbox: [b.x, b.y, b.width, b.height], natural: [parseFloat(im.dataset.pxw||0), parseFloat(im.dataset.pxh||0)]});
  }
  for (const f of document.fonts) { if (f.status === 'loaded') out.loaded_fonts.push(f.family.replace(/["']/g, '')); }
  return out;
}
"""


def _html(svg: str, w_in: float, h_in: float) -> str:
    return ("<!doctype html><html><head><meta charset='utf-8'><style>"
            f"@page{{size:{w_in}in {h_in}in;margin:0}}html,body{{margin:0;padding:0;background:#fff}}"
            "svg{display:block}</style></head><body>" + svg + "</body></html>")


class Renderer:
    def __init__(self):
        self._pw = None
        self._browser = None
        self._contexts: dict[float, object] = {}

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        exe = os.environ.get("DPS_CHROMIUM_PATH")
        try:
            self._browser = self._pw.chromium.launch(executable_path=exe) if exe else self._pw.chromium.launch()
        except Exception as e:  # noqa: BLE001
            raise RuntimeError("Could not start Chromium for rendering. Run:  python -m playwright install chromium  "
                               f"(details: {e})") from e
        return self

    def __exit__(self, *exc):
        for c in self._contexts.values():
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def _page(self, css_w: int, css_h: int, scale: float):
        key = round(scale, 4)
        ctx = self._contexts.get(key)
        if ctx is None:
            ctx = self._browser.new_context(device_scale_factor=scale, viewport={"width": 800, "height": 600})
            self._contexts[key] = ctx
        page = ctx.new_page()
        page.set_viewport_size({"width": max(1, css_w), "height": max(1, css_h)})
        return page

    def render(self, svg: str, *, unit: str, width: float, height: float, png_path: Path | None = None,
               jpg_path: Path | None = None, pdf_path: Path | None = None, preview_path: Path | None = None,
               dpi: int = 300, preview_max: int = 1400, measure: bool = True, jpg_quality: int = 90) -> dict:
        """Render one SVG. width/height are SVG user units (pt for print, px for digital)."""
        if unit == "pt":
            w_in, h_in = width / 72, height / 72
            css_w, css_h = round(w_in * 96), round(h_in * 96)
        else:
            css_w, css_h = int(width), int(height)
            w_in, h_in = width / 96, height / 96
        html = _html(svg, round(w_in, 4), round(h_in, 4))
        result: dict = {}

        # Preview (+ measurements) at screen resolution
        prev_scale = min(2.0, preview_max / max(css_w, css_h))
        page = self._page(css_w, css_h, prev_scale)
        try:
            page.set_content(html, wait_until="load")
            page.evaluate("document.fonts.ready.then(() => true)")
            if measure:
                result["measure"] = page.evaluate(MEASURE_JS)
                result["measure"]["css_size"] = [css_w, css_h]
            png_bytes = page.screenshot(clip={"x": 0, "y": 0, "width": css_w, "height": css_h}, type="png")
            if preview_path:
                Path(preview_path).write_bytes(png_bytes)
            result["preview_png"] = png_bytes
            result["preview_scale"] = prev_scale
            if measure:  # same view with all text hidden -> lets QC see what graphics sit under each text
                page.add_style_tag(content="text{visibility:hidden !important}")
                result["textless_png"] = page.screenshot(clip={"x": 0, "y": 0, "width": css_w, "height": css_h},
                                                         type="png")
                page.evaluate("document.querySelectorAll('style').forEach(s => { if (s.textContent.includes('visibility:hidden')) s.remove(); })")
            if pdf_path and unit == "pt":
                page.pdf(path=str(pdf_path), width=f"{w_in}in", height=f"{h_in}in", print_background=True,
                         margin={"top": "0", "right": "0", "bottom": "0", "left": "0"}, prefer_css_page_size=True)
        finally:
            page.close()

        # Full-resolution raster
        if png_path or jpg_path:
            scale = dpi / 96 if unit == "pt" else 1.0
            page = self._page(css_w, css_h, scale)
            try:
                page.set_content(html, wait_until="load")
                page.evaluate("document.fonts.ready.then(() => true)")
                raw = page.screenshot(clip={"x": 0, "y": 0, "width": css_w, "height": css_h}, type="png",
                                      timeout=180000)
            finally:
                page.close()
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            target = (round(w_in * dpi), round(h_in * dpi)) if unit == "pt" else (int(width), int(height))
            if img.size != target:
                img = img.resize(target, Image.LANCZOS)
            save_dpi = (dpi, dpi) if unit == "pt" else (72, 72)
            if png_path:
                img.save(png_path, "PNG", dpi=save_dpi, optimize=False, compress_level=6)
            if jpg_path:
                img.save(jpg_path, "JPEG", quality=jpg_quality, dpi=save_dpi, optimize=True, subsampling=0)
            result["raster_size"] = img.size
            log.debug("rendered raster %s", img.size)
        return result

    def html_to_image(self, html: str, css_w: int, css_h: int, out_path: Path, *, scale: float = 1.0,
                      quality: int = 88, max_bytes: int | None = None) -> Path:
        """Render arbitrary HTML (used for mockups). Saves JPG (optionally under max_bytes) or PNG."""
        page = self._page(css_w, css_h, scale)
        try:
            page.set_content(html, wait_until="load")
            page.evaluate("document.fonts.ready.then(() => true)")
            raw = page.screenshot(clip={"x": 0, "y": 0, "width": css_w, "height": css_h}, type="png")
        finally:
            page.close()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        out_path = Path(out_path)
        if out_path.suffix.lower() in (".jpg", ".jpeg"):
            q = quality
            while True:
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
                if not max_bytes or buf.tell() <= max_bytes or q <= 50:
                    break
                q -= 6
            out_path.write_bytes(buf.getvalue())
        else:
            img.save(out_path, "PNG", optimize=True)
        return out_path

    def pdf_from_html(self, html: str, w_in: float, h_in: float, out_path: Path) -> Path:
        page = self._page(round(w_in * 96), round(h_in * 96), 1.0)
        try:
            page.set_content(html, wait_until="load")
            page.evaluate("document.fonts.ready.then(() => true)")
            page.pdf(path=str(out_path), width=f"{w_in}in", height=f"{h_in}in", print_background=True,
                     margin={"top": "0", "right": "0", "bottom": "0", "left": "0"}, prefer_css_page_size=True)
        finally:
            page.close()
        return Path(out_path)
