"""The always-on process on the PC (Docker): collect, sync with GitHub, publish, answer the admin.

Loops:
  - every COLLECT_EVERY_MIN: collect sources -> export candidates -> push to GitHub
  - every minute: pull new posts -> publish what is due -> push history
  - continuously: admin commands in a private chat with the bot
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .cluster import export
from .collect import collect
from .publisher import run_once, upcoming
from .store import Store
from .telegram import Bot, TelegramSender

log = logging.getLogger("dtdz.runner")
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SSH_KEY = DATA / "ssh" / "id_ed25519"
TZ = ZoneInfo("Africa/Algiers")


# ---------------- git ----------------

def ensure_ssh_key() -> str:
    if not SSH_KEY.exists():
        SSH_KEY.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "deeptech-dz-pc", "-f", str(SSH_KEY)],
                       check=True, capture_output=True)
    return (SSH_KEY.with_suffix(".pub")).read_text().strip()


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = os.environ | {
        "GIT_SSH_COMMAND": f"ssh -i {SSH_KEY} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new "
                           f"-o UserKnownHostsFile={SSH_KEY.parent / 'known_hosts'}",
        "GIT_AUTHOR_NAME": "Deeptech DZ PC", "GIT_AUTHOR_EMAIL": "pc@deeptech-dz.local",
        "GIT_COMMITTER_NAME": "Deeptech DZ PC", "GIT_COMMITTER_EMAIL": "pc@deeptech-dz.local",
    }
    return subprocess.run(["git", *args], cwd=ROOT, env=env, check=check, capture_output=True, text=True,
                          timeout=120)


def ensure_ssh_remote() -> None:
    """The deploy key works over SSH only: turn an https origin into its SSH form."""
    url = git("remote", "get-url", "origin", check=False).stdout.strip()
    if url.startswith("https://github.com/"):
        repo = url.removeprefix("https://github.com/").removesuffix(".git")
        git("remote", "set-url", "origin", f"git@github.com:{repo}.git")


def git_ready() -> bool:
    return git("ls-remote", "-q", "origin", "HEAD", check=False).returncode == 0


def git_pull() -> None:
    git("pull", "--rebase", "--autostash", "-q", check=False)


def git_push(paths: list[str], message: str) -> None:
    git("add", *paths)
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        return
    git("commit", "-q", "-m", message)
    for _ in range(3):
        if git("push", "-q", check=False).returncode == 0:
            return
        git_pull()
    log.error("git push failed after retries")


# ---------------- runner ----------------

class Runner:
    def __init__(self):
        self.token = os.environ["BOT_TOKEN"]
        self.channel = os.environ["CHANNEL"]
        self.admin = int(os.environ.get("ADMIN_ID") or 0)
        self.collect_every = int(os.environ.get("COLLECT_EVERY_MIN", "30")) * 60
        self.bot = Bot(self.token)
        self.poller = Bot(self.token)          # separate connection for long polling
        self.sender = TelegramSender(self.bot, self.channel)
        self.sync = False
        self.last_collect = 0.0
        self.last_collect_stats: dict = {}
        self.warned: set[str] = set()

    # -- helpers
    async def tell_admin(self, text: str) -> None:
        if not self.admin:
            log.info("admin message (ADMIN_ID not set): %s", text)
            return
        try:
            await asyncio.to_thread(self.bot.send_message, self.admin, text[:4000])
        except Exception as exc:  # noqa: BLE001
            log.warning("cannot message admin: %s", exc)

    async def check_sync(self) -> None:
        ok = await asyncio.to_thread(git_ready)
        if ok and not self.sync:
            # first connection: publish the local history to the (possibly empty) repository
            await asyncio.to_thread(git, "push", "-u", "-q", "origin", "main", check=False)
            await self.tell_admin("✅ الربط مع GitHub يعمل. النشر الآلي جاهز.")
        if not ok and "sync" not in self.warned:
            key = ensure_ssh_key()
            await self.tell_admin("⚠️ الربط مع GitHub غير مفعّل بعد.\nأرسل هذا المفتاح العام إلى Claude ليضيفه "
                                  "إلى المستودع (مفتاح عام، ليس سراً):\n\n" + key)
            self.warned.add("sync")
        self.sync = ok

    # -- loops
    async def collect_loop(self) -> None:
        while True:
            try:
                if not self.sync:
                    await self.check_sync()
                if self.sync:
                    await asyncio.to_thread(git_pull)
                stats = await collect(ROOT / "sources.yaml", DATA / "dtdz.sqlite")
                exp = await asyncio.to_thread(export, DATA / "dtdz.sqlite", ROOT / "queue" / "candidates.json",
                                              ROOT / "queue" / "history.jsonl")
                self.last_collect, self.last_collect_stats = time.time(), stats | exp
                log.info("collect %s", self.last_collect_stats)
                if stats["disabled"]:
                    await self.tell_admin("🔧 مصادر عُطّلت بعد 3 إخفاقات: " + "، ".join(stats["disabled"]))
                if self.sync:
                    await asyncio.to_thread(git_push, ["queue/candidates.json"], "candidates")
            except Exception as exc:  # noqa: BLE001
                log.exception("collect loop: %s", exc)
            await asyncio.sleep(self.collect_every)

    async def publish_loop(self) -> None:
        while True:
            try:
                if self.sync:
                    await asyncio.to_thread(git_pull)
                stats = await asyncio.to_thread(run_once, ROOT, self.sender)
                if stats["sent"] or stats["rejected"] or stats["skipped"]:
                    if self.sync:
                        await asyncio.to_thread(git_push, ["queue/history.jsonl", "queue/rejected.jsonl"],
                                                "publish log")
                for pid in stats["rejected"]:
                    await self.tell_admin(f"⛔ رفضت البوابة المنشور {pid}. الأسباب في queue/rejected.jsonl")
                if stats["skipped"]:
                    await self.tell_admin("⏭ فات موعد: " + "، ".join(stats["skipped"]) + " (كان الجهاز متوقفاً؟)")
                await self.watchdog()
            except Exception as exc:  # noqa: BLE001
                log.exception("publish loop: %s", exc)
            await asyncio.sleep(60)

    async def watchdog(self) -> None:
        now = datetime.now(TZ)
        key = now.strftime("%Y-%m-%d-%H")
        if now.hour in (9, 14, 20) and now.minute < 5 and key not in self.warned:
            if not upcoming(ROOT):
                self.warned.add(key)
                await self.tell_admin("🕳 لا منشورات مجدولة قادمة. هل المهمة المجدولة تعمل؟")

    async def admin_loop(self) -> None:
        offset = None
        while True:
            try:
                updates = await asyncio.to_thread(self.poller.updates, offset)
            except Exception as exc:  # noqa: BLE001
                log.warning("getUpdates: %s", exc)
                await asyncio.sleep(10)
                continue
            for u in updates:
                offset = u["update_id"] + 1
                msg = u.get("message") or {}
                text, uid = (msg.get("text") or "").strip(), (msg.get("from") or {}).get("id")
                if not text.startswith("/"):
                    continue
                reply = self.command(text.split()[0].split("@")[0], uid)
                if reply:
                    try:
                        await asyncio.to_thread(self.bot.send_message, msg["chat"]["id"], reply)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("reply failed: %s", exc)

    def command(self, cmd: str, uid: int) -> str | None:
        if cmd == "/id":
            return f"معرّفك: {uid}"
        if not self.admin or uid != self.admin:
            return None
        paused = DATA / "PAUSED"
        if cmd == "/pause":
            paused.touch()
            return "⏸ النشر متوقف. /resume للاستئناف."
        if cmd == "/resume":
            paused.unlink(missing_ok=True)
            return "▶️ استُؤنف النشر."
        if cmd == "/queue":
            items = upcoming(ROOT)
            if not items:
                return "لا منشورات قادمة."
            return "\n".join(f"{datetime.fromisoformat(p['slot']).astimezone(TZ):%d/%m %H:%M} · {p['type']} · "
                             f"{p['first_line'][:60]}" for p in items[:12])
        if cmd == "/health":
            bad = [r for r in Store(DATA / "dtdz.sqlite").health() if r["fails"] or r["disabled"]]
            if not bad:
                return "كل المصادر تعمل."
            return "\n".join(f"{'⛔' if r['disabled'] else '⚠️'} {r['name']}: {r['fails']} إخفاق" for r in bad)
        if cmd in ("/status", "/start"):
            ago = int((time.time() - self.last_collect) / 60) if self.last_collect else None
            return "\n".join([
                "Deeptech DZ",
                f"النشر: {'متوقف ⏸' if paused.exists() else 'يعمل ▶️'}",
                f"GitHub: {'متصل' if self.sync else 'غير متصل'}",
                f"آخر تجميع: {'منذ ' + str(ago) + ' د' if ago is not None else 'لم يتم بعد'}",
                f"عناصر جديدة: {self.last_collect_stats.get('new', '—')} · مجموعات: "
                f"{self.last_collect_stats.get('clusters', '—')}",
                f"منشورات قادمة: {len(upcoming(ROOT))}",
                "/queue · /health · /pause · /resume",
            ])
        return None

    async def run(self) -> None:
        ensure_ssh_key()
        ensure_ssh_remote()
        await self.check_sync()
        await asyncio.gather(self.collect_loop(), self.publish_loop(), self.admin_loop())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(Runner().run())


if __name__ == "__main__":
    main()
