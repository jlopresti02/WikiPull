#!/usr/bin/env python3
"""Write a sketch post file into posts/queue/ from environment variables.

Used by the "Sketch video" workflow (.github/workflows/sketch.yml); the
inputs arrive as VIDEO, CAPTIONS ("phrase one | phrase *two*"), TITLE, TAG,
START, END, FIGHTERS, AUDIO, CAPTION and FOOTAGE. Prints the file's path.
"""

import datetime as dt
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def env(name, default=""):
    return (os.environ.get(name) or default).strip()


def num(name):
    v = env(name)
    return float(v) if v else None


def main():
    video = env("VIDEO")
    if not video:
        raise SystemExit("VIDEO is required")
    captions = [c.strip() for c in env("CAPTIONS").split("|") if c.strip()]
    title = env("TITLE")
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=-4)))  # Eastern (EDT)
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "breakdown").lower()).strip("-")[:40] or "breakdown"
    name = f"{now:%Y-%m-%d-%H%M}-sketch-{slug}"
    head_words = re.sub(r"[^A-Za-z0-9 ]+", " ", title).split()[:3] or ["Breakdown"]
    caption = env("CAPTION") or (
        f"Breaking down {title or 'the exchange'} frame by frame ✏️\n"
        "Who had the better game plan? 👇\n\nFight breakdown, drawn by WWIT MMA. MMA news.")
    spec = {
        "story_id": f"sketch-{slug}",
        "headline": " ".join(head_words),
        "format": "sketch",
        "visual": [{"type": "text"}],
        "color": "#111111",
        "caption": caption,
        "hashtags": ["MMA", "UFC", "MMABreakdown", "FightBreakdown", "MMANews"],
        "sources": [],
        "music_pool": "espn",
        "sketch": {
            "video": video,
            "captions": captions,
            "title": title or None,
            "tag": env("TAG") or None,
            "start": num("START"),
            "end": num("END"),
            "fighters": int(env("FIGHTERS", "2") or 2),
            "audio": env("AUDIO", "music") or "music",
        },
        "requested": True,
    }
    if env("FOOTAGE"):
        spec["footage_credit"] = env("FOOTAGE")
    spec["sketch"] = {k: v for k, v in spec["sketch"].items() if v is not None}
    path = ROOT / "posts" / "queue" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n")
    print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
