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
              "deck", "collection", "tin", "blister", "half box", "display"]
# Product web addresses are the most reliable clue: ".../pokemon-me06-delta-reign-half-booster-box"
SLUG_KINDS = [("elite-trainer-box", "elite trainer box"), ("booster-bundle", "booster bundle"), ("booster-box", "booster box"),
              ("booster-pack", "booster pack"), ("blister", "blister"), ("collection", "collection"), ("tin", "tin"),
              ("deck", "deck"), ("display", "booster box"), ("box", "booster box"), ("booster", "booster pack"),
              ("pack", "booster pack")]
SINGLE_SLUG = re.compile(r"-\d{1,3}(-[a-z-]+)?$|\b(svp|swsh|sm|xy)-?\d{2,3}\b|\bpsa-?\d|graded")


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


PAGE_KINDS = [("elite-trainer", "elite trainer box"), ("booster-box", "booster box"), ("booster-pack", "booster pack"),
              ("booster-bundle", "booster bundle"), ("tins", "tin")]


def parse(page_html, page_url=""):
    page_kind = next((k for slug, k in PAGE_KINDS if slug in page_url), "")
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
            link = offers.get("url") or p.get("url") or ""
            slug = link.rstrip("/").rsplit("/", 1)[-1].lower()
            slug_kind = next((k for part, k in SLUG_KINDS if re.search(rf"(^|-){part}(-|$)", slug)), "")
            is_single = not slug_kind and bool(SINGLE_SLUG.search(slug))
            # Clue order: product address, then the shop's category page, then the description.
            kind_word = "" if any(w in low for w in KIND_WORDS) or is_single else (
                slug_kind or page_kind or next((w for w in KIND_WORDS if w in desc.lower()), ""))
            num_hint = set_hint = None
            match_title = None
            if is_single:
                words = [w for w in slug.split("-") if w not in ("pokemon", "en", "jp", "th")]
                name_words = set(re.sub(r"[^a-z0-9]+", " ", name.lower()).split())
                full_number = None
                if len(words) >= 2 and words[-1].isdigit() and words[-2].isdigit():
                    total, n = words.pop(), words.pop()        # "...-paf-215-091": card 215 of 091
                    full_number = f"{n}/{total}"
                elif words and words[-1].isdigit():
                    num_hint = words.pop()                      # "...-paldea-evolved-237": card 237
                rest = [w for w in words if w not in name_words and w not in ("single", "graded")]
                set_hint = " ".join(rest) or None
                if full_number:
                    match_title = f"{name} {full_number} {set_hint or ''}".strip()
            out.append({
                "num_hint": num_hint,
                "set_hint": set_hint,
                "title": name + (" (pre-order)" if "PreOrder" in avail else ""),
                "match_title": match_title or f"{name} {kind_word}".strip(),
                "price": price,
                "currency": offers.get("priceCurrency"),
                "in_stock": "InStock" in avail or "PreOrder" in avail,
                "url": link or None,
                "image": img if isinstance(img, str) else None,
                "product_type": "",
                "tags": ((p.get("brand") or {}).get("name", "") if isinstance(p.get("brand"), dict) else str(p.get("brand") or "")),
                "vendor": "",
                "hint": f"{desc[:300]} {p.get('sku', '')} {link}",
                "kind": "single" if is_single else ("sealed" if kind_word else None),
            })
    return out


def fetch(store):
    out, seen = [], set()
    for url in store.get("pages", []):
        r = get(url, polite_delay=2)
        if not r.ok:
            continue
        for item in parse(r.text, url):
            if item["url"] and item["url"] not in seen:
                seen.add(item["url"])
                out.append(item)
    return out
