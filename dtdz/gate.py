"""Publishing gate. A post goes out only if check_post() returns no errors.

Run by the writer task before committing, and again by the publisher on the PC.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

from .text import (EMOJI, LATIN_WORD, URL, canon_url, entities, host, jaccard, norm_ar, numbers,
                   same_site, tokens)

SIGNATURE = "◆ Deeptech DZ"
TYPES = {"list", "course", "news", "free", "tool", "market", "odd", "app", "site", "sport", "film", "discovery", "study", "visa", "trend"}
WORDS = {"list": (45, 220), "course": (40, 150), "news": (35, 130), "odd": (35, 130), "free": (35, 140), "tool": (40, 160), "market": (25, 140), "app": (60, 170), "site": (55, 160), "sport": (35, 150),
         "film": (40, 190), "discovery": (40, 150), "study": (60, 180), "visa": (60, 180), "trend": (60, 170)}
MAX_LATIN_WORDS = 4               # Latin words outside links: Arabic first, names in Arabic
MAX_SENTENCE_WORDS = 22
HEADLINE_WORDS = (4, 10)
MAX_PARA_LINES = {"list": 14, "market": 9, "tool": 6, "app": 6, "site": 6, "news": 5, "film": 8, "sport": 6}
MAX_EMOJI, MAX_EMOJI_FIRST = 4, 2
MAX_CHARS = 1024                 # Telegram photo caption limit
SHINGLE = 8                      # words in a row shared with a source = copying
DEDUPE_DAYS, DEDUPE_SIM = 7, 0.5
SMALL_FREE_NUMBER = 10           # bare integers <= this need no source (e.g. "3 خطوات")

OFFICIAL_LINK_SITES = {
    "store.epicgames.com", "store.steampowered.com", "gog.com", "play.google.com", "apps.apple.com",
    "microsoft.com", "github.com", "edx.org", "coursera.org", "freecodecamp.org", "harvard.edu",
    "google.com", "youtube.com", "openai.com", "apple.com", "ubisoft.com", "ea.com", "amazon.com",
    "primegaming.com", "humblebundle.com", "itch.io", "netflix.com", "shahid.mbc.net", "osnplus.com",
    "primevideo.com", "disneyplus.com", "max.com", "youtube.com", "vovsoft.com", "giveawayoftheday.com",
    "sharewareonsale.com",
}
BLOCKED_LINK_SITES = {"gamerpower.com", "t.me", "telegram.me", "mediafire.com", "mega.nz", "market.local",
                      "primetv", "egybest", "mycima", "cimaclub", "shahid4u", "apkpure.com", "apkmirror.com"}
LATIN_OK = {"deeptech", "dz", "https", "http", "www", "com", "usd"}


def load_banned(path: str | Path) -> list[tuple[str, re.Pattern | str]]:
    rules = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("re:"):
            rules.append((line, re.compile(line[3:], re.I)))
        else:
            rules.append((line, norm_ar(line).lower()))
    return rules


def _shingles(s: str) -> set[tuple]:
    w = re.findall(r"[\w]+", norm_ar(s).lower())
    return {tuple(w[i:i + SHINGLE]) for i in range(len(w) - SHINGLE + 1)}


def check_post(post: dict, cluster: dict | None, banned: list, history: list[dict],
               now: float | None = None, strict: bool = True) -> list[str]:
    """strict=True: full quality check, used by the writer while writing (fix, never drop).
    strict=False: publish-time safety only (facts, links, duplicates, Telegram limits) — a post the
    writer already checked is never thrown away at the last minute for a style detail."""
    errs = _check_post(post, cluster, banned, history, now)
    if strict:
        return errs
    keep = ("schema:", "fact:", "link:", "dedupe:")
    return [e for e in errs if e.startswith(keep) or "Telegram caption" in e or "unbalanced" in e]


def _check_post(post: dict, cluster: dict | None, banned: list, history: list[dict],
                now: float | None = None) -> list[str]:
    now = now or time.time()
    err: list[str] = []
    text = (post.get("text") or "").strip()
    bold_unbalanced = text.count("**") % 2 == 1
    text = text.replace("**", "")          # **bold** markers are formatting only
    ptype = post.get("type")

    # schema
    for k in ("id", "type", "cluster_id", "slot", "text"):
        if not post.get(k):
            err.append(f"schema: missing '{k}'")
    if ptype not in TYPES:
        err.append(f"schema: type must be one of {sorted(TYPES)}")
    if cluster is None:
        return err + [f"schema: cluster '{post.get('cluster_id')}' not found in candidates"]
    if err:
        return err
    if ptype == "market" and cluster["kind"] != "market":
        err.append("schema: market post must use the market cluster")

    lines = text.split("\n")
    body_lines = [l for l in lines if l.strip() and l.strip() != SIGNATURE and not l.strip().startswith("#")]
    body = "\n".join(body_lines)
    facts_text = body + "\n" + post.get("headline", "")
    norm = norm_ar(text).lower()
    src_text = "\n".join(s["title"] + "\n" + s["text"] + "\n" + s["url"] for s in cluster["sources"])
    src_norm = norm_ar(src_text).lower()

    # banned phrases
    for raw, rule in banned:
        hit = rule.search(text) or rule.search(norm) if isinstance(rule, re.Pattern) else rule in norm
        if hit:
            err.append(f"style: banned phrase «{raw}»")

    # shape
    if bold_unbalanced:
        err.append("format: unbalanced ** bold markers")
    if lines[-1].strip() != SIGNATURE:
        err.append(f"format: last line must be exactly '{SIGNATURE}'")
    if re.search(r"(?<![\w&])#[\w_]+", text):
        err.append("format: no hashtags in posts")
    emo = EMOJI.findall(text)
    if len(emo) > MAX_EMOJI:
        err.append(f"format: {len(emo)} emoji (max {MAX_EMOJI})")
    if len(EMOJI.findall(lines[0])) > MAX_EMOJI_FIRST:
        err.append("format: max one emoji in the first line")
    if lines[0].strip() == "" or lines[0].lstrip().startswith("#"):
        err.append("format: the first line must carry the news")
    # Arabic first: Telegram sets each paragraph's direction from its first strong letter
    for ln in body_lines:
        first = next((ch for ch in ln if ch.isalpha()), "")
        is_item = re.match(r"\s*(\d+[.)•-]|•)", ln) and ptype == "list"     # "1• KVRT - ..." list lines
        if first and not is_item and not ("\u0600" <= first <= "\u06FF") and not ln.strip().startswith("🔗"):
            err.append(f"format: line starts with a non-Arabic word — rewrite: «{ln.strip()[:40]}»")
    latin = LATIN_WORD.findall(URL.sub(" ", body))
    cap = 25 if ptype == "list" else MAX_LATIN_WORDS if ptype in ("news", "odd", "discovery", "breaking") else 8
    if len(latin) > cap and ptype != "market":
        err.append(f"style: {len(latin)} English words (max {cap}); drop technical names, write known names in Arabic")
    for sent in re.split(r"[.!؟?\n]+", URL.sub(" ", body)):
        if len(sent.split()) > MAX_SENTENCE_WORDS:
            err.append(f"style: sentence of {len(sent.split())} words (max {MAX_SENTENCE_WORDS})")
            break
    if "headline" in post:
        hw = post["headline"].split()
        if not HEADLINE_WORDS[0] <= len(hw) <= HEADLINE_WORDS[1]:
            err.append(f"format: headline must be {HEADLINE_WORDS[0]}-{HEADLINE_WORDS[1]} words")
        first = next((ch for ch in post["headline"] if ch.isalpha()), "")
        if first and not ("\u0600" <= first <= "\u06FF"):
            err.append("format: headline must start with an Arabic word")
    # every card must carry at least one real brand logo
    from .brands import logo_specs
    for lg in post.get("logos") or []:
        if not lg.get("domain"):
            err.append("visual: each entry in 'logos' needs the brand's official 'domain'")
    if not logo_specs(post, post.get("headline", "") + "\n" + text):
        err.append("visual: no brand logo — name the company/app/coin in the text, or add "
                   '"logos": [{"name": "...", "domain": "official-site.com"}]')
    # no "clever" closing remark: a short last paragraph must carry a fact, a link or practical advice
    paras = [p_.strip() for p_ in re.split(r"\n\s*\n", text.replace(SIGNATURE, "")) if p_.strip()]
    if len(paras) >= 2 and ptype not in ("market", "list"):
        last = paras[-1]
        advice = re.match(r"^(🔗|•|لا ت|احرص|فعّل|فعل|حمّل|حمل|افتح|ادخل|اضغط|غيّر|غير|تحقق|راجع|للحصول|للبدء|"
                          r"للتفعيل|للتسجيل|سجّل|سجل|اشترك|انتبه|إن كان|إن كنت|إذا كان|إذا كنت|الرابط|المنصة|العرض|"
                          r"الموعد|التسجيل|متاح|يعرض|تبث|تُعرض|المباراة)", last)
        fact = re.search(r"\d", last) or URL.search(last) or LATIN_WORD.search(last)
        if len(last.split()) <= 18 and not advice and not fact:
            err.append("style: the last paragraph is a closing remark — end on a fact, a date, a link or "
                       "practical advice (or merge it into the previous paragraph)")
    if len(text) > MAX_CHARS:
        err.append(f"format: {len(text)} characters (max {MAX_CHARS}, Telegram caption limit)")
    n_words = len(re.findall(r"\S+", URL.sub("", body)))
    lo, hi = WORDS[ptype]
    if not lo <= n_words <= hi:
        err.append(f"format: {n_words} words (allowed {lo}-{hi} for {ptype})")
    max_lines = MAX_PARA_LINES.get(ptype, 3)
    for para in re.split(r"\n\s*\n", text):
        if len([l for l in para.split("\n") if l.strip()]) > max_lines:
            err.append(f"format: a paragraph is longer than {max_lines} lines")
            break

    # facts: every number and every Latin name must exist in the sources
    src_nums = numbers(src_text)
    body_no_urls = URL.sub(" ", facts_text)
    for m in re.finditer(r"\d+(?:[.,٫٬]\d+)*", norm_ar(body_no_urls)):
        n = numbers(m.group())
        if n <= src_nums:
            continue
        ctx = norm_ar(body_no_urls)[max(0, m.start() - 2): m.end() + 8]
        bare = m.group().isdigit() and int(m.group()) <= SMALL_FREE_NUMBER
        if bare and not re.search(r"[%$€]|مليون|مليار|الف", ctx):
            continue
        err.append(f"fact: number {m.group()} is not in the sources")
    for w in set(LATIN_WORD.findall(body_no_urls)):
        lw = w.lower()
        if lw in LATIN_OK or re.search(r"(?<![a-z0-9])" + re.escape(lw) + r"(?![a-z0-9])", src_norm):
            continue
        err.append(f"fact: name '{w}' is not in the sources")

    # sensitive stories need two independent sites
    top_trust = max(s["trust"] for s in cluster["sources"])
    if (cluster.get("sensitive") or ptype in ("visa", "trend")) and top_trust < 3 and (
            cluster["distinct_sites"] < 2 or top_trust < 2):
        err.append("fact: sensitive story needs 2 independent sources (trust>=2)")

    # links
    src_hosts = {host(s["url"]) for s in cluster["sources"]} | {host(u) for u in URL.findall(src_text)}
    links = [u for u in URL.findall(text) if "." in u and not u.endswith(".")]
    for u in links:
        h = host(u)
        if any(same_site(h, b) for b in BLOCKED_LINK_SITES):
            err.append(f"link: {h} is not allowed (use the official page)")
        elif not any(same_site(h, a) for a in src_hosts | OFFICIAL_LINK_SITES):
            err.append(f"link: {h} is neither a source nor an official site")
    if ptype in ("free", "app", "site", "study", "list", "course", "visa") and not links:
        err.append("link: a free-offer post needs the official link")

    # no copying: no run of SHINGLE words shared with any source
    if _shingles(URL.sub(" ", text)) & _shingles(URL.sub(" ", src_text)):  # links are expected to match
        err.append(f"style: {SHINGLE}+ words copied verbatim from a source — rewrite")

    # library items: once per 60 days
    if str(post["cluster_id"]).startswith("lib-"):
        for h in history:
            if (h.get("cluster_id") == post["cluster_id"] and h.get("id") != post["id"]
                    and now - h.get("published_ts", 0) < 60 * 86400):
                err.append(f"dedupe: library item already posted ({h['id']})")
    # Real photos of the story itself, from anywhere on the web, as long as the image is published by
    # the organisation the story is about (its site, newsroom, press kit, CDN) or is freely licensed.
    ph = post.get("photo")
    specs = ([ph] if ph else []) + list(post.get("gallery") or [])
    if len(post.get("gallery") or []) > 3:
        err.append("visual: max 3 gallery photos")
    allowed = photo_hosts(post, cluster)
    for spec in specs:
        if not (spec.get("wiki") or spec.get("url") or spec.get("commons")):
            err.append("visual: a photo needs 'url', 'commons' or 'wiki'")
        if spec.get("url"):
            h = host(spec["url"])
            ok = any(same_site(h, a) for a in allowed) or (
                same_site(h, "play-lh.googleusercontent.com") and ptype in ("app", "tool", "free", "site"))
            if not ok:
                err.append(f"visual: photo host {h} is not the official site of a brand in this post — add the "
                           "brand to 'logos' with its domain, or set 'photo_owner' to the official domain")
            if spec.get("owner") and not any(same_site(h, a) for a in allowed):
                err.append(f"visual: photo owner {spec['owner']} not allowed")

    # 7-day dedupe
    key = tokens(cluster.get("title_hint", "")) | tokens(lines[0]) | entities(lines[0])
    urls = {canon_url(s["url"]) for s in cluster["sources"]}
    for h in history:
        if (now - h.get("published_ts", 0) > DEDUPE_DAYS * 86400 or h.get("id") == post["id"]
                or h.get("id") in (post.get("replaces") or [])):  # a corrected re-issue of an older post
            continue
        if h.get("cluster_id") == post["cluster_id"] and ptype != "market":
            err.append(f"dedupe: cluster already posted ({h['id']})")
        elif urls & set(h.get("source_urls", [])) and ptype != "market":
            err.append(f"dedupe: same source already posted ({h['id']})")
        elif ptype != "market" and jaccard(key, set(h.get("key", []))) >= DEDUPE_SIM:
            err.append(f"dedupe: same topic as {h['id']} in the last {DEDUPE_DAYS} days")
        elif (ptype == "market" and h.get("type") == "market"
              and abs(_slot_ts(post["slot"]) - h.get("published_ts", 0)) < 4 * 3600):
            err.append("dedupe: market posts need 4 hours between them")
    return err


def history_entry(post: dict, cluster: dict, published_ts: float) -> dict:
    first = post["text"].split("\n")[0]
    return {
        "id": post["id"], "type": post["type"], "cluster_id": post["cluster_id"],
        "published_ts": published_ts, "day": post["slot"][:10],
        "source_urls": sorted({canon_url(s["url"]) for s in cluster["sources"]}),
        "key": sorted(tokens(cluster.get("title_hint", "")) | tokens(first) | entities(first)),
    }


def load_history(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def check_file(posts_path: str | Path, candidates_path: str | Path, banned_path: str | Path,
               history_path: str | Path, now: float | None = None) -> dict[str, list[str]]:
    """Check a batch; posts in the same batch also dedupe against each other."""
    cands = json.loads(Path(candidates_path).read_text(encoding="utf-8"))
    clusters = {c["id"]: c for c in cands["clusters"]}
    banned = load_banned(banned_path)
    history = load_history(history_path)
    posts = json.loads(Path(posts_path).read_text(encoding="utf-8"))
    results, seen_ids = {}, set()
    for p in posts:
        pid = p.get("id", "?")
        errs = check_post(p, clusters.get(p.get("cluster_id")) or web_cluster(p), banned, history, now)
        if pid in seen_ids:
            errs.append("schema: duplicate id in batch")
        seen_ids.add(pid)
        results[pid] = errs
        if not errs:
            slot_ts = _slot_ts(p["slot"]) or (now or time.time())
            history.append(history_entry(p, clusters.get(p["cluster_id"]) or web_cluster(p), slot_ts))
    if len(posts) >= 3 and all(p.get("type") == "news" for p in posts):
        last = posts[-1].get("id", "?")
        results[last] = results.get(last, []) + [
            "mix: a run of 3+ posts needs at least one non-news post (free, tool, market or odd)"]
    return results


def _slot_ts(slot: str) -> float | None:
    try:
        return datetime.fromisoformat(slot).timestamp()
    except ValueError:
        return None


# CDNs that official organisations use to host their own press images
OFFICIAL_CDNS = {
    "apple.com": ["apple.com", "cdsassets.apple.com"], "google.com": ["googleusercontent.com", "gstatic.com", "blog.google"],
    "microsoft.com": ["microsoft.com", "msft.net", "azureedge.net"], "meta.com": ["fbcdn.net", "meta.com", "fb.com"],
    "samsung.com": ["samsung.com", "samsungmobilepress.com"], "nasa.gov": ["nasa.gov"], "openai.com": ["openai.com", "oaiusercontent.com"],
    "netflix.com": ["netflix.com", "nflxext.com", "nflximg.net"], "tesla.com": ["tesla.com", "tesla.cn"],
    "nvidia.com": ["nvidia.com", "nvidianews.nvidia.com"], "epicgames.com": ["epicgames.com", "unrealengine.com"],
    "steampowered.com": ["steamstatic.com", "steampowered.com"],
}


def photo_hosts(post: dict, cluster: dict) -> set[str]:
    from .brands import DOMAINS, detect_brands
    hosts = {"wikimedia.org", "wikipedia.org"}
    hosts |= {host(s["url"]) for s in cluster["sources"] if s.get("trust", 0) >= 3}
    hosts |= {host(i) for s in cluster["sources"] if s.get("trust", 0) >= 3
              for i in [(s.get("extra") or {}).get("image"), (s.get("extra") or {}).get("page_image")] if i}
    doms = [lg.get("domain") for lg in post.get("logos") or [] if lg.get("domain")]
    slugs = (post.get("brands") or []) + detect_brands(post.get("headline", "") + "\n" + post.get("text", ""), limit=4)
    doms += [DOMAINS[s] for s in slugs if s in DOMAINS]
    if post.get("photo_owner"):
        doms.append(post["photo_owner"])
    for d in doms:
        base = d.split("/")[0].removeprefix("www.")
        hosts.add(base)
        hosts.update(OFFICIAL_CDNS.get(base, []))
    return hosts


def web_cluster(post: dict) -> dict | None:
    """A post built from the writer's own web research (cluster_id "web-…"): it carries its sources —
    the official pages it read — as {"url", "title", "text"} with the facts copied from those pages."""
    if not str(post.get("cluster_id", "")).startswith("web-") or not post.get("sources"):
        return None
    srcs = [{"id": f"w{i}", "source": "web", "trust": 3, "url": s["url"], "title": s.get("title", ""),
             "lang": "en", "extra": {}, "published": "", "text": s.get("text", "")}
            for i, s in enumerate(post["sources"][:4]) if s.get("url") and s.get("text")]
    if not srcs:
        return None
    return {"id": post["cluster_id"], "kind": "web", "score": 0, "sensitive": False,
            "distinct_sites": len({host(s["url"]) for s in srcs}), "title_hint": post.get("headline", ""),
            "sources": srcs}
