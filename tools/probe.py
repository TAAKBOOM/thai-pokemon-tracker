"""One-off: look at shop websites and save what we need to write scrapers. Output in probe-out/."""
import json, re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests

UA = {"User-Agent": "Mozilla/5.0 (ThaiTCGTracker probe)"}
OUT = Path("probe-out"); OUT.mkdir(exist_ok=True)
SITES = sys.argv[1:]

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
    for i, l in enumerate(rep["pokemon_links"][:4]):
        x = get(l); (d / f"page{i}.html").write_text(x.text)
    (d / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(json.dumps(rep, ensure_ascii=False)[:1500], flush=True)
