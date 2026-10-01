# Hourly WWIT MMA News automation

This is the runbook the hourly scheduled task follows. It turns new MMA news
into Instagram Reels for **@wwitmma** and schedules them through Metricool.
Edit this file to change how the automation behaves; the task reads it fresh
every run.

## Accounts and constants

- Instagram account: **@wwitmma**, via Metricool brand id **7159326**
- Time zone: **America/New_York**
- Repo: **jlopresti02/WikiPull** (public; Metricool pulls videos from it)
- Music: the ESPN-style pool, `"music_pool": "espn"` (rotates automatically)

## Each run, in order

### 1. Get the repo and the ledger

Clone WikiPull and read `stories.json`. It lists every story already posted,
with its facts, sources and posts. Also read the last ~10 entries in
`posts/` folder names so you know what went out recently.

### 2. Sweep the news

Run the news sweep (several separate web searches: general MMA news, UFC,
PFL, ONE Championship and others, fight announcements and bookings,
injuries and withdrawals, results from events happening now, weigh-ins,
contracts and signings, notable callouts or controversies). Look at roughly
the past hour, plus anything major from the past few hours still
developing. Prefer reputable MMA outlets and official sources.

Send the user the usual short briefing with SendUserMessage: biggest story
in one line, then a bullet per new story (what, who, source link). If
nothing significant happened, say so in one line.

### 3. Decide what to post

For each story from the sweep, compare it with `stories.json`:

- **New story** (not in the ledger): post it.
- **Update** (in the ledger, and there is a genuinely new fact: the bout is
  made official, an opponent or date changes, a withdrawal or injury, a
  result, a title implication, a venue announced): post an update, and say
  in the caption that it's an update (e.g. "UPDATE:").
- **Same story, nothing new**: do not post. Never repeat a story without an
  update.

Rules:
- Post every story that qualifies, but **never more than 3 in one time
  block** (see step 6). Extra posts wait for later blocks; they are not
  dropped. Order them most newsworthy first.
- Only post what a reputable outlet or official source reports. A rumor can
  be posted only if clearly worded as a report ("reportedly", "per ESPN").
- No posts that mock or sensationalize serious injuries, deaths, arrests or
  personal tragedies. Report them plainly or skip them.
- If nothing qualifies, skip to step 7 and say no posts this hour.

### 4. Write the post file

Create `posts/queue/<YYYY-MM-DD-HHMM>-<short-slug>.json`:

```json
{
  "story_id": "prochazka-vs-stirling-ufc-qatar",
  "headline": "BJP Returns",
  "visual": [
    {"type": "fighter", "name": "Jiri Prochazka"},
    {"type": "venue", "name": "Lusail Sports Arena"},
    {"type": "flag", "country": "Qatar"}
  ],
  "color": "#d2202f",
  "caption": "...",
  "hashtags": ["MMANews", "UFC", "UFCQatar", "JiriProchazka", "LightHeavyweight"],
  "sources": ["CBS Sports", "ESPN"],
  "music_pool": "espn",
  "reel": true
}
```

**Headline**: 1 to 3 punchy words, like a sports graphic ("BJP RETURNS",
"TITLE SHOT", "OUT OF UFC 330"). Match it to the image that will be used
(see Visual below).

**Visual**, in priority order (the first that works is used). Any entry
can carry its own `"headline"`, which replaces the post's headline only if
that entry is the one used.

1. **Photos of fighters connected to the story**, by the names Wikipedia
   uses (cut out automatically). Order: the main fighter, then the other
   fighters who are in the story *and still involved* (e.g. a new opponent).
2. **The fighter who is out**: for a withdrawal, injury, release or
   replacement, add the fighter who is leaving last among the fighter
   photos, with a headline about them leaving, e.g.
   `{"type": "fighter", "name": "Bernardo Sopaj", "headline": "Sopaj Out"}`
   ("INJURED OUT", "SOPAJ REPLACED", "SOPAJ PULLS OUT"). The caption should
   still tell the whole story.
3. **Story-type graphic**: for money stories (purses, bonuses, contracts,
   fines, betting) add `{"type": "money"}`; for location or event
   announcements add the arena/stadium (`venue`), then the host country's
   `flag`.
4. **Silhouette backup** for any story about fighters: `{"type": "mystery"}`
   draws a silhouette with a question mark and always works. It's the
   stand-in when no connected fighter has a usable photo, so put the main
   fighter's **last name in the headline** ("MCGHEE'S NEW FOE",
   "ASPINALL'S REPLACEMENT").
5. Otherwise the main fighter's country `flag`.
A text-only post is the automatic last resort.

Example for a replacement story:

```json
"headline": "McGhee's New Foe",
"visual": [
  {"type": "fighter", "name": "Marcus McGhee"},
  {"type": "fighter", "name": "Anthony Romero"},
  {"type": "fighter", "name": "Bernardo Sopaj", "headline": "Sopaj Out"},
  {"type": "mystery"}
]
```

**Color**: vary it so the grid isn't one color. Red `#d2202f` for big news
and fights, blue `#1f3fbf` for announcements, black `#111111` for money and
contracts, yellow `#f5c518` for results and wins, green `#0f8a5f` for
updates, purple `#6b2fd1` for anything else.

**Caption**: write it in your own words (never copy an article's sentences).
Built for Instagram search and the Reels algorithm:
- First line is a hook that names who and what: "Jiří Procházka is back in
  the main event."
- 2 to 4 short sentences of the facts, naturally packed with search
  keywords: full fighter names, the promotion (UFC, PFL, ONE), the event
  name and number, weight class, city/country, and terms like "MMA news",
  "UFC news", "fight announcement", "title fight" where they're true.
- End with a question to get comments ("Who takes it?").
- Keep it under about 1,200 characters. Use 1 or 2 emoji at most.

**Hashtags**: exactly 5 (Instagram's limit). Mix: 1 broad (`MMA` or
`MMANews`), 1 promotion (`UFC`), 1 event (`UFCQatar`, `UFC330`), and 1 to 2
names (`JiriProchazka`). No spaces or punctuation.

**Sources**: the outlet names for the story (CBS Sports, ESPN, MMA
Junkie...). The photo, music and source credit lines are added to the
caption automatically; don't write them yourself.

### 5. Update the ledger, then push

In `stories.json`:
- New story: add an entry at the top with `id`, `title`, `people`,
  `event`, `first_reported`, `facts`, `sources` (URLs) and a `posts` list.
- Update: add the new facts and sources to the existing entry.
- Add `{"post": "<file name without .json>", "kind": "new" or "update"}`
  to its `posts`.

Commit the queue file(s) and `stories.json` together and push to `main`.
The push starts the **Make posts** workflow.

### 6. Wait for the Reels, then schedule them

Poll (`git pull` every 30 s, up to 15 minutes) until a commit named
"Make posts" appears after yours and `posts/<name>/reel.mp4` exists for
every queued post. If a post is missing, read `posts/make-posts-log.txt`
for the reason, leave it unscheduled, and tell the user.

For each finished post, schedule it with Metricool `createScheduledPost`:
- `blogId` 7159326, network `instagram`, `instagramData.type` `REEL`,
  `showReelOnFeed` true, `isAiGenerated` false.
- `media`: the Reel's raw GitHub URL **pinned to the commit**:
  `https://raw.githubusercontent.com/jlopresti02/WikiPull/<commit sha>/posts/<name>/reel.mp4`
- `videoThumbnailUrl`: the same for `posts/<name>/cover.png`.
- `text`: the exact contents of `posts/<name>/caption.txt`.
- `autoPublish` true.

**When to schedule (time blocks):** a time block is a 10-minute window,
and it holds at most 3 posts, spaced 2 minutes apart.

1. First call Metricool `getScheduledPosts` (brand 7159326, from now to 6
   hours ahead, America/New_York) to see what is already waiting to go out,
   including overflow from earlier runs. Never put a 4th post in a block
   that already has 3.
2. The first block starts **10 minutes from now**, so new posts go out
   within 15 minutes of being made whenever there's room.
3. Fill that block with up to 3 posts (at +0, +2 and +4 minutes in the
   block). If more posts remain, start the next block 10 minutes after the
   previous one, and repeat until every post has a time.
4. If the blocks run into the next hour, keep going: later runs read the
   Metricool schedule in step 1 and place their own posts after these, so
   nothing collides and nothing is dropped.

Then add `"scheduled_for"` and the Metricool `plannerUrl` to the post's
entry in `stories.json`, commit and push.

### 7. Report

Send one short SendUserMessage: which posts were scheduled (headline, time,
which image type was used), any that were pushed to later blocks, which
stories were skipped as repeats, and any failures. If there were no posts, say so in one line.
