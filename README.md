# WikiPull

Downloads openly licensed photos from Wikimedia Commons into this repo, so
Claude (or anything else) can pull them into a workflow, like the MMA news
post template.

## How to get images

**Option 1: Run it by hand**
1. Open the **Actions** tab, pick **Fetch images**, tap **Run workflow**.
2. Type a search (e.g. `Renato Moicano`) and how many images you want.
3. In about a minute the photos appear in `images/<name>/`.

**Option 2: Add to the queue**
Add names to `queue.txt`, one per line, and commit. The workflow fetches
each one, commits the images, and clears the queue. This is the route Claude
uses: it pushes a name, waits for the run, then pulls the images.

**Option 3: Run locally**
```
python fetch.py "Renato Moicano" --count 5
```
No packages to install; it only uses Python's standard library.

## What you get

```
images/renato-moicano/
  01-....jpg        # the main photo Wikipedia uses, when there is one
  02-....jpg
  credits.md        # author, license and source link for each image
  credits.json      # same info, machine-readable
```

Images are resized to about 1600px wide. Only files under CC0, CC BY,
CC BY-SA or public domain are kept.

## Using the photos in posts

These licenses let you reuse the photos, including commercially, but most
require **credit to the photographer** (see `credits.md`), and CC BY-SA
also asks that edited versions be shared under the same license. A small
"Photo: Name / CC BY-SA 4.0" line on the post or in the caption covers it.

## Cutouts

Every run also removes the background from each photo and saves a
transparent PNG in `images/<name>/cutouts/`, cropped to the fighter and
ready for the post template. (Uses `rembg`, then trims the old background's halo and fades any edge where the photo's frame cut the fighter off; the first run downloads its
model, later runs reuse a cached copy.)

## Making posts

WikiPull also builds finished WWIT MMA News posts.

1. Add a post file to `posts/queue/`, e.g. `posts/queue/2026-09-30-bjp-returns.json`:
   ```json
   {
     "fighter": "Jiri Prochazka",
     "headline": "BJP Returns",
     "caption": "BJP is back. Jiří Procházka headlines UFC Qatar...",
     "sources": ["CBS Sports", "ESPN"],
     "color": "#d2202f",
     "photo": 1
   }
   ```
   `fighter` is the Wikimedia search name, `headline` is 1 to 3 words,
   `color` and `photo` (which cutout to use) are optional.
2. Push. The **Make posts** workflow fetches photos and cutouts if the
   fighter is new, renders the post, and commits it to `posts/<name>/`:
   - `post.png`: 1080×1350, ready for Instagram
   - `caption.txt`: your caption plus the source and photo credit lines
   - `post.json`: the post file, for the record

### Reels with music

Add `"reel": true` to a post file to also get `reel.mp4`: an 8-second
1080×1920 video in the same design (headline fades in, the fighter slowly
pushes in), plus `cover.png` for the Reel cover. Add music with:

```json
"music": "music/track.mp3",
"music_credit": "Track by Artist / CC BY 4.0",
"music_start": 12.5,
"seconds": 8
```

The music is baked into the video. See `music/README.md` for which tracks
are safe to use.

To preview locally: `python render.py posts/queue/<name>.json`

The design follows the MMA post template: the WWIT MMA NEWS tag, a big
headline in Anton (bundled in `fonts/`, SIL Open Font License), and the
fighter as large as possible without ever touching the text.
