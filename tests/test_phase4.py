import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dtdz import runner as R
from dtdz.telegram import Bot, TelegramError, TelegramSender


def fake_bot(handler):
    return Bot("123:ABC", httpx.Client(transport=httpx.MockTransport(handler)))


def test_send_photo_posts_caption_and_returns_id(tmp_path):
    seen = {}

    def handler(req):
        seen["path"] = req.url.path
        seen["body"] = req.content
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 77}})

    img = tmp_path / "c.png"
    img.write_bytes(b"\x89PNG fake")
    mid = TelegramSender(fake_bot(handler), "@DeeptechDZ").send({"text": "نص المنشور"}, img)
    assert mid == "77"
    assert seen["path"].endswith("/sendPhoto")
    assert "نص المنشور".encode() in seen["body"] and b"@DeeptechDZ" in seen["body"]


def test_api_error_raises():
    bot = fake_bot(lambda req: httpx.Response(400, json={"ok": False, "description": "chat not found"}))
    with pytest.raises(TelegramError, match="chat not found"):
        bot.send_message("@x", "hi")


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("CHANNEL", "@DeeptechDZ")
    monkeypatch.setenv("ADMIN_ID", "42")
    monkeypatch.setattr(R, "ROOT", tmp_path)
    monkeypatch.setattr(R, "DATA", tmp_path / "data")
    (tmp_path / "data").mkdir()
    (tmp_path / "queue" / "posts").mkdir(parents=True)
    return R.Runner()


def test_admin_commands(runner, tmp_path):
    assert runner.command("/id", 999) == "معرّفك: 999"
    assert runner.command("/pause", 999) is None                       # strangers are ignored
    assert "متوقف" in runner.command("/pause", 42)
    assert (tmp_path / "data" / "PAUSED").exists()
    assert "متوقف ⏸" in runner.command("/status", 42)
    runner.command("/resume", 42)
    assert not (tmp_path / "data" / "PAUSED").exists()
    assert runner.command("/queue", 42) == "لا منشورات قادمة."
    assert runner.command("/health", 42) == "كل المصادر تعمل."
