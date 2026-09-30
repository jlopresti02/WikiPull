#!/usr/bin/env python3
"""Turn every post file in posts/queue/ into a finished post.

For each posts/queue/<name>.json:
  1. If WikiPull has no cutouts for the fighter yet, fetch photos from
     Wikimedia Commons and make cutouts (fetch.py, then cutout.py).
  2. Render the post (render.py) into posts/<name>/.
  3. Remove the file from the queue; posts/<name>/post.json keeps a copy.

A post that fails is left in the queue with the reason printed, so it can be
fixed and pushed again. The GitHub workflow runs this whenever a post file
is added to posts/queue/.
"""

import json
import subprocess
import sys
from pathlib import Path

from render import ROOT, render, slugify

QUEUE = ROOT / "posts" / "queue"


def has_cutouts(fighter):
    folder = ROOT / "images" / slugify(fighter) / "cutouts"
    return folder.is_dir() and any(folder.glob("*.png"))


def run(*cmd):
    print("$", " ".join(cmd))
    subprocess.run([sys.executable, *cmd], cwd=ROOT, check=True)


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
            fighter = spec["fighter"]
            if not has_cutouts(fighter):
                run("fetch.py", fighter, "--count", "5")
                run("cutout.py", str(ROOT / "images" / slugify(fighter)))
            render(spec_path)
            spec_path.unlink()
        except (Exception, SystemExit) as exc:
            failed += 1
            print(f"!! {spec_path.name} not rendered: {exc}")
    if failed:
        sys.exit(f"{failed} post(s) failed; they stay in posts/queue/.")


if __name__ == "__main__":
    main()
