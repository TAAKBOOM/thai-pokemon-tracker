"""Match a store listing to its TCGplayer product."""
import re
from collections import defaultdict

from .common import NUMBER_RE, PROMO_RE, card_number, norm

STOP = {"ex", "the", "and", "of", "a", "-", "sv", "m"}


def tokens(text):
    t = NUMBER_RE.sub(" ", text or "")
    t = PROMO_RE.sub(" ", t)
    return [w for w in norm(t).split() if w]


def name_score(listing_title, tcg_name):
    """Share of the TCGplayer name's words that appear in the listing title."""
    want = [w for w in tokens(tcg_name) if w not in STOP] or tokens(tcg_name)
    if not want:
        return 0.0
    have = set(tokens(listing_title))
    return sum(w in have for w in want) / len(want)


def _num_key(n):
    if not n:
        return None
    n = n.upper().replace(" ", "")
    m = re.match(r"^0*(\w+?)/0*(\w+)$", n)
    return f"{m.group(1)}/{m.group(2)}" if m else n.replace("-", "")


class Matcher:
    def __init__(self, tcg_items, overrides=None):
        self.items = {i["id"]: i for i in tcg_items}
        self.by_number = defaultdict(list)
        self.sealed = []
        self.by_token = defaultdict(list)
        for i in tcg_items:
            if i.get("number"):
                self.by_number[_num_key(i["number"])].append(i)
                for w in set(tokens(i["name"])) - STOP:
                    self.by_token[w].append(i)
            else:
                self.sealed.append(i)
        self.overrides = overrides or []

    def _lang_bonus(self, lang, item):
        if lang == item["lang"]:
            return 0.15
        if lang == "TH" and item["lang"] == "JP":   # Thai sets mirror Japanese ones
            return 0.1
        return 0.0

    def _set_bonus(self, title, item):
        t = f" {title.lower()} "
        abbr = (item.get("setAbbr") or "").lower()
        if abbr and re.search(rf"[\s\[\(]{re.escape(abbr)}[\s\]\)a-z]", t):
            return 0.2
        set_words = [w for w in tokens(item.get("set") or "") if len(w) > 3]
        if set_words and all(w in t for w in set_words):
            return 0.2
        return 0.0

    def match(self, listing):
        title = listing["title"]
        for o in self.overrides:
            if o.get("url") == listing.get("url") or (
                o.get("title_contains") and o["title_contains"].lower() in title.lower()
            ):
                item = self.items.get(o["tcgplayer_id"])
                if item:
                    return item, "manual"

        lang = listing.get("lang")
        num = _num_key(card_number(title))
        best, best_score = None, 0.0

        if num:
            for i in self.by_number.get(num, []):
                s = name_score(title, i["name"]) + self._lang_bonus(lang, i) + self._set_bonus(title, i)
                if s > best_score:
                    best, best_score = i, s
            if best and best_score >= 0.75:
                conf = "high" if lang == best["lang"] or (lang is None and best_score >= 1.0) else "approx"
                return best, conf
            return None, None

        pool = self.sealed if listing["kind"] == "sealed" else self._token_pool(title)
        for i in pool:
            s = name_score(title, i["name"]) + self._lang_bonus(lang, i) * 0.5 + self._set_bonus(title, i) * 0.5
            if s > best_score:
                best, best_score = i, s
        threshold = 0.95 if listing["kind"] == "sealed" else 1.05
        if best and best_score >= threshold:
            return best, "medium" if lang == best["lang"] else "approx"
        return None, None

    def _token_pool(self, title):
        seen, pool = set(), []
        for w in set(tokens(title)) - STOP:
            for i in self.by_token.get(w, []):
                if i["id"] not in seen:
                    seen.add(i["id"])
                    pool.append(i)
        return pool
