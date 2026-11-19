"""Offline tests with fake store + TCGplayer data.  Run: python -m pytest -q"""
import json
from types import SimpleNamespace

from scraper import run
from scraper.adapters import shopify, woocommerce
from scraper.common import card_number, kind, language
from scraper.match import Matcher
from scraper.tcgplayer import summarise

TCG = [summarise(x) for x in [
    {"id": 1, "name": "Mega Rayquaza ex - 110/076", "set": "M6: Storm Emeralda", "setAbbr": "M6", "number": "110/076",
     "rarity": "Special Art Rare", "lang": "JP", "kind": "single", "url": "u1", "img": None,
     "variants": {"Holofoil": {"market": 610.0, "low": 560.0, "mid": 600.0}}},
    {"id": 2, "name": "Raikou ex - 110/076", "set": "Some Other Set", "setAbbr": "SV9", "number": "110/076",
     "rarity": "SAR", "lang": "EN", "kind": "single", "url": "u2", "img": None,
     "variants": {"Holofoil": {"market": 20.0, "low": 18.0, "mid": 19.0}}},
    {"id": 3, "name": "Storm Emeralda Booster Box", "set": "M6: Storm Emeralda", "setAbbr": "M6", "number": None,
     "rarity": None, "lang": "JP", "kind": "sealed", "url": "u3", "img": None,
     "variants": {"Normal": {"market": 180.0, "low": 170.0, "mid": 175.0}}},
    {"id": 4, "name": "Pikachu ex - 057/191", "set": "SV08: Surging Sparks", "setAbbr": "SSP", "number": "057/191",
     "rarity": "Double Rare", "lang": "EN", "kind": "single", "url": "u4", "img": None,
     "variants": {"Holofoil": {"market": 4.5, "low": 4.0, "mid": 4.4}}},
]]

SHOP = {"products": [
    {"title": "Mega Rayquaza ex SAR 110/076 [M6] Storm Emeralda (Japanese)", "handle": "m-ray", "product_type": "Singles JP",
     "tags": ["pokemon"], "images": [{"src": "img"}], "variants": [{"id": 1, "title": "Default Title", "price": "21,500.00", "available": True}]},
    {"title": "Pokemon Storm Emeralda Booster Box Japanese", "handle": "box", "product_type": "Japanese Booster Boxes",
     "tags": [], "images": [], "variants": [{"id": 2, "title": "Default Title", "price": "6500.00", "available": False}]},
    {"title": "Pikachu ex 057/191 English", "handle": "pika", "product_type": "Singles EN", "tags": [],
     "images": [], "variants": [{"id": 3, "title": "NM", "price": "190", "available": True},
                                {"id": 4, "title": "LP", "price": "150", "available": True}]},
    {"title": "MTG Lightning Bolt", "handle": "bolt", "product_type": "Magic", "tags": [], "images": [],
     "variants": [{"id": 5, "title": "Default Title", "price": "100", "available": True}]},
]}


def fake_get(payloads):
    def _get(url, **kw):
        for frag, body in payloads.items():
            if frag in url:
                return SimpleNamespace(ok=True, text=json.dumps(body)[:300], json=lambda b=body: b, status_code=200)
        return SimpleNamespace(ok=False, text="", json=lambda: {}, status_code=404)
    return _get


def test_parsing():
    assert card_number("Mega Rayquaza ex SAR 110/076") == "110/076"
    assert card_number("Pikachu 57/191") == "057/191"
    assert card_number("Mew SVP 053") == "SVP053"
    assert kind("Storm Emeralda Booster Box") == "sealed"
    assert kind("Raikou ex 108/076") == "single"
    assert language("Mega Dream (Japanese)") == "JP"
    assert language("การ์ดโปเกมอน ภาษาไทย") == "TH"


def test_shopify_and_matching(monkeypatch):
    page1 = {"products.json?limit=250&page=1": SHOP}
    monkeypatch.setattr(shopify, "get", fake_get(page1))
    raw = shopify.fetch({"url": "https://shop.example"}, max_pages=2)
    assert len(raw) == 5   # Pikachu has 2 variants

    store = {"name": "Shop", "url": "https://shop.example", "currency": "THB"}
    ls = run.build_listings(store, raw, ["pokemon"], Matcher(TCG), 33.0)
    by_title = {l["title"]: l for l in ls}
    ray = by_title["Mega Rayquaza ex SAR 110/076 [M6] Storm Emeralda (Japanese)"]
    assert ray["tcg_id"] == 1 and ray["match"] == "high" and ray["price_thb"] == 21500.0
    box = by_title["Pokemon Storm Emeralda Booster Box Japanese"]
    assert box["tcg_id"] == 3 and box["in_stock"] is False and box["kind"] == "sealed"
    assert by_title["Pikachu ex 057/191 English - NM"]["tcg_id"] == 4
    assert "MTG Lightning Bolt" not in by_title   # non-Pokémon filtered out

    products = run.group(ls, {i["id"]: i for i in TCG}, 33.0)
    ray_p = next(p for p in products if p["key"] == "tcg:1")
    assert ray_p["tcg"]["market_thb"] == round(610 * 33.0, 2)
    pika = next(p for p in products if p["key"] == "tcg:4")
    assert [l["price_thb"] for l in pika["listings"]] == [150.0, 190.0]


def test_thai_listing_is_approx():
    m = Matcher(TCG)
    item, conf = m.match({"title": "Mega Rayquaza ex 110/076 SAR (Thai)", "lang": "TH", "kind": "single"})
    assert item["id"] == 1 and conf == "approx"


def test_override():
    m = Matcher(TCG, [{"title_contains": "เมก้าเรย์ควาซา", "tcgplayer_id": 1}])
    item, conf = m.match({"title": "เมก้าเรย์ควาซา ex SAR", "lang": "TH", "kind": "single", "url": "x"})
    assert item["id"] == 1 and conf == "manual"


def test_woocommerce(monkeypatch):
    body = [{"name": "Pokemon Mega Dream Booster Box", "prices": {"price": "450000", "currency_minor_unit": 2},
             "is_in_stock": True, "permalink": "p", "images": [], "categories": [{"name": "Pokemon"}], "tags": []}]
    monkeypatch.setattr(woocommerce, "get", fake_get({"page=1": body}))
    raw = woocommerce.fetch({"url": "https://w.example"}, max_pages=2)
    assert raw[0]["price"] == 4500.0


SEALED = [summarise(x) for x in [
    {"id": 20, "name": "Eevee Evolutions Tin [Vaporeon V]", "set": "Tins", "setAbbr": None, "number": None, "rarity": None,
     "lang": "EN", "kind": "sealed", "url": "", "img": None, "variants": {"Normal": {"market": 30.0, "low": 28.0, "mid": 30.0}}},
    {"id": 21, "name": "Eevee Evolutions Tin [Jolteon V]", "set": "Tins", "setAbbr": None, "number": None, "rarity": None,
     "lang": "EN", "kind": "sealed", "url": "", "img": None, "variants": {"Normal": {"market": 31.0, "low": 28.0, "mid": 30.0}}},
    {"id": 22, "name": "Pikachu", "set": "Mini Tins", "setAbbr": None, "number": None, "rarity": None,
     "lang": "EN", "kind": "sealed", "url": "", "img": None, "variants": {"Normal": {"market": 9.0, "low": 8.0, "mid": 9.0}}},
    {"id": 23, "name": "151 Booster Pack", "set": "SV: 151", "setAbbr": "SV2a", "number": None, "rarity": None,
     "lang": "JP", "kind": "sealed", "url": "", "img": None, "variants": {"Normal": {"market": 6.0, "low": 5.0, "mid": 6.0}}},
]]


def test_sealed_variants_stay_separate():
    m = Matcher(SEALED)
    jolt, _ = m.match({"title": "Pokémon TCG: Eevee Evolutions Tin - Jolteon", "lang": "EN", "kind": "sealed"})
    assert jolt and jolt["id"] == 21
    tin, _ = m.match({"title": "Pokémon TCG: Paldea Friends Mini Tins - Pikachu", "lang": "EN", "kind": "sealed"})
    assert tin is None   # a one-word "Pikachu" product must not swallow every tin
    en_pack, _ = m.match({"title": "Pokemon 151 Booster Pack English", "lang": "EN", "kind": "sealed"})
    assert en_pack is None   # English pack must not match the Japanese one
    jp_pack, _ = m.match({"title": "Pokemon 151 JP Booster Pack", "lang": "JP", "kind": "sealed"})
    assert jp_pack and jp_pack["id"] == 23


def test_duplicate_language_pages_and_accessories():
    raw = [
        {"title": "Pack ARs SRs", "price": 162, "url": "https://s/fr/product/pack/"},
        {"title": "Pack ARs SRs", "price": 162, "url": "https://s/en/product/pack/"},
        {"title": "Pokemon Pack Keychain 30th", "price": 300, "url": "https://s/en/product/key/"},
    ]
    ls = run.build_listings({"name": "S", "url": "", "currency": "THB"}, raw, ["pokemon", "pack"], Matcher(TCG), 33.0, ["keychain"])
    assert [l["url"] for l in ls] == ["https://s/en/product/pack/"]


def test_jsonld_shop():
    from scraper.adapters import jsonld
    page = '''<script type="application/ld+json">{"@type":"ItemList","itemListElement":[
      {"@type":"ListItem","item":{"@type":"Product","name":"Vivid Voltage","description":"Pokemon TCG Vivid Voltage Booster Box. 36 packs, English edition.",
       "url":"https://k/en/product/pokemon-en-vivid-voltage","brand":{"name":"Pokémon"},
       "offers":{"price":"5900.00","priceCurrency":"THB","availability":"https://schema.org/InStock"}}},
      {"@type":"ListItem","item":{"@type":"Product","name":"OP-01 Romance Dawn Booster Box","brand":{"name":"One Piece"},
       "offers":{"price":"3000","priceCurrency":"THB","availability":"https://schema.org/OutOfStock","url":"https://k/op"}}}]}</script>'''
    raw = jsonld.parse(page)
    assert raw[0]["match_title"] == "Vivid Voltage booster box" and raw[0]["in_stock"] and not raw[1]["in_stock"]
    ls = run.build_listings({"name": "K", "url": "", "currency": "THB"}, raw, ["pokemon", "pokémon"], Matcher([]), 33.0)
    assert len(ls) == 1 and ls[0]["kind"] == "sealed" and ls[0]["lang"] == "EN"   # One Piece dropped


def test_nextrsc_shop():
    import json as _json
    from scraper.adapters import nextrsc
    payload = 'x:{"product":{"name":"Shadow Rider Calyrex V Box","meta":"Pokemon Sealed","priceValue":2455,"handle":"calyrex-box",' \
              '"link":"/products/calyrex-box","tcgProductId":240977,"categoryId":3,"isSealed":true,"hideVariants":true,' \
              '"variants":[{"id":"1","title":"Sealed","price":2455,"maxQuantity":1,"displayLabel":"NM"}]}}'
    page = f'<script>self.__next_f.push([1,{_json.dumps(payload)}])</script>'
    raw = nextrsc.parse(page, "https://y")
    assert raw[0]["tcg_id_hint"] == 240977 and raw[0]["url"] == "https://y/products/calyrex-box" and raw[0]["lang"] == "EN"
    tcg = [summarise({"id": 240977, "name": "Shadow Rider Calyrex V Box", "set": "SWSH06", "setAbbr": None, "number": None,
                      "rarity": None, "lang": "EN", "kind": "sealed", "url": "", "img": None,
                      "variants": {"Normal": {"market": 70.0, "low": 60.0, "mid": 65.0}}})]
    ls = run.build_listings({"name": "Y", "url": "", "currency": "THB"}, raw, ["pokemon"], Matcher(tcg), 33.0)
    assert ls[0]["tcg_id"] == 240977 and ls[0]["match"] == "high"


def test_language_words():
    assert language("Premium TCG retailer in Phuket, Thailand. English edition.") == "EN"
    assert language("image.jpg booster pack") is None
