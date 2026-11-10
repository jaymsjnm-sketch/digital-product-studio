"""Standalone, offline browser personalizer shipped to buyers as a genuinely editable format.

Buyers open the .html file in any modern browser (no account, no install), edit every text
field, see text auto-fit, then Print / Save as PDF at the exact size. Fonts are embedded.
"""
from __future__ import annotations

import html


def build_editor(svg: str, *, title: str, w_in: float | None, h_in: float | None, px: tuple[int, int] | None = None,
                 note: str = "") -> str:
    page_css = (f"@page{{size:{w_in}in {h_in}in;margin:0}}" if w_in else
                f"@page{{size:{px[0]}px {px[1]}px;margin:0}}")
    print_size = (f"width:{w_in}in;height:{h_in}in" if w_in else f"width:{px[0]}px;height:{px[1]}px")
    t = html.escape(title)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Personalize - {t}</title>
<style>
{page_css}
*{{box-sizing:border-box}} body{{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f4f2ee;color:#222}}
header{{padding:14px 20px;background:#fff;border-bottom:1px solid #e5e1da;display:flex;gap:12px;align-items:center;flex-wrap:wrap}}
header h1{{font-size:16px;margin:0;flex:1}}
button{{background:#2f3a30;color:#fff;border:0;border-radius:8px;padding:10px 16px;font-size:14px;cursor:pointer}}
button.secondary{{background:#e9e5de;color:#222}}
main{{display:grid;grid-template-columns:minmax(260px,340px) 1fr;gap:20px;padding:20px}}
@media (max-width:800px){{main{{grid-template-columns:1fr}}}}
.panel{{background:#fff;border-radius:12px;padding:16px;max-height:calc(100vh - 110px);overflow:auto}}
label{{display:block;font-size:12px;color:#666;margin:10px 0 4px}}
input{{width:100%;padding:8px 10px;border:1px solid #d9d4cc;border-radius:6px;font-size:14px}}
.stage{{display:flex;justify-content:center;align-items:flex-start}}
.stage svg{{width:100%;height:auto;max-height:calc(100vh - 110px);box-shadow:0 8px 30px rgba(0,0,0,.15);background:#fff}}
.tip{{font-size:12px;color:#777;line-height:1.5}}
@media print{{header,.panel{{display:none!important}} body{{background:#fff}} main{{display:block;padding:0}}
 .stage svg{{{print_size};max-height:none;box-shadow:none}}}}
</style></head><body>
<header><h1>{t}</h1><button class="secondary" id="reset">Reset text</button><button id="print">Print / Save as PDF</button></header>
<main><div class="panel"><p class="tip">Edit the text below. It updates live and shrinks automatically to fit its space.
When you're done, click <b>Print / Save as PDF</b>, set margins to <b>None</b> and scale to <b>100%</b>.
{html.escape(note)}</p><div id="fields"></div></div>
<div class="stage" id="stage">{svg}</div></main>
<script>
(function(){{
  const svg = document.querySelector('#stage svg');
  const els = [...svg.querySelectorAll('text[data-field]')];
  const box = document.getElementById('fields');
  els.forEach((el, i) => {{
    el.dataset.origSize = el.getAttribute('font-size');
    el.dataset.orig = el.textContent;
    const lab = document.createElement('label'); lab.textContent = el.dataset.field;
    const inp = document.createElement('input'); inp.value = el.dataset.upper ? el.textContent : el.textContent;
    inp.addEventListener('input', () => {{ setText(el, inp.value); }});
    box.appendChild(lab); box.appendChild(inp); el._input = inp;
  }});
  function setText(el, v) {{
    el.textContent = el.dataset.upper ? v.toUpperCase() : v;
    let size = parseFloat(el.dataset.origSize);
    el.setAttribute('font-size', size);
    const max = parseFloat(el.dataset.maxWidth || '0');
    if (max > 0) {{
      let guard = 0;
      while (el.getComputedTextLength() > max && guard++ < 60) {{ size *= 0.97; el.setAttribute('font-size', size.toFixed(2)); }}
    }}
  }}
  document.getElementById('print').onclick = () => window.print();
  document.getElementById('reset').onclick = () => els.forEach(el => {{ setText(el, el.dataset.orig); el._input.value = el.dataset.orig; }});
}})();
</script></body></html>"""
