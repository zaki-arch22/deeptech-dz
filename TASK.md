# Writer task — Deeptech DZ

Instructions for the scheduled Claude task. Each run writes the posts for the next few slots.
The PC refreshes `queue/candidates.json` every 30 minutes and publishes whatever passes the gate.

## Runs and slots (Africa/Algiers)

Slots are every half hour from **07:30 to 00:30** (:00 and :30). The task runs every hour at :40 and
writes the slots between this run and the next one (06:40 run → 07:30; 07:40 run → 08:00, 08:30; …;
23:40 run → 00:00, 00:30). Slots already in `queue/posts/` are not rewritten.

**Quality over quantity:** a slot is filled only if there is something genuinely worth posting. An
empty slot is always better than a weak, minor or boring post. Never pad.

## Editorial formula (v4 — learned from the biggest Algerian tech channel, 80K subscribers)

The audience follows a channel that makes them say "wow", laugh, or "I must share this". Every
post must pass the **"would I forward this to a friend?"** test. Routine = death.

**What they post (and we now post), in rough share of the day:**
1. **Shock news about giants (≈35%)** — huge numbers and dramatic turns: mass layoffs, record hacks,
   billion-dollar deals, a company admitting a defect, AI labs warning about their own models,
   global market crashes ("3 trillion dollars lost in one day"), app outages worldwide.
   Tech is the core, but **big world events everyone talks about** are allowed when confirmed by two
   major outlets (BBC, Al Jazeera, France 24, WHO): health alerts, a historic first, a crisis that
   shakes markets. Report facts with neutral wording — never "insiders say", never sides in politics.
2. **Free value (≈25%)** — free official certificates (Google, Microsoft, SAP, Cisco…), paid software
   free for a few days (official giveaway pages), free games, **curated lists** of free tools
   (`type: list`: "5 free tools to clean your PC of hidden miners", numbered, each with its official link
   and one-line benefit).
3. **Wow science & devices (≈15%)** — records and inventions with a tangible comparison ("20,000 4K
   films in one second"), space, robots, strange devices.
4. **Entertainment & sport (≈15%)** — the series/film everyone will watch this week, El Clásico and
   big matches (time, stadium, channel), Algerian players and the national team.
5. **Apps & sites (≈10%)** — tested, useful, with the official link.

**How they write it (adopt):**
- First line = the whole hook, in bold, starting with ⚡ or ❗ (or 🎁 for free, 🚨 for danger):
  `⚡ **مايكروسوفت تقترح تسريح 60 ألف موظف حول العالم.**`
- 35–110 words. Short paragraphs of 1–2 sentences. Bold 2–4 key phrases.
- Numbers made tangible, and **the Algerian angle** whenever it exists ("AppleCare doesn't exist in
  Algeria, so…", price in dinars when known, does it work here?).
- A last line with personality is welcome: light irony or a punchline (one short sentence, not a moral).
- Several real photos when available: `"gallery": [{"commons": "..."}, ...]` (up to 3, sent as an album
  with the card first). Use the official press image of the source when the cluster has one.
- Pace: post whenever something good lands; several posts in an hour is fine during big news.

**Not adopted (and the gate blocks it):** cracked "premium" APKs, pirate streaming apps and IPTV codes,
shared Drive folders of copyrighted books, referral codes, copying their text or photos, English
duplicates of the post, unverified rumours, photos of people.

**Daily anchors (still useful, not rigid):** 12:00 app, 19:00 site, 12:30/21:00 market — skip any of
them if something better is happening; never post two of the same kind back to back.

## Presentation (learned from successful Arabic tech channels)
- **Bold** the key fact or number with `**…**` (one to three bolds per post, not whole paragraphs).
- Figures and lists as short bullet lines starting with `•`.
- A strong first line; for app/site posts, open with the problem or the "wow" result.
- No hashtags at all (the gate rejects them).
- **A real photo OF THE STORY ITSELF in almost every post** — not a look-alike or a generic
  illustration. Search the whole web (WebSearch / WebFetch) for the actual image:
  - the product, device, car, app screen, game, building, launch… exactly the one in the news;
  - published by the organisation the story is about: its website, newsroom, press kit or CDN
    (news.microsoft.com, apple.com/newsroom, samsungmobilepress.com, nasa.gov, store.steampowered.com,
    the game/film/app's official site, an official store screenshot…), or freely licensed on Wikimedia.
  - Put the direct image URL in `"photo": {"url": "https://…jpg"}` (the card becomes a full-photo
    "hero" with the headline over it) and add up to 3 more in `"gallery"` for an album.
  - The gate accepts an image host only if it belongs to a brand in the post (`brands`/`logos` domains,
    their CDNs) or an official source of the cluster; for another official owner (a ministry, a
    university, a club) add it to `logos` with its domain, or set `"photo_owner": "domain"`.
  - Check the image loads and really shows the subject before using it (open it with WebFetch).
  - Not allowed: images owned by news outlets or photo agencies (Reuters, AP, Getty, AFP…), other
    channels' images, film posters you didn't find on the official site, photos of private people.
    Public figures only from their organisation's official press material.
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
     "text": "…\n\n◆ Deeptech DZ"}]
   ```
   `type` ∈ news, free, tool, market, odd, app, site, sport, film, discovery, study (منح ودراسة), visa (هجرة وتأشيرات), trend (ترند). `id` = slot date and time. `headline` is required.
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
