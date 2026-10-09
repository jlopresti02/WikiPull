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
PFL, ONE Championship (its own search every run; see the ONE section
below) and others, fight announcements and bookings,
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

**Week 1 review (Oct 1-4, 55 Reels; added Oct 4).** Median 194 views per
Reel, but followers only went 304 to 307 and likes/shares/saves are near
zero: reach is fine, conversion is the problem. What the week showed:
- **Fighter vs. fighter drama wins**: Figueiredo's fake punch at Talbott
  (491), Wang mocking Silva (279), Morales says nobody will fight him
  (286), Pimblett would vacate rather than fight a teammate (284).
- **Boxing and business flop**: Fury/Trump 24, Dana vs. Hearn 37,
  Whittaker 50. Routine bookings too: Lucindo vs. Caliari 82.
- **Overnight posts die**: posts going out 12-6 AM got a median of 91
  views vs. 194 overall (UFC 332 results queued past midnight: Silva 91,
  Nickal/Pyfer 75, Fury 24). **8 PM to midnight is this account's best
  window** (median about 220), better than mornings or afternoons.
- **More posts didn't mean more followers**: 20 Reels on Oct 1 alone.
  Fewer, stronger posts.

What performs (from @wwitmma's first day of data, 2026-10-01):
- **Top posts (200-260 views)**: a well-known star in the first line, plus
  conflict or stakes: a feud, a clapback, an ultimatum, a refusal, a
  fight falling through, a "who's next?" mystery.
- **Bottom posts (34-44 views)**: no person's photo, a repeat story with a
  weak update, or a lesser-known fighter with no hook.
- Viewers decide in about 2 seconds (average watch time 1.6-3.4 s), so the
  first frame (headline + face) matters most.

Rules:
- **Daily cap: 10 automated news posts per calendar day (Eastern)**:
  the news Reels and Trial Reels this runbook makes. **Not counted**: the
  results carousel after a UFC event (step 6b) and anything the user asks
  for directly (picks, memes, requested stories, manual posts); those
  don't use up the 10 and are never dropped for the cap. Before writing
  posts, count the day's automated news posts already published or
  scheduled (step 6 explains how) and only make as many as fit. Rank the run's stories
  **most newsworthy first** (star + conflict at the top, routine bookings
  and lesser-known names last) and **drop the weakest** when over the cap.
  Dropped stories are not queued for later; say in the report which were
  skipped for the cap. A genuinely big story (title fight booked, a star's
  result, a major injury or withdrawal) can replace a weaker one already
  scheduled for that day if it hasn't gone out yet.
- **Save the evening (Oct 5).** 8 PM to midnight is this account's best
  window, but on Oct 4 the day's 10 were used up by 7:30 PM and the 10 PM
  run's stories got pushed to 7:30 AM. So **4 of the 10 are reserved for
  posts going out 7 PM to 12:30 AM**:
  - Posts scheduled before 7 PM may use at most **6** of the day's 10.
    When a daytime run has more good stories than that, pick the ones
    that would go stale fast for now, and **hold the rest for the evening**:
    add them to `stories.json` as normal entries (facts, sources) with
    `"held_for_evening": true` and an empty `"posts": []`, and don't queue
    them. The 6 PM and 10 PM runs read held entries first, post the ones
    that still stand up (dropping the flag when they do), and drop any
    that went stale. Stories with a reaction or a "what's next" angle
    hold up fine for a few hours.
  - The 6 PM run schedules from **7 PM** onward (not 10 minutes from now)
    unless a story is breaking, and the 10 PM run fills the rest up to
    12:30 AM. Evening slots never get pushed to the next morning while
    the day's cap still has room.
  - Posts that go out after midnight (12:00-12:30 AM) count toward the
    day before, not the new day, so overnight overflow doesn't eat the
    next day's cap.
- **Breaking-news exception (added at the user's request, Oct 4):** a
  truly major breaking story goes out **in the current news cycle even if
  the day is already at 10**, as a regular Reel in the next open slot. The
  bar is high, roughly once a week at most: a champion vacating, stripped
  or retiring; a superstar (McGregor, Jones, Pereira, Topuria, Makhachev
  level) booked, injured out of a fight or making a shock announcement; a
  main event or title fight falling apart close to the event; a death or
  serious incident (reported plainly); a major business shake-up (UFC
  leadership, a broadcast deal). Fight-week drama, callouts and routine
  bookings are never exceptions, however good. Breaking stories still
  skip quiet hours unless they're so big they'd be stale by 7:30 AM; then
  post at the next slot even overnight. Say in the report when the
  exception was used and why.
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
  pro boxing, arm wrestling, spectacle sports). Post at most **1 per run**
  (they flopped in week 1, see above), picking the most interesting: a famous name, a viral moment, a feud,
  or a crossover with MMA. Skip routine results nobody outside the sport
  would recognize.

**ONE Championship (added at the user's request, Oct 5).** The best
Reel of week 1 was a ONE story: "ERDOGAN 14-0" (Shamil Erdogan stays
unbeaten, next wrestles Kyle Snyder at RAF), a Trial Reel with 636 views,
the highest 3-second view rate of the week (38%), still climbing two days
later. Few English-language accounts cover ONE, so there's less
competition. So **post the big ONE Championship stories every run** as
**Trial Reels**:
- Big means one of: a title change or title fight booked; an unbeaten
  fighter's streak continuing or ending; a viral finish; a crossover with
  a name UFC fans know (a UFC veteran, Demetrious Johnson, a RAF or boxing
  tie-in); a star (Rodtang, Superlek, Takeru, Jonathan Haggerty, Anatoly
  Malykhin, Christian Lee, Adriano Moraes level) doing something notable.
  ONE's Muay Thai and kickboxing count when the story is that big. Skip
  routine results and bookings.
- Headline the hook in numbers or stakes when it fits ("ERDOGAN 14-0",
  "NEW CHAMP"). Use the fighter's own photo; check the Drive image bank
  first, and if there's no usable photo, hold the post and tell the user
  so they can add one, instead of using a silhouette.
- Hashtags: `MMA` or `MMANews`, `ONEChampionship`, the event tag
  (`ONEFightNight48`, `ONE172`), and the fighter's name.
- They count toward the daily 10 like any news post, but they're **not
  dropped as lesser-known fighters**: rank them like a mid-tier UFC story,
  and prefer the evening slots. They are not adjacent sports, so the
  one-per-run adjacent sports limit doesn't apply. Up to 2 ONE posts a
  day; more only for a truly huge night.
- Include ONE Championship in the news sweep every run (onefc.com news,
  plus MMA outlets that cover ONE).

Mark a Trial Reel by adding `"trial_reel": true` to its queue file.
Order the schedule with regular Reels first (most newsworthy first),
then Trial Reels. The 30-minute spacing applies to every post, Trial
Reels included.

### 3b. Check the Google Drive image bank, then pick each photo

The user keeps extra photos in a Google Drive folder, **Gemini Images**
(folder id `100IXlX0jQO1WqckSc6pW29d2ejaVPc_W`). `drive_images.json` in the
repo lists every Drive photo already brought in.

1. **List the folder** with the Google Drive `search_files` tool:
   `parentId = '100IXlX0jQO1WqckSc6pW29d2ejaVPc_W'` (pageSize 100; follow
   `nextPageToken`). If it has subfolders named after people, list those
   too; their files belong to that person.
2. **Add new files** (any id not in `drive_images.json`) to its `files`
   list: `{"id", "name", "person"}`. Work out the person from the file
   name ("Joe_Rogan_3.JPG" is Joe Rogan, "Josh Hokit 1" is Josh Hokit) or
   the subfolder name, spelled the way Wikipedia spells them. If the file
   has a description naming the photographer or source, put it in
   `"credit"`. If you can't tell who it is, add it with `"skip": true`.
3. If you added anything, commit and push `drive_images.json` **on its
   own first**. That starts the Make posts workflow, which downloads the
   photos into `images/<person>/drive-<name>.jpg` and cuts them out. Wait
   for its "Make posts" commit (`git pull` every 30 s, up to 10 minutes).
   If `posts/make-posts-log.txt` says a Drive file couldn't be downloaded
   ("is the folder shared by link?"), tell the user in the final report
   that the folder needs to be shared as "anyone with the link can view",
   and carry on with the other photos.
4. **Pick the best photo for each post.** For every person you're about
   to show, look at all of their cutouts, Drive and Wikimedia alike
   (`images/<slug>/cutouts/*.png`; open them with Read). Choose the one
   that suits *this* post best:
   - the face is clear, large and in focus, one person, not cut off oddly;
   - the expression fits the story: intense or serious for feuds,
     call-outs and fight news; smiling for wins, signings and good news;
   - fight gear or a press-event look for fight stories; a recent look
     over an old one;
   - **funny photos for funny stories** (user, Oct 4): when a story is
     lighthearted, a trolling post, a joke or something absurd, use a
     playful photo if the person has one. Drive files with "funny" in
     the name are meant for this (e.g. `drive-sean-strickland-funny`,
     Strickland as a scorpion), and so are old-look photos marked
     with a `"note"` in `drive_images.json` (e.g. `drive-sean-strickland-3`,
     Strickland years ago with hair). Keep these out of serious
     stories (injuries, title fights, real disputes).
   Put the chosen photo's file name on that visual entry:
   `{"type": "fighter", "name": "Joe Rogan", "file": "drive-joe-rogan-3"}`.
   If a person has no cutouts yet (new name), leave out `"file"`; the
   workflow fetches and uses the first good photo.

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
  "seconds": 5,
  "question": "BJP or Stirling?",
  "follow_card": true,
  "reel": true
}
```

**On the Reel itself** (added Oct 3: people leave after about 2.4 s and
almost nobody opens the caption). Reels are **5 seconds** (Oct 4): shorter
means more people reach the end and it loops. The renderer pushes in on the
face from the first frame; leave `"seconds"` at 5 unless there's a reason.
- `"question"`: at about 2 s the headline turns into this question, set just
  as big. Use the same two-option question as the caption's second line,
  2 to 4 words, no emoji (the font has none): "COLBY OR STRICKLAND?",
  "BAN IT?", "FAIR OR NOT?". Every post gets one.
- `"follow_card": true`: the last 1.2 s read FOLLOW @WWITMMA, then the
  Reel loops back to the headline. Every post gets it.

**Reel format v2 (trial, Oct 8, user request).** `reel_v2.py` renders the
"WWIT Reel Format v2" mockup: an 8-second loop with two fighter photos and a
VS badge (hook), a white story card with fact chips (context), then a
"YOUR PICK" card with two answer boxes. A post opts in with `"format": "v2"`
and a `"v2"` block (`tag`, `kicker`, `hook`, `left`, `right`, `story`,
`chips`, `question`, `options`; see the top of `reel_v2.py`). The first one
is Leben vs. Akiyama (Oct 8, 7 PM). Use it only when the user asks until
they decide whether it replaces the default format.

**v2 test day: Friday, Oct 9 (user request, Oct 8 10 PM run).** Every
automated news Reel and Trial Reel scheduled to go out on Oct 9 (Eastern)
uses `"format": "v2"`; results/DWCS carousels stay as they are. From
Oct 10 on, go back to the default format unless the user says otherwise.
Writing a v2 post:
- Keep everything else in the post file as usual (headline, `visual` as a
  fallback, caption, `question`, 5 hashtags, sources, `trial_reel`), and
  add the `"v2"` block. `"seconds"` can be left out (v2 is 8 s).
- `left` = the story's main person, `right` = the other side of the
  conflict (opponent, the person they called out or answered). Use lists
  with alternate names, and `"file"` to pick a photo, as in `visual`. For
  a one-person story, put the most relevant second person on the right
  (the rival, the champion they want), never Dana as a stand-in.
- `tag`: promotion + division or event ("UFC · WELTERWEIGHT", "RAF ABU
  DHABI"). `kicker`: 2-4 words of stakes ("TITLE SHOT NEXT?", "NOT
  SIGNED"). `hook`: 2-4 words ("Colby vs Prates"). `story`: one own-words
  sentence. `chips`: 2-3 short facts (records, date, event). `options`:
  two 1-2 word answers matching the question.
- Mark these in the ledger post entry with `"style": "v2"` so their
  views can be compared with default-format posts.

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

**Photo-needed alerts** (requested 2026-10-04). Right after the Reels
render, and before scheduling, check every post's `post.json`. If
`subject.kind` is `"graphic"` with `"graphic": "mystery"` (silhouette)
or `"none"`, or the photo used is not the person the story is about,
send the user a **PushNotification** (status "proactive") straight
away, separate from the end-of-run alert, so they can add a photo while
there's still time. One notification per run covering every such post,
under 200 characters, naming who needs a photo, the headline and the
time it's scheduled for, and saying where to put it, e.g.
"Photo needed: Esteban Ribovics ('Blame The AC?', 2:25 PM) and Raoni
Barcelos (2:55 PM). Add to Gemini Images in Drive to replace the silhouette."
For a held-back text-only post, say it's held until a photo is added.
Schedule silhouette posts at the end of the run's slots so there is as
much time as possible to swap them.

**Swap silhouettes when a photo arrives.** At the start of every run
(and whenever the user asks), check Metricool's waiting posts and
`stories.json` for posts that went out to Metricool with a silhouette
(`"image"` says silhouette) and haven't published yet. If the Drive
folder now has a photo of that person: add it to `drive_images.json`,
re-queue the post (its original queue file from git history plus
`"file": "drive-<slug>"` on the person's visual entry) in one push, wait
for the Make posts commit, check the new `post.png`, then update the
Metricool post (`updateScheduledPost`, same caption from the new
`caption.txt`, media and cover pinned to the new commit). If the post
is due within about 10 minutes, first move it 30 minutes later (keeping
the 30-minute spacing) so the silhouette version never goes out. Record
the new image and time in `stories.json`. Held-back text-only posts get
rendered and scheduled the same way once a photo is added.

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
- **2 short sentences** of the facts (Oct 4: long captions got no likes or
  comments; nobody reads them), naturally packed with search
  keywords: full fighter names, the promotion (UFC, PFL, ONE), the event
  name and number, weight class, city/country, and terms like "MMA news",
  "UFC news", "fight announcement", "title fight" where they're true.
- **Second line: a two-option question** with a 👇, so people see it
  without opening the caption: "Colby or Strickland? 👇", "Ban it or keep
  it? 👇", "Fair or not? 👇". Through Oct 2, 38 Reels got 0 comments with
  only an open question at the end; easy picks are easier to answer.
- End with a short open question too ("Who takes it?").
- Keep the written part (before sources and credits) under about 450
  characters. Use 1 or 2 emoji at most.

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

**Quiet hours (Oct 4): nothing goes out between 12:30 AM and 7:30 AM
Eastern.** Overnight posts got half the views of everything else.

1. First call Metricool `getScheduledPosts` (brand 7159326, from now to 24
   hours ahead, America/New_York) to see what is already waiting to go out,
   including overflow from earlier runs. For the daily cap (step 3), count
   that day's automated news posts in `stories.json` (`scheduled_for`
   dates; leave out results carousels and posts the user asked for) plus
   any of those waiting in Metricool for that day.
2. The first post goes **10 minutes from now**, or 30 minutes after the
   last post already waiting in Metricool, whichever is later. Never put a
   post within 30 minutes of another one.
3. Each following post goes 30 minutes after the previous one, most
   newsworthy first, until every post has a time.
4. **If a slot would land in quiet hours**, move it and everything after
   it to **7:30 AM** onward (30 minutes apart). Those morning posts count
   toward the next day's cap of 10, so drop the weakest if that day would
   go over. Late-night news that will be stale by morning (a live result
   everyone already covered) is better skipped than posted at 8 AM; a
   story with a reaction or a next step (a callout, a "what's next") holds
   up fine.
5. If the slots run past the next run, keep going: later runs read the
   Metricool schedule in step 1 and place their own posts after these, so
   nothing collides.

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

### 6c. Contender Series carousels (after every DWCS episode)

Added at the user's request (Oct 7): followers like keeping up with Dana
White's Contender Series, even though the fighters aren't known names. So
DWCS results are **not** skipped as "lesser-known fighters"; instead, the
first run after each DWCS episode (usually the Wednesday 9 AM run, since
episodes air Tuesday night) makes one **DWCS carousel**. One per episode:
check `stories.json` for a `"format": "carousel"` entry for that week
first. Individual DWCS fighters don't get their own Reels unless the story
has a real hook beyond the contract (as with a famous name or a viral
moment).

- Same file format, renderer and scheduling as step 6b (`"carousel":
  true`, Metricool `POST` with every slide pinned to the commit, first
  comment = question + " 👇"). Schedule it in the run's first open slot,
  ahead of that run's Reels, following the usual spacing and quiet hours.
- Like the UFC results carousel, it **doesn't count toward the daily 10**.
- Slides (aim for 5 to 8):
  1. **cover**: "DWCS WEEK 9" or a hook like "4 CONTRACTS", with the
     standout winner and a subtitle pill ("SEASON 10 · WEEK 9").
  2. **hook**: the best moment of the night (fastest KO, wildest finish,
     a great backstory, like Dana's own runner earning a deal).
  3. **result** slides, one per fighter who got a contract: winner, loser,
     method and time; the label says "UFC contract ✓" plus weight class.
     List alternate name spellings so a photo is found; the silhouette
     fills in automatically when there's none.
  4. **list**: every result from the night, contract or not (winner, loser,
     short method).
  5. **cta**: "Who'll make noise in the UFC first?" with "Comment your
     pick" and "Follow @wwitmma for DWCS results".
- Caption: first line names the number of contracts and the standout
  ("Dana White handed out 4 UFC contracts on Contender Series Week 9.");
  then 1 to 2 short sentences with the names, "Dana White's Contender
  Series", season and week, "UFC contract" and "MMA news" for search; a
  two-option question with 👇; hashtags `DWCS`, `UFC`, `MMANews`,
  `ContenderSeries` and the standout fighter's name; sources (UFC.com,
  MMA Junkie, Sherdog...). Only report results from reputable sources.
- Ledger: one entry per episode (`id` like `dwcs-s10-week-9`), with
  `{"post": "<name>", "kind": "new", "format": "carousel"}`.

### 7. Report

Send one short SendUserMessage: which posts were scheduled (headline, time,
which image type was used, and Reel, Trial Reel or carousel), any that were pushed to later slots, which were held back for having no photo, which silhouettes are still waiting for a photo (person and time), which
stories were skipped as repeats, and any failures. If there were no posts, say so in one line.
