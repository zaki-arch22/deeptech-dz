"""Find a working feed for each failing source (run on GitHub Actions: open internet).

For each source: the current URL, then <link rel="alternate"> feeds announced on its home pages,
then common feed paths. A feed counts only if it parses and has entries; fresher feeds win.
Prints one JSON line per source: {"name", "old", "new", "entries", "age_h", "tried"}.
"""
import asyncio, json, re, sys, time
from urllib.parse import urljoin, urlparse

import feedparser, httpx, yaml

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
     "Accept": "text/html,application/rss+xml,application/atom+xml,application/xml;q=0.9,*/*;q=0.8",
     "Accept-Language": "en-US,en;q=0.9,fr;q=0.8,ar;q=0.7"}
PATHS = ["/feed", "/feed/", "/rss", "/rss.xml", "/feed.xml", "/atom.xml", "/index.xml", "/rss/", "/feeds/posts/default",
         "/news/rss", "/news/feed", "/news/rss.xml", "/en/rss", "/en/rss.xml", "/rss/news", "/blog/feed", "/blog/rss.xml",
         "/newsroom/rss", "/press/rss", "/?feed=rss2", "/arc/outboundfeeds/rss/", "/rss/all", "/feeds/all.rss"]


async def feed_ok(c, url):
    try:
        r = await c.get(url)
        if r.status_code != 200:
            return None
        f = feedparser.parse(r.content)
        if not f.entries:
            return None
        ts = [time.mktime(e[k]) for e in f.entries for k in ("published_parsed", "updated_parsed") if e.get(k)]
        age = (time.time() - max(ts)) / 3600 if ts else 9999
        return {"entries": len(f.entries), "age_h": round(age, 1)}
    except Exception:
        return None


async def announced(c, page):
    try:
        r = await c.get(page)
        html = r.text[:600_000]
    except Exception:
        return []
    out = []
    for m in re.finditer(r"<link[^>]+>", html, re.I):
        tag = m.group(0)
        if re.search(r"application/(rss|atom)\+xml", tag, re.I):
            h = re.search(r'href=["\']([^"\']+)', tag)
            if h:
                out.append(urljoin(str(r.url), h.group(1).replace("&amp;", "&")))
    for m in re.finditer(r'href=["\']([^"\']*(?:rss|feed|atom)[^"\']*)["\']', html, re.I):
        u = urljoin(str(r.url), m.group(1).replace("&amp;", "&"))
        if urlparse(u).netloc.endswith(urlparse(page).netloc.split(":")[0].removeprefix("www.")) and len(out) < 40:
            out.append(u)
    return out


async def one(c, sem, src):
    async with sem:
        old = src["url"]
        tried, best = [], None
        p = urlparse(old)
        host = p.netloc
        roots = [f"{p.scheme}://{host}"]
        bare = host.removeprefix("www.")
        for pre in ("feeds.", "feed.", "rss.", "rssfeeds.", "syndication.", "export."):
            bare = bare.removeprefix(pre)
        for h in (bare, "www." + bare):
            if f"https://{h}" not in roots:
                roots.append(f"https://{h}")
        if src.get("home"):
            roots.insert(0, src["home"])
        path_dir = old.rsplit("/", 1)[0]
        cands = [old] + ALT.get(src["name"], [])
        for r in roots[:3]:
            cands += await announced(c, r + "/")
        for r in roots[:2]:
            cands += [r + x for x in PATHS]
        cands.append(path_dir + "/")
        seen = set()
        for u in cands:
            if u in seen or len(tried) > 45:
                continue
            seen.add(u)
            tried.append(u)
            res = await feed_ok(c, u)
            if res and (best is None or res["age_h"] < best["age_h"] - 1):
                best = {"url": u, **res}
                if res["age_h"] < 48 and u != old:
                    break
                if u == old and res["age_h"] < 168:
                    break
        print(json.dumps({"name": src["name"], "old": old, "new": best and best["url"],
                          "entries": best and best["entries"], "age_h": best and best["age_h"],
                          "tried": len(tried)}, ensure_ascii=False), flush=True)


ALT = json.load(open("tools/alt_feeds.json", encoding="utf-8"))


async def gnews(c, sem, src):
    """Check the Google News fallback the collector uses when the site's own feed fails."""
    import sys as _s; _s.path.insert(0, ".")
    from dtdz.collect import fallback_url
    async with sem:
        u = fallback_url({**src, "parser": src.get("parser", "rss"), "grp": src.get("grp", "")})
        res = await feed_ok(c, u) if u else None
        print(json.dumps({"gnews": src["name"], "url": u, **(res or {"entries": 0})}, ensure_ascii=False), flush=True)


async def main(names):
    data = yaml.safe_load(open("sources.yaml", encoding="utf-8"))
    srcs = [dict(s, grp=gname) for gname, g in data.items() for s in (g or []) if s.get("name") in names]
    sem = asyncio.Semaphore(12)
    async with httpx.AsyncClient(headers=H, timeout=15, follow_redirects=True) as c:
        await asyncio.gather(*(one(c, sem, s) for s in srcs))
        await asyncio.gather(*(gnews(c, sem, s) for s in srcs))


if __name__ == "__main__":
    asyncio.run(main(set(l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip())))
