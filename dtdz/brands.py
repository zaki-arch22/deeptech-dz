"""Brand and topic detection for cards.

A post may name its visuals explicitly ("brands": ["binance"], "topic": "security");
otherwise they are detected from the headline and text using Arabic and English names.
Brands without an icon in assets/brands are drawn as a wordmark tile.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .text import norm_ar

ASSETS = Path(__file__).resolve().parent.parent / "assets"

# slug: (display label, [aliases...], fallback hex for brands without an icon)
BRANDS: dict[str, tuple[str, list[str], str | None]] = {
    "binance": ("Binance", ["binance", "بينانس", "باينانس"], None),
    "openai": ("OpenAI", ["openai", "أوبن إيه آي", "اوبن ايه اي", "أوبن أي آي"], "#10A37F"),
    "chatgpt": ("ChatGPT", ["chatgpt", "شات جي بي تي", "تشات جي بي تي", "شات جي بي تي برو"], "#10A37F"),
    "reddit": ("Reddit", ["reddit", "ريديت", "رديت"], None),
    "meta": ("Meta", ["meta", "ميتا"], None),
    "google": ("Google", ["google", "جوجل", "غوغل", "قوقل"], None),
    "googlegemini": ("Gemini", ["gemini", "جيميني", "جيمناي"], None),
    "apple": ("Apple", ["apple", "آبل", "أبل", "ابل"], None),
    "ios": ("iPhone", ["iphone", "ios", "آيفون", "ايفون"], None),
    "microsoft": ("Microsoft", ["microsoft", "مايكروسوفت", "ميكروسوفت"], "#00A4EF"),
    "windows": ("Windows", ["windows", "ويندوز"], "#0078D4"),
    "amazon": ("Amazon", ["amazon", "أمازون", "امازون"], "#FF9900"),
    "samsung": ("Samsung", ["samsung", "galaxy", "سامسونج", "سامسونغ", "جالاكسي", "غالاكسي"], None),
    "whatsapp": ("WhatsApp", ["whatsapp", "واتساب", "واتس آب", "واتس اب"], None),
    "telegram": ("Telegram", ["telegram", "تيليجرام", "تلغرام", "تيليغرام"], None),
    "tiktok": ("TikTok", ["tiktok", "تيك توك", "تيكتوك"], None),
    "youtube": ("YouTube", ["youtube", "يوتيوب"], None),
    "instagram": ("Instagram", ["instagram", "إنستغرام", "انستغرام", "إنستجرام", "انستقرام"], None),
    "facebook": ("Facebook", ["facebook", "فيسبوك", "فايسبوك"], None),
    "x": ("X", ["twitter", "تويتر", "منصة إكس", "منصة اكس"], None),
    "threads": ("Threads", ["threads", "ثريدز"], None),
    "netflix": ("Netflix", ["netflix", "نتفليكس", "نيتفليكس"], None),
    "nvidia": ("NVIDIA", ["nvidia", "إنفيديا", "انفيديا", "نفيديا"], None),
    "tesla": ("Tesla", ["tesla", "تسلا"], None),
    "spacex": ("SpaceX", ["spacex", "سبيس إكس", "سبيس اكس"], None),
    "starlink": ("Starlink", ["starlink", "ستارلينك"], "#FFFFFF"),
    "bitcoin": ("Bitcoin", ["bitcoin", "btc", "بيتكوين", "بتكوين"], None),
    "ethereum": ("Ethereum", ["ethereum", "إيثريوم", "ايثريوم", "إيثيريوم"], None),
    "tether": ("Tether", ["tether", "usdt", "تيثر"], None),
    "solana": ("Solana", ["solana", "سولانا"], None),
    "ton": ("TON", ["toncoin", "تون كوين"], None),
    "coinbase": ("Coinbase", ["coinbase", "كوين بيس", "كوينبيس"], None),
    "bybit": ("Bybit", ["bybit", "باي بت", "بايبت"], "#F7A600"),
    "okx": ("OKX", ["okx"], None),
    "android": ("Android", ["android", "أندرويد", "اندرويد"], None),
    "playstation": ("PlayStation", ["playstation", "ps5", "بلايستيشن", "بلاي ستيشن"], None),
    "xbox": ("Xbox", ["xbox", "إكس بوكس", "اكس بوكس"], "#107C10"),
    "nintendo": ("Nintendo", ["nintendo", "نينتندو"], "#E60012"),
    "steam": ("Steam", ["steam", "ستيم"], None),
    "epicgames": ("Epic Games", ["epic games", "epic", "إيبك", "ايبك"], None),
    "roblox": ("Roblox", ["roblox", "روبلوكس"], None),
    "minecraft": ("Minecraft", ["minecraft", "ماينكرافت"], "#62B47A"),
    "ubisoft": ("Ubisoft", ["ubisoft", "يوبيسوفت"], None),
    "toyota": ("Toyota", ["toyota", "تويوتا"], None),
    "waymo": ("Waymo", ["waymo", "وايمو"], "#00E5C0"),
    "uber": ("Uber", ["uber", "أوبر"], None),
    "anthropic": ("Anthropic", ["anthropic", "أنثروبيك", "انثروبيك"], None),
    "claude": ("Claude", ["claude", "كلود"], None),
    "perplexity": ("Perplexity", ["perplexity", "بيربلكسيتي"], None),
    "deepseek": ("DeepSeek", ["deepseek", "ديب سيك", "ديبسيك"], None),
    "mistralai": ("Mistral", ["mistral", "ميسترال"], None),
    "huggingface": ("Hugging Face", ["hugging face", "huggingface"], None),
    "spotify": ("Spotify", ["spotify", "سبوتيفاي"], None),
    "snapchat": ("Snapchat", ["snapchat", "سناب شات", "سنابشات"], None),
    "discord": ("Discord", ["discord", "ديسكورد"], None),
    "github": ("GitHub", ["github", "جيت هب", "غيت هب"], None),
    "huawei": ("Huawei", ["huawei", "هواوي"], None),
    "xiaomi": ("Xiaomi", ["xiaomi", "شاومي", "شياومي"], None),
    "oneplus": ("OnePlus", ["oneplus", "ون بلس"], None),
    "oppo": ("OPPO", ["oppo", "أوبو", "اوبو"], None),
    "intel": ("Intel", ["intel", "إنتل", "انتل"], None),
    "amd": ("AMD", ["amd"], None),
    "qualcomm": ("Qualcomm", ["qualcomm", "snapdragon", "كوالكوم", "سنابدراغون"], None),
    "googlechrome": ("Chrome", ["chrome", "كروم"], None),
    "firefox": ("Firefox", ["firefox", "فايرفوكس"], None),
    "gmail": ("Gmail", ["gmail", "جيميل"], None),
    "googleplay": ("Google Play", ["google play", "جوجل بلاي", "متجر بلاي"], None),
    "appstore": ("App Store", ["app store", "آب ستور", "اب ستور", "متجر آبل"], None),
    "paypal": ("PayPal", ["paypal", "باي بال", "بايبال"], None),
    "visa": ("Visa", ["visa", "فيزا"], None),
    "mastercard": ("Mastercard", ["mastercard", "ماستركارد"], None),
    "aliexpress": ("AliExpress", ["aliexpress", "علي إكسبريس", "علي اكسبريس"], None),
    "temu": ("Temu", ["temu", "تيمو"], "#FB7701"),
    "shein": ("SHEIN", ["shein", "شي إن", "شي ان"], "#FFFFFF"),
    "twitch": ("Twitch", ["twitch", "تويتش"], None),
    "kick": ("Kick", ["kick.com", "منصة كيك"], None),
    "zoom": ("Zoom", ["zoom", "زوم"], None),
    "notion": ("Notion", ["notion", "نوشن"], None),
    "canva": ("Canva", ["canva", "كانفا"], "#00C4CC"),
    "adobe": ("Adobe", ["adobe", "photoshop", "أدوبي", "ادوبي", "فوتوشوب"], "#FF0000"),
    "capcut": ("CapCut", ["capcut", "كاب كات"], "#FFFFFF"),
    "signal": ("Signal", ["signal app", "تطبيق سيجنال"], None),
    "truecaller": ("Truecaller", ["truecaller", "تروكولر"], "#0087FF"),
    "duolingo": ("Duolingo", ["duolingo", "دولينجو", "دوولينجو"], None),
    "coursera": ("Coursera", ["coursera", "كورسيرا"], None),
    "udemy": ("Udemy", ["udemy", "يوديمي"], None),
    "khanacademy": ("Khan Academy", ["khan academy", "أكاديمية خان"], None),
    "freecodecamp": ("freeCodeCamp", ["freecodecamp"], None),
    "linux": ("Linux", ["linux", "لينكس"], None),
    "ubuntu": ("Ubuntu", ["ubuntu", "أوبونتو", "اوبونتو"], None),
    "sony": ("Sony", ["sony", "سوني"], None),
    "lenovo": ("Lenovo", ["lenovo", "لينوفو"], None),
    "asus": ("ASUS", ["asus", "أسوس", "اسوس"], None),
    "cloudflare": ("Cloudflare", ["cloudflare", "كلاودفلير"], None),
    "docker": ("Docker", ["docker", "دوكر"], None),
    "cursor": ("Cursor", ["cursor"], None),
    "duckduckgo": ("DuckDuckGo", ["duckduckgo"], None),
    "brave": ("Brave", ["brave browser", "متصفح بريف"], None),
    "opera": ("Opera", ["opera browser", "متصفح أوبرا"], None),
    "waze": ("Waze", ["waze", "ويز"], None),
}

# topic: Arabic/English keywords (normalized forms are matched)
TOPICS: dict[str, list[str]] = {
    "security": ["اختراق", "مخترق", "ثغره", "هجوم", "سرقه", "احتيال", "برمجيه خبيثه", "تسريب", "hack", "breach", "malware"],
    "crypto": ["عملات رقميه", "عمله رقميه", "كريبتو", "crypto"],
    "games": ["لعبه", "العاب", "جيمر", "game"],
    "free": ["مجانا", "مجانيه", "مجاني", "free"],
    "ai": ["ذكاء اصطناعي", "نموذج لغوي", " ai "],
    "phones": ["هاتف", "هواتف", "جوال", "smartphone"],
    "cars": ["سياره", "سيارات", "روبوتاكسي", "قياده ذاتيه"],
    "space": ["فضاء", "صاروخ", "قمر صناعي", "مدار"],
    "privacy": ["خصوصيه", "تتبع", "بياناتك"],
    "money": ["مليار دولار", "مليون دولار", "سعر", "اسعار"],
    "course": ["دوره", "دورات", "شهاده", "تعلم"],
    "internet": ["انترنت", "الياف", "شبكه", "5g", "اتصالات"],
    "social": ["منصه", "تواصل اجتماعي", "متابعين"],
    "chip": ["معالج", "رقاقه", "شريحه", "رقائق"],
}
TYPE_TOPIC = {"free": "free", "market": "money", "tool": "tool", "odd": "odd"}
MAX_BRANDS = 2

_meta: dict | None = None


def meta() -> dict:
    global _meta
    if _meta is None:
        p = ASSETS / "brands" / "meta.json"
        _meta = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return _meta


def _alias_re(alias: str) -> re.Pattern:
    a = re.escape(norm_ar(alias).lower())
    # Arabic aliases may carry a prefix (و، ب، ل، ال): allow 0-2 letters before; Latin needs word bounds
    if re.search(r"[a-z]", a):
        return re.compile(rf"(?<![a-z0-9]){a}(?![a-z0-9])")
    return re.compile(rf"(?:(?<=\s)|^|(?<=[وبلف]))(?:ال)?{a}")


_ALIASES = [(slug, _alias_re(al)) for slug, (_, als, _) in BRANDS.items() for al in als]
# a product brand also implies its parent: only show the product
_PARENT = {"chatgpt": "openai", "ios": "apple", "googlegemini": "google", "claude": "anthropic",
           "googleplay": "google", "gmail": "google", "googlechrome": "google", "appstore": "apple",
           "windows": "microsoft", "xbox": "microsoft", "threads": "meta", "instagram": "meta",
           "whatsapp": "meta", "facebook": "meta"}


def detect_brands(text: str, limit: int = MAX_BRANDS) -> list[str]:
    t = " " + norm_ar(text).lower() + " "
    hits: list[tuple[int, str]] = []
    for slug, rx in _ALIASES:
        m = rx.search(t)
        if m and slug not in [s for _, s in hits]:
            hits.append((m.start(), slug))
    found = [s for _, s in sorted(hits)]
    # drop a parent when one of its products is present (ChatGPT beats OpenAI on the card)
    found = [s for s in found if not any(_PARENT.get(o) == s for o in found)]
    return found[:limit]


def detect_topic(text: str, ptype: str) -> str:
    if ptype in TYPE_TOPIC and ptype != "market":
        return TYPE_TOPIC[ptype]
    t = " " + norm_ar(text).lower() + " "
    best, score = "ai", 0
    for topic, kws in TOPICS.items():
        n = sum(t.count(norm_ar(k).lower()) for k in kws)
        if n > score:
            best, score = topic, n
    if ptype == "market":
        return "market_down" if re.search(r"[-−]\d", text) and "+" not in text.split("\n")[0] else "market_up"
    return best


def brand_color(slug: str) -> str:
    m = meta().get(slug)
    if m:
        return "#" + m["hex"]
    fallback = BRANDS.get(slug, ("", [], None))[2]
    return fallback or "#22D3EE"


def brand_icon(slug: str) -> Path | None:
    p = ASSETS / "brands" / f"{slug}.png"
    return p if p.exists() else None


def brand_label(slug: str) -> str:
    return BRANDS.get(slug, (slug.title(), [], None))[0]


def topic_icon(topic: str) -> Path | None:
    p = ASSETS / "topics" / f"{topic}.png"
    return p if p.exists() else None
