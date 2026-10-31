"""Daily coverage plan: what the channel still owes its readers today.

`python -m dtdz plan` prints, for today (Africa/Algiers), how many posts of each category were
published or are queued, the daily target, and what to write next. The writer runs it first.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=1))   # Algeria, no DST

# category: (label, daily minimum, daily maximum, post types that count)
CATEGORIES = {
    "breaking":  ("عواجل وأحداث مثيرة",         2, 6, None),          # posts with "breaking": true
    "news":      ("أخبار التقنية والشركات",      5, 10, {"news", "odd"}),
    "discovery": ("اكتشافات واختراعات وأجهزة",   3, 6, {"discovery"}),
    "app":       ("تطبيقات",                     2, 4, {"app"}),
    "site":      ("مواقع",                       2, 4, {"site"}),
    "tool":      ("أدوات وذكاء اصطناعي وحماية",  2, 4, {"tool", "list"}),
    "free":      ("اشتراكات وألعاب وبرامج مجانية", 2, 5, {"free"}),
    "course":    ("دورات وشهادات",               2, 4, {"course"}),
    "study":     ("منح ودراسة",                  1, 3, {"study"}),
    "visa":      ("هجرة وتأشيرات",               1, 2, {"visa"}),
    "market":    ("أسواق مالية وعملات",          2, 3, {"market"}),
    "film":      ("أفلام ومسلسلات",              2, 3, {"film"}),
    "sport":     ("رياضة",                       2, 4, {"sport"}),
    "trend":     ("ترند",                        1, 3, {"trend"}),
}
DAY_START, DAY_END = 7, 25   # 07:00 → 01:00 next day
MIN_GAP_MIN = 12             # never two posts closer than this (except breaking news)


def _posts(root: Path) -> list[dict]:
    out = {}
    for f in sorted((root / "queue" / "posts").glob("*.json")):
        try:
            for p in json.loads(f.read_text(encoding="utf-8")):
                out[p["id"]] = p
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return list(out.values())


def category_of(post: dict) -> str:
    if post.get("category") in CATEGORIES:
        return post["category"]
    if post.get("breaking"):
        return "breaking"
    t = post.get("type")
    for cat, (_, _, _, types) in CATEGORIES.items():
        if types and t in types:
            return cat
    return "news"


def today_bounds(now: datetime) -> tuple[datetime, datetime]:
    base = now.astimezone(TZ)
    if base.hour < 1:
        base -= timedelta(days=1)
    start = base.replace(hour=DAY_START, minute=0, second=0, microsecond=0)
    return start, start + timedelta(hours=DAY_END - DAY_START)


def plan(root: str | Path, now: datetime | None = None) -> dict:
    root = Path(root)
    now = now or datetime.now(TZ)
    start, end = today_bounds(now)
    rejected = set()
    rej = root / "queue" / "rejected.jsonl"
    if rej.exists():
        rejected = {json.loads(l)["id"] for l in rej.read_text(encoding="utf-8").splitlines() if l.strip()}
    counts = {c: 0 for c in CATEGORIES}
    slots = []
    for p in _posts(root):
        try:
            t = datetime.fromisoformat(p["slot"])
        except (KeyError, ValueError):
            continue
        if start <= t < end and p["id"] not in rejected:
            counts[category_of(p)] += 1
            slots.append(t)
    missing = {c: CATEGORIES[c][1] - n for c, n in counts.items() if n < CATEGORIES[c][1]}
    hours_left = max(0.0, (end - max(now.astimezone(TZ), start)).total_seconds() / 3600)
    return {"day": start.strftime("%Y-%m-%d"), "counts": counts, "missing": missing,
            "total": sum(counts.values()), "hours_left": round(hours_left, 1),
            "taken_times": sorted(t.strftime("%H:%M") for t in slots if t >= now.astimezone(TZ))}


def print_plan(root: str | Path) -> None:
    p = plan(root)
    print(f"Day {p['day']} — {p['total']} posts so far, {p['hours_left']} h left (07:00–01:00)")
    for c, (label, lo, hi, _) in CATEGORIES.items():
        n = p["counts"][c]
        mark = "MISSING" if n < lo else ("full" if n >= hi else "ok")
        print(f"  {c:9} {label:28} {n}/{lo}-{hi}  {mark}")
    if p["missing"]:
        print("Write next (priority to categories furthest behind): " +
              ", ".join(f"{c}×{k}" for c, k in sorted(p["missing"].items(), key=lambda x: -x[1])))
    print("Already taken upcoming times:", ", ".join(p["taken_times"]) or "none")
