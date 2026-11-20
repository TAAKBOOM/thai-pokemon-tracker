"""Daily job: scrape stores + TCGplayer, match, write site/data/*.json.

Usage:  python -m scraper.run            (full run)
        python -m scraper.run --skip-tcg  (reuse cached TCGplayer data)
"""
import argparse
import json
import re
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import tcgplayer
from .adapters import html, jsonld, nextrsc, shopify, woocommerce
from .common import NUMBER_RE, card_number, get, kind, language, norm, rarity, to_float
from .match import Matcher

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "site" / "data"
CACHE = ROOT / ".cache"
FALLBACK_USD_THB = 33.0
BKK = timezone(timedelta(hours=7))


def usd_thb():
    try:
        r = get("https://open.er-api.com/v6/latest/USD", polite_delay=0)
        return float(r.json()["rates"]["THB"])
    except Exception:
        return FALLBACK_USD_THB


def fetch_store(store):
    platform = store.get("platform", "auto")
    base = store["url"].rstrip("/")
    if platform == "auto":
        if shopify.detect(base):
            platform = "shopify"
        elif woocommerce.detect(base):
            platform = "woocommerce"
        else:
            raise RuntimeError("couldn't detect platform; set platform: html with selectors in stores.yaml")
    adapter = {"shopify": shopify, "woocommerce": woocommerce, "html": html, "jsonld": jsonld, "nextrsc": nextrsc}[platform]
    return adapter.fetch(store), platform


LANG_PATH = re.compile(r"/(fr|de|es|it|ja|zh|ko|th)(/|$)")


def build_listings(store, raw, keywords, matcher, rate, exclude=()):
    out, seen = [], {}
    skip_urls = store.get("exclude_urls", [])
    skip_title = re.compile(store["exclude_title_regex"], re.I) if store.get("exclude_title_regex") else None
    # Multilingual shops list one product once per language page (/en/, /fr/...): keep one, preferring English.
    raw = sorted(raw, key=lambda r: bool(LANG_PATH.search(r.get("url") or "")))
    for r in raw:
        price = to_float(r.get("price"))
        if not price:
            continue
        dup = (r["title"].strip().lower(), price)
        if dup in seen:
            continue
        seen[dup] = True
        hint = r.get("hint") or ""
        blob = f"{r['title']} {r.get('product_type','')} {r.get('tags','')} {r.get('vendor','')} {r.get('url','')} {hint}".lower()
        if any(x in f"{r['title']} {r.get('product_type', '')} {r.get('tags', '')}".lower() for x in exclude):
            continue
        if any(u in (r.get("url") or "") for u in skip_urls) or (skip_title and skip_title.search(r["title"])):
            continue
        listing = {
            "store": store["name"],
            "title": r["title"],
            "url": r.get("url"),
            "image": r.get("image"),
            "in_stock": r.get("in_stock", True),
            "kind": r.get("kind") or ("single" if card_number(r["title"]) or NUMBER_RE.search(hint) or re.search(r"\bpsa\s?\d|\bbgs\b|\bcgc\b|graded", blob)
                                      else kind(r.get("match_title") or r["title"], r.get("product_type", ""), r.get("tags", ""))),
            "lang": r.get("lang") or language(f"{r['title']} {hint}") or language(blob),
            "number": card_number(r["title"]) or (card_number(hint) if NUMBER_RE.search(hint) else None),
            "rarity": rarity(r["title"]),
            "price": price,
            "currency": r.get("currency") or store.get("currency", "THB"),
        }
        listing["_match_title"] = " ".join(filter(None, [r.get("match_title") or r["title"],
                                                         None if card_number(r["title"]) else listing["number"]]))
        listing["_tcg_id_hint"] = r.get("tcg_id_hint")
        listing["price_thb"] = round(price * rate, 2) if listing["currency"] == "USD" else price
        listing["currency"] = listing["currency"].upper()
        item, conf = matcher.match(listing)
        listing["tcg_id"] = item["id"] if item else None
        listing["match"] = conf
        listing.pop("_match_title"); listing.pop("_tcg_id_hint")
        if not keywords or any(k in blob for k in keywords) or conf in ("high", "manual"):
            out.append(listing)
    return out


def group(listings, tcg_by_id, rate):
    groups = {}
    for l in listings:
        key = f"tcg:{l['tcg_id']}" if l["tcg_id"] else f"t:{norm(l['title'])}"
        g = groups.setdefault(key, {"key": key, "listings": []})
        g["listings"].append(l)
    products = []
    for g in groups.values():
        tcg = tcg_by_id.get(g["listings"][0]["tcg_id"]) if g["key"].startswith("tcg:") else None
        first = g["listings"][0]
        g["name"] = tcg["name"] if tcg else first["title"]
        g["kind"] = tcg["kind"] if tcg else first["kind"]
        g["set"] = tcg["set"] if tcg else None
        g["number"] = tcg["number"] if tcg else first["number"]
        g["image"] = (tcg or {}).get("img") or first["image"]
        if tcg:
            g["tcg"] = {k: tcg.get(k) for k in ("id", "name", "set", "number", "rarity", "lang", "url", "market", "low", "printing")}
            if tcg.get("market"):
                g["tcg"]["market_thb"] = round(tcg["market"] * rate, 2)
        g["listings"].sort(key=lambda l: (not l["in_stock"], l["price_thb"]))
        stocked = [l["price_thb"] for l in g["listings"] if l["in_stock"]]
        g["best_thb"] = min(stocked) if stocked else None
        products.append(g)
    products.sort(key=lambda p: (-len(p["listings"]), p["name"]))
    return products


def update_history(products, today):
    path = DATA / "history.json"
    hist = json.loads(path.read_text()) if path.exists() else {}
    for p in products:
        if p["best_thb"] is None:
            continue
        h = hist.setdefault(p["key"], [])
        if h and h[-1][0] == today:
            h[-1] = [today, p["best_thb"], (p.get("tcg") or {}).get("market_thb")]
        else:
            h.append([today, p["best_thb"], (p.get("tcg") or {}).get("market_thb")])
        del h[:-120]   # keep ~4 months
    path.write_text(json.dumps(hist, separators=(",", ":")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-tcg", action="store_true")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "stores.yaml").read_text())
    overrides_path = ROOT / "overrides.yaml"
    overrides = (yaml.safe_load(overrides_path.read_text()) or {}).get("overrides", []) if overrides_path.exists() else []
    keywords = [k.lower() for k in cfg.get("keywords", [])]
    exclude = [k.lower() for k in cfg.get("exclude", [])]
    DATA.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(exist_ok=True)

    tcg_cache = CACHE / "tcgplayer.json"
    if args.skip_tcg and tcg_cache.exists():
        tcg_items = json.loads(tcg_cache.read_text())
    else:
        print("Fetching TCGplayer prices from tcgcsv.com ...", flush=True)
        tcg_items = tcgplayer.fetch()
        tcg_cache.write_text(json.dumps(tcg_items))
    print(f"  {len(tcg_items)} TCGplayer products", flush=True)

    rate = usd_thb()
    matcher = Matcher(tcg_items, overrides)
    all_listings, status = [], []
    today = datetime.now(timezone.utc).astimezone(BKK).date().isoformat()
    for store in cfg["stores"]:
        try:
            daily_file = CACHE / "daily" / f"{re.sub(r'[^a-z0-9]+', '-', store['name'].lower())}.json"
            if store.get("daily") and daily_file.exists():
                saved = json.loads(daily_file.read_text())
                if saved.get("date") == today:
                    # Slow shop: scraped once a day; reuse today's listings in between.
                    ls = saved["listings"]
                    all_listings += ls
                    status.append({"name": store["name"], "url": store["url"], "platform": "daily", "ok": True,
                                   "listings": len(ls), "matched": sum(1 for l in ls if l["tcg_id"])})
                    print(f"  {store['name']}: {len(ls)} listings reused (checked once a day)", flush=True)
                    continue
            raw, platform = fetch_store(store)
            kw = [k.lower() for k in store["keywords"]] if "keywords" in store else keywords
            ex = exclude + [k.lower() for k in store.get("exclude", [])]
            ls = build_listings(store, raw, kw, matcher, rate, ex)
            if store.get("daily"):
                daily_file.parent.mkdir(parents=True, exist_ok=True)
                daily_file.write_text(json.dumps({"date": today, "listings": ls}, ensure_ascii=False))
            all_listings += ls
            status.append({"name": store["name"], "url": store["url"], "platform": platform, "ok": True,
                           "listings": len(ls), "matched": sum(1 for l in ls if l["tcg_id"])})
            print(f"  {store['name']}: {len(ls)} Pokémon listings ({platform})", flush=True)
        except Exception as e:
            traceback.print_exc()
            status.append({"name": store["name"], "url": store["url"], "ok": False, "error": str(e)[:200]})
            print(f"  {store['name']}: FAILED - {e}", file=sys.stderr, flush=True)

    tcg_by_id = {i["id"]: i for i in tcg_items}
    products = group(all_listings, tcg_by_id, rate)
    now = datetime.now(timezone.utc)
    (DATA / "data.json").write_text(json.dumps({
        "updated": now.isoformat(timespec="minutes"),
        "usd_thb": rate,
        "stores": status,
        "products": products,
    }, ensure_ascii=False, separators=(",", ":")))
    update_history(products, now.date().isoformat())
    print(f"Wrote {len(products)} products, {len(all_listings)} listings.")
    if status and not any(s["ok"] for s in status):
        sys.exit(1)


if __name__ == "__main__":
    main()
