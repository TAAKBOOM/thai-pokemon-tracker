"""One-off: look at shop websites and save what we need to write scrapers. Output in probe-out/."""
import json, re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests

UA = {"User-Agent": "Mozilla/5.0 (ThaiTCGTracker probe)"}
OUT = Path("probe-out"); OUT.mkdir(exist_ok=True)
SITES = sys.argv[1:]
sys_extra = {
    "www.vgcardshop.com": ["https://www.vgcardshop.com/category/150/%E0%B9%82%E0%B8%9B%E0%B9%80%E0%B8%81%E0%B8%A1%E0%B8%AD%E0%B8%99-pokemon-union-arena-summoner-eidolon-battle-of-talingchan-eveden-fadalgia/pokemon-%E0%B9%82%E0%B8%9B%E0%B9%80%E0%B8%81%E0%B8%A1%E0%B8%AD%E0%B8%99"],
    "www.kira-cards.com": ["https://www.kira-cards.com/en/pokemon", "https://www.kira-cards.com/en/shop"],
    "yannickthegathering.com": ["https://yannickthegathering.com/pokemon", "https://yannickthegathering.com/shop"],
    "tcgnexus.com": ["https://tcgnexus.com/llms.txt"],
    "thaipkmn.shop": ["https://thaipkmn.shop/wp-json/wc/store/v1/products?per_page=3&search=Lunatone",
                      "https://thaipkmn.shop/wp-json/wc/store/v1/products?per_page=3&search=Zekrom",
                      "https://thaipkmn.shop/en/product/lunatone/", "https://thaipkmn.shop/wp-json/wc/store/v1/products/categories?per_page=100",
                      "https://thaipkmn.shop/wp-json/wc/store/v1/products/attributes"],
    "sasom.co.th": ["https://sasom.co.th/en/shop/trading-card-box-and-pack", "https://sasom.co.th/terms", "https://sasom.co.th/th/terms-and-conditions"],
}

def get(u):
    try:
        r = requests.get(u, headers=UA, timeout=25, allow_redirects=True); time.sleep(1); return r
    except Exception as e:
        return type("R", (), {"status_code": f"ERR {e.__class__.__name__}", "text": "", "url": u, "headers": {}})()

for base in SITES:
    host = urlparse(base).netloc
    d = OUT / host; d.mkdir(exist_ok=True)
    rep = {"base": base}
    r = get(base); rep["home"] = [str(r.status_code), r.url]; (d / "home.html").write_text(r.text)
    t = r.text.lower()
    rep["hints"] = [k for k in ["shopify", "woocommerce", "wp-content", "lnwshop", "wix", "squarespace", "__next", "nuxt", "magento", "opencart", "prestashop", "shopee", "line.me", "weebly", "bigcommerce", "ecwid", "cart", "add to cart", "เพิ่มลงตะกร้า", "ตะกร้า", "฿", "thb"] if k in t]
    for name, path in [("robots", "/robots.txt"), ("shopify", "/products.json?limit=1"), ("woo", "/wp-json/wc/store/v1/products?per_page=1"), ("sitemap", "/sitemap.xml")]:
        x = get(urljoin(base, path)); rep[name] = [str(x.status_code), x.text[:300]]
        (d / f"{name}.txt").write_text(x.text[:200000])
    links = sorted(set(urljoin(r.url, h) for h in re.findall(r'href="([^"#]+)"', r.text)))
    rep["pokemon_links"] = [l for l in links if re.search(r"pok|โปเก", l, re.I) and urlparse(l).netloc.endswith(host.replace("www.", ""))][:25]
    # Sitemaps: collect product/category URLs mentioning Pokémon
    sm_urls, todo, seen = [], [urljoin(base, "/sitemap.xml")], set()
    while todo and len(seen) < 8:
        u = todo.pop(0)
        if u in seen: continue
        seen.add(u); x = get(u)
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", x.text)
        for l in locs:
            (todo if l.endswith(".xml") or "sitemap" in l else sm_urls).append(l)
    (d / "sitemap_urls.txt").write_text("\n".join(sm_urls))
    rep["sitemap_count"] = len(sm_urls)
    pk = [u for u in sm_urls if re.search(r"pok|โปเก|%E0%B9%82%E0%B8%9B%E0%B9%80%E0%B8%81", u, re.I)]
    rep["sitemap_pokemon"] = pk[:15]
    extra = [l for l in sys_extra.get(host, [])]
    for i, l in enumerate(rep["pokemon_links"][:4] + pk[:3] + extra):
        x = get(l); (d / f"page{i}.html").write_text(x.text); rep.setdefault("pages", []).append([l, str(x.status_code), len(x.text)])
    (d / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(json.dumps(rep, ensure_ascii=False)[:1500], flush=True)
