"""One cloud tick (GitHub Actions, every few minutes): no computer needed.

  collect + export (if the last one is older than COLLECT_EVERY_MIN)
  publish every due post (gate re-check inside run_once)
  answer admin commands received since the last tick
  commit queue/ changes back to the repository (done by the workflow)

State that must survive between ticks:
  - in git (queue/): candidates, posts, history, rejected, PAUSED flag, cloud.enabled
  - in the Actions cache (data/): sqlite (items, source health, cluster cache, kv), logos, photos
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

from .cluster import export
from .collect import collect
from .publisher import run_once
from .store import Store
from .telegram import Bot, TelegramSender

log = logging.getLogger("dtdz.cloud")
ROOT = Path(__file__).resolve().parent.parent
DATA, QUEUE = ROOT / "data", ROOT / "queue"
COLLECT_EVERY = int(os.environ.get("COLLECT_EVERY_MIN", "30")) * 60
MAX_POSTS_PER_TICK = 3


def tell(bot: Bot, admin: int, text: str) -> None:
    if admin:
        try:
            bot.send_message(admin, text[:4000])
        except Exception as exc:  # noqa: BLE001
            log.warning("admin message failed: %s", exc)


def sync_pause_flag(to_repo: bool) -> None:
    repo_flag, data_flag = QUEUE / "PAUSED", DATA / "PAUSED"
    if to_repo:
        if data_flag.exists():
            repo_flag.touch()
        else:
            repo_flag.unlink(missing_ok=True)
    else:
        if repo_flag.exists():
            data_flag.touch()
        else:
            data_flag.unlink(missing_ok=True)


def admin_commands(bot: Bot, store: Store, admin: int) -> None:
    """Handle commands received since the last tick (no long polling in the cloud)."""
    from . import runner as R
    offset = (store.get("tg_offset")[0]) or None
    try:
        updates = bot.updates(offset, timeout=0)
    except Exception as exc:  # noqa: BLE001
        log.warning("getUpdates failed: %s", exc)
        return
    r = R.Runner.__new__(R.Runner)          # reuse the command handler without starting loops
    r.admin, r.sync, r.last_collect = admin, True, (store.get("last_collect")[0] or 0)
    r.last_collect_stats = store.get("last_collect_stats")[0] or {}
    from .admin import handle_update
    for u in updates:
        offset = u["update_id"] + 1
        try:
            extra = handle_update(bot, ROOT, admin, u, os.environ.get("CHANNEL", ""))
        except Exception as exc:  # noqa: BLE001
            extra = None
            log.warning("admin update failed: %s", exc)
        if extra:
            tell(bot, admin, extra)
            continue
        msg = u.get("message") or {}
        text, uid = (msg.get("text") or "").strip(), (msg.get("from") or {}).get("id")
        if text.startswith("/"):
            reply = r.command(text.split()[0].split("@")[0], uid)
            if reply:
                try:
                    bot.send_message(msg["chat"]["id"], reply + "\n☁️ يعمل من السحابة")
                except Exception as exc:  # noqa: BLE001
                    log.warning("reply failed: %s", exc)
    if offset:
        store.put("tg_offset", offset)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    token, channel = os.environ.get("BOT_TOKEN"), os.environ.get("CHANNEL")
    admin = int(os.environ.get("ADMIN_ID") or 0)
    if not token or not channel:
        log.error("BOT_TOKEN / CHANNEL not configured (repository secrets) — nothing to do")
        return 0
    DATA.mkdir(exist_ok=True)
    store = Store(DATA / "dtdz.sqlite")
    bot = Bot(token)
    sync_pause_flag(to_repo=False)

    first = not (ROOT / "cloud.enabled").exists()
    if first:
        # hand-over: the PC bot sees this file on its next pull and stops publishing
        (ROOT / "cloud.enabled").write_text("Publishing runs on GitHub Actions.\n", encoding="utf-8")
        tell(bot, admin, "☁️ Deeptech DZ انتقل إلى السحابة: النشر يعمل الآن دون الحاجة إلى الحاسوب.")

    now = time.time()
    last = store.get("last_collect")[0] or 0
    if now - last >= COLLECT_EVERY or not (QUEUE / "candidates.json").exists():
        try:
            stats = asyncio.run(collect(ROOT / "sources.yaml", DATA / "dtdz.sqlite"))
            exp = export(DATA / "dtdz.sqlite", QUEUE / "candidates.json", QUEUE / "history.jsonl")
            store.put("last_collect", now)
            store.put("last_collect_stats", stats | exp)
            log.info("collect %s %s", stats, exp)
            if stats["disabled"]:
                tell(bot, admin, "🔧 مصادر عُطّلت بعد 3 إخفاقات: " + "، ".join(stats["disabled"]))
        except Exception as exc:  # noqa: BLE001
            log.exception("collect failed: %s", exc)

    if not first:   # publish from the second tick on, so the PC has time to stand down
        sender = TelegramSender(bot, channel)
        for i in range(MAX_POSTS_PER_TICK):
            stats = run_once(ROOT, sender)
            from .facebook import maybe_share
            for post, image in stats.get("sent_posts", []):
                maybe_share(bot, channel, store, post, image)
            for pid in stats["rejected"]:
                tell(bot, admin, f"⛔ رفضت البوابة المنشور {pid}. الأسباب في queue/rejected.jsonl")
            if stats["skipped"]:
                tell(bot, admin, "⏭ فات موعد: " + "، ".join(stats["skipped"]))
            if not (stats["sent"] or stats["rejected"] or stats["skipped"]):
                break
            if stats["sent"] and i + 1 < MAX_POSTS_PER_TICK:
                time.sleep(20)

    admin_commands(bot, store, admin)
    from .admin import maybe_daily_report, send_previews
    send_previews(bot, ROOT, admin)
    maybe_daily_report(bot, ROOT, admin, store)
    sync_pause_flag(to_repo=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
