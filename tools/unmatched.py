"""Report listings that didn't match TCGplayer, with the closest TCGplayer candidates.

Needs .cache/tcgplayer.json (from a scraper run) and site/data/data.json. Writes probe-out/unmatched.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scraper.match import Matcher, STOP, tokens  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
tcg = json.loads((ROOT / ".cache" / "tcgplayer.json").read_text())
data = json.loads((ROOT / "site" / "data" / "data.json").read_text())
m = Matcher(tcg)

out = []
for p in data["products"]:
    for l in p["listings"]:
        if l.get("tcg_id"):
            continue
        words = set(tokens(l["title"])) - STOP
        pool = m.sealed if l["kind"] == "sealed" else m._token_pool(l["title"])
        if l.get("number"):
            pool = pool + m.by_number.get(l["number"].lstrip("0"), []) + m.by_number.get(l["number"], [])
        scored = []
        for i in pool:
            iw = set(tokens(i["name"])) - STOP
            if not iw:
                continue
            scored.append((len(words & iw) / len(words | iw), i))
        scored.sort(key=lambda x: -x[0])
        out.append({
            "store": l["store"], "title": l["title"], "kind": l["kind"], "lang": l["lang"], "number": l["number"],
            "url": l.get("url"),
            "candidates": [[round(s, 2), i["id"], i["name"], i["set"], i["lang"], i.get("number")] for s, i in scored[:4]],
        })

Path("probe-out").mkdir(exist_ok=True)
Path("probe-out/unmatched.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
# A compact sample of the catalogue for offline work: every sealed product + set names
Path("probe-out/tcg_sealed.json").write_text(json.dumps(
    [{k: i[k] for k in ("id", "name", "set", "setAbbr", "lang")} for i in tcg if i["kind"] == "sealed"], ensure_ascii=False))
Path("probe-out/tcg_sets.json").write_text(json.dumps(sorted({(i["set"], i["setAbbr"], i["lang"]) for i in tcg}), ensure_ascii=False))
print(f"{len(out)} unmatched listings")
