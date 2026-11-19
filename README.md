# Thai TCG Price Tracker

Search any Pokémon single or sealed product and see every Thai card shop that lists it, its price in baht, and how that compares with TCGplayer.

- **Scraper** (`scraper/`) reads each shop in `stores.yaml`, pulls TCGplayer prices from [tcgcsv.com](https://tcgcsv.com) (a free nightly mirror of TCGplayer data), matches listings to TCGplayer products and writes `site/data/data.json`.
- **Website** (`site/index.html`) is a single static page that loads that JSON: search, singles/sealed filter, sort by best deal, price history sparkline.
- **Automation** (`.github/workflows/update.yml`) checks the shops every 15 minutes and TCGplayer once a day, and republishes the site on GitHub Pages, for free.

## Put it online (about 10 minutes, no server needed)

1. Create a free GitHub account, then a new **public** repository (e.g. `thai-tcg-tracker`).
2. Upload everything in this folder (keep the `.github` folder — on a Mac press `Cmd+Shift+.` to see hidden folders).
3. In the repo: **Settings → Pages → Source: GitHub Actions**.
4. **Actions** tab → "Update prices & deploy site" → **Run workflow**. The first run takes ~10–20 min (it downloads all TCGplayer Pokémon sets).
5. Your site is live at `https://<your-username>.github.io/thai-tcg-tracker/` and refreshes shop prices every 15 minutes (TCGplayer prices once a day).

## Run it on your own computer

```bash
pip install -r requirements.txt
python -m scraper.run            # full run
python -m scraper.run --skip-tcg # re-scrape shops, reuse cached TCGplayer data
cd site && python -m http.server 8000   # open http://localhost:8000
python -m pytest -q              # offline tests
```

## Adding a shop

Add it to `stores.yaml` with `platform: auto`. The scraper detects **Shopify** and **WooCommerce** shops by itself (most Thai TCG web shops use one of the two). For anything else, use `platform: html` and fill in CSS selectors (example in the file; right-click a product on the shop → Inspect to find them). The footer of the site shows which shops updated and which failed.

## How matching works (and its limits)

- **Singles** are matched by card number (e.g. `110/076`) plus name words, with a bonus when the set code (e.g. `M6`) or set name appears in the title.
- **Sealed** products are matched by name similarity.
- **Thai cards:** TCGplayer doesn't list Thai-language cards, so Thai listings are compared with the Japanese (or English) version and labelled as an approximate comparison. Thai sets often combine or renumber Japanese sets, so many Thai singles won't match automatically — fix the important ones in `overrides.yaml`.
- TCGplayer prices are USD and converted to THB daily (open.er-api.com). They exclude shipping and import costs to Thailand.

## Good manners

The scraper identifies itself, waits between requests and runs once a day. Edit the contact email in `scraper/common.py`, check each shop's terms, and remove a shop if it asks. Shopee/Lazada/Facebook-only sellers aren't supported: those sites block scraping and their terms forbid it.
