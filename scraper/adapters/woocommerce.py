"""WooCommerce (WordPress) stores expose a public Store API."""
import html

from ..common import get

API = "/wp-json/wc/store/v1/products"


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
            out.append({
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
