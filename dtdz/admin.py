"""Owner control from Telegram, shared by the PC runner and the cloud tick.

- Preview: every post is sent privately to the admin ~15 min before its time, with buttons
  «انشر الآن» / «ألغِ». No answer = it is published on time (automation stays automatic).
- Commands: /delete <id|last> removes a published post from the channel; /now publishes the next
  queued post immediately; /cancel <id>; /report sends the daily report now.
- Daily report at 08:00: yesterday's posts per category, cancellations, failing sources.
Overrides live in queue/overrides.json (committed, so the PC and the cloud share them).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("dtdz.admin")
TZ = timezone(timedelta(hours=1))
PREVIEW_MIN = 15


def _ovr_path(root: Path) -> Path:
    return Path(root) / "queue" / "overrides.json"


def load_overrides(root: Path) -> dict:
    p = _ovr_path(root)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        d = {}
    for k in ("cancel", "now", "previewed"):
        d.setdefault(k, [])
    return d


def save_overrides(root: Path, d: dict) -> None:
    d["previewed"] = d["previewed"][-300:]
    _ovr_path(root).write_text(json.dumps(d, ensure_ascii=False, indent=0), encoding="utf-8")


def _history(root: Path) -> list[dict]:
    p = Path(root) / "queue" / "history.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def send_previews(bot, root: Path, admin: int, now: float | None = None) -> int:
    """Private preview of posts due within PREVIEW_MIN minutes, once each."""
    from .card import render
    from .publisher import load_queue, _done_ids, _ts
    from .telegram import to_html
    if not admin:
        return 0
    root, now = Path(root), now or time.time()
    ovr = load_overrides(root)
    q = root / "queue"
    done = _done_ids(q / "history.jsonl", q / "rejected.jsonl") | set(ovr["cancel"])
    sent = 0
    try:
        clusters = {c["id"]: c for c in json.loads((q / "candidates.json").read_text(encoding="utf-8"))["clusters"]}
    except Exception:  # noqa: BLE001
        clusters = {}
    from .gate import web_cluster
    for p in load_queue(q / "posts"):
        pid = p.get("id")
        if not pid or pid in done or pid in ovr["previewed"] or not p.get("slot"):
            continue
        dt = _ts(p["slot"]) - now
        if not (0 < dt <= PREVIEW_MIN * 60):
            continue
        try:
            img = render(p, root / "data" / "cards" / f"{pid}.png", clusters.get(p.get("cluster_id")) or web_cluster(p))
            when = datetime.fromtimestamp(_ts(p["slot"]), TZ).strftime("%H:%M")
            kb = {"inline_keyboard": [[{"text": "✅ انشر الآن", "callback_data": f"now:{pid}"},
                                       {"text": "🗑 ألغِ", "callback_data": f"cancel:{pid}"}]]}
            from .publisher import normalize_signature
            caption = f"⏰ سيُنشر الساعة {when}\n\n" + to_html(normalize_signature(p["text"]))
            with open(img, "rb") as fh:
                bot.call("sendPhoto", files={"photo": (img.name, fh, "image/png")}, chat_id=admin,
                         caption=caption[:1024], parse_mode="HTML", reply_markup=json.dumps(kb))
            ovr["previewed"].append(pid)
            sent += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("preview failed %s: %s", pid, exc)
    if sent:
        save_overrides(root, ovr)
    return sent


def handle_update(bot, root: Path, admin: int, u: dict, channel: str) -> str | None:
    """Buttons and the new commands. Returns a reply text, or None if not handled here."""
    root = Path(root)
    cq = u.get("callback_query")
    if cq:
        if (cq.get("from") or {}).get("id") != admin:
            return None
        action, _, pid = (cq.get("data") or "").partition(":")
        ovr = load_overrides(root)
        if action in ("cancel", "now") and pid not in ovr[action]:
            ovr[action].append(pid)
            save_overrides(root, ovr)
        try:
            bot.call("answerCallbackQuery", callback_query_id=cq["id"],
                     text="أُلغي المنشور" if action == "cancel" else "سيُنشر خلال دقيقة")
        except Exception:  # noqa: BLE001
            pass
        return None
    msg = u.get("message") or {}
    if (msg.get("from") or {}).get("id") != admin:
        return None
    parts = (msg.get("text") or "").split()
    if not parts:
        return None
    cmd, arg = parts[0].split("@")[0], (parts[1] if len(parts) > 1 else "")
    if cmd == "/delete":
        hist = _history(root)
        target = hist[-1] if arg in ("", "last") and hist else next((h for h in hist if h["id"] == arg), None)
        if not target or not target.get("message_id"):
            return "لم أجد هذا المنشور. استعمل: /delete last أو /delete <id>"
        try:
            bot.call("deleteMessage", chat_id=channel, message_id=int(target["message_id"]))
            return f"🗑 حُذف المنشور {target['id']} من القناة."
        except Exception as exc:  # noqa: BLE001
            return f"تعذّر الحذف: {exc}"
    if cmd == "/cancel" and arg:
        ovr = load_overrides(root)
        ovr["cancel"].append(arg)
        save_overrides(root, ovr)
        return f"أُلغي {arg}."
    if cmd == "/now":
        from .publisher import upcoming
        nxt = upcoming(root)
        if not nxt:
            return "لا منشورات قادمة."
        ovr = load_overrides(root)
        ovr["now"].append(nxt[0]["id"])
        save_overrides(root, ovr)
        return f"⏩ سيُنشر الآن: {nxt[0]['first_line'][:80]}"
    if cmd == "/report":
        return daily_report(root)
    return None


def daily_report(root: Path, day: datetime | None = None) -> str:
    from .plan import CATEGORIES, category_of
    from .publisher import load_queue
    root = Path(root)
    day = (day or datetime.now(TZ) - timedelta(days=1)).astimezone(TZ)
    start = day.replace(hour=7, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=18)
    posts = {p["id"]: p for p in load_queue(root / "queue" / "posts")}
    hist = [h for h in _history(root) if start.timestamp() <= h.get("published_ts", 0) < end.timestamp()]
    counts: dict[str, int] = {}
    for h in hist:
        c = category_of(posts.get(h["id"], {"type": h.get("type")}))
        counts[c] = counts.get(c, 0) + 1
    rej = root / "queue" / "rejected.jsonl"
    rejected = []
    if rej.exists():
        rejected = [json.loads(l) for l in rej.read_text(encoding="utf-8").splitlines() if l.strip()]
        rejected = [r for r in rejected if start.timestamp() <= r.get("at", 0) < end.timestamp()]
    lines = [f"📊 تقرير {start:%Y-%m-%d}: نُشر {len(hist)} منشوراً"]
    for c, (label, lo, _, _) in CATEGORIES.items():
        n = counts.get(c, 0)
        lines.append(f"{'✅' if n >= lo else '⚠️'} {label}: {n}")
    if rejected:
        lines.append(f"\n🚫 لم يُنشر: {len(rejected)}")
        for r in rejected[:5]:
            lines.append(f"• {r['id']}: {(r.get('reason') or ['?'])[0][:70]}")
    try:
        from .store import Store
        bad = [r["name"] for r in Store(root / "data" / "dtdz.sqlite").health() if r["disabled"]]
        if bad:
            lines.append(f"\n⛔ مصادر معطلة ({len(bad)}): " + "، ".join(bad[:12]))
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(lines)


def maybe_daily_report(bot, root: Path, admin: int, store) -> None:
    now = datetime.now(TZ)
    key = f"report:{now:%Y-%m-%d}"
    if admin and now.hour >= 8 and not store.get(key)[0]:
        store.put(key, 1)
        try:
            from .facebook import joins_report
            import os
            extra = joins_report(bot, os.environ.get("CHANNEL", ""), store)
            bot.send_message(admin, daily_report(root) + (f"\n{extra}" if extra else ""))
        except Exception as exc:  # noqa: BLE001
            log.warning("report failed: %s", exc)
