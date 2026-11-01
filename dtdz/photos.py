"""Find the real photo of a story. Runs where publishing runs (GitHub Actions: open internet).

The writer's sandbox often cannot download images, so the writer gives several options and the
publisher picks the first one that is real and sharp. Order:
  1. post["photo"]                     — the writer's first choice
  2. post["photo_candidates"]          — more image URLs of the same story
  3. lead images of official sources   — og:image of trust>=3 pages (company newsroom, agency site)
  4. Wikimedia Commons, post["photo_query"] (English, specific: "Martian meteorite NWA 7034")
  5. lead images of the other sources  — the story's photo in the press article
  6. Wikimedia Commons, a query built from the category/topic (stock exchange, rocket launch…)
Only if all fail does the card fall back to the logo layout. The choice is cached per post, so the
private preview and the channel post show the same image.
"""
from __future__ import annotations

import io
import json
import logging
import re
from pathlib import Path

log = logging.getLogger("dtdz.photos")
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "photos"
MIN_W, MIN_H = 1200, 500
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36")
AGENCY_MARKS = ("getty", "reuters", "apimages", "ap-photo", "afp", "shutterstock", "alamy", "istock",
                "epa-", "dreamstime", "depositphotos")
LOGOISH = re.compile(r"logo|icon|favicon|sprite|avatar|placeholder|default|banner-ad|\.svg", re.I)

# Fallback searches when the writer gave nothing usable (Commons, freely licensed).
CATEGORY_QUERY = {
    "market": "stock exchange trading floor screens",
    "crypto": "bitcoin cryptocurrency coins",
    "space": "observatory night sky milky way",
    "sport": "football stadium night match",
    "film": "cinema theater audience screen",
    "study": "university campus library students",
    "visa": "airport departures board",
    "security": "data center server room",
    "ai": "data center server racks",
    "phone": "smartphone close-up",
    "car": "electric car charging",
    "game": "gaming setup controller",
    "science": "laboratory microscope research",
    "discovery": "laboratory research scientist equipment",
    "course": "laptop online learning desk",
    "free": "video game controller",
}


def _get(url: str, timeout: float = 12):
    import httpx
    from .brands import UA
    for ua in (BROWSER_UA, UA):
        try:
            r = httpx.get(url, timeout=timeout, follow_redirects=True,
                          headers={"User-Agent": ua, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"})
            if r.status_code == 200:
                return r
        except Exception:  # noqa: BLE001
            continue
    return None


def _image(url: str):
    """Download and open an image if it is a real, sharp photo; else None."""
    from PIL import Image
    if not url or url.startswith("data:"):
        return None
    low = url.lower()
    if any(m in low for m in AGENCY_MARKS) or LOGOISH.search(low.split("?")[0].rsplit("/", 1)[-1]):
        return None
    r = _get(url)
    if r is None or not r.headers.get("content-type", "").startswith("image"):
        return None
    try:
        im = Image.open(io.BytesIO(r.content))
        im.load()
        im = im.convert("RGB")
    except Exception:  # noqa: BLE001
        return None
    if im.width < MIN_W or im.height < MIN_H:
        log.info("photo too small %sx%s: %s", im.width, im.height, url[:120])
        return None
    return im


def og_image(page_url: str) -> str | None:
    """Lead image declared by a page (og:image / twitter:image)."""
    r = _get(page_url, timeout=10)
    if r is None:
        return None
    html = r.text[:400_000]
    for pat in (r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
                r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)'):
        m = re.search(pat, html, re.I)
        if m:
            from urllib.parse import urljoin
            return urljoin(str(r.url), m.group(1).replace("&amp;", "&"))
    return None


def commons_search(query: str, limit: int = 12):
    """Best large photo for a query on Wikimedia Commons: biggest landscape JPEG among top results."""
    import httpx
    from .brands import UA
    try:
        r = httpx.get("https://commons.wikimedia.org/w/api.php", timeout=12, headers={"User-Agent": UA},
                      params={"action": "query", "generator": "search", "gsrsearch": f"filetype:bitmap {query}",
                              "gsrnamespace": 6, "gsrlimit": limit, "prop": "imageinfo",
                              "iiprop": "url|size|mime", "iiurlwidth": 1920, "format": "json"})
        pages = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    except Exception as exc:  # noqa: BLE001
        log.warning("commons search failed: %s", exc)
        return None
    ok = []
    for p in pages:
        info = (p.get("imageinfo") or [{}])[0]
        w, h = info.get("width", 0), info.get("height", 0)
        if info.get("mime") != "image/jpeg" or w < 1600 or h < 800 or LOGOISH.search(p.get("title", "")):
            continue
        ok.append((p.get("index", 99), -(w / max(h, 1) >= 1.2), info.get("thumburl") or info["url"]))
    for _, _, url in sorted(ok, key=lambda t: (t[1], t[0]))[:4]:      # landscape first, then relevance
        im = _image(url)
        if im is not None:
            return im, url
    return None


def _source_urls(post: dict, cluster: dict | None, official: bool) -> list[str]:
    out = []
    for s in (cluster or {}).get("sources", []) + (post.get("sources") or []):
        trust = s.get("trust", 2)
        if (trust >= 3) != official:
            continue
        ex = s.get("extra") or {}
        for u in (ex.get("image"), ex.get("page_image")):
            if u:
                out.append(("img", u))
        if s.get("url"):
            out.append(("page", s["url"]))
    if official and cluster and cluster.get("official_image"):
        out.insert(0, ("img", cluster["official_image"]))
    seen, uniq = set(), []
    for kind, u in out:
        if u not in seen:
            seen.add(u)
            uniq.append((kind, u))
    return uniq[:6]


def _from_sources(post, cluster, official):
    for kind, u in _source_urls(post, cluster, official):
        img_url = u if kind == "img" else og_image(u)
        im = _image(img_url) if img_url else None
        if im is not None:
            return im, img_url
    return None


def _fallback_query(post: dict) -> str | None:
    from .brands import detect_topic
    text = (post.get("headline") or "") + "\n" + post.get("text", "")
    cat = post.get("category") or post.get("type")
    if cat in CATEGORY_QUERY and cat not in ("discovery",):
        if cat == "market" and re.search(r"بيتكوين|إيثيريوم|عملات رقمية|كريبتو|بينانس", text):
            return CATEGORY_QUERY["crypto"]
        return CATEGORY_QUERY[cat]
    topic = detect_topic(text, post.get("type", "news"))
    return CATEGORY_QUERY.get(topic) or CATEGORY_QUERY.get(cat)


def resolve(post: dict, cluster: dict | None = None):
    """(PIL image, source url) of the best real photo for this post, or None."""
    from PIL import Image
    CACHE.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"[^A-Za-z0-9_-]+", "-", post.get("id", "x"))
    cached, meta = CACHE / f"post-{key}.jpg", CACHE / f"post-{key}.json"
    if cached.exists() and meta.exists():
        return Image.open(cached).convert("RGB"), json.loads(meta.read_text())["url"]

    from .brands import product_photo
    steps = []
    ph = post.get("photo") or {}
    if ph.get("url"):
        steps.append(lambda: (lambda im: (im, ph["url"]) if im is not None else None)(_image(ph["url"])))
    if ph.get("commons"):
        steps.append(lambda: commons_search(ph["commons"]))
    if ph.get("wiki"):
        steps.append(lambda: (lambda im: (im, "wiki:" + ph["wiki"])
                              if im is not None and im.width >= MIN_W else None)(product_photo(ph["wiki"])))
    for u in post.get("photo_candidates") or []:
        steps.append(lambda u=u: (lambda im: (im, u) if im is not None else None)(_image(u)))
    steps.append(lambda: _from_sources(post, cluster, official=True))
    if post.get("photo_query"):
        steps.append(lambda: commons_search(post["photo_query"]))
    steps.append(lambda: _from_sources(post, cluster, official=False))
    fq = _fallback_query(post)
    if fq:
        steps.append(lambda: commons_search(fq))

    for i, step in enumerate(steps):
        try:
            got = step()
        except Exception as exc:  # noqa: BLE001
            log.warning("photo step %s failed for %s: %s", i, post.get("id"), exc)
            got = None
        if got:
            im, url = got
            im.save(cached, quality=92)
            meta.write_text(json.dumps({"url": url, "step": i}), encoding="utf-8")
            log.info("photo for %s: step %s %s (%sx%s)", post.get("id"), i, url[:100], im.width, im.height)
            return im, url
    log.warning("no real photo found for %s — logo card", post.get("id"))
    return None
