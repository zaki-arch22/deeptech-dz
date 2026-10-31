"""Group items that tell the same story, score them, and export candidates for the writer."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path

from .store import Item, Store, item_dict
from .text import entities, host, jaccard, norm_ar, tokens

SENSITIVE = [
    # en
    r"\bhack(ed|ers?)?\b", r"\bbreach", r"\bleak(ed|s)?\b", r"\bdie[ds]?\b", r"\bdeath\b", r"\bdead\b",
    r"\bkill", r"\barrest", r"\bban(s|ned)?\b", r"\blawsuit", r"\bbankrupt", r"\bcollapse",
    r"\blayoffs?\b", r"\bsanction", r"\bgovernment\b", r"\bministry\b", r"\bcrash",
    # ar (normalized: ة->ه, أ->ا)
    "اختراق", "تسريب", "وفاه", "توفي", "مقتل", "اعتقال", "حظر", "افلاس", "انهيار", "تسريح",
    "عقوبات", "وزاره", "الحكومه", "قرار", "دعوي قضاييه",
]
_SENS = [re.compile(p, re.I) for p in SENSITIVE]

TITLE_SIM = 0.40
ENTITY_SIM = 0.20      # token similarity needed when >=2 entities are shared
EXPORT_CLUSTERS = 90
SOURCE_TEXT = 3500     # chars per source sent to the writer


@dataclass
class Cluster:
    items: list[Item] = field(default_factory=list)
    toks: set = field(default_factory=set)
    ents: set = field(default_factory=set)

    @property
    def id(self) -> str:
        first = min(self.items, key=lambda i: i.published)
        return "c" + sha1(first.url.encode()).hexdigest()[:10]

    @property
    def hosts(self) -> set[str]:
        return {host(i.url) for i in self.items}

    @property
    def kind(self) -> str:
        grps = {i.grp for i in self.items}
        return "free" if "opportunities" in grps else "news"

    @property
    def sensitive(self) -> bool:
        blob = norm_ar(" ".join(i.title + " " + i.text[:400] for i in self.items))
        return any(p.search(blob) for p in _SENS)

    def score(self, now: float) -> float:
        newest = max(i.published for i in self.items)
        age_h = (now - newest) / 3600
        s = 2.0 * len(self.hosts) + max(i.trust for i in self.items)
        s += 1.5 if any(i.trust >= 3 for i in self.items) else 0
        s += 2 if age_h < 6 else 1 if age_h < 12 else 0
        s += 1 if any(i.lang == "ar" for i in self.items) else 0
        s += wow(" ".join(i.title + " " + i.text[:600] for i in self.items))
        return round(s, 2)


# "Would I forward this?" — boosts stories with a wow factor, buries filler.
_WOW = [
    (4, r"\b(first[- ]ever|world'?s first|record|historic|breakthrough|in (space|orbit)|satellite|"
        r"quantum|robot|humanoid|starship|moon|mars|nasa|spacex)\b|في الفضاء|لأول مرة|رقم قياسي|قمر صناعي|روبوت"),
    (3, r"\b(billion|trillion|layoffs?|lays? off|hack(ed|ers)?|breach|stolen|leak(ed)?|outage|down worldwide|"
        r"lawsuit|banned?|antitrust|admits?|defect|recall|ai model|openai|anthropic|nvidia|chatgpt|gemini|"
        r"north korea|ransomware|infostealer|malware|whatsapp|tiktok|telegram|instagram)\b|مليار|اختراق|تسريح|"
        r"حظر|عطل|ذكاء اصطناعي"),
    (2, r"\b(launch(es|ed)?|unveil(s|ed)?|reveals?|new (phone|chip|model)|free|iphone|galaxy|playstation|"
        r"el cl[aá]sico|champions league|algeria|algerian)\b|الجزائر|مجان"),
]
_DULL = [
    (-2, r"\b(deals?|discount|% off|save \$|lowest price|all-time low|black friday|coupon|mattress|"
         r"earbuds drop|summit|webinar|register now|tickets?)\b"),
    (-2, r"\b(player ratings|press conference|fit to face|injury update|set for new .* deal|"
         r"night sky notes|apod|how to|tips|guide|explained|daily:|podcast|week in review)\b"),
    (-1, r"\b(beta \d|rolling out to|minor update|firmware)\b"),
]


def wow(text: str) -> float:
    t = text.lower()
    s = sum(w for w, rx in _WOW if re.search(rx, t))
    s += sum(w for w, rx in _DULL if re.search(rx, t))
    return s


def build_clusters(items: list[Item]) -> list[Cluster]:
    clusters: list[Cluster] = []
    for it in sorted(items, key=lambda i: i.published):
        t, e = tokens(it.title), entities(it.title)
        best, best_sim = None, 0.0
        for c in clusters:
            if c.kind == "free" and it.grp != "opportunities":
                continue
            sim = jaccard(t, c.toks)
            shared = len(e & c.ents)
            ok = sim >= TITLE_SIM or (shared >= 2 and sim >= ENTITY_SIM) or (shared >= 1 and sim >= 0.3)
            if ok and sim > best_sim:
                best, best_sim = c, sim
        if best is None:
            best = Cluster()
            clusters.append(best)
        best.items.append(it)
        best.toks |= t
        best.ents |= e
    return clusters


def export(db_path: str | Path, out: str | Path, history_path: str | Path | None = None,
           hours: float = 36, now: float | None = None) -> dict:
    now = now or time.time()
    store = Store(db_path)
    used = _used_urls(history_path, now) if history_path else set()
    items = [i for i in store.recent(hours, now) if i.url not in used]
    clusters = sorted(build_clusters(items), key=lambda c: c.score(now), reverse=True)

    news = [c for c in clusters if c.kind == "news"][:EXPORT_CLUSTERS]
    free = [c for c in clusters if c.kind == "free"]
    payload = {
        "generated_at": datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds"),
        "clusters": [_cluster_json(c, now) for c in news + free],
    }
    market = _market_cluster(store, now)
    if market:
        payload["clusters"].append(market)
    library = _library_clusters(Path(db_path).resolve().parent.parent / "library.yaml", history_path, now)
    payload["clusters"] += library
    for c in payload["clusters"]:  # the publisher still finds a cluster after it leaves the top list
        store.put(f"cluster:{c['id']}", c)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"items": len(items), "clusters": len(payload["clusters"]), "news": len(news), "free": len(free),
            "market": bool(market), "library": len(library)}


def _cluster_json(c: Cluster, now: float) -> dict:
    return {
        "id": c.id,
        "kind": c.kind,
        "score": c.score(now),
        "sensitive": c.sensitive,
        "distinct_sites": len(c.hosts),
        "title_hint": max(c.items, key=lambda i: i.trust).title,
        "official_image": next((i.extra.get("image") or i.extra.get("page_image") for i in c.items
                                if i.extra and i.trust >= 3 and (i.extra.get("image") or i.extra.get("page_image"))), None),
        "sources": [
            {**{k: v for k, v in item_dict(i).items() if k in ("id", "source", "trust", "url", "title", "lang", "extra")},
             "published": datetime.fromtimestamp(i.published, timezone.utc).isoformat(timespec="minutes"),
             "text": i.text[:SOURCE_TEXT]}
            for i in sorted(c.items, key=lambda i: -i.trust)
        ],
    }


def _market_cluster(store: Store, now: float) -> dict | None:
    parts = []
    for kind in ("crypto", "stocks"):
        snap, updated = store.get(f"market:{kind}")
        if snap and now - updated < 6 * 3600:
            it = snap["item"]
            parts.append({"id": kind, "source": it["source"], "trust": it["trust"], "url": it["url"],
                          "title": it["title"], "lang": "en", "extra": it["extra"],
                          "published": datetime.fromtimestamp(it["published"], timezone.utc).isoformat(timespec="minutes"),
                          "text": it["text"]})
    if not parts:
        return None
    day = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
    return {"id": f"market-{day}", "kind": "market", "score": 0, "sensitive": False,
            "distinct_sites": len(parts), "title_hint": f"Market {day}", "sources": parts}


def _used_urls(history_path: str | Path, now: float, days: int = 7) -> set[str]:
    p = Path(history_path)
    if not p.exists():
        return set()
    used = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        h = json.loads(line)
        if now - h.get("published_ts", now) <= days * 86400:
            used.update(h.get("source_urls", []))
    return used


LIBRARY_COOLDOWN_DAYS = 60
LIBRARY_EXPORT = 10


def _library_clusters(path: Path, history_path, now: float) -> list[dict]:
    """Evergreen opportunities (free courses, tools, security checks) not posted in the last 60 days.
    Rotates daily so the writer sees different items."""
    if not path.exists():
        return []
    import yaml
    items = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    recent = set()
    if history_path and Path(history_path).exists():
        for line in Path(history_path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                h = json.loads(line)
                if now - h.get("published_ts", 0) < LIBRARY_COOLDOWN_DAYS * 86400:
                    recent.add(h.get("cluster_id"))
    fresh = [it for it in items if f"lib-{it['id']}" not in recent]
    day = int(now // 86400)
    by_kind: dict[str, list] = {}
    for it in fresh:
        by_kind.setdefault(it["kind"], []).append(it)
    picked = []
    for kind, lst in sorted(by_kind.items()):
        k = day % len(lst)
        picked += (lst[k:] + lst[:k])[:3]          # up to 3 per kind, rotating daily
    out = []
    for it in picked:
        links = it["url"] + (" Download: " + it["store"] if it.get("store") else "")
        out.append({
            "id": f"lib-{it['id']}", "kind": "library", "library_kind": it["kind"], "score": 0,
            "sensitive": False, "distinct_sites": 1, "title_hint": it["title"], "logos": it.get("logos", []),
            "sources": [{"id": it["id"], "source": "library", "trust": 3, "url": it["url"], "title": it["title"],
                         "lang": "en", "extra": {}, "published": "",
                         "text": it["facts"] + " Official link: " + links}],
        })
    return out
