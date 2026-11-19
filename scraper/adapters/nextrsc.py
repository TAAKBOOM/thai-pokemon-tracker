"""Next.js shops that stream product objects in the page (Yannick The Gathering).

The page carries self.__next_f.push([1,"..."]) chunks; joined, they contain
"product":{...} objects with name, price, variants, stock and often the TCGplayer product ID.

stores.yaml:
  platform: nextrsc
  pages: [collection URLs]      # each followed with ?page=2,3... until no new products
  max_pages: 20
"""
import json
import re
from urllib.parse import urljoin

from ..common import get

PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
LANG = {3: "EN", 85: "JP"}
THAI = re.compile(r"[ก-๙]")


def rsc_text(page_html):
    parts = []
    for m in PUSH_RE.finditer(page_html):
        try:
            parts.append(json.loads(m.group(1)))
        except ValueError:
            pass
    return "".join(parts)


def objects(text, key='"product":{'):
    dec, i = json.JSONDecoder(), 0
    while True:
        i = text.find(key, i)
        if i < 0:
            return
        try:
            obj, end = dec.raw_decode(text, i + len(key) - 1)
            yield obj
            i = end
        except ValueError:
            i += len(key)


def parse(page_html, base):
    out = []
    for p in objects(rsc_text(page_html)):
        meta = (p.get("meta") or "").lower()
        if "pokemon" not in meta and "pokémon" not in meta:
            continue
        lang = LANG.get(p.get("categoryId")) or ("JP" if "japan" in meta else None)
        if not lang and THAI.search(p.get("name") or ""):
            lang = "TH"   # products named in Thai are the Thai-language editions
        sealed = p.get("isSealed") or "sealed" in meta
        link = urljoin(base, p.get("link") or f"/products/{p.get('handle')}")
        variants = p.get("variants") or [{"title": "", "price": p.get("priceValue"), "maxQuantity": p.get("maxQuantity")}]
        for v in variants:
            vt = (v.get("title") or "").strip()
            label = v.get("displayLabel") or v.get("condition") or ""
            # Sealed variants are either "Sealed" or a different product (which deck); single-card
            # variants are condition/finish ("Near Mint - Holofoil"), shown after the name.
            is_choice = sealed and vt and vt not in ("Sealed", "Default Title", label) and not p.get("hideVariants")
            title = p["name"] + (f" - {vt}" if vt and (is_choice or not sealed) else "")
            out.append({
                "title": title,
                "price": v.get("price") if v.get("price") is not None else p.get("priceValue"),
                "in_stock": (v.get("maxQuantity") or 0) > 0,
                "url": link + (f"?variant={v['id']}" if is_choice and v.get("id") else ""),
                "image": p.get("imageUrl"),
                "product_type": "sealed" if sealed else "single",
                "tags": "pokemon",
                "vendor": "",
                "hint": p.get("expansionName") or "",
                "lang": lang,
                "kind": "sealed" if sealed else "single",
                # Only trust the shop's TCGplayer ID when the variant is that product, not a deck choice.
                "tcg_id_hint": None if is_choice else p.get("tcgProductId"),
            })
    return out


def fetch(store):
    out, seen = [], set()
    for url in store.get("pages", []):
        for page in range(1, int(store.get("max_pages", 20)) + 1):
            page_url = url if page == 1 else f"{url}{'&' if '?' in url else '?'}page={page}"
            r = get(page_url, polite_delay=2)
            if not r.ok:
                break
            new = 0
            for item in parse(r.text, store["url"]):
                if item["url"] not in seen:
                    seen.add(item["url"])
                    out.append(item)
                    new += 1
            if new == 0:
                break
    return out
