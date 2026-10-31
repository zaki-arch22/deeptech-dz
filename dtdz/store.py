"""SQLite storage: collected items, source health, small key/value snapshots."""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, asdict
from hashlib import sha1
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY, source TEXT, grp TEXT, trust INTEGER, url TEXT, title TEXT,
  text TEXT, published REAL, fetched REAL, lang TEXT, extra TEXT
);
CREATE INDEX IF NOT EXISTS items_published ON items(published);
CREATE TABLE IF NOT EXISTS sources (
  name TEXT PRIMARY KEY, fails INTEGER DEFAULT 0, disabled INTEGER DEFAULT 0,
  last_ok REAL, last_error TEXT
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT, updated REAL);
"""


@dataclass
class Item:
    source: str
    grp: str
    trust: int
    url: str
    title: str
    text: str
    published: float
    lang: str = "en"
    extra: dict | None = None

    @property
    def id(self) -> str:
        return sha1(self.url.encode()).hexdigest()[:16]


class Store:
    def __init__(self, path: str | Path):
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # items
    def has(self, item_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM items WHERE id=?", (item_id,)).fetchone() is not None

    def add(self, it: Item) -> bool:
        cur = self.db.execute(
            "INSERT OR IGNORE INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (it.id, it.source, it.grp, it.trust, it.url, it.title, it.text, it.published,
             time.time(), it.lang, json.dumps(it.extra or {}, ensure_ascii=False)),
        )
        self.db.commit()
        return cur.rowcount == 1

    def recent(self, hours: float, now: float | None = None) -> list[Item]:
        since = (now or time.time()) - hours * 3600
        rows = self.db.execute("SELECT * FROM items WHERE published>=? ORDER BY published", (since,))
        return [Item(r["source"], r["grp"], r["trust"], r["url"], r["title"], r["text"],
                     r["published"], r["lang"], json.loads(r["extra"] or "{}")) for r in rows]

    def prune(self, days: int = 14) -> None:
        self.db.execute("DELETE FROM items WHERE published < ?", (time.time() - days * 86400,))
        self.db.execute("DELETE FROM kv WHERE (k LIKE 'cluster:%' OR k LIKE 'enriched:%') AND updated < ?",
                        (time.time() - 4 * 86400,))
        self.db.commit()

    # source health
    def source_ok(self, name: str) -> None:
        self.db.execute(
            "INSERT INTO sources(name,fails,last_ok) VALUES(?,0,?) "
            "ON CONFLICT(name) DO UPDATE SET fails=0,last_ok=excluded.last_ok,last_error=NULL",
            (name, time.time()))
        self.db.commit()

    def source_fail(self, name: str, err: str, disable_after: int | None) -> bool:
        self.db.execute(
            "INSERT INTO sources(name,fails,last_error) VALUES(?,1,?) "
            "ON CONFLICT(name) DO UPDATE SET fails=fails+1,last_error=excluded.last_error",
            (name, err[:300]))
        fails = self.db.execute("SELECT fails FROM sources WHERE name=?", (name,)).fetchone()[0]
        disabled = disable_after is not None and fails >= disable_after
        if disabled:
            self.db.execute("UPDATE sources SET disabled=1 WHERE name=?", (name,))
        self.db.commit()
        return disabled

    def disabled(self, name: str) -> bool:
        r = self.db.execute("SELECT disabled FROM sources WHERE name=?", (name,)).fetchone()
        return bool(r and r[0])

    def health(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM sources ORDER BY fails DESC, name")]

    # snapshots
    def put(self, k: str, v) -> None:
        self.db.execute("INSERT OR REPLACE INTO kv VALUES(?,?,?)",
                        (k, json.dumps(v, ensure_ascii=False), time.time()))
        self.db.commit()

    def get(self, k: str):
        r = self.db.execute("SELECT v, updated FROM kv WHERE k=?", (k,)).fetchone()
        return (json.loads(r[0]), r[1]) if r else (None, None)


def item_dict(it: Item) -> dict:
    d = asdict(it)
    d["id"] = it.id
    return d
