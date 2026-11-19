"""Shops that describe their products with schema.org JSON-LD on listing pages (Kira Cards, SASOM).

stores.yaml:
  platform: jsonld
  pages: [list of category page URLs]      # read in order, products de-duplicated by link
"""
import html
import json
import re

from ..common import get

LD_RE = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)
KIND_WORDS = ["booster box", "booster bundle", "elite trainer box", "booster pack", "booster", "starter deck",
              "deck", "collection", "tin", "blister", "premium", "half box", "display"]


def _products(o):
    if isinstance(o, list):
        for x in o:
            yield from _products(x)
    elif isinstance(o, dict):
        if o.get("@type") == "Product":
            yield o
        for k in ("itemListElement", "item", "@graph", "mainEntity", "hasVariant"):
            if k in o:
                yield from _products(o[k])


def parse(page_html):
    out = []
    for m in LD_RE.finditer(page_html):
        try:
            data = json.loads(html.unescape(m.group(1)))
        except ValueError:
            continue
        for p in _products(data):
            offers = p.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = offers.get("price", offers.get("lowPrice"))
            if price in (None, ""):
                continue
            avail = str(offers.get("availability", "InStock"))
            name = html.unescape(p.get("name", "")).strip()
            desc = html.unescape(p.get("description") or "")
            img = p.get("image")
            if isinstance(img, list):
                img = img[0] if img else None
            # Some shops name a booster box just "Vivid Voltage"; the description says what it is.
            low = name.lower()
            kind_word = "" if any(w in low for w in KIND_WORDS) else next((w for w in KIND_WORDS if w in desc.lower()), "")
            out.append({
                "title": name + (" (pre-order)" if "PreOrder" in avail else ""),
                "match_title": f"{name} {kind_word}".strip(),
                "price": price,
                "currency": offers.get("priceCurrency"),
                "in_stock": "InStock" in avail or "PreOrder" in avail,
                "url": offers.get("url") or p.get("url"),
                "image": img if isinstance(img, str) else None,
                "product_type": "",
                "tags": ((p.get("brand") or {}).get("name", "") if isinstance(p.get("brand"), dict) else str(p.get("brand") or "")),
                "vendor": "",
                "hint": f"{desc[:300]} {p.get('sku', '')} {offers.get('url') or p.get('url') or ''}",
            })
    return out


def fetch(store):
    out, seen = [], set()
    for url in store.get("pages", []):
        r = get(url, polite_delay=2)
        if not r.ok:
            continue
        for item in parse(r.text):
            if item["url"] and item["url"] not in seen:
                seen.add(item["url"])
                out.append(item)
    return out
