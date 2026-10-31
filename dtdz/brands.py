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
    "hbomax": ("HBO Max", ["hbo max", "hbo", "إتش بي أو"], "#991EEB"),
    "shahid": ("Shahid", ["shahid", "شاهد في آي بي", "منصة شاهد"], "#00C389"),
    "disneyplus": ("Disney+", ["disney+", "ديزني بلس"], "#113CCF"),
    "primevideo": ("Prime Video", ["prime video", "برايم فيديو"], "#1A98FF"),
    "osn": ("OSN+", ["osn+", "osn"], "#E4007C"),
    "bein": ("beIN SPORTS", ["bein", "بي إن سبورت", "بي ان سبورت"], "#5C2D91"),
    "realmadrid": ("Real Madrid", ["real madrid", "ريال مدريد"], "#FEBE10"),
    "fcbarcelona": ("FC Barcelona", ["barcelona", "برشلونة"], "#A50044"),
    "fifa": ("FIFA", ["fifa", "فيفا"], "#326295"),
    "caf": ("CAF", ["الاتحاد الأفريقي لكرة القدم", "كاف"], "#00843D"),
    "faf": ("FAF", ["المنتخب الجزائري", "الخضر", "الاتحادية الجزائرية لكرة القدم"], "#006233"),
    "premierleague": ("Premier League", ["premier league", "الدوري الإنجليزي"], "#3D195B"),
    "uefa": ("UEFA", ["uefa", "دوري أبطال أوروبا", "الاتحاد الأوروبي لكرة القدم"], "#00004B"),
    "nasa": ("NASA", ["nasa", "ناسا"], "#E03C31"),
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
# official site per brand: used to fetch the real, full-colour logo on the PC (cached in data/logos)
DOMAINS = {
    "binance": "binance.com", "openai": "openai.com", "chatgpt": "chatgpt.com", "reddit": "reddit.com",
    "meta": "meta.com", "google": "google.com", "googlegemini": "gemini.google.com", "apple": "apple.com",
    "ios": "apple.com", "microsoft": "microsoft.com", "windows": "microsoft.com", "amazon": "amazon.com",
    "samsung": "samsung.com", "whatsapp": "whatsapp.com", "telegram": "telegram.org", "tiktok": "tiktok.com",
    "youtube": "youtube.com", "instagram": "instagram.com", "facebook": "facebook.com", "x": "x.com",
    "threads": "threads.net", "netflix": "netflix.com", "nvidia": "nvidia.com", "tesla": "tesla.com",
    "spacex": "spacex.com", "starlink": "starlink.com", "bitcoin": "bitcoin.org", "ethereum": "ethereum.org",
    "tether": "tether.to", "solana": "solana.com", "ton": "ton.org", "coinbase": "coinbase.com",
    "bybit": "bybit.com", "okx": "okx.com", "android": "android.com", "playstation": "playstation.com",
    "xbox": "xbox.com", "nintendo": "nintendo.com", "steam": "store.steampowered.com",
    "epicgames": "epicgames.com", "roblox": "roblox.com", "minecraft": "minecraft.net", "ubisoft": "ubisoft.com",
    "toyota": "toyota.com", "waymo": "waymo.com", "uber": "uber.com", "anthropic": "anthropic.com",
    "claude": "claude.ai", "perplexity": "perplexity.ai", "deepseek": "deepseek.com", "mistralai": "mistral.ai",
    "huggingface": "huggingface.co", "spotify": "spotify.com", "snapchat": "snapchat.com",
    "discord": "discord.com", "github": "github.com", "huawei": "huawei.com", "xiaomi": "mi.com",
    "oneplus": "oneplus.com", "oppo": "oppo.com", "intel": "intel.com", "amd": "amd.com",
    "qualcomm": "qualcomm.com", "googlechrome": "google.com/chrome", "firefox": "firefox.com",
    "gmail": "mail.google.com", "googleplay": "play.google.com", "appstore": "apps.apple.com",
    "paypal": "paypal.com", "visa": "visa.com", "mastercard": "mastercard.com", "aliexpress": "aliexpress.com",
    "temu": "temu.com", "shein": "shein.com", "twitch": "twitch.tv", "kick": "kick.com", "zoom": "zoom.us",
    "notion": "notion.so", "canva": "canva.com", "adobe": "adobe.com", "capcut": "capcut.com",
    "signal": "signal.org", "truecaller": "truecaller.com", "duolingo": "duolingo.com",
    "coursera": "coursera.org", "udemy": "udemy.com", "khanacademy": "khanacademy.org",
    "freecodecamp": "freecodecamp.org", "linux": "kernel.org", "ubuntu": "ubuntu.com", "sony": "sony.com",
    "lenovo": "lenovo.com", "asus": "asus.com", "cloudflare": "cloudflare.com", "docker": "docker.com",
    "cursor": "cursor.com", "duckduckgo": "duckduckgo.com", "brave": "brave.com", "opera": "opera.com",
    "waze": "waze.com", "hbomax": "hbomax.com", "shahid": "shahid.mbc.net", "disneyplus": "disneyplus.com",
    "primevideo": "primevideo.com", "osn": "osnplus.com", "bein": "beinsports.com", "realmadrid": "realmadrid.com",
    "fcbarcelona": "fcbarcelona.com", "fifa": "fifa.com", "caf": "cafonline.com", "faf": "faf.dz",
    "premierleague": "premierleague.com", "uefa": "uefa.com", "nasa": "nasa.gov",
}

TYPE_TOPIC = {"free": "free", "market": "money", "tool": "tool", "odd": "odd", "film": "video",
              "sport": "games", "discovery": "space", "app": "apps", "site": "internet"}
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


# ---------- real logos ----------
LOGO_CACHE = ASSETS.parent / "data" / "logos"
# Wikimedia requires a descriptive User-Agent with contact info, otherwise images return 403
UA = "DeeptechDZBot/1.0 (https://t.me/DeeptechDZ; Telegram tech channel) httpx"
GOOD_SIZE = 128


def _fetch(url: str):
    """Download an image; None on any failure. Kept tiny so a slow site never blocks publishing."""
    try:
        import io
        import httpx
        from PIL import Image
        r = httpx.get(url, timeout=10, follow_redirects=True, headers={"User-Agent": UA})
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image"):
            return None
        return Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception:  # noqa: BLE001
        return None


def _wiki_logo(title: str):
    try:
        import httpx
        r = httpx.get("https://en.wikipedia.org/w/api.php", timeout=8, params={
            "action": "query", "titles": title, "prop": "pageimages", "piprop": "thumbnail",
            "pithumbsize": 400, "format": "json", "redirects": 1})
        for page in r.json()["query"]["pages"].values():
            src = (page.get("thumbnail") or {}).get("source")
            if src:
                return _fetch(src)
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("dtdz.photos").warning("photo lookup failed: %s", exc)
        return None
    return None


def real_logo(key: str, domain: str | None, wiki: str | None = None):
    """Best available original logo as RGBA, cached on disk. Order: big site icon, Wikipedia logo,
    then a small site icon. Returns None when nothing could be fetched (offline)."""
    from PIL import Image
    LOGO_CACHE.mkdir(parents=True, exist_ok=True)
    cached = LOGO_CACHE / f"{key}.png"
    miss = LOGO_CACHE / f"{key}.miss"
    if cached.exists():
        return Image.open(cached).convert("RGBA")
    if miss.exists() and miss.stat().st_mtime > __import__("time").time() - 86400:
        return None
    small = None
    candidates = []
    if domain:
        candidates.append(lambda: _fetch(f"https://www.google.com/s2/favicons?domain={domain}&sz=256"))
        candidates.append(lambda: _fetch(f"https://{domain.split('/')[0]}/apple-touch-icon.png"))
    if wiki:
        candidates.append(lambda: _wiki_logo(wiki))
    for get in candidates:
        im = get()
        if im is None:
            continue
        if min(im.size) >= GOOD_SIZE:
            im.save(cached)
            return im
        if small is None or min(im.size) > min(small.size):
            small = im
    if small is not None and min(small.size) >= 32:
        small.save(cached)
        return small
    miss.touch()
    return None


def logo_specs(post: dict, text: str) -> list[dict]:
    """What the card should show: explicit `logos` first, then `brands`, then detected brands."""
    specs = []
    for lg in post.get("logos") or []:
        name = lg.get("name") or lg.get("domain", "")
        specs.append({"key": re.sub(r"[^a-z0-9]+", "-", (lg.get("domain") or name).lower()).strip("-"),
                      "label": name, "domain": lg.get("domain"), "wiki": lg.get("wiki"), "slug": lg.get("slug")})
    for slug in post.get("brands") or detect_brands(text):
        if len(specs) >= MAX_BRANDS:
            break
        if any(s.get("slug") == slug for s in specs):
            continue
        specs.append({"key": slug, "label": brand_label(slug), "domain": DOMAINS.get(slug),
                      "wiki": brand_label(slug), "slug": slug})
    return specs[:MAX_BRANDS]


# ---------- product photos (optional, creative touch) ----------
PHOTO_CACHE = ASSETS.parent / "data" / "photos"


def photo_for(spec: dict):
    """spec = {"wiki": title} or {"url": direct image url (Wikimedia or an official newsroom)}."""
    if spec.get("url"):
        from PIL import Image
        key = re.sub(r"[^a-z0-9]+", "-", spec["url"].lower())[-80:].strip("-")
        PHOTO_CACHE.mkdir(parents=True, exist_ok=True)
        cached = PHOTO_CACHE / f"{key}.jpg"
        if cached.exists():
            return Image.open(cached).convert("RGB")
        im = _fetch(spec["url"])
        if im is not None and min(im.size) >= 300:
            im = im.convert("RGB")
            im.save(cached, quality=90)
            return im
        return None
    if spec.get("commons"):
        return commons_photo(spec["commons"])
    return product_photo(spec["wiki"]) if spec.get("wiki") else None


def commons_photo(query: str):
    """First good photo for a search on Wikimedia Commons (freely licensed media)."""
    from PIL import Image
    key = "c-" + re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
    PHOTO_CACHE.mkdir(parents=True, exist_ok=True)
    cached = PHOTO_CACHE / f"{key}.jpg"
    if cached.exists():
        return Image.open(cached).convert("RGB")
    try:
        import httpx
        r = httpx.get("https://commons.wikimedia.org/w/api.php", timeout=10, headers={"User-Agent": UA},
                      params={"action": "query", "generator": "search", "gsrsearch": f"filetype:bitmap {query}",
                              "gsrnamespace": 6, "gsrlimit": 10, "prop": "imageinfo", "iiprop": "url|size|mime",
                              "iiurlwidth": 1200, "format": "json"})
        pages = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
        for page in pages:
            info = (page.get("imageinfo") or [{}])[0]
            if info.get("mime") not in ("image/jpeg", "image/png") or info.get("width", 0) < 800:
                continue
            im = _fetch(info.get("thumburl") or info["url"])
            if im is not None and min(im.size) >= 300:
                im = im.convert("RGB")
                im.save(cached, quality=90)
                return im
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("dtdz.photos").warning("photo lookup failed: %s", exc)
        return None
    return None


def product_photo(wiki_title: str):
    """Lead image of an English Wikipedia article (products, devices, vehicles, places — never people).
    Wikipedia/Wikimedia lead images are freely licensed; the card credits the source."""
    from PIL import Image
    key = re.sub(r"[^a-z0-9]+", "-", wiki_title.lower()).strip("-")
    PHOTO_CACHE.mkdir(parents=True, exist_ok=True)
    cached = PHOTO_CACHE / f"{key}.jpg"
    if cached.exists():
        return Image.open(cached).convert("RGB")
    try:
        import httpx
        r = httpx.get("https://en.wikipedia.org/w/api.php", timeout=8, headers={"User-Agent": UA},
                      params={"action": "query", "titles": wiki_title, "prop": "pageimages", "piprop": "thumbnail",
                              "pithumbsize": 1200, "format": "json", "redirects": 1})
        for page in r.json()["query"]["pages"].values():
            src = (page.get("thumbnail") or {}).get("source")
            if src and not src.lower().endswith(".svg.png"):     # skip logos/diagrams, want a photo
                im = _fetch(src)
                if im is not None and min(im.size) >= 300:
                    im = im.convert("RGB")
                    im.save(cached, quality=90)
                    return im
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("dtdz.photos").warning("photo lookup failed: %s", exc)
        return None
    return None
