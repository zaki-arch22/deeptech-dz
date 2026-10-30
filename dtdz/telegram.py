"""Minimal Telegram Bot API client (no framework needed for one channel and one admin)."""
from __future__ import annotations

from pathlib import Path

import httpx

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(RuntimeError):
    pass


class Bot:
    def __init__(self, token: str, client: httpx.Client | None = None):
        self.token = token
        self.http = client or httpx.Client(timeout=60)

    def call(self, method: str, files: dict | None = None, **params):
        r = self.http.post(API.format(token=self.token, method=method), data=params, files=files)
        try:
            body = r.json()
        except ValueError as exc:
            raise TelegramError(f"{method}: HTTP {r.status_code}") from exc
        if not body.get("ok"):
            raise TelegramError(f"{method}: {body.get('description', r.status_code)}")
        return body["result"]

    def send_message(self, chat_id, text: str, **kw):
        return self.call("sendMessage", chat_id=chat_id, text=text, disable_web_page_preview="true", **kw)

    def send_photo(self, chat_id, photo: Path, caption: str, html: bool = False):
        extra = {"parse_mode": "HTML"} if html else {}
        with open(photo, "rb") as fh:
            return self.call("sendPhoto", files={"photo": (photo.name, fh, "image/png")},
                             chat_id=chat_id, caption=caption, **extra)

    def updates(self, offset: int | None, timeout: int = 25) -> list[dict]:
        params = {"timeout": timeout, "allowed_updates": '["message"]'}
        if offset is not None:
            params["offset"] = offset
        return self.call("getUpdates", **params)


class TelegramSender:
    """Publisher sender: one photo post per item, card as the photo, post text as caption."""

    def __init__(self, bot: Bot, channel: str):
        self.bot, self.channel = bot, channel

    def send(self, post: dict, image: Path) -> str:
        msg = self.bot.send_photo(self.channel, image, to_html(post["text"]), html=True)
        return str(msg["message_id"])


def to_html(text: str) -> str:
    """Post text -> Telegram HTML: escape everything, then **bold** -> <b>bold</b>."""
    import html
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(text, quote=False), flags=re.S)
