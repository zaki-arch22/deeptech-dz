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
TYPES = {"news", "free", "tool", "market", "odd"}
WORDS = {"news": (40, 180), "odd": (40, 180), "free": (30, 150), "tool": (40, 180), "market": (20, 140)}
MAX_PARA_LINES = {"market": 9, "tool": 6}
MAX_EMOJI, MAX_EMOJI_FIRST = 3, 1
MAX_CHARS = 1024                 # Telegram photo caption limit
SHINGLE = 8                      # words in a row shared with a source = copying
DEDUPE_DAYS, DEDUPE_SIM = 7, 0.5
SMALL_FREE_NUMBER = 10           # bare integers <= this need no source (e.g. "3 خطوات")

OFFICIAL_LINK_SITES = {
    "store.epicgames.com", "store.steampowered.com", "gog.com", "play.google.com", "apps.apple.com",
    "microsoft.com", "github.com", "edx.org", "coursera.org", "freecodecamp.org", "harvard.edu",
    "google.com", "youtube.com", "openai.com", "apple.com", "ubisoft.com", "ea.com", "amazon.com",
    "primegaming.com", "humblebundle.com", "itch.io",
}
BLOCKED_LINK_SITES = {"gamerpower.com", "t.me", "telegram.me", "mediafire.com", "mega.nz", "market.local"}
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
               now: float | None = None) -> list[str]:
    now = now or time.time()
    err: list[str] = []
    text = (post.get("text") or "").strip()
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
    norm = norm_ar(text).lower()
    src_text = "\n".join(s["title"] + "\n" + s["text"] + "\n" + s["url"] for s in cluster["sources"])
    src_norm = norm_ar(src_text).lower()

    # banned phrases
    for raw, rule in banned:
        hit = rule.search(text) or rule.search(norm) if isinstance(rule, re.Pattern) else rule in norm
        if hit:
            err.append(f"style: banned phrase «{raw}»")

    # shape
    if lines[-1].strip() != SIGNATURE:
        err.append(f"format: last line must be exactly '{SIGNATURE}'")
    tags = re.findall(r"#[\w_]+", text)
    if len(tags) > 1:
        err.append("format: at most one hashtag")
    if tags and not (len(lines) >= 2 and lines[-2].strip() == tags[0]):
        err.append("format: the hashtag goes alone on the line before the signature")
    emo = EMOJI.findall(text)
    if len(emo) > MAX_EMOJI:
        err.append(f"format: {len(emo)} emoji (max {MAX_EMOJI})")
    if len(EMOJI.findall(lines[0])) > MAX_EMOJI_FIRST:
        err.append("format: max one emoji in the first line")
    if lines[0].strip() == "" or lines[0].lstrip().startswith("#"):
        err.append("format: the first line must carry the news")
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
    body_no_urls = URL.sub(" ", body)
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
    if cluster.get("sensitive") and (cluster["distinct_sites"] < 2 or
                                     max(s["trust"] for s in cluster["sources"]) < 2):
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
    if ptype == "free" and not links:
        err.append("link: a free-offer post needs the official link")

    # no copying: no run of SHINGLE words shared with any source
    if _shingles(URL.sub(" ", text)) & _shingles(URL.sub(" ", src_text)):  # links are expected to match
        err.append(f"style: {SHINGLE}+ words copied verbatim from a source — rewrite")

    # 7-day dedupe
    key = tokens(cluster.get("title_hint", "")) | tokens(lines[0]) | entities(lines[0])
    urls = {canon_url(s["url"]) for s in cluster["sources"]}
    for h in history:
        if now - h.get("published_ts", 0) > DEDUPE_DAYS * 86400 or h.get("id") == post["id"]:
            continue
        if h.get("cluster_id") == post["cluster_id"] and ptype != "market":
            err.append(f"dedupe: cluster already posted ({h['id']})")
        elif urls & set(h.get("source_urls", [])) and ptype != "market":
            err.append(f"dedupe: same source already posted ({h['id']})")
        elif ptype != "market" and jaccard(key, set(h.get("key", []))) >= DEDUPE_SIM:
            err.append(f"dedupe: same topic as {h['id']} in the last {DEDUPE_DAYS} days")
        elif ptype == "market" and h.get("type") == "market" and h.get("day") == post["slot"][:10]:
            err.append("dedupe: one market post per day")
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
        errs = check_post(p, clusters.get(p.get("cluster_id")), banned, history, now)
        if pid in seen_ids:
            errs.append("schema: duplicate id in batch")
        seen_ids.add(pid)
        results[pid] = errs
        if not errs:
            slot_ts = _slot_ts(p["slot"]) or (now or time.time())
            history.append(history_entry(p, clusters[p["cluster_id"]], slot_ts))
    return results


def _slot_ts(slot: str) -> float | None:
    try:
        return datetime.fromisoformat(slot).timestamp()
    except ValueError:
        return None
