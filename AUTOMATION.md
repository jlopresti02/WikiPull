# WWIT MMA News automation

This is the runbook the scheduled task follows. It runs 4 times a day
(9 AM, 1 PM, 6 PM and 10 PM Eastern), every day except Saturday. It turns new MMA news
into Instagram Reels for **@wwitmma** and schedules them through Metricool.
Edit this file to change how the automation behaves; the task reads it fresh
every run.

## Accounts and constants

- Instagram account: **@wwitmma**, via Metricool brand id **7159326**
- Time zone: **America/New_York**
- Repo: **jlopresti02/WikiPull** (public; Metricool pulls videos from it)
- Music: the ESPN-style pool, `"music_pool": "espn"` (rotates automatically)

## Requested stories (one-time)

Post these on the next run even if they fall outside the sweep window,
then delete the item from this list in the same commit as the ledger
update. Still follow every rule below (own-words caption, sources,
5 hashtags, 30-minute spacing, no repeats).

## Each run, in order

### 1. Get the repo and the ledger

Clone WikiPull and read `stories.json`. It lists every story already posted,
with its facts, sources and posts. Also read the last ~10 entries in
`posts/` folder names so you know what went out recently.

### 2. Sweep the news

Run the news sweep (several separate web searches: general MMA news, UFC,
PFL, ONE Championship and others, fight announcements and bookings,
injuries and withdrawals, results from events happening now, weigh-ins,
contracts and signings, notable callouts or controversies). Cover
everything since the previous run: about 4 to 11 hours, and on the Sunday
9 AM run everything since Friday 10 PM (all of Saturday, including any
Saturday-night event results). Use `stories.json` and recent `posts/`
folders to see what's already covered. Prefer reputable MMA outlets and official sources.

Also run a separate **adjacent combat sports sweep** over the same window
(see "Trial Reels" in step 3 for what to do with these stories). Use
separate searches for each:
- RAF (Real American Freestyle wrestling)
- Olympic and international wrestling (freestyle, Greco-Roman, women's;
  UWW world championships, national teams)
- College wrestling (NCAA, top programs, transfers, big duals, recruits)
- Pro BJJ and submission grappling (ADCC, CJI, UFC BJJ, IBJJF, Craig
  Jones, Gordon Ryan, FloGrappling)
- Bare knuckle boxing (BKFC and others)
- Pro boxing (title fights, results, big signings, feuds)
- Arm wrestling (East vs West, top pullers like Devon Larratt, Levan
  Saginashvili)
- "Spectacle sports" stories: anything else adjacent to combat sports
  that is surprising or viral (Power Slap, influencer boxing, strongman
  crossovers, celebrity fights, unusual matchups, wild moments)

Send the user the usual short briefing with SendUserMessage: biggest story
in one line, then a bullet per new story (what, who, source link), with
the adjacent combat sports stories in their own short section. If
nothing significant happened, say so in one line.

### 3. Decide what to post

For each story from the sweep, compare it with `stories.json`:

- **New story** (not in the ledger): post it.
- **Update** (in the ledger, and there is a genuinely new fact: the bout is
  made official, an opponent or date changes, a withdrawal or injury, a
  result, a title implication, a venue announced): post an update, and say
  in the caption that it's an update (e.g. "UPDATE:").
- **Same story, nothing new**: do not post. Never repeat a story without an
  update. The bar for an update is high: a *date for an announcement*
  ("Pereira's next fight will be revealed Saturday") is not new; the
  *announcement itself* (the opponent is named) is. On 2026-10-01 a
  low-bar Pereira update got 34 views vs 246 for the original.

What performs (from @wwitmma's first day of data, 2026-10-01):
- **Top posts (200-260 views)**: a well-known star in the first line, plus
  conflict or stakes: a feud, a clapback, an ultimatum, a refusal, a
  fight falling through, a "who's next?" mystery.
- **Bottom posts (34-44 views)**: no person's photo, a repeat story with a
  weak update, or a lesser-known fighter with no hook.
- Viewers decide in about 2 seconds (average watch time 1.6-3.4 s), so the
  first frame (headline + face) matters most.

Rules:
- Post every story that qualifies, ordered **most newsworthy first**: star
  + conflict stories at the top, routine bookings and lesser-known names
  last. Spacing is one post every 30 minutes (see step 6). Extra posts
  wait for later slots; they are not dropped.
- Only post what a reputable outlet or official source reports. A rumor can
  be posted only if clearly worded as a report ("reportedly", "per ESPN").
- No posts that mock or sensationalize serious injuries, deaths, arrests or
  personal tragedies. Report them plainly or skip them.
- If nothing qualifies, skip to step 7 and say no posts this run.

**Trial Reels** (started 2026-10-02). Instagram Trial Reels are shown
only to non-followers at first, so they test weaker content without
diluting the main feed. Each post is either a regular Reel or a Trial
Reel, never both (the same video twice would split its reach).

Through Oct 2, Trial Reels averaged 157 views vs 147 for regular Reels,
while reaching only new people ("Flinch!": 226 views in 90 minutes), so
use them freely for anything that isn't a top story.

- **Regular Reel**: MMA stories with a well-known star plus conflict or
  stakes, shown with that star's own photo (the top performers above).
- **Trial Reel**, any of these:
  - Weaker MMA posts: lesser-known fighters with no hook, routine
    bookings and card additions, updates with a modest new fact.
  - Any post whose image isn't the story's own person: silhouette,
    flag, venue or money graphic.
  - Business and cross-sport stories, even with a big name: promoter
    spats, broadcast deals, a UFC figure talking about boxing ("PR War",
    Dana vs Eddie Hearn over a boxing match: 30 views as a regular Reel).
- **Trial Reel, always**: every adjacent combat sports story from the
  second sweep (RAF, Olympic and college wrestling, pro BJJ, bare knuckle,
  pro boxing, arm wrestling, spectacle sports). Post up to **3 per run**,
  picking the most interesting: a famous name, a viral moment, a feud,
  or a crossover with MMA. Skip routine results nobody outside the sport
  would recognize.

Mark a Trial Reel by adding `"trial_reel": true` to its queue file.
Order the schedule with regular Reels first (most newsworthy first),
then Trial Reels. The 30-minute spacing applies to every post, Trial
Reels included.

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
  "seconds": 6,
  "question": "BJP or Stirling?",
  "follow_card": true,
  "reel": true
}
```

**On the Reel itself** (added Oct 3: people leave after about 2.4 s and
almost nobody opens the caption):
- `"question"`: at 2.5 s the headline turns into this question, set just
  as big. Use the same two-option question as the caption's second line,
  2 to 4 words, no emoji (the font has none): "COLBY OR STRICKLAND?",
  "BAN IT?", "FAIR OR NOT?". Every post gets one.
- `"follow_card": true`: the last 1.2 s read FOLLOW @WWITMMA, then the
  Reel loops back to the headline. Every post gets it.

**Headline**: 1 to 3 punchy words, like a sports graphic ("BJP RETURNS",
"TITLE SHOT", "OUT OF UFC 330"). Match it to the image that will be used
(see Visual below). Make it emotional and specific, built on the conflict
or the stakes, not a neutral label: "FAKE NEWS", "1 HOUR", "SCARED?",
"BAN IT?" beat "STERLING SPEAKS" or "NEW FIGHT". For location posts, name
the place: "SYDNEY BOUND", "UFC PARIS".

**Visual**, in priority order (the first that works is used). Any entry
can carry its own `"headline"`, which replaces the post's headline only if
that entry is the one used.

**Use the photo of the person the story is about.** Through Oct 2, Reels
with the story's own fighter averaged 191 views; Reels using Dana White's
photo for someone else's story averaged 68 (King Green story with Dana's
face: 25 views). A face that doesn't match the headline gets scrolled
past. Pick the list for the story type:

**A. Location / event announcements** (a new event, a city or country,
an arena, "UFC returns to X"): lead with the place, not a fighter.
1. The host country's `flag` first, with a headline naming the city or
   country: `{"type": "flag", "country": "Australia", "headline": "Sydney Bound"}`.
2. Then the arena/stadium (`venue`).
3. Then a fighter from that country who is linked to the card, if any.
Also put the country's flag emoji in the caption's first line
("🇦🇺 The UFC is officially going back to Sydney.").

**B. Rules, regulations, officiating, commissions** (rule changes, banned
techniques, fouls, scoring, commission decisions, drug-testing policy):
use a UFC referee, with a headline about the rule ("BAN IT?", "NEW RULE").
List several so one works:
`{"type": "fighter", "name": "Herb Dean"}`, then `"Marc Goddard"`, then
`"Jason Herzog"`. A fighter at the center of the debate can go first if
the story is about them (e.g. Sterling speaking against the rule); put
the referees right after.

**C. Everything else** (fights, call-outs, feuds, injuries, signings,
results, business):
1. **Photos of fighters connected to the story**, by the names Wikipedia
   uses (cut out automatically). Order: the main fighter, then the other
   fighters who are in the story *and still involved* (e.g. a new opponent).
2. **The fighter who is out**: for a withdrawal, injury, release or
   replacement, add the fighter who is leaving last among the fighter
   photos, with a headline about them leaving, e.g.
   `{"type": "fighter", "name": "Bernardo Sopaj", "headline": "Sopaj Out"}`
   ("INJURED OUT", "SOPAJ REPLACED", "SOPAJ PULLS OUT"). The caption should
   still tell the whole story.
   **Try every name a fighter goes by** before giving up: list the
   Wikipedia name and common alternates as separate entries (e.g. "Bobby
   Green" and "King Green"; "Natalia Silva" and "Natália Silva").
3. **Dana White (or another non-fighter) only when they ARE the story**:
   he announced it, said it, did it, or is in the conflict ("Wrong
   Fighter", Dana's own mix-up: 154 views). Then he can go first. When the
   story is about a fighter and Dana merely commented, use the fighter;
   never use Dana's face as a stand-in. Same for Joe Rogan, Daniel
   Cormier, commentators and executives: when they talk about a fighter,
   show the fighter ("Rogan On MVP" with Michael Page's photo: 144;
   "Rogan: Ban It" with Rogan's photo: 115 vs 248 for Sterling on the same
   topic).
4. **Money graphic**, money stories only (purses, bonuses, contracts,
   fines, betting): `{"type": "money"}`, after all the people above.
5. **Silhouette backup** for fighter stories when no photo of anyone in
   the story works: `{"type": "mystery"}` with the fighter's **last name in
   the headline** ("MCGHEE'S NEW FOE"). It beat the Dana stand-in on views
   (132 vs 68 average), so it's the fallback instead of a stand-in face.
   Post silhouette Reels as **Trial Reels** (`"trial_reel": true`).

After the Reels are rendered (step 6), check each post's
`posts/<name>/post.json`: if `subject.kind` is `"none"` (text only),
**don't schedule it**. Tell the user it was held back for having no
image, and name the person whose photo would fix it so they can add one
to the image bank.

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

Example for a rules story:

```json
"headline": "Ban It?",
"visual": [
  {"type": "fighter", "name": "Aljamain Sterling"},
  {"type": "fighter", "name": "Herb Dean"},
  {"type": "fighter", "name": "Marc Goddard"},
  {"type": "fighter", "name": "Jason Herzog"}
]
```

Example for a location announcement:

```json
"headline": "Sydney Bound",
"visual": [
  {"type": "flag", "country": "Australia"},
  {"type": "venue", "name": "Qudos Bank Arena"}
]
```

**Color**: vary it so the grid isn't one color. Red `#d2202f` for big news
and fights, blue `#1f3fbf` for announcements, black `#111111` for money and
contracts, yellow `#f5c518` for results and wins, green `#0f8a5f` for
updates, purple `#6b2fd1` for anything else.

**Caption**: write it in your own words (never copy an article's sentences).
Built for Instagram search and the Reels algorithm:
- First line is a hook that names the star and the conflict or stakes:
  "Colby Covington just called the report fake news." beats "A report says
  RAF offered a wrestling match." For location posts, start with the
  country's flag emoji and the city.
- 2 to 4 short sentences of the facts, naturally packed with search
  keywords: full fighter names, the promotion (UFC, PFL, ONE), the event
  name and number, weight class, city/country, and terms like "MMA news",
  "UFC news", "fight announcement", "title fight" where they're true.
- **Second line: a two-option question** with a 👇, so people see it
  without opening the caption: "Colby or Strickland? 👇", "Ban it or keep
  it? 👇", "Fair or not? 👇". Through Oct 2, 38 Reels got 0 comments with
  only an open question at the end; easy picks are easier to answer.
- End with a short open question too ("Who takes it?").
- Keep it under about 1,200 characters. Use 1 or 2 emoji at most.

**Hashtags**: exactly 5 (Instagram's limit). Mix: 1 broad (`MMA` or
`MMANews`), 1 promotion (`UFC`), 1 event (`UFCQatar`, `UFC330`), and 1 to 2
names (`JiriProchazka`). No spaces or punctuation. For adjacent sports,
use that sport's broad tag instead (`Wrestling`, `NCAAWrestling`, `BJJ`,
`BareKnuckle`, `Boxing`, `ArmWrestling`), then its promotion (`RAF`,
`ADCC`, `BKFC`), event and names.

**Adjacent sports posts** follow the same rules as MMA posts: a real
photo of the athlete (the `fighter` visual type works for anyone with a
Wikipedia photo; list several people so one works), a 1 to 3 word
headline, an own-words caption whose first line names the star and the
hook, sources, and `"music_pool": "espn"`. Color purple `#6b2fd1` unless
another color above fits better.

**Sources**: the outlet names for the story (CBS Sports, ESPN, MMA
Junkie...). The photo, music and source credit lines are added to the
caption automatically; don't write them yourself.

### 5. Update the ledger, then push

In `stories.json`:
- New story: add an entry at the top with `id`, `title`, `people`,
  `event`, `first_reported`, `facts`, `sources` (URLs) and a `posts` list.
- Update: add the new facts and sources to the existing entry.
- Add `{"post": "<file name without .json>", "kind": "new" or "update",
  "format": "reel" or "trial_reel"}` to its `posts`.
- Adjacent sports entries also get a `"sport"` field (e.g. `"boxing"`,
  `"bjj"`, `"wrestling"`, `"arm wrestling"`).

Commit the queue file(s) and `stories.json` together and push to `main`.
The push starts the **Make posts** workflow.

### 6. Wait for the Reels, then schedule them

Poll (`git pull` every 30 s, up to 15 minutes) until a commit named
"Make posts" appears after yours and `posts/<name>/reel.mp4` (for a
carousel, `posts/<name>/slide-01.jpg`) exists for every queued post. If a post is missing, read `posts/make-posts-log.txt`
for the reason, leave it unscheduled, and tell the user.

For each finished post, schedule it with Metricool `createScheduledPost`:
- `blogId` 7159326, network `instagram`, `instagramData.type` `REEL`
  (or `TRIAL_REEL` when `posts/<name>/post.json` has `"trial_reel":
  true`), `showReelOnFeed` true, `isAiGenerated` false. If Metricool
  rejects `TRIAL_REEL` (for example, the account isn't eligible yet),
  schedule an MMA post as a regular `REEL` instead, leave an adjacent
  sports post unscheduled, and tell the user.
- `media`: the Reel's raw GitHub URL **pinned to the commit**:
  `https://raw.githubusercontent.com/jlopresti02/WikiPull/<commit sha>/posts/<name>/reel.mp4`
- `videoThumbnailUrl`: the same for `posts/<name>/cover.png`.
- `text`: the exact contents of `posts/<name>/caption.txt`.
- `firstCommentText`: the post's question followed by " 👇 Drop your
  pick", e.g. "Colby or Strickland? 👇 Drop your pick". A first comment
  from the account gives viewers a thread to reply to.
- `autoPublish` true.

**When to schedule (30-minute spacing):** posts go out **one at a time,
at least 30 minutes apart**, so each Reel gets its own push from
Instagram. (On day one, posts 2 minutes apart split each other's reach.)

1. First call Metricool `getScheduledPosts` (brand 7159326, from now to 12
   hours ahead, America/New_York) to see what is already waiting to go out,
   including overflow from earlier runs.
2. The first post goes **10 minutes from now**, or 30 minutes after the
   last post already waiting in Metricool, whichever is later. Never put a
   post within 30 minutes of another one.
3. Each following post goes 30 minutes after the previous one, most
   newsworthy first, until every post has a time.
4. If the slots run past the next run, keep going: later runs read the
   Metricool schedule in step 1 and place their own posts after these, so
   nothing collides and nothing is dropped.

Then add `"scheduled_for"` and the Metricool `plannerUrl` to the post's
entry in `stories.json`, commit and push.

### 6b. Results carousels (after every UFC event)

The first run after a UFC event finishes (usually the Sunday 9 AM run for
a Saturday card) also makes one **results carousel**: every result from
the card in one swipeable post, the kind of post people save and share.
Make it before the Reels, and schedule it **first** (the Reels follow it
in the usual 30-minute slots). Only one per event: check `stories.json`
for an entry with `"format": "carousel"` for that event first.

Get the results from official or reputable sources (UFC.com, ESPN, MMA
Junkie, MMA Fighting): winner, loser, method, round and time for every
fight, plus the four bonuses. Only use what is reported; never guess a
result. If the card isn't finished yet, skip the carousel this run.

Create `posts/queue/<YYYY-MM-DD-HHMM>-<event-slug>-results.json`:

```json
{
  "carousel": true,
  "story_id": "ufc-332-results",
  "headline": "UFC 332 Results",
  "color": "#d2202f",
  "slides": [
    {"type": "cover", "title": "UFC 332 Results", "fighter": ["Natalia Silva", "Natália Silva"],
     "kicker": "New champion", "subtitle": "Silva def. Wang Cong"},
    {"type": "hook", "title": "Night Of Finishes", "fighter": "Payton Talbott",
     "kicker": "Best finish", "subtitle": "Talbott KO R1 2:11"},
    {"type": "result", "label": "Main event · Flyweight title",
     "winner": ["Natalia Silva", "Natália Silva"], "loser": "Wang Cong",
     "method": "Decision (unanimous)", "detail": "R5 5:00"},
    {"type": "result", "label": "Co-main · Bantamweight", "winner": "...", "loser": "...",
     "method": "KO", "detail": "R1 2:11"},
    {"type": "list", "title": "Main Card",
     "rows": [["Winner Name", "Loser Name", "Sub R2"], ["...", "...", "Dec"]]},
    {"type": "list", "title": "Prelims", "rows": [["...", "...", "KO R1"]]},
    {"type": "bonuses", "title": "Bonuses",
     "rows": [["Fight of the Night", "Silva vs Wang"], ["Performance of the Night", "..."]]},
    {"type": "cta", "title": "Who's next for the champ?",
     "lines": ["Comment your pick", "Follow @wwitmma for results"]}
  ],
  "caption": "...",
  "hashtags": ["UFC332", "UFC", "MMA", "MMANews", "NataliaSilva"],
  "sources": ["UFC.com", "ESPN"]
}
```

Slides (2 to 10, Instagram's limit; aim for 7 or 8):
1. **cover**: "<EVENT> RESULTS" (1 to 4 words) with the main event winner
   (or new champion) and a subtitle pill like "SILVA DEF. WANG CONG".
2. **hook**: the night's best moment, a fast finish, a title change, a
   wild ending: a 1 to 4 word title plus that fighter. Instagram often
   re-shows a carousel starting from slide 2, so this must stand alone.
3. **result** slides for the main event and co-main (add one for any
   other headline fight): winner big in color, loser smaller in gray,
   method pill. List alternate names as a list so a photo is found.
4. **list** slides: the rest of the main card, then the prelims, up to 6
   rows each (winner, loser, short method like "KO R1", "Sub R2", "Dec").
5. **bonuses**, if announced.
6. **cta**: a question about what's next ("Who's next for the champ?"),
   with "Comment your pick" and "Follow @wwitmma for results".

Fighters with no photo get the silhouette automatically, so the carousel
always renders. No betting language anywhere (no odds, favorites or
underdogs; "surprise" not "upset").

Caption: first line names the main event result; then 2 to 3 short
sentences with full names, event name and number, city and "UFC results"
/ "MMA results" for search; then a two-option question and 👇; 5
hashtags; sources. Credits are added automatically.

Push it with the other queue files. The Make posts workflow writes
`posts/<name>/slide-01.jpg` ... `slide-NN.jpg` and `caption.txt` (no
video). Schedule it with Metricool `createScheduledPost`:
- `instagramData.type` `POST` (several images make a carousel),
  `isAiGenerated` false, no `showReelOnFeed`, no `videoThumbnailUrl`.
- `media`: every slide's raw GitHub URL, pinned to the commit, in order.
- `text`: `caption.txt`; `firstCommentText`: the question + " 👇".
- Music can't be added through Metricool's scheduling; skip it.

Ledger: `{"post": "<name>", "kind": "new", "format": "carousel"}`.

### 7. Report

Send one short SendUserMessage: which posts were scheduled (headline, time,
which image type was used, and Reel, Trial Reel or carousel), any that were pushed to later slots, which were held back for having no photo, which
stories were skipped as repeats, and any failures. If there were no posts, say so in one line.
