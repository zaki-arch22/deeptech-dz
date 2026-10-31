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
    for e in feed.entries[:PER_FEED]:
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
    r = await client.get(url)
    r.raise_for_status()
    return r.content


async def collect(sources_path: str | Path, db_path: str | Path, now: float | None = None) -> dict:
    now = now or time.time()
    store = Store(db_path)
    sources = [s for s in load_sources(sources_path) if not store.disabled(s["name"])]
    stats = {"sources": len(sources), "new": 0, "failed": [], "disabled": [], "articles": 0}
    sem = asyncio.Semaphore(24)
    async with httpx.AsyncClient(headers={"User-Agent": UA}, timeout=20, follow_redirects=True) as client:

        async def one(src):
            async with sem:
                try:
                    body = await _get(client, src["url"])
                    items = PARSERS[src["parser"]](src, body, now)
                    store.source_ok(src["name"])
                    return items
                except Exception as exc:  # noqa: BLE001 — any failure counts against the source
                    log.warning("source %s failed: %s", src["name"], exc)
                    stats["failed"].append(src["name"])
                    if store.source_fail(src["name"], repr(exc), DISABLE_AFTER if src.get("verify") else None):
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
