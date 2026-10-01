#!/usr/bin/env python3
"""Fetch openly licensed music for Reels from Openverse.

Usage:
    python music.py "epic hip hop"               # top 3 tracks
    python music.py "cinematic drums" --count 5

Openverse (https://openverse.org) is a free search engine for Creative
Commons media; its music comes mostly from Jamendo, Freesound and Wikimedia.
Only tracks whose license allows commercial use AND editing are kept
(CC0, public domain, CC BY, CC BY-SA), since a Reel cuts and fades them.

Tracks land in music/<slug>/ with credits.json and credits.md recording the
title, artist, license, source page, and "best_start": where the most
energetic stretch of the track begins, so a Reel can start on the hook.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
MUSIC_DIR = ROOT / "music"
API = "https://api.openverse.org/v1/audio/"
USER_AGENT = "WikiPull/1.0 (https://github.com/jlopresti02/WikiPull) python-urllib"
OK_LICENSES = {"cc0", "pdm", "by", "by-sa"}  # commercial use + modification allowed
MIN_SECONDS = 20
CLIP_SECONDS = 8  # length used to find the best stretch


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "music"


def get_json(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except Exception as exc:
            detail = ""
            if hasattr(exc, "read"):
                try:
                    detail = " " + exc.read().decode("utf-8", "replace")[:300]
                except Exception:
                    pass
            if attempt == 2:
                print(f"  request failed: {exc}{detail}", file=sys.stderr)
                raise
            print(f"  retrying after error: {exc}{detail}", file=sys.stderr)
            time.sleep(3 * (attempt + 1))


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


def license_label(item):
    lic, ver = item.get("license", ""), item.get("license_version") or ""
    if lic == "cc0":
        return "CC0"
    if lic == "pdm":
        return "Public domain"
    return f"CC {lic.upper()} {ver}".strip()


def best_start(path, seconds=CLIP_SECONDS):
    """Start time (s) of the loudest, busiest stretch of the track."""
    if not shutil.which("ffmpeg"):
        return 0.0
    rate = 8000
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", str(rate),
         "-f", "s16le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    hop = rate // 4  # quarter-second steps
    n = len(x) // hop
    if n * hop < (seconds + 2) * rate:
        return 0.0
    energy = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
    win = int(seconds * 4)
    sums = np.convolve(energy, np.ones(win), mode="valid")
    # Skip the first 2 s (intros) and leave 2 s of tail.
    lo, hi = 8, max(9, len(sums) - 8)
    i = lo + int(np.argmax(sums[lo:hi])) if hi > lo else int(np.argmax(sums))
    return round(i / 4, 2)


def fetch(query, count):
    print(f"Searching Openverse music for: {query}")
    params = {
        "q": query, "category": "music", "license_type": "commercial,modification",
        "page_size": 20,  # the most Openverse allows without an API key
    }
    results = get_json(API + "?" + urllib.parse.urlencode(params)).get("results", [])

    folder = MUSIC_DIR / slugify(query)
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.iterdir():  # a rerun replaces the previous set
        if old.is_file():
            old.unlink()

    credits = []
    for item in results:
        if len(credits) == count:
            break
        if item.get("license") not in OK_LICENSES or not item.get("url"):
            continue
        if (item.get("duration") or 0) < MIN_SECONDS * 1000:
            continue
        ext = (item.get("filetype") or "").lower()
        ext = ext if ext in {"mp3", "ogg", "wav", "flac", "m4a"} else "mp3"
        name = f"{len(credits) + 1:02d}-{slugify(item.get('title') or 'track')[:50]}.{ext}"
        dest = folder / name
        try:
            download(item["url"], dest)
            start = best_start(dest)
        except Exception as exc:
            print(f"  skipped {item.get('title')}: {exc}", file=sys.stderr)
            dest.unlink(missing_ok=True)
            continue
        time.sleep(1)  # be polite to the hosts
        credits.append({
            "file": name,
            "title": item.get("title") or "Untitled",
            "artist": item.get("creator") or "Unknown",
            "license": license_label(item),
            "license_url": item.get("license_url", ""),
            "source": item.get("foreign_landing_url", ""),
            "provider": item.get("source", ""),
            "seconds": round((item.get("duration") or 0) / 1000),
            "best_start": start,
        })
        print(f"  saved music/{folder.name}/{name}  [{credits[-1]['license']}]"
              f"  hook at {start}s")

    if not credits:
        print("  No suitably licensed tracks found; try a broader search.")
        return 0
    (folder / "credits.json").write_text(json.dumps(credits, indent=2, ensure_ascii=False) + "\n")
    lines = [f"# Music credits: {query}", ""]
    for c in credits:
        lines.append(f"- **{c['file']}**: \"{c['title']}\" by {c['artist']}, {c['license']}, "
                     f"{c['seconds']}s, hook at {c['best_start']}s, {c['source']}")
    (folder / "credits.md").write_text("\n".join(lines) + "\n")
    return len(credits)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", help="what kind of music, e.g. 'epic hip hop'; "
                                  "separate several searches with ';'")
    ap.add_argument("--count", type=int, default=3, help="tracks to keep per search (default 3)")
    args = ap.parse_args()
    queries = [q.strip() for q in args.query.split(";") if q.strip()]
    total = 0
    for i, q in enumerate(queries):
        if i:
            time.sleep(4)  # stay well under Openverse's anonymous rate limit
        try:
            total += fetch(q, args.count)
        except Exception as exc:
            print(f"  search '{q}' failed: {exc}", file=sys.stderr)
    print(f"Done: {total} track(s) saved.")
    if not total:
        sys.exit(1)


if __name__ == "__main__":
    main()
