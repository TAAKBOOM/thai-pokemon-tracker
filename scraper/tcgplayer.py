"""TCGplayer prices via tcgcsv.com, a free nightly mirror of TCGplayer's data.

Category 3 = Pokémon (English), 85 = Pokémon Japan. TCGplayer does not list Thai
cards, so Thai listings are compared with the Japanese/English equivalent.
"""
from datetime import datetime, timedelta, timezone

from .common import get, norm

BASE = "https://tcgcsv.com/tcgplayer"
CATEGORIES = {3: "EN", 85: "JP"}


def _ext(product, key):
    for e in product.get("extendedData") or []:
        if e.get("name") == key:
            return e.get("value")
    return None


def fetch(max_age_years=6):
    cutoff = datetime.now(timezone.utc) - timedelta(days=365 * max_age_years)
    out = []
    for cat, lang in CATEGORIES.items():
        groups = get(f"{BASE}/{cat}/groups", polite_delay=0.2).json()["results"]
        for g in groups:
            pub = g.get("publishedOn") or ""
            try:
                if datetime.fromisoformat(pub.replace("Z", "+00:00")).replace(tzinfo=timezone.utc) < cutoff:
                    continue
            except ValueError:
                pass
            gid = g["groupId"]
            prods = get(f"{BASE}/{cat}/{gid}/products", polite_delay=0.2).json().get("results", [])
            prices = get(f"{BASE}/{cat}/{gid}/prices", polite_delay=0.2).json().get("results", [])
            by_id = {}
            for p in prices:
                by_id.setdefault(p["productId"], []).append(p)
            for p in prods:
                number = _ext(p, "Number")
                variants = {
                    pr.get("subTypeName") or "Normal": {
                        "market": pr.get("marketPrice"),
                        "low": pr.get("lowPrice"),
                        "mid": pr.get("midPrice"),
                    }
                    for pr in by_id.get(p["productId"], [])
                }
                out.append(summarise({
                    "id": p["productId"],
                    "name": p.get("name"),
                    "set": g.get("name"),
                    "setAbbr": g.get("abbreviation"),
                    "number": number,
                    "rarity": _ext(p, "Rarity"),
                    "lang": lang,
                    "kind": "single" if number else "sealed",
                    "url": p.get("url"),
                    "img": p.get("imageUrl"),
                    "variants": variants,
                }))
    return out


def summarise(item):
    """Pick a headline market price (prefer Holofoil/Normal over Reverse)."""
    v = item.get("variants") or {}
    order = ["Holofoil", "Normal", "1st Edition Holofoil", "Reverse Holofoil"]
    keys = [k for k in order if k in v] + [k for k in v if k not in order]
    for k in keys:
        if v[k].get("market") or v[k].get("low"):
            item["market"] = v[k].get("market") or v[k].get("mid") or v[k].get("low")
            item["low"] = v[k].get("low")
            item["printing"] = k
            break
    else:
        item["market"] = item["low"] = item["printing"] = None
    item["key"] = norm(item["name"])
    return item
