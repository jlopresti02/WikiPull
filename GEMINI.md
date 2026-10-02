# Gemini images → Google Drive

Generates images with Google Gemini through GitHub Actions and keeps them in
the user's Google Drive folder **Gemini Images**
(folder id `100IXlX0jQO1WqckSc6pW29d2ejaVPc_W`,
https://drive.google.com/drive/folders/100IXlX0jQO1WqckSc6pW29d2ejaVPc_W).

## What it's for

AI-made images: backgrounds, arenas and cages, crowds, generic (unnamed)
referees, lighting and texture plates, graphics. **Never** use it to make
images of real, named people (fighters, Dana White, real referees): on a
news account those would pass as real photos, and Gemini usually refuses
anyway. Real people keep coming from Wikimedia Commons via `fetch.py`.

## One-time setup (the user does this)

1. Get a Gemini API key at https://aistudio.google.com/apikey.
2. In GitHub: WikiPull → Settings → Secrets and variables → Actions →
   **New repository secret**, name `GEMINI_API_KEY`, paste the key.
3. Optional: under the **Variables** tab, add `GEMINI_IMAGE_MODEL` to use a
   different Gemini image model (default `gemini-2.5-flash-image`).

## Making images

Either:
- **Actions tab → Gemini images → Run workflow**: type a prompt, a short
  name, a count (1-4) and an aspect ratio (default 9:16 for Reels).
- **Push a request file** to `gemini/requests/<anything>.json`:

```json
[
  {"name": "empty-octagon", "prompt": "An empty UFC-style octagon cage under dramatic arena spotlights, dark crowd in the background, no people in the cage, no logos, photorealistic", "count": 2, "aspect_ratio": "9:16"},
  {"name": "red-smoke-bg", "prompt": "Abstract red smoke background, dark, high contrast, room for text", "count": 1, "aspect_ratio": "9:16"}
]
```

The workflow saves `gemini/images/<name>/<name>-<n>.png` plus `prompt.txt`,
moves the request to `gemini/requests/done/`, logs to `gemini/log.txt`,
and commits "Gemini images".

## Copying to Google Drive (Claude does this)

After a "Gemini images" commit:
1. `git pull` and read `gemini/drive.json` (map of repo path → Drive file id).
2. For each image in `gemini/images/` not yet in `drive.json`: make (or
   reuse) a subfolder named `<name>` inside the Gemini Images folder, then
   upload the file with the Google Drive `create_file` tool
   (`base64Content`, `contentMimeType` `image/png`,
   `disableConversionToGoogleType` **true** (otherwise Drive turns it into
   a Google Doc), `parentId` = that
   subfolder). Record the new file id in `drive.json`.
3. Commit `drive.json` and push.

Claude can also read images back from that Drive folder for any project
(search by `parentId`, then `download_file_content`), including ones the
user drops there by hand.
