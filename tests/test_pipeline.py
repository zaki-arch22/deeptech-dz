import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dtdz import collect as C
from dtdz.cluster import build_clusters, export
from dtdz.gate import SIGNATURE, check_file, check_post, history_entry, load_banned
from dtdz.store import Item, Store
from dtdz.text import canon_number, canon_url, norm_ar

ROOT = Path(__file__).resolve().parent.parent
BANNED = load_banned(ROOT / "banned_phrases.txt")
NOW = 1_793_440_000.0  # fixed clock

SRC_A = ("Nimbus Labs released Orbit 3, a phone chip that the company says uses 40% less power "
         "than Orbit 2. Phones with Orbit 3 ship in March 2027 starting at $499. The chip supports "
         "Arabic on-device translation in 12 languages.")
SRC_B = ("Orbit 3 from Nimbus Labs promises 40% better battery efficiency. The first phones arrive "
         "in March 2027, the company confirmed.")


def cluster(sensitive=False, sites=2, kind="news", texts=(SRC_A, SRC_B)):
    srcs = [{"id": f"s{i}", "source": f"S{i}", "trust": 2, "url": f"https://site{i}.com/orbit-3",
             "title": "Nimbus Labs unveils Orbit 3 chip", "lang": "en", "extra": {}, "published": "",
             "text": t} for i, t in enumerate(texts[:sites])]
    return {"id": "cx", "kind": kind, "score": 5, "sensitive": sensitive, "distinct_sites": sites,
            "title_hint": "Nimbus Labs unveils Orbit 3 chip", "sources": srcs}


GOOD = (
    "شركة Nimbus Labs تقول إن شريحتها الجديدة تستهلك طاقة أقل بنسبة 40%.\n\n"
    "الشريحة اسمها Orbit 3، وأول الهواتف التي تحملها تصل في مارس 2027 بسعر يبدأ من $499.\n\n"
    "الجديد بالنسبة إليك: ترجمة فورية بالعربية داخل الهاتف دون اتصال بالإنترنت، "
    "وهذا يعني محادثات أسرع وخصوصية أكبر.\n\n"
    "الأرقام جميلة على الورق، والحكم الحقيقي عند التجربة.\n\n"
    "#هواتف\n" + SIGNATURE
)


def post(text=GOOD, **kw):
    return {"id": "2026-10-31-0830", "slot": "2026-10-31T08:30:00+01:00", "type": "news",
            "cluster_id": "cx", "text": text, "logos": [{"name": "Nimbus Labs", "domain": "site0.com"}], **kw}


# ---------- text ----------

def test_numbers_and_arabic():
    assert canon_number("1,000") == canon_number("1000") == canon_number("١٠٠٠") == "1000"
    assert canon_number("2.50") == "2.5"
    assert norm_ar("لا تفوّت") == norm_ar("لا تفوت")
    assert canon_url("https://www.x.com/a/?utm_source=t&id=2") == "https://x.com/a?id=2"


# ---------- gate ----------

def test_good_post_passes():
    assert check_post(post(), cluster(), BANNED, [], NOW) == []


@pytest.mark.parametrize("mutate,expect", [
    (lambda t: t.replace("الأرقام جميلة", "في عالم التقنية، الأرقام جميلة"), "banned phrase"),
    (lambda t: t.replace("سعر يبدأ", "سارع، سعر يبدأ"), "banned phrase"),
    (lambda t: t.replace("40%", "60%"), "number 60"),
    (lambda t: t.replace("Orbit 3،", "Orbit 3 وشريحة Quasar،"), "name 'Quasar'"),
    (lambda t: t.replace(SIGNATURE, "Deeptech"), "last line"),
    (lambda t: t.replace("#هواتف", "#هواتف #تقنية"), "one hashtag"),
    (lambda t: "🔥 🚀 " + t, "first line"),
    (lambda t: t + "!!", "banned phrase"),
    (lambda t: t.replace("الأرقام جميلة", "حمّل من t.me/somechannel الأرقام جميلة"), "not allowed"),
    (lambda t: t.replace("الأرقام جميلة", "التفاصيل على randomblog.net الأرقام جميلة"), "neither a source"),
])
def test_bad_posts_fail(mutate, expect):
    errs = check_post(post(mutate(GOOD)), cluster(), BANNED, [], NOW)
    assert any(expect in e for e in errs), errs


def test_verbatim_copy_fails():
    ar_src = "أعلنت الشركة اليوم عن شريحة جديدة تستهلك طاقة أقل وتدعم الترجمة الفورية داخل الهاتف بالكامل"
    c = cluster(texts=(SRC_A + " " + ar_src, SRC_B))
    text = GOOD.replace("الأرقام جميلة", ar_src + ".\n\nالأرقام جميلة")
    assert any("verbatim" in e for e in check_post(post(text), c, BANNED, [], NOW))


def test_sensitive_needs_two_sites():
    errs = check_post(post(), cluster(sensitive=True, sites=1), BANNED, [], NOW)
    assert any("2 independent" in e for e in errs)
    assert check_post(post(), cluster(sensitive=True, sites=2), BANNED, [], NOW) == []


def test_dedupe_within_7_days():
    h = history_entry(post(), cluster(), NOW - 86400)
    h["id"], h["cluster_id"] = "older", "other"
    h["source_urls"] = []
    errs = check_post(post(), cluster(), BANNED, [h], NOW)
    assert any("same topic" in e for e in errs)
    h["published_ts"] = NOW - 8 * 86400
    assert check_post(post(), cluster(), BANNED, [h], NOW) == []


def test_free_post_needs_official_link():
    c = cluster(kind="free", texts=("Starfall Tactics is free on Epic Games Store until 2026-11-06 16:00 UTC. "
                                    "Regular price: $24.99.", ""), sites=1)
    c["sources"][0]["url"] = "https://store.epicgames.com/p/starfall-tactics"
    text = ("🎁 لعبة Starfall Tactics مجانية على Epic Games Store.\n\n"
            "سعرها المعتاد $24.99، وتبقى لك للأبد إذا أضفتها إلى مكتبتك قبل 16:00 بتوقيت UTC يوم 6 نوفمبر.\n\n"
            "تحتاج فقط حساباً مجانياً في المتجر.\n\n"
            "🔗 store.epicgames.com/p/starfall-tactics\n" + SIGNATURE)
    p = post(text, type="free")
    assert check_post(p, c, BANNED, [], NOW) == []
    no_link = text.replace("🔗 store.epicgames.com/p/starfall-tactics\n", "")
    assert any("official link" in e for e in check_post(post(no_link, type="free"), c, BANNED, [], NOW))


def test_check_file_dedupes_inside_batch(tmp_path):
    cands = tmp_path / "c.json"
    cands.write_text(json.dumps({"generated_at": "", "clusters": [cluster()]}), encoding="utf-8")
    posts = tmp_path / "p.json"
    second = post(id="2026-10-31-1030", slot="2026-10-31T10:30:00+01:00")
    posts.write_text(json.dumps([post(), second], ensure_ascii=False), encoding="utf-8")
    res = check_file(posts, cands, ROOT / "banned_phrases.txt", tmp_path / "none.jsonl", NOW)
    assert res["2026-10-31-0830"] == []
    assert any("dedupe" in e for e in res["2026-10-31-1030"])


# ---------- collector parsers ----------

RSS = f"""<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>
<item><title>Nimbus Labs unveils Orbit 3 chip</title><link>https://site0.com/orbit-3?utm_source=rss</link>
<pubDate>{time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(NOW - 3600))}</pubDate>
<description>&lt;p&gt;{SRC_A}&lt;/p&gt;</description></item>
<item><title>Old story</title><link>https://site0.com/old</link>
<pubDate>{time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(NOW - 5 * 86400))}</pubDate></item>
</channel></rss>""".encode()


def test_rss_parser_keeps_recent_and_cleans_url():
    src = {"name": "S", "grp": "news_en", "trust": 2, "url": "https://site0.com/feed"}
    items = C.parse_rss(src, RSS, NOW)
    assert len(items) == 1
    assert items[0].url == "https://site0.com/orbit-3"
    assert "40%" in items[0].text


def test_epic_parser_only_current_free():
    def game(title, pct, start, end):
        return {"title": title, "productSlug": title.lower(), "description": "d", "seller": {"name": "X"},
                "price": {"totalPrice": {"fmtPrice": {"originalPrice": "$19.99"}}},
                "promotions": {"promotionalOffers": [{"promotionalOffers": [{
                    "startDate": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(start)),
                    "endDate": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(end)),
                    "discountSetting": {"discountPercentage": pct}}]}]}}
    body = json.dumps({"data": {"Catalog": {"searchStore": {"elements": [
        game("Free", 0, NOW - 100, NOW + 100), game("Discount", 50, NOW - 100, NOW + 100),
        game("Later", 0, NOW + 100, NOW + 200)]}}}}).encode()
    items = C.parse_epic({"name": "Epic", "grp": "opportunities", "trust": 3}, body, NOW)
    assert [i.title for i in items] == ["Free on Epic: Free"]
    assert "$19.99" in items[0].text


def test_market_parsers():
    cg = C.parse_coingecko({"name": "CG", "grp": "markets", "trust": 3},
                           b'{"bitcoin":{"usd":67012.4,"usd_24h_change":-1.234}}', NOW)
    assert cg[0].text == "Bitcoin: $67,012 (-1.2% 24h)"
    st = C.parse_stooq({"name": "St", "grp": "markets", "trust": 3},
                       b"Symbol,Date,Time,Open,High,Low,Close,Volume\nNVDA.US,2026-10-30,22:00:00,100,110,99,104,1\n", NOW)
    assert st[0].text.startswith("NVDA: $104.00 (+4.0% today")


# ---------- clustering + export ----------

def _item(url, title, text="", grp="news_en", trust=2, age_h=1):
    return Item("S", grp, trust, url, title, text, NOW - age_h * 3600)


def test_same_story_clusters_across_sites():
    items = [_item("https://a.com/1", "Nimbus Labs unveils Orbit 3 chip with 40% less power"),
             _item("https://b.com/2", "Orbit 3: Nimbus Labs' new chip cuts power use by 40%"),
             _item("https://c.com/3", "Valve announces new handheld console")]
    cl = build_clusters(items)
    assert sorted(len(c.items) for c in cl) == [1, 2]


def test_export_end_to_end(tmp_path):
    db = tmp_path / "db.sqlite"
    s = Store(db)
    s.add(_item("https://a.com/1", "Hackers breach Nimbus Labs servers", "x" * 50))
    s.add(_item("https://b.com/2", "Valve announces new handheld console", "y" * 50))
    stats = export(db, tmp_path / "cands.json", tmp_path / "hist.jsonl", now=NOW)
    data = json.loads((tmp_path / "cands.json").read_text(encoding="utf-8"))
    assert stats["news"] == 2
    hack = next(c for c in data["clusters"] if "breach" in c["title_hint"])
    assert hack["sensitive"] is True and hack["distinct_sites"] == 1


def test_arabic_first_and_headline():
    bad = GOOD.replace("شركة Nimbus Labs تقول", "Nimbus Labs تقول")
    assert any("non-Arabic" in e for e in check_post(post(bad), cluster(), BANNED, [], NOW))
    assert check_post(post(headline="شريحة توفر 40% من البطارية"), cluster(), BANNED, [], NOW) == []
    errs = check_post(post(headline="Orbit 3 chip"), cluster(), BANNED, [], NOW)
    assert any("headline must start" in e for e in errs)
    assert any("number 60" in e for e in check_post(post(headline="شريحة توفر 60% من البطارية"),
                                                    cluster(), BANNED, [], NOW))


def test_every_post_needs_a_logo():
    errs = check_post(post(logos=[]), cluster(), BANNED, [], NOW)
    assert any("no brand logo" in e for e in errs)
    assert any("domain" in e for e in check_post(post(logos=[{"name": "X"}]), cluster(), BANNED, [], NOW))
