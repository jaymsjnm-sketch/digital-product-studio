# Digital Product Studio

Research Etsy digital-product opportunities, rank them, generate **original** printable products, check their quality automatically, package them for Etsy and write the listings. You review and approve every product. Nothing is published without your approval.

```
Research → Rank → Select → Generate designs → Quality check → Review → Bundle → Listing → Approve → Publish (as an Etsy draft)
```

---

## 1. Start the app (beginner-friendly)

1. Install **Python 3.10 or newer** from https://www.python.org/downloads/. On Windows, tick *"Add Python to PATH"* during setup.
2. Unzip this folder somewhere convenient, such as `Documents/DigitalProductStudio`.
3. Start it:
   - **Mac:** right-click `start.sh` → Open With → Terminal. Alternatively, open Terminal in the folder and run `./start.sh`.
   - **Windows:** double-click `start.bat`.
4. The first start takes a few minutes while it installs its parts, including a private copy of Chromium that it uses to render designs. After that it starts in seconds.
5. Your browser opens at **http://127.0.0.1:8000**. Keep the terminal window open while you use the app.

Your data stays on your computer in the `data/` folder: the database, every generated file and the logs.

## 2. Using the dashboard

| Section | What you do there |
|---|---|
| **Dashboard** | Click **Research Opportunities**. Review the top 5 recommendations and click **Generate Product**. |
| **Market Research** | Browse niches, cited evidence (with links and dates), buyer needs and complaints, and design trends. Import keyword CSVs and add evidence you find yourself. |
| **Opportunity Explorer** | View the top 20 ideas, scored 0-100 with an evidence-confidence score. Filter by niche, profit, competition, ease of production and confidence. Compare up to 3 ideas, then save, dismiss or generate. |
| **Design Studio** | Preview every piece and read the QC report and file checks. Ask for revisions in plain English, try style variations, restore old versions, then approve or reject. |
| **Product Library** | All products, versions and downloadable bundles. |
| **Listing Studio** | Edit the title (140 max), the 13 tags (20 characters max), the description, price (with fees and profit), FAQ and mockups. Approve the listing, then send it to Etsy as a **draft**. |
| **Analytics** | API spend, production costs, product status, and real sales once you import your Etsy orders CSV. |
| **Settings** | Scoring weights, spending limits, the daily schedule, shop settings, quality threshold and credentials status. |

**Revision examples:** "Make this more minimalist", "Change the colors to sage green and cream", "Make the typography more elegant", "Make this suitable for a luxury wedding", "Create five matching products", "More white space", "Bigger text", "Remove the leaves", "New layout", "Set of 5 prints", "Add paper texture".

## 3. What it produces today

| Product type | Pieces | Files for buyers |
|---|---|---|
| **Wedding stationery suite** | Invitation 5x7, welcome signs 24x36 and 18x24, seating chart 24x36 (auto-fit), menu 4x9, table numbers 1-20, thank-you card | Vector PDF, 300 DPI PNG, **editable SVG**, **browser personalizer**, fonts with licences |
| **Printable wall art set** | 3 coordinated original artworks (count adjustable) | 300 DPI JPG in 5 ratios (2:3, 3:4, 4:5, 11x14, ISO A), up to 24x36 in, plus a size guide |
| **Small-business marketing kit** | Flyer, price list, 18x24 promo poster, Instagram post and story, web banner. Industry packs: beauty, real estate, boutique | PDF, PNG, editable SVG, browser personalizer |
| **Printable planner** | 8-page paycheck budget planner, or a habit and focus planner | Multi-page PDF in US Letter and A4 |

Every product also gets listing mockups (2400x1800, under 1 MB each), a `READ_ME_FIRST.pdf` for buyers, a complete organised bundle ZIP, and up to **5 Etsy deliverable files of 20 MB or less** (Etsy's limits).

**Editable formats, described honestly:** the SVG files are editable in Inkscape (free), Illustrator, Affinity and Figma, with the fonts included. The `_personalize.html` file opens in any browser: buyers type their text, it auto-fits, and they print or save it as PDF. No account is needed. PNG and PDF files are print-ready, not editable templates. Listings never mention Canva unless you have actually created a Canva template link. The listing checker enforces this.

**Artwork** is generated from scratch by the app's own code: botanical line work, arches, sun and hills, cut-paper shapes, whimsical florals and holiday motifs. No clip art, stock images or competitor material is used. AI image generation is optional (OpenAI). When a product uses it, the listing automatically includes Etsy's required AI disclosure.

**Fonts:** 21 families are bundled, all under the SIL Open Font License, which allows commercial use and embedding.

## 4. Credentials (all optional)

Copy `.env.example` to `.env` (the start script does this for you), fill in what you have, then restart the app.

### Etsy Open API: live market data and sending drafts
1. Go to https://www.etsy.com/developers/your-apps → **Create a New App**. Choose a *Seller App* for your own shop; these are usually approved fastest.
2. Copy the **Keystring** into `ETSY_API_KEY` and the **Shared secret** into `ETSY_SHARED_SECRET`.
3. In the app settings on Etsy, add the callback URL `http://localhost:8000/api/etsy/oauth/callback`.
4. Restart, then go to **Settings → Connect Etsy shop**. This is needed only for sending drafts.

With the key, research adds per-keyword competing-listing counts, price quartiles, favorites, views, listing ages, top competitor tags (which drive automatic **sub-niche discovery**) and example competitor URLs. Calls are rate-limited and capped per day, and responses are cached for no more than 6 hours, as Etsy's API terms require.

### Other optional services
- `OPENAI_API_KEY`: AI artwork for wall art. Uses the `art_source: "ai"` parameter and is spend-limited. Image models return about 1-2 megapixels, so QC flags any print under 300 DPI. Use AI artwork for small pieces or add upscaling first.
- `ANTHROPIC_API_KEY`: AI web research that discovers new niches, with citations, plus interpretation of free-form revision requests.
- `CANVA_CLIENT_ID` / `CANVA_CLIENT_SECRET`: imports a product PDF into your Canva account as an editable design (Canva Connect Design Import). You then create the template link inside Canva yourself.

### Spending controls
**Settings → Spending limits** sets daily and monthly USD limits (defaults: $2 per day, $20 per month). Every paid call is checked *before* it runs and logged afterwards. Analytics shows usage per provider.

## 5. How research and scoring work (and what they don't claim)

**Sources**, each labelled in the UI:
- `public_web`: curated, dated public evidence gathered on 2026-10-14 from the Etsy Seller Handbook trend report, eRank and EverBee public posts, The Knot, BLS, SBA and NAR. No Etsy pages were scraped.
- `etsy_api`: live Etsy Open API v3 data. Needs a key.
- `csv_import`: exports from keyword tools you subscribe to (eRank, EverBee, Marmalead). Columns: `keyword, searches, competition, ctr, avg_price, niche`. New keywords become discovered niches or sub-niches.
- `claude_web`: optional AI web research with source URLs.
- `user`: evidence you add yourself.

**Score (0-100)** uses weights you can adjust: demand and growth 25%, competition and differentiation 20%, expected profitability 20%, automation feasibility 15%, bundle and personalization 10%, seasonal or long-term 10%. Each factor comes from the best evidence available: live API data, then CSV data, then analyst assessments based on cited sources. The Opportunity Explorer shows which inputs each factor used.

**Evidence confidence (0-100)** goes up with live data, more cited and recent sources, and observed prices. It goes down when prices are assumptions. Every opportunity lists the data that is **unavailable**.

**Honesty rules built in:**
- Favorites, views and rankings are labelled *engagement indicators*, never sales.
- Sales estimates are shown only with live data, as a labelled range with the method (favorites gained per month × an assumed 5-25% favorite-to-purchase ratio).
- Prices with no observation behind them are marked **ASSUMPTION**. They count less in the ranking and lower the confidence score.
- Missing data sources are reported after every research run. The app never fills them with made-up numbers.
- Fees use Etsy's US schedule: $0.20 listing/renewal + 6.5% transaction + 3% + $0.25 processing. Offsite Ads (12-15%) are optional in Settings.

Etsy Marketplace Insights is only available inside Etsy's own Shop Manager and has no public API, so the app does not use it.

## 6. Quality control

After rendering in real Chromium, the app measures every text element and checks for:
- text overflow and clipping, off-page text, print-safe margins
- text overlapping text, and text sitting on top of graphics (by comparing renders with and without text)
- contrast against the actual pixels behind the text (WCAG thresholds)
- spelling, missing glyphs, fonts that are not loaded or not bundled
- tiny type, low-resolution images, visual balance and density
- for files: PDF page size, embedded fonts and page count; PNG/JPG pixel size and DPI; SVG validity; ZIP integrity; Etsy's 5-file and 20 MB limits

Fixable problems are **corrected automatically and re-rendered**, up to 3 rounds by default: text is shrunk to fit, and colour is adjusted for contrast. The QC score is a review aid. **It does not guarantee professional quality**, so always look at the previews.

The current product types include no educational content, so the factual-accuracy check for educational materials is not implemented yet. It is the first item on the roadmap below.

## 7. Automation

**Settings → Scheduled research** runs research every day at a time you choose (the app must be running then). The scheduled run:
1. Researches niches.
2. Ranks opportunities.
3. Recommends the top N, skipping ones you have already produced.
4. Optionally generates up to N draft products per day.
5. Creates listing drafts for your review.

Duplicate designs are blocked by fingerprinting. Products are **never** published automatically.

## 8. Architecture

```
backend/app/
  config.py          env-based settings (no hardcoded secrets), logging
  db.py              SQLAlchemy models (SQLite default, set DATABASE_URL for PostgreSQL)
  services.py        spending limits, cache, rate limiter, HTTP retries/backoff
  jobs.py            persistent background jobs: progress, steps, retry
  scheduler.py       daily automation (APScheduler)
  research/          Etsy API client, evidence sources, niche discovery, concept builder
  scoring/           weighted 0-100 scoring + confidence + Etsy fee math
  design/            styles, fonts, SVG builder, ornaments, generative art, product generators,
                     Chromium renderer, pipeline (export/package), mockups, personalizer, revisions, image-gen
  qc/                layout + file quality checks
  listing/           Etsy listing writer + accuracy checks
  publish/           Etsy OAuth (PKCE) draft publishing, Canva Connect import
  workflow.py        job handlers that orchestrate the workflow
  main.py            REST API + serves the dashboard
frontend/            React (Vite) dashboard source; prebuilt into backend/app/static
```

- Rebuild the dashboard after UI changes: `cd frontend && npm install && npm run build`.
- Run the tests: `cd backend && ../.venv/bin/python -m pytest -q` (use `..\.venv\Scripts\python` on Windows).

## 9. Known limitations and roadmap

- The live Etsy API, OpenAI, Anthropic and Canva integrations follow the official documentation. Their network paths could not be exercised in the build environment, which blocked those hosts. They are covered by unit tests with recorded data; run a research pass after adding your key to confirm them.
- Without an Etsy key, rankings rest on public evidence and labelled assumptions. Confidence scores reflect that.
- Not yet automated: educational worksheets (with answer verification), kids' party invitations, GoodNotes hyperlinked planners, resumes. These appear as *research-only* opportunities.
- The Etsy category is suggested as a text path. Enter the numeric taxonomy id when sending a draft.

*The term "Etsy" is a trademark of Etsy, Inc. This application uses the Etsy API but is not endorsed or certified by Etsy, Inc.*
