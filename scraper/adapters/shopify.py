"""Shopify stores expose every product at /products.json (public, paginated)."""
from ..common import get


def detect(base):
    r = get(f"{base}/products.json?limit=1")
    return r.ok and "products" in r.text[:200]


def fetch(store, max_pages=60):
    base = store["url"].rstrip("/")
    out = []
    for page in range(1, max_pages + 1):
        r = get(f"{base}/products.json?limit=250&page={page}")
        if not r.ok:
            break
        products = r.json().get("products", [])
        if not products:
            break
        for p in products:
            img = (p.get("images") or [{}])[0].get("src") if p.get("images") else None
            tags = p.get("tags") or []
            tags = ", ".join(tags) if isinstance(tags, list) else str(tags)
            for v in p.get("variants", []):
                vt = v.get("title") or ""
                title = p["title"] if vt in ("", "Default Title") else f"{p['title']} - {vt}"
                out.append({
                    "title": title,
                    "price": v.get("price"),
                    "in_stock": bool(v.get("available", True)),
                    "url": f"{base}/products/{p['handle']}" + (f"?variant={v['id']}" if vt not in ("", "Default Title") else ""),
                    "image": img,
                    "product_type": p.get("product_type") or "",
                    "tags": tags,
                    "vendor": p.get("vendor") or "",
                })
    return out
