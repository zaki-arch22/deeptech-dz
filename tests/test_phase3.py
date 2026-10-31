import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from dtdz.card import _isolate, headline, render
from dtdz.gate import check_post, load_banned
from dtdz.publisher import DryRunSender, run_once, upcoming
from dtdz.store import Store
from test_pipeline import GOOD, cluster, post

ROOT = Path(__file__).resolve().parent.parent
SLOT = "2026-10-31T08:30:00+01:00"
T0 = datetime.fromisoformat(SLOT).timestamp()


def setup_root(tmp_path, posts, with_candidates=True):
    (tmp_path / "queue" / "posts").mkdir(parents=True)
    (tmp_path / "data").mkdir()
    (tmp_path / "banned_phrases.txt").write_text((ROOT / "banned_phrases.txt").read_text(encoding="utf-8"),
                                                 encoding="utf-8")
    (tmp_path / "queue" / "posts" / "batch.json").write_text(json.dumps(posts, ensure_ascii=False),
                                                              encoding="utf-8")
    if with_candidates:
        (tmp_path / "queue" / "candidates.json").write_text(
            json.dumps({"generated_at": "", "clusters": [cluster()]}), encoding="utf-8")
    return tmp_path


def hist(root):
    p = root / "queue" / "history.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def test_card_renders_1280x720(tmp_path):
    out = render(post(), tmp_path / "c.png")
    assert Image.open(out).size == (1280, 720)


def test_headline_and_bidi():
    assert headline("🚨 خبر مهم!\nبقية") == "خبر مهم!"
    assert _isolate("بنسبة 40% و $67,012 و Orbit 3") == "بنسبة ⁦40%⁩ و ⁦$67,012⁩ و Orbit 3"


def test_caption_limit():
    long = GOOD.replace("الأرقام جميلة", "الأرقام جميلة " + "كلام " * 200)
    errs = check_post(post(long), cluster(), load_banned(ROOT / "banned_phrases.txt"), [], T0)
    assert any("Telegram caption" in e for e in errs)


def test_publishes_due_post_once(tmp_path):
    root = setup_root(tmp_path, [post()])
    out = tmp_path / "outbox"
    assert run_once(root, DryRunSender(out), T0 - 60)["sent"] == []          # not yet
    assert run_once(root, DryRunSender(out), T0 + 30)["sent"] == [post()["id"]]
    assert (out / f"{post()['id']}.png").exists()
    assert run_once(root, DryRunSender(out), T0 + 90)["sent"] == []          # never twice
    assert hist(root)[0]["message_id"] == f"dry-{post()['id']}"


def test_late_post_is_skipped(tmp_path):
    root = setup_root(tmp_path, [post()])
    s = run_once(root, DryRunSender(tmp_path / "o"), T0 + 3 * 3600)
    assert s["skipped"] == [post()["id"]] and hist(root) == []


def test_pause(tmp_path):
    root = setup_root(tmp_path, [post()])
    (root / "data" / "PAUSED").touch()
    assert run_once(root, DryRunSender(tmp_path / "o"), T0 + 30)["paused"] is True


def test_failing_post_is_rejected_and_logged(tmp_path):
    root = setup_root(tmp_path, [post(GOOD.replace("40%", "70%"))])
    s = run_once(root, DryRunSender(tmp_path / "o"), T0 + 30)
    assert s["rejected"] == [post()["id"]]
    rej = (root / "queue" / "rejected.jsonl").read_text(encoding="utf-8")
    assert "number 70" in rej


def test_one_post_per_tick_and_cluster_from_store(tmp_path):
    second = post(id="b", slot="2026-10-31T08:31:00+01:00", cluster_id="cy",
                  text=GOOD.replace("Nimbus Labs تقول", "Nimbus Labs تؤكد"))
    root = setup_root(tmp_path, [post(), second])
    c2 = cluster() | {"id": "cy", "title_hint": "Zeta",
                      "sources": [s | {"url": s["url"] + "-other"} for s in cluster()["sources"]]}
    Store(root / "data" / "dtdz.sqlite").put("cluster:cy", c2)        # no longer in candidates.json
    out = DryRunSender(tmp_path / "o")
    assert len(run_once(root, out, T0 + 120)["sent"]) == 1
    s = run_once(root, out, T0 + 180)
    # second post shares the topic of the first: the gate's dedupe stops it
    assert s["rejected"] == ["b"]


def test_upcoming(tmp_path):
    root = setup_root(tmp_path, [post()])
    assert [p["id"] for p in upcoming(root, T0 - 3600)] == [post()["id"]]


def test_brand_and_topic_detection():
    from dtdz.brands import detect_brands, detect_topic
    assert detect_brands("بينانس تتعرض لأكبر سرقة") == ["binance"]
    assert detect_brands("حدود شات جي بي تي من أوبن إيه آي") == ["chatgpt"]   # product beats parent
    assert detect_brands("تويوتا ووايمو تختبران") == ["toyota", "waymo"]
    assert detect_brands("خبر عن الطقس") == []
    assert detect_topic("ثغرة اختراق خطيرة", "news") == "security"
    assert detect_topic("أي شيء", "free") == "free"


def test_card_with_brands_renders(tmp_path):
    p = post(headline="تويوتا ووايمو في اليابان") | {"brands": ["toyota", "waymo"]}
    assert Image.open(render(p, tmp_path / "b.png")).size == (1280, 720)


def test_album_send(tmp_path, monkeypatch):
    import httpx
    from dtdz import telegram as T
    from PIL import Image as I
    seen = {}

    def handler(req):
        seen["path"], seen["body"] = req.url.path, req.content
        return httpx.Response(200, json={"ok": True, "result": [{"message_id": 9}, {"message_id": 10}]})
    bot = T.Bot("1:A", httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr("dtdz.brands.photo_for", lambda spec: I.new("RGB", (800, 600), "red"))
    card = tmp_path / "c.png"; I.new("RGB", (10, 10)).save(card)
    mid = T.TelegramSender(bot, "@x").send({"id": "p1", "text": "**عاجل** نص", "gallery": [{"commons": "x"}]}, card)
    assert mid == "9" and seen["path"].endswith("/sendMediaGroup") and b"<b>" in seen["body"]
