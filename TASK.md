# Writer task — Deeptech DZ

Instructions for the scheduled Claude task. Each run writes the posts for the next few slots.
The PC refreshes `queue/candidates.json` every 30 minutes and publishes whatever passes the gate.

## Runs and slots (Africa/Algiers)

| Run | Writes slots |
|---|---|
| ~07:40 | 08:30, 10:30, 12:30 |
| ~12:40 | 14:30, 16:30, 18:30 |
| ~18:40 | 20:30, 22:00 |

Daily mix across the 8 slots — the channel is NOT a news feed, it is news + real value:
- 3 news (the most important or surprising of the day)
- 2 opportunities (`free`): free games (Epic/Steam/GOG), free courses or certificates, free official
  offers — from `kind: free` clusters or `kind: library` items of library_kind course/tool/books
- 1 tool or AI tool (`tool`): a `library` item (ai/tool) or a useful new tool from Show HN / Product Hunt,
  explained step by step: what it does, who it helps, how to start
- 1 market (`market`, always 12:30)
- 1 protection tip or odd story: a `library` security item (`tool`) or a genuinely strange news (`odd`)
Every run must contain at least one non-news post (the gate enforces it). Read the last 24 h of
`queue/history.jsonl` to see what today already has.

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
     "cluster_id": "c1a2b3c4d5", "headline": "3 إلى 8 كلمات للصورة",
     "text": "…\n\n#تصنيف\n◆ Deeptech DZ"}]
   ```
   `type` ∈ news, free, tool, market, odd. `id` = slot date and time. `headline` is required.
   EVERY card must show at least one real brand logo (the gate rejects posts without one).
   Brands in dtdz/brands.py are detected from the text automatically and their official logo is
   fetched from their site. If the story's main company/app/coin is not in that list (or detection
   would pick the wrong one), add it explicitly:
   `"logos": [{"name": "Waymo", "domain": "waymo.com", "wiki": "Waymo"}]` (max 2; `domain` = the
   brand's official site, `wiki` = its English Wikipedia title). For a story about a country,
   operator or institution, use its official site (e.g. "djezzy.dz", "mobilis.dz").
   Optional `"topic": "security"` (a file name in assets/topics) for the small badge.
   Creative touch when it fits (a car, a phone, a console, a rocket, a game): add
   `"photo": {"wiki": "Toyota bZ4X"}` — the English Wikipedia article of the PRODUCT or OBJECT; its lead
   photo fills the card with the logos on top. Never use a photo of a person. Skip when no clear
   product article exists.
   Preview: `python -m dtdz render queue/posts/<file>.json --outbox /tmp/cards`.
5. Run `python -m dtdz check queue/posts/<file>.json`. Fix every failing post and re-run.
   After 3 failed attempts on one post, replace it with another cluster or drop the slot.
6. Commit only the posts file: `git add queue/posts && git commit -m "posts <date> <run>" && git push`.

## Never

- Invent or round a number, a name, a quote, or a date.
- Link to Telegram channels, file hosts, cracked apps, leaked courses, or shared team invites.
- Mention prices you would sell at, or anything about Digital DZ.
- Edit `candidates.json`, `history.jsonl`, the style files, or the code.
