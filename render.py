#!/usr/bin/env python3
"""Render a WWIT MMA News post from a post file.

Usage:
    python render.py posts/queue/2026-09-30-bjp-returns.json

A post file is a small JSON file:

    {
      "fighter":  "Jiri Prochazka",          # WikiPull search name
      "headline": "BJP Returns",             # 1 to 3 words
      "caption":  "BJP is back. ...",        # the story, in your words
      "sources":  ["CBS Sports", "ESPN"],    # where the story came from
      "color":    "#d2202f",                 # optional, background
      "photo":    1                          # optional, which cutout to use
    }

Output goes to posts/<post name>/:
    post.png     1080x1350 image, ready for Instagram
    caption.txt  caption + source credit + photo credit
    post.json    the post file, for the record

The design matches the MMA post template: tag at top left, big Anton
headline, fighter cutout as large as possible without touching the text.
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
FONT = ROOT / "fonts" / "Anton-Regular.ttf"
W, H = 1080, 1350
TAG = "WWIT MMA NEWS"
TAG_X, TAG_Y, TAG_H, TAG_SIZE = 60, 60, 70, 38
TOP_Y = 160          # where the headline's capitals start
LEAD = 0.16          # space between lines, as a share of capital height
MAX_TEXT_W = 980     # widest a headline line may be
MAX_BLOCK_H = 440    # tallest the whole headline block may be
MARGIN = 28          # gap kept between the text and the fighter
MIN_SHOW = 0.8       # share of the fighter that must stay in frame
DEFAULT_COLOR = "#d2202f"


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


def layout_headline(words):
    """Pick the biggest size that fits the width and height limits."""
    size = 340.0
    for w in words:
        width = font(size).getlength(w)
        if width > MAX_TEXT_W:
            size = min(size, size * MAX_TEXT_W / width)
    ratio = cap_height(100) / 100
    size = min(size, MAX_BLOCK_H / (ratio * (len(words) + (len(words) - 1) * LEAD)))
    cap = cap_height(size)
    baselines = [TOP_Y + cap + i * cap * (1 + LEAD) for i in range(len(words))]
    return size, baselines


def tag_width():
    return int(font(TAG_SIZE).getlength(TAG) + 60)


def draw_text_layer(draw, words, size, baselines, fg, bg, light):
    f = font(size)
    for w, y in zip(words, baselines):
        draw.text((W / 2, y), w, font=f, fill=fg, anchor="ms")
    tw = tag_width()
    draw.rounded_rectangle([TAG_X, TAG_Y, TAG_X + tw, TAG_Y + TAG_H], radius=10, fill=fg)
    tf = font(TAG_SIZE)
    cap = cap_height(TAG_SIZE)
    draw.text((TAG_X + tw / 2, TAG_Y + TAG_H / 2 + cap / 2), TAG, font=tf,
              fill=(255, 255, 255) if light else bg, anchor="ms")


def text_bottoms(words, size, baselines):
    """Lowest painted pixel of the headline and tag, per column (-1 = empty)."""
    mask = Image.new("L", (W, H), 0)
    draw_text_layer(ImageDraw.Draw(mask), words, size, baselines, 255, 255, False)
    draw = ImageDraw.Draw(mask)
    draw.rectangle([TAG_X, TAG_Y, TAG_X + tag_width(), TAG_Y + TAG_H], fill=255)
    a = np.asarray(mask) > 20
    rows = np.arange(H)[:, None]
    return np.where(a.any(axis=0), (a * rows).max(axis=0), -1)


def place_fighter(cut, bottoms):
    """Largest size and highest spot where the fighter never touches the text."""
    s = min(W * 0.96 / cut.width, H * 1.6 / cut.height)
    for _ in range(30):
        w2, h2 = max(1, round(cut.width * s)), max(1, round(cut.height * s))
        scaled = cut.resize((w2, h2), Image.LANCZOS)
        alpha = np.asarray(scaled.getchannel("A")) > 40
        has = alpha.any(axis=0)
        tops = np.where(has, alpha.argmax(axis=0), -1)
        x0 = (W - w2) // 2
        y = H - h2  # default: bottom edge on the bottom of the post
        for i in np.nonzero(has)[0]:
            col = x0 + i
            if 0 <= col < W and bottoms[col] >= 0:
                y = max(y, bottoms[col] + MARGIN - tops[i])
        if (H - y) / h2 >= MIN_SHOW or s < 0.05:
            return scaled, x0, int(y)
        s *= 0.95
    return scaled, x0, int(y)


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
    light = is_light(bg)
    fg = (17, 17, 17) if light else (255, 255, 255)

    size, baselines = layout_headline(words)
    img = Image.new("RGBA", (W, H), bg + (255,))
    with Image.open(cut_path) as cut:
        fighter, x, y = place_fighter(cut.convert("RGBA"), text_bottoms(words, size, baselines))
    img.paste(fighter, (x, y), fighter)  # paste clips whatever runs off the bottom
    draw_text_layer(ImageDraw.Draw(img), words, size, baselines, fg, bg, light)

    name = spec_path.stem
    out = ROOT / "posts" / name
    out.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out / "post.png", optimize=True)

    lines = [spec["caption"].strip(), ""]
    if spec.get("sources"):
        lines.append("📰 Source: " + ", ".join(spec["sources"]))
    credit = photo_credit(folder, cut_path.name)
    if credit:
        lines.append("📸 Photo: " + credit)
    (out / "caption.txt").write_text("\n".join(lines).strip() + "\n")
    (out / "post.json").write_text(json.dumps({**spec, "photo_file": cut_path.name}, indent=2,
                                              ensure_ascii=False) + "\n")
    print(f"Rendered posts/{name}/post.png")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for arg in sys.argv[1:]:
        render(arg)
