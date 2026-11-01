"""Scheduler + publisher. Runs on the PC every minute.

For each post whose slot has arrived: re-check it with the gate (the history may have
changed since it was written), render its card, send it, then record it in history.
Posts more than GRACE late (PC was off) are skipped, never sent in a burst.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .card import render
from .gate import check_post, history_entry, load_banned, load_history
from .store import Store

log = logging.getLogger("dtdz.publisher")
GRACE_MIN = 90


class Sender(Protocol):
    def send(self, post: dict, image: Path) -> str: ...


class DryRunSender:
    """Writes what would be posted into an outbox folder."""

    def __init__(self, outbox: str | Path):
        self.outbox = Path(outbox)

    def send(self, post: dict, image: Path) -> str:
        self.outbox.mkdir(parents=True, exist_ok=True)
        (self.outbox / f"{post['id']}.txt").write_text(post["text"], encoding="utf-8")
        target = self.outbox / f"{post['id']}.png"
        target.write_bytes(image.read_bytes())
        return f"dry-{post['id']}"


def _ts(slot: str) -> float:
    return datetime.fromisoformat(slot).timestamp()


def load_queue(posts_dir: str | Path) -> list[dict]:
    posts = {}
    for f in sorted(Path(posts_dir).glob("*.json")):
        try:
            for p in json.loads(f.read_text(encoding="utf-8")):
                posts[p["id"]] = p  # a later file replaces an earlier draft of the same slot
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            log.error("bad posts file %s: %s", f.name, exc)
    return sorted(posts.values(), key=lambda p: p.get("slot", ""))


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _done_ids(*paths: Path) -> set[str]:
    ids = set()
    for p in paths:
        if p.exists():
            ids.update(json.loads(l)["id"] for l in p.read_text(encoding="utf-8").splitlines() if l.strip())
    return ids


def normalize_signature(text: str) -> str:
    """Every post ends with exactly the channel signature, whatever the writer typed."""
    import re
    from .gate import SIGNATURE
    text = re.sub(r"(?<![\w/])#[\w_]+", "", text)            # no hashtags, ever
    lines = [l.rstrip() for l in text.rstrip().split("\n")]
    if lines and lines[-1].strip().startswith("◆"):
        lines[-1] = SIGNATURE
    elif lines[-1].strip() != SIGNATURE:
        lines += ["", SIGNATURE]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines))


def run_once(root: str | Path, sender: Sender, now: float | None = None) -> dict:
    root = Path(root)
    now = now or time.time()
    q = root / "queue"
    hist_p, rej_p = q / "history.jsonl", q / "rejected.jsonl"
    stats = {"sent": [], "rejected": [], "skipped": [], "paused": False, "sent_posts": []}
    if (root / "data" / "PAUSED").exists():
        stats["paused"] = True
        return stats

    done = _done_ids(hist_p, rej_p)
    from .admin import load_overrides
    ovr = load_overrides(root)
    for pid in ovr["cancel"]:
        if pid not in done:
            _append(rej_p, {"id": pid, "at": now, "reason": ["cancelled by admin"]})
            done.add(pid)
    forced = set(ovr["now"])
    due = [p for p in load_queue(q / "posts") if p.get("id") not in done and p.get("slot")
           and (_ts(p["slot"]) <= now or p["id"] in forced)]
    for p in due:
        if p["id"] in forced:
            p["slot"] = datetime.fromtimestamp(now, timezone.utc).isoformat()
    if not due:
        return stats

    store = Store(root / "data" / "dtdz.sqlite")
    cands_p = q / "candidates.json"
    clusters = ({c["id"]: c for c in json.loads(cands_p.read_text(encoding="utf-8"))["clusters"]}
                if cands_p.exists() else {})
    banned = load_banned(root / "banned_phrases.txt")
    history = load_history(hist_p)

    for post in due:
        late_min = (now - _ts(post["slot"])) / 60
        if late_min > GRACE_MIN:
            _append(rej_p, {"id": post["id"], "at": now, "reason": [f"skipped: {late_min:.0f} min late"]})
            stats["skipped"].append(post["id"])
            continue
        from .gate import web_cluster
        cluster = (clusters.get(post.get("cluster_id")) or store.get(f"cluster:{post.get('cluster_id')}")[0]
                   or web_cluster(post))
        post["text"] = normalize_signature(post["text"])
        errs = check_post(post, cluster, banned, history, now, strict=False)
        if errs:
            _append(rej_p, {"id": post["id"], "at": now, "reason": errs})
            stats["rejected"].append(post["id"])
            log.warning("rejected %s: %s", post["id"], errs)
            continue
        image = render(post, root / "data" / "cards" / f"{post['id']}.png", cluster)
        try:
            msg_id = sender.send(post, image)
        except Exception as exc:  # noqa: BLE001 — retried next minute, inside the grace window
            log.error("send failed %s: %s", post["id"], exc)
            continue
        entry = history_entry(post, cluster, now) | {"message_id": msg_id}
        _append(hist_p, entry)
        history.append(entry)
        stats["sent"].append(post["id"])
        stats["sent_posts"].append((post, image))
        break  # at most one post per minute, even if several slots are due
    return stats


def upcoming(root: str | Path, now: float | None = None) -> list[dict]:
    """Planned posts, for the admin /queue view in phase 4."""
    root, now = Path(root), now or time.time()
    q = root / "queue"
    done = _done_ids(q / "history.jsonl", q / "rejected.jsonl")
    return [{"id": p["id"], "slot": p["slot"], "type": p["type"], "first_line": p["text"].split("\n")[0]}
            for p in load_queue(q / "posts") if p["id"] not in done and _ts(p["slot"]) > now]
