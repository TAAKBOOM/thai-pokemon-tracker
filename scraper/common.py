"""Shared helpers: HTTP session, product classification, card-number parsing."""
import re
import time

import requests

UA = "ThaiTCGTracker/1.0 (+price comparison; contact: set-your-email@example.com)"

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept": "application/json,text/html;q=0.9"})


def get(url, polite_delay=1.0, **kw):
    """GET with a polite delay between requests and a couple of retries."""
    for attempt in range(3):
        try:
            r = session.get(url, timeout=30, **kw)
            time.sleep(polite_delay)
            if r.status_code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            return r
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(3)
    return r


SEALED_WORDS = [
    "booster box", "booster pack", "booster bundle", "elite trainer", "etb", "display",
    "collection", "premium", "tin", "starter", "deck", "gift box", "special box",
    "set box", "case", "blister", "bundle", "partner set", "box", "pack",
    "บูสเตอร์", "กล่อง", "ซอง", "เด็ค",
]

NUMBER_RE = re.compile(r"(?<![\d/])([A-Z]{0,4}\d{1,3})\s*/\s*([A-Z]{0,4}-?[A-Z]?\d{1,3}|[A-Z]{1,3}-P)(?![\d])", re.I)
PROMO_RE = re.compile(r"\b(SVP|SWSH|SM|XY|BW)\s?-?(\d{2,3})\b", re.I)

RARITIES = ["MUR", "SAR", "SIR", "UR", "SR", "AR", "IR", "CHR", "CSR", "HR", "RRR", "RR", "ACE", "MA"]

# Whole-word patterns, so "Thailand" isn't read as Thai and ".jpg" isn't read as Japanese.
LANG_HINTS = {
    "TH": [r"\bthai\b", r"ไทย", r"\[th\]", r"\(th\)", r"\bth\)", r"\bthai version\b", r"-th$", r"\bt\]"],
    "JP": [r"\bjapanese\b", r"\bjp\b", r"\bjpn\b", r"ญี่ปุ่น", r"\[jp\]", r"-jp\b"],
    "EN": [r"\benglish\b", r"\ben\b", r"\beng\b", r"อังกฤษ", r"-en-"],
    "CN": [r"\bchinese\b", r"\bs-chinese\b", r"\bt-chinese\b", r"จีน", r"\bcn\b"],
    "KR": [r"\bkorean\b", r"\bkr\b", r"เกาหลี"],
}


def card_number(title):
    """Return a normalised card number like '110/076' or 'SVP-085', else None."""
    m = NUMBER_RE.search(title or "")
    if m:
        a, b = m.group(1).upper(), m.group(2).upper()
        if a.isdigit():
            a = a.zfill(3)
        if b.isdigit():
            b = b.zfill(3)
        return f"{a}/{b}"
    m = PROMO_RE.search(title or "")
    if m:
        return f"{m.group(1).upper()}{m.group(2)}"
    return None


def rarity(title):
    t = f" {(title or '').upper()} "
    for r in RARITIES:
        if re.search(rf"[\s\[\(]{r}[\s\]\),]", t):
            return r
    return None


URL_RE = re.compile(r"https?://\S+")


def language(text):
    # In a link only the product's own name counts: "/en/" in a shop's address isn't the card's language.
    t = URL_RE.sub(lambda m: " " + m.group(0).rstrip("/").rsplit("/", 1)[-1].replace("-", " ") + " ", (text or "").lower())
    for lang, pats in LANG_HINTS.items():
        if any(re.search(p, t) for p in pats):
            return lang
    return None


def kind(title, product_type="", tags=""):
    """'single' or 'sealed'."""
    blob = f"{title} {product_type} {tags}".lower()
    if card_number(title) or "single" in blob or "การ์ดแยก" in blob:
        return "single"
    if any(w in blob for w in SEALED_WORDS):
        return "sealed"
    return "single"


def norm(text, keep_brackets=True):
    """Lower-case, strip punctuation/noise for fuzzy matching.

    Bracketed text is kept by default: in "Eevee Evolutions Tin [Vaporeon V]" it is
    what tells one product from another.
    """
    t = (text or "").lower()
    if not keep_brackets:
        t = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", t)
    t = re.sub(r"pok[eé]mon|tcg|card game|การ์ด|โปเกมอน|japanese|english|thai|ไทย|ญี่ปุ่น", " ", t)
    t = re.sub(r"[^a-z0-9ก-๙ ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def to_float(price):
    if price is None:
        return None
    if isinstance(price, (int, float)):
        return float(price)
    s = re.sub(r"[^\d.,]", "", str(price)).replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None
