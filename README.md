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
ready for the post template. (Uses `rembg`; the first run downloads its
model, later runs reuse a cached copy.)
