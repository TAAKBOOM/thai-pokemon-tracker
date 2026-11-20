"""Match a store listing to its TCGplayer product."""
import re
from collections import defaultdict

from .common import NUMBER_RE, PROMO_RE, card_number, norm

STOP = {"ex", "the", "and", "of", "a", "-", "sv", "m"}


def tokens(text, keep_brackets=True):
    t = NUMBER_RE.sub(" ", text or "")
    t = PROMO_RE.sub(" ", t)
    return [w for w in norm(t, keep_brackets).split() if w]


# Words that say nothing about which product it is.
NOISE = {"jp", "jpn", "en", "eng", "th", "sealed", "new", "version", "ver", "official", "authentic",
         "japan", "lang", "language", "nm", "near", "mint", "s"}


FOLD = {"tins": "tin", "boosters": "booster", "packs": "pack", "boxes": "box", "decks": "deck", "festival": "fest",
        "collections": "collection", "blisters": "blister", "bundles": "bundle", "gyrados": "gyarados",
        "etb": "elite", "pokemon": "", "pokémon": "", "tcg": "", "random": "", "lgs": "", "retail": "", "art": "", "card": "", "cards": ""}
SERIES = {"mega", "evolution", "scarlet", "violet", "sword", "shield", "sun", "moon"}
SET_CODE = re.compile(r"^(?=.*\d)[a-z]{1,4}\d{1,3}[a-z]?$")   # m6a, sv8a, me05, swsh12


def _sealed_words(text):
    words = set()
    for w in tokens(text):
        w = FOLD.get(w, w)
        if w and w not in STOP and w not in NOISE:
            words.add(w)
    if "elite" in words:
        words |= {"trainer"}
    return words


def sealed_score(listing_title, tcg_name):
    """How well a shop's sealed product name fits a TCGplayer one.

    Two-way overlap (F1), so a one-word "Pikachu" doesn't match every tin, plus credit when every
    word the shop wrote appears in the TCGplayer name ("Mini Tins - Fuecoco" vs "Mini Tin [Fuecoco & Smoliv]").
    """
    a = {w for w in _sealed_words(listing_title) if not SET_CODE.match(w)}
    b = _sealed_words(tcg_name)
    if not a or not b:
        return 0.0
    best = _fit(a, b)
    # "Mega Evolution Phantasmal Flames" is the Phantasmal Flames set: try without the series name
    if (a & SERIES) and len(a - SERIES) >= 2 and not (b & SERIES):
        best = max(best, _fit(a - SERIES, b))
    return best


def _fit(a, b):
    both = len(a & b)
    f1 = 2 * both / (len(a) + len(b))
    contained = both / len(a)
    if contained == 1 and len(a) >= 3:
        return max(f1, 0.8 + 0.2 * f1)
    return f1


def name_score(listing_title, tcg_name):
    """Share of the TCGplayer name's words that appear in the listing title."""
    # Brackets in a TCGplayer card name are notes like "(Secret)", not required words.
    want = [w for w in tokens(tcg_name, False) if w not in STOP] or tokens(tcg_name, False)
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
                for w in set(tokens(i["name"], False)) - STOP:
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
        title = listing.get("_match_title") or listing["title"]
        hinted = self.items.get(listing.get("_tcg_id_hint"))
        if hinted:   # the shop told us the exact TCGplayer product
            return hinted, "high"
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

        if listing["kind"] == "sealed":
            for i in self.sealed:
                # Sealed products differ by language (an English and a Japanese 151 pack are different things).
                if lang and lang != i["lang"]:
                    continue
                s = sealed_score(title, i["name"]) + self._set_bonus(title, i) * 0.25
                if s > best_score:
                    best, best_score = i, s
            if best and best_score >= 0.8:
                return best, "medium"
            return None, None

        for i in self._token_pool(title):
            s = name_score(title, i["name"]) + self._lang_bonus(lang, i) * 0.5 + self._set_bonus(title, i) * 0.5
            if s > best_score:
                best, best_score = i, s
        if best and best_score >= 1.05:
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
