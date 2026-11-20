"""WooCommerce (WordPress) stores expose a public Store API."""
import html
import re

from ..common import get

API = "/wp-json/wc/store/v1/products"
SKU_RE = re.compile(r"^([A-Za-z0-9]+)-(\d{1,3})([a-z]?)-([A-Z]{2})$")   # MA3-086r-TH: set, number, variant, language
LANGS = {"TH": "TH", "JP": "JP", "EN": "EN", "JA": "JP"}
LANG_WORDS = {"thai": "TH", "japan": "JP", "english": "EN", "anglais": "EN", "japonais": "JP"}


def detect(base):
    r = get(f"{base}{API}?per_page=1")
    return r.ok and r.text.strip().startswith("[")


def fetch(store, max_pages=60):
    base = store["url"].rstrip("/")
    out = []
    for page in range(1, max_pages + 1):
        search = f"&search={store['search']}" if store.get("search") else ""
        r = get(f"{base}{API}?per_page=100&page={page}{search}")
        if not r.ok:
            break
        items = r.json()
        if not items:
            break
        for p in items:
            prices = p.get("prices") or {}
            minor = int(prices.get("currency_minor_unit", 2) or 0)
            raw = prices.get("price")
            price = int(raw) / (10 ** minor) if raw not in (None, "") else None
            cats = ", ".join(c.get("name", "") for c in p.get("categories", []))
            tags = ", ".join(t.get("name", "") for t in p.get("tags", []))
            imgs = p.get("images") or []
            sku = p.get("sku") or ""
            attrs = {a.get("name", "").lower(): ", ".join(t.get("name", "") for t in a.get("terms", []))
                     for a in p.get("attributes") or []}
            m = SKU_RE.match(sku)
            serie = attrs.get("serie") or attrs.get("série") or ""
            lang_attr = (attrs.get("language") or attrs.get("langue") or "").lower()
            out.append({
                "num_hint": m.group(2) if m else None,
                "set_hint": serie.split(" - ", 1)[-1] if serie else None,
                "lang": LANGS.get(m.group(4)) if m else next((v for k, v in LANG_WORDS.items() if k in lang_attr), None),
                "currency": prices.get("currency_code"),
                "title": html.unescape(p.get("name", "")),
                "price": price,
                "in_stock": bool(p.get("is_in_stock", True)),
                "url": p.get("permalink"),
                "image": imgs[0].get("src") if imgs else None,
                "product_type": cats,
                "tags": tags,
                "vendor": "",
            })
    return out
