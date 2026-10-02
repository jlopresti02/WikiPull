#!/usr/bin/env python3
"""Generate images with Google Gemini and save them into gemini/images/.

Requests come from either:
  - a JSON file in gemini/requests/ (one request, or a list of them):
        {"name": "octagon-empty", "prompt": "An empty MMA cage under arena lights...",
         "count": 2, "aspect_ratio": "9:16"}
  - the command line:  python gemini_images.py --name NAME --prompt "..." [--count N]

Each image is saved as gemini/images/<name>/<name>-<n>.png with a prompt.txt
next to it. Processed request files are moved to gemini/requests/done/.
Results and errors are appended to gemini/log.txt.

Needs the GEMINI_API_KEY environment variable (a GitHub Actions secret).
The model can be changed with GEMINI_IMAGE_MODEL (a GitHub Actions variable).

Generated images are AI-made: use them for backgrounds, arenas, crowds,
generic referees and graphics, never as photos of real, named people.
"""

import argparse
import base64
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GEM = ROOT / "gemini"
REQUESTS = GEM / "requests"
DONE = REQUESTS / "done"
IMAGES = GEM / "images"
LOG = GEM / "log.txt"

MODEL = os.environ.get("GEMINI_IMAGE_MODEL") or "gemini-2.5-flash-image"
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
RATIOS = {"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}
EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "image"


def log(line):
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(line)
    with LOG.open("a") as f:
        f.write(f"{stamp}  {line}\n")


def generate(prompt, aspect_ratio):
    """Return a list of (mime, bytes) images for one Gemini call."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set (add it as a repository secret)")
    gen_config = {"responseModalities": ["IMAGE"]}
    if aspect_ratio:
        gen_config["imageConfig"] = {"aspectRatio": aspect_ratio}
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": gen_config,
    }).encode()
    req = urllib.request.Request(
        API.format(model=MODEL), data=body, method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": key})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            if e.code in (429, 500, 503) and attempt < 2:
                time.sleep(15 * (attempt + 1))
                continue
            raise RuntimeError(f"Gemini HTTP {e.code}: {detail}") from None
    images, notes = [], []
    for cand in data.get("candidates", []):
        for part in (cand.get("content") or {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                mime = inline.get("mimeType") or inline.get("mime_type") or "image/png"
                images.append((mime, base64.b64decode(inline["data"])))
            elif part.get("text"):
                notes.append(part["text"].strip())
        if not images and cand.get("finishReason") not in (None, "STOP"):
            notes.append(f"finishReason={cand['finishReason']}")
    if not images:
        block = (data.get("promptFeedback") or {}).get("blockReason")
        raise RuntimeError("no image returned"
                           + (f" (blocked: {block})" if block else "")
                           + (f": {' | '.join(notes)[:300]}" if notes else ""))
    return images


def run_request(req):
    prompt = (req.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("request has no prompt")
    name = slugify(req.get("name") or prompt[:40])
    count = max(1, min(int(req.get("count", 1)), 4))
    ratio = req.get("aspect_ratio") or "9:16"
    if ratio not in RATIOS:
        raise ValueError(f"aspect_ratio must be one of {sorted(RATIOS)}")
    folder = IMAGES / name
    folder.mkdir(parents=True, exist_ok=True)
    existing = len([p for p in folder.iterdir() if p.suffix in EXT.values()])
    saved = 0
    while saved < count:
        for mime, raw in generate(prompt, ratio):
            if saved >= count:
                break
            n = existing + saved + 1
            out = folder / f"{name}-{n}{EXT.get(mime, '.png')}"
            out.write_bytes(raw)
            saved += 1
            log(f"OK   {out.relative_to(ROOT)}  ({len(raw) // 1024} KB, {MODEL})")
    (folder / "prompt.txt").write_text(
        f"model: {MODEL}\naspect_ratio: {ratio}\n\n{prompt}\n")
    return saved


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name")
    ap.add_argument("--prompt")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--aspect-ratio", default="9:16")
    args = ap.parse_args()
    GEM.mkdir(exist_ok=True)

    failures = 0
    if args.prompt:
        try:
            run_request({"name": args.name, "prompt": args.prompt,
                         "count": args.count, "aspect_ratio": args.aspect_ratio})
        except Exception as exc:
            failures += 1
            log(f"FAIL {args.name or args.prompt[:40]}: {exc}")

    DONE.mkdir(parents=True, exist_ok=True)
    for path in sorted(REQUESTS.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            for req in (data if isinstance(data, list) else [data]):
                try:
                    run_request(req)
                except Exception as exc:
                    failures += 1
                    log(f"FAIL {path.name} / {req.get('name', '?')}: {exc}")
        except Exception as exc:
            failures += 1
            log(f"FAIL {path.name}: {exc}")
        path.rename(DONE / path.name)

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
