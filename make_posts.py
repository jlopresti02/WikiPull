#!/usr/bin/env python3
"""Turn every post file in posts/queue/ into a finished post.

For each posts/queue/<name>.json:
  1. Pick the image ("visual"), trying each option in order until one works:
       {"type": "fighter", "name": "Jiri Prochazka"}   cutout from Wikimedia Commons
       {"type": "venue",   "name": "Etihad Arena"}     arena/stadium photo, as a framed card
       {"type": "flag",    "country": "Qatar"}         country flag, as a framed card
       {"type": "money"}                               a big dollar sign (always works)
       {"type": "mystery"}                             silhouette with a "?" (always works;
                                                       for fighters with no photo)
       {"type": "text"}                                headline only (always works)
     Old post files with a plain "fighter" field still work.
  2. Pick music: "music_pool": "espn" rotates through music/pools/espn.json;
     "music_search" searches Openverse; "music" names a file directly.
  3. Render the post (render.py) into posts/<name>/.
  4. Remove the file from the queue; posts/<name>/post.json keeps a copy.

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
        if not first_image(folder, "cutouts"):
            if not first_image(folder):
                run("fetch.py", v["name"], "--count", "5")
            if first_image(folder):
                run("cutout.py", str(folder))
        cuts = sorted((folder / "cutouts").glob("*.png")) if (folder / "cutouts").is_dir() else []
        if not cuts:
            return None
        cut = cuts[min(max(int(v.get("photo", 1)), 1), len(cuts)) - 1]
        return {"kind": "fighter", "image": str(cut.relative_to(ROOT)),
                "credit": photo_credit(folder, cut.name)}
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
            print(f"Image: {v} -> {subject['kind']} {subject.get('image') or ''}")
            return True
    return False


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
    specs = sorted(QUEUE.glob("*.json")) if QUEUE.is_dir() else []
    if not specs:
        print("Queue is empty.")
        return
    failed = 0
    for spec_path in specs:
        print(f"\n== {spec_path.name}")
        try:
            spec = json.loads(spec_path.read_text())
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
