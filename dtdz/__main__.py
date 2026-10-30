"""Command line.

  python -m dtdz collect   [--sources sources.yaml] [--db data/dtdz.sqlite]
  python -m dtdz export    [--db ...] [--out queue/candidates.json] [--history queue/history.jsonl]
  python -m dtdz check     POSTS.json [--candidates ...] [--history ...]   (exit 1 if any post fails)
  python -m dtdz health    [--db ...]
  python -m dtdz render    POSTS.json [--outbox data/outbox]                (cards only)
  python -m dtdz publish   --dry-run [--outbox data/outbox]                 (one scheduler tick)
  python -m dtdz queue                                                      (upcoming posts)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dtdz")
    ap.add_argument("cmd", choices=["collect", "export", "check", "health", "render", "publish", "queue"])
    ap.add_argument("posts", nargs="?")
    ap.add_argument("--sources", default=ROOT / "sources.yaml")
    ap.add_argument("--db", default=ROOT / "data" / "dtdz.sqlite")
    ap.add_argument("--out", default=ROOT / "queue" / "candidates.json")
    ap.add_argument("--candidates", default=ROOT / "queue" / "candidates.json")
    ap.add_argument("--history", default=ROOT / "queue" / "history.jsonl")
    ap.add_argument("--banned", default=ROOT / "banned_phrases.txt")
    ap.add_argument("--outbox", default=ROOT / "data" / "outbox")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    Path(a.db).parent.mkdir(parents=True, exist_ok=True)

    if a.cmd == "collect":
        from .collect import collect
        print(json.dumps(asyncio.run(collect(a.sources, a.db)), ensure_ascii=False))
    elif a.cmd == "export":
        from .cluster import export
        print(json.dumps(export(a.db, a.out, a.history), ensure_ascii=False))
    elif a.cmd == "health":
        from .store import Store
        for row in Store(a.db).health():
            print(row)
    elif a.cmd == "render":
        from .card import render
        for p in json.loads(Path(a.posts).read_text(encoding="utf-8")):
            print(render(p, Path(a.outbox) / f"{p['id']}.png"))
    elif a.cmd == "publish":
        from .publisher import DryRunSender, run_once
        if not a.dry_run:
            ap.error("the Telegram sender arrives in phase 4; use --dry-run")
        print(json.dumps(run_once(ROOT, DryRunSender(a.outbox)), ensure_ascii=False))
    elif a.cmd == "queue":
        from .publisher import upcoming
        for p in upcoming(ROOT):
            print(p["slot"], p["type"].ljust(6), p["first_line"][:70])
    elif a.cmd == "check":
        from .gate import check_file
        if not a.posts:
            ap.error("check needs a posts file")
        res = check_file(a.posts, a.candidates, a.banned, a.history)
        bad = {k: v for k, v in res.items() if v}
        for pid, errs in res.items():
            print(("FAIL " if errs else "OK   ") + pid)
            for e in errs:
                print("     - " + e)
        print(f"{len(res) - len(bad)}/{len(res)} posts pass")
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
