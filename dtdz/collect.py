"""Collector: pulls every enabled source, stores new items, records source health.

Article pages are fetched only to give the writer verifiable facts. The writer never
copies them: the gate rejects any long verbatim overlap with source text.
"""
from __future__ import annotations

import asyncio
import calendar
import csv
import io
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import httpx
import trafilatura
import yaml

from .store import Item, Store
from .text import canon_url, is_arabic

log = logging.getLogger("dtdz.collect")

UA = "Mozilla/5.0 (compatible; DeeptechDZ/1.0; +https://t.me/)"
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0 Safari/537.36",
           "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
           "Accept-Language": "en-US,en;q=0.9,fr;q=0.8,ar;q=0.7"}
TEMPORARY = (429, 500, 502, 503, 504, 520, 521, 522, 524)   # site busy / rate limit: try again later
RETRY_DISABLED_H = 24   # a disabled source is tried again once a day
MAX_AGE_H = 36
PER_FEED = 15
MIN_TEXT = 700          # shorter feed content -> fetch the article page
MAX_TEXT = 12000
ARTICLE_FETCHES = 60    # per run
DISABLE_AFTER = 3       # consecutive failures before a verify:true source is disabled


def load_sources(path: str | Path) -> list[dict]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    out = []
    for grp, entries in data.items():
        for s in entries or []:
            if s.get("enabled", True):
                out.append({**s, "grp": grp, "parser": s.get("parser", "rss")})
    return out


def _ts(struct) -> float | None:
    return calendar.timegm(struct) if struct else None


def _iso(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        try:
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            return None


def _clean(html: str) -> str:
    return (trafilatura.extract(f"<html><body>{html}</body></html>") or "").strip() if html else ""


# ---------- parsers: body -> list[Item] ----------

def parse_rss(src: dict, body: bytes, now: float) -> list[Item]:
    feed = feedparser.parse(body)
    if feed.bozo and not feed.entries:
        raise ValueError(f"not a feed: {feed.bozo_exception}")
    items = []
    for e in feed.entries[:src.get("per_feed", PER_FEED)]:
        url = e.get("link")
        title = (e.get("title") or "").strip()
        if not url or not title:
            continue
        published = _ts(e.get("published_parsed") or e.get("updated_parsed")) or now
        if now - published > MAX_AGE_H * 3600:
            continue
        content = ""
        if e.get("content"):
            content = _clean(e.content[0].get("value", ""))
        if len(content) < MIN_TEXT:
            content = max(content, _clean(e.get("summary", "")), key=len)
        extra = {}
        if src.get("trust", 0) >= 3:          # official sources: keep their own press image
            img = None
            for m in (e.get("media_content") or []) + (e.get("media_thumbnail") or []):
                if m.get("url"):
                    img = m["url"]; break
            if not img:
                for l in e.get("links") or []:
                    if l.get("rel") == "enclosure" and str(l.get("type", "")).startswith("image"):
                        img = l.get("href"); break
            if img:
                extra["image"] = img
        if "hnrss" in src["url"]:
            extra["comments"] = e.get("comments")
        if "news.google.com" in url and " - " in title:       # Google News appends " - Publisher"
            title = title.rsplit(" - ", 1)[0].strip()
        items.append(Item(src["name"], src["grp"], src["trust"], canon_url(url), title,
                          content[:MAX_TEXT], published, "ar" if is_arabic(title) else "en", extra))
    return items


def parse_epic(src: dict, body: bytes, now: float) -> list[Item]:
    import json
    els = json.loads(body)["data"]["Catalog"]["searchStore"]["elements"]
    items = []
    for g in els:
        offers = ((g.get("promotions") or {}).get("promotionalOffers") or [])
        for block in offers:
            for o in block.get("promotionalOffers", []):
                start, end = _iso(o.get("startDate")), _iso(o.get("endDate"))
                if o.get("discountSetting", {}).get("discountPercentage") != 0:
                    continue
                if not (start and end and start <= now < end):
                    continue
                slug = g.get("productSlug") or next(
                    (m.get("pageSlug") for m in g.get("offerMappings") or [] if m.get("pageSlug")), None)
                if not slug:
                    continue
                price = (g.get("price") or {}).get("totalPrice", {}).get("fmtPrice", {}).get("originalPrice")
                end_txt = datetime.fromtimestamp(end, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                text = (f"{g['title']} is free on Epic Games Store until {end_txt}. "
                        f"Regular price: {price}. Seller: {g.get('seller', {}).get('name', '')}. "
                        f"{g.get('description', '')}")
                items.append(Item(src["name"], src["grp"], src["trust"],
                                  canon_url(f"https://store.epicgames.com/p/{slug.split('/')[0]}"),
                                  f"Free on Epic: {g['title']}", text, start, "en",
                                  {"ends": end, "official_url": f"https://store.epicgames.com/p/{slug}"}))
    return items


def parse_gamerpower(src: dict, body: bytes, now: float) -> list[Item]:
    import json
    items = []
    for g in json.loads(body)[:60]:
        if g.get("status") != "Active" or g.get("type") != "Game":
            continue
        published = _iso(g.get("published_date")) or now
        if now - published > MAX_AGE_H * 3600:
            continue
        text = (f"{g['title']}. Worth: {g.get('worth')}. Platforms: {g.get('platforms')}. "
                f"Ends: {g.get('end_date')}. {g.get('description', '')} "
                f"How to get it: {g.get('instructions', '')}")
        items.append(Item(src["name"], src["grp"], src["trust"], canon_url(g["gamerpower_url"]),
                          g["title"], text, published, "en",
                          {"ends": g.get("end_date"), "needs_official_link": True}))
    return items


def parse_coingecko(src: dict, body: bytes, now: float) -> list[Item]:
    import json
    names = {"bitcoin": "Bitcoin", "ethereum": "Ethereum", "solana": "Solana", "the-open-network": "Toncoin",
             "toncoin": "Toncoin"}
    lines = []
    for cid, v in json.loads(body).items():
        price, chg = v.get("usd"), v.get("usd_24h_change")
        if price is None:
            continue
        p = f"${price:,.0f}" if price >= 1000 else f"${price:,.2f}"
        lines.append(f"{names.get(cid, cid)}: {p} ({chg:+.1f}% 24h)")
    return [_market_item(src, "crypto", lines, now)] if lines else []


def parse_stooq(src: dict, body: bytes, now: float) -> list[Item]:
    lines = []
    for r in csv.DictReader(io.StringIO(body.decode("utf-8", "replace"))):
        try:
            o, c = float(r["Open"]), float(r["Close"])
        except (KeyError, ValueError):
            continue
        sym = r["Symbol"].split(".")[0].upper()
        lines.append(f"{sym}: ${c:,.2f} ({(c - o) / o * 100:+.1f}% today, date {r.get('Date')})")
    return [_market_item(src, "stocks", lines, now)] if lines else []


def _market_item(src: dict, kind: str, lines: list[str], now: float) -> Item:
    day = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
    hour = datetime.fromtimestamp(now, timezone.utc).strftime("%H")
    return Item(src["name"], src["grp"], src["trust"],
                f"https://market.local/{kind}/{day}/{hour}", f"Market snapshot {kind} {day}",
                "\n".join(lines), now, "en", {"market": kind, "day": day})


PARSERS = {"rss": parse_rss, "epic": parse_epic, "gamerpower": parse_gamerpower,
           "coingecko": parse_coingecko, "stooq": parse_stooq}


# ---------- run ----------

async def _get(client: httpx.AsyncClient, url: str) -> bytes:
    """Browser headers first (many sites refuse bot user-agents), then the bot identity."""
    last = None
    for headers in (BROWSER, {"User-Agent": UA}):
        try:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return r.content
        except httpx.HTTPStatusError as exc:
            last = exc
            if exc.response.status_code not in (401, 403, 406, 419, 429):
                break
    raise last


def is_temporary(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in TEMPORARY
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


def site_of(src: dict) -> str | None:
    """Domain used for the Google News fallback ("site:" search)."""
    if src.get("site"):
        return src["site"]
    from urllib.parse import urlparse
    h = urlparse(src["url"]).netloc.lower().split(":")[0]
    if any(x in h for x in ("reddit.com", "youtube.com", "news.google.com", "arxiv.org", "hnrss", "ycombinator")):
        return None
    for pre in ("www.", "feeds.", "feed.", "rss.", "rssfeeds.", "syndication.", "export."):
        h = h.removeprefix(pre)
    return h or None


def fallback_url(src: dict) -> str | None:
    """Google News search restricted to the source's site: same stories, through a feed that works
    from any server. Used when the site's own feed is missing, blocked or broken."""
    site = site_of(src)
    if not site or src.get("parser", "rss") != "rss":
        return None
    from urllib.parse import quote
    lang = src.get("lang") or ("ar" if src.get("grp") in ("news_ar", "arabic_press") else
                               "fr" if src.get("grp") == "algeria" else "en")
    loc = {"ar": "hl=ar&gl=DZ&ceid=DZ:ar", "fr": "hl=fr&gl=FR&ceid=FR:fr"}.get(lang, "hl=en-US&gl=US&ceid=US:en")
    return f"https://news.google.com/rss/search?q={quote('site:' + site + ' when:2d')}&{loc}"


async def collect(sources_path: str | Path, db_path: str | Path, now: float | None = None) -> dict:
    now = now or time.time()
    store = Store(db_path)
    if not store.get("reenable:v2")[0]:          # one-time: give every source a second chance
        store.db.execute("UPDATE sources SET disabled=0, fails=0")
        store.db.commit()
        store.put("reenable:v2", 1)
    sources = []
    for s in load_sources(sources_path):
        if store.disabled(s["name"]):
            last = store.get(f"retry:{s['name']}")[0] or 0
            if now - last < RETRY_DISABLED_H * 3600:
                continue
            store.put(f"retry:{s['name']}", now)
        sources.append(s)
    stats = {"sources": len(sources), "new": 0, "failed": [], "disabled": [], "articles": 0}
    sem = asyncio.Semaphore(24)
    async with httpx.AsyncClient(headers={"User-Agent": UA}, timeout=20, follow_redirects=True) as client:

        reddit_lock = asyncio.Lock()

        async def one(src):
            if "reddit.com" in src["url"]:          # Reddit rate-limits bursts: one request at a time
                async with reddit_lock:
                    await asyncio.sleep(4)
                    return await _one(src)
            return await _one(src)

        async def _one(src):
            async with sem:
                try:
                    body = await _get(client, src["url"])
                    items = PARSERS[src["parser"]](src, body, now)
                    store.source_ok(src["name"])
                    return items
                except Exception as exc:  # noqa: BLE001
                    err = exc
                fb = fallback_url(src)
                if fb:
                    try:
                        items = parse_rss(src, await _get(client, fb), now)
                        store.source_ok(src["name"])
                        stats.setdefault("via_fallback", []).append(src["name"])
                        log.info("source %s via Google News (%s)", src["name"], err)
                        return items
                    except Exception as exc2:  # noqa: BLE001
                        log.info("fallback failed %s: %s", src["name"], exc2)
                log.warning("source %s failed: %s", src["name"], err)
                stats["failed"].append(src["name"])
                if is_temporary(err):          # busy or rate-limited today is not broken: never disable
                    return []
                if store.source_fail(src["name"], repr(err), DISABLE_AFTER if src.get("verify") else None):
                    stats["disabled"].append(src["name"])
                return []

        batches = await asyncio.gather(*(one(s) for s in sources))
        new = [it for batch in batches for it in batch if not store.has(it.id) or it.extra.get("market")]

        need_page = [it for it in new if (len(it.text) < MIN_TEXT or it.trust >= 3)
                     and it.grp not in ("markets", "opportunities")]
        for it in need_page[:ARTICLE_FETCHES]:
            try:
                html = (await _get(client, it.url)).decode("utf-8", "replace")
                text = trafilatura.extract(html, favor_precision=True) or ""
                meta = trafilatura.extract_metadata(html)
                if meta is not None and getattr(meta, "image", None):
                    it.extra["page_image"] = meta.image      # the article's lead image (for reference)
                if len(text) > len(it.text):
                    it.text = text[:MAX_TEXT]
                    stats["articles"] += 1
            except Exception as exc:  # noqa: BLE001
                log.info("article fetch failed %s: %s", it.url, exc)

        # enrich: stories stored earlier with only a one-line summary get their full article text,
        # so the writer has enough facts to explain them (top-wow first)
        from .cluster import wow
        thin = [it for it in store.recent(36, now) if len(it.text) < MIN_TEXT
                and it.grp not in ("markets", "opportunities", "trends")
                and not store.get(f"enriched:{it.id}")[0]]
        thin.sort(key=lambda it: wow(it.title), reverse=True)
        for it in thin[:30]:
            store.put(f"enriched:{it.id}", 1)
            try:
                html = (await _get(client, it.url)).decode("utf-8", "replace")
                text = trafilatura.extract(html, favor_precision=True) or ""
                meta = trafilatura.extract_metadata(html)
                extra = dict(it.extra or {})
                if meta is not None and getattr(meta, "image", None):
                    extra["page_image"] = meta.image
                if len(text) > len(it.text):
                    store.db.execute("UPDATE items SET text=?, extra=? WHERE id=?",
                                     (text[:MAX_TEXT], json.dumps(extra, ensure_ascii=False), it.id))
                    store.db.commit()
                    stats["articles"] += 1
            except Exception as exc:  # noqa: BLE001
                log.info("enrich failed %s: %s", it.url, exc)

    for it in new:
        if it.extra.get("market"):
            store.put(f"market:{it.extra['market']}", {"item": it.__dict__})
        elif store.add(it):
            stats["new"] += 1
    store.prune()
    return stats
