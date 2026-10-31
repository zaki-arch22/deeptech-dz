# Writer task — Deeptech DZ

Instructions for the scheduled Claude task. Each run writes the posts for the next few slots.
The PC refreshes `queue/candidates.json` every 30 minutes and publishes whatever passes the gate.

## Runs and slots (Africa/Algiers)

Slots are every half hour from **07:30 to 00:30** (:00 and :30). The task runs every hour at :40 and
writes the slots between this run and the next one (06:40 run → 07:30; 07:40 run → 08:00, 08:30; …;
23:40 run → 00:00, 00:30). Slots already in `queue/posts/` are not rewritten.

**Quality over quantity:** a slot is filled only if there is something genuinely worth posting. An
empty slot is always better than a weak, minor or boring post. Never pad.

## Daily plan (about 25–35 posts on a good day)

The channel is news + real value, not a news feed. Fixed daily rendez-vous:
- **12:00 تطبيق اليوم** (`type: app`): a `library` item with library_kind app. Present it in an
  exciting, practical way: the problem it solves, 3 standout features, who it is for, free or not,
  then the download link (`store` link, or official site).
- **19:00 موقع اليوم** (`type: site`): a `library` item with library_kind site, same approach, with link.
- **12:30 and 21:00 السوق** (`type: market`).
Between them, mix through the day:
- news (≈half of posts): the important or surprising; use `"breaking": true` only for truly major,
  confirmed breaking news (shows a red عاجل label).
- opportunities (`free`): free games (Epic/Steam/GOG), free courses/certificates, free official offers,
  library items course/books.
- tools and AI tools (`tool`): library ai/tool items or a useful new tool from Show HN / Product Hunt.
- protection tips (`tool` with a library security item) and odd-but-true stories (`odd`).
- **sport** (`type: sport`): big matches, results and transfers that interest Algerian/Arab fans
  (Algeria national team, Algerian players abroad, El Clásico, Champions League, AFCON). Facts from
  the sports sources only. Logos: the clubs/competition (`logos` with official domains).
- **ماذا نشاهد؟** (`type: film`): a new film/series worth watching, or a themed list of 3–5 good
  titles, from the entertainment sources. Say where to watch it legally (Netflix, Shahid, OSN+,
  Prime Video, HBO Max…) — never pirate sites, IPTV apps or "codes". Logo: the platform.
- **اكتشاف** (`type: discovery`): a striking device, invention, scientific or space discovery from
  the science/tech sources, explained simply: what it is, why it is impressive, a concrete comparison
  ("enough to download 20,000 films in one second"), and when it may reach people.
- **software giveaways**: a paid program free for a limited time on its official developer site
  (e.g. vovsoft.com giveaways) — `free` post with the original price, the end date and the official link.
- **outage alerts**: when a major app (WhatsApp, Telegram, Instagram…) is down and at least two sources
  report it, post a short `breaking` news with what is affected.
Every run of 3+ posts needs one non-news post (the gate enforces it). Check the last 24 h of
`queue/history.jsonl` so the day stays varied and nothing repeats.

## Presentation (learned from successful Arabic tech channels)
- **Bold** the key fact or number with `**…**` (one to three bolds per post, not whole paragraphs).
- Figures and lists as short bullet lines starting with `•`.
- A strong first line; for app/site posts, open with the problem or the "wow" result.
- No hashtags at all (the gate rejects them).
- **Real photos in most posts** (brand logos always, plus a real photo whenever one fits — aim for
  most news, discovery, app, sport and film posts):
  - `"photo": {"commons": "<search words>"}` — Wikimedia Commons, freely licensed: cars, phones,
    devices, consoles, rockets, satellites, data centers, stadiums, buildings, places, objects.
    E.g. "Toyota bZ4X", "Samsung Galaxy S24", "Falcon 9 launch", "Camp Nou", "fiber optic cable".
  - `"photo": {"url": "<cluster official_image>"}` — the press image of an official source
    (company newsroom, NASA); copy it exactly from the cluster's `official_image`.
  - `"photo": {"wiki": "<English article>"}` — lead photo of a product article.
  - app posts: an official store screenshot (`play-lh.googleusercontent.com`) is allowed.
  - NOT allowed: photos of people (players, CEOs, actors, teams), photos or screenshots taken
    from news sites or newspapers, film posters/stills, other channels' images. For films use
    the platform logo plus a Commons photo of a related object/place if any; for football use
    club/competition logos plus a Commons photo of the stadium.
- Good ideas seen on big Arabic channels and adopted here: "عاجل" for real outages and major news,
  concrete comparisons that make numbers tangible, themed film lists, free software giveaways,
  a short English summary is NOT used (we stay Arabic).
- Do NOT copy what weak channels do: unverified rumours presented as fact ("insiders say", "it is
  reported"), politics unrelated to tech, referral/affiliate links, cracked or "premium unlocked" apps,
  pirate streaming apps or IPTV codes, film posters or player photos copied from news sites.

Library items (`kind: library`): before writing, open the item's official `url` (WebFetch) and confirm
it is still free and as described; if not, skip it. Copy the cluster's `logos` into the post. Write it
as a practical guide: what it is, why it is valuable, 2–3 steps to start, the official link.

## Steps

1. `git pull`. Read `STYLE.md` and `banned_phrases.txt` in full. Read `queue/candidates.json`.
   If `generated_at` is older than 3 hours, write nothing and stop (the PC is off).
2. Pick one cluster per slot using STYLE.md section 1 (selection), not `score` alone.
   Relevance to an Arab/Algerian reader beats everything: apps they use daily, money, free
   things, real danger to regular users, genuinely surprising facts. Skip developer-niche news,
   US-only deals and minor updates — an empty slot is better than a boring post.
   Variety: no two posts about the same company or topic in one run. Skip clusters with `sensitive: true`
   and `distinct_sites < 2`. For `kind: free` sources with `needs_official_link`, open the
   offer and find the official store page; if you cannot, skip it.
3. Write each post in Arabic (فصحى) following STYLE.md: every line starts with an Arabic word,
   known companies and apps written in Arabic (جوجل، واتساب، بينانس…), amounts as "6.3 مليار دولار",
   60–150 words that explain (context: who/what it is, why it happened, what it means for the
   reader), short direct sentences, no templates like "رأينا:". Write it from the facts, in your own
   words and your own structure; never translate or paraphrase a source sentence by sentence.
   Use only facts present in the cluster's `sources[].text`. Every number and every Latin
   name must appear there. Copy market figures exactly as written in the snapshot.
4. Save `queue/posts/<YYYY-MM-DD>-<HHMM>.json` (run time) as a JSON array:
   ```json
   [{"id": "2026-10-31-0830", "slot": "2026-10-31T08:30:00+01:00", "type": "news",
     "cluster_id": "c1a2b3c4d5", "headline": "4 إلى 10 كلمات واضحة للصورة",
     "text": "…\n\n#تصنيف\n◆ Deeptech DZ"}]
   ```
   `type` ∈ news, free, tool, market, odd, app, site. `id` = slot date and time. `headline` is required.
   Before writing, list `queue/posts/` and skip slots that already have a post.
   EVERY card must show at least one real brand logo (the gate rejects posts without one).
   Brands in dtdz/brands.py are detected from the text automatically and their official logo is
   fetched from their site. If the story's main company/app/coin is not in that list (or detection
   would pick the wrong one), add it explicitly:
   `"logos": [{"name": "Waymo", "domain": "waymo.com", "wiki": "Waymo"}]` (max 2; `domain` = the
   brand's official site, `wiki` = its English Wikipedia title). For a story about a country,
   operator or institution, use its official site (e.g. "djezzy.dz", "mobilis.dz").
   Optional `"topic": "security"` (a file name in assets/topics) for the small badge.
   Real photo when it makes the post more striking (see Presentation above).
   Preview: `python -m dtdz render queue/posts/<file>.json --outbox /tmp/cards`.
5. Run `python -m dtdz check queue/posts/<file>.json`. Fix every failing post and re-run.
   After 3 failed attempts on one post, replace it with another cluster or drop the slot.
6. Commit only the posts file: `git add queue/posts && git commit -m "posts <date> <run>" && git push`.

## Never

- Invent or round a number, a name, a quote, or a date.
- Link to Telegram channels, file hosts, cracked apps, leaked courses, or shared team invites.
- Mention prices you would sell at, or anything about Digital DZ.
- Edit `candidates.json`, `history.jsonl`, the style files, or the code.
