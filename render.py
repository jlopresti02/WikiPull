#!/usr/bin/env python3
"""Render a WWIT MMA News post (and optionally a Reel) from a post file.

Usage:
    python render.py posts/queue/2026-09-30-bjp-returns.json

A post file is a small JSON file:

    {
      "fighter":  "Jiri Prochazka",          # WikiPull search name
      "headline": "BJP Returns",             # 1 to 3 words
      "caption":  "BJP is back. ...",        # the story, in your words
      "sources":  ["CBS Sports", "ESPN"],    # where the story came from
      "color":    "#d2202f",                 # optional, background
      "photo":    1,                         # optional, which cutout to use

      "reel":     true,                      # optional, also make a Reel video
      "music":    "music/track.mp3",         # optional, track in the repo
      "music_credit": "Track by Artist / CC BY 4.0",  # shown in the caption
      "music_start": 12.5,                   # optional, where in the track to start
      "seconds":  8                          # optional, Reel length (default 8)
    }

Output goes to posts/<post name>/:
    post.png     1080x1350 image for a feed post
    reel.mp4     1080x1920 video with music (only when "reel" is true)
    cover.png    Reel cover image (only when "reel" is true)
    caption.txt  caption + source, photo and music credits
    post.json    the post file, for the record

The design matches the MMA post template: tag at top left, big Anton
headline, fighter cutout as large as possible without touching the text.
"""

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
FONT = ROOT / "fonts" / "Anton-Regular.ttf"
TAG = "WWIT MMA NEWS"
TAG_X, TAG_H, TAG_SIZE = 60, 70, 38
LEAD = 0.16          # space between lines, as a share of capital height
MAX_TEXT_W = 980     # widest a headline line may be
MARGIN = 28          # gap kept between the text and the fighter
MIN_SHOW = 0.8       # share of the fighter that must stay in frame
DEFAULT_COLOR = "#d2202f"
FPS = 30


@dataclass(frozen=True)
class Layout:
    w: int
    h: int
    tag_y: int        # top of the WWIT MMA NEWS tag
    top_y: int        # where the headline's capitals start
    max_block_h: int  # tallest the whole headline block may be


# Feed post, 4:5.
POST = Layout(1080, 1350, tag_y=60, top_y=160, max_block_h=440)
# Reel, 9:16. Content starts lower to clear Instagram's top bar, and also
# sits inside the 4:5 middle crop that the profile grid shows.
REEL = Layout(1080, 1920, tag_y=330, top_y=430, max_block_h=470)


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def is_light(rgb):
    r, g, b = (c / 255 for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.6


def font(size):
    return ImageFont.truetype(str(FONT), max(1, int(round(size))))


def cap_height(size):
    # Height of a capital letter above the baseline, measured from the font
    return -font(size).getbbox("H", anchor="ls")[1]


def layout_headline(words, L):
    """Pick the biggest size that fits the width and height limits."""
    size = 340.0
    for w in words:
        width = font(size).getlength(w)
        if width > MAX_TEXT_W:
            size = min(size, size * MAX_TEXT_W / width)
    ratio = cap_height(100) / 100
    size = min(size, L.max_block_h / (ratio * (len(words) + (len(words) - 1) * LEAD)))
    cap = cap_height(size)
    baselines = [L.top_y + cap + i * cap * (1 + LEAD) for i in range(len(words))]
    return size, baselines


def tag_width():
    return int(font(TAG_SIZE).getlength(TAG) + 60)


def draw_text_layer(draw, L, words, size, baselines, fg, bg, light):
    f = font(size)
    for w, y in zip(words, baselines):
        draw.text((L.w / 2, y), w, font=f, fill=fg, anchor="ms")
    tw = tag_width()
    draw.rounded_rectangle([TAG_X, L.tag_y, TAG_X + tw, L.tag_y + TAG_H], radius=10, fill=fg)
    cap = cap_height(TAG_SIZE)
    draw.text((TAG_X + tw / 2, L.tag_y + TAG_H / 2 + cap / 2), TAG, font=font(TAG_SIZE),
              fill=(255, 255, 255) if light else bg, anchor="ms")


def text_bottoms(L, words, size, baselines):
    """Lowest painted pixel of the headline and tag, per column (-1 = empty)."""
    mask = Image.new("L", (L.w, L.h), 0)
    draw = ImageDraw.Draw(mask)
    draw_text_layer(draw, L, words, size, baselines, 255, 255, False)
    draw.rectangle([TAG_X, L.tag_y, TAG_X + tag_width(), L.tag_y + TAG_H], fill=255)
    a = np.asarray(mask) > 20
    rows = np.arange(L.h)[:, None]
    return np.where(a.any(axis=0), (a * rows).max(axis=0), -1)


def place_fighter(L, cut, bottoms):
    """Largest size and highest spot where the fighter never touches the text.

    Returns (scale, x, y) for the cutout.
    """
    s = min(L.w * 0.96 / cut.width, L.h * 1.6 / cut.height)
    y = 0
    for _ in range(30):
        w2, h2 = max(1, round(cut.width * s)), max(1, round(cut.height * s))
        alpha = np.asarray(cut.resize((w2, h2), Image.BILINEAR).getchannel("A")) > 40
        has = alpha.any(axis=0)
        tops = np.where(has, alpha.argmax(axis=0), -1)
        x0 = (L.w - w2) // 2
        y = L.h - h2  # default: bottom edge on the bottom of the frame
        for i in np.nonzero(has)[0]:
            col = x0 + i
            if 0 <= col < L.w and bottoms[col] >= 0:
                y = max(y, bottoms[col] + MARGIN - tops[i])
        if (L.h - y) / h2 >= MIN_SHOW or s < 0.05:
            break
        s *= 0.95
    return s, (L.w - round(cut.width * s)) // 2, int(y)


class Scene:
    """Everything needed to draw one post in one layout."""

    def __init__(self, L, words, bg, cut):
        self.L, self.words, self.bg, self.cut = L, words, bg, cut
        self.light = is_light(bg)
        self.fg = (17, 17, 17) if self.light else (255, 255, 255)
        self.size, self.baselines = layout_headline(words, L)
        self.scale, self.x, self.y = place_fighter(
            L, cut, text_bottoms(L, words, self.size, self.baselines))
        self.text = Image.new("RGBA", (L.w, L.h), (0, 0, 0, 0))
        draw_text_layer(ImageDraw.Draw(self.text), L, words, self.size, self.baselines,
                        self.fg, bg, self.light)

    def frame(self, zoom=1.0, text_alpha=1.0):
        """Draw the post. zoom < 1 shrinks the fighter toward his bottom edge,
        so he only ever moves away from the headline."""
        L = self.L
        img = Image.new("RGBA", (L.w, L.h), self.bg + (255,))
        s = self.scale * zoom
        w2, h2 = max(1, round(self.cut.width * s)), max(1, round(self.cut.height * s))
        full_w = round(self.cut.width * self.scale)
        full_h = round(self.cut.height * self.scale)
        fighter = self.cut.resize((w2, h2), Image.LANCZOS)
        x = self.x + (full_w - w2) // 2
        y = self.y + (full_h - h2)  # keep the bottom edge fixed
        img.paste(fighter, (x, y), fighter)
        if text_alpha >= 1:
            img.alpha_composite(self.text)
        elif text_alpha > 0:
            t = self.text.copy()
            t.putalpha(t.getchannel("A").point(lambda v: int(v * text_alpha)))
            img.alpha_composite(t)
        return img.convert("RGB")


def ease_out(t):
    return 1 - (1 - t) ** 3


def make_reel(scene, out, spec):
    """Write reel.mp4: the fighter slowly pushes in, headline punches in,
    with the music track (or silence) underneath."""
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is needed to make a Reel")
    seconds = float(spec.get("seconds", 8))
    frames = int(seconds * FPS)
    music = spec.get("music")
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{scene.L.w}x{scene.L.h}",
           "-r", str(FPS), "-i", "-"]
    if music:
        track = ROOT / music
        if not track.exists():
            sys.exit(f"music file not found: {music}")
        start = float(spec.get("music_start", 0))
        cmd += ["-ss", str(start), "-t", str(seconds), "-i", str(track)]
        fade_out = max(0.0, seconds - 1.2)
        cmd += ["-af", f"afade=t=in:d=0.3,afade=t=out:st={fade_out}:d=1.2"]
    else:
        cmd += ["-f", "lavfi", "-t", str(seconds), "-i", "anullsrc=r=44100:cl=stereo"]
    cmd += ["-map", "0:v", "-map", "1:a", "-shortest",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            str(out / "reel.mp4")]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    punch = int(0.35 * FPS)  # headline fades/punches in over the first moment
    for i in range(frames):
        t = i / max(1, frames - 1)
        zoom = 0.93 + 0.07 * ease_out(t)
        text_alpha = min(1.0, (i + 1) / punch)
        proc.stdin.write(scene.frame(zoom, text_alpha).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("ffmpeg failed to write the Reel")
    scene.frame(1.0, 1.0).save(out / "cover.png", optimize=True)


def photo_credit(folder, cut_name):
    credits = json.loads((folder / "credits.json").read_text())
    stem = Path(cut_name).stem
    for c in credits:
        if Path(c["file"]).stem == stem:
            return f"{c['author']} / {c['license']}"
    return None


def render(spec_path):
    spec_path = Path(spec_path)
    spec = json.loads(spec_path.read_text())
    words = [w.upper() for w in spec["headline"].split()]
    if not 1 <= len(words) <= 3:
        sys.exit(f"{spec_path.name}: headline must be 1 to 3 words")

    folder = ROOT / "images" / slugify(spec["fighter"])
    cutouts = sorted((folder / "cutouts").glob("*.png"))
    if not cutouts:
        sys.exit(f"{spec_path.name}: no cutouts for {spec['fighter']}; fetch them first")
    pick = int(spec.get("photo", 1))
    cut_path = cutouts[min(max(pick, 1), len(cutouts)) - 1]
    bg = hex_rgb(spec.get("color", DEFAULT_COLOR))

    name = spec_path.stem
    out = ROOT / "posts" / name
    out.mkdir(parents=True, exist_ok=True)

    with Image.open(cut_path) as im:
        cut = im.convert("RGBA")
    Scene(POST, words, bg, cut).frame().save(out / "post.png", optimize=True)
    print(f"Rendered posts/{name}/post.png")
    if spec.get("reel"):
        make_reel(Scene(REEL, words, bg, cut), out, spec)
        print(f"Rendered posts/{name}/reel.mp4")

    lines = [spec["caption"].strip(), ""]
    if spec.get("sources"):
        lines.append("📰 Source: " + ", ".join(spec["sources"]))
    credit = photo_credit(folder, cut_path.name)
    if credit:
        lines.append("📸 Photo: " + credit)
    if spec.get("reel") and spec.get("music_credit"):
        lines.append("🎵 Music: " + spec["music_credit"])
    (out / "caption.txt").write_text("\n".join(lines).strip() + "\n")
    (out / "post.json").write_text(json.dumps({**spec, "photo_file": cut_path.name}, indent=2,
                                              ensure_ascii=False) + "\n")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for arg in sys.argv[1:]:
        render(arg)
