"""Etsy listing generator: title, description, 13 tags, category, attributes, price, FAQ,
file specs, download instructions, AI disclosure - plus accuracy checks so nothing in the
listing promises something the files don't deliver."""
from __future__ import annotations

import re

from ..scoring.engine import etsy_fees, profit_after_fees

CATEGORY = {
    "wedding_suite": "Paper & Party Supplies > Paper > Invitations & Announcements > Invitations",
    "wall_art_set": "Art & Collectibles > Prints > Digital Prints",
    "business_kit": "Paper & Party Supplies > Paper > Stationery > Design & Templates",
    "budget_planner": "Paper & Party Supplies > Paper > Calendars & Planners",
}

BASE_TAGS = {
    "wedding_suite": ["wedding invitation", "wedding template", "editable invitation", "printable wedding",
                      "wedding bundle", "welcome sign", "seating chart", "wedding menu", "table numbers",
                      "botanical wedding", "greenery wedding", "diy wedding", "thank you card"],
    "wall_art_set": ["printable wall art", "set of 3 prints", "gallery wall set", "boho wall art",
                     "abstract art print", "digital download", "mid century print", "neutral wall decor",
                     "living room art", "printable poster", "modern art print", "minimalist print", "apartment decor"],
    "business_kit": ["price list template", "salon price list", "business flyer", "instagram template",
                     "social media kit", "small business", "marketing bundle", "editable flyer", "lash price list",
                     "beauty salon", "story template", "promo poster", "brand kit"],
    "budget_planner": ["budget planner", "printable planner", "paycheck budget", "monthly budget", "expense tracker",
                       "bill tracker", "savings tracker", "debt payoff", "finance planner", "budget template",
                       "money planner", "budget binder", "a4 planner"],
}

FORBIDDEN_CLAIMS = [
    (r"\bcanva\b", "Mentions Canva, but no Canva template link is included"),
    (r"\bcorjl\b|\btemplett\b", "Mentions an editing platform that isn't provided"),
    (r"\bframed?\b(?! not)", "May imply a physical frame is included"),
    (r"\bhand[- ]?(made|painted|drawn)\b", "Claims handmade/hand-drawn work"),
    (r"\bdisney|marvel|pokemon|sonic|barbie|harry potter\b", "Trademark/IP term"),
]

STYLE_WORDS = {"botanical": "Botanical", "arch": "Modern Arch", "classic": "Classic", "minimal": "Minimalist"}


def _title(parts: list[str], limit: int = 140) -> str:
    out = ""
    for p in parts:
        cand = (out + " | " + p) if out else p
        if len(cand) > limit:
            break
        out = cand
    # Etsy: %, :, & and + may each appear only once in a title
    for ch in "%:&+":
        if out.count(ch) > 1:
            first = out.index(ch)
            out = out[:first + 1] + out[first + 1:].replace(ch, "and" if ch == "&" else "")
    return re.sub(r"\s{2,}", " ", out).strip()


def _tags(candidates: list[str], banned: list[str]) -> list[str]:
    seen, out = set(), []
    for t in candidates:
        t = re.sub(r"[^a-z0-9 '\-]", "", t.lower()).strip()
        if not t or len(t) > 20 or t in seen or any(re.search(b, t) for b in banned):
            continue
        seen.add(t)
        out.append(t)
        if len(out) == 13:
            break
    return out


def generate_listing(*, product: dict, version: dict, opportunity: dict | None, shop: dict,
                     ai_used: bool = False, canva_link: str | None = None) -> dict:
    pt = product["product_type"]
    p = product["params"]
    opp = opportunity or {}
    pieces = version["pieces"]
    keywords = [k.lower() for k in (opp.get("keywords") or [])]
    palette_name = p.get("palette") if isinstance(p.get("palette"), str) else "custom"
    color_words = palette_name.replace("_", " ").title() if palette_name != "custom" else "Custom Color"
    banned = [] if canva_link else [r"\bcanva\b"]
    banned += [r"\bcorjl\b", r"\btemplett\b"]

    if pt == "wedding_suite":
        style = STYLE_WORDS.get(p.get("style", "botanical"), "Elegant")
        title = _title([f"{style} Wedding Invitation Suite Template", "Editable Printable Bundle",
                        "Welcome Sign, Seating Chart, Menu, Table Numbers", f"{color_words} Greenery Wedding",
                        "Instant Download"])
        hook = (f"A complete, coordinated {style.lower()} wedding stationery suite you can personalize in minutes - "
                "right in your web browser, no Canva or paid editor account needed.")
        features = ["Every piece matches: invitation, welcome signs, seating chart, menu, table numbers 1-20 and "
                    "thank-you card", "Edit all wording in the included browser personalizer (works offline)",
                    "Text auto-fits as you type, so long names still look right",
                    "Professional SVG source files for Inkscape / Illustrator / Affinity / Figma",
                    "Print at home, at a local print shop or online"]
        occasion = "Wedding"
    elif pt == "wall_art_set":
        n = len(pieces)
        theme = p.get("theme", "boho").title()
        title = _title([f"Set of {n} {theme} Abstract Printable Wall Art", f"{color_words} Gallery Wall Prints",
                        "Mid Century Modern Decor", "Digital Download", "5 Ratios up to 24x36"])
        hook = (f"A coordinated set of {n} original {theme.lower()} art prints, designed to hang together. "
                "Download, print and frame - styled wall decor in an afternoon.")
        features = [f"{n} original, coordinating artworks", "5 frame ratios for every print (2:3, 3:4, 4:5, 11x14, ISO A)",
                    "High-resolution 300 DPI JPG files, print up to 24x36 in",
                    "Print at home, at a local print shop or with an online print lab", "Instant download"]
        occasion = None
    elif pt == "business_kit":
        ind = p.get("industry", "beauty")
        label = {"beauty": "Salon & Lash", "real_estate": "Real Estate", "boutique": "Boutique"}.get(ind, "Small Business")
        title = _title([f"{label} Marketing Kit Template", "Editable Price List, Flyer, Instagram Post & Story",
                        "Small Business Bundle", f"{color_words} Branding", "Instant Download"])
        hook = (f"Look polished across print and social in one afternoon: a coordinated {label.lower()} marketing kit "
                "with a price list, flyer, promo poster, Instagram post and story and a web banner.")
        features = ["6 coordinated designs for print, social media and web",
                    "Edit every word in the included browser personalizer - no design software needed",
                    "Editable SVG source files (Inkscape, Illustrator, Affinity, Figma)",
                    "Print-ready PDF + PNG, social-ready PNG at native Instagram sizes",
                    "Clearly marked areas for your own photos and branding" if ind == "real_estate"
                    else "Original artwork accents in a cohesive palette"]
        occasion = None
    else:
        title = _title(["Paycheck Budget Planner Printable" if p.get("kind") != "habit" else "Habit Tracker Planner Printable",
                        "Monthly Budget, Bill and Expense Tracker", "Savings and Debt Payoff", "US Letter and A4 PDF",
                        "Instant Download"])
        hook = "A clean, uncluttered printable planner to take control of your money - one paycheck at a time."
        features = [f"{pieces[0]['pages']} printable pages", "US Letter and A4 PDFs included",
                    "Generous writing space and calm, minimal design", "Print as many copies as you need",
                    "Instant download"]
        occasion = None

    # file specifications from what was actually exported
    specs = []
    for pc in pieces:
        fmts = sorted({f["format"].upper() for f in pc["files"]})
        size = (f'{pc["size_in"][0]} x {pc["size_in"][1]} in' if pc["size_in"][0] else
                {"ig_post": "1080 x 1080 px", "ig_story": "1080 x 1920 px", "web_banner": "1640 x 624 px"}.get(pc["key"], ""))
        if pt == "wall_art_set":
            size = "5 ratios, up to 24 x 36 in"
        specs.append(f"{pc['label']}: {size}" + (f", {pc['pages']} pages" if pc["pages"] > 1 else "") +
                     f" ({', '.join(f for f in fmts if f != 'HTML')}{', browser personalizer' if 'HTML' in fmts else ''})")
    deliver = [d["name"] for d in version["deliverables"]]

    ai_text = ("AI DISCLOSURE: Some artwork in this product was created with the help of AI image-generation tools from "
               "our own original prompts, then designed and finished by us." if ai_used else
               "All artwork and layouts are original designs created by us with our own design software. "
               "No AI image generation was used.")
    desc = "\n".join([
        hook, "",
        "THIS IS A DIGITAL DOWNLOAD - no physical item will be shipped.", "",
        "WHAT'S INCLUDED", *[f"- {s}" for s in specs], "",
        "FEATURES", *[f"- {f}" for f in features], "",
        "HOW IT WORKS",
        "1. Purchase and download your files from Etsy (Purchases & Reviews > Download Files).",
        "2. Unzip the folders on a computer.",
        *(["3. Open the _personalize.html file in Chrome, Edge, Safari or Firefox, type your details, then click "
           "Print / Save as PDF."] if any(f["format"] == "html" for pc in pieces for f in pc["files"]) else
          ["3. Open the files and print at 100% / actual size."]),
        "4. Print at home, at a local print shop, or with an online printing service.", "",
        "FILES YOU'LL DOWNLOAD", *[f"- {d}" for d in deliver], "",
        "PLEASE NOTE",
        "- Colors may vary slightly between screens and printers.",
        "- For personal use" + (" or your own business's marketing." if pt == "business_kit" else "."),
        "- Please do not resell or share the files.",
        "- Fonts are included and licensed under the SIL Open Font License (free for commercial use).", "",
        ai_text, "",
        f"Questions? Message {shop.get('shop_name', 'us')} anytime - we're happy to help.",
    ])

    tags = _tags(BASE_TAGS[pt][:6] + keywords + BASE_TAGS[pt][6:] + [color_words.lower()], banned)
    price = float(opp.get("suggested_price") or {"wedding_suite": 24.99, "wall_art_set": 9.99,
                                                  "business_kit": 17.99, "budget_planner": 7.99}[pt])
    offsite = shop.get("offsite_ads_rate", 0.15) if shop.get("include_offsite_ads") else 0.0
    cost = float(product.get("production_cost") or 0)
    faq = [
        {"q": "Will I receive a physical item?", "a": "No - this is a digital download. You'll print it yourself or with a print service."},
        {"q": "What program do I need?", "a": ("Just a web browser for the included personalizer. Designers can also edit the SVG files in Inkscape (free), Illustrator, Affinity or Figma."
                                                if pt in ("wedding_suite", "business_kit") else "Any PDF or image viewer to print.")},
        {"q": "Can I edit it on my phone?", "a": "We recommend a computer for editing and printing; the files can be viewed on any device."},
        {"q": "What paper should I use?", "a": "Heavy matte cardstock (250-300 gsm / 80-110 lb cover) for cards and signs; photo or fine-art paper for wall art."},
        {"q": "Can I get a refund?", "a": "Because files are delivered instantly, we can't offer refunds - but message us and we'll gladly help with any issue."},
        {"q": "Where are my files?", "a": "Etsy: You > Purchases and reviews > Download files. You'll also get an email link."},
    ]
    if pt == "wall_art_set":
        faq.insert(2, {"q": "Which file fits my frame?", "a": "2:3 for 4x6-24x36, 3:4 for 6x8-18x24, 4:5 for 8x10/16x20, 11x14, and ISO for A-sizes. See the size guide image."})

    attributes = {"type": "download", "who_made": "i_did", "is_supply": False,
                  "when_made": "made_to_order (choose the current date range in Etsy if preferred)",
                  "creation_type": "Designed by a seller", "occasion": occasion, "primary_color": color_words,
                  "digital_file_types": sorted({f["format"].upper() for pc in pieces for f in pc["files"]} - {"HTML"}),
                  "personalization": pt in ("wedding_suite", "business_kit")}
    listing = {
        "title": title, "description": desc, "tags": tags, "category": CATEGORY[pt], "attributes": attributes,
        "price": round(price, 2), "fees_per_sale": etsy_fees(price, offsite),
        "profit_per_sale": profit_after_fees(price, cost, offsite),
        "features": features, "file_specs": specs, "download_instructions": desc.split("HOW IT WORKS")[1].split("FILES YOU'LL")[0].strip(),
        "ai_disclosure": ai_text, "ai_used": ai_used, "faq": faq,
        "mockups": version.get("mockups", []), "previews": [pc["preview"] for pc in pieces],
        "deliverables": version["deliverables"], "price_basis": (opp.get("price_range") or {}).get("basis", "default"),
    }
    listing["checks"] = check_listing(listing, canva_link=canva_link)
    return listing


def check_listing(l: dict, canva_link: str | None = None) -> list[dict]:
    issues = []
    if len(l["title"]) > 140:
        issues.append({"severity": "error", "message": f"Title is {len(l['title'])} characters (max 140)"})
    for ch in "%:&+":
        if l["title"].count(ch) > 1:
            issues.append({"severity": "error", "message": f"'{ch}' appears more than once in the title"})
    if len(l["tags"]) != 13:
        issues.append({"severity": "warning", "message": f"{len(l['tags'])} tags (Etsy allows 13 - use them all)"})
    for t in l["tags"]:
        if len(t) > 20:
            issues.append({"severity": "error", "message": f"Tag '{t}' longer than 20 characters"})
    text = (l["title"] + " " + l["description"] + " " + " ".join(l["tags"])).lower()
    for pat, why in FORBIDDEN_CLAIMS:
        if pat == r"\bcanva\b" and canva_link:
            continue
        for m in re.finditer(pat, text):
            ctx = text[max(0, m.start() - 40):m.end() + 40]
            if "no canva" in ctx or "not include" in ctx or "or paid editor" in ctx or "canva or paid" in ctx:
                continue
            if pat.startswith(r"\bframed") and ("frame" in ctx and ("ratio" in ctx or "fits" in ctx or "your frame" in ctx
                                                                   or "frame-size" in ctx or "and frame" in ctx)):
                continue
            issues.append({"severity": "warning", "message": f"Check wording: {why} ('...{ctx.strip()}...')"})
            break
    if "digital download" not in text:
        issues.append({"severity": "error", "message": "Listing must say it is a digital download"})
    if len(l.get("mockups", [])) < 2:
        issues.append({"severity": "warning", "message": "Add at least 2 listing images (Etsy allows up to 20)"})
    for m in l.get("mockups", []):
        if m.get("bytes", 0) > 1_000_000:
            issues.append({"severity": "warning", "message": f"{m['name']} is over 1 MB (Etsy uploads may fail)"})
    return issues
