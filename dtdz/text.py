"""Text helpers shared by the collector and the gate (Arabic-aware)."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_ARABIC_LETTERS = re.compile(r"[؀-ۿ]")

EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿⬀-⯿←-⇿〰〽㊗㊙]"
)
URL = re.compile(r"(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s)\]»]*)?", re.I)
LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+]*(?:[.\-][A-Za-z0-9+]+)*")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")

_STOP = set(
    """the a an and or of to in on for with from by at is are was were be been it its this that
    as how why what new now after over into about you your their they his her has have will just
    more than up out not can could may says said report reports first one two
    في من على إلى الى عن مع أن ان هذا هذه التي الذي كان كانت بعد قبل عبر حول بين او أو ما لا لم لن قد
    كل اول أول جديد جديدة يكشف تكشف يعلن تعلن رسميا رسمياً""".split()
)

TRACKING = ("utm_", "fbclid", "gclid", "ref", "mc_", "ocid", "cmpid")


def norm_ar(s: str) -> str:
    """Normalize Arabic for matching: drop diacritics/tatweel, unify letter forms, digits."""
    s = unicodedata.normalize("NFKC", s)
    s = _DIACRITICS.sub("", s).translate(_ARABIC_DIGITS)
    s = re.sub("[أإآٱ]", "ا", s)
    return s.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")


def is_arabic(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and sum(bool(_ARABIC_LETTERS.match(c)) for c in letters) / len(letters) > 0.4


def tokens(s: str) -> set[str]:
    s = norm_ar(s).lower()
    words = re.findall(r"[\w+]+", s)
    out = set()
    for w in words:
        if w.startswith("ال") and len(w) > 4:  # Arabic definite article
            w = w[2:]
        if len(w) >= 3 and w not in _STOP and not w.isdigit():
            out.add(w)
    return out


def entities(s: str) -> set[str]:
    """Latin proper-noun-ish tokens: product and company names survive translation."""
    found = set()
    for w in LATIN_WORD.findall(s):
        if len(w) >= 2 and (w[0].isupper() or is_arabic(s)) and w.lower() not in _STOP:
            found.add(w.lower())
    return found


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def canon_number(raw: str) -> str:
    """'1,000' / '1000' / '1٬000' -> '1000'; '2.5' stays; '1.000.000' -> '1000000'."""
    raw = raw.translate(_ARABIC_DIGITS).replace("٬", ",").replace("٫", ".")
    if raw.count(".") > 1 or re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):
        raw = raw.replace(".", "")
    raw = raw.replace(",", "")
    if "." in raw:
        raw = raw.rstrip("0").rstrip(".")
    return raw


def numbers(s: str) -> set[str]:
    return {canon_number(n) for n in NUMBER.findall(norm_ar(s))}


def canon_url(url: str) -> str:
    if not url.lower().startswith("http"):
        url = "https://" + url
    p = urlsplit(url.strip())
    q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(TRACKING)]
    host = p.netloc.lower().removeprefix("www.")
    return urlunsplit(("https", host, p.path.rstrip("/") or "/", urlencode(q), ""))


def host(url: str) -> str:
    return urlsplit(canon_url(url)).netloc


def same_site(h: str, allowed: str) -> bool:
    return h == allowed or h.endswith("." + allowed) or allowed.endswith("." + h)
