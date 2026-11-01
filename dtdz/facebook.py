"""Cross-post the best channel posts to the Deeptech DZ Facebook Page.

Facebook punishes pages that post 40 times a day, so only a selection goes there:
  - categories people share (free stuff, courses, scholarships, visas, breaking, discoveries, apps…)
  - at most FB_MAX_PER_DAY posts, at least FB_GAP_MIN minutes apart (breaking news skips the gap)
Each Facebook post = the same card image + the text without Telegram formatting + a line that
invites readers to the Telegram channel through a tracked invite link (named "facebook"), so the
daily report can say how many subscribers Facebook brought.

Needs two repository secrets: FB_PAGE_ID and FB_PAGE_TOKEN (a Page access token with
pages_manage_posts). Without them this module does nothing.
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

log = logging.getLogger("dtdz.facebook")
GRAPH = "https://graph.facebook.com/v23.0"
TZ = timezone(timedelta(hours=1))
FB_MAX_PER_DAY = int(os.environ.get("FB_MAX_PER_DAY", "10"))
FB_GAP_MIN = int(os.environ.get("FB_GAP_MIN", "60"))
SHARE_FIRST = ("breaking", "free", "course", "study", "visa", "discovery", "app", "site", "tool", "trend", "film", "sport")


def configured() -> bool:
    return bool(os.environ.get("FB_PAGE_ID") and os.environ.get("FB_PAGE_TOKEN"))


def caption(post: dict, invite: str) -> str:
    """Telegram text -> Facebook text: no ** markers, no channel signature, invite at the end."""
    text = post["text"].replace("**", "")
    lines = [l for l in text.rstrip().split("\n") if not l.strip().startswith("◆")]
    body = "\n".join(lines).rstrip()
    return f"{body}\n\n📲 كل الأخبار والروابط أولاً بأول على قناتنا في تيليجرام:\n{invite}"


def invite_link(bot, channel: str, store) -> str:
    """A named invite link for Facebook (counts who joined from it); public link as fallback."""
    cached = store.get("invite:facebook")[0]
    if cached:
        return cached
    try:
        r = bot.call("createChatInviteLink", chat_id=channel, name="facebook")
        link = r["invite_link"]
    except Exception as exc:  # noqa: BLE001 — bot may lack the invite right
        log.warning("invite link failed: %s", exc)
        link = "https://t.me/" + channel.lstrip("@")
        return link
    store.put("invite:facebook", link)
    return link


def should_share(post: dict, store, now: float | None = None) -> bool:
    now = now or time.time()
    cat = post.get("category") or post.get("type")
    breaking = bool(post.get("breaking")) or cat == "breaking"
    if not breaking and cat not in SHARE_FIRST and cat != "news":
        return False
    day = datetime.fromtimestamp(now, TZ).strftime("%Y-%m-%d")
    count = store.get(f"fb:count:{day}")[0] or 0
    if count >= FB_MAX_PER_DAY:
        return False
    last = store.get("fb:last")[0] or 0
    if not breaking and now - last < FB_GAP_MIN * 60:
        return False
    if cat == "news" and not breaking and count >= FB_MAX_PER_DAY // 2:
        return False           # plain news fills at most half of the day's Facebook posts
    return True


def publish(post: dict, image: Path, invite: str) -> str:
    page, token = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
    with open(image, "rb") as fh:
        r = httpx.post(f"{GRAPH}/{page}/photos", timeout=60,
                       data={"caption": caption(post, invite), "published": "true", "access_token": token},
                       files={"source": (image.name, fh, "image/png")})
    data = r.json()
    if r.status_code != 200 or "id" not in data:
        raise RuntimeError(f"Facebook: {data.get('error', {}).get('message', r.text[:200])}")
    return data.get("post_id") or data["id"]


def maybe_share(bot, channel: str, store, post: dict, image: Path, now: float | None = None) -> str | None:
    """Called right after a post went out on Telegram. Returns the Facebook post id or None."""
    if not configured() or not should_share(post, store, now):
        return None
    now = now or time.time()
    try:
        fid = publish(post, image, invite_link(bot, channel, store))
    except Exception as exc:  # noqa: BLE001 — Facebook problems never block Telegram
        log.warning("facebook post failed %s: %s", post.get("id"), exc)
        store.put("fb:last_error", str(exc)[:300])
        return None
    day = datetime.fromtimestamp(now, TZ).strftime("%Y-%m-%d")
    store.put(f"fb:count:{day}", (store.get(f"fb:count:{day}")[0] or 0) + 1)
    store.put("fb:last", now)
    log.info("facebook: %s -> %s", post.get("id"), fid)
    return fid


def joins_report(bot, channel: str, store) -> str | None:
    """How many people joined through the Facebook invite link (Telegram counts it)."""
    link = store.get("invite:facebook")[0]
    if not link:
        return None
    try:
        r = bot.call("editChatInviteLink", chat_id=channel, invite_link=link, name="facebook")
        return f"📘 انضموا من فيسبوك: {r.get('member_count', 0)}"
    except Exception:  # noqa: BLE001
        return None
