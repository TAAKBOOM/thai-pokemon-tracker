"""Generic listing-page scraper driven by CSS selectors in stores.yaml."""
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..common import get


def fetch(store):
    sel = store["selectors"]
    out, seen = [], set()
    for pattern in store.get("pages", []):
        for page in range(1, int(store.get("max_pages", 1)) + 1):
            url = pattern.format(page=page)
            r = get(url)
            if not r.ok:
                break
            soup = BeautifulSoup(r.text, "html.parser")
            items = soup.select(sel["item"])
            if not items:
                break
            new = 0
            for it in items:
                t = it.select_one(sel["title"])
                p = it.select_one(sel["price"])
                a = it.select_one(sel.get("link", "a"))
                img = it.select_one(sel.get("image", "img"))
                if not t:
                    continue
                link = urljoin(url, a["href"]) if a and a.get("href") else url
                if link in seen:
                    continue
                seen.add(link)
                new += 1
                out.append({
                    "title": t.get_text(" ", strip=True),
                    "price": p.get_text(" ", strip=True) if p else None,
                    "in_stock": not (sel.get("sold_out") and it.select_one(sel["sold_out"])),
                    "url": link,
                    "image": urljoin(url, img.get("src") or img.get("data-src") or "") if img else None,
                    "product_type": "",
                    "tags": "",
                    "vendor": "",
                })
            if new == 0:
                break
    return out
