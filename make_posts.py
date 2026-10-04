#!/usr/bin/env python3
"""Turn every post file in posts/queue/ into a finished post.

For each posts/queue/<name>.json:
  1. Pick the image ("visual"), trying each option in order until one works:
       {"type": "fighter", "name": "Jiri Prochazka"}   cutout from Wikimedia Commons
                                                       (add "file": "<photo file>" to use a
                                                       specific photo in images/<slug>/,
                                                       e.g. one copied from Google Drive)
       {"type": "venue",   "name": "Etihad Arena"}     arena/stadium photo, as a framed card
       {"type": "flag",    "country": "Qatar"}         country flag, as a framed card
       {"type": "money"}                               a big dollar sign (always works)
       {"type": "mystery"}                             silhouette with a "?" (always works;
                                                       for fighters with no photo)
       {"type": "text"}                                headline only (always works)
     Any option may add "headline": "..." to replace the post's headline
     when that option is the one used.
     Old post files with a plain "fighter" field still work.
  2. Pick music: "music_pool": "espn" rotates through music/pools/espn.json;
     "music_search" searches Openverse; "music" names a file directly.
  3. Render the post (render.py) into posts/<name>/.
  4. Remove the file from the queue; posts/<name>/post.json keeps a copy.

Carousel post files ("carousel": true, see carousel.py) skip steps 1-2:
each slide looks up its own fighters (silhouette when there's no photo)
and the slides are written as posts/<name>/slide-NN.jpg.

A post that fails is left in the queue with the reason printed, so it can be
fixed and pushed again. The GitHub workflow runs this whenever a post file
is added to posts/queue/.
"""

import json
import subprocess
import sys
from pathlib import Path

from render import ROOT, photo_credit, render, slugify

QUEUE = ROOT / "posts" / "queue"
DRIVE_MANIFEST = ROOT / "drive_images.json"
POOLS = ROOT / "music" / "pools"


def run(*cmd):
    print("$", " ".join(cmd))
    subprocess.run([sys.executable, *cmd], cwd=ROOT, check=True)


def first_image(folder, sub=""):
    d = folder / sub if sub else folder
    files = sorted(p for p in d.glob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}) \
        if d.is_dir() else []
    return files[0] if files else None


def try_visual(v):
    """Return a subject dict for one visual option, or None if it can't be had."""
    t = v.get("type")
    if t == "fighter":
        folder = ROOT / "images" / slugify(v["name"])
        if not first_image(folder):
            run("fetch.py", v["name"], "--count", "5")
        # Cut out any photo that doesn't have a cutout yet (e.g. one just
        # added from the Google Drive image bank).
        photos = [p for p in folder.glob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}] \
            if folder.is_dir() else []
        if any(not (folder / "cutouts" / (p.stem + ".png")).exists() for p in photos):
            run("cutout.py", str(folder))
        cuts = sorted((folder / "cutouts").glob("*.png")) if (folder / "cutouts").is_dir() else []
        if not cuts:
            return None
        if v.get("file"):
            # a specific photo chosen by the run (Drive or Wikimedia)
            want = Path(v["file"]).stem
            match = [c for c in cuts if c.stem == want]
            if not match:
                print(f"  chosen photo {v['file']} has no cutout; trying the next option")
                return None
            cut = match[0]
        else:
            cut = cuts[min(max(int(v.get("photo", 1)), 1), len(cuts)) - 1]
        return {"kind": "fighter", "image": str(cut.relative_to(ROOT)),
                "credit": photo_credit(folder, cut.name)}
    if t == "pair":
        # Two people side by side in one cutout, e.g. a fighter and the
        # person he called out: {"type": "pair", "left": {"name": ...},
        # "right": {"name": ..., "file": ...}}. Both must have a cutout.
        from PIL import Image
        sides = []
        for side in ("left", "right"):
            sub = try_visual({"type": "fighter", **v[side]})
            if not sub:
                print(f"  pair: no cutout for {v[side].get('name')}")
                return None
            sides.append(sub)
        cuts = []
        for sub in sides:
            im = Image.open(ROOT / sub["image"]).convert("RGBA")
            cuts.append(im.crop(im.getbbox() or (0, 0, im.width, im.height)))
        # Same height by default; a side's "scale" (e.g. 0.6) shrinks it, for
        # a close-up headshot next to a half-body photo. Bottoms line up.
        h = max(c.height for c in cuts)
        hs = [max(1, round(h * float(v[side].get("scale", 1)))) for side in ("left", "right")]
        cuts = [c.resize((max(1, round(c.width * t / c.height)), t), Image.LANCZOS)
                for c, t in zip(cuts, hs)]
        overlap = int(min(c.width for c in cuts) * 0.12)
        # A side's "lift" (fraction of the tallest height) raises it off the
        # bottom, so a small headshot isn't cut off by the frame.
        lifts = [int(h * float(v[side].get("lift", 0))) for side in ("left", "right")]
        H = max(c.height + l for c, l in zip(cuts, lifts))
        out = Image.new("RGBA", (cuts[0].width + cuts[1].width - overlap, H), (0, 0, 0, 0))
        out.alpha_composite(cuts[1], (cuts[0].width - overlap, H - cuts[1].height - lifts[1]))
        out.alpha_composite(cuts[0], (0, H - cuts[0].height - lifts[0]))  # left person in front
        folder = ROOT / "images" / "pairs"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (slugify(v["left"]["name"] + " " + v["right"]["name"]) + ".png")
        out.save(path)
        credits = [s["credit"] for s in sides if s.get("credit")]
        credit = "; ".join(dict.fromkeys(credits)) or None
        return {"kind": "fighter", "image": str(path.relative_to(ROOT)), "credit": credit}
    if t in ("venue", "flag"):
        query = v.get("name") or v.get("country")
        folder = ROOT / "images" / (("flag-" if t == "flag" else "") + slugify(query))
        if not first_image(folder):
            if t == "flag":
                run("fetch.py", query, "--count", "1", "--flag")
            else:
                run("fetch.py", query, "--count", "3")
        img = first_image(folder)
        if not img:
            return None
        return {"kind": "card", "image": str(img.relative_to(ROOT)),
                "credit": photo_credit(folder, img.name)}
    if t == "money":
        return {"kind": "graphic", "graphic": "money", "image": None, "credit": None}
    if t == "mystery":
        return {"kind": "graphic", "graphic": "mystery", "image": None, "credit": None}
    if t == "text":
        return {"kind": "none", "image": None, "credit": None}
    raise ValueError(f"unknown visual type: {t}")


def resolve_visual(spec):
    if spec.get("subject"):
        return False
    options = spec.get("visual")
    if not options:
        if spec.get("fighter"):
            options = [{"type": "fighter", "name": spec["fighter"],
                        "photo": spec.get("photo", 1)}]
        else:
            options = []
    for v in list(options) + [{"type": "text"}]:
        try:
            subject = try_visual(v)
        except Exception as exc:
            print(f"  visual {v} failed: {exc}")
            subject = None
        if subject:
            spec["subject"] = subject
            # An option can carry its own headline, used only if that option
            # wins: e.g. the withdrawn fighter's photo with "SOPAJ OUT".
            if v.get("headline"):
                spec["headline"] = v["headline"]
            print(f"Image: {v} -> {subject['kind']} {subject.get('image') or ''}"
                  f"  headline: {spec['headline']}")
            return True
    return False


def sync_drive():
    """Download photos listed in drive_images.json (the user's Google Drive
    image bank) into images/<person>/drive-<name>.<ext>, with a credit entry,
    and cut them out. The Drive folder must be shared as "anyone with the
    link can view"; otherwise the download returns a sign-in page, which is
    skipped with a note in the log."""
    if not DRIVE_MANIFEST.exists():
        return
    import io
    import urllib.request
    from PIL import Image
    manifest = json.loads(DRIVE_MANIFEST.read_text())
    touched = set()
    for f in manifest.get("files", []):
        person = f.get("person")
        if not person or f.get("skip"):
            continue
        folder = ROOT / "images" / slugify(person)
        stem = "drive-" + slugify(Path(f["name"]).stem)
        if any(folder.glob(stem + ".*")):
            continue
        url = f"https://drive.usercontent.google.com/download?id={f['id']}&export=download&confirm=t"
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = r.read()
            with Image.open(io.BytesIO(data)) as im:
                im.load()
                fmt = (im.format or "JPEG").lower()
        except Exception as exc:
            print(f"Drive: could not download {f['name']} ({exc}); is the folder shared by link?")
            continue
        ext = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}.get(fmt, ".jpg")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (stem + ext)).write_bytes(data)
        credits_path = folder / "credits.json"
        credits = json.loads(credits_path.read_text()) if credits_path.exists() else []
        credits.append({"file": stem + ext, "title": f["name"],
                        "author": f.get("credit") or "WWIT MMA News",
                        "license": "", "source": f"https://drive.google.com/file/d/{f['id']}"})
        credits_path.write_text(json.dumps(credits, indent=2) + "\n")
        print(f"Drive: saved images/{folder.name}/{stem + ext}")
        touched.add(folder)
    for folder in sorted(touched):
        run("cutout.py", str(folder))


def get_cut(names):
    """For carousels: the first of `names` that has a usable cutout, as
    (RGBA image, credit). (None, None) when none do."""
    if not names:
        return None, None
    for name in (names if isinstance(names, list) else [names]):
        try:
            subject = try_visual({"type": "fighter", "name": name})
        except Exception as exc:
            print(f"  photo for {name} failed: {exc}")
            subject = None
        if subject:
            from PIL import Image
            with Image.open(ROOT / subject["image"]) as im:
                return im.convert("RGBA"), subject["credit"]
    print(f"  no photo for {names}: using the silhouette")
    return None, None


def resolve_music(spec):
    """Fill in "music", "music_credit" and "music_start" from a pool or a
    search; turns on "reel". Returns True if the spec changed."""
    if spec.get("music"):
        return False
    pool = spec.get("music_pool")
    if pool:
        tracks = json.loads((POOLS / f"{pool}.json").read_text())["tracks"]
        state_file = POOLS / "rotation.json"
        state = json.loads(state_file.read_text()) if state_file.exists() else {}
        i = state.get(pool, 0) % len(tracks)
        state[pool] = i + 1
        state_file.write_text(json.dumps(state, indent=2) + "\n")
        t = tracks[i]
        spec["music"] = t["file"]
    else:
        query = spec.get("music_search")
        if not query:
            return False
        folder = ROOT / "music" / slugify(query)
        credits_file = folder / "credits.json"
        if not credits_file.exists():
            run("music.py", query, "--count", "3")
        if not credits_file.exists():
            raise RuntimeError(f"no music found for '{query}'")
        tracks = json.loads(credits_file.read_text())
        t = tracks[min(max(int(spec.get("music_pick", 1)), 1), len(tracks)) - 1]
        spec["music"] = f"music/{folder.name}/{t['file']}"
    spec.setdefault("music_credit", f"\"{t['title']}\" by {t['artist']} / {t['license']}")
    spec.setdefault("music_start", t.get("best_start", 0))
    spec["reel"] = True
    print(f"Music: {spec['music']} from {spec['music_start']}s")
    return True


def main():
    sync_drive()
    specs = sorted(QUEUE.glob("*.json")) if QUEUE.is_dir() else []
    if not specs:
        print("Queue is empty.")
        return
    failed = 0
    for spec_path in specs:
        print(f"\n== {spec_path.name}")
        try:
            spec = json.loads(spec_path.read_text())
            if spec.get("carousel"):
                from carousel import render_carousel
                render_carousel(spec_path, get_cut)
                spec_path.unlink()
                continue
            changed = resolve_visual(spec)
            changed = resolve_music(spec) or changed
            if changed:
                spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n")
            render(spec_path)
            spec_path.unlink()
        except (Exception, SystemExit) as exc:
            failed += 1
            print(f"!! {spec_path.name} not rendered: {exc}")
    if failed:
        sys.exit(f"{failed} post(s) failed; they stay in posts/queue/.")


if __name__ == "__main__":
    main()
